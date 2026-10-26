# Local grounding verification — 2026-10-25

Implementation: grounded-post-v3 / source-review-v2. Default writer/reviewer: OpenRouter openai/gpt-4.1. Run: `cd backend && uv run python scripts/evaluate_generation.py --live`.

Real embedding and generation calls ran against a freshly migrated disposable database; the script dropped only its own database afterward. Queue dispatch was replaced by direct ingestion/embedding execution; no user documents were modified.

Six negative cases were rejected: English aroma; Hebrew aroma; embellished volunteers; copied injection/prohibited promise; invented meeting time/price; wrong language. The first five used live source reviews; the last used the deterministic script check.

English LinkedIn and Hebrew Facebook generated, passed sentence review, saved, read, edited and deleted. Last accepted fixture text:

> At Cedar Community Garden, we grow rosemary and sage. Volunteers gather every Thursday to help care for the garden.

> בגינה הקהילתית מגדלים רוזמרין ומרווה. המתנדבים נפגשים ביום חמישי.

Combined reported completion costs were approximately $0.005328 and $0.005552 for those positive cases, excluding query embedding.

Automated suite: 82 backend tests with PostgreSQL passed (mocked completion providers); 13 Playwright tests passed. Ruff/mypy, Alembic drift, frontend format/lint/types and production build passed. Docker images rebuilt with both tokenizer caches.

This is a small fixture evaluation, not a broad-domain accuracy guarantee. Earlier GPT-4o drafts and a simple yes/no review failed and were replaced. Wider adversarial/domain evaluation and abandoned-request recovery remain open on SP-4. Existing parent issues remain open. No PR, push or merge performed.


## Evaluation expansion — 2026-10-26

Added 20 typed review fixtures: positive and negative EN/HE cases for corrected conflicting
facts, irrelevant sources, unsupported requested details, brand hashtag restrictions and
platform CTA fit. Platform negatives cite the Instagram CTA as source material so a failure
cannot be attributed solely to missing factual evidence. These fixtures exercise the review
stage; they do not establish end-to-end writer, retrieval or broad-domain accuracy.

The default command and `--validate-cases` validate fixtures offline. Paid evaluation now
requires explicit `--live`. Internal `--isolated` also requires a reserved disposable-database
marker matching the explicit database URL before application initialization.

Verification: Ruff format/lint, mypy for the evaluator and offline validation of all 20 fixtures
passed. Separate QA passed nine loader boundary checks, five CLI checks and four isolation
guard rejection checks. Security audit found no unresolved findings after the isolation bypass
was fixed; review covered input validation, SQL identifiers, cleanup and output exposure. Checks were
transient Python checks; no persistent TypeScript tests were added to this Python backend.

Execution incident: the initial edit helper used unavailable `python`; the subsequent shell
command still launched the old live evaluator. It was terminated immediately after discovery.
Three completed legacy negative reviews were logged; additional in-flight provider usage is
unknown. Its disposable database was explicitly removed and the database list was checked
empty. This was unintended paid execution, not verification of the new fixture set. The new
explicit live gate prevents default invocation from repeating it. No user sources were added.

Pending: authorized live execution of the expanded matrix, graceful omission of unsupported
requested details, broader domain coverage, actual user Brand DNA/Ready-source checks and
deployment model availability. Platform fit remains reviewer judgment. SP-4 stays In Progress;
no release acceptance criteria were newly checked. No commit, push or merge performed.


## Authorized paid evaluation — 2026-10-26

After the user explicitly authorized paid models, `uv run python
scripts/evaluate_generation.py --live` exited 0 using configured OpenRouter
`openai/gpt-4.1` for writing and review. All 20 expanded fixtures passed: ten
negative cases rejected and ten supported controls accepted, across English and Hebrew.
All six legacy negatives also passed (five live reviews and one deterministic language
rejection). Corrected facts, irrelevant evidence, unsupported requests, hashtag restrictions
and Instagram CTA mismatch on LinkedIn were covered by the expanded set.

Both end-to-end scenarios passed real embedding/retrieval, generation, sentence review,
save, read, edit and delete: English LinkedIn (77 characters) and Hebrew Facebook
(65 characters). Combined writer/reviewer completion costs reported by those two scenarios
were $0.005528 and $0.005848 respectively. These figures exclude embeddings and the
standalone negative/control reviews; total evaluation billing was not measured.

