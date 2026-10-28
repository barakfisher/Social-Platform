# Social Platform continuation handoff — 2026-10-28 (after PR #13)

## Startup

Read AGENTS.md, this file, docs/implementation.md (decision entries at the end) and
verification/generation-grounding.md (latest sections at the end). Inspect git status/log and
confirm PR #13 is on `main` by content:
`git grep -n "google/gemini-3.8-flash" origin/main -- backend/app/writer_models.py`.
Then give a short next-step summary and wait. Do not start engineering, paid calls, pushes or
PRs on startup. Linear works through the Linear MCP (project Social Platform).

The main checkout was clean on `main` at handoff. Old worktrees under `.claude/worktrees/`
(`cranky-dewdney-ed0c02`, `fastapi-csrf-guard-39e6dc` with no commits, `sp-22-writer-model-dbdd87`)
hold nothing unmerged that matters; leave them unless the owner asks.

Never print, overwrite or stage ignored backend/.env (no GENERATION_* overrides; generation
uses EMBEDDING_API_KEY on OpenRouter; code defaults apply). Preserve the user's Brand DNA, the
Ready Hebrew source and saved posts. **Paid model calls need explicit authorization and a
dollar cap each time.** Merging needs an admin bypass of the required review, approved by the
user each time.

## Deliveries since the last handoff (PRs #9–#13)

- **#9 advisory source review (`source-review-v5`).** Drafts are always shown. Problems are
  coded findings in a "Points to check" panel. Only `copied_instructions` or
  `revealed_instructions` blocks a draft. Claims are typed `factual` or `creative`; tone and CTA
  presets; optional offer details; "Check again" reviews server-stored text only.
- **#10 live-evaluation pass rules for v5.** Each review is classified as clean, flagged or
  blocked (`review_outcome`). Supported scenarios must be clean. An invented missing fact
  passes only when `unsupported_claim`/`contradicted_claim` flags it. An obeyed injection fails
  even when flagged.
- **#11 reasoning reviewers can finish (`source-review-v6`).** Review output limit 1,600 →
  4,000, request cap $0.16 → $0.31, timeout 30 → 40 s. `finish_reason: length` raises
  `generation_output_truncated`. The prompt quotes the server's `CONNECTIVES` list verbatim.
  Hebrew evidence quotes may differ by one attached prefix letter.
- **#12 writer choice (SP-22 slice 1).** `GENERATION_WRITER_MODELS` allowlist,
  `app/writer_models.py` `WriterProfile` (token ratio, typical tokens, optional output limit),
  `writer_model` on `POST /generation` (stored, fingerprinted, never in prompts, 422
  `writer_model_unavailable`), `GET /generation/writer-models`, and the Create Post writer
  select with a total-cost line. Budgets stay in o200k units; the writer's ratio scales the
  cost reservation, the estimate and the context-length check.
- **#13 Gemini 3.8 Flash listed as an optional writer; GPT-4.1 stays the default** (owner
  decision), plus `evaluate_generation.py --live --writer-only`.

| Writer (vs. GPT-4.1) | Added unsupported detail | Meta notes in post | Injection obeyed | Garden drafts passed | Writer $/draft | Latency |
| --- | --- | --- | --- | --- | --- | --- |
| Gemini 3.8 Flash | 1/40 | 0/40 | 0 | 4/7 | 0.0035 | 9.0 s mean, 21.7 s max |
| GPT-4.1 | 5/20 | 8/20 | 0 | 0/2 | ~0.0025 | 1.5 s |

Gemini meets the agreed rule for becoming the default; the owner kept the faster GPT-4.1.
Rejected: Claude Sonnet 5.5 (16/20 meta notes, one Hebrew draft blocked) and GPT-5.6-luna (7/20
added details). Evidence and alternatives: the SP-22 entries in docs/implementation.md and
"Writer candidates: confirmation runs" in verification/generation-grounding.md.

## Lessons (do not re-learn)

