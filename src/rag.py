"""The agent: retrieval, a versioned prompt, a policy check, and generation.

Module 1 builds the retrieval half (TODO R1-R2), Module 2 the generation
half with a versioned prompt (TODO R3-R4) and the policy check
(TODO R5-R6). rag_answer() at the bottom wires them together
and records what the monitoring in Module 5 needs. It's already written.
"""
import difflib
import math
import re
import time
from pathlib import Path

import chromadb
import torch
from sentence_transformers import SentenceTransformer
from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "chroma_db"
PROMPTS_DIR = ROOT / "prompts"
COLLECTION_NAME = "policies"

EMBEDDING_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
GENERATOR_MODEL_NAME = "google/flan-t5-base"

# Which prompt in prompts/ is live. Changing it is a release: run the
# quality gate first (Module 3, Task 3) and record the change in prompts/CHANGELOG.md.
PROMPT_VERSION = "v1"

# What the bot says when its policy says not to answer (AGENT_POLICY.md, P3-P4).
REFUSAL_MESSAGE = (
    "I don't have information about that. "
    "For anything else, please contact LumaBox technical support."
)

device = "cuda" if torch.cuda.is_available() else "cpu"


# ------------------------------------------------- Module 1: retrieval
# TODO R1: load the embedding model (EMBEDDING_MODEL_NAME, on the CPU), then
# connect to the collection ingest.py built: same path, same name, but get
# it rather than create it. If it says the collection doesn't exist, run
# `python -m src.ingest` first.
embedding_model = SentenceTransformer(EMBEDDING_MODEL_NAME, device="cpu")
_client = chromadb.PersistentClient(path=str(DB_PATH))
_collection = _client.get_collection(COLLECTION_NAME)

# Spelling correction (monitoring_report.md, Fix 2): a typo like "pasword"
# pushes similarity below the refusal threshold. Unknown words are replaced by
# the closest word in the knowledge base's own vocabulary. 0.85 is strict on
# purpose: at 0.8, "never" became "every" and "change" became "exchanges".
SPELLING_CUTOFF = 0.85

# Every document, loaded once for spelling correction and keyword search.
# The knowledge base is small (policy chunks + price rows), so this is cheap.
_ALL = _collection.get(include=["documents", "metadatas", "embeddings"])
_VOCABULARY = sorted({w for doc in _ALL["documents"] for w in re.findall(r"[a-z]+", doc.lower())})


def correct_spelling(text):
    """Replace unknown words (5+ letters) with the closest knowledge-base word."""
    def fix(match):
        word = match.group(0)
        lower = word.lower()
        if len(lower) < 5 or lower in _VOCABULARY:
            return word
        close = difflib.get_close_matches(lower, _VOCABULARY, n=1, cutoff=SPELLING_CUTOFF)
        return close[0] if close else word
    return re.sub(r"[A-Za-z]+", fix, text)


# Hybrid search (homework Challenge): to the embedding model, "X200" and
# "X250" mean nearly the same thing and serial codes like "LMX-201" mean
# nothing, so vector search returns a sibling product's price row. A keyword
# (BM25) search over the same documents matches them exactly. It only steps in
# when the question contains a model identifier (letters and digits together,
# e.g. "x300", "lmx-201") that appears in some document.
_TOKEN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
_IDENTIFIER = re.compile(r"(?=.*[a-z])(?=.*\d)")
_DOC_TOKENS = [_TOKEN.findall(doc.lower()) for doc in _ALL["documents"]]
_AVG_LEN = sum(map(len, _DOC_TOKENS)) / max(len(_DOC_TOKENS), 1)
_DOC_FREQ = {}
for _tokens in _DOC_TOKENS:
    for _t in set(_tokens):
        _DOC_FREQ[_t] = _DOC_FREQ.get(_t, 0) + 1


