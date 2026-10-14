# Changelog

All notable changes to FORGE. Dates are ISO 8601. Entries under **Unreleased** are not yet
released.

## Unreleased — Legacy web UI usability and accessibility fixes (Phase A)

The existing page at `/` (`src/forge/templates/index.html`) keeps its layout, dark theme,
champagne accent, WebGL background, wordmark and hover effects. The backend and the
`/enhance` stream protocol are unchanged.

### Fixed

- The enhanced prompt is shown as literal text, exactly as it is copied. Previously the page
  reformatted model output (underscores became italics, `**`, code fences and paths were
  altered, headings were re-capitalised), so the displayed text differed from the copied
  text.
- Ctrl/⌘+C is no longer intercepted: copying a selected part of the output works.
- Escape no longer deletes the prompt.
- Errors show the server's own safe message (unavailable, server error, credentials,
  concurrency limit, missing configuration, …) instead of "Something went wrong"; the error
  panel, retry button, button spinner and character-counter warnings are now styled.
- The native cursor (including the text I-beam) is visible again; the decorative ring now
  trails it and is off when reduced motion is requested.
- Text contrast meets WCAG AA (muted text 5.2:1 or more on every surface).
- The shortcuts dialog is a native `<dialog>` opened with `showModal()`: opened by a button
  or `?`, focus moves in and back to the trigger, the page behind it is inert (keyboard and
  assistive technology), and Escape, the close button or a backdrop click closes it. The
  Copy menu exposes its expanded state, supports arrow keys, Home/End and Escape, is
  disabled until there is output, and is shown with the `hidden` attribute so its first
  item can take focus as soon as it opens. On short viewports (small phones, 400% zoom) the
  dialog scrolls instead of cutting off its title and close button.
- Status changes (enhancing, complete, stopped, failed, copied) are announced through a
  polite live region. Decorative icons are hidden from screen readers.
- The removed "Saved" indicator never saved anything; the footer no longer shows "© 2024 THE
  SILENT MONOLITH"; touch devices are no longer told to press ⌘/Ctrl+Enter.
- Where the browser offers no Clipboard API (plain-HTTP pages other than localhost), Copy
  says so and suggests copying the selected text manually, instead of throwing.

### Added

- A Stop button while generating: it aborts the request (the server already releases the
  provider stream when the client disconnects), keeps the partial output with a clear
  "Stopped" state, and allows a clean new request. One request at a time.
- Explicit idle, loading, success, stopped and error states (`data-state` on the output).
- Copy menu: "Copy text" and "Copy as JSON" (the identical "Plain Text"/"Markdown" options
  were merged). JSON of stopped output includes `"partial": true`.

### Tests

- `tests/frontend/`: a fake DOM (`fake_dom.mjs`) that runs the template's real script, a
  behaviour suite (`legacy_ui_behavior.test.mjs`, Node's built-in test runner) and a replay
  harness that feeds real Flask `/enhance` streams (fake provider) into the UI. The fake DOM
  runs the script while the page is still being parsed, as a browser does.
  `tests/test_legacy_ui.py` runs them and checks contrast and removed behaviours.
- Checked once in headless Chrome 155 against the real Flask app with a fake provider
  (isolated: no `.env`, all hosts except 127.0.0.1 blocked, so Tailwind and fonts did not
  load): 28/28 behavioural checks passed, plus the shortcuts dialog at 320×256, 375×812
  and 1280×900. Visual styling that depends on Tailwind and the web fonts was not verified.

## Unreleased — FORGE 2.0 Phase 0 Step 7 (design; no live run)

### Added

- Step 7 real-model pilot protocol (`docs/benchmark/step-7-experimental-protocol.md`,
  `forge-step7-pilot` 1.1.0): preregistered primary outcome (blinded human task success,
  F-legacy vs B0), secondary outcomes, rubric (`benchmarks/evaluation/rubric-v1.json`),
  rater notes for `pilot-v1`, failure classification and a descriptive paired analysis plan.
  Interpretation stays INCONCLUSIVE. No real model has been called. Provider facts (model
  availability, published pricing, data-use terms, subscriptions, thinking mode) are cited
  from public sources retrieved 2026-10-14; account tier, billing status and rate limits are
  owner checks.
- `forge benchmark plan` (offline plan and preflight from a versioned experiment config;
  never builds a provider adapter or reads credentials). For real providers it fails closed:
  a positive token budget is required; every provider/model pair needs a published price
  bound to that exact provider entry (name, type, endpoint) and model, with tier, source URL
  and retrieval date (a missing price is unknown, never free; a price is never applied to
  another provider with the same model name; duplicates are rejected); the cost at the
  token budget must not exceed the ceiling (an estimate: the budget stops the next call but
  does not cap the final call's reported usage; a nonzero Gemini price is refused because
  thought tokens are not counted); and the owner's tier/billing, rate-limit and data-use
  confirmations for every real provider, the thinking-risk acknowledgement and
  `live_execution_approved` are separate checks.
- `forge benchmark export-blind` (seeded, label-free rater folder with only items and a
  rating template; the key is written to a separate `--key` path that must lie outside the
  rater folder and is never overwritten) and `forge benchmark analyze` (paired analysis on
  one task set; refuses fake-provider runs unless `--allow-synthetic`, which labels the
  report SYNTHETIC; refuses runs whose recorded experiment identity, dataset, conditions,
  profiles, providers, models or execution mapping differ from the config).
- Experiment configs `benchmarks/experiments/step7-pilot-v1.json` (proposed Gemini API
  `gemma-4-31b-it` run) and `step7-smoke-v1.json` (one-task smoke test), both
  `live_execution_approved: false` with every owner check unset, and an offline rehearsal
  config.
- `forge benchmark run --pace-seconds`: optional minimum interval between model calls
  (default 0, unchanged behaviour), recorded in `run.json`.

### Changed

- **`forge benchmark run` refuses real providers unless `--experiment FILE` is given** (in
  addition to `--allow-real-providers`). With `--experiment` the offline preflight runs
  before `.env`, credentials or adapters are touched, every run setting comes from the
  config (conflicting flags are refused), the runner re-checks the run against the config
  (including each provider's endpoint, refused before any request if it differs), and the
  manifest records the experiment ID, protocol, version, config hash and the effective
  endpoint of each role (no credentials or query strings); analysis rejects a run whose
  recorded endpoints differ from the config's providers file.
- Offline fake-provider runs without `--database` no longer load `.env`.
- The CLI no longer crashes when a console cannot encode report characters, and reports
  unreadable input files as errors instead of tracebacks.

## FORGE 2.0 Phase 0 Step 6 (local commit 60cf680)

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