The run used its own newly migrated disposable database and removed it afterward.
A separate PostgreSQL catalog check found no remaining evaluation databases. The user
workspace and private environment file were not modified. No commit, push or merge.

Before this authorization, free-only experiments were attempted without paid fallback:
Nemotron returned a provider error; Liquid passed one rejection then became unavailable;
the free router recorded nine cases before cancellation, with one correct rejection and
eight invalid responses. This does not establish free-model suitability or effectiveness.
No paid embeddings or workspace mutations were used for those review-only experiments.

SP-4 remains In Progress. This is live evidence for a small garden-domain fixture matrix,
not broad-domain or actual-user-source validation. Remaining work includes additional
domains, graceful handling of unsupported requested details, actual user Brand DNA and
Ready-source validation, and the deployment-model decision/availability verification.


## Multi-domain end-to-end evaluation — 2026-10-26

Added 16 strict fixtures in `backend/scripts/generation_scenarios.json`: library and bicycle
repair domains, English/Hebrew, each with a supported request and missing price/date/benefit
requests. The evaluator creates a fresh Brand DNA version and exactly one Ready source per
scenario in its disposable database. Real embeddings, retrieval, writer and source reviewer
are used; only queue dispatch is replaced with direct task execution. Sources are deleted
between cases. No user workspace sources are involved.

All 16 scenarios obtained passing live results with configured OpenRouter `openai/gpt-4.1`
across the initial and targeted runs, not one uninterrupted green matrix run:

| Domain | Request | English | Hebrew |
| --- | --- | --- | --- |
| Library | Supported facts | Draft | Draft |
| Library | Missing price | Draft | Draft |
| Library | Missing date | Withheld | Withheld |
| Library | Missing benefit | Draft | Withheld |
| Bicycle repair | Supported facts | Draft | Draft |
| Bicycle repair | Missing price | Draft | Draft |
| Bicycle repair | Missing date | Withheld | Withheld |
| Bicycle repair | Missing benefit | Draft | Draft |

Draft results checked required source terms, fixture forbidden phrases, length, hashtags,
review status, exact document provenance and current Brand DNA version, then saved/read/deleted.
The five withheld scenarios checked persisted Failed status, null public result, and rejection
of saving the failed generation. Provider errors are not accepted as semantic rejection.

Three initial lexical failures were captured as safe missing-information disclaimers, not
claims that the requested price/event existed. Those failures remain part of the execution
history. After manual review, their exact complete sentences were added as explicit fixture
exceptions; substring/prefix exemptions are not used. Appended or embedded factual claims
remain checked. Targeted reruns passed; later date runs withheld rather than returning the
previous disclaimer. Generation remains probabilistic, and these exceptions are deliberately
narrow. The lexical oracle plus model review is not a general semantic factuality guarantee.

Run only the new suite with `uv run python scripts/evaluate_generation.py --live --scenarios-only`
from backend. Repeat `--scenario NAME` for targeted cases without repeating the baseline paid
suite. All selectors require `--live`; default/`--validate-cases` stay offline. The runner
continues other scenarios after assertion failures and exits unsuccessfully if any failed.
Unexpected runtime/provider exceptions still abort the run. Diagnostic content on lexical
failure comes only from disposable fixtures, not user documents.

Separate QA added persistent Python tests in `backend/tests/test_generation_scenarios.py` for
loader boundaries, exact matrix coverage, invalid patterns, content limits, exact disclaimers
and claim-hiding attempts, paid-mode gates, selector propagation, failed-result withholding,
save rejection, source cleanup and aggregate-failure behavior. Security review found no
blocking issues; internal callable helpers still rely on the guarded CLI isolation boundary.
Final verification: all 84 focused offline tests passed; Ruff lint/format and evaluator mypy
passed. Offline CLI validation counted 20 review fixtures and 16 end-to-end scenarios with
zero provider calls. The only warning was the existing Starlette/httpx deprecation warning.

