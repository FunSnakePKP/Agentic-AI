# LumaBox Support Bot: Behavior Policy

**Version 3** · Owner: the LumaBox support team · Reviewed with every release.

`data/lumabox_policies.txt` says *what LumaBox's rules are*, and
`homework/model_prices.xlsx` says *what LumaBox's products cost*. This document says
*how the bot behaves*: what it answers, what it refuses, and what it must
never do.

Every rule names **how it's enforced** and **what tests it**. A rule that
nothing enforces or tests is a wish, not a policy.

| # | Rule | Enforced by | Tested by |
|---|---|---|---|
| P1 | **Scope.** Answer only questions about LumaBox's customer policies (returns, delivery, refunds, technical support and accounts) and the prices of products in the price table. | Code: `should_refuse()` refuses when no retrieved chunk is similar enough (`SIMILARITY_THRESHOLD`). | Golden rows with `"expected_action": "refuse"` · `test_out_of_scope_is_refused` |
| P2 | **Don't over-refuse.** A fair paraphrase of a covered question gets an answer. | Code: the threshold is set below every in-scope question's score. | `test_in_scope_is_not_refused` |
| P3 | **Fixed refusal.** When the bot won't answer, it replies with `REFUSAL_MESSAGE` and never calls the model. | Code: `rag_answer()` | `test_out_of_scope_is_refused` · gate category `out of scope` |
| P4 | **Escalation.** Anything the bot can't answer is pointed to LumaBox technical support. | The text of `REFUSAL_MESSAGE` | Manual review of refused turns (Module 5) |
| P5 | **Grounding.** Answer only from the retrieved policy text, never from general knowledge. | Prompt: "Use only the context below". | Golden `must_include` facts · gate |
| P6 | **No invented facts.** Never state a price, date or number that isn't in the retrieved text. | Prompt only (weak). | Golden row `out_of_scope_tricky` · gate |
| P7 | **Transparency.** Every answer shows which chunks it came from. | `src/main.py` and `app.py` print the sources. | Manual |
| P8 | **Privacy.** Never ask for passwords or payment details. Conversation logs never enter version control. | Prompt and documents contain no such request · `logs/` is in `.gitignore`. | Manual review |
| P9 | **Prices only from the table.** The bot may state a price only for a product listed in `homework/model_prices.xlsx`, and only the price in that row, in THB. For any other product (another brand, or a LumaBox model that isn't in the table, e.g. "X999") it refuses with `REFUSAL_MESSAGE`. It never estimates, converts or compares prices. | Knowledge: `src/ingest.py` adds one sentence per table row to the same collection (`metadata source = "price"`). Code: when the top hit is a price row, `should_refuse()` refuses unless the question names a product from a retrieved price row (`names_product()`: model code or name word, ignoring the shared word "LumaBox"). | Golden category `price`: `price_x100`, `price_screen`, `price_sonabox` (non-LumaBox brand that *is* in the table) must answer with the exact price; `price_not_listed` (iPhone, Galaxy, PlayStation) and `out_of_scope_tricky` X999 must be refused · `test_retrieval_finds_the_evidence`, `test_out_of_scope_is_refused`, `test_in_scope_is_not_refused` · gate |
| P10 | **Price sources.** A price answer shows the price row it came from (an id starting `price_`). | Same as P7. | Manual |
| P11 | **Frustrated customers.** When a message is negative, or the same customer asks about the same topic a second time, the bot (a) starts with one short acknowledgement ("Sorry this has taken so long."), (b) still answers from the policies if it can, and (c) whenever it refuses or would say "I do not know", replaces the bare reply with a handover to a human, with the support contact. It never argues, blames the customer, or repeats the same unhelpful reply. *(Proposed, not implemented yet.)* | Code: run the sentiment check from `src/review.py` (`is_negative()`) inside `rag_answer()` before answering, plus a per-session count of turns that retrieve the same top chunk. If either triggers, wrap the answer with the acknowledgement and, on a refusal or decline, swap in an escalation message instead of `REFUSAL_MESSAGE`. Log `"sentiment": "negative"` and `"escalated": true` in the trace. | Golden category `frustrated` with `expected_action` = `escalate` (needs a new action in `src/golden.py`): "This bot is useless, I asked about my refund twice already!" must contain `8 business days` *and* the escalation text; "Seriously, nobody has answered my question about my broken screen" must escalate. A unit test that a repeated topic in one session triggers escalation. Monitoring: in `python -m src.review`, every negative turn should show `escalated`; any that doesn't is a failure. |

## Known gaps

- **P6 still relies on the prompt for policy questions.** Questions that
  share words with the policies ("Does LumaBox ship to the moon?", "Is
  LumaBox a good company to invest in?") score above the threshold, so only
  the model's own "I do not know" stops an invented answer, and a prompt
  change can remove that instruction (Module 2, Task 2 shows what happens).
  Tracked as `known_issue` in `tests/golden.xlsx`. For *prices* this gap is
  closed by P9 in code: "How much is the LumaBox X999?" is now refused
  deterministically, so its `known_issue` was removed.
- **P9's name check is lexical and simple.** A question that names a listed
  product *and* asks about another ("Is the X100 cheaper than an iPhone?")
  passes the check, and a generic word that appears in a product name
  (e.g. "screen", "speaker") can match a question about something else.
  Sibling models ("X200" vs "X250") and serial codes ("LMX-201") confuse the
  embedding model; this is handled by hybrid search in `retrieve()` (an exact
  model identifier in the question puts its row first) and tested by the
  `price_exact_*` golden rows. Questions that name a product without an
  identifier ("the speaker") still rely on vector search alone.
- **P4 has no automated test yet.**

## Changing this policy

Change the rule here, change its enforcement, add or update the golden rows
that test it, and run `pytest` and `python -m src.gate` before committing.
