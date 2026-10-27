# Social Platform continuation handoff — 2026-10-27

## Startup

The user asked for handoff + merge + a fresh session. Read AGENTS.md, this file,
docs/implementation.md (decision entries at the end) and verification/generation-grounding.md
(latest sections at the end). Inspect git status/log and confirm this delivery's PR is merged
by content on `main`:
`grep -n test_writer_keeps_injected_text_inside_its_own_data_field backend/tests/test_generation.py`.
Then give a short next-step summary and wait. Do not start engineering, paid calls, pushes or
PRs on startup. Linear works through the Linear MCP in Claude Code sessions (project Social
Platform).

Never print, overwrite or stage ignored backend/.env (it sets no GENERATION_REVIEW_MODEL(S),
MAX_REQUEST_USD, output-token or retry overrides; code defaults apply). Preserve user Brand
DNA v2, the one Ready Hebrew source and saved posts. Paid model calls need explicit
authorization each time.

## What this delivery contains

PR #3 (source-review-v4, selectable reviewer, $0.16 cap) merged as 4877adb. This delivery
(PR #4) adds only tests and evidence for the SP-4 criterion "Context is bounded by a token
budget and source text cannot override system instructions". No application code changed.

- 38 offline tests in backend/tests/test_generation.py (mocked provider): context-budget
  boundaries (exact fit, one token less, metadata/title counted, rank order kept, inputs not
  mutated, Hebrew and special-token text), writer receives only budgeted context, writer
  prompt-limit guard fails before any provider call, 28 writer-side injection cases
  (4 strings × topic/goal/tone/CTA/guidelines/source content/source title), role-separated
  provider messages, strict writer schema before review.
- Evidence table in verification/generation-grounding.md and an SP-4 comment. The criterion
  is deliberately **unchecked** (user decision): structural isolation is proven offline, but
  model behaviour under injected instructions needs a live check.

## Lessons (do not re-learn)

- **Tests must not read backend/.env.** `Settings` uses `env_file=".env"` relative to the
  current directory, so `uv run pytest` from backend/ loads it. Run the suite from a directory
  without `.env` (the session scratchpad):
  `uv run --project <backend> pytest -c <backend>/pyproject.toml --rootdir <backend> <backend>/tests`.
- Disposable test DB: `CREATE DATABASE` as social_admin in the social-platform-postgres-1
  container, pipe docker/postgres-init.sql with the CREATE ROLE line removed and the database
  name substituted, run `alembic upgrade head` from backend/ with MIGRATION_DATABASE_URL and
  DATABASE_URL set to the admin URL, and test as social_app. Drop it afterwards.
- `bounded_context` uses a binary search over prefix length, so "one token less keeps an
  empty list" is false: it truncates. Only a source whose metadata alone exceeds the budget
  (e.g. a long title, which is never truncated) is dropped, and everything after it too.
- `mypy .` fails on an existing duplicate-module error (scripts/generation_scenarios.py);
  CI runs `mypy app`, which passes.
- Earlier lessons still hold: v4 coverage only helps when the model splits claims; reasoning
  models spend reasoning tokens against max_completion_tokens (Sonnet 5.5 hit 1,600);
  measure before sizing limits; `npm test` starts `npm run dev` on 53073 and writes `.next`,
  so rebuild production before `npm run start`; own disposable DBs as social_admin, not
  social_app.

## Open risks and debt

- No live injection check since 2026-10-25 (GPT-4.1, source-review-v2). Not run with
  GPT-5.6-terra or source-review-v4. Blocks the SP-4 criterion above.
- GPT-5.6-terra end-to-end generation has never run. It raised
  `missing_requested_future_launch_date` on the private case (false-rejection risk).
- Both strong reviewers rejected `outside_context_en_supported`, probably for topic fit;
  the fixture may be ambiguous (issue text not captured).
- Typical reviewer cost constants (backend/app/review_models.py) come from one review.
- A reviewer can still pair a claim with an unrelated exact quote.
- The live 16-scenario generation suite has not been rerun since v3.
- The context budget truncates by code point and can split a multi-code-point emoji
  (harmless, untested).

## Private evidence (outside Git; never print or commit contents)

/var/folders/0w/spf_k7c124l8t8rztmqk721m0000gn/T/social-grounding-review-j6qu9t1z/ (0700):
case.json and v4_replay_review*.json. Temporary OS directory; it may be cleaned.

## Verification at delivery

Backend 307 passed (269 before) on a disposable DB as the restricted role, run from a
directory without `.env`; DB dropped. Ruff format/lint and `mypy app` passed. PR #4: all 6
hosted checks passed. No paid calls this delivery. Frontend untouched.

## Runtime

Unchanged by this delivery: API container (default reviewer GPT-5.6-terra), production
frontend on 53073 (`npm run start`), Postgres 55473, Redis 56373. Port 3000 belongs to
another project; never stop it.

## Linear and next task

SP-4 and SP-16 In Progress; no checkbox changed. Latest SP-4 comment holds this delivery's
evidence and why the criterion stays open.

Recommended next existing task: the paid end-to-end GPT-5.6-terra run, extended with one or
two live writer-injection scenarios (EN/HE) so it can close the SP-4 context/injection
criterion. Needs explicit cost authorization; estimate before running. After that: SP-4's
model-deployment criterion (Claude 3.5 Sonnet is not in the OpenRouter catalog; GPT-4o is).
Other partial issues: SP-5 (suggestions/media), SP-1/SP-2, SP-8/9/10, SP-11/13. Backlog:
SP-6, SP-3.