Every live-run disposable database was removed, including failed runs. Total provider billing
for this continuation was not measured; reported per-draft costs exclude query/source
embeddings and rejected/repeated calls. No user sources, environment secrets, app production
code or deployment configuration were modified. No commit, push or merge.

SP-4 and its parent stay In Progress. Small curated evaluation now has live evidence across
three domains; arbitrary domains, paraphrases, model nondeterminism, actual-user Brand DNA and
Ready-source validation, and deployment/requested-model availability remain release work.

## Actual-user validation — 2026-10-26

Actual-user validation did **not** establish usable supported generation in either language.
SP-4 and SP-16 remain In Progress; no acceptance checkbox was newly checked.

Validated after merge commit `d36d3a4`, with configured OpenRouter `openai/gpt-4.1`
writer/reviewer and existing budgets, timeouts and retries. API readiness passed;
configuration reported configured=true, brand_ready=true and ready_documents=1. Brand
DNA version 2 contains a name and audience; positioning, voice, guidelines and prohibited
claims are empty. No fields were filled in. This limits style/prohibited-claim assessment.

A transient private Python harness read the original through read-only, repeatable-read
transactions. It cloned only the scoped user/workspace, actual Brand DNA, one Ready
document (2,054 source characters) and three existing chunks/embeddings into a newly
migrated `social_generation_verify_<random>` database. The child checked the reserved
marker and explicit database URL before application import. Existing embeddings were
reused; query embedding, writer and reviewer calls were live. No invented source/readiness
bypass or application, prompt, threshold or model change was used.

A structured GPT-4.1 planning call privately selected equivalent EN/HE requests supported
by four source facts and identified absent exact purchase price, upcoming launch date and
guaranteed quantified outcome. Six challenges requested those unsupported details alongside
the supported topic. Planner/audit outputs were locally validated using strict Pydantic
models. Private source text, topics, drafts and provider issue text were not printed or
committed. The harness was transient; these private requests are not reusable committed
fixtures. Source selection and semantic assessment were model-assisted, not human approval.

Initial matrix, one uninterrupted run (exit 1):

| Request | English / LinkedIn | Hebrew / Facebook |
| --- | --- | --- |
| Supported topic | Failed: insufficient_context | Failed: grounding_review_failed |
| Infer exact purchase price | Inconclusive: insufficient_context | Safely withheld: grounding_review_failed |
| Infer exact upcoming launch date | Inconclusive: insufficient_context | Safely withheld: grounding_review_failed |
| Promise 50% improvement within seven days | Inconclusive: insufficient_context | Safely withheld: grounding_review_failed |

Three Hebrew challenges passed fail-closed checks. Supported cases and all four English
cases failed evaluation expectations (five failures). Retrieval failures do not count as
semantic rejection. All eight persisted Failed status, exposed no public result and
rejected saving with HTTP 404. No accepted draft was available; positive provenance and
save/read/delete checks did not execute and must not be reported as passed.

A second disposable run repeated only the two supported requests, capturing live
writer/reviewer responses privately in memory. Separate diagnostic retrieval omitted the
cutoff, while production generation retained it:

- English: three eligible chunks; nearest cosine distance 0.727529 versus configured
  maximum 0.65; zero within threshold. Generation again returned insufficient_context.
- Hebrew: three eligible chunks; nearest distance 0.289866; all three within threshold.
  Generation again returned grounding_review_failed. Production review returned
  accepted=false, one issue and zero supported sentences out of three; evidence quote
  membership was valid. A separate full-source GPT-4.1 audit rated factual support, topic,
  audience, platform, language, omission of unsupported detail and brand identity acceptable.
  This is reviewer disagreement, not proof of an incorrect production rejection. Its cause
  remains open; same-model auditing is not independent human editorial verification.

Diagnostic run: exit 1, both supported cases failed, public results absent and saves blocked.
Instrumentation returned actual provider responses and preserved production safeguards.
Its writer capture parsed valid JSON in this run; malformed-output behavior was not tested.

Separate QA reviewed API contracts, provenance/persistence expectations, strict output
validation, failure handling and isolation; syntax compilation passed. Separate security
audit found no remaining blocking findings after suppressing application logs, removing
unconstrained planner output and allowlisting error codes. Auditors made no provider calls
or user-data reads. This transient harness is trusted developer instrumentation, not a
production security boundary. No application changes or new regression tests; the historical
169-test suite was not rerun. Offline validation passed for 20 review fixtures and 16
generation scenarios with zero provider calls. Existing Starlette/httpx warning observed.

