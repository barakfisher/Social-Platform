# Social Platform

Single-user, single-brand content studio. Phase 1 creates drafts for LinkedIn and Facebook in English and Hebrew. Publishing and scheduling are Phase 2.

## Implemented foundation

- Next.js 15 App Router, TypeScript, Tailwind 4, Shadcn-compatible Button and design tokens.
- English/Hebrew routes and translated dashboard shell: Brand DNA, Knowledge Base, Create Post, History. Hebrew is RTL at server render, with logical spacing and borders.
- FastAPI liveness/readiness, configured CORS, consistent errors with request IDs.
- Cross-site protection on the API and its proxies: writes from pages other than this app (`CORS_ORIGINS`) get 403, write bodies must be `application/json` (415), and requests for unknown hosts are refused (API `ALLOWED_HOSTS`, proxy `APP_HOSTS`). Opening the app or API under another hostname requires adding it to these settings.
- PostgreSQL 17 / pgvector migrations, workspace and user ownership constraints, Brand DNA, documents, chunks, drafts, and ingestion jobs.
- Celery/Redis worker with persistent database job status and idempotent probe task.
- Locked dependencies, lint/type/build checks, browser navigation and PostgreSQL integration tests, GitHub Actions workflow.

Brand DNA is functional: load/save your profile and edit six fields in English or Hebrew with validation and save feedback. Knowledge Base supports pasted-text ingestion, processing, preview, retry, and deletion. Create Post generates editable English/Hebrew drafts with source references and saves them to searchable History. Each generated draft now passes a separate sentence-by-sentence source review before display. Check drafts against their sources; AI review is not a factual guarantee. Topic suggestions and media are not yet implemented.

## Start locally

Requirements: Node.js 22+, uv, Docker Compose.

```sh
# From repository root: PostgreSQL, Redis, migrations, API, and worker
docker compose up -d --build

# Frontend runs on the host
cd frontend
npm ci
npm run dev
```

Open http://localhost:53073. API docs: http://localhost:58073/docs (read-only: its "Try it out" writes get 403, because writes are accepted only from the app). Health: `/health/live` (process), `/health/ready` (database migrations and Redis). Readiness does not assert worker availability.

PostgreSQL uses localhost:55473 and Redis localhost:56373 to avoid other local projects. All published ports bind to loopback. Docker credentials are development-only; volumes retain data across restarts. `docker compose down` preserves volumes.

### Host backend development

Start only PostgreSQL/Redis if running API/worker on the host:

```sh
docker compose up -d --wait postgres redis
cd backend
cp .env.example .env
uv sync --frozen --python 3.12
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 58073
# In another backend terminal:
uv run celery -A app.worker.celery_app worker --loglevel=INFO
```

Do not run container and host API on port 58073 simultaneously.

### Verify worker dispatch through the API

Development-only endpoints create a fixed local user/workspace on first use. Ownership is server-controlled; clients cannot select a different user or workspace.

```sh
curl -X POST http://localhost:58073/dev/jobs/probe
# Use the returned UUID:
curl http://localhost:58073/dev/jobs/UUID
```

The job should reach Ready with attempts=1. Redis carries job IDs, while PostgreSQL stores status independently of Redis result expiration. The probe is a foundation smoke test; document ingestion and scheduled recovery are also implemented. `ENVIRONMENT=production` removes `/dev` endpoints. Authentication must replace the fixed local scope before exposing product APIs publicly.

## Checks

```sh
cd frontend
npm run format:check
npm run lint
npm run build
npm run typecheck
npx playwright install chromium
npm test

cd ../backend
uv run ruff format --check .
uv run ruff check .
uv run mypy app
uv run pytest
# Include database tests after migration:
TEST_DATABASE_URL=postgresql+psycopg://social_app:social_app_local@localhost:55473/social uv run pytest
uv run alembic check
```

Database tests roll back their fixtures; the worker test creates and deletes its own temporary owner/workspace. Use a dedicated database in CI. Without TEST_DATABASE_URL, PostgreSQL tests are explicitly skipped.

## Schema and migrations

Runtime role `social_app` has DML access only; `social_admin` applies migrations. The initial migration enables pgvector. Migration files contain frozen schema operations rather than importing live models.

Every owned record has `user_id` and `workspace_id`, enforced against workspace ownership. Chunk and job document references also enforce the same owner/workspace. Document deletion cascades chunks; saved posts retain JSON source snapshots. Post status is constrained to Draft until Phase 2.

OpenRouter embeddings use openai/text-embedding-3-small at 1536 dimensions with profile-aware retrieval. Live provider verification passed. Retrieval currently uses exact cosine search; a production vector index remains outstanding. See docs/ai-setup.md.

Create a migration with `uv run alembic revision --autogenerate -m 'description'`, review it, and run `uv run alembic upgrade head`. Use MIGRATION_DATABASE_URL separately from DATABASE_URL. In production, provision non-superuser migrator/runtime roles outside Compose and require TLS (`sslmode=verify-full` with your CA) on database connections.

## Backup and restore (local procedure)

```sh
mkdir -p backups
docker compose exec -T postgres pg_dump -U social_admin -Fc social > backups/social.dump
# Restore into a separate validation database:
docker compose exec -T postgres createdb -U social_admin social_restore
docker compose exec -T postgres pg_restore -U social_admin -d social_restore --no-owner < backups/social.dump
docker compose exec -T postgres psql -U social_admin -d social_restore -c 'SELECT version_num FROM alembic_version'
```

Backups contain private brand and knowledge data. Production policy: encrypted daily backups retained 30 days, with a monthly restore drill. This is a deployment requirement, not an automated backup service in this repository. Store backups outside the repository. Redis uses AOF with an every-second fsync; sudden host failure can lose the last second of enqueues. Document ingestion will require database reconciliation for pending jobs, rather than relying on the broker as the source of truth.

