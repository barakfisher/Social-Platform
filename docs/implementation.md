# Implementation decisions — 2026-10-25

Confirmed by the project owner:

1. Single-user/single-brand initially; retain user_id for future tenant ownership.
2. Draft generation only in Phase 1; publishing/scheduling in Phase 2.
3. English and Hebrew, with RTL and Tailwind logical properties from day one.
4. Shadcn UI / Tailwind dashboard: Brand DNA, Knowledge Base, Create Post, History.
5. One repository: frontend (Next.js 15), backend (FastAPI/Celery), Compose (PostgreSQL/pgvector and Redis).
6. Order: Foundation → First Working Flow → Expand.

Foundation deliberately retains workspace boundaries in addition to user ownership. Local development uses server-owned fixed identity, not caller-supplied user IDs. Authentication is required before public deployment.

Text generation is planned through OpenRouter. Before integrating live AI, select generation and embedding models, obtain credentials, and set cost/usage limits. Embedding dimensions are not guessed in the initial schema.

No hosted repository or Git remote was supplied. CI configuration is prepared locally; no GitHub workflow has run yet.

## Brand DNA editor delivered

GET/PUT profile API and localized form share the existing BrandDNA model. Atomic version-checked writes prevent stale-tab overwrites. PostgreSQL upserts make local identity bootstrap safe under concurrent first saves. The fixed server identity is gated to development; no caller-supplied ownership is accepted. Same-origin Next.js API proxy uses server-side API_URL.

Verified: 15 backend tests, four Playwright scenarios, frontend production build, lint/type checks, and live browser save/reload against the Docker API and PostgreSQL. Temporary live verification data was removed afterward. Next delivery: pasted-text knowledge ingestion.

## Pasted-text ingestion delivered

Knowledge Base now stores bounded pasted text, deduplicates normalized content, dispatches durable job IDs, prepares Unicode-safe chunks, and exposes scoped status/preview/retry/delete operations. UI is English/Hebrew with polling and clear text-prepared state. Document Ready remains reserved for embeddings. Source text is stored in private PostgreSQL rows for this slice; file/object storage is not implemented.

Migrate to 6f3256b0e448 before starting the updated API/worker. Recovery command: python -m app.reconcile. Next: configure an embedding provider/model, then grounded generation. SP-8/9/10 remain partial until PDF/URL and remaining requirements are delivered.

## Embedding integration implemented; live verification pending

Configured OpenRouter-compatible embedding client and separate secret settings, safe error codes, response validation, bounded retries, durable resumable batches, per-job PostgreSQL advisory locks, document Ready gating, profile-aware re-embedding, and scoped query retrieval. English/Hebrew UI exposes connection state and per-source embedding actions. Migration: 00df4e86db62.

No provider keys were configured. The Git-ignored backend/.env now contains an empty embedding-key slot and defaults; no fake vectors or test credentials were put into the application database. Offline tests use isolated rollback fixtures and mocked provider responses. SP-7 remains In Progress until live provider/source/query smoke tests pass. See docs/ai-setup.md.

## Worker recovery completion

Added minute-scheduled recovery for lost enqueues and abandoned Processing jobs, with age thresholds and advisory-lock exclusion for active embedding work. Domain logs now emit whitelisted JSON correlation fields. Redis AOF persistence, duplicate delivery, database-backed status after broker data loss, real scheduled recovery, and graceful shutdown are checked by scripts/verify_worker_recovery.py in an isolated disposable stack. The development Redis/database are never stopped or cleared by this verification. CI now includes the isolated recovery check; hosted CI remains unrun without a Git remote.

Verification result: all 52 backend tests passed; the isolated live Redis crash/data-loss/scheduler/graceful-stop verification passed. SP-12 is Done with all acceptance criteria checked; SP-18 remains In Progress. Live embedding verification is still pending a provider key.

## Live embedding verification complete

