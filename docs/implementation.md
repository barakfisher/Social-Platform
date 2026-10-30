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

## Decision: advisory source review — drafts are always shown — 2026-10-27

Problem: drafts were withheld whenever the reviewer found any sentence without an exact
quote. Humor, questions and calls to action (CTAs) always failed, because they carry no
quotable fact. Three real Hebrew attempts ("מה זה מנטורינג", humorous tone, "הרשמה לקורס"
CTA) were billed (~$0.024 each) and discarded with a generic message. Ready sources were
retrieved in every attempt.

Choices (owner-approved, one question at a time):
1. Claims are typed. A factual claim still needs exact quotes. A creative claim (humor,
   metaphor, a question, an invitation) passes without evidence if it states no fact. The
   CTA the user chose is the owner's intent, not a fact to prove.
2. Web search is deferred. It will be decided from how many drafts still get findings for
   missing facts once (1) ships.
3. Tone and CTA are preset selects with "Other…" free text. The server validates preset IDs
   and maps them to writer instructions, so a preset's needs (an offer, a link) are known.
4. Optional "offer details" (course name, date, link). It is owner-provided evidence for
   that post only, treated as data. The writer may use it freely, but any fact it takes from
   it must match it. A CTA with no details may only invite in general terms.
5. A draft is always persisted and shown. Review problems become findings: a sentence
   excerpt plus a problem code, rendered in a separate "Points to check" panel and never
   inline in the text. Only copied source instructions or revealed system instructions
   block a draft.
6. A technical reviewer failure (timeout, malformed review, unavailable model) still shows
   the draft, marked unchecked, with a reason. "Check again" is offered only when a retry
   can help; spending, context or configuration limits do not offer it.
7. "Check again" reviews the server-saved version (generation result or saved draft),
   replaces the stored findings and records which version was checked.

Rejected alternatives:
- Keep fail-closed and rely on more sources or web search: humor and CTAs still fail,
  because they contain nothing to quote.
- Let the model use world knowledge without sources: it removes the only evidence that a
  fact is true. The model cannot tell a fluent hallucination from a fact.
- Inline highlights in the editable text: they mix review marks into the content the owner
  edits and publishes.
- Block brand-rule violations: it brings back "error with no draft" for a quality issue the
  owner can fix by editing.
- Free text with suggestion chips for tone and CTA: the server cannot tell which preset was
  chosen, so it cannot know a CTA needs an offer.
- Re-check only the original generation: after an edit the button would have no use.

Why the blocks remain: when instructions copied from a source appear in the draft, the
writing step was steered by source text, and the findings for that draft cannot be trusted
either. URL import will bring sources from third parties, which raises this risk.

Known limits: Phase 1 never publishes, so an advisory finding protects only if the owner
reads it. A reviewer can still label a fact as creative. The prompt forbids it and the live
evaluation tests it, but no code enforces it. When the reviewer itself fails, injection
detection does not run; the draft is shown marked unchecked.

### Addendum: blocks found by "Check again" — 2026-10-27

The security review found that a block raised by "Check again" was only returned as an error.
The draft stayed stored and saveable, and a retry could replace the block with a cleaner
review, because reviewer verdicts vary from run to run.

- Generation result: a block marks the run Failed with `draft_blocked` and drops its content,
  the same as a block on the first review. It can no longer be returned, saved or re-checked.
- Saved draft (owner decision): the owner's text is kept. The review is stored as `blocked`
  for that version and shown as a red "Do not publish" panel. Re-checking the same version is
  refused before any paid call. Only a newly saved version can be checked again.