def _bm25(query_tokens, i, k1=1.5, b=0.75):
    """BM25 score of document i; shorter documents win ties ("X300" beats "Pro X300")."""
    tokens, n = _DOC_TOKENS[i], len(_DOC_TOKENS)
    score = 0.0
    for t in set(query_tokens):
        tf = tokens.count(t)
        if tf:
            idf = math.log(1 + (n - _DOC_FREQ[t] + 0.5) / (_DOC_FREQ[t] + 0.5))
            score += idf * tf * (k1 + 1) / (tf + k1 * (1 - b + b * len(tokens) / _AVG_LEN))
    return score


def keyword_match(query):
    """Index of the best document that contains a model identifier from the query, or None."""
    query_tokens = _TOKEN.findall(query.lower())
    identifiers = {t for t in query_tokens if _IDENTIFIER.match(t) and t in _DOC_FREQ}
    candidates = [i for i, tokens in enumerate(_DOC_TOKENS) if identifiers & set(tokens)]
    if not candidates:
        return None
    return max(candidates, key=lambda i: _bm25(query_tokens, i))


def retrieve(query, k=2):
    """Return the top-k chunks for a query.

    TODO R2: embed the query the same way the chunks were embedded
    (embedding_model, normalize_embeddings=True), then ask _collection for
    the k nearest chunks.

    Return a list of dicts, best match first, each with "id", "text" and
    "similarity" keys. Note that Chroma reports *distances*, not
    similarities.
    """
    query = correct_spelling(query)
    query_vector = embedding_model.encode(query, normalize_embeddings=True).tolist()
    results = _collection.query(
        query_embeddings=[query_vector],
        n_results=k,
        include=["documents", "distances", "metadatas"],
    )
    hits = []
    for doc_id, text, distance, meta in zip(
        results["ids"][0], results["documents"][0], results["distances"][0], results["metadatas"][0]
    ):
        hits.append({
            "id": doc_id,
            "text": text,
            "similarity": 1 - distance,
            "source": (meta or {}).get("source", "policy"),
        })

    # Hybrid: an exact keyword match on a model identifier goes first.
    best = keyword_match(query)
    if best is not None and (not hits or hits[0]["id"] != _ALL["ids"][best]):
        similarity = float(sum(q * d for q, d in zip(query_vector, _ALL["embeddings"][best])))
        exact = {
            "id": _ALL["ids"][best],
            "text": _ALL["documents"][best],
            "similarity": similarity,
            "source": (_ALL["metadatas"][best] or {}).get("source", "policy"),
        }
        hits = [exact] + [h for h in hits if h["id"] != exact["id"]][: k - 1]
    return hits


# ------------------------------------------------- Module 2: generation
# TODO R3: load the tokenizer and model for GENERATOR_MODEL_NAME
# (google/flan-t5-base) with transformers' AutoTokenizer and
# AutoModelForSeq2SeqLM. Move the model to `device` and put it in eval mode.
tokenizer = AutoTokenizer.from_pretrained(GENERATOR_MODEL_NAME)
generator = AutoModelForSeq2SeqLM.from_pretrained(GENERATOR_MODEL_NAME).to(device)
generator.eval()


def load_prompt(version):
    """Return the prompt template stored in prompts/answer_<version>.txt."""
    return (PROMPTS_DIR / f"answer_{version}.txt").read_text(encoding="utf-8").strip()


def build_prompt(question, context, version=None):
    """TODO R4: fill the template with the context and the question.

    The template comes from load_prompt(version or PROMPT_VERSION) and has
    {context} and {question} placeholders.
    """
    template = load_prompt(version or PROMPT_VERSION)
    return template.format(context=context, question=question)


