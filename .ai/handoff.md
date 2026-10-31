# Social Platform continuation handoff — 2026-10-31 (after PR #23, SP-27 Done)

## Startup

Read AGENTS.md, this file, docs/implementation.md (decision entries at the end) and
verification/generation-grounding.md (latest sections at the end). Inspect git status/log and
confirm the last delivery is on `main` by content:
`git grep -n 'REVIEW_VERSION = "source-review-v8"' origin/main -- backend/app/grounding.py`.
Then give a short next-step summary and wait. Do not start engineering, paid calls, pushes or
PRs on startup. Linear works through the Linear MCP (project Social Platform).

Never print, overwrite or stage ignored backend/.env. It holds only `EMBEDDING_*` values;
generation has no key of its own and falls back to the embedding key on OpenRouter
(`app.generation_provider.generation_key()`), so a run-only script must use that function,
not `settings.generation_api_key`. Preserve the owner's Brand DNA, the four Ready Knowledge
Base documents, the 19 generation runs and the saved post. **Paid model calls need a dollar
cap each time.** Every grant from earlier sessions (the $1.50 cap, "merge" for #23) covered
that work only and has ended.

## Deliveries since the last handoff (PRs #20–#23)

- **#20:** the previous handoff.
- **#21 (SP-27 limit, SP-17 file slice):** review output limit 4,000 → 5,000 and
  `GENERATION_MAX_REQUEST_USD` $0.31 → $0.37 (option 1, owner-approved). PDF/TXT/MD uploads:
  raw `application/octet-stream` (multipart stays refused by the write guard and proxy),
  signature vs extension, strict UTF-8, per-workspace checksum dedupe, private files on a
  Compose volume (`source_files` at `/app/var/sources`, random keys, 0600), pypdf extraction
  outside the row lock with `page_start`/`page_end` on chunks.
- **#22 (SP-8/9/10 web slice):** web pages through trafilatura (Markdown, favor_precision),
  SSRF checks on every redirect hop with the request pinned to the resolved IP; "Load again
  from the site" with a staging copy (`replaces_id`), paragraph diff, and replace / append
  (dated `## Added YYYY-MM-DD / נוסף YYYY-MM-DD` heading) / keep; chunks carry
  `source_location.added_on`; writer prompt `grounded-post-v5` says newer wins on conflicts.
- **#23 (SP-27 Done): `source-review-v8`.** `CONNECTIVES` gains the bare word בהם; version
  bumped because the reviewer prompt lists connectives verbatim (owner chose the bump over
  keeping v7, so one version name never covers two prompts). Stored v7 reviews now ask for a
  new check.

All of #21–#23 were verified live on 2026-10-30/31 (details in
verification/generation-grounding.md and the comments on SP-8, SP-9, SP-10, SP-27).

## Lessons (do not re-learn)

- **Never run the backend tests against the owner's database.** The conftest `api` fixture
  deletes every Knowledge Base document in the local workspace (inside a transaction it rolls
  back, but one crash away from real loss). Create a disposable DB (`CREATE DATABASE
  social_test`, grant the runtime role usage and default privileges, `alembic upgrade head`
  as admin), run pytest from the repo root (no `.env` there) with
  `TEST_DATABASE_URL=…/social_test` and `env -u OPENROUTER_API_KEY`, then drop it.
- **"Check again" writes.** `POST /generation/{id}/review` stores the new review on the run,
  and on `draft_blocked` it marks the run Failed and drops its content. For measurement, call
  `app.grounding.review_draft` directly on drafts read in a `SET TRANSACTION READ ONLY`
  session (scratchpad `sp27.py` pattern).
