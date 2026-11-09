# Challenge — Exact model names (hybrid search)

## Why it happens (the plan)

An embedding model turns text into a vector that captures *meaning*, and to
it "LumaBox X200", "X250" and "X300" mean almost the same thing: a LumaBox
product. Serial codes like "LMX-201" carry no meaning at all, so the vector
for "How much does model LMX-201 cost?" lands near *every* price row, and
the closest one is effectively random. Vector search is good at paraphrases
but bad at exact identifiers; keyword search is the opposite. So I'll add a
keyword (BM25) match on the same documents alongside vector search, and let
an exact identifier match go first.

## Golden rows first

16 new `price` rows (`price_exact_*`): for each of the 8 products, "How much
is the {name}?" and "How much does model {serial} cost?". Before the fix, 4
failed and were marked `known_issue`:

| question | what went wrong |
|---|---|
| How much does model LMX-201 cost? | retrieved LMX-202/203 → P9 refused |
| How much does model LMX-204 cost? | retrieved a sibling → P9 refused |
| How much does model LMX-205 cost? | retrieved a sibling → P9 refused |
| How much is the LumaBox X300? | retrieved the **Pro** X300 row → answered **9990** (should be 7990) |

The X300 row shows the limit of marking a whole row `known_issue`: its
retrieval test failed, but its "not refused" test passed (the bot answered,
wrongly), so strict xfail reported an unexpected pass. The rows and the fix
are therefore in the same commit, so that no commit has a red pytest.

## The fix (`src/rag.py`)

- `keyword_match()`: a small BM25 over the same documents (no new
  dependency). It steps in only when the question contains a **model
  identifier** (a token with letters *and* digits, like `x300` or
  `lmx-201`) that appears in some document. Order numbers ("#48213"), "24/7"
  and unknown models ("X999", "S24") never trigger it.
- Among documents with that identifier, BM25 picks the best. Its length
  normalization makes "LumaBox X300" prefer the shorter X300 row over
  "Pro X300", and the extra word "pro" makes "Pro X300" prefer its own row.
- `retrieve()` puts that document first (with its real cosine similarity),
  then fills the rest with the vector results. There's still one collection
  and one search pipeline, with no price routing.

## Result

- All 4 rows then failed as **unexpectedly passing** (XPASS strict), so I
  removed their `known_issue`.
- pytest: **107 passed, 2 xfailed** (the 2 are the moon and invest rows).
- Gate: price **11/12 → 27/28**, every other category unchanged:

```
category                   now  baseline
account                    2/6       2/6
delivery                   1/3       1/3
exchange                   2/3       2/3
out of scope               6/6       6/6
price                    27/28     11/12
refund                     3/3       3/3
returns                    3/6       3/6
technical support          1/3       1/3
overall                  45/58
GATE PASSED: no category got worse than the baseline.
```

This also fixes two failures from the monitoring report: turn 8 ("How much
does model LMX-201 cost?", which was refused) and the in-class X300 wrong
price.

# Challenge — CI on GitHub

Pushed to https://github.com/FunSnakePKP/Agentic-AI (branch `main`). The
first Actions run (#1, commit `99e121c`) passed all three jobs in 4m 50s:
Tests and quality gate (ingest, pytest, gate against the committed
baseline), Build container image, and Deploy to production.

Screenshot: [`ci_green_run.png`](ci_green_run.png)

The two warnings on the run say GitHub is moving its actions from Node.js 20
to Node.js 24. They come from GitHub's own actions (`checkout@v4`,
`setup-python@v5`, `cache@v4`), not from this project, and they don't
affect the result.
