# Reflection — Where would you fix it?

## a. A customer has asked about their refund three times, gets "I do not know" or a refusal each time, and is getting angry

**Where:** first monitoring, to find out which failure it is, then the
prompt (or knowledge), plus the policy for the frustration itself.
**What:** read the three traces. If `chunk_2` (Refund) was retrieved and the
model still said "I do not know", it's a generation error and needs a new
prompt version. If it was refused, it's a threshold or retrieval problem. If
they asked about *their own* refund status, it's a knowledge gap the bot
can't fill, and it must hand over to a human. In every case, P11 (frustrated
customers) should have escalated on the second ask instead of repeating the
same reply.
**How I'd know:** add the customer's wordings to `golden.xlsx` (they fail
first), then pytest and the gate pass after the fix. In the next week's
review, negative-sentiment turns about refunds are answered or escalated,
never a bare "I do not know".

## b. LumaBox changes its refund time from 8 to 5 business days

**Where:** the knowledge (owned by the content owner), plus the tests,
not the prompt or the model.
**What:** change the sentence in `data/lumabox_policies.txt`, update every
golden row whose `must_include` is `8 business days` to `5 business days`,
and push. CI re-runs `python -m src.ingest`, so the index and `kb_version`
change.
**How I'd know:** pytest fails until the golden rows are updated (old facts
can't be retrieved any more), and then passes. The gate's refund category
stays at its baseline. In production, every trace shows the new
`kb_version`, and a spot check of refund turns says "5 business days".

## c. A teammate writes a friendlier prompt and wants it live today

**Where:** the tests and gate, through the pipeline. Never a direct edit
of production.
**What:** add it as a new file (`prompts/answer_v3.txt`); never edit v1 in
place. Run `python -m src.gate --prompt v3` against the baseline and record
the result in `prompts/CHANGELOG.md`. Only if no category got worse,
change `PROMPT_VERSION` and push, so CI runs the same gate again before
build and deploy. Prompt v2 was exactly this situation: friendlier, and it
invented "$99" and lost out-of-scope and refund.
**How I'd know:** a green gate (no category worse) and a green CI run. After
release, monitoring shows the refusal rate and decline rate didn't jump, and
the traces show `prompt_version: v3`. If something goes wrong, rolling back
is a one-line change back to v1.

## d. The day after a release, the refusal rate jumps from 20% to 60%

**Where:** monitoring first (to diagnose), then the pipeline (to roll back),
then whichever part changed.
**What:** roll back immediately by redeploying the previous image by its
commit tag, so customers stop getting refused while I investigate. Then compare
traces before and after: did `kb_version` or `prompt_version` change? Did
`top_similarity` drop across the board? That would point to a changed embedding
model, re-chunked documents or a broken ingest, which pushes everything below
`SIMILARITY_THRESHOLD`. Or did the threshold itself change? Fix that part.
The gate also missed it, so add golden rows that cover the refused
questions.
**How I'd know:** after the fix, pytest's `test_in_scope_is_not_refused`
passes for the new rows, the gate passes, and after redeploying, the refusal
rate in `python -m src.review` is back to about 20%. I'd also add a monitoring
alert on refusal rate so the next jump is caught in hours, not the next day.