def generate_answer(prompt):
    """TODO R4: run the model on the prompt and return its answer as text.

    - tokenize the prompt as PyTorch tensors on `device`, without truncating;
    - raise ValueError if it's longer than 512 tokens (flan-t5's input limit);
    - generate greedily (do_sample=False), at most 64 new tokens, inside
      torch.inference_mode();
    - decode the output, skipping special tokens.
    """
    inputs = tokenizer(prompt, return_tensors="pt", truncation=False).to(device)
    if inputs["input_ids"].shape[1] > 512:
        raise ValueError(
            "Prompt exceeds the 512 token budget. Reduce k or passage length."
        )
    with torch.inference_mode():
        output = generator.generate(**inputs, max_new_tokens=64, do_sample=False)
    return tokenizer.decode(output[0], skip_special_tokens=True)


# ------------------------------------------------- Module 2: policy
# TODO R5: choose the threshold from the similarity scores you printed in
# Module 1, Task 3: below every in-scope question, above the clearly
# out-of-scope ones.
# Module 1 scores: in-scope >= 0.42, clearly out-of-scope <= 0.10.
SIMILARITY_THRESHOLD = 0.25


# Words in a price row that don't identify one product: the brand name is in
# every LumaBox model (and in many policy questions), "pro" in many products.
GENERIC_PRODUCT_WORDS = {"lumabox", "pro"}
_PRICE_ROW = re.compile(r"^The (.+) costs \d+ THB\.$")


def _words(text):
    return set(re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)*", text.lower()))


def names_product(question, price_hit):
    """True when the question names the product in this price row.

    "LMX-202 LumaBox X200" is identified by "lmx-202" or "x200"; the shared
    brand word "lumabox" alone doesn't count.
    """
    match = _PRICE_ROW.match(price_hit["text"])
    if not match:
        return False
    return bool((_words(match.group(1)) - GENERIC_PRODUCT_WORDS) & _words(question))


def should_refuse(hits, question=None):
    """Decide whether the bot must refuse instead of answering.

    AGENT_POLICY.md P1: refuse when there are no hits, or when the top hit's
    similarity is below SIMILARITY_THRESHOLD.
    AGENT_POLICY.md P9: when the best match is a price row, refuse unless the
    question names a product from a retrieved price row. Products that
    aren't in the table ("iPhone 15", "LumaBox X999") still look like price
    questions to the embedding model, so similarity alone can't stop them.
    """
    if not hits or hits[0]["similarity"] < SIMILARITY_THRESHOLD:
        return True
    if question is not None and hits[0].get("source") == "price":
        price_hits = [h for h in hits if h.get("source") == "price"]
        return not any(names_product(question, h) for h in price_hits)
    return False


# ------------------------------------------------- the agent
def kb_version():
    """Which version of the knowledge base is being searched (set by ingest.py)."""
    return (_collection.metadata or {}).get("kb_version", "unknown")


def rag_answer(question, k=2, search_query=None, enforce_policy=True, prompt_version=None):
    """Answer a question and return everything a trace needs.

    enforce_policy=False skips the policy check (Module 2, Task 2 compares both).
    prompt_version overrides PROMPT_VERSION (the quality gate uses it).
    """
    version = prompt_version or PROMPT_VERSION
    started = time.perf_counter()
    hits = retrieve(search_query or question, k)
    retrieved = time.perf_counter()

    result = {
        "question": question,
        "hits": hits,
        "refused": False,
        "context": "",
        "prompt": None,
        "prompt_version": version,
        "kb_version": kb_version(),
        "models": {"embedding": EMBEDDING_MODEL_NAME, "generator": GENERATOR_MODEL_NAME},
    }
    if enforce_policy and should_refuse(hits, question):
        # Deterministic: the generator is never called.
        result.update(answer=REFUSAL_MESSAGE, refused=True)
    else:
        context = "\n".join(h["text"] for h in hits)
        prompt = build_prompt(question, context, version)
        result.update(context=context, prompt=prompt, answer=generate_answer(prompt))

    finished = time.perf_counter()
    result["timings_ms"] = {
        "retrieve": round((retrieved - started) * 1000),
        "generate": round((finished - retrieved) * 1000),
    }
    return result