- **To observe a reload's in-between state, pause the worker** (`docker compose pause
  worker`): the choice is taken, the embedding job waits in Redis, and search and status can
  be checked before `unpause`. To simulate "the site changed", edit `source_text` (and a
  chunk) of a test source in the DB; no public page changes on demand.
- **Linear auto-closed SP-27 on merge again,** minutes before its last criterion was
  verified. After every merge naming an issue, check its status and criteria.
- **Merging into `main`:** the ruleset requires one approving review, linear history and
  resolved threads, and requests a Copilot review on push. The owner merges with an admin
  bypass (`gh pr merge N --squash --admin`) only when they say so; squash or rebase, never a
  merge commit.
- **Verify a reviewer change offline before paying.** Raw reviews from every paid run are
  kept outside the repo; a rule change is re-scored on them for free (v8: 8 SP-27 reviews and
  54 older ones). Keep doing this.
- **Key usage lags; failed reviews report no cost.** Check `GET /api/v1/key` before every
  paid call with a margin (0.15 used), and wrap uncapped scripts such as
  `evaluate_generation.py` in a watchdog that stops at a lower threshold.
- **The full live evaluation cannot pass with GPT-4.1 as writer:** it stops at the first
  garden post ("support the garden together", correctly flagged). Use
  `--scenarios-only` (19/20 under v5; the failure is the same writer habit) and the
  reviewer-only cases (34/34 under v8) as the real signals.
- **Shell traps on this Mac:** zsh treats `===` as an expansion and aborts the whole
  command (two doc appends silently did not run); there is no `timeout`; a background
  `… | grep` buffers its output, so read the script's own output file instead.
- **External test targets:** httpbin.dev works for redirect tests (httpbin.org and
  postman-echo return 403); Wikipedia `Special:Random` hits 429 on the second hop; gov.il
  returns 403 to bots (shows as `url_http_error`).
- Earlier lessons still hold: measure the failing check before fixing a reviewer; a broken
  `sitecustomize.py` fails open; never name helper scripts after stdlib modules; three
  separate OpenRouter limits (credits, key limit, workspace budget); CI runs `mypy app`;
  reasoning tokens count against output limits; `next dev` on 53073 serves whatever is
  checked out, while the API container needs a rebuild.

## Open risks and debt

- **SP-8, extraction (found live, criterion "headings and paragraphs" unchecked):**
  - Hebrew PDFs with mixed Hebrew/Latin lines come out in visual order: words reordered,
    full stops at line starts. Any Hebrew PDF with English terms, numbers or punctuation is
    affected, so citations and the source check see garbled text.
  - Table-layout pages (paulgraham.com) become one 66,785-character paragraph, so a reload
    treats any edit as the whole page removed and added.
  - Minor: PDF trailing-space padding inflates token counts; Wikipedia footnotes stay as
    raw `<sup>` markup.
  - A fix likely needs a new dependency or library change (bidi handling, or PyMuPDF instead
    of pypdf): an owner decision under the working agreement.
- **SP-10, interface (criterion "keyboard navigation and accessible error announcements"
  unchecked):** focus drops to `<body>` after delete, URL submit and a reload choice; the URL
  field's error has no `aria-invalid`/`aria-describedby`; focus is not moved into the delete
  confirmation; every row's buttons share one name with no source title. Also: Hebrew URLs
  shown percent-encoded; "try again" offered for scanned/encrypted PDFs, where it cannot
  succeed; `upload_conflict` and `refresh_*` codes have no specific message. Still untested:
  upload progress vs processing, polling stopping at a terminal state, empty/loading states.
- **SP-9** has every box checked; response-size, timeout, storage-failure and
  dispatch-failure limits are verified by tests only. It stays In Progress until the owner
  closes it.
- **Source check (v8):** only the bare בהם is a connective (ובהם, בהן, ביניהם still must sit in
  a claim, until a live review shows otherwise). Medium Hebrew reviews peaked at 4,215 of
  5,000 tokens; long drafts (2,400 characters) can still end `grounding_review_truncated`
  (retryable). Earlier v7 limits in docs/implementation.md still apply.
- **Newer wins** was tested with hand-built sources (4/4), not with retrieval of a real
  reloaded page. Conflicts inside one chunk are not resolved by dates; an edited paragraph
  counts as one removed and one new.
- **Not run this session:** `npm run build`. It would overwrite the `.next` folder the owner's
  running dev server uses. CI builds the frontend; the frontend did not change after #22.
- **Carried over:** the 403 workspace-budget error is labelled an authentication failure
  (app/generation_provider.py, app/embeddings.py; no issue); cross-language retrieval only
  translates when nothing is found; topic suggestions sample at most 8 documents and show no
  cost first; SP-5 Done with its media criterion unchecked (belongs to SP-3); stale remote
  branches, now including `claude/sp-27-review-v8`, which should not be deleted without the
  owner.
- **Private files outside git:** `backups/before-sp8-live-check-2026-10-30.dump` (a full
  dump of the owner's DB, ignored). The owner may delete it. A `social_restore_check`
  database exists in Postgres from an earlier restore drill; leave it.

## Verification at delivery

Backend 840 passed on a disposable migrated DB as the runtime role from the repo root (no
`.env`), DB dropped; ruff, format and `mypy app` passed. Playwright 73/73 and frontend
Prettier, lint and tsc passed on `a5f0537` (no frontend change since). Hosted CI 6/6 on #23;
merged with the owner's admin bypass on their instruction and verified on `main` by content.

Live on 2026-10-30/31 (local Docker, `a5f0537` then `21c1dcf`): files, web pages, SSRF
blocking (including redirects and DNS tricks), reload (unchanged, keep, append, replace,
search during preparation), the v5 newer-wins case, v5 scenarios, v8 reviewer-only cases
34/34, and the SP-27 re-reviews (no cut-off; draft 49f7579f finished under v8). Test sources
and test databases were deleted; the owner's data matches the baseline (4 documents, 45
chunks, 9 jobs, 19 runs, 1 post, 1 brand; volume empty).

Paid spend this session: OpenRouter key usage +$0.72 (from $5.057 to $5.777), against the
owner's $1.50 cap. About $4.22 of the $10 workspace budget remains.

## Runtime

API, worker and scheduler rebuilt from `main` (`21c1dcf`) on 2026-10-31; readiness passed and
the API reports `source-review-v8`. Migrations at head `b3e8d5f1c260`. The Next server on
53073 is `next dev` from this checkout (started 2026-10-27). Postgres 55473, Redis 56373, API
127.0.0.1:58073. Ports 3000 and 8000 belong to other projects; never stop them.

## Linear and next task

- SP-16 In Progress: every child Done except SP-21 (Backlog, deferred web search). Whether
  to close SP-16 with SP-21 deferred is the owner's call.
- SP-17 In Progress: SP-7, SP-20 Done; SP-8, SP-9, SP-10 In Progress (gaps above).
- SP-15 In Progress: SP-1, SP-2 In Progress; SP-3 Backlog.
- SP-18 In Progress: SP-11, SP-13 In Progress.

**Recommended next: the SP-10 accessibility gaps** (four concrete fixes plus the untested
states listed above). They were found live, need no paid calls and no owner decision, and
they are the main thing between SP-17 and Done. Then SP-8's Hebrew PDF and table-layout
extraction, which needs a library decision first. Then SP-15, post history (SP-1/SP-2).
