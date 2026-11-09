"""Build the local Chroma index from data/lumabox_policies.txt and
homework/model_prices.xlsx (one collection holds both).

Unlike a clean JSON array, this is one raw text file - real documents
usually arrive this way. You have to decide how to split it into
retrievable pieces before you can embed anything.

Run this once (and again any time the documents change):
    python -m src.ingest
"""
import hashlib
from pathlib import Path

import chromadb
import pandas as pd
from sentence_transformers import SentenceTransformer

ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = ROOT / "data" / "lumabox_policies.txt"
PRICES_PATH = ROOT / "homework" / "model_prices.xlsx"
DB_PATH = ROOT / "chroma_db"
COLLECTION_NAME = "policies"

# A short fingerprint of the source documents. It changes whenever any of
# them change, and every answer logs it, so a wrong answer can be traced back
# to the exact knowledge it came from.
KB_VERSION = hashlib.sha256(DATA_PATH.read_bytes() + PRICES_PATH.read_bytes()).hexdigest()[:12]

# TODO I1: load the embedding model "sentence-transformers/all-MiniLM-L6-v2"
# with SentenceTransformer, on the CPU (device="cpu").
embedding_model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2", device="cpu")


def chunk_documents():
    """Split the raw policy text into a list of chunk strings.

    TODO I2: open data/lumabox_policies.txt and look at its shape first. Then
    return one string per policy:
      - policies are separated by blank lines
      - strip surrounding whitespace from each piece
      - drop the title line at the top of the file (a heading with no body)
    """
    text = DATA_PATH.read_text(encoding="utf-8")
    raw_chunks = [c.strip() for c in text.split("\n\n")]
    return [c for c in raw_chunks if "\n" in c]


def price_sentences():
    """One sentence per row of the price table.

    Embeddings work on sentences, not table cells. The model column is kept
    as is (serial code and name run together, e.g. "LMX-201 LumaBox X100").
    """
    table = pd.read_excel(PRICES_PATH)
    return [f"The {row.model} costs {int(row.price)} THB." for row in table.itertuples()]


def build_index():
    chunks = chunk_documents()

    # TODO I3: open a persistent Chroma client that stores its files at
    # DB_PATH, delete any old collection called COLLECTION_NAME (so running
    # this twice is safe), then create a fresh collection that compares
    # vectors by cosine distance and records KB_VERSION in its metadata.
    client = chromadb.PersistentClient(path=str(DB_PATH))
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass
    collection = client.create_collection(
        COLLECTION_NAME, metadata={"hnsw:space": "cosine", "kb_version": KB_VERSION}
    )

    # TODO I4: embed the chunks (with normalize_embeddings=True) and add them to the
    # collection with generic ids: chunk_0, chunk_1, ... There's no natural
    # "returns"/"delivery" label anymore, because the chunks were derived by
    # splitting, not handed to you pre-labeled.
    embeddings = embedding_model.encode(chunks, normalize_embeddings=True).tolist()
    ids = [f"chunk_{i}" for i in range(len(chunks))]
    collection.add(
        ids=ids,
        documents=chunks,
        embeddings=embeddings,
        metadatas=[{"source": "policy"}] * len(chunks),
    )

    # Prices go into the same collection, so one search covers both sources.
    prices = price_sentences()
    collection.add(
        ids=[f"price_{i}" for i in range(len(prices))],
        documents=prices,
        embeddings=embedding_model.encode(prices, normalize_embeddings=True).tolist(),
        metadatas=[{"source": "price"}] * len(prices),
    )

    print(
        f"Indexed {len(chunks)} policy chunks and {len(prices)} prices into {DB_PATH} "
        f"(kb_version {KB_VERSION})"
    )


if __name__ == "__main__":
    build_index()
