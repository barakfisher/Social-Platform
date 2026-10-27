# Social Platform continuation handoff — 2026-10-26 (evening)

## Startup

The user asked for handoff + merge + a fresh session. Read AGENTS.md, this file,
docs/implementation.md (decision entries at the end) and verification/generation-grounding.md
(latest sections at the end). Inspect git status/log and confirm this delivery's PR is merged
by content on `main` (e.g. `grep -n source-review-v4 backend/app/grounding.py`). Then give a
short next-step summary and wait. Do not start engineering, paid calls, pushes or PRs on
startup. Linear works through the Linear MCP in Claude Code sessions (project Social Platform).

Never print, overwrite or stage ignored backend/.env (it sets no GENERATION_REVIEW_MODEL(S),
MAX_REQUEST_USD, output-token or retry overrides; code defaults apply). Preserve user Brand
DNA v2, the one Ready Hebrew source and saved posts. Paid model calls need explicit
authorization each time.

## What this delivery contains

PR #2 merged as 1347763. This delivery adds:

1. **Spending-limit fix, written by a separate concurrent session.** Per-request cap
   $0.05 → $0.10. Adds `attempt_estimate_usd`, `TRANSLATION_BUDGET_SHARE`,
   tests/test_generation_budget.py and an EN/HE `generation_spending_limit` UI message. The
   decision is in docs/implementation.md. That session's state was unknown at delivery; its
   files had been unchanged for over an hour and pass every check.
2. **Hebrew date-case adjudication** (offline): no date leaked. Sentence 1 carried an origin
   clause absent from the retrieved context (chars 622–2054 of 2054 were retrieved); its
   exact quotes supported only the rest of the sentence. The earlier "conflicting audits"
   looked at different sentences.
3. **`outside_context` review fixtures**: 24 cases in total, EN/HE.
4. **source-review-v4**: the reviewer splits sentences into claims copied exactly from them.
   The server requires the claims to cover every word except a fixed EN/HE connective list,
   requires every claim supported with exact quotes, and allows empty evidence for
   unsupported claims. Reviewers cite short source aliases (S1…), mapped back to real
   chunk IDs in stored provenance. v3 results are invalidated on retry/GET/save.
5. **Reviewer output limit**: GENERATION_REVIEW_MAX_OUTPUT_TOKENS=1600, separate from the
   writer's 900. The provider clamp is the larger of the two limits.
6. **Default reviewer `openai/gpt-5.6-terra`, user-selectable per draft** from the
   allowlist GENERATION_REVIEW_MODELS (GPT-5.6-terra, GPT-4.1). `GET /generation/review-models`
   returns typical and maximum source-check cost from the live catalog. Create Post has a
   "Source check model" select in its advanced options. Unlisted models get 422
   `review_model_unavailable` before any provider call. Cap is now $0.16.

## Lessons (do not re-learn)

- v4 coverage only helps when the model splits claims. Live GPT-4.1 under v4 returned whole
  sentences as single claims and still accepted the private case and `outside_context_he`.
  The misses are reviewer judgment, so a different reviewer model fixed them, not more
  structure.
- Reasoning models spend reasoning tokens against max_completion_tokens. Sonnet 5.5 hit
  1,600 on the longest case (withheld as invalid). The app sends `temperature: 0` and no
  reasoning control. Gemini 3.7 Flash returned HTTP 400 for every request (cause not
  captured).
- Measured review size (≤501 tokens GPT-4.1, ≤907 GPT-5.6-terra) was far below my
  pre-measurement estimate. Measure before sizing limits.
- `npm test` runs Playwright, which starts `npm run dev` on 53073 and writes `.next`.
  Always rebuild production after it before `npm run start`.
- Disposable test DBs: create as `social_admin` (local dev credentials are in
  docker-compose.yml), apply docker/postgres-init.sql grants, migrate as admin, and test as
  `social_app`. Owning the DB as `social_app` fails test_runtime_cannot_create_tables.

## Open risks and debt

- GPT-5.6-terra is stricter. On the private case it also raised
  `missing_requested_future_launch_date`, penalizing correct omission of an unsupported
  request. End-to-end generation with it has NOT been run (user declined for now).
- Both strong reviewers rejected the exactly-sourced `outside_context_en_supported` control,
  probably for topic fit (the draft doesn't answer the topic's question). The fixture may be
  ambiguous; not confirmed because issue text wasn't captured.
- Typical cost constants (backend/app/review_models.py) come from one realistic review.
  Remeasure when the review prompt or models change.
- A reviewer can still pair a claim with an unrelated exact quote. Coverage makes that
  deliberate, not impossible.
- The live 16-scenario generation suite has not been rerun since v3.

## Private evidence (outside Git; never print or commit contents)

/var/folders/0w/spf_k7c124l8t8rztmqk721m0000gn/T/social-grounding-review-j6qu9t1z/ (0700):
case.json (draft, inputs, complete source snapshot), v4_replay_review*.json (raw reviews
per model; 0600). Temporary OS directory; it may be cleaned by the system.

## Verification at delivery

Backend 269 passed on a fresh disposable DB as the restricted role (dropped; none remain).
Ruff format/lint and mypy passed. Offline validation: 24 review cases, 16 scenarios, zero
provider calls. Frontend: Playwright 17 passed; production build, lint, Prettier and types
passed. Browser pane: EN desktop and HE RTL at 375 px. Paid today: v4 live check $0.07436 and
3-model comparison $0.2924 (provider-reported; total billing not measured).

## Runtime

API container rebuilt with this code (default reviewer GPT-5.6-terra). Production frontend
restarted on 53073 with `npm run start` from the delivering session. Postgres 55473, Redis
56373. Port 3000 belongs to another project; never stop it.

## Linear and next task

SP-4 and SP-16 In Progress; no acceptance checkbox changed. Evidence is in SP-4 comments
(latest: reviewer default/selectable) and an SP-5 comment for the UI. Claude 3.5 Sonnet is
not in the OpenRouter catalog (relevant to SP-4's model criterion); GPT-4o is.

Recommended next existing task: SP-4 criterion "Context is bounded by a token budget and
source text cannot override system instructions". Map existing budget/untrusted-data code to
evidence: offline boundary tests for the context budget and writer-side injection fixtures.
After that: the paid end-to-end GPT-5.6-terra run, then SP-4's model-deployment criterion.
Other partial issues: SP-5 (suggestions/media), SP-1/SP-2, SP-8/9/10, SP-11/13. Backlog:
SP-6, SP-3.
