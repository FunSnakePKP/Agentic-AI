# Monitoring report

## Part 1 — In-class review (Module 5, Tasks 1–3)

9 CLI turns, prompt v1, kb `6ebf6d0ba0cb`. `python -m src.review --sample 5`:
refusal rate 22%, latency median 270 ms, p95 525 ms, 7 flagged turns.

Three flagged turns, classified:

| trace id | question | failure type | evidence in the trace | where I'd fix it |
|---|---|---|---|---|
| `c8c91d5fc1e9` | I forgot my pasword | **Wrongly refused** | Top similarity 0.189, below the 0.25 threshold. The right chunk (`chunk_4`, Account) *was* the top hit; the typo just pushed the score down. | Policy/retrieval: spelling correction or keyword search, rather than lowering the threshold for everyone. Add the question to `golden.xlsx` first. |
| `06405b854704` | Do you offer exchanges instead of refunds? | **Knowledge gap** | Retrieved Returns and Refund chunks (0.416), and the model said "I do not know". No policy mentions exchanges. | The documents: LumaBox's support team writes an exchange policy, then re-run `python -m src.ingest`. |
| `a80f68899fa0` | Is tech support open at 3am? | **Generation error** | The right chunk was retrieved (`chunk_3`, "Available 24/7, every day", 0.549), but the model said "I do not know". | A new prompt version (or a larger model), checked with the quality gate. |

Also seen in the random sample (no rule flagged it):
`450b55061190` "How much is the LumaBox X300?" → **9990 THB**, which is the
*Pro* X300's price; the X300 costs 7990. It retrieved `price_4` (Pro X300) and
`price_0` (X100), not `price_3` (X300). That's a **retrieval miss**: the
embedding model treats sibling model names as near-identical. Fix in
retrieval (keyword/hybrid search).
