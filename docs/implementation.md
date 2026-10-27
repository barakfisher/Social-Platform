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

## Decision: per-request completion reservation cap raised to $0.10 — 2026-10-26

Problem: with four Ready sources, every Create Post request failed with
`generation_spending_limit` before any completion call. The preflight reserves
(prompt + 128) × prompt price + max output × completion price per attempt, times
(retries + 1). With GPT-4.1 ($2/$8 per million tokens), 900 output tokens and one retry,
a $0.025 stage allowance (half of $0.05) fits a prompt of only about 2,500 tokens, while
GENERATION_CONTEXT_BUDGET alone allows 2,800 source tokens. Small single-source workspaces
worked; any workspace whose retrieval filled the context budget could never generate.

Choice (owner-approved): default GENERATION_MAX_REQUEST_USD 0.10. The smallest stage
allowance, after the 20% translation share, is $0.04; the largest prompt the prompt-budget
guard admits (6,000 tokens) reserves about $0.039 with one retry. Actual spend is unchanged
by the cap (earlier runs cost roughly $0.005–0.015 per request); it is a reservation ceiling.

Rejected alternatives:
- Keep $0.05 and shrink GENERATION_CONTEXT_BUDGET to roughly 1,200 tokens: the writer and
  reviewer would see one or two chunks, raising insufficient-context and unsupported-claim
  rejections for real topics.
- Leave the values and only improve the error: every multi-source workspace would still be
  unable to generate.

Guard: tests/test_generation_budget.py builds Settings from code defaults (no .env) and
fails if the largest admitted prompt for the default writer or reviewer cannot pass the
spending preflight. It fails on the old $0.05 default. It pins GPT-4.1 catalog prices, so
update it when the default model changes. Raising GENERATION_RETRIES to 2 at this cap would
reintroduce the conflict for maximum-size prompts. The UI now shows a specific EN/HE
message for `generation_spending_limit` instead of the generic error.

## Decision: claim-level source review (source-review-v4) — 2026-10-26

Problem: under v3 a Hebrew draft passed review even though its first sentence made an
origin claim that the retrieved context did not contain. Its exact quotes supported only
the rest of the sentence. Exact-quote and ordered-coverage checks cannot catch a clause
that no quote is attached to (verification/generation-grounding.md).

Choice (owner-approved):
- The reviewer splits each sentence into claims copied exactly from it. The server requires
  the claims to cover every word except a fixed EN/HE connective list, and every claim to
  be supported by exact quotes. Unsupported claims may have empty evidence.
- The reviewer cites short aliases (S1, S2...) instead of UUID chunk IDs, mapped back to
  real IDs in stored provenance.
- The reviewer gets its own GENERATION_REVIEW_MAX_OUTPUT_TOKENS of 1600; the writer stays
  at 900.
- GENERATION_MAX_REQUEST_USD rises from $0.10 to $0.13, superseding the $0.10 entry above.
  The reviewer's smallest stage share after the 20% translation share is $0.052. Its worst
  case (6,000-token prompt, 1,600 output tokens, one retry, GPT-4.1 prices) reserves about
  $0.0501, which exceeds the $0.040 share at $0.10. Actual spend is not set by the cap;
  it is a reservation ceiling.

Measured basis: compact v4 output for a 600-character post was 818–1,322 tokens in Hebrew
and 626–974 in English with aliases (2–5 claims per sentence, o200k_base), and up to about
1,950 with UUIDs.

Rejected alternatives:
- Stronger v3 prompt wording only: the v3 prompt already forbade world knowledge and
  required every clause to be checked, and the model still accepted the clause.
- A second per-sentence verification call: about double the review cost and still relies
  on the model.
- A lexical check of draft words against sources: Hebrew prefixes and inflection make it
  wrong in both directions.
- Aliases with the shared 900-token limit: full-length Hebrew posts would often truncate
  the review and fail as grounding_review_invalid.

Known limits: a reviewer can still pair a claim with an unrelated exact quote; coverage
makes that deliberate rather than an omission, but does not prevent it. A 1,600-token
review may approach the 30-second GENERATION_TIMEOUT; this is not measured. v4 has not
been run against the live model. tests/test_generation_budget.py now checks each stage
with its own output limit and fails at $0.10.

## Decision: GPT-5.6-terra default reviewer, user-selectable per draft — 2026-10-26

Problem: GPT-4.1 accepted an unsourced origin clause in the private Hebrew case and in the
`outside_context_he` fixture, even under source-review-v4. In the paid 25-case comparison,
GPT-5.6-terra was the only candidate that rejected both, with no truncation or retries
(verification/generation-grounding.md).

Choice (owner-approved):
- GENERATION_REVIEW_MODEL defaults to `openai/gpt-5.6-terra`.
- Users choose the source-check model per draft in Create Post's advanced options, from
  the server allowlist GENERATION_REVIEW_MODELS (GPT-5.6-terra, GPT-4.1). The API resolves
  an omitted choice to the default before fingerprinting, rejects unlisted models with 422
  `review_model_unavailable`, stores the choice in run inputs and keeps it out of the writer
  and reviewer prompts. review_draft re-checks the allowlist.
- `GET /generation/review-models` returns, per model, a typical cost (one measured
  realistic review's tokens × the live catalog price) and a maximum (the reservation for the
  largest admitted prompt, full reviewer output limit and every retry). Models missing from
  the catalog are listed but cannot be chosen. The UI shows the selected model's cost
  below the select, because closed selects truncate options on phones.
