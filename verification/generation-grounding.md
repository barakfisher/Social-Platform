# Local grounding verification — 2026-10-25

Implementation: grounded-post-v3 / source-review-v2. Default writer/reviewer: OpenRouter openai/gpt-4.1. Run: `cd backend && uv run python scripts/evaluate_generation.py`.

Real embedding and generation calls ran against a freshly migrated disposable database; the script dropped only its own database afterward. Queue dispatch was replaced by direct ingestion/embedding execution; no user documents were modified.

Six negative cases were rejected: English aroma; Hebrew aroma; embellished volunteers; copied injection/prohibited promise; invented meeting time/price; wrong language. The first five used live source reviews; the last used the deterministic script check.

English LinkedIn and Hebrew Facebook generated, passed sentence review, saved, read, edited and deleted. Last accepted fixture text:

> At Cedar Community Garden, we grow rosemary and sage. Volunteers gather every Thursday to help care for the garden.

> בגינה הקהילתית מגדלים רוזמרין ומרווה. המתנדבים נפגשים ביום חמישי.

Combined reported completion costs were approximately $0.005328 and $0.005552 for those positive cases, excluding query embedding.

Automated suite: 82 backend tests with PostgreSQL passed (mocked completion providers); 13 Playwright tests passed. Ruff/mypy, Alembic drift, frontend format/lint/types and production build passed. Docker images rebuilt with both tokenizer caches.

This is a small fixture evaluation, not a broad-domain accuracy guarantee. Earlier GPT-4o drafts and a simple yes/no review failed and were replaced. Wider adversarial/domain evaluation and abandoned-request recovery remain open on SP-4. Existing parent issues remain open. No PR, push or merge performed.
