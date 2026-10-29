# AI search setup

The embedding integration has passed live OpenRouter verification: provider connectivity, a temporary source becoming Ready, idempotent embedding requests, and semantic query retrieval. The temporary source was removed afterward. Post generation and separate source review are now available; the backend suite has 82 passing tests, including provider response validation and grounding failure handling.

## Connect OpenRouter

1. Open backend/.env (Git-ignored) and set EMBEDDING_API_KEY to your OpenRouter API key. Keep credentials out of frontend variables and source control.
2. Keep the initial configuration, or change it to a supported embedding model:

```dotenv
EMBEDDING_BASE_URL=https://openrouter.ai/api/v1
EMBEDDING_MODEL=openai/text-embedding-3-small
EMBEDDING_DIMENSIONS=1536
EMBEDDING_REVISION=1
EMBEDDING_BATCH_SIZE=16
EMBEDDING_TIMEOUT=20
```

The default request shape follows [OpenRouter embedding documentation](https://openrouter.ai/docs/api/api-reference/embeddings/create-embeddings). Availability, permissions, and credits still require a real account check. Other compatible endpoints can be configured with a base URL/model/dimensions; they must return the requested model identifier, indexed float vectors, and the configured dimensions. For the official OpenRouter endpoint, the verified upstream OpenAI identifier without the openai/ prefix is also accepted; unrelated models and aliases from other endpoints remain rejected.

3. Recreate API and worker to load the new environment, then run the small live smoke test:

```sh
docker compose up -d --force-recreate api worker
docker compose exec api python -m app.embedding_smoke
```

The smoke test makes one small paid provider request and prints only a success summary. It does not store vectors or reveal credentials. No paid request is made just by starting services or viewing the Knowledge Base.

4. Refresh the Knowledge Base and use Enable AI search on a prepared source. Sources become Ready only after all chunks have compatible vectors. Failed batches can be retried from the same button; completed batches are reused. Existing prepared documents are not automatically sent to the provider.

## Processing and recovery

POST /knowledge/{id}/embed creates/reuses one durable embedding job for the document. Redis receives only its ID. Provider calls occur outside database transactions and row locks. A session advisory lock prevents two workers embedding the same job simultaneously. Completed batches commit independently, so partial failures resume without repeating completed chunks. A timeout after the provider accepted a request may still incur repeated charges on retry; provider billing is not exactly-once.

Requests contain at most EMBEDDING_BATCH_SIZE chunks (1–16) and a bounded timeout. Network failures, rate limits, and server failures use bounded exponential retry backoff. Authentication/payment/invalid-response failures require an explicit retry after fixing the cause. Empty, malformed, incorrectly indexed, nonfinite, zero, mismatched-model, and wrong-dimension vectors are rejected. No response bodies, source text, or secrets are stored in error messages.

Embedding tasks have a 240-second soft limit and 270-second hard limit; worker graceful shutdown and Redis visibility timeouts cover this window. A dedicated Celery beat scheduler runs reconciliation every minute. It requeues Pending ingestion/embedding jobs older than two minutes and abandoned Processing jobs older than ten minutes. Active embedding jobs are protected by their advisory lock, and previously stored batches are retained. You can also run `docker compose exec api python -m app.reconcile` or explicitly use Enable AI search again after a worker recovers. Failed jobs require explicit retry.

## Retrieval

POST /knowledge/search accepts query (1–5,000 characters, at most 2,000 tokens) and limit (1–10, default 5). Query vectors use the same client/model/dimensions/profile as document vectors. Results include matched chunk text and source location. Only Ready documents with the current profile, model, dimensions, user, and workspace are queried. The initial implementation uses exact cosine-distance ordering and a profile index; an approximate vector index is deferred until live validation and volume measurements.

## Model changes and re-embedding

The profile hash includes endpoint, model, dimensions, and EMBEDDING_REVISION. Change the revision when an upstream model changes under the same identifier. Recreate API/worker after changes. Existing vectors remain stored, but queries immediately exclude profiles that do not match the current configuration. The UI presents old Ready sources as text-prepared for re-embedding. Enable AI search on each source to move it to Processing and regenerate incompatible chunks. Old and new vectors are never mixed in search results.

The source tokenizer is cl100k_base. Before selecting another model, verify tokenizer compatibility, input limits, and dimension behavior; re-chunk sources if required. No fixed-dimension schema migration is needed because vector metadata and profile filtering enforce compatibility. Migration 00df4e86db62 adds profile columns and the unique embedding-job index.

SP-7 live verification is complete for the configured OpenRouter model. Repeat the provider smoke test and a source/query check after changing providers or models.

## Generation and source review

GENERATION_MODEL, the default writer, is `openai/gpt-4.1`. Users may pick any writer in GENERATION_WRITER_MODELS (default: GPT-4.1 and Gemini 3.8 Flash) per draft in Create Post; `GET /generation/writer-models` returns each writer's typical and maximum writing cost, and Create Post shows the total with the chosen source check. Every listed writer needs a measured profile in `app/writer_models.py` (token ratio, typical tokens, optional output limit); a listed writer without one is shown as unavailable, and the API rejects it, like any unlisted writer, with `writer_model_unavailable` before any provider call. Only writers that passed the writer evaluation are listed (docs/implementation.md, SP-22). GENERATION_REVIEW_MODEL, the default source-check model, is `openai/gpt-5.6-terra`. Users may pick any model in GENERATION_REVIEW_MODELS (default: GPT-5.6-terra and GPT-4.1) per draft in Create Post. `GET /generation/review-models` returns each option's typical and maximum source-check cost, priced from the live catalog. The API rejects a model outside the allowlist with `review_model_unavailable` before any provider call. GPT-4o was live-tested but added unsupported descriptions even with restrictive prompts, so the default writer changed after evaluation. Both models remain configurable and are checked against the provider catalog before use. GENERATION_TOKENIZER defaults to `o200k_base`, compatible with GPT-4.1/GPT-4o. Prompt and context budgets are counted with it for every writer, so each writer receives the same sources; a writer with another tokenizer multiplies the count by its measured token ratio for the cost reservation, the cost estimate and the context-length check. Embedding chunks continue using cl100k_base. Docker preloads both encodings.

The writer and reviewer each receive half of GENERATION_MAX_REQUEST_USD (default $0.31), including their permitted retries. The writer may produce up to GENERATION_MAX_OUTPUT_TOKENS (900) unless its profile sets a larger limit for reasoning; the reviewer has its own GENERATION_REVIEW_MAX_OUTPUT_TOKENS (4000) because claim-level reviews repeat each claim and its quotes, and a reasoning reviewer such as GPT-5.6-terra spends part of the limit on reasoning tokens. A response cut off by the limit fails as `generation_output_truncated` (a review shows it as `grounding_review_truncated`, which can be checked again) instead of a generic invalid response. GENERATION_TIMEOUT defaults to 40 seconds per provider call. The default is sized so the largest prompt the prompt budget admits still passes this check; lowering it, raising GENERATION_RETRIES or switching to a pricier model can make full-context requests fail with `generation_spending_limit` (see docs/implementation.md). Unused allowance is not transferred. This is a conservative preflight estimate for completion calls, not a provider billing cap; query embedding is separate. Usage and cost for each stage and the combined reported completion cost are stored. Missing provider cost remains unknown, not zero. Generation prompts and review prompts have separate token budget checks. The local proxy allows time for both calls.

The reviewer (source-review-v7) splits each numbered sentence into claims taken from it, cites exact excerpts for each supported factual claim using short source aliases (S1, S2...), and reports unsupported or contradicted claims and brand, language, topic or platform problems as findings. The server verifies the review: claims must cover every draft token except a fixed connective list (`CONNECTIVES` in app/grounding.py, quoted verbatim in the reviewer prompt) and plain punctuation, whole words and signs must match the draft, and every excerpt must be verbatim source text. A link, email, @handle or phone number repeated from a source but absent from the offer details becomes a `source_contact_detail` finding. Drafts are always shown with their findings; only `copied_instructions` or `revealed_instructions` withholds one. A review the server cannot verify leaves the draft unchecked, with `failed_check` and `failed_sentence` stored, and the UI offers "Check again". An AI review can still miss a semantic error, so source review remains part of the user workflow.

Cached results from older prompt/review versions require regeneration before saving. Existing saved drafts remain accessible. Editing a draft clears its grounded flag; stored review metadata always describes the original generated text, not later user edits.

Opt-in paid verification: `cd backend && uv run python scripts/evaluate_generation.py`. The script uses a disposable migrated database, real embeddings, six negative cases (EN/HE aroma, embellished volunteers, source injection, invented schedule/price, wrong language), and two positive EN LinkedIn/HE Facebook generation/save/edit/delete cases. Wrong-script rejection runs without a paid review. Passing this small fixture set is not evidence of broad-domain accuracy. To evaluate a writer without the reviewer-only cases, add `--live --writer-only`: it runs the garden positives and the 20 scenarios but skips the fixed-draft review cases, whose outcome does not depend on the writer.