- GENERATION_MAX_REQUEST_USD rises from $0.13 to $0.16, superseding the $0.13 entry above.
  GPT-5.6-terra's worst-case review reserves about $0.0629 against a $0.064 share. The
  budget guard test now checks every selectable reviewer.

Rejected alternatives:
- A workspace-wide setting, or both a setting and a per-draft override: switching models to
  compare would take more steps, or more UI and API surface for one user.
- Offering Claude Sonnet 5.5 now: its reasoning used the whole 1,600-token output limit on
  the longest case, and the app does not control reasoning effort yet.
- Showing only the maximum cost (overstates typical spend about four times) or only the
  typical cost (hides the server's per-draft ceiling).
- Keeping $0.13 with a 1,000-token reviewer limit: GPT-5.6-terra's longest review already
  used 907 tokens including reasoning.

Known limits: the typical cost comes from one realistic review, so remeasure when the
review prompt or models change. Estimates cover the source check only; writing, query
translation and embeddings are separate. GPT-5.6-terra can penalize a draft for omitting
an unsupported request (`missing_requested_future_launch_date`), which is a false-rejection
risk. Generation with GPT-5.6-terra has not been run end to end.

## Decision: same-origin guard on API proxy writes — 2026-10-27

Problem: the Next.js proxies under `frontend/src/app/api` accepted a write when
`content-type` merely contained `application/json`, and nothing checked where a request
came from (`middleware.ts` skips `/api`). Browsers treat `text/plain;application/json` as
`text/plain`, a "simple" content type that needs no CORS preflight. Reproduced on a dev
server whose API_URL pointed at a logging stub (no FastAPI, no provider): a page on
`http://localhost:53174` sent `fetch(..., {mode: "no-cors"})` to `127.0.0.1`. Both
`POST /api/generation` (body `text/plain;application/json`) and a bodiless
`POST /api/knowledge/<id>/embed` reached the stub, so any open site could start paid
generations or embeddings. A page on another local port (same site, different origin)
could do the same. After the fix both get 403 and nothing reaches the stub.

Choice: `frontend/src/lib/csrf-guard.ts` (`rejectUnsafeWrite`), called first by every
proxy route, before path validation and before any upstream call.
- GET/HEAD/OPTIONS are never blocked.
- A write is rejected with 403 `cross_site_request` when `Sec-Fetch-Site` is present and
  not `same-origin`, or when `Origin` is present and differs from the request's own
  protocol plus `Host`. Using the request's `Host` keeps both `127.0.0.1:53073` and
  `localhost:53073` working.
- A write whose body is forwarded must have content-type essence exactly
  `application/json`, or it gets 415 `invalid_content_type`.
- A write with neither `Origin` nor `Sec-Fetch-Site` is allowed. Current browsers send
  `Origin` on every cross-origin POST, so only non-browser clients (curl, scripts) omit
  both, and those cannot use the user's browser.

Rejected alternatives:
- Fix only the content-type check: bodiless POSTs (knowledge retry/embed) send no body
  to check, so cross-site paid embeddings would remain.
- Check only `Sec-Fetch-Site`: browsers without Fetch Metadata (older Safari) send only
  `Origin`, and they would pass.
- Rejecting writes without `Origin`: breaks curl and scripts against the local API
  without stopping any browser attack.
- Comparing `Origin` with one fixed configured origin: opening the app as `localhost` vs
  `127.0.0.1` would reject the owner's own saves. An allowlist of both hosts would work and
  would also stop DNS rebinding; it is deferred as a follow-up, not rejected.
- Enforcing in `middleware.ts`: middleware currently excludes `/api`. Next.js advises
  against relying on middleware alone for access checks (CVE-2025-29927 bypassed it), and
  routes already decide which writes forward a body. A test instead fails if any
  `route.ts` under `src/app/api` stops calling `rejectUnsafeWrite`.
- CSRF tokens: needs per-session state and client changes in every form. For a
  single-user local app, same-origin checks give the same protection.

Known limits: DNS rebinding (an attacker domain re-resolved to 127.0.0.1) makes `Host`,
`Origin` and `Sec-Fetch-Site` look same-origin and passes this guard. Blocking that needs
a `Host` allowlist; it is not implemented. FastAPI itself (127.0.0.1:58073) has no origin
check, and a browser page can send simple requests to it directly, bypassing this guard.
A `no-cors` POST whose body is a Blob or ArrayBuffer carries no Content-Type, and FastAPI
0.162.0 parses a body without Content-Type as JSON (`fastapi/routing.py`, read in source,
not exercised). So any open page can likely call `POST /generation`, `PUT /brand`,
`POST /posts` and the bodiless knowledge writes on the backend directly. Chrome's Local
Network Access prompt may stop public sites, but not a page on another local port. Closing
this needs a backend check (JSON content type plus Origin on writes); it is a follow-up.

Tests: `frontend/tests/csrf-guard.spec.ts` covers the guard's rules (same-origin allowed;
other site, other local port, `null` origin, foreign Origin alone and Sec-Fetch-Site
alone rejected; `text/plain;application/json` rejected; bodiless, non-browser and GET
allowed), the route coverage check, and two browser cases against the dev server that
target an invalid path so no request can reach the backend. With the guard disabled, 8
of the 13 tests fail.
