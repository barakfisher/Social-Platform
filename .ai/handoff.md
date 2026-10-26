# Social Platform continuation handoff — 2026-10-26

## Delivery and startup

The user requested merge, handoff and a fresh session for this delivery. Read AGENTS.md,
this file, docs/HANDOFF.md, docs/implementation.md and verification/generation-grounding.md.
Read .ai/codex-rules.md and .ai/project-memory.md if they exist (currently absent).
Inspect Git status/log, origin/main and the delivery PR's actual merge/check/review status.
The previous PR #1 was merged as d36d3a4; its historical review blocker is resolved.
This delivery is on codex/cross-language-grounding-handoff. Final PR/merge state must be
read from GitHub, not inferred from a startup handoff written before delivery finishes.

Never print, overwrite or stage ignored backend/.env. Preserve user Brand DNA, Ready
sources and saved posts. No policy/billing changes or merge bypasses. The user authorized
paid model validation in the preceding work; it does not authorize new paid calls merely
because a new chat starts. Existing evaluator defaults offline. Future implementation
stays local until another delivery request. A fresh chat was explicitly requested.

## Current change

- app/query_translation.py: bounded EN/HE fallback using configured writer GPT-4.1 only
  when original scoped retrieval returns no hits. Opposite topic script, strict JSON/query
  validation, max450 output tokens/1000 characters. No EN/HE letters means no paid fallback.
- app/generation.py: retry same scope/Ready/profile/cosine cutoff/context budget with the
  translated query; retain original preferences. Existing hits removed by context trimming
  never trigger translation. Translated text is not evidence and is not returned in metadata.
- Translation preflights at most20% of completion allowance including retries. On completion,
  per-attempt estimate × attempts actually made remains consumed. Writer/reviewer each get
  half the remainder including all their possible retries. Invalid/nonfinite reservations
  fail closed. Direct retrieval stays50/50. Translation usage retained on failures and added
  to successful cost totals. Extra embedding cost is outside completion accounting; estimates
  are not provider billing caps.
- app/grounding.py: source-review-v3 explicitly requires separate contiguous exact excerpts;
  server substring/coverage checks unchanged. Old v2 retry/read/save approval invalidated.
  Actual model had stitched nonadjacent passages, omitting126 source characters.
- New tests test_query_translation.py and test_grounding_evidence.py; expanded
  test_generation.py. docs/implementation.md and verification/generation-grounding.md record
  behavior, actual paid history, failures and limitations.

## Evidence and unresolved scope

Final local backend suite:231 passed in a fresh disposable migrated DB; providers mocked.
Ruff format/lint, app mypy and offline20-review/16-scenario validation passed. Existing
Starlette/httpx warning only. No frontend changes/tests rerun during this slice.
Fresh separate QA added tests for exact/stitched EN/HE evidence, malformed/null boundaries,
legacy v2 approvals, translation/schema/attempt/reservation boundaries, scoped fallback,
remaining budgets, usage, idempotency, failure persistence and context trimming.
Fresh independent pre-merge security audit reviewed the complete delivery diff/new files:
no blocking findings. No private data/credentials read or paid calls by auditors.

Live GPT-4.1 source-review-v3 regression:20/20 fixtures passed (10 controls,10 negatives).
Actual Brand DNA v2 / existing Hebrew Ready source: fresh supported EN LinkedIn and HE
Facebook drafts passed exact review and save/read/delete across targeted runs. English used
translation; Hebrew did not. Do not describe this as one uninterrupted green matrix.
Six unsupported-detail challenges: EN price/date withheld; EN guarantee omitted in accepted
source-supported draft; HE price/guarantee withheld. HE date case remains UNRESOLVED:
production accepted with exact evidence, full-source audit flagged an extra claim, later
focused source/sentence check judged it supported. Initial classifier's invented-date claim
is not established. The six-challenge run exited unsuccessfully and no exception was added.
Some withheld drafts were judged safe by extra audits. False rejection/model disagreement
remain. Model assessment is not independent human editorial verification.

Private disputed sample retained outside Git (directory0700,file0600):
/var/folders/0w/spf_k7c124l8t8rztmqk721m0000gn/T/social-grounding-review-j6qu9t1z/case.json
Contains private draft/input/source snapshot and production review; never print or commit it.
Use privately for the next adjudication; do not regenerate a different case and call it fixed.
Other transient scripts/captures removed. All disposable DBs removed; final catalog count0.
Original fingerprints matched after each run. Total experiment billing not measured.

QA also noted existing unsupported sentence schema still requires nonempty evidence;
this can yield review_invalid and is NOT fixed or the cause of valid rejected reviews.

## Local runtime

API rebuilt and ready at localhost:58073; reports source-review-v3 and retrieval-translation-v1.
PostgreSQL55473, Redis56373. Last config:configured=true,brand_ready=true,ready_documents=1;
Brand DNA v2, zero saved posts. Source2054 characters/three chunks, original data untouched.
Only brand name/audience populated; voice/positioning/guidelines/prohibited claims empty.
Do not invent brand settings/sources to improve evaluation.
Project services had stopped between checks; existing PostgreSQL/Redis/API were restarted
without resetting volumes. Worker/scheduler were not restarted. Frontend53073 was not
restarted in this continuation; recheck availability. Never stop another project's port3000.
No public deployment/authentication/media/publishing delivered.

## Linear and next task

SP-4 Implement grounded RAG post generation and parent SP-16 remain In Progress.
https://linear.app/test-bf/issue/SP-4/implement-grounded-rag-post-generation
No new acceptance checkbox checked. Existing curated-evaluation checkbox was already checked.
Context/source-instruction release and requested Claude3.5Sonnet/GPT-4o deployment availability
remain open. Do not close SP-4/parents based on this delivery.
Evidence and limitations recorded in existing SP-4 comments, latest continuation comment
69f0a59b-8524-44b3-ac0d-2fd6f3fd9dd9.

Next existing atomic task: adjudicate retained HE date sample/model-audit disagreement before
further release claims; then remaining SP-4 release criteria. Recommend only; this merge/
fresh-session request does not explicitly authorize new engineering or new paid validation.
If delivery is blocked, the fresh chat's first priority is completing the already-authorized
normal merge after actual required review/check gates are satisfied. Do not bypass them.
Broader SP-5,SP-1/2,SP-8/9/10,SP-11/13 remain partial; SP-6 suggestions and SP-3 media Backlog.
