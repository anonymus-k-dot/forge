# Changelog

All notable changes to FORGE. Dates are ISO 8601. Entries under **Unreleased** are not yet
released.

## Unreleased — FORGE 2.0 Phase 0 Step 6

### Added

- Pilot benchmark (`forge.benchmark`, protocol `forge-pilot` v1): 30-task versioned datasets
  `benchmarks/pilot-v1` (`forge-pilot` 1.0.0, current) and `benchmarks/pilot-v0` (0.1.0,
  kept for verifying earlier runs; six of its tasks can be fully passed by the answer "ok"),
  conditions B0 (raw), B1 (generic rewrite) and F-legacy (FORGE 1.x enhancement as on the
  `/enhance` `stream: false` path — not the streamed output the web UI shows), deterministic
  L0 checks, hashed manifests,
  `results.jsonl`/`summary.json`/`summary.md`, optional PostgreSQL persistence in the
  existing `runs`/`executions`/`evaluations` tables, and run verification. Results are always
  labelled INCONCLUSIVE; fake-provider runs are labelled synthetic. Accounting reports
  condition results, executions, provider attempts (retries included), cache hits and
  provider-reported versus estimated tokens separately. No real model has been benchmarked.
  See `docs/benchmark/pilot-protocol.md`.
- `forge` command (`forge benchmark validate-dataset | run | verify`, also
  `python -m forge`). `run` refuses non-fake providers unless `--allow-real-providers` is
  given.

## FORGE 2.0 Phase 0 Step 5 (local commit d101e71)

### Added

- Response cache for run executions (opt-in; never used by `/enhance` or streams):
  canonical SHA-256 keys over the exact request each adapter would send, PostgreSQL table
  `llm_cache_entries` (Alembic `0002`), TTL `FORGE_CACHE_TTL_SECONDS` (default 30 days),
  fail-open on database errors and malformed entries, `cache_hit` on results. Only complete,
  successful results are stored; empty, blocked or filtered responses are not.
- Per-run budgets: required `max_model_calls`, optional token budget with reserve-then-
  reconcile, structural limits and a confirmation threshold; every provider attempt counts;
  atomic PostgreSQL reservations; exhausted runs become `budget_exceeded`. Alembic `0002`
  adds the counters to `runs`.

### Changed

- `repositories.create_run` now requires a valid `budget_limits` with `max_model_calls`.
- Existing databases must run `alembic upgrade head` (`0001` → `0002`, additive); until then
  `/ready` reports `migrations_pending`.

## FORGE 2.0 Phase 0 Steps 1–4 (local commit eb126f0)

### Deprecated

- **`/enhance` fields `confidence` and `score` now return `null`.** They were hardcoded
  constants (`"98%"` / `0.98` on success, `"N/A"` / `0` on error) that were never computed
  from anything. The keys are kept so the response schema is unchanged during the
  transition. **Planned removal:** in the next release after this one ships; removal will be
  listed here first.
  - *Impact:* clients that display these values will show nothing/`null`; clients that do
    arithmetic on `score` (e.g. `score * 100`) must handle `null`. The bundled web UI never
    read these fields from the server and is unaffected.
- `/enhance` fields `template_id`, `template_name`, `template_matched`, `domain` are static
  labels, not classifications. Values unchanged; documented as deprecated.
- `/health` field `templates_loaded` (always `0`). Value unchanged; documented as deprecated.

### Changed

- **`/enhance` error messages are now fixed, safe per-category strings** instead of the raw
  exception text (which could contain upstream response content). Status codes, JSON keys
  and the SSE `{"error": ...}` frame are unchanged. Clients matching on specific upstream
  error wording must switch to the documented messages in `docs/api.md`. (Step 2)
- Transient provider failures are retried up to twice with backoff before an error is
  returned; Gemini requests have a 60 s per-request timeout. (Step 2)
- The application starts and `/health` works without `GEMINI_API_KEY`; `/enhance` then
  returns a configuration error. Previously the process failed to start. (Step 1)

### Added

- PostgreSQL persistence (Step 4): SQLAlchemy 2 + psycopg 3 models for `workspaces`, `runs`,
  `executions`, `evaluations`; Alembic revision `0001`; configured with `DATABASE_URL` and
  `DATABASE_*` pool/SSL options. The app still starts without a database.
- `GET /ready`: 200 when PostgreSQL is reachable and migrated to the shipped head, otherwise
  503 with `not_configured`, `unavailable`, or `migrations_pending`. `/health` unchanged.
- `docker-compose.yml`: `db` service (`postgres:17`, named volume, health check, published on
  `127.0.0.1:5433`). The `forge` service now waits for it and receives `DATABASE_URL`.
  Migrations are never run automatically (`alembic upgrade head`).
- CI: PostgreSQL service, migration steps (`upgrade`, `current`, repeat, `alembic check`) and
  database tests that cannot be silently skipped.
- `X-Request-ID` response header on every response (client value echoed if it matches
  `^[A-Za-z0-9._-]{1,128}$`, otherwise generated). (Step 3)
- Structured JSON logs on stderr for the `forge` logger: `request.completed`,
  `provider.retry`, `enhance.failed`, `enhance.internal_error`, each with `request_id`.
  Prompts, model output, upstream error bodies and credentials are not logged; only an
  unexpected internal error (a bug, not a provider failure) logs its traceback.
  `FORGE_LOG_LEVEL` sets the level (default `INFO`). (Step 3)
- Provider layer: Google GenAI (default), OpenAI-compatible endpoints (Groq, Ollama,
  llama.cpp, …), and a fake provider; selected by `FORGE_PROVIDERS_FILE`. (Step 2)

### Fixed

- `/enhance` with a non-object JSON body or a non-string `prompt` (e.g. `123`, `{}`) crashed
  with a `500` HTML page; it now returns `400` JSON `{"error": "Invalid request. Send a JSON
  object with a string 'prompt' field."}`. `"prompt": null` and falsy bodies keep the
  existing "Empty prompt" `400`. Pre-existing since FORGE 1.x; found in the Steps 1–3 review.
- `scripts/verify_environment.py` printed the first and last four characters of
  `GEMINI_API_KEY`; it now prints only that the key is set and its length.
- Web UI **"Copy as JSON"** exported hardcoded metadata (`confidence: "98%"`, `score: 0.98`,
  …) instead of the enhanced prompt. It now exports `{"enhanced_prompt": "..."}`. (Step 3)

### Internal

- Code moved into the installable `src/forge` package; `gunicorn app:app` and
  `pip install -r requirements.txt` keep working. (Step 1)