## Delivery decisions

See [implementation notes](docs/implementation.md). Generation and editable saved drafts are available locally. Remaining work includes PDF/URL ingestion, suggestions, previews, images and broader grounding evaluation.

## Brand DNA editor

Open `/en/brand` or `/he/brand`. Brand name is required (200 characters); audience, positioning, and voice allow 5,000 characters each; guidelines and prohibited claims allow 10,000 each. Fields accept mixed English/Hebrew text with automatic input direction.

`GET /brand` returns the current profile or null; `PUT /brand` creates/updates it. Send version=0 for first creation, then the returned version for updates. Stale writes return 409 and the UI retains edits until you explicitly reload. Ownership is server-controlled; request bodies cannot supply user_id or workspace_id. Fixed local identity is available only in development; production endpoints fail closed until authentication is configured.

The browser calls `/api/brand` on Next.js, which forwards requests to FastAPI. Set the server-side API_URL in frontend/.env.local if the API is hosted elsewhere (default http://127.0.0.1:58073). English and Hebrew views edit the same brand profile.

## Pasted-text Knowledge Base

`/en/knowledge` and `/he/knowledge` accept a title (1–300 characters) and text (1–100,000 characters). Source text is stored privately in PostgreSQL with server-controlled workspace/user ownership; it is not included in list responses, logs, or queue messages. The worker receives a job ID. PDF/URL ingestion and object storage are later work.

Text is normalized to NFC and LF line endings and trimmed. SHA-256 deduplication within a workspace returns the original source regardless of title, without queueing another job. A unique database index makes concurrent duplicate submissions safe.

Celery prepares Unicode-safe chunks targeting 800 cl100k_base tokens with a suffix overlap of up to 100 tokens. Paragraph/newline boundaries are preferred; each chunk records character offsets into the normalized source, tokenizer name, token count, and ordering. The tokenizer cache is bundled into the Docker image. Verify tokenizer compatibility and re-chunk if needed when choosing the embedding model.

After preparation, the ingestion job is Ready but the document remains Processing with stage=text_prepared. UI displays “Text prepared” and stops polling. Documents must not become Ready for retrieval until all embeddings exist. No AI calls or generation are performed in this step.

API endpoints: POST /knowledge/text, GET /knowledge (offset/limit pagination), GET /knowledge/{id}, POST /knowledge/{id}/retry, DELETE /knowledge/{id}. Every endpoint enforces the same local server-owned scope; production access stays gated until authentication is configured. Sources and jobs commit before dispatch. Dispatch failures preserve the source, record a Failed status, and permit explicit retry. Permanent worker failures are recorded with a safe error code. Database locks serialize processing, retries, and deletion; duplicate delivery cannot duplicate chunks, and deleted sources cannot be recreated by old messages.

A dedicated Celery beat scheduler checks durable jobs every minute. It requeues up to 100 Pending ingestion/embedding jobs older than two minutes and abandoned Processing jobs older than ten minutes, while skipping actively locked embedding workers. Failed jobs require explicit retry. For immediate recovery, run `docker compose exec api python -m app.reconcile`. The ten-minute grace exceeds task hard limits and Redis visibility timeout.

Validation includes 26 backend tests, six browser tests, and a live browser-to-worker save/prepare/reload/delete check.

## Embeddings and AI search

The provider client, resumable embedding worker, Ready gating, and scoped vector-search API are implemented and live-verified with OpenRouter. Provider connectivity, source readiness, idempotent embedding requests, and semantic retrieval passed; temporary verification data was removed. See [AI setup](docs/ai-setup.md) for configuration and repeat verification. Credentials remain local in the Git-ignored backend/.env.

The default configuration is OpenRouter / openai/text-embedding-3-small / 1536 dimensions, with separate embedding credentials. Configuration/model/revision changes are isolated using profile hashes; existing vectors must be re-embedded before they are eligible for the current search. The generation API retrieves Ready sources and performs a separate factual-support review.

## Worker reliability verification

Run `python3 scripts/verify_worker_recovery.py` from the repository root. It builds a disposable Compose project with its own PostgreSQL, Redis AOF volume, API, worker, and scheduler. The API uses a random loopback port. The test exercises a Redis SIGKILL/restart, duplicate delivery, database-backed status after isolated Redis data loss, automatic recovery by the real minute scheduler, structured log correlation, and graceful worker shutdown. It cleans up its own containers and volumes; development services and data are not changed. The CI workflow includes the same check.

Worker domain events are JSON with job_id, document_id, and request_id. Arbitrary logging extras and exception bodies are excluded. Celery timeouts, late acknowledgements, broker-loss cancellation, concurrency, and visibility timeout are configured together; provider failures still follow their bounded retry policy.
# Social-Platform

## Generate and save drafts locally

Configure Brand DNA, paste a source in Knowledge Base and enable AI search until it is Ready. Open Create Post, select platform/language and preferences, generate, review and edit, then Save Draft. History supports searching, editing and deleting drafts. Generation defaults to configurable OpenRouter `openai/gpt-4.1`. It can reuse the existing embedding key on official OpenRouter; all provider calls and secrets stay on the backend. See backend/.env.example for generation budgets and docs/implementation.md for known grounding limitations and retention.

To run the opt-in live provider evaluation (incurs API usage): `cd backend && uv run python scripts/evaluate_generation.py`. It uses a disposable database and deliberately fails known unsupported embellishments. It checks six rejected examples and two bilingual generation/save/edit/delete flows. Exact excerpt validation and model review improve grounding but cannot guarantee factual correctness.