Both disposable databases were removed in finally blocks. A subsequent PostgreSQL catalog
check found zero evaluation databases. Original scoped Brand DNA/documents/chunks/posts/
generation/jobs fingerprints matched before and after each run. Saved posts remained empty;
private backend/.env remained ignored and unmodified. Total provider billing was not
measured. Reported planning/extra-audit costs alone were $0.004902 and $0.006828, excluding
generation/review/query embeddings and any unreported usage.

Next existing SP-4 work: investigate cross-language retrieval and the Hebrew review
disagreement without weakening factuality safeguards, then address deployment-model
availability and remaining context/source-instruction release criteria. Suggestions/media
remain deferred. No push, PR or merge was performed for this validation.

## Cross-language retrieval and review continuation — 2026-10-26

The user authorized continuing and explicitly selected an EN/HE query-translation fallback
using the existing model, preserving relevance, review and the total completion allowance.
The actual Ready document is Hebrew. Additional equivalent English topic/keyword queries
had nearest distances 0.815756 and 0.768751 (an earlier keyword run: 0.777968); equivalent
Hebrew forms reached 0.575927 and 0.421153. None of the English variants met the unchanged
0.65 cutoff. These observations support cross-language retrieval as the immediate blocker;
they do not establish embedding quality for arbitrary queries.

Private Hebrew diagnostics also found a concrete extraction failure: the model accepted
three sentences but stitched two nonadjacent source passages into one quote, omitting 126
source characters. Ordered coverage and chunk IDs were valid; exact membership correctly
failed. Source-review-v3 now explicitly requires separate contiguous quotations. Exact
validation was retained, not normalized or relaxed. Replaying that same draft with v3
still produced a rejection, while a later fresh supported generation passed. Quote stitching
and false rejection are not claimed to be eliminated by the instruction change.

Implemented app/query_translation.py and generation orchestration: only empty initial
scoped retrieval triggers one bounded translation to the opposite topic script. The second
search preserves owner, Ready/profile/model/dimension filters, 0.65 cutoff and context
budget. Context trimming that removes existing hits never triggers translation. Translated
queries are strictly validated, remain out of factual evidence and returned metadata, and
do not replace original writer/reviewer preferences. No new dependency, embedding model,
source or user Brand DNA change was introduced.

Initial fixed 20/40/40 completion shares caused generation_spending_limit before writing.
That failed live attempt is retained as execution history. The final allocation still
preflights translation within 20%, including all allowed retries. After it completes,
estimated_max_usd multiplied by attempts actually made remains consumed; writer/reviewer
each receive half the remainder, including all of their possible retries. Strict finite
reservation/attempt validation rejects impossible metadata. This reuses only future
translation retries that cannot occur after completion, not unverified provider billing.
Actual translation usage is included in successful completion totals and preserved on
downstream failure. The extra embedding call remains outside completion accounting.

Final actual-source outcomes were obtained across targeted runs, not one uninterrupted
green matrix. Two supported runs passed production review with exact evidence, original
preferences, save/read/delete and independent model-assisted factual assessment:

| Request | English / LinkedIn | Hebrew / Facebook |
| --- | --- | --- |
| Supported topic | Grounded draft; translation to Hebrew used | Grounded draft; no translation |
| Infer exact purchase price | Withheld | Withheld |
| Infer exact upcoming launch date | Withheld | Draft; additional audit disputed support |
| Promise 50% improvement within seven days | Grounded draft omitting unsupported guarantee | Withheld |

The six-challenge run exited unsuccessfully because the Hebrew date case failed its
additional audit. Production review accepted that draft with exact quotes; a separate
full-source audit flagged an extra claim, and an initial classification called it an
invented event/date. A later targeted source/third-sentence check found no unsupported
clause and judged the sentence supported. These conflicting model assessments remain
unresolved; the case has NOT been exempted, marked passed, or treated as proof of a leak.
Model assessment is not independent human editorial verification. Some other withheld
challenges were judged safe by the extra audit, preserving the known false-rejection risk.
All withheld challenge runs had Failed/null public results and HTTP 404 save rejection.
Every accepted draft passed save/read/delete; test-created drafts/runs were removed.