The configured OpenRouter key passed the provider smoke test at 1536 dimensions. A temporary bilingual source was ingested by Celery, embedded to Ready, requested again idempotently, retrieved by a semantic query, and deleted afterward. Live testing revealed that OpenRouter returns text-embedding-3-small for the requested openai/text-embedding-3-small route; the client now accepts this specific upstream alias only for the official OpenRouter endpoint. Different model IDs and aliases on unrelated endpoints remain rejected. All 54 backend tests pass. SP-7 can be completed; the Knowledge Base parent remains open for its unfinished PDF/URL/file-storage requirements. No user source was modified for the live check.

## Draft generation and history — local delivery

Added versioned generation requests, scoped Ready-source cosine retrieval, bounded prompts, JSON completion validation, provider usage metadata, and idempotent requests. English/Hebrew forms support LinkedIn/Facebook, topic/goal, tone/hook/length/CTA, editable output and Draft save. History supports platform filters, debounced search, pagination, editing with version conflicts, source snapshots and confirmed deletion. Local-only identity gating remains in force. Migration: 04825b5fcc24.

The default generation model is configurable OpenRouter `openai/gpt-4o`; live catalog availability and generation were verified. Claude 3.5 Sonnet was absent from the catalog checked. A separate GENERATION_API_KEY is optional when the existing embedding key and both URLs use official OpenRouter. The preflight cost estimate includes allowed retries and rejects requests exceeding GENERATION_MAX_REQUEST_USD; it is not an account billing cap, and token estimates are approximate. Timeouts or malformed paid responses can still incur provider charges. Source and prompt budgets use the existing cl100k tokenizer as an estimate.

Live evaluation used a disposable migrated database, real embeddings and real completions, with English LinkedIn and Hebrew Facebook fixtures containing injected instructions. Both completed generation/save/edit/delete and ignored the injection. Human review nevertheless found unsupported embellishments (for example the Hebrew draft added an aroma description). The lexical evaluation originally missed this synonym; it has been expanded and is not a semantic grounding guarantee. SP-4 remains In Progress: stronger grounding checks and a broader curated evaluation must pass before release. Sources returned and the legacy grounded flag indicate cited retrieval, not independent verification of every claim; the form explicitly asks users to review factual claims.

Run the opt-in paid live evaluation with `cd backend && uv run python scripts/evaluate_generation.py --live`. It fails on known unsupported phrases and removes only its own temporary database. Never weaken a failed evaluation to mark the issue complete.

Deletion hard-deletes the saved draft and its associated generation result. Source snapshots remain with drafts until deletion; deleting a knowledge source does not erase existing draft snapshots. Unsaved generation results are retained locally without automatic expiry. Interrupted requests are now recovered on retry/status reads; see the 2026-10-26 follow-up below. No media objects are created yet.

Still open: semantic grounding quality, topic suggestions, image upload/system media, History URL state and media restoration. Scheduling/publication remain Phase 2. Parent issues stay open. Work is local and unmerged; no push or hosted CI execution is claimed. A GitHub origin was present at the final check, but this delivery remains local as requested. The frontend now runs at http://127.0.0.1:53073 because another local project uses port 3000.

Verification for this delivery: 69 backend tests passed with PostgreSQL enabled (completion providers mocked in the automated suite); 12 Playwright tests passed; production build, frontend lint/format/types, backend Ruff/mypy and Alembic schema drift checks passed. Docker services were rebuilt and migrations applied. Paid live provider checks are separate from automated tests and have the grounding limitation above.

## Grounding review follow-up — 2026-10-25

This supersedes the initial generation defaults and citation-only grounding behavior above. Prompt grounded-post-v3 now requires separate source-review-v2 before a draft reaches Ready. The default writer and reviewer are configurable OpenRouter GPT-4.1. GPT-4o's embellishments and a weak yes/no review failed live tests; neither was treated as sufficient evidence. The final reviewer checks every numbered sentence with exact source excerpts, and the server checks coverage, excerpt membership and requested EN/HE script. Unsupported or malformed reviews withhold content. Old cached versions cannot bypass review; saved user edits clear the grounded flag and preserve review provenance for the original generation.

