# Social Platform continuation handoff — 2026-10-29 (after PR #19, SP-16 milestone)

## Startup

Read AGENTS.md, this file, docs/implementation.md (decision entries at the end) and
verification/generation-grounding.md (latest sections at the end). Inspect git status/log and
confirm the last delivery is on `main` by content:
`git grep -n "def suggest_topics" origin/main -- backend/app/topic_suggestions.py`.
Then give a short next-step summary and wait. Do not start engineering, paid calls, pushes or
PRs on startup. Linear works through the Linear MCP (project Social Platform).

Never print, overwrite or stage ignored backend/.env (no GENERATION_* overrides; generation
uses EMBEDDING_API_KEY on OpenRouter). Preserve the owner's Brand DNA, the four Ready
Knowledge Base documents and saved posts. **Paid model calls need a dollar cap each time.**
The owner's grant on 2026-10-29 ("continue with all SP-16 tasks … merge, open PRs, make
decisions and start new sessions; stop only for a real product issue") covered SP-16 work
only and ends with this handoff.

## Deliveries since the last handoff (PRs #15–#19)

- **#15 (SP-22 Done):** Gemini 3.8 Flash output limit 4,000; live writer choice verified.
- **#16 (SP-23 Done):** FastAPI rejects cross-site writes and unknown hosts.
- **#17 (SP-24, SP-26 Done): `source-review-v7`.** Measured first: 45 reviews, failures were
  the Hebrew copula "הוא" left outside claims and a final "." on an exact excerpt; one owner
  draft was blocked for repeating the owner's own CTA. Fixes: הוא/היא/הם/הן are connectives;
  coverage compares whole tokens in one pass (numbers keep their sign and separators; fact
  signs must match); excerpts sit on source token boundaries (one attached Hebrew prefix
  allowed before an exact excerpt); `copied_instructions` means instructions aimed at the AI,
  and the owner's offer-details CTA never blocks; new advisory finding
  `unlisted_contact_detail` for any link/email/handle/phone the owner did not give; failed
  reviews store `failed_check`/`failed_sentence`. Three `bf-security-reviewer` rounds.
  Typical Terra review cost remeasured on real drafts (~$0.041).
- **#18 (SP-25 Done): retrieval spreads across documents.** At most 3 chunks per document
  (SQL `row_number()` per document) while another document has chunks within 0.65; freed
  slots fill back; each document's best chunk first. The mentoring-vs-coaching topic now
  reaches the mentoring article.
- **#19 (SP-6): "Suggest topics"** in Create Post, backed by `POST /generation/topic-suggestions`
  (sampling, strict schema, server-side citation/language/duplicate checks). Live: 3 cited
  ideas in HE ($0.0078) and EN ($0.0032).

## Lessons (do not re-learn)

- **Measure the failing check before fixing a reviewer.** Keep raw reviews privately outside
  the repo (`run-only script` patching `app.grounding.chat_completion`), then re-score any
  server-side rule change offline on the same reviews for free. Every rule change in #17 was
  re-scored this way; one round (no prefix allowance on exact quotes) turned 7 good reviews
  invalid and was reverted before merge. Terra quotes Hebrew source words without their
  attached prefix ("הספורט" from "והספורט") constantly.
- **OpenRouter key usage lags calls by up to about a minute,** so a cap checked against
  `GET /api/v1/key` before each call can overrun by a few calls; keep a margin. Cut-off
  (`length`) reviews report no cost to the app, so provider metadata undercounts; key usage
  does not.
- **A broken `sitecustomize.py` fails open:** Python prints "Error in sitecustomize" and runs
  uncapped. Preflight every paid run: `python -c "import sitecustomize as s; print(s.CAP)"`.
