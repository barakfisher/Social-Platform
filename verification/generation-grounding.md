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
