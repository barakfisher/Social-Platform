# Social Platform handoff — 2026-10-26 (Asia/Jerusalem)

## User intent and workflow

Continue implementation locally in this existing checkout. The user requested handoff + merge + a new session on 2026-10-26, authorizing committing and pushing this delivery to main. Repository origin: https://github.com/barakfisher/Social-Platform.git. This delivery contains the previously untracked application, not just the interrupted-generation patch. Inspect Git history/status for the completed merge and hosted checks. Preserve private git-ignored backend/.env and all local data. No paid provider checks are authorized merely by startup or merge. Future implementation should stay local unless the user requests another delivery.

Read root AGENTS.md. Keep parents In Progress while any required children/acceptance criteria remain. Completed slices do not close overlapping original requirements. Record actual evidence and deferrals in existing Linear issues; mocked tests are not live provider evidence. No subagents requested.

## Product decisions

Single user/brand initially, with user_id/workspace boundaries preserved. Phase 1 drafts only; publishing/scheduling Phase 2. English/Hebrew with RTL and Tailwind logical properties. Four sections: Brand DNA, Knowledge Base, Create Post, History. Monorepo frontend Next.js 15 App Router; backend FastAPI/Celery; PostgreSQL/pgvector and Redis via Compose.

## Running locally

Frontend http://127.0.0.1:53073 (another project owns 3000; do not kill it). API localhost:58073; PostgreSQL 55473; Redis 56373. Docker services api, worker, scheduler, postgres, redis, migrate. Frontend is currently running a production build with `cd frontend && npm run start`; use `npm run dev` for further development after stopping only this project’s frontend. Stop only this project's dev process before production build to avoid concurrent .next corruption, then restart. Current availability should be rechecked, not assumed.

The last live workspace configuration check showed configured=true, brand_ready=true, ready_documents=0. This is why Generate Draft is disabled: the user must add/prepare a Knowledge Base source and enable AI search until Ready. Brand and provider are connected. No user source was invented/added to bypass this. Most recent user question was why they couldn't create a draft; this prerequisite was explained. Their browser was on /he/knowledge.

## Implemented

- Bilingual RTL dashboard and Brand DNA profile GET/PUT, version conflicts, persistence.
- Pasted-text ingestion with normalized checksum dedup, durable job IDs, preview/retry/delete, Unicode-safe 800/100 cl100k_base chunks.
- OpenRouter embeddings openai/text-embedding-3-small, 1536 dimensions, model/profile validation, bounded batches, safe errors/retries, advisory locks, Ready gating, scoped exact cosine retrieval. Official OpenRouter bare response alias accepted only for this model at official endpoint.
- Worker recovery scheduler, age thresholds and locks; structured metadata-only logs. Isolated real Redis crash/data-loss/scheduler/graceful shutdown verification passed previously.
- Generation API with validated platform/language/topic/goal/tone/hook/length/CTA; Ready-only scoped retrieval, context/prompt budgets, versioned Brand DNA, idempotent UUID requests, stored model/usage/preferences/source metadata.
- Separate sentence-level source review before Ready/display. Current prompt grounded-post-v3; reviewer source-review-v2. Every numbered sentence requires supporting exact excerpts; server checks ordered coverage, quote membership, requested EN/HE script. Unsupported/malformed/unavailable/over-budget reviews withhold content. UI preserves inputs with localized failure and fresh-key retry. Old cached prompt/review versions cannot bypass review/save. Legacy GET results are marked ungrounded. User edits clear grounded flag; review provenance applies to original generation.
- Default configurable writer and reviewer now OpenRouter openai/gpt-4.1, tokenizer o200k_base. GPT-4o and a simple yes/no review failed live quality tests and were replaced. Both tokenizer caches bundled in Docker. Generation/review each receive half GENERATION_MAX_REQUEST_USD including allowed retries; actual usage/cost tracked separately and totalled. Estimate is not provider billing cap; query embedding is separate.
- EN/HE Create Post form, advanced preferences, editable output, save/update Draft.
- Draft CRUD/search APIs with owner scoping, idempotent creation, optimistic updates, pagination/platform/Draft filters, PostgreSQL simple full-text plus Unicode substring search, deterministic sort.
- History search/list/edit/conflict/reload/confirmed delete, source snapshots. Hard delete removes draft + associated generation result; unsaved generation results have no automatic expiry. No media objects yet.
- Latest migration 04825b5fcc24; Alembic schema drift check passed.

## Verification and secrets

Last checks: 82 backend tests with PostgreSQL passed (completion providers mocked in automated suite); 13 Playwright tests passed; frontend production build, lint/format/types, backend Ruff/mypy, Alembic drift passed. Updated Docker services rebuilt and API readiness passed. Check docs/ai-setup.md, docs/implementation.md and verification/generation-grounding.md.