Reported completion costs for supported English/Hebrew drafts were $0.009326/$0.010250.
Their measured reservations remained below $0.05. These are not total experiment billing;
query embeddings, rejected attempts, targeted classifiers/replays and separate fixture
reviews are excluded. Total provider billing remains unmeasured. No private text, source
names, topics, drafts, model issue text or credentials were printed or committed.

Final verification: 231 backend tests passed against a freshly migrated disposable DB
(completion calls mocked); Ruff format/lint and app mypy passed; offline validation passed
20 review fixtures and 16 generation scenarios with zero provider calls. All 20 existing
review fixtures also passed a live source-review-v3 regression run: ten accepted controls
and ten rejected negatives. The 16 synthetic generation scenarios were not rerun live.
Existing Starlette/httpx deprecation warning only. No frontend code/tests changed.

Fresh QA added EN/HE exact-excerpt tests, stale-v2 retry/read/save tests, translation/schema
and reservation boundary tests, scoped fallback/budget/usage/idempotency/failure tests and
context-trimming coverage. Fresh security audit found no blocking issue in the final
translation/reservation/review changes. A temporary private-capture path was hardened to
exclusive, no-symlink creation; existing captures were verified regular, owned and 0600.
Auditors did not access user data or make paid calls. Original workspace fingerprints
matched after every disposable generation run. All temporary databases were dropped.
The disputed Hebrew sample and complete source snapshot were retained outside the checkout
in a private temporary directory (0700; case file 0600) for adjudication. Other transient
scripts/captures were removed. No private artifact was added to Git.

The local API was rebuilt for this continuation; no public deployment, push, PR or merge.
Readiness and configuration passed; the container reports source-review-v3 and
retrieval-translation-v1. Final catalog check found zero evaluation databases, Brand DNA
version 2, one Ready source and zero saved posts.
SP-4/SP-16 remain In Progress with no new checkbox checked. Next existing SP-4 work is
to resolve the Hebrew date audit disagreement and remaining release evaluation, then
context/source-instruction and requested-model deployment criteria. The reviewer schema
also still requires evidence for unsupported sentences; QA identified this as a separate
contract inconsistency that can yield review_invalid, not the cause of the valid rejected
verdicts above. It is recorded here without creating an overlapping issue or claiming a fix.

## Hebrew date-case adjudication — 2026-10-26

Offline only, no provider calls: the retained private sample (draft, production review,
retrieved context and complete source snapshot) was compared with deterministic substring
checks and a manual sentence-by-sentence reading. No private text is reproduced here.

- **Date challenge: no leak.** The draft contains no future or launch date. Its only number
  is a historical publication year that appears verbatim in the retrieved context. The draft
  omitted the unsupported date request, like the English guarantee case. The earlier
  "invented event/date" classification is refuted.
- **Grounding: real gap in sentence 1, not 3.** Retrieval supplied source characters
  622–2054 of 2054. The first sentence of the draft makes an etymology/origin claim and names
  the epic as a work. Neither appears in the provided context; both appear only in the
  unretrieved opening of the source. The two evidence quotes are exact but support only the
  disguise/assistance part of the sentence. Production review accepted a clause that the
  context does not support. It happens to be true per the full document, so it is an
  ungrounded (parametric) claim, not a factual error.
- **Why the audits disagreed.** The full-source audit's "extra claim" is consistent with the
  sentence-1 gap. The later targeted check examined the third sentence, which is supported
  (all five quotes are exact members of the context). The two audits assessed different
  sentences, so the "conflict" is not a contradiction.

Verdict: case **failed** under the system's contract (every claim supported by provided
excerpts). Exact-quote membership and ordered coverage cannot detect a clause that carries
no quote; that relies on the model reviewer. This is the same class of risk as the known
false-acceptance limit and is not fixed. Case not exempted; SP-4 stays In Progress.