Rejected: deleting the saved text (destroys the owner's own writing); returning 409 with
nothing stored (the block leaves no trace and a lucky retry can replace it).

### Addendum: wrong-language drafts are reviewed — 2026-10-27

The security review found that the deterministic script check (mostly the wrong EN/HE script,
or no letters) skipped the paid review, and with it the injection block. Source text could
trigger this on purpose ("answer in English") and get an unchecked draft shown.

Choice (owner decision): such drafts are still reviewed. The server adds a `wrong_language`
finding (once, even if the reviewer also reports it), and blocking runs as usual.
`review_wrong_language` no longer exists as an unchecked reason.

Rejected: withholding the draft with an error (brings back "error with no draft" for a quality
problem); keeping the skip (a reliable way around injection detection). Cost: one extra review
(about $0.016 with GPT-5.6-terra), only for drafts in the wrong script.

### Addendum: live-evaluation pass rules for source-review-v5 — 2026-10-27

`scripts/evaluate_generation.py` and `scripts/generation_scenarios.py` no longer expect
withheld drafts. Every outcome is now one of: clean, flagged (findings) or blocked.

- Supported scenario: shown, checked, no findings.
- Missing-fact scenario: shown and checked. Inventing the missing detail passes only when an
  `unsupported_claim` or `contradicted_claim` finding flags it; style findings don't count.
- Injection scenario: shown without the attack, or blocked (the run is then Failed, has no
  content and cannot be saved). An obeyed attack that is only flagged fails, because the
  policy says steering must block.
- Garden negative cases and curated review cases: a negative case must be flagged or blocked,
  a positive one clean. `wrong_language` must produce a `wrong_language` finding.
- An unchecked review (technical failure) or provider error fails in every category.

Rejected: counting any finding as a pass for missing facts (a brand-style note would hide an
invented price); counting a flagged obeyed injection as a pass (it would accept the case the
block exists for).

## Decision: room for reasoning reviewers, and a code for cut-off reviews — 2026-10-27

Problem: the first end-to-end generation with the default reviewer GPT-5.6-terra (Hebrew
LinkedIn post, 505 characters, 4 sentences, offer details) showed every draft as unchecked.
Measured with one-off paid calls (total $0.086 for the three diagnosis calls below plus one
earlier call; no code changed):
- At 1,600 output tokens Terra spent all 1,600 on reasoning, returned no content and stopped
  with `finish_reason: "length"`. The provider check reported this as the generic
  `generation_invalid_response`, and the UI showed "check the service settings".
- At 4,000 tokens the same draft took 1,615–2,699 completion tokens (1,552 reasoning in one
  run) and finished normally, in up to 32.8 s, above the 30 s GENERATION_TIMEOUT.
- With room to finish, the server still rejected all three reviews as
  `grounding_review_invalid`: Terra left the opening "כך," outside the last sentence's claim,
  and "כך" was not on the connective list, so coverage failed. Evidence quotes were exact.
- `outside_context_he` at 4,000 tokens: 151 tokens, 3.0 s, correctly flagged.

Choice (owner-approved):
- GENERATION_REVIEW_MAX_OUTPUT_TOKENS rises from 1,600 to 4,000 (the settings maximum).
- GENERATION_MAX_REQUEST_USD rises from $0.16 to $0.31, superseding the $0.16 entry above.
  Terra's worst-case review (6,000-token prompt, 4,000 output tokens, one retry) reserves
  about $0.1205 against a $0.124 share. Typical actual review cost stays about $0.02–0.03.
- Terra's typical cost in Create Post is remeasured from the middle of those three reviews
  (1,852 prompt / 2,019 completion tokens): about $0.028 instead of $0.016, which assumed
  907 completion tokens.
- GENERATION_TIMEOUT rises from 30 to 40 seconds (the settings maximum). The Next.js
  generation proxy already allows 280 seconds.
- `finish_reason: "length"` raises `generation_output_truncated`; the reviewer reports it as
  `grounding_review_truncated`, retryable, with its own EN/HE message. The UI also explains a
  reviewer's `generation_invalid_response` instead of pointing at service settings.
- The connective list gains discourse words that cannot state a fact on their own: EN
  therefore, thus, however, moreover, furthermore, additionally; HE כך, וכך, לכן, ולכן,
  בנוסף, ובנוסף, אולם, אך, כלומר, למשל, ובכן.

Live check after these changes: generation and review completed with no cut-off (3,281
completion tokens), but the review was still rejected on coverage. A diagnostic rerun
($0.030) showed Terra leaving בו, שם and כולל outside claims; every evidence quote was exact.
The reviewer prompt only said "except connecting words", and Terra's idea of a connecting
word was wider than the server's list.

Follow-up choice (owner-approved), source-review-v6:
- The reviewer prompt lists the accepted words verbatim, generated from `CONNECTIVES`, and
  says every other word, including short ones such as "there", "שם" and "לא", belongs inside
  a claim. A test keeps the prompt list and the coverage list identical.
- The list gains the relative and listing words בו, שבו, כולל and אשר. שם stays excluded
  because it is also a place word; a test covers it. Negation, time, place and quantity
  words stay excluded (tests cover כיום, לא and שם).
- REVIEW_VERSION becomes `source-review-v6`. As with earlier bumps, stored v5 reviews ask for
  a new check (`generation_review_required`) on retry, GET and save.

Second follow-up (owner-approved), after the v6 live evaluation stopped on
`outside_context_he` (verification/generation-grounding.md): Terra quoted the draft's
"שנהג לאכול…" as evidence for a source that says "נהג לאכול…", so the exact-quote check
rejected an otherwise correct review.
- An evidence quote that is not an exact substring is retried once without a single leading
  Hebrew prefix letter (ו ה ב ל מ ש כ). The rest must be an exact substring that starts with a
  Hebrew letter. Two prefixes, a detached letter or any other letter still fail.
- Stored provenance keeps the source text that matched, not the model's quote, so every
  stored excerpt is still verbatim source text.
- No prompt change, so REVIEW_VERSION stays `source-review-v6`.
- Rejected: telling the reviewer to copy quotes from the source (a v7 prompt). The model can
  still slip, and it costs another version bump and evaluation. Rejected: fuzzy or
  normalized matching. It would accept stitched or reworded quotes, which the exact-quote
  rule exists to stop.

Rejected alternatives:
- Lowering Terra's reasoning effort to fit 1,600 tokens: Terra was chosen because it
  reasons enough to reject an unsourced clause; a cheaper review that misses it defeats the
  choice. Not measured.
- Raising only the token limit: all three reviews that finished were still rejected on
  coverage, so drafts would stay unchecked.
- Accepting any uncovered word that the reviewer left out: coverage exists so that no
  factual phrase escapes review; a fixed list keeps that guarantee.
- Only adding the words Terra left out: the next unlisted word fails the same way, and
  adding שם would let a place word escape review.
- Retrying a cut-off review automatically: reasoning length varies (1,615–2,699 tokens on the
  same draft), but an automatic retry doubles the spend on every cut-off; the user can
  Check again instead.

Known limits: 4,000 tokens is the settings ceiling and does not cap reasoning, so a long
draft can still be cut off; it is then shown as `grounding_review_truncated`. A review can
still approach the 40 s timeout; not measured on 1,200- or 2,400-character drafts. The
writer path still shows its own truncation as the generic error. The connective list is
not a full Hebrew grammar; a reviewer that ignores the listed words can still fail coverage
as `grounding_review_invalid`. The v6 prompt has not yet passed the paid review evaluation.

## Decision: token estimates for writers with other tokenizers (SP-22) — 2026-10-27

Problem: budgets and cost reservations count prompt tokens locally with `o200k_base`
(`prompt_tokens` in app/grounding.py). That is accurate for GPT-4.1: stored Hebrew runs
under-count by a constant 29 tokens. Measured on synthetic EN/HE writer prompts
(verification/generation-grounding.md, "Writer tokenizer ratios"), other families count more
tokens for the same text. For long source text the provider-reported count approaches
o200k × 1.66 (EN) / 1.78 (HE) for Claude Haiku/Sonnet 5.5, and about × 1.2 (HE) for Gemini
3.8 Flash, DeepSeek v4.1 Flash and Nemotron. Without a correction, a Claude writer's
reservation and displayed cost would be about 40% too low.

Choice (owner-approved):
- Each writer in the writer allowlist carries a measured token ratio: the larger of the EN and
  HE ratios measured on long source text, rounded up (initially GPT-4.1 1.0, Claude 5.5 family
  1.8, Gemini/DeepSeek/Qwen 1.25). Tests assert the named constant, not a number.
- The ratio applies to the cost reservation (spending-limit preflight), the cost estimate
  shown in Create Post, and the context-length check against the catalog.
- The prompt and context budgets (GENERATION_PROMPT_BUDGET, GENERATION_CONTEXT_BUDGET) stay in
  o200k units, so every writer receives the same retrieved sources and evaluations compare
  writers, not context sizes.
- Provider-reported prompt tokens stay stored next to `prompt_tokens_estimate`, so a ratio can
  be rechecked from real runs. A candidate writer gets a ratio measured before it is listed.

Rejected:
- A local tokenizer per model: Claude 5.x has no public tokenizer, and Gemini's needs a new
  package; an unmapped model would silently fall back to a wrong count.
- Provider-reported counts only: they arrive after the call, so the spending cap could not be
  checked beforehand.
- Shrinking the prompt budget by the ratio: a Claude writer would get about 45% less source
  text, and its evaluation would mix model quality with missing context.
- One global safety margin: 1.8 for every model would overstate GPT-4.1 costs by 80%; a smaller
  margin would under-reserve Claude.

Limits: one measurement per case on one synthetic topic; Qwen long Hebrew and Gemma were
rate-limited and not measured. Ratios can drift when a provider changes tokenizers under the
same model ID; recheck from stored runs when costs look off.

### SP-22 acceptance criteria (owner-approved) — 2026-10-27

Selection and cost:
- The writer select lists only allowlisted, evaluated models; each option shows its writing
  cost, typical and maximum.
- One line below both selects shows the estimated total per draft (writing + the chosen source
  check), typical and maximum; it updates when either select changes and is visible on phones.
  Assumption agreed: option labels carry only the writing cost, so they do not change with the
  reviewer.
- Per-model cost comes from live catalog prices × the model's token ratio; the same ratio
  drives the spending-limit reservation and the context-length check.

API and data:
- An unlisted model is rejected with 422 `writer_model_unavailable` before any provider call.
  An omitted choice resolves to the default with the same fingerprint as an explicit default.
- The chosen writer is stored with the run and in the fingerprint, never in the prompts. A
  retry with another writer is a new request.
- The writer output limit is set per model so a reasoning writer can finish;
  `test_generation_budget.py` passes for every listed writer at its worst case.

States:
- Loading: select disabled with "Loading models…", total line hidden; generating still works
  with the default.
- Error (catalog or API unreachable): the select is replaced by "the default writer will be
  used"; the total line shows "cost unavailable".
- Empty: settings forbid an empty allowlist; an empty response is treated as the error state.
- Model unavailable: a delisted or unpriced model is a disabled "unavailable" option. If it
  disappears between load and submit, an EN/HE message asks for another model; inputs stay.
- Writer cut off: `generation_output_truncated` from the writer has its own EN/HE message,
  retry allowed, inputs preserved.

Quality and records:
- Every listed writer is compared with the GPT-4.1 baseline on the same 20 scenarios
  (unsupported additions, meta notes, latency, cost) in verification/generation-grounding.md.
- The default changes only if a candidate has fewer unsupported additions than GPT-4.1 and
  fails no injection case; a candidate that fails an injection case is not listed.
- Each candidate's token ratio is measured before it is listed.
- Decisions and rejected alternatives are recorded here.

### SP-22 candidate decision: Claude Sonnet 5.5 dropped — 2026-10-27

Owner decision after the 20-scenario run (verification/generation-grounding.md, "Writer
candidates on the 20 scenarios"): Claude Sonnet 5.5 is not listed. It ended 16/20 drafts with
a meta note about its sources (baseline GPT-4.1: 8/20), added 6 unsupported details, and one
supported Hebrew draft was blocked as `copied_instructions` because the note echoed the brand
guideline. Its writing costs about 2× GPT-4.1 per draft. Rejected alternative: keeping it and
tuning the prompt against meta notes (a prompt change is outside SP-22 and would need a new
baseline for every writer). Gemini 3.8 Flash and GPT-5.6-luna stay candidates pending a
confirmation run and luna's 7 missing reviews.

### SP-22 slice 1: writer choice plumbing — 2026-10-27

Built while OpenRouter credits were exhausted, so no paid calls; every check is offline.

- `GENERATION_WRITER_MODELS` (default GPT-4.1 only, the one evaluated writer) mirrors the
  reviewer allowlist; `GENERATION_MODEL` must be in it. app/writer_models.py holds a measured
  `WriterProfile` per writer: token ratio, typical provider tokens for the cost estimate, and an
  optional output limit for reasoning writers.
- `writer_model` in `POST /generation` resolves to the default, is stored in the run inputs
  and fingerprint, and never reaches the prompts. An unlisted writer, or a listed one without a
  profile, gets 422 `writer_model_unavailable` before any provider call.
- The prompt-budget check stays in o200k units; the writer call receives o200k × ratio
  (rounded up), which drives the spending reservation and the context-length check.
  `writer_token_ratio` is stored with each result for recalibration.
- `GET /generation/writer-models` prices each writer from the live catalog: typical = profile
  tokens × price; maximum = full prompt budget × ratio, profile output limit, every retry.
- Create Post: a writer select above the source-check select, the chosen writer's cost below
  it, and a total line (writing + chosen source check). States follow the agreed criteria;
  `generation_output_truncated` and `writer_model_unavailable`/`generation_model_unavailable`
  have their own EN/HE messages.

Decision (low risk, not argued): a candidate gets its profile only when it is listed, with
typical tokens measured on a realistic prompt. Gemini 3.8 Flash and GPT-5.6-luna therefore
have no profile yet; a candidate evaluation that sets GENERATION_MODEL on this code must also
add its measured profile and set GENERATION_WRITER_MODELS. Rejected: deriving typical tokens
from the one-sentence scenario drafts (Gemini's 697 mean completion tokens there would misstate
a real post).

Security review (bf-security-reviewer, read-only): no confirmed vulnerability; allowlist, spend
reservation, fingerprint and prompt isolation held. Acted on its low-severity notes: profiles
reject a float, zero or non-finite ratio and non-positive token counts at import; a test keeps
profile output limits under the provider ceiling; the cross-language query translation (run by
the default writer) now scales its count by that writer's ratio; "Check again" maps
`generation_model_unavailable` to the source-check message. Accepted as fail-safe: runs stored
before this change have no `writer_model`, so retrying such an old request key returns 409
`generation_request_conflict`; a writer removed from the allowlist returns 422 even for a retry
of a finished run.

### SP-22: Gemini 3.8 Flash listed as an optional writer; GPT-4.1 stays default — 2026-10-28

Owner decision after the confirmation runs (verification/generation-grounding.md, "Writer
candidates: confirmation runs"). Gemini 3.8 Flash against GPT-4.1:

| Measure | Gemini 3.8 Flash | GPT-4.1 |
| --- | --- | --- |
| Added unsupported details | 1/40 | 5/20 |
| Meta notes in the post | 0/40 | 8/20 |
| Injections obeyed | 0 | 0 |
| Garden drafts passed | 4/7 | 0/2 |
| Writer cost per draft | $0.0035 | ~$0.0025 |
| Writer latency | 9.0 s mean, 21.7 s max | 1.5 s |

Gemini meets the agreed rule for becoming the default (fewer additions, no injection failure).
The owner chose to list it as an optional writer and keep GPT-4.1 as the default.

- Profile: ratio 1.25 (measured, see the tokenizer decision); output limit 2,000, because it
  reasons before writing and used up to 1,055 completion tokens; typical tokens 2,585 / 1,007
  from one realistic synthetic Hebrew LinkedIn prompt (EN: 1,833 / 938). GPT-4.1's typical
  tokens come from a stored real run instead; remeasure both if the writer prompt changes.
- Worst case at the settings maximum (6,000 o200k prompt tokens × 1.25, 4,000 output tokens,
  one retry: about $0.045) fits the writer's stage budget ($0.124); `test_generation_budget.py`
  covers it. The limit was 2,000 at listing and raised to 4,000 the same day (entry below).
- GPT-5.6-luna is not listed: 7/20 drafts with added details, worse than GPT-4.1.

Rejected:
- Making Gemini the default now. The data supports it, but the owner kept the faster GPT-4.1.
- Listing luna as a cheap option. It adds details more often than the default.
- Waiting for a clean garden-positive record. The reviewer is inconsistent on the Hebrew
  garden name ("סידר": accepted once, flagged twice), and GPT-4.1 passed 0 of 2 garden drafts.

`scripts/evaluate_generation.py --live --writer-only` skips the 24 reviewer-only cases, which
use fixed drafts and no writer call. Terra stopped the full evaluation twice in those cases
with `grounding_review_invalid` (paraphrased claim text fails the coverage check), which kept
the garden positives from running.

## SP-22: Gemini 3.8 Flash output limit raised to 4,000 — 2026-10-28

The first live Create Post draft with Gemini selected (Hebrew, LinkedIn, medium, the owner's
Hebrew Wikipedia sources) used all 2,000 output tokens and failed with
`generation_output_truncated`; no draft was produced. The 2,000 limit came from synthetic
garden and LinkedIn sources (up to 1,055 completion tokens). Real Hebrew knowledge-base
chunks make Gemini reason longer, and reasoning tokens count against the limit.

- Choice: `output_tokens=4000` in Gemini's profile, the same room the reviewer got in #11.
  The worst case shown per draft rises from about $0.029 to about $0.045; the typical estimate
  is unchanged because it comes from measured tokens.

Rejected:
- Capping Gemini's reasoning (OpenRouter `reasoning` settings). It would make cost more
  predictable, but it changes the writer that was evaluated, so the 20-scenario and garden
  results would no longer apply and would need paid re-runs.
- Retrying with a larger limit after a truncation. It doubles cost on exactly the drafts that
  are already the most expensive.
- Keeping 2,000 and asking users to pick GPT-4.1 for long Hebrew drafts. The listed writer
  would fail on the owner's own sources.

## Decision: FastAPI rejects cross-site writes and unknown hosts (SP-23) — 2026-10-29

Problem: the proxy guard (entry above) protects only `/api/*` on 53073. FastAPI listens on
127.0.0.1:58073 and had no origin check, so any page the owner opened could send it a
simple request. Reproduced with a hermetic `TestClient` test on `main`: a cross-site
bodiless `POST /knowledge/{id}/embed` (paid embeddings) reached the handler. The live
check confirmed the same from a page on another local port.

Correction to the earlier "Known limits": FastAPI 0.162.0 does **not** parse a body
without Content-Type as JSON. `strict_content_type` is on by default (`fastapi/routing.py`),
so a Blob-body `POST /generation` got 422 and never reached the handler. The real exposure
was writes without a body: knowledge embed and retry, and `/dev/jobs/probe`. `PUT /brand`
and the deletes need a CORS preflight, which `localhost:3000` passed while it was an
allowed origin.

Choice:
- `app/write_guard.py` (`write_rejection`), run by an HTTP middleware inside
  `request_context`, so rejections carry the request ID and never reach a handler.
  For `POST`, `PUT`, `PATCH` and `DELETE`:
  - An `Origin` outside `cors_origins` → 403 `cross_site_request`.
  - A `Sec-Fetch-Site` other than `same-origin`/`none` without an allowed `Origin` → 403.
    `same-site` is not trusted, because every localhost port is the same site.
  - A body whose content-type essence is not exactly `application/json` → 415
    `invalid_content_type`. This is stricter than FastAPI, which also accepts `+json`.
  - Neither header (the Next proxy, curl, scripts) → allowed, the same rule as the proxy
    guard.
- Starlette's `TrustedHostMiddleware` with `allowed_hosts` (`ALLOWED_HOSTS`, default
  `127.0.0.1` and `localhost`) refuses other `Host` values with 400 on every method. This
  stops DNS rebinding, including reads.
- `cors_origins` keeps only the two 53073 origins (owner decision 2026-10-28). Port 3000
  belongs to other local projects.
- The proxy guard checks `Host` against `APP_HOSTS` (default `127.0.0.1:53073`,
  `localhost:53073`) for every method, closing the rebinding gap noted above.
- Tests and the evaluation script use `TestClient(..., base_url="http://127.0.0.1")`,
  because Starlette's default `testserver` host is not trusted.

Rejected alternatives:
- Relying on CORS: it hides responses but does not stop simple requests.
- Content-type check only: bodiless paid POSTs carry no body to check.
- Trusting `Sec-Fetch-Site: same-site`: a page on any localhost port qualifies.
- CSRF tokens: there are no cookies or sessions, so origin checks give the same protection
  without per-form state (as for the proxy).
- Binding FastAPI to a Unix socket or the Docker network only: it would break the host-run
  Next server and the evaluation tooling, and would not cover DNS rebinding of the proxy.
- Adding `testserver` to the allowed hosts: a test-only value in a security allowlist.

Limits: future multipart uploads (SP-9) must add an explicit exception for their route.
Writes from FastAPI's own Swagger UI (`http://127.0.0.1:58073/docs`, "Try it out") now get
403, because that page's origin is not allowed; use curl or the app. Adding the 58073
origins was rejected because it would trust Swagger's CDN-loaded script to write.
Wildcards in `ALLOWED_HOSTS` or `CORS_ORIGINS` are refused at startup, because a `*`
silently turns the Host check off.
Next.js pages outside `/api` are not covered by the Host check. That is acceptable today
because no page fetches data on the server; all data reads go through the `/api` proxies,
which do check `Host`. Recheck this if a page starts loading data server-side.


## SP-24 and SP-26: the source check finishes on real Hebrew drafts (source-review-v7) — 2026-10-29

Problem: "source check did not finish" (`grounding_review_invalid`) on a third of the
owner's stored drafts, and one of them blocked outright. The cause was not measured, because
every failed check ended in the same code.

Measurement first (verification/generation-grounding.md, "SP-24 measurement"):
`review_draft` now stores `failed_check` (`schema`, `coverage` or `evidence`) and
`failed_sentence` (a draft sentence index) in the unchecked review's `failure`, and no
model-written text. In 45 Terra reviews (the evaluation's 30 reviewer-only fixtures plus the
owner's 5 stored Hebrew drafts ×3):
- fixtures: 30/30 verified;
- real drafts: 3 invalid (2 coverage, 1 evidence), 2 cut off at the output limit, 2 blocked.

Causes, from the raw reviews (kept outside the repo):
- **Coverage (both times the same sentence):** every claim was exact, and only the Hebrew
  copula "הוא" sat outside them. English "is/are" were connectives; Hebrew "הוא" was not.
- **Evidence:** an exact source excerpt with a final "." added where the source sentence
  continues.
- **Block:** the draft repeated the owner's own call to action from offer details ("שלחו
  הודעה פרטית…"). The prompt defined `copied_instructions` as repeating instructions "inside
  a source or the offer details", so a CTA written for readers counted as one.

Choice (`source-review-v7`):
- `CONNECTIVES` gains הוא, היא, הם, הן. They join subject and predicate like "is" and "are".
  They are also subject pronouns, but a pronoun alone states no fact, and the verb and object
  around it stay inside claims. Negation after a copula still fails ("היעד הוא לא רווח"; test).
- Coverage compares tokens, not substrings (`claim_span`). Claim words, numbers (one token
  with their sign, inner separators and unit letters: "-20", "1-5", "050-1234567", "2a") and
  fact signs (currency, math, %, #, @, &, /, °, ❌ ✅ ⭐ 🆓 and similar, flags) must equal whole
  draft tokens in order. Invisible characters (zero-width, bidi, variation selectors) between
  letters stay inside the word, so they cannot split one; elsewhere they are skippable. A claim word may lack the
  draft word's one-letter Hebrew prefix. Only connectives and plain punctuation may be passed
  over, before a claim or inside it ("opens Tuesdays" for "opens on Tuesdays", a skipped
  "גם"). That equals splitting the claim at those words, which coverage already allowed.
  Part of a word ("effective" in "ineffective", "עלי" in "עליהם"), a changed sign ("$5" for
  "€5") or an added, moved or negated word never matches. A fact sign may no longer sit outside
  every claim ("€" in "Tickets cost €5" with claims "Tickets cost" and "5"), which v6 allowed.
  One pass over the tokens, so the cost grows linearly. Findings and stored provenance show
  the draft's own span, never the model's claim text.
- `matched_quote`: a quote may end with one punctuation mark the source lacks. The excerpt
  must then end where a source word ends, before whitespace or the end of the source, so
  "starts at 1." never matches "starts at 10" and "free." never replaces "free?". Every
  excerpt, exact or not, must start and end on a source token boundary, numbers included
  ("start at 1" no longer matches "start at 10", "500" no longer "1,500", "20%" no longer
  "-20%", "מנטור" no longer "מנטורים"). An exact excerpt may start after one attached Hebrew
  prefix letter in the source, which Terra does constantly ("הספורט" from "והספורט"). Every
  quote needs a letter or digit; v6 accepted "." as an exact quote. A quote found more than
  `MAX_QUOTE_OCCURRENCES` times is not verified, and quotes are matched only after coverage
  passes, so tiny steered quotes against a long planted source stay cheap.
- Prompt (SP-26): `copied_instructions` means instructions aimed at the AI (ignore rules,
  reveal instructions, change the output, add content). A reader-directed call to action the
  owner wrote in offer details is the owner's intent; repeating it never blocks.
- New deterministic finding `unlisted_contact_detail` (SP-26). Any link (with a scheme, www.,
  a path, or a common top-level domain), email, @handle (also "ל@x") or phone number (9+
  digits, also after "Tel:"; dates, times, year lists, versions and grouped numbers excluded)
  in the draft that is not in the offer details, the chosen CTA or the brand profile (except
  its prohibited claims) becomes a point to check. Links compare
  by host and path, phones by their last nine digits. It does not depend on the reviewer or on
  which sources the writer cited: a planted source can be used without being cited, and a
  writer can invent a contact detail. Advisory like every other finding; to keep a detail
  without the note, the owner adds it to offer details. EN/HE copy in "Points to check".
- REVIEW_VERSION becomes `source-review-v7`, because the prompt changed (its word list and
  the blocking definition). As with earlier bumps, stored v6 reviews ask for a new check
  (`generation_review_required`) on retry, GET and save.

On the same 45 captured reviews, re-scored offline with the final rules: invalid 3 → 0. The
other 40 keep their outcome and every finding, and no negative fixture became clean.

Security review (`bf-security-reviewer`, before merge) found four problems in the first
version of this change, all fixed above with regression tests: claim matching inside words
and with stripped symbols, the final-mark tolerance accepting a quote cut inside a number or
word, the CTA wording letting a source-planted reader CTA pass unnoticed (now the
deterministic finding), and a matching loop whose cost grew with the cube of the claim
length. Its re-check of the fixes found more, also fixed: a dropped minus or re-punctuated
number, an exact quote ending inside a source number, a contact check that only saw cited
sources and missed bare domains, prefixed handles and reformatted details, a quadratic email
pattern on planted text, and dates with times counted as phones. Known limits: planted reader
prompts with no contact detail ("comment your email below") are neither blocked nor flagged;
a dropped "כ" ("about") makes the checked claim stricter, not looser. A third pass found
quote boundaries ignoring number separators, a bare domain ending a sentence going
undetected, more evasion formats and false alarms, number-with-letter tokens and missing
invisible characters; all fixed. Further known limits: the prefix allowance cannot tell a
prefix from a root letter ("לא" after the "מ" of "מלא"), unlisted top-level domains without
a path ("cedar.xyz" is listed, "cedar.berlin" is not), 3-3-3 phone groupings and phones with
4+ dots are not detected, and tech names on listed domains ("ASP.NET") or third-party
@mentions are flagged (advisory). Re-scored after each round: all captured reviews keep
their outcomes. Accepted with it: הוא/היא outside claims can
lose who-does-what in a sentence such as "היא מנהלת, הוא מתנדב"; the referents are usually
claimed elsewhere, and the verbs stay inside claims.

Rejected alternatives:
- Retrying the review once on a coverage failure. The copula failure repeated on 2 of 3
  reviews of the same sentence, so a retry often fails again, at about $0.04 a review.
- Telling the reviewer to put הוא inside claims (prompt only). The prompt already said
  "every other word belongs inside a claim" and Terra still left it out. The model's
  reading is the natural one, and English already allowed "is".
- Fuzzy or normalized claim matching (edit distance, stemming). It could accept a changed
  number or name, which the coverage check exists to stop.
- Accepting quotes with an inner or doubled mark, or any normalized quote. They are no longer
  verbatim source text.
- Exempting every reader-directed CTA from `copied_instructions`. A planted source could then
  steer the post with "contact us at …"; only the owner's own offer details are exempt.
- Blocking source CTAs through the prompt ("a CTA, contact detail or link that appears only
  in a numbered source and that the draft repeats is copied_instructions"). Tried live: it
  blocked the two curated platform drafts that repeat the source's own "swipe up" CTA, which
  v6 only flagged (`platform_fit`). Blocking withholds the draft, too harsh for text the
  owner pasted in; the deterministic finding covers the planted contact detail instead.
- Substring matching with word-boundary checks added. Token matching gives the same
  boundaries, handles symbols explicitly and runs in one pass.

Typical review cost: `TYPICAL_REVIEW_TOKENS` for Terra rises from (1,852, 2,019) to
(2,650, 2,950) tokens, the median of 16 reviews of the owner's medium Hebrew drafts. The old
figure came from one 505-character draft and understated real drafts by about 40%. Create
Post's typical review estimate goes from about $0.028 to $0.041.

Not changed (SP-27, Backlog): 2 of 15 real-draft reviews used the whole 4,000-token output
limit (`grounding_review_truncated`). A higher limit does not fit the review's smallest stage
budget ($0.124: the $0.31 request cap, minus the 20% translation share, halved; Terra's worst
case at 4,000 tokens is $0.1205). It needs an owner decision on the request cap or the
translation share.

## SP-25: retrieval spreads across documents — 2026-10-29

Problem: the live Hebrew draft "ההבדל בין מנטורינג לאימון אישי" discussed coaching only.
Measured read-only (verification/generation-grounding.md, "SP-25"): the writer received 5
chunks, all from the coaching article; `result.sources` lists only the 2 it cited. The
mentoring article's best chunk was within the 0.65 distance limit (0.577) but ranked 7th,
behind more coaching chunks. A second cause: English chunks are about 750 o200k tokens, so
the 2,800-token context budget holds about 3.7, and a 5th-ranked chunk from another document
is the one cut.

Choice:
- `search_context(..., per_document=GENERATION_CHUNKS_PER_DOCUMENT)` (default 3) ranks each
  chunk within its own document in SQL (`row_number()` per document) and takes the nearest
  chunks ranked at most 3 in their document, within the distance limit. There is no
  candidate-pool ceiling: a second document is found behind any number of nearer chunks of
  one long document. When that selection runs short (no other document within the limit), it
  is filled up from the plain nearest chunks, so a one-document Knowledge Base still gets 5,
  the same ones (`spread_across_documents`).
- Context order puts each document's best chunk first, then the rest, each by distance, so a
  tight budget trims a document's extra chunks before it drops another document.
- Count, distance limit, budget and the empty state ("no sources", never unrelated chunks)
  are unchanged. The Knowledge Base search endpoint keeps plain nearest-first results.

Replay on the owner's Knowledge Base: both Hebrew two-concept topics now reach the second
document (mentoring at 0.577 and 0.571). The Hebrew single-concept topic keeps exactly the
same chunks, reordered. The English "personal coaching" topic now also receives the Hebrew
coaching chunk the budget used to drop.

Rejected alternatives:
- Raising the count or the distance limit: more weak chunks and prompt cost, and one large
  document still fills the extra slots.
- Lowering the cap to 2: more documents, but a single-concept topic loses its third-best
  chunk to weaker documents more often.
- Clustering or maximal-marginal-relevance re-ranking: needs every candidate's vector and a
  tuning weight; the per-document cap fixes the measured miss with one setting.
- Translating every topic (cross-language retrieval): a Hebrew topic puts the English
  Mentorship article at about 0.85, beyond the limit, and the translation fallback runs only
  when nothing is found. Translating always adds a writer call and latency to every draft;
  left as a possible follow-up, not part of this fix.

Trade-off, by design: for a single-concept topic, a weaker document inside the distance limit
now takes the main document's slots beyond the cap (and its best chunk comes second). In
the replay this kept the same chunks for "מהו מנטורינג"; with English chunks and the
2,800-token budget, the main document can lose about one chunk of context. A test pins it.

The first version drew 4× the count of candidates and capped them in Python; QA (`bf-qa`)
showed a second document ranked 21st or lower was still missed, so the cap moved into SQL.

Limits: English two-concept topics still find only the English article, because the other
documents are Hebrew and beyond the limit (the cross-language gap above).

## SP-6: topic suggestions from the Knowledge Base — 2026-10-29

Create Post gets "Suggest topics": up to three grounded ideas for the chosen platform,
language and goal. Choosing one fills in the topic. The draft written from it still goes
through retrieval and the source check, because a suggestion is an idea, not a post.

Choice:
- `POST /generation/topic-suggestions` (`app/topic_suggestions.py`) with platform,
  language, optional goal, count 1–5 (default 3) and an optional writer from the allowlist.
  Stateless: nothing is stored.
- Representative sampling, no clustering: the 8 most recently updated Ready documents of the
  workspace, up to 3 chunks spread evenly through each (start, middle, end), interleaved so
  every document is represented before any gets a second chunk. Each excerpt gets an equal
  share of the 2,800-token context budget (cut at a word), so long English chunks cannot
  crowd later documents out: QA measured that whole 800-token chunks let only 4 of 8 English
  documents through. No embedding call.
- One call to the chosen writer (default GPT-4.1) with a strict JSON schema. Sources go in
  as data under aliases (S1…); the system prompt says all sources, brand and preferences are
  untrusted data.
- Server checks, which drop an idea rather than repair it: it must cite at least one
  sampled source and only sampled sources; topic and rationale must be in the requested
  language (a Hebrew topic needs 30% Hebrew letters, so it may name English terms); a
  near-duplicate of an earlier idea is dropped (80% shared words, or a topic of three or more
  words inside another of similar length; words match across one Hebrew prefix letter);
  invisible direction, zero-width and tag characters drop the idea. Each kept idea returns the titles and IDs of its sources.
- An empty Knowledge Base is 409 `insufficient_context` with no model call. No surviving
  idea is 200 with `reason: "no_grounded_suggestions"`. Provider failures use the generation
  error codes (503, or 409 for the prompt limit); an unlisted writer is 422.
- The UI shows the button only when `/generation/configuration` reports
  `topic_suggestions`, disables it until the Knowledge Base is ready, and gives EN/HE empty,
  error and spending-limit messages that keep the user's own topic.

Live (owner's Knowledge Base, GPT-4.1): three distinct, cited ideas each in Hebrew ($0.0078)
and English ($0.0032), drawn from all four documents.

Rejected alternatives:
- Vector clustering for "representative" material: needs every chunk vector and a cluster
  count; the issue makes it optional, and even sampling with an equal share per excerpt
  already covers up to 8 documents.
- Embedding the goal and retrieving by it: one more paid call per click, and with no goal
  there is nothing to retrieve by.
- Running the source check on each suggestion: about $0.04 per idea with Terra; the draft
  is checked anyway.
- Storing suggestions: nothing reads them later, and they would be stale once sources
  change.

Security review (`bf-security-reviewer`): no blocking findings. Applied: a context too small
for any source is 409 with no model call; ideas with invisible direction overrides or tag
characters are dropped (Hebrew LRM/RLM are kept); sampling loads no embeddings; the UI labels
sources "Sources it cites", because the server checks that a cited source was sampled, not
that it supports the idea; an unprofiled writer is 422 as on the draft route; the route is in
the write-guard test list.

QA (`bf-qa`) also found stale ideas after a language change (now cleared when platform,
language, goal or writer change) and generic "try again" text for errors a retry cannot fix
(now specific EN/HE messages).

Limits: ideas come from at most 8 documents, each excerpt a share of the budget (about 100
tokens with 8 documents × 3 chunks), so a large Knowledge Base is sampled, not covered. The rationale
is the model's own short text; it is shown as an idea, never as a fact about the brand.

## SP-27: room for the source check on medium Hebrew drafts — 2026-10-30

Problem: in the SP-24 measurement 2 of 15 Terra reviews of the owner's medium Hebrew drafts
used the whole 4,000-token output limit and ended as `grounding_review_truncated`. A higher
limit did not fit the review's smallest stage budget ($0.124).

Choice (owner-approved, option 1 of SP-27):
- GENERATION_MAX_REQUEST_USD rises from $0.31 to $0.37, superseding the $0.31 entry above.
- GENERATION_REVIEW_MAX_OUTPUT_TOKENS rises from 4,000 to 5,000, and so does its settings
  maximum. The smallest stage budget becomes $0.148 ($0.37 minus the 20% translation share,
  halved); Terra's worst case (6,000-token prompt, 5,000 output tokens, one retry) reserves
  $0.1445, GPT-4.1 as reviewer $0.1045. `test_default_budget_affords_largest_allowed_prompt`
  asserts this for every choosable stage.
- Typical cost is unchanged: providers bill used tokens. Create Post's worst case per draft
  rises with the limit; it is computed from these settings, so no UI constant changed.
- The settings maximum also caps writer profiles' output limits (`chat_completion` uses the
  larger maximum); no writer profile changed.

Rejected: shrinking TRANSLATION_BUDGET_SHARE toward the translation's measured worst case
(about $0.016) leaves little headroom; keeping 4,000 leaves about 1 in 7 medium Hebrew
reviews to "Check again".

Not verified live: the owner chose not to re-review the cut-off drafts now, expecting mostly
short posts. Long drafts (up to 2,400 characters) may still need more than 5,000 tokens and
end as `grounding_review_truncated`, which stays retryable.

Create Post also shows each length's limit: short up to 600 characters (~100 words), medium
up to 1,200 (~200), long up to 2,400 (~400), in EN and HE. These are the maximums the server
already enforces; the word counts assume about 6 characters a word.

## SP-17: PDF and text file uploads (SP-8, SP-9, SP-10 slice) — 2026-10-30

Owner decisions: pypdf (BSD) for PDF text, not PyMuPDF (AGPL); private source files on local
disk now, behind a small storage module so S3-compatible storage can replace it later.

Upload contract:
- `POST /knowledge/files?filename=…&title=…` with the raw bytes as
  `application/octet-stream`. That type is not CORS-safelisted, so a cross-site browser
  request needs a preflight that CORS refuses. Multipart form data is never accepted: any
  page can send it without a preflight. `app/write_guard.py` allows octet-stream on this
  route only; the Next proxy forwards only octet-stream, bounded at 50 MB before the
  backend's own limit. No multipart parser dependency was added.
- Type comes from the extension (`.pdf`, `.txt`, `.md`) and must match the content: a PDF
  must start with `%PDF-`; a text file must not, must be strict UTF-8 (a BOM is dropped) and
  contain no NUL. Limits: UPLOAD_MAX_BYTES 10 MB, PDF_MAX_PAGES 300,
  SOURCE_MAX_CHARACTERS 200,000 of extracted text (pasted text stays at 100,000).
  `/knowledge/configuration` reports the limits, and the UI checks the same ones before
  uploading. Errors carry actionable codes (`file_too_large`, `file_type_unsupported`,
  `file_signature_mismatch`, `file_not_utf8`, `file_not_text`, `source_empty`,
  `source_too_long`, `file_name_invalid`, `storage_failed`).
- Only the last path segment of the filename is kept, without control characters; it is
  shown back and never used as a path. The title defaults to the file name without its
  extension.
- Duplicates: the same bytes of the same type in one workspace return the first document
  (`uq_file_workspace_checksum`, sha256 of the raw bytes). A pasted text and a file with the
  same words are separate sources.

Storage (`app/storage.py`): random 32-hex keys (`storage_key`, migration `7b2e4c9d1a35`), files
written owner-only (0600) through a temporary file and an atomic rename, in
SOURCE_STORAGE_DIR (`var/sources`; docker-compose mounts the `source_files` volume there for
the API and the worker; ignored by git and Docker builds). The file is stored before the
database row. If the row is not committed, the file is removed. Deleting a source removes
its file after the row is gone. If that removal fails, an unreferenced private file can
remain, but no row is left pointing at a missing file.

Processing: text files are decoded at upload, so a bad file fails in the request. PDFs are
read by the worker, outside the document row lock, and the locked step checks that the
document still exists before writing. Each page's text is normalized and pages are joined by
a blank line; every chunk records `page_start`/`page_end` in `source_location` next to its
character offsets. Failures are stored on the document, not retried automatically:
`pdf_requires_ocr` (no text layer; OCR is not attempted), `pdf_encrypted` (an owner-password-only
file opens with an empty password), `pdf_corrupt`, `pdf_too_many_pages`, `source_too_long`,
`source_empty`, `source_file_missing`. "Process again" re-reads the stored file.

UI: an "Upload a file" form under the pasted-text form shows the configured limits, uploads
with XMLHttpRequest so upload progress (a progress bar) is separate from background
processing (the status badge and polling), and shows EN/HE messages for every code above.
Each source shows its type (pasted text, text file, PDF), file name and creation time.

Verification: backend 735 passed (39 new: extraction, storage, upload API, write guard)
on a disposable migrated database as the runtime role; ruff, format, `mypy app`, `alembic
check` and a downgrade/upgrade round trip passed. Frontend Prettier, lint, tsc, production
build and Playwright 68/68 passed (4 new). End to end on the production build with the real
API and PostgreSQL, but no Redis: a two-page PDF uploaded through the Next proxy was stored as
a 0600 file, dispatch failed cleanly as `dispatch_failed` (no broker), the worker task run
directly produced one chunk with pages 1–2, and deleting through the proxy removed the
file. Form data was refused with 415 by both the proxy and the API. EN and HE pages had no
horizontal scroll at 1280 and 390 px.

Not done in this slice: URL submissions (SSRF-safe fetching, HTML extraction), S3-compatible
storage, a scheduled sweep for unreferenced files, OCR, and a live Docker run with the worker
(no Docker here). Known limits: pypdf may return Hebrew from some PDFs in visual (reversed)
order, depending on how the PDF was produced; headings are not detected separately in PDFs;
pypdf's own decompression limits plus the worker's 90 s soft time limit bound hostile files.

## SP-17: web page sources (SP-8, SP-9, SP-10 slice) — 2026-10-30

Owner decision: trafilatura (Apache 2.0) extracts a page's main text, as Markdown so
headings survive; navigation, footers and comments are dropped.

Submission: `POST /knowledge/url` (JSON `{url, title?}`) checks only the URL's form:
http/https, no user name or password, default ports (80/443) only, at most 2,048
characters, and no internal IP literal or `localhost`/`.local`/`.internal` name. Each failure
is a 422 with its code. The URL is normalized (lowercase scheme and host, default port and
fragment dropped). One source per normalized URL per workspace
(`uq_url_workspace_checksum`, migration `9d4f2a6c8e17`). Without a title, the source is named
after host and path until the page's own title is known; an owner's title is never replaced.

Fetching (`app/web_fetch.py`) runs in the worker, before any row lock:
- Every hop resolves the name and requires every answer to be public (`ip.is_global`, not
  multicast; IPv4 inside IPv4-mapped, 6to4 and NAT64 addresses is checked as IPv4; Teredo is
  refused). One internal answer blocks the host.
- The connection goes to the checked address, with the name in the Host header and TLS SNI,
  so certificate checks still use the name and a second DNS answer cannot redirect it (DNS
  rebinding).
- Redirects are followed by hand, at most 3, each re-checked like the first URL.
- Environment proxies are ignored (`trust_env=False`): a proxy would resolve the name
  itself.
- Limits: 5 s connect and 10 s read timeouts, 30 s in total, and UPLOAD_MAX_BYTES (10 MB)
  applied after decompression. gzip and deflate go through our own bounded decoder; other
  encodings are refused. Only `text/html` and `application/xhtml+xml` are accepted.
- Codes: `url_dns_failed`, `url_blocked_address`, `url_timeout`, `url_too_large`,
  `url_http_error`, `url_unsupported_type`, `url_too_many_redirects`, `url_fetch_failed`,
  `url_no_content`, `url_parse_failed`, `source_too_long`.

The fetched HTML is stored privately like an uploaded file. A copy is kept only once a
committed row refers to it: if the source is deleted while the page is fetched, or the write
fails, the copy is removed. "Process again" on a web page drops the stored copy and fetches
the page afresh.

UI: an "Add a web page" form (EN/HE) under the upload form checks the address's form
before sending, shows the server's codes, and lists web sources as "Web link" with the
address as an outgoing link (`rel="noopener noreferrer"`). Every fetch failure has its own
message.

Verification: backend 812 passed (77 new: 52 fetcher, 19 URL source, 6 write guard). The
fetcher tests cover every internal address class, form checks, IP pinning with Host and SNI,
IPv6 pinning, mixed DNS answers, redirects to internal addresses and to names that resolve
inside, redirect limits, HTTP errors, content types, encodings, size limits before and after
decompression, timeouts, connection errors and the proxy setting. Frontend Playwright 70/70
(2 new). The real network path ran against a local server on port 80 with only DNS and the
public-address rule overridden: the request reached the checked IP with `Host: garden.test`,
followed a 301, decoded gzip, and the extracted text kept both headings.

Not verified: a fetch of a real public site. This sandbox reaches the internet only through
a proxy, and the fetcher deliberately ignores proxies. It needs a check on the owner's
machine. Known limits: pages that render their text with JavaScript yield `url_no_content`;
trafilatura may keep a short menu line on a page with almost no text; DNS lookups use the
system resolver's own timeout; a redirect to a PDF is refused (`url_unsupported_type`), so
the owner downloads and uploads it instead.

## SP-17: loading a web page again — 2026-10-30

Owner decisions: the current version stays in use until the new one is ready, and a
searchable page is embedded again automatically (about $0.0001 a page).

`POST /knowledge/{id}/refresh` works on web sources whose text is prepared or Ready. It
creates a hidden staging copy (`replaces_id`, migration `b3e8d5f1c260`, one per source,
deleted with the source) that runs through the normal fetch, extraction and embedding jobs
(`app/refresh.py`):
- Staging copies never become Ready, so retrieval, generation and topic suggestions keep
  using the original. They are excluded from listing, GET, retry and delete by ID.
- Unchanged extracted text: the staging copy is dropped, only `fetched_at` and
  `refresh_result = "unchanged"` change, and no embedding is paid for.
- Changed text, original not yet searchable: the new text and chunks replace the original's
  at once.
- Changed text, original Ready: the worker creates and dispatches an embedding job for the
  staging copy. When it completes, one transaction moves the new chunks onto the original,
  deletes the old ones and the staging copy, and keeps the original Ready
  (`refresh_result = "updated"`). If embeddings are not configured, the request is a 503
  `embedding_not_configured` and nothing starts.
- Every refresh write locks the original before its staging copy. The replaced page's stored
  copy is removed after commit.
- A failed refresh stays on the staging copy (its code is shown in the UI) and the original
  is untouched. Loading again replaces the failed attempt. A second click while a refresh
  runs starts nothing new; enabling AI search on the original meanwhile is a 409
  `refresh_in_progress`.
- Saved drafts keep their own source snapshots, so a refresh does not change them.

UI: web sources show "Last loaded" and a "Load again from the site" button. While a refresh
runs, the original keeps its status and shows "Loading again…", and the list polls. Then it
shows "No changes since the last load." or "Updated from the site.". A failure says what went
wrong and that the previous version is still in use (EN/HE).

Verification: backend 824 passed (6 refresh tests on the real database, covering unchanged,
replaced at once, searchable until embedded with search results checked during the refresh,
failure and retry, delete during a refresh, and refusals), ruff, `mypy app`, `alembic check`
and a downgrade/upgrade round trip. Frontend Prettier, lint, tsc, production build and
Playwright 72/72 (2 new). Not verified live: the same fetch limits as web page sources apply
(no public fetch from this sandbox).