- **OpenRouter has three separate limits.** Account credits, the API key's own limit, and a
  **workspace lifetime budget** ($10 here, raised by the owner on 2026-10-28; it never resets).
  Topping up credits does not lift the workspace budget. Check all three for free with
  `GET https://openrouter.ai/api/v1/key` and read `effective_budget`. The workspace 403
  reaches users as `generation_authentication_failed` / `embedding_authentication_failed`,
  which wrongly suggests a bad key.
- **Terra sometimes rejects its own review.** It paraphrases claim text ("museum opens Tuesdays"
  for "opens on Tuesdays", or drops "גם"), and the coverage check turns the review into
  `grounding_review_invalid`. This happened 3 times in 70 reviews on 2026-10-28. In the full
  evaluation it stops the run inside the 24 reviewer-only cases, before any writer is tested.
  Use `--writer-only` to evaluate a writer.
- **The evaluator exits 1 whenever any case fails**, and a garden-positive failure stops the run.
  Read the JSON lines in its output, not the exit code. Classify drafts by hand; "no findings"
  is not the same as "no additions".
- **Evaluate a candidate writer without code changes:** a `sitecustomize.py` placed on
  `PYTHONPATH` outside the repo can add a run-only `WriterProfile` once `app.writer_models`
  loads, log each `/chat/completions` call (model, tokens, finish, cost, content), refuse new
  calls at a spend cap, and stop after N calls. Set `GENERATION_MODEL` and
  `GENERATION_WRITER_MODELS` together; the config rejects a default that is not listed.
- **The reviewer is inconsistent on Hebrew garden names.** "בגינה הקהילתית סידר" was accepted once
  and flagged twice, because only the English line of the garden source names the garden. One
  garden sample proves little; run at least 3.
- **Typical tokens for a reasoning writer** must come from a realistic prompt. Gemini's
  scenario drafts are one sentence and still used ~700 completion tokens, mostly reasoning.
  A medium LinkedIn draft used 1,007 (775 reasoning).
- **Disposable test DB:** grant the runtime role like `isolated_database` does and point
  `TEST_DATABASE_URL` at that role. With the admin role,
  `test_runtime_cannot_create_tables` fails. Without `TEST_DATABASE_URL`, 120 tests skip and
  `test_generation_lock_excludes_other_connections_and_releases_on_disconnect` fails.
- **Looking at a branch's UI:** the API container on 58073 runs old code. Start
  `uv run uvicorn app.main:app --port <other>` from backend/ and a Next dev server from a copy
  of frontend/ (rsync without node_modules/.next, symlink node_modules) with `API_URL` pointing
  at it. Two dev servers in one frontend/ folder would share `.next`. Delete any temporary
  `.claude/launch.json`; it is not git-ignored.
- **Catalog fetches can time out (10 s)** right after start-up. The writer is then shown as
  "unavailable" (the designed state); a reload fixes it.
- Earlier lessons still hold: Linear auto-closed SP-4 on merges of branches named `sp-4-*`, so
  check the issue status after every merge. Measure spend from provider-reported usage, never
  from run output. Tests must not read backend/.env (run pytest from a directory without it,
  using `uv run --project <backend> pytest --rootdir <backend> <backend>/tests`). CI runs
  `mypy app`, because `mypy .` has a duplicate-module error. Reasoning tokens count against
  the output limit. Playwright's `reuseExistingServer` tests whatever already runs on 53073.

## Open risks and debt

- **FastAPI (127.0.0.1:58073) still accepts cross-site writes, bypassing the proxy guard.**
  This is unchanged since the last handoff. A `no-cors` POST with a Blob body sends no
  Content-Type, and FastAPI parses it as JSON. `POST /generation` is paid. CORS only withholds
  responses. The proxy guard (frontend/src/lib/csrf-guard.ts) also still passes DNS rebinding
  (no Host allowlist).