Completion spending is split into two conservative half-budget allowances including retries. Actual usage for both stages is stored; cost estimates are not a billing guarantee. Generation/review budgets use configurable o200k_base while ingestion remains cl100k_base.

Live verification passed six negative cases plus English LinkedIn and Hebrew Facebook generation/save/edit/delete against a disposable database with real provider calls. Final generated fixture drafts stayed within sourced garden facts. Model review remains probabilistic, and broader domain/adversarial evaluation remains visible on SP-4. Topic suggestions, media, History URL state remain unfinished; parent issues remain open. No PR, push or merge was performed.


## Interrupted generation recovery — 2026-10-26

Each generation request now holds a PostgreSQL transaction advisory lock scoped to its workspace, user and request key. A separate connection owns that lock across retrieval, writer and reviewer calls; no data row lock is held across provider calls. Concurrent requests return generation_in_progress. PostgreSQL releases the lock when its owning connection/process closes. Retry/status reads encountering Processing without a live lock mark the run Failed with generation_interrupted. Recovery is on access, not a scheduled sweep or automatic provider replay; untouched orphan rows remain Processing until accessed. A fresh explicit retry uses a new key. English/Hebrew error copy explains this while preserving inputs. Existing cached Ready results remain idempotent and undergo the existing review-version gate.

## Cross-language retrieval continuation — 2026-10-26

When the original scoped query returns no hits, generation now tries one bounded EN/HE
query translation using the existing configured writer model. It targets the other script
based on the topic, not the requested post language. The translation is strictly validated
and capped at 450 output tokens and 1,000 characters. Topics without EN/HE letters skip it.
The translated query uses the same embedding model, Ready/profile/owner filters, relevance
cutoff and context budget. Existing hits that cannot fit the context budget do not trigger
translation. Original preferences reach the writer and reviewer unchanged; translated text
is never evidence and is not included in returned metadata.

Direct retrieval retains half-budget writer/reviewer allowances. Translation first reserves
at most 20% of GENERATION_MAX_REQUEST_USD, including its permitted retries. After completion,
its per-attempt maximum estimate multiplied by attempts actually made remains reserved;
unused future translation retries cannot run. Writer and reviewer each receive half the
remaining allowance, including their own permitted retries. Invalid reservation metadata
fails closed. Translation usage and this consumed estimate are retained on success and
downstream failure; successful total reported completion cost includes all three stages.
This remains an estimated completion limit, not a provider billing cap. The additional
query embedding is separate from completion cost accounting.

Source review is now source-review-v3. It explicitly requires separate exact evidence
entries for nonadjacent passages instead of stitched quotations. Exact substring, source
ownership and ordered sentence coverage checks are unchanged. Old review approvals cannot
bypass retry/read/save version gates. This improves the contract but does not eliminate
model disagreement or false rejection; actual-user validation results and remaining limits
are recorded in verification/generation-grounding.md. SP-4/SP-16 remain In Progress.

Verification: 85 backend tests passed with PostgreSQL, including real separate-connection lock exclusion/release, active-run protection, recovery via POST/GET, no provider replay and fresh-key success. Provider completions remain mocked. Browser suite: all 14 tests passed against the production build. An earlier development-server run had an unrelated navigation timeout that passed in isolation. Both grounding-failure and interruption retry cases passed. Ruff/mypy, frontend production build/lint/format/types and Alembic drift passed. Frontend left running with npm run start on port 53073. API image rebuilt and readiness confirmed locally. No paid provider evaluation or user document changes were performed. SP-4 and parent issues remain In Progress; broad grounding/brand/platform evaluation, requested model deployment checks and actual-user-source validation remain outstanding.
