# Social Platform handoff — 2026-10-26

## Startup

Read AGENTS.md, this file, docs/HANDOFF.md and verification/generation-grounding.md.
Inspect git status/log and the delivery PR before changing files. Do not start paid calls,
modify user data, or assume a hosted CI pass on startup. Recommend the next existing task;
wait for authorization before starting it. No new chat was requested for this delivery.

Never print, overwrite or stage private ignored backend/.env. Preserve local user data.
User authorized paid evaluations in this chat and explicitly requested this handoff, PR and
merge. Further implementation stays local until another delivery is authorized.

## Delivery scope

Expand SP-4 evaluation, not production generation behavior:

- backend/scripts/evaluate_generation.py: offline by default, explicit --live, strict fixtures,
  isolated DB identity guard, --scenarios-only and repeatable --scenario selection.
- backend/scripts/generation_review_cases.json: 20 positive/negative EN/HE reviewer fixtures.
- backend/scripts/generation_scenarios.py + generation_scenarios.json: 16 end-to-end EN/HE
  library/repair scenarios for supported facts and missing prices/dates/benefits; provenance,
  persistence, withholding/save prevention, cleanup and aggregate failure checks.
- backend/tests/test_generation_scenarios.py: 84 offline tests.
- verification/generation-grounding.md: actual execution history, false positives, limitations.
- docs/implementation.md: explicit --live command. docs/HANDOFF.md points here.
- AGENTS.md: preserve the user's communication/clarification and next-task rules.

## Verification and audit evidence

Current pre-PR local verification: 169 backend tests passed against PostgreSQL (provider
completions mocked in automated tests), Ruff format/lint for backend and recovery script,
app mypy and evaluator mypy passed. Existing Starlette/httpx deprecation warning only.
Offline CLI validates 20 review fixtures +16 generation scenarios without provider calls.
No frontend code changed; prior 14 Playwright/build evidence is historical, not rerun here.

Authorized live OpenRouter GPT-4.1: 20 expanded review fixtures, six legacy negatives, and
EN LinkedIn/HE Facebook generation/save/read/edit/delete passed. New 16 multi-domain
scenarios passed across initial and targeted runs: 11 drafts and five safely withheld.
This was not one uninterrupted green matrix run. Three lexical false positives were safe
missing-information disclaimers, reviewed manually and exempted only as exact complete
sentences. Regression tests ensure appended/embedded claims still fail. Model review and
fixture-specific lexical checks do not prove arbitrary-domain factuality. No production
prompt/review behavior was weakened. Total provider billing was not measured.

All evaluation databases were removed and catalog checks found none remaining.
Free-only experiments were inconclusive; do not claim free-model suitability. An earlier
unintended paid invocation is disclosed in verification/generation-grounding.md.

Separate QA completed with 84 offline tests. Security reviews during implementation found
no unresolved blocker after fixing the old --isolated workspace bypass. Final independent
pre-merge security audit completed with no blocking findings: CLI opt-in/isolation, SQL
identifiers, subprocess arguments, diagnostic exposure, fixtures and exact disclaimer checks
reviewed. Static audit only; no provider/DB operations or secrets access. Internal Python
helpers rely on the guarded CLI and trusted developer usage.

## Runtime and user workspace

Frontend http://127.0.0.1:53073 (production); API localhost:58073; PostgreSQL 55473;
Redis 56373. Do not stop another project's port 3000 process. Stop only this project's
frontend before rebuilding to avoid concurrent .next writes.

Last read-only check: API ready; configured=true, brand_ready=true, ready_documents=1.
Unlike the historical startup handoff, the user now has one Ready source. No user source
was created, edited or deleted during these disposable evaluations.

## Linear and next task

SP-4 Implement grounded RAG post generation remains In Progress:
https://linear.app/test-bf/issue/SP-4/implement-grounded-rag-post-generation
Only the verified small-curated-evaluation criterion was newly checked. Source-instruction/
context release criteria and requested-model deployment availability remain unchecked.
SP-16 and broader parents stay In Progress; do not close them for this delivery.

Recommended next work: finish SP-4 validation against actual user Brand DNA/Ready source,
then resolve the deployment model decision/availability criterion. Recommend only; do not
start without authorization. Broader-domain/nondeterministic behavior remains a limitation.
SP-5, SP-1/2, SP-8/9/10, SP-11/13 remain partial; SP-6 topic suggestions and SP-3 media remain
Backlog. No public deployment/authentication, media or publishing was delivered here.

## Hosted checks and merge

Previous hosted run 40285333281 was blocked before job steps by failed GitHub payments or
Actions spending limits. Do not change billing/paid limits. Inspect the new PR's actual
checks and annotations; local passing tests do not establish hosted verification.
Record the PR URL and final audit/check evidence below before merging. Use GitHub PR state
and git history for the final merge commit; do not infer it from this source file alone.