- **Do not name helper scripts after stdlib modules** (`inspect.py` broke pydantic imports).
- **GPT-4.1 (default writer) adds small unsupported details** ("for visitors", "Local
  residents can access…", meta notes). The full evaluation therefore stops at the garden
  positives and the English supported scenarios fail; the reviewer is right each time. Read
  the drafts (log them through the spend hook's `SPEND_CONTENT_LOG`) before blaming a change.
- **Linear auto-closes issues named in a merged branch or PR.** It closed SP-24/25/26 on
  merge; check status and only keep Done when every criterion is verified.
- **The Next server on 53073 is `next dev` from this checkout,** so Playwright and the owner's
  UI run whatever branch is checked out. The API container does not: it needs a rebuild.
- Earlier lessons still hold: three separate OpenRouter limits (credits, key limit,
  workspace lifetime budget — check `effective_budget`); tests must not read backend/.env
  (scratchpad `testdb.sh` pattern: disposable DB, runtime role, pytest from a directory without
  `.env`); CI runs `mypy app`; reasoning tokens count against output limits.

## Open risks and debt

- **SP-27 (Backlog, needs an owner decision):** about 1 in 7 medium Hebrew reviews hits the
  4,000-token output limit (`grounding_review_truncated`). A higher limit does not fit the
  review's smallest stage budget ($0.124). Options: raise `GENERATION_MAX_REQUEST_USD` to
  ~$0.37, shrink `TRANSLATION_BUDGET_SHARE`, or keep "Check again".
- **Known v7 limits** (docs/implementation.md): the prefix allowance cannot tell a prefix
  from a root letter ("לא" after the "מ" of "מלא"); planted reader prompts with no contact
  detail are neither blocked nor flagged; unlisted top-level domains without a path, 3-3-3
  phone groupings and phones with 4+ dots are not detected; tech names such as "ASP.NET" are
  flagged (advisory); הוא/היא outside claims can lose who-does-what.
- **Cross-language retrieval:** a Hebrew topic puts English documents at ~0.85, beyond the
  limit; the translation fallback runs only when nothing is found. Always translating would
  add a writer call per draft.
- **Topic suggestions sample at most 8 documents** and what fits 2,800 tokens (6 chunks on
  the owner's KB); a large Knowledge Base is sampled, not covered. No cost line is shown
  before "Suggest topics" (about $0.003–0.008 a click with GPT-4.1).
- **The 403 workspace-budget error is still mislabelled as an authentication failure** in
  app/generation_provider.py and app/embeddings.py (no Linear issue).
- **SP-5 is Done with its media criterion unchecked**; media belongs to SP-3 (Backlog).
- Carried over: Gemini latency (9 s mean); typical tokens from different sources; the
  evaluation fixture's required-wording check rejects a fair paraphrase; stale remote branches
  (`sp-4-*`, `codex/*`, `handoff-*`, `claude/*`) — do not delete without the owner.

## Verification at delivery

Backend 696 passed on a disposable migrated DB with the runtime role, run from a directory
without `.env` (the DB was dropped); ruff, format and `mypy app` passed. Frontend Prettier,
lint, tsc and Playwright 63/63 passed. Hosted CI 6/6 on #17, #18 and #19; each was merged with
an admin bypass under the owner's grant and verified on `main` by content. Reviews:
`bf-security-reviewer` (three rounds on #17, one on #19) and `bf-qa` (#18, #19); every
finding was fixed or recorded as a known limit in docs/implementation.md.

Live checks: the v7 reviewer-only cases 34/34; EN/HE injection scenarios clean; the owner's
previously blocked draft no longer blocked; retrieval replay on the owner's Knowledge Base;
topic suggestions through the full browser → proxy → API path in Create Post (HE and EN).
Paid spend for the SP-16 run: about $1.61 of OpenRouter key usage (from $3.447 to $5.055)
against a self-set $2.00 cap; $4.95 of the $10 workspace budget remains. The first
measurement step overran its own $0.70 sub-cap by $0.074 (cut-off reviews report no cost).

## Runtime

API, worker and scheduler containers rebuilt from `main` (`d2b3e72`) on 2026-10-29; API
readiness passed and `/generation/configuration` reports `topic_suggestions: true`. Stored
v6 reviews now ask for a new check (`generation_review_required`) on retry, GET and save.
The Next server on 53073 is `next dev` from this checkout, now on `main`. Postgres 55473, Redis
56373. Ports 3000 and 8000 belong to other projects; never stop them.

## Linear and next task

SP-16 In Progress: SP-4, SP-5, SP-6, SP-22, SP-24, SP-25, SP-26 Done; SP-27 Backlog (owner
decision above); SP-21 Backlog (deferred web search). Other epics: SP-15 (SP-1/SP-2 In
Progress, SP-3 Backlog), SP-17 (SP-8/SP-9/SP-10 In Progress), SP-18 (SP-11/SP-13 In Progress).

**Recommended next:** the owner's SP-27 decision (one answer unblocks a small change). Then
the Knowledge Base file-upload slice under SP-17 (SP-10 UI, SP-9 ingestion and private
storage, SP-8 extraction): UTF-8 text files first, then PDFs. It needs two owner decisions
before code: the PDF library (pypdf vs PyMuPDF) and where private source files live (local
disk vs S3-compatible storage). Remember SP-23's limit: multipart uploads need an explicit
exception in `app/write_guard.py`.
