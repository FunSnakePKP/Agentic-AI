# Exercise 1 — A second knowledge source: prices

## What changed

- **Knowledge** (`src/ingest.py`): `price_sentences()` reads
  `homework/model_prices.xlsx` with `pandas.read_excel` and turns each row
  into `"The {model} costs {price} THB."` (model column kept as is, e.g.
  `The LMX-201 LumaBox X100 costs 2990 THB.`). The 8 sentences are added to
  the **same** `policies` collection as the 5 policy chunks, with ids
  `price_0`…`price_7` and `metadatas={"source": "price"}` (policy chunks get
  `{"source": "policy"}`). `KB_VERSION` now hashes both source files, so it
  changed from `2f8f4e43e5ae` to `6ebf6d0ba0cb`.
- **Retrieval** (`src/rag.py`): each hit now also carries its `source`.
- **Policy** (`AGENT_POLICY.md`, version 2): new rules P9 (prices only from
  the table; refuse any product not in it) and P10 (price sources shown);
  P1 scope now includes listed prices; known gaps updated.
- **Enforcement** (`src/rag.py`): `should_refuse(hits, question)` adds a P9
  check. When the top hit is a price row, the bot refuses unless the question
  names a product from a retrieved price row (`names_product()`: the model code
  or a name word such as `x100`, `sonabox` or `screen`, ignoring the brand
  word "lumabox" shared by every model). `rag_answer()` and
  `tests/test_golden.py` pass the question in. There is still one collection
  and one search, with no routing.
- **Golden dataset** (`tests/golden.xlsx`): new category `price`, 12 rows:
  - `price_x100` (3 wordings) → `2990`
  - `price_screen` (3 wordings) → `6990`
  - `price_sonabox` (3 wordings, a product that isn't a LumaBox but *is* in the table) → `1990`
  - `price_not_listed` (iPhone 15, Galaxy S24, PlayStation 5) → refuse
  - The `out_of_scope_tricky` X999 row's `known_issue` was removed: it now
    passes (see below), and strict xfail flagged it as unexpectedly passing.

## Why similarity alone wasn't enough

After adding the prices, products that aren't in the table still look like
price questions to the embedding model:

| question | top hit | similarity |
|---|---|---|
| How much is an iPhone 15? | price_6 (SonaCube Earphone) | 0.41 |
| What's the price of a Samsung Galaxy S24? | price_6 | 0.44 |
| How much does a PlayStation 5 cost? | price_4 (Pro X300) | 0.35 |
| How much is the LumaBox X999? | price_1 (X200) | 0.72 |

All of them score above the 0.25 threshold, and as high as real in-scope
questions (lowest 0.42), so raising the threshold would break P2. With only
the threshold, pytest failed the 3 `price_not_listed` refuse rows. That's
why P9 is enforced with the product-name check.

## Gate output — before (price rows added, prices not yet ingested)

```
category                   now  baseline
account                    1/3       1/3
delivery                   1/3       1/3
out of scope               6/6       6/6
price                     3/12       new
refund                     3/3       3/3
returns                    3/6       3/6
technical support          1/3       1/3
overall                  18/36
```

The 3 price passes were the `price_not_listed` refusals; all 9 real price
questions were refused or got "I do not know". pytest: `16 failed, 46 passed, 3 xfailed`
(the 9 price rows had no evidence to retrieve, and 7 of them were wrongly refused).

## Gate output — after

```
category                   now  baseline
account                    1/3       1/3
delivery                   1/3       1/3
out of scope               6/6       6/6
price                    11/12       new
refund                     3/3       3/3
returns                    3/6       3/6
technical support          1/3       1/3
overall                  26/36

  [price] Price of the SonaBox speaker please
      -> I do not know

GATE PASSED: no category got worse than the baseline.
```

pytest: `63 passed, 2 xfailed` (the 2 xfails are the moon and invest rows,
which are still known issues for policy questions).

No existing category moved, so the new baseline was accepted. The one
price failure is a generation miss: the right row was retrieved, but
flan-t5 said "I do not know". It declined, so no price was invented.

## What the bot says now

| question | answer | sources |
|---|---|---|
| How much is the LumaBox X999? | **[refused]** I don't have information about that. For anything else, please contact LumaBox technical support. | price_1 (0.72), price_0 (0.71) |
| How much is the LumaBox X100? | 2990 THB | price_0, price_1 |
| How much is the SonaBox Speaker? | 1990 THB | price_5, price_6 |
| How much is an iPhone 15? | **[refused]** | price_6, price_7 |

**X999:** the question retrieves real price rows (X200, X100) with high
similarity, so without P9 it reaches the generator. With prompt v1 the model
happens to say "I do not know", but that depends on the prompt. Module 2
showed that prompt v2 invents "$99" for the same question. With P9 the
refusal is now decided in code: no retrieved row names "X999", so the
generator is never called, whatever the prompt says.

## Remaining limitations

- The name check is lexical: a question that names a listed product and
  also asks about another one passes, and generic name words ("screen",
  "speaker") can match unrelated questions.
- Sibling models (X200 / X250, X300 / Pro X300) can retrieve each other's
  rows. Hybrid search (the Challenge) is the proper fix.