- **The running API container predates #12.** `GET /generation/writer-models` returns 422 there
  (it falls through to `/generation/{run_id}`), so Create Post on 53073 shows the writer
  select's error state. Rebuilding (`docker compose up -d --build api worker scheduler`)
  changes the owner's runtime; ask first.
- **Live writer choice is unverified.** No draft has been generated by choosing Gemini in
  Create Post (`writer_model` sent by the UI). The evaluations reached Gemini only as the
  configured default. This is the last open item on SP-22.
- **Reviewer coverage flakiness** (lesson above) makes "Check again" and the full evaluation
  unreliable. Fixing it means changing the reviewer, which is outside SP-22 and not a Linear
  issue yet.
- **The 403 workspace-budget error is mislabelled as an authentication failure** in
  app/generation_provider.py and app/embeddings.py.
- **Gemini's draft latency** is 9 s on average and up to 23 s for a medium Hebrew draft, before
  the 6–13 s review. The writer timeout is 40 s per call, so there is headroom, but slow.
- **Typical tokens come from different sources:** Gemini's from a synthetic prompt, GPT-4.1's
  from one stored real run. Remeasure both if the writer prompt changes.
- The evaluation fixture's required-wording check rejects a fair paraphrase ("provides bicycle
  repairs" for "repairs bicycles").
- Carried over: GPT-5.6-terra can penalize a draft for omitting an unsupported request.
  Typical reviewer cost constants come from few reviews. A reviewer can still pair a claim
  with an unrelated exact quote. The context budget can split a multi-code-point emoji.
- Stale remote branches remain (`sp-4-*`, `codex/*`, `fix/review-token-budget`,
  `handoff-*`, `claude/*`). Do not delete them without the owner.

## Verification at delivery (PR #13)

Backend 444 passed on a disposable migrated DB with the runtime role, run from a directory
without `.env`; the DB was dropped. Ruff, format and `mypy app` passed. Frontend lint, tsc,
Prettier and Playwright 47/47 passed. Hosted CI 6/6 passed; merged as 3a95b58 with an
owner-approved admin bypass and verified on `main` by content. Create Post was checked against
a local API on the branch with live prices (EN/HE, desktop and 375 px). Paid spend on
2026-10-28: $0.54 provider-reported, against an approved $0.60 cap.

## Runtime

API, worker and scheduler containers built 2026-10-27 21:43 (pre-#12). A Next server on 53073
runs from the main checkout's frontend/. Postgres 55473, Redis 56373. Port 3000 and 8000 belong
to other projects; never stop them.

## Linear and next task

SP-22 In Progress: all 15 acceptance criteria are checked with evidence (comment on
2026-10-28). It stays open only for the live check below. SP-16 In Progress (children: SP-22,
SP-6 Backlog, SP-21 deferred; SP-4 and SP-5 Done). Other open items: SP-15 with SP-1/SP-2 In
Progress and SP-3 Backlog; SP-17 with SP-8/SP-9/SP-10 In Progress; SP-18 with SP-11/SP-13 In
Progress.

**Recommended next: close SP-22.** With the owner's OK, rebuild the API containers (or run a
local API from `main`), generate one Hebrew draft in Create Post with Gemini 3.8 Flash
selected (about $0.035, needs authorization), confirm the run stores
`writer_model: google/gemini-3.8-flash` and the cost line is plausible, record it on SP-22,
then mark it Done. SP-16 then has only SP-6 and the deferred SP-21 left.

After that: **block cross-site writes directly to FastAPI** (security, not a Linear issue yet;
ask before creating one). Add a Starlette middleware in backend/app: writes with a body need
content type exactly `application/json` (415); writes with an `Origin` outside `cors_origins`, or
a `Sec-Fetch-Site` other than `same-origin`/`none`, get 403. The Next.js proxy sends neither
header and must keep working. Reproduce first with a hermetic `TestClient` test. Then add a
Host allowlist to csrf-guard.ts. Next existing task: SP-6 (topic suggestions from the
Knowledge Base, Backlog under SP-16).