Paid opt-in live evaluation: `cd backend && uv run python scripts/evaluate_generation.py`. It creates/migrates/drops only a randomly named disposable database, uses real embeddings/completions, substitutes direct worker execution for queue dispatch, leaves user workspace untouched. Last final run rejected six negative cases (EN/HE aroma, embellished volunteers, copied source injection/prohibited promise, fabricated time/price, wrong language; first five live reviews, last deterministic) and passed EN LinkedIn + HE Facebook generation/save/read/edit/delete. Positive completion costs about $0.0053/$0.0056 excluding embedding. Small fixture success is not broad semantic accuracy proof. No automatic repair loop; rejection retains inputs for manual retry.

Provider key is private in git-ignored backend/.env. Never print/read secrets into outputs or copy into handoff/commits. GENERATION_API_KEY may reuse EMBEDDING_API_KEY only when both endpoints are official OpenRouter. Settings/examples contain no real key. `git check-ignore backend/.env` passed.

Commands:
- `cd backend && uv run ruff format --check . && uv run ruff check . && uv run mypy app`
- `cd backend && TEST_DATABASE_URL=postgresql+psycopg://social_app:social_app_local@localhost:55473/social uv run pytest`
- `cd backend && uv run alembic check`
- `cd frontend && npm run format:check && npm run lint && npm run build && npm run typecheck && npm test`

## Linear and next work

Project Social Platform (P-SP-3): https://linear.app/test-bf/project/social-platform-a4450460ffa3 . Relevant tool namespace mcp__codex_apps__linear. Discover metadata with ALL_TOOLS. get_agent_context was tried but server repeatedly returned Tool not found; other Linear tools work.

- SP-4 grounded generation In Progress: follow-up evidence recorded; do not silently close. Next: broaden live adversarial/domain evaluation (conflicting facts, irrelevant sources, unsupported requests in both languages), then validate against actual user Brand DNA/Ready sources when available. Current small live fixture passed but remaining release criteria are visible.
- SP-16 generation parent In Progress. SP-5 creation form In Progress: suggestions/media unfinished. SP-6 topic suggestions Backlog.
- SP-15 Media/History parent In Progress. SP-1 CRUD In Progress: media lifecycle and Phase 2 status semantics outstanding. SP-2 History In Progress: URL-preserved search/filter state, media indicator/restoration and full saved preference restoration outstanding. SP-3 media/preview Backlog.
- SP-17 Knowledge parent In Progress: SP-7 embedding Done (real provider/source/query passed); SP-20 pasted slice Done; SP-8/9/10 partial for PDF/URL/private file/object storage requirements.
- SP-18 Foundation In Progress: SP-14 scaffold Done, SP-12 reliability Done; SP-11/13 partial (production/index/remaining schema requirements). SP-19 Brand editor Done.

Do not confuse open parents displayed as context in Linear Done views with completed parents. Check actual statuses/children before any closure. No hosted CI run/push/merge is claimed. Prioritize finishing SP-4 before expanding suggestions/media. On new-session startup: read this document, inspect checkout without mutations, confirm inherited state and wait. Do not start paid tests, publish, push, create PRs or modify user data merely as startup work. Resume implementation when asked.


## Continuation — 2026-10-26

Interrupted-generation recovery is implemented locally in app/generation.py: transaction advisory request lock; active requests protected; orphan Processing becomes Failed/generation_interrupted on retry or GET; explicit fresh-key retry only, no automatic provider replay. EN/HE UI explains interruption and preserves inputs. This is on-access recovery, not a scheduled sweep. Backend 85 tests passed; all 14 browser tests passed against the production build (an earlier dev-server navigation timeout passed in isolation). Frontend production build/types passed and npm run start is running on port 53073. See docs/implementation.md for evidence and remaining scope. API rebuilt and readiness passed. No paid evaluations, PR/push/merge, or user-source edits this turn. Next engineering scope is broader grounding evaluation; SP-4 and broader parents stay open.


## Delivery request — 2026-10-26

User explicitly requested “handoff + merge + start a new session.” Delivery workflow commits the complete existing implementation to a codex branch, merges into main and pushes origin/main; no PR was requested. Earlier local-only/no-merge notes above are historical and superseded for this delivery only. Check the final Git log and GitHub Checks run for actual delivery state. Keep incomplete Linear issues open.

New session first action: read root AGENTS.md and this handoff, inspect git status/log, confirm loaded state and give a concise next-step summary, then wait. Next engineering priority: broader adversarial/domain grounding evaluation (conflicting facts, irrelevant sources, unsupported requests in EN/HE), brand/platform-fit checks, requested model availability/deployment decision, and actual-user Brand DNA/Ready-source validation. Paid provider evaluation needs explicit authorization beyond this merge/startup request. Current user workspace still has zero Ready sources; user must supply/prepare their own source before UI generation. No source should be invented to bypass this requirement.