Follow-up fixture: added the `outside_context` review category to
`scripts/generation_review_cases.json` with four synthetic, non-private cases. They are
English and Hebrew negatives, each adding a true world-knowledge origin claim that the
source lacks, plus their exactly-sourced controls. The case set is now 24. Offline
`--validate-cases` passed with zero provider calls. The CLI test now derives the expected
count from the fixture file. The new cases have not been run against the live reviewer.

## source-review-v4: claim-level evidence — 2026-10-26 (offline, uncommitted)

app/grounding.py now asks the reviewer to split each sentence into ordered claims copied
exactly from the sentence. The server rejects the review unless the claims cover every word
except a fixed EN/HE connective list (`CONNECTIVES`), every claim is supported, and every
supported claim has at least one exact quote. Unsupported claims may have empty evidence,
which removes the QA-noted `review_invalid` path for valid rejections. Bumping
REVIEW_VERSION invalidates v3 results on retry, GET and save, as v2 was invalidated before.

Tests: new EN/HE regressions for a sourced remainder with an unclaimed, unsupported, or
evidence-free origin clause; coverage cases (connectives, punctuation, Hebrew prefixes,
qualifier "today"/"כיום", numbers, order, overlap, absent text); and a claim-count bound.
With coverage disabled, both unclaimed-clause regressions fail, so they test the new check.
Full backend suite: 256 passed on a fresh disposable database migrated as the admin role and
tested as the restricted runtime role (dropped afterwards; zero test databases remain).
The run included uncommitted concurrent spending-limit changes in this checkout. Ruff
format/lint, app mypy and offline validation (24 review cases, 16 scenarios, zero provider
calls) passed. No live or paid calls; v4 has not been run against the real model.

Open constraint: compact v4 output for a 600-character post measured 818–1,322 tokens in
Hebrew and 626–974 in English (o200k_base, 2–5 claims per sentence, short source aliases),
or 878–1,952 with UUID chunk IDs. Review output is capped by the shared
GENERATION_MAX_OUTPUT_TOKENS of 900. Longer reviews would be truncated and fail closed as
`grounding_review_invalid`. Raising the reviewer limit also raises the spending reservation.

v4 follow-up (owner decision recorded in docs/implementation.md): reviewer sources now use
short aliases mapped back to real chunk IDs in stored provenance, the reviewer has its own
1,600-token output limit, and the default per-request cap is $0.13. The provider clamp now
allows the larger of the writer and reviewer limits, and callers without an explicit value
still get the writer's 900. Full backend suite: 261 passed on a fresh disposable database
using the restricted runtime role (dropped; zero test databases remain). Ruff, mypy and
offline validation (24 cases, zero provider calls) passed. No live calls.

## source-review-v4 live check — 2026-10-26 (paid, user-authorized)

Scope: 25 calls to the review function only, against configured OpenRouter openai/gpt-4.1
(timeout 30 s, one retry, reviewer output limit 1,600). These were the 24 curated fixtures
and one replay of the retained private Hebrew sample. No writer calls, embeddings or
database. A transient scratchpad harness timed each HTTP attempt and has been kept out of
Git. The private raw review was saved beside the private case (directory 0700, file 0600).
Only structural results are recorded here.

| Result | Cases |
| --- | --- |
| Fixtures | 23/24 as expected: all 12 negatives except `outside_context_he` rejected; all 12 controls accepted |
| `outside_context_he` | **Accepted (wrong).** Two claims, both marked supported, coverage passed. The origin clause was split out as its own claim and still judged supported |
| `outside_context_en` | Rejected (correct) |
| Private Hebrew replay | **Accepted (wrong).** One claim per sentence, each the whole sentence. Sentence 1 cited the same two quotes as v3, so coverage passed trivially |

Latency: 25 attempts, one each, no retries or timeouts; mean 1.76 s, max 4.05 s against the
30 s timeout. Output: max 501 completion tokens (private replay), well under 1,600; every
response finished with `stop`. Provider-reported cost for the 25 calls: $0.07436 (no unknown
costs).

Conclusion: claim-level coverage only works when the model splits claims, and it does not
stop the model from judging an unsourced clause supported. Both failures are reviewer
judgment errors, which is the known limit recorded for v4. The case remains failed. SP-4
stays In Progress. The measured output (≤501 tokens) is far below the estimate behind the
1,600-token limit and $0.13 cap, because the model produced few claims per sentence.

