# Prompt changelog

Every prompt is a file in this folder, and `PROMPT_VERSION` in `src/rag.py`
says which one is live. Never edit a released prompt in place: add a new
version, run the quality gate (`python -m src.gate --prompt <version>`),
and record the result here. Rolling back is then a one-line change.

| Version | Status | What changed | Gate result |
|---|---|---|---|
| v1 | **live** | The original prompt: answer briefly, only from the context, say "I do not know" otherwise. | Baseline |
| v2 | **rejected** | Friendlier persona; "answer by meaning"; "always give a helpful, complete answer". Aimed at the "I do not know" replies to paraphrased questions. | GATE FAILED, 13/24 vs v1's 15/24. Worse: **out of scope** (6/6 → 3/6: invents "$99" for the X999 and answers the moon/invest questions) and **refund** (3/3 → 2/3: "8" without "business days"). Better: account 1/3 → 2/3, returns 3/6 → 4/6. |