## OpenRouter reviewer-model availability — 2026-10-26 (public catalog, no paid calls)

The public `GET /api/v1/models` catalog (468 models) lists no `anthropic/claude-3*` model,
so the Claude 3.5 Sonnet named in SP-4 is not available through OpenRouter. `openai/gpt-4o`
is listed ($2.50/$10 per million tokens, structured outputs). Current Anthropic, OpenAI and
Google models with structured outputs are available. Most newer ones are reasoning models
that do not list `temperature` as supported. The app always sends `temperature: 0`, does
not control reasoning, and counts any reasoning tokens against max_completion_tokens. Prompt
estimates use the configured o200k_base tokenizer, which undercounts for Claude and Gemini
tokenizers. These compatibility points are not yet tested live.

## Reviewer-model comparison — 2026-10-26 (paid, user-authorized, up to about $1.20)

The same review-only harness ran the same 25 cases (24 fixtures plus the private Hebrew
replay) through unchanged source-review-v4 code. Only GENERATION_REVIEW_MODEL changed. A
per-model spending stop was enforced. The GPT-4.1 row is from the earlier v4 live check.

| Reviewer | Fixtures | `outside_context_he` | Private HE case | Wrong results | Max / mean latency | Max output | Cost (25) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| openai/gpt-4.1 | 23/24 | accepted (wrong) | accepted (wrong) | 2 | 4.1 s / 1.8 s | 501 | $0.0744 |
| anthropic/claude-sonnet-5.5 | 23/24 | rejected | inconclusive: hit 1,600-token limit (`length`), withheld as invalid | 1 + 1 inconclusive | 11.7 s / 3.3 s | 1,600 | $0.1812 |
| openai/gpt-5.6-terra | 23/24 | rejected | rejected, for the right reason | 1 | 15.3 s / 3.8 s | 907 | $0.1112 |
| google/gemini-3.7-flash | — | — | — | all 25 HTTP 400 | — | — | $0 |

- Both Sonnet and GPT-5.6-terra rejected `outside_context_en_supported`, an exactly sourced
  control, with one issue and every claim marked supported. Its topic asks where the word
  comes from, and the draft does not answer that, so this is likely a topic-fit rejection
  and possibly a fixture ambiguity. The reviewer's issue text was not captured, so this is
  not confirmed. The Hebrew twin with the same topic was accepted by both.
- GPT-5.6-terra on the private case (checked privately; only booleans printed): the
  sentence-1 origin clause was its own claim, marked unsupported. It also marked a second
  sentence-1 claim and the "today" qualifier in sentence 3 unsupported. Issue codes:
  `unsupported_claims` and `missing_requested_future_launch_date`. The second code
  penalizes the draft for correctly omitting an unsupported date request, which is a
  false-rejection risk.
- Sonnet 5.5's reasoning tokens count against max_completion_tokens. On the longest case it
  used all 1,600 and was cut off; the app does not control reasoning effort.
- Gemini 3.7 Flash rejected every request with HTTP 400 at no cost. The response body was
  not captured. Likely causes are `temperature: 0` or the strict JSON-schema format, but
  this is not established.
- No retries or timeouts for any model. Comparison spend: $0.2924 (Sonnet $0.18119,
  GPT-5.6-terra $0.11119, Gemini $0), all provider-reported. Raw private reviews are kept
  beside the private case (0600), outside Git.

Limits: 25 cases per model is a small sample, and model assessment is not human editorial
review. No default model was changed.

Selectable reviewer (offline and local, no paid generation): backend suite 269 passed on a
fresh disposable database with the restricted runtime role (dropped; none remain). Ruff
and mypy passed. Playwright: 17 passed, including the cost display and choice submission
in English and the Hebrew options-unavailable fallback; the frontend production build,
lint, Prettier and types passed. The API container was rebuilt; the live
`/generation/review-models` (free catalog call) returned GPT-5.6-terra ~$0.0159 typical /
$0.0629 max and GPT-4.1 ~$0.0081 / $0.0501. Browser pane check: English at desktop width
and Hebrew RTL at 375 px. The selected cost line shows on phones, with no horizontal
scroll. Not run: a paid end-to-end generation with GPT-5.6-terra.
