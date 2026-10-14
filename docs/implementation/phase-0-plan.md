# Phase 0 — Foundation and Baseline: Implementation Plan

Inputs: [current-state](../architecture/current-state.md),
[target architecture](../architecture/target-architecture.md),
[ADRs](../architecture/architecture-decisions.md).

## 1. Findings that drive the plan

1. Single-module backend with import-time credential requirement → package + factory (ADR-001, ADR-004).
2. No persistence at all → PostgreSQL + Alembic from scratch; nothing to migrate (ADR-002).
3. Hardcoded single model, no timeouts/retries → provider layer (ADR-005, ADR-006).
4. Fabricated `confidence`/`score`; UI JSON export bug → remove + fix (ADR-009).
5. Raw exception text returned to clients → normalized messages (ADR-010).
6. Unused `groq` SDK, unpinned deps, no lockfile.
7. Tests mock SDK internals → tests move to a fake-provider seam while keeping every
   behavioral assertion about the HTTP contract.
8. Groq keys in pushed git history → owner must revoke (not fixable in code).

## 2. Increments

Each increment ends green: `pytest`, `ruff check`, and (from increment 2 on) `mypy src/forge`.
Each is a separately reviewable diff.

| # | Increment | Files (add / change) | Verification |
|---|---|---|---|
| 1 | **Package skeleton + settings + factory + shim.** Move legacy logic into `forge.legacy.enhance`; `create_app()`; root `app.py` shim; lazy provider construction. **Done — see §7.** | add `src/forge/{__init__,app,settings,errors}.py`, `src/forge/api/{health,legacy}.py`, `src/forge/legacy/enhance.py`; move `templates/` → `src/forge/templates/`; change `app.py`, `pyproject.toml`, `requirements-dev.txt`, `scripts/verify_environment.py` | All 12 legacy tests pass with **no test file changes**; app imports and `/health` works with no `GEMINI_API_KEY`; `gunicorn app:app` import check |
| 2 | **Provider layer.** Protocol, capabilities, normalized errors, retries, concurrency, router, fake adapter, Google GenAI adapter, OpenAI-compatible adapter, JSON provider config. Legacy `/enhance` routed through `ProviderRouter`. Safe client error messages (ADR-010, moved here from increment 3). **Done — see §7.** | add `src/forge/providers/*`, `config/providers.example.json`; change `legacy/enhance.py`, `api/*.py`, `app.py`, `settings.py`, root `app.py`, `requirements.txt` (pydantic), `.env.example` | Unit tests: error mapping per adapter (HTTP status/SDK exception → category), retry/backoff + `Retry-After`, no retry on non-retryable, timeout, unsupported capability, streaming failure mid-stream, contract tests run against fake + both real adapters with `httpx.MockTransport` / stubbed SDK |
| 3 | **Remove fake metrics + logging.** ADR-009 (implemented as a null-value deprecation); UI JSON-export fix; **Done — see §7.** JSON structured logging and `X-Request-ID` (moved here from increment 1, which was kept to a pure restructure); `CHANGELOG.md`; `docs/api.md` update. | add `src/forge/logging.py`; change `api/legacy.py`, `src/forge/templates/index.html`, tests, docs | Tests assert fields absent; JSON export contains the prompt; every response has `X-Request-ID`; logs contain no prompt text or secrets by default |
| 4 | **Database layer.** **Done — see §7** (no `forge db` CLI: the standard `alembic` CLI plus `forge.db.migrate` helpers covered every need). Settings → engine (pool, SSL, connect timeout, pool mode), session scope with explicit transactions, models, first Alembic migration, repositories, `/ready`, `forge db upgrade/current`. Docker Compose `db` service. | add `alembic.ini`, `src/forge/db/**`, `src/forge/cli.py`; change `docker-compose.yml`, `.env.example` | Unit: URL normalization, SSL/pool-mode options, missing-URL error. **Postgres:** `alembic upgrade head` on empty DB, `downgrade base` + upgrade again, `alembic check` (models == migrations), FK/unique/check constraints reject bad rows, `RESTRICT` prevents deleting runs with executions, data visible from a fresh engine (restart simulation) |
| 5 | **Cache + budgets.** **Done — see §7** (code in `src/forge/infrastructure/`; SQL in the stores rather than a separate `db/repositories/cache.py`). Cache key, memory + Postgres stores, router integration, `BudgetGuard`. | add `src/forge/infrastructure/{cache,budgets}.py`, `db/repositories/cache.py` | Unit: key differs when any of provider/model/params/system/messages/schema change; identical inputs → identical key; failures not cached; `cache_hit` flagged. Budget stops the N+1th call. Postgres: unique key under concurrent insert |
| 6 | **Pilot benchmark.** ~30 tasks, systems B0/B1/F-legacy, L0 checks, manifest hashing, runner, reports, persistence, `forge benchmark run`. **Implemented — see §7** (module names differ: `dataset`, `conditions`, `manifest`, `records`, `verify`, `report`; no migration). | add `src/forge/benchmark/*`, `benchmarks/pilot-v0/{tasks.jsonl,README.md}` | Task-file schema validation; manifest hash stable across runs and changes when any input changes; fake-provider end-to-end run writes manifest + results + summary and DB rows; replay from cache flagged as cached |
| 7 | **Real-provider verification** (needs your go-ahead, see §6). Single smoke request; then optionally the pilot on one real target model. **Designed and validated offline — see §7 and `docs/benchmark/step-7-experimental-protocol.md`; live calls NOT RUN.** | — | Recorded command output, model ID, usage; or marked **NOT RUN** |
| 8 | **CI, docs, status.** Postgres service in CI, migrations check, mypy; required docs from spec §29 that Phase 0 touches; README corrected; feature-status updated. | change `.github/workflows/ci.yml`, `Dockerfile`, `README.md`, `docs/**` | CI config validated locally where possible (same commands run locally) |

## 3. Dependencies

| Change | Package | Justification |
|---|---|---|
| add | `SQLAlchemy>=2.0,<2.2` | ORM / core (spec) |
| add | `alembic>=1.13,<2` | migrations (spec) |
| add | `psycopg[binary]>=3.1,<4` | maintained PG driver (ADR-002) |
| add | `pydantic>=2.6,<3` | request/config/task-file validation; already a transitive dep of `google-genai` |
| keep | `httpx` | now used directly by the OpenAI-compatible adapter |
| remove | `groq` | unused (ADR-005) |
| remove (dev) | `pytest-asyncio` | no async tests |
| add (dev) | `mypy` | type checking of `src/forge` |

No paid services, no vendor DB SDKs, no Redis/Celery.

## 4. Risks

| Risk | Mitigation |
|---|---|
| Breaking the Render deployment | Keep `app:app` + `requirements.txt` path (requirements installs the package with `.`); add a test that imports root `app` and serves `/health` without any env vars |
| API consumers relying on `confidence`/`score` | Explicit changelog entry; awaiting your confirmation (ADR-009) |
| No local Postgres right now (Docker daemon stopped) | Postgres tests skip loudly locally until a DB is available; CI always runs them. **Phase 0 cannot be declared accepted until they have run green against a real Postgres.** |
| SQLAlchemy 2.1 installed locally vs 2.0 elsewhere | Pin `>=2.0,<2.2`; CI matrix exercises a fresh resolve |
| Real-model availability / quotas | Model IDs are configuration; smoke test validates; pilot is budget-capped |
| `gemma-4-31b-it` may not be available on the Gemini API | Smoke test will reveal it; the model ID stays configurable without code changes |
| Small pilot misread as evidence | Reports label results INCONCLUSIVE and state L0 limits |

## 5. Phase 0 acceptance criteria → how each will be demonstrated

| Criterion (spec §28) | Evidence |
|---|---|
| Existing functionality has a documented compatibility status | `feature-status.md` compatibility table; legacy contract tests |
| Application starts locally with documented configuration | `docs/implementation/local-development.md`; test + manual `flask`/`gunicorn` start |
| PostgreSQL migrations apply cleanly | `alembic upgrade head` / `downgrade base` / `check` output against Postgres |
| Data survives application restarts | Postgres test writes via one engine, disposes it, reads via a new engine; manual compose restart check |
| One configured provider can execute a real request | `forge providers smoke <profile>` output (step 7) |
| A fake provider can run the same code path in CI | Benchmark e2e test with `fake` adapter through `ProviderRouter` |
| Provider errors are normalized | Adapter error-mapping unit tests |
| Cache keys separate different models and configurations | Cache key unit tests |
| Budget limits stop excessive work | BudgetGuard + router tests; benchmark run aborted by budget test |
| A small benchmark run creates a reproducible manifest and results | Benchmark e2e test: same inputs → same manifest hash; outputs on disk + in DB |
| Raw, generic rewrite, and current FORGE are distinguishable baselines | System IDs `B0`, `B1`, `F-legacy` in manifest, rows and report |
| Tests pass, or remaining failures are documented | Final verification section in `feature-status.md` |
| No unverified performance or quality claims | README/docs cleanup; reports state limitations |

## 6. Decisions needed from the owner

1. **Local PostgreSQL.** *Update 2026-10-12: Docker Desktop is now running (confirmed by the owner and by a successful image build in Step 2).* Start Docker Desktop (then `docker compose up -d db`), or point
   `TEST_DATABASE_URL` at another Postgres (e.g. a Neon dev branch).
2. **Real provider calls.** Permission to use keys in `.env` for (a) one smoke request and
   (b) the ~30-task pilot: 30 tasks × 3 conditions = 90 condition results. On the normal
   path B0 needs one target call per task and B1 and F-legacy one rewrite plus one target
   call each — 5 provider attempts per task, 150 for 30 tasks, if every call succeeds on
   its first attempt and caching is disabled. Retries add attempts (up to
   `retry.max_attempts` per call, 450 at the default of 3); cache hits remove them.
   Attempts are not the same as billable requests, which depend on the provider.
   Which provider: Groq (open-weight models via OpenAI-compatible API), Gemini (legacy
   default), or local Ollama.
3. **ADR-009**: confirm removal of `confidence` / `score` from `/enhance`.
4. **Commits**: whether to commit each increment (spec forbids committing without authorization).
5. **Hosted DB**: Neon as primary (default) unless you prefer Supabase.

## 7. Progress log

### Increment 1 — package restructure (completed 2026-10-12, uncommitted)

**What changed**

- New installable package `src/forge` (setuptools, `src/` layout). Version and dependencies
  are dynamic: `forge.__version__` and `requirements.txt` (single dependency list).
- `forge.app.create_app(settings=None)` builds the app; no network or database I/O.
- `forge.settings.Settings` reads `GEMINI_API_KEY`; `.env` is now found by searching up from
  the **current working directory** (previously from `app.py`'s directory — same result when
  started from the repo root, as Render, Docker and the docs do).
- `forge.legacy.enhance` holds the FORGE 1.x prompt, config, builder and cleaner (moved
  verbatim) plus `LegacyEnhancer`, which creates the Google GenAI client on first use.
- `forge.api.health` (`/health`) and `forge.api.legacy` (`/`, `/enhance`) blueprints.
- Root `app.py` is a compatibility shim: `app = create_app()`, re-exports
  `GEMMA_MODEL`, `LLM_CONFIG`, `build_forge_prompt`, `_clean_output`, `enhance_prompt`, and a
  lazy module attribute `client`. If the package is not installed (Render's
  `pip install -r requirements.txt`), it adds `src/` to `sys.path`.
- `templates/index.html` moved to `src/forge/templates/index.html` (pure rename, 0 lines
  changed) so it ships as package data.
- `requirements-dev.txt` adds `-e .`; `scripts/verify_environment.py` template path updated.
- New `tests/test_package.py` (16 tests).

**Intentional behavior change (documented incompatibility):** with no `GEMINI_API_KEY`, the
app now starts and `/health` returns 200; `/enhance` then returns the existing error shapes
(500 JSON with `success: false`, or an SSE `error` frame) with the message
`GEMINI_API_KEY is not set…`. Previously the process failed to start. With a key set,
behavior is unchanged (verified byte-for-byte below).

**Not done in this increment (deliberately):** logging/request IDs (moved to increment 3),
provider abstraction, database, removal of `confidence`/`score`, dependency removals,
Dockerfile/Compose/CI changes, README/docs path updates (increment 8).

**Verification (all actually run)**

| Check | Result |
|---|---|
| `python -m pytest -v` (global Py 3.11.0) | 27 passed, 1 skipped |
| Same in a clean venv after `pip install -r requirements-dev.txt` (editable install) | 27 passed, 1 skipped |
| Skipped test | `test_gunicorn_loads_app_app` — `gunicorn.util` imports `fcntl`, unavailable on Windows; runs on Linux CI |
| `git diff -- tests/test_app.py tests/conftest.py` | empty — the 12 original tests pass unmodified |
| `ruff check .` (ruff 0.3.5 global, latest ruff in clean venv) | All checks passed |
| `ruff format --check src tests/test_package.py app.py` | 11 files already formatted |
| Render simulation: fresh venv, `pip install -r requirements.txt` only, import `app:app` from repo root | package not installed → shim fallback used; `/health` 200, `/` 200 (89,863 bytes), GenAI client not created |
| Wheel build (`pip wheel .`) | contains `forge/templates/index.html`; installed wheel serves `/` and `/health` with 200 |
| Original `app.py` (HEAD) vs new module, runtime comparison | `GEMMA_MODEL`, system prompt, `LLM_CONFIG`, `build_forge_prompt`, `_clean_output` identical |
| Original vs new app, 12 HTTP cases with the same scripted fake stream | status, content type and body bytes identical for `/`, `/health`, `/enhance` (400 ×3, SSE ok ×2, JSON ok, SSE error, JSON 500), 405, 404 |

**Not verified**

- Docker image build/run (Docker daemon not running). The Dockerfile is unchanged; the
  image copies `src/` and relies on the shim fallback, the same path verified above in a venv.
- Python 3.10 and 3.12 (not installed locally; covered by the CI matrix once pushed).
- Real Gunicorn process start (Windows-incompatible); covered by the Linux-only test above.
- Any real model call (none made, by design).

### Increment 2 — provider abstraction layer (completed 2026-10-12, uncommitted)

**What changed**

- New `src/forge/providers/`: `base.py` (types, `ProviderAdapter` protocol), `errors.py`
  (10 categories, safe messages), `retry.py` (`RetryPolicy`, `Retry-After` parsing),
  `config.py` (pydantic-validated JSON config), `default_providers.json` (packaged default),
  `router.py` (`ProviderRouter`: profiles, capability checks, retries, per-provider
  concurrency), `google_genai.py`, `openai_compatible.py` (httpx), `fake.py`.
- `legacy/enhance.py` is now provider-independent: same system prompt, prompt builder,
  cleaner, parameters (`LEGACY_PARAMS`) and response dicts; calls `ProviderRouter`. The
  non-streaming path still aggregates the stream and cleans once at the end (as before).
- `/enhance` streams through `contextlib.closing`, so a client disconnect closes the provider
  stream and frees its concurrency slot. `/health` reports the default profile's model ID.
- `Settings` gains `providers_file` (`FORGE_PROVIDERS_FILE`) and an environment snapshot
  (excluded from `repr`) used only for credential lookup by variable name.
- Root `app.py`: `GEMMA_MODEL` now comes from the default profile; `client` returns the
  default Google adapter's lazily created client; `LLM_CONFIG` is no longer exported (the
  Google adapter builds an equal config — see verification).
- `requirements.txt`: `pydantic>=2,<3` declared (already installed via google-genai).
  `.env.example`: `FORGE_PROVIDERS_FILE`, `GROQ_API_KEY` placeholders (commented).
- `config/providers.example.json`: Gemini, Groq, Ollama, llama.cpp; model IDs other than the
  Gemini default are explicit placeholders (not verified against any catalog).

**Compatibility deviations (intentional, documented)**

1. Error text: `/enhance` error responses carry a fixed safe message per error category
   instead of the raw exception string (ADR-010). Status codes, JSON keys and SSE frame shape
   are unchanged. Three assertions in original `tests/test_app.py` that required raw text
   were changed accordingly (diff limited to those assertions).
2. Retries: transient upstream failures (rate limit ≤ 20 s `Retry-After`, 5xx, timeouts,
   connection errors) are now retried up to 2 times with backoff before an error is returned;
   previously they failed immediately.
3. Timeout: Gemini calls now have a 60 s per-request timeout (previously unbounded apart
   from Gunicorn's 120 s worker timeout).
4. `app.LLM_CONFIG` removed from the root module (no route or test used it).

**Not done (deliberately, per Step 2 scope):** database, cache, budgets, benchmark, real
provider calls, `confidence`/`score` removal, JSON-export fix, structured logging and
request IDs, `groq` SDK removal, Docker/Compose/CI changes.

**Verification (all actually run, 2026-10-12)**

| Check | Result |
|---|---|
| `python -m pytest -q` (global Py 3.11.0) | **249 passed, 1 skipped** |
| Same in a fresh venv from `requirements-dev.txt` (editable install; google-genai 1.2.0, httpx 0.27.0, pydantic 2.14.1, ruff 0.17.0) | **249 passed, 1 skipped** |
| Skipped | `test_gunicorn_loads_app_app` — needs `fcntl` (POSIX); the real Gunicorn was verified in Docker instead (below) |
| Tests per file | `test_app.py` 12 (original), `test_package.py` 17, `test_enhance_providers.py` 24, `providers/test_config.py` 21, `test_errors_and_retry.py` 39, `test_google_genai.py` 38, `test_openai_compatible.py` 67, `test_router.py` 32 |
| `ruff check .` (0.3.5 and 0.17.0) | All checks passed |
| `ruff format --check` on new/changed source and new tests (both versions) | 28 files already formatted |
| `mypy src/forge --ignore-missing-imports --check-untyped-defs` (1.9.0; extra check) | Success: no issues in 18 source files |
| HEAD `app.py` vs new app, same scripted Gemini stream, 12 HTTP cases | 10 byte-identical (`/`, `/health`, 400 ×3, SSE success ×2, JSON success, 405, 404); 2 differ only in error message text (same status, keys, frame shape) |
| Gemini request equivalence | `build_config(build_request(x)).model_dump()` equals the original `LLM_CONFIG`; contents is the same plain prompt string; model `gemma-4-31b-it` |
| Render path: fresh venv, `pip install -r requirements.txt` only, no `GEMINI_API_KEY` | `/health` 200, `/` 200, no adapter created |
| Wheel | includes all `forge/providers/*.py` and `default_providers.json`; installed wheel (outside repo) serves `/health` 200, `/` 200, `/enhance` 500 with the missing-key message |
| Docker: `docker build` with the **unchanged** Dockerfile, run with no env vars | build OK; Gunicorn 22.0.0 started 2 gthread workers on Linux; `/health` 200; `/` 200 (89,863 bytes); `/enhance` JSON 500 / SSE error frame with missing-key message; `gunicorn.util.import_app("app:app")` → Flask app; `.env` absent from image; container health check reported `healthy`. Test container and image removed afterwards. |
| Real model calls | **None made.** All provider tests use the fake adapter, a stubbed Google SDK, or `httpx.MockTransport`. |
| Credential exposure review | no real-key-shaped strings in changed/new files; config validation and adapter errors tested to not echo secrets; `Settings` repr excludes the environment |

**Known limitations**

- OpenAI-compatible adapter: verified only against mocked HTTP. Groq, Ollama and llama.cpp
  have **not** been called.
- Google adapter: verified against a stubbed SDK only; real `gemma-4-31b-it` availability is
  unverified.
- Concurrency limits are per process (ADR-014).
- The SSE streaming path is still not cleaned (preserved behavior, ADR-015).
- Retry warnings go through the standard `logging` module without structured fields or
  request IDs (increment 3).
- Observation (not changed, Docker config out of scope): `.dockerignore` does not exclude
  `.mypy_cache/` and `.ruff_cache/`, so they are copied into the image.
- Python 3.10 and 3.12 not run locally (CI matrix covers them once pushed).

**Exact remaining work for increment 3**

1. ADR-009: remove `confidence` and `score` from `/enhance` success and error bodies —
   **needs owner confirmation**; update `test_app.py` assertions on `"98%"` accordingly.
2. Fix UI "Copy as JSON" to export the enhanced prompt instead of the fake metadata
   (`src/forge/templates/index.html` `defaultMeta` / `latestOutputData`).
3. `src/forge/logging.py`: JSON log formatter, `FORGE_LOG_LEVEL`, prompts/outputs not logged
   by default; route the router's retry warnings through it.
4. `X-Request-ID`: accept a well-formed client value or generate one; return it on every
   response; include it in logs.
5. `CHANGELOG.md` and `docs/api.md` describing the error-message change (Step 2) and the
   field removal (Step 3).

### Step 2 review (2026-10-12, before increment 3)

Focused review of the increment 2 diff. No architectural defect found. Changes made:

| Finding | Severity | Action |
|---|---|---|
| `iter_lines` rescanned the remaining buffer per line: O(n·k) for a chunk with k lines (measured 0.67 s for 50k lines in one chunk vs 0.012 s after) | Defect (performance / robustness against a broken upstream) | Rewritten as a single linear regex scan resuming at the new data; regression tests added for many lines per chunk and CRLF split after consumed lines |
| Gemini `generate()` read `response.text` outside the `try`; the real SDK raises `ValueError` for non-text parts, which escaped the adapter (router wrapped it) | Minor contract defect | Moved inside the `try`; covered by an SDK-level test |
| All Gemini tests stubbed the SDK's `models` object, so the real SDK request/stream/error paths were unverified | Coverage gap | Added `tests/providers/test_google_genai_sdk.py` (18 tests) driving the real google-genai 1.2.0 code with `requests.Session.request` intercepted: the adapter's wire request (URL, body) equals the original FORGE 1.x call except the new 60 s timeout; SSE parsing, usage, `RetryInfo`, `Retry-After`, `API_KEY_INVALID`, HTML 500 and transport errors all classify correctly |
| `HttpOptions(timeout=…)` might override the SDK's default base URL/API version | Assumption | Verified: `base_url` `https://generativelanguage.googleapis.com/`, `api_version` `v1beta` preserved |
| No total deadline across retries (worst case ≈ 3 × 60 s per-read timeout + backoff) | Limitation | Documented, not changed (previously a hung upstream had no bound at all) |

Re-verified after fixes: 269 passed, 1 skipped; ruff; mypy clean.

### Increment 3 — fake-metric deprecation, JSON export fix, logging, request IDs (completed 2026-10-12, uncommitted)

**What changed**

- `/enhance`: `confidence` and `score` are `null` in success and error bodies (previously
  `"98%"`/`0.98` and `"N/A"`/`0`). Keys kept for one release (ADR-009 revised). Other legacy
  labels unchanged, documented as deprecated.
- Consumer inventory: bundled UI never read these fields from the server; only its own
  client-side `defaultMeta` constant used them. No other in-repo consumer; external unknown.
- UI (`src/forge/templates/index.html`): removed the `defaultMeta` constant and the two
  places it was passed to `renderOutput`; "Copy as JSON" now falls through to the existing
  `{"enhanced_prompt": latestOutput}` export. 2 lines added, 5 removed; nothing else in the
  template changed.
- New `src/forge/logging.py`: JSON formatter, request-ID filter, idempotent
  `configure_logging` (only the `forge` logger, `propagate=False`), `X-Request-ID`
  assignment/echo with validation, `request.completed` event.
- `legacy/enhance.py` logs `enhance.failed` (category, provider, status_code) and
  `enhance.internal_error`; the router's retry message is now a structured
  `provider.retry` event. `Settings.log_level` from `FORGE_LOG_LEVEL` (validated).
- Docs: new `CHANGELOG.md`; `docs/api.md` rewritten to the actual contract; README response
  line; `.env.example` (`FORGE_LOG_LEVEL`); ADR-009 status; target-architecture §3/§8.

**API compatibility decisions**

| Item | Decision |
|---|---|
| `confidence`, `score` | Kept, value `null`, deprecated; removal planned for the following release |
| `template_id`, `template_name`, `template_matched`, `domain`, `templates_loaded` | Values unchanged; documented as deprecated static labels |
| Request schema, SSE event names/payload shape, status codes | Unchanged |
| `X-Request-ID` | New response header only; bodies unchanged |
| Original tests | `tests/test_app.py`: two `confidence == "98%"` assertions now assert `confidence`/`score` are `None` (deliberate contract change) |

**Verification (all actually run, 2026-10-12)**

| Check | Result |
|---|---|
| `python -m pytest -q` | **298 passed, 1 skipped** (skip: gunicorn loader needs `fcntl`) |
| UI export test (`tests/test_legacy_ui.py` → Node 24 runs the template's real inline script with a fake DOM and a streaming `fetch` stub) | Passes on the fixed template; **fails on the original HEAD template** with exactly the reported bug (exports `confidence: '98%'`, `score: 0.98`, … and no `enhanced_prompt`) |
| Real browser (built-in browser pane, real clicks) against the Docker container with a mounted *fake* provider config | Enhance rendered the output; "Copy → JSON" copied `{"enhanced_prompt": "Act as a senior data engineer.
Parse the CSV files robustly and report malformed rows."}` (captured by wrapping `navigator.clipboard.writeText`) |
| Docker (unchanged Dockerfile, real Gunicorn 22.0.0, fake provider) | `X-Request-ID` generated (32 hex), valid client ID echoed, invalid (`bad id;drop`) replaced; `/enhance` JSON has `confidence: null`, `score: null`; SSE frames unchanged; one JSON log line per request with matching `request_id`; prompt marker found in logs 0 times. Container and image removed afterwards |
| Request-ID / logging tests (`tests/test_observability.py`, 27) | IDs on 200/400/404/405/SSE, uniqueness, echo, rejection of malformed values, ID in log lines, no prompt/output/secret in logs (stream and JSON), structured retry/failure events, level filtering, no duplicate handlers, root logger untouched, invalid `FORGE_LOG_LEVEL` rejected |
| `ruff check .` (0.3.5 and 0.17.0) | All checks passed |
| `ruff format --check` (new/changed source + new tests, both versions) | 32 files already formatted |
| `mypy src/forge --ignore-missing-imports --check-untyped-defs` | Success: no issues in 19 source files |
| Real model calls | None |

**Known limitations**

- The UI behavior test needs Node.js; without it, it is skipped (GitHub `ubuntu-latest`
  includes Node). It uses a minimal fake DOM, not a browser engine; the real-browser check
  above was a one-off manual verification, not part of CI.
- `request.completed.duration_ms` for streamed responses measures time to headers, not to
  the end of the stream.
- `enhance.internal_error` logs a traceback for unexpected bugs; tracebacks may contain
  exception text.
- Log lines go to stderr; no retention policy is defined yet (spec §26 — later step).
- `setMeta()` in the template is now an unused no-op (left to keep the template diff minimal).

**Remaining before Phase 0 acceptance:** increments 4 (PostgreSQL + Alembic), 5 (cache +
budgets), 6 (pilot benchmark), 7 (real-provider verification — needs owner permission),
8 (CI with PostgreSQL, docs, README).

### Cumulative review of Steps 1–3 (2026-10-12, before increment 4)

Scope: full diff since `131d0df` (staged + unstaged), docs vs implementation, provider
configuration, secrets, logging, packaging, deployment, and whether tests detect regressions.

**Git state.** The only staged change is the template rename, verified as a pure rename
(staged blob identical to `HEAD:templates/index.html`); all other changes are unstaged or
untracked. Template content change vs HEAD: +2/−5 (JSON-export fix). Package layout matches
§2 of the target architecture. Ignored artifacts: `.env` (owner's), `src/forge.egg-info/`.

**Findings and fixes**

| # | Finding | Action |
|---|---|---|
| 1 | `/enhance` with a non-object JSON body or non-string `prompt` crashed (`AttributeError`) → `500` HTML + traceback log. Inherited from FORGE 1.x and preserved by Steps 1–3 | Fixed: `400` JSON with a new documented message; `null`/falsy bodies keep the original "Empty prompt" `400`; `stream` truthiness left unchanged and documented. 14 tests added |
| 2 | The route's explicit stream close was not distinguishable from CPython refcount GC in tests (mutation survived) | Test added that holds a reference to the enhancer stream, so only an explicit close passes |
| 3 | No guard against `docs/api.md` drifting from code | `tests/test_api_docs.py`: error-message table, request-ID pattern, 400 messages, success/error/health bodies checked against the running app |
| 4 | README: static "Tests Passing (12/12)" badge (false since Step 1) and project tree listing the removed `templates/`; `docs/architecture.md` pointed at the old template path | Badge replaced with the live CI badge; tree and path updated |
| 5 | `scripts/verify_environment.py` printed 8 characters of `GEMINI_API_KEY` (pre-existing) | Prints only "configured (N characters)" |
| 6 | `requirements.txt` had mixed CRLF/LF line endings after Step 2's append | Normalized (git normalizes to LF on commit either way). Correction: an earlier session message claimed all working files were CRLF; byte-level check shows 39 changed/new files LF, 10 CRLF — irrelevant to committed content under `core.autocrlf=true` |
| 7 | `ruff 0.3.5` flagged UP038 on the new validation line | Rewritten; clean on 0.3.5 and 0.17.0 |

Confirmed without changes: docs/api.md matches the implementation for SSE errors, request
IDs, and deprecated fields (mechanical comparison, now a test); unhandled exceptions still
return a generic 500 with `X-Request-ID`, and Flask's own exception log (`forge.app`) is
emitted as JSON with the request ID and no request content; provider config never echoes
values; `Settings` repr excludes the environment.

**Mutation check** (one injected regression at a time; source restored and diffed after):
14/14 caught — stream retry after output, slot release, retrying permanent errors,
unbounded `Retry-After`, raw upstream text to clients, permissive `X-Request-ID`, CRLF split,
incomplete stream accepted, Gemini `API_KEY_INVALID`, config echoing input, fabricated
confidence, UI exporting fabricated metadata, type-invalid prompt, route not closing stream.
(Before the fixes above: 12/14.)

**Reproduced verification**

| Check | Result |
|---|---|
| `pytest` (Windows, Py 3.11.0, global and clean venv) | **318 passed, 1 skipped** (gunicorn loader: needs `fcntl`) |
| CI commands in Docker `python:3.10-slim`, `3.11-slim`, `3.12-slim` (`pip install -r requirements-dev.txt`, `ruff check .`, `pytest`), `.env` removed from the copy | each **318 passed, 1 skipped**; on Linux the gunicorn loader test runs and passes; skip = UI test (no Node in those images) |
| UI export harness in `node:18-slim` and `node:24-slim` | PASS on both |
| `ruff check` / `ruff format --check` (0.3.5 and 0.17.0) | clean / 33 files formatted |
| `mypy src/forge --ignore-missing-imports --check-untyped-defs` | no issues in 19 files |
| Docker image (unchanged Dockerfile), Render-style run (no key, no providers file) | build OK; `/health` 200; `/` 200; `/enhance` configuration error (JSON 500 / SSE frame); type-invalid prompt 400; `X-Request-ID` on 200/404; `.env` absent; `import_app("app:app")` OK; 9/9 log lines JSON; prompt markers in logs: 0; health check `healthy`. Test containers/images and pulled base images removed |
| Render path (fresh venv, `requirements.txt` only) | `/health` 200 with `X-Request-ID`, `/` 200 |
| Wheel | 21 package files incl. `logging.py`, `default_providers.json`, template; no tests |
| HEAD vs current, 12 HTTP cases | 9 identical; 3 intended differences: JSON success differs only in `confidence`/`score` (`"98%"`/`0.98` → `null`), and the two error cases (safe messages) |

**Not reproducible here / not verified**

- Real model calls (none made, by instruction).
- GitHub Actions itself was not run (no push); its commands were reproduced in containers.
- The real-browser JSON-export check from increment 3 was not repeated (the Node harness,
  which fails on the original template, is the reproducible check).

**Remaining limitations (unchanged scope):** no request-body size limit
(`FORGE_MAX_REQUEST_BYTES` is planned but unassigned to a step); no total deadline across
retries; per-process concurrency limits; streamed output not cleaned; old docs
(`docs/setup.md`, `docs/deployment.md`, `docs/architecture.md` body, README architecture
section) still describe FORGE 1.x in places — scheduled for increment 8.

### Increment 4 — PostgreSQL and Alembic (completed 2026-10-12, uncommitted)

**What changed**

- Dependencies (`requirements.txt`): `SQLAlchemy>=2.0,<2.2`, `alembic>=1.13,<2`,
  `psycopg[binary]>=3.1,<4`.
- `src/forge/db/`: `config.py` (validated `DATABASE_*` settings; only PostgreSQL schemes;
  errors and `repr` never contain the URL/password), `models.py` (4 tables, naming
  convention, CHECK/UNIQUE/FK constraints, `ON DELETE RESTRICT` everywhere), `session.py`
  (lazy engine, `session()` unit of work with commit/rollback/close, `readiness()`),
  `migrate.py` (Alembic without `alembic.ini`), `repositories.py` (workspace get-or-create via
  `ON CONFLICT DO NOTHING`, create/get run), `migrations/` (`env.py`, template, revision
  `0001_initial_schema`). `alembic.ini` at the repo root for the CLI (no URL inside).
- `Settings.database`; `create_app(..., database=)`; `/ready` (ADR-017);
  `DatabaseUnavailableError` with a fixed safe message.
- `docker-compose.yml`: `db` service (`postgres:17`, volume `forge_pgdata`, `pg_isready`
  health check, `127.0.0.1:5433`); `forge` gets `DATABASE_URL` and waits for `db` healthy.
- CI: `postgres:17` service; migration step (upgrade, current, repeat, check); tests with
  `TEST_DATABASE_URL` and `FORGE_REQUIRE_DB_TESTS=1`.
- Packaging: migrations included as package data.
- Docs: `docs/implementation/database.md` (new), `docs/api.md` (`/ready`), `.env.example`,
  target architecture §2/§3/§6/§9, ADR-002 status, ADR-016, ADR-017, current-state
  correction (a native PostgreSQL 18 on 5432 exists), `CHANGELOG.md`.

**Scope decisions**

- `llm_cache_entries` is **not** created: the plan assigns the cache and its tests to
  increment 5, which will add it as revision `0002`.
- `executions` gained `role` (spec §8 logical roles) and `sample_index` (spec §14 repeated
  samples) beyond the §6 sketch, because slot uniqueness `(run, case, system, role, sample)`
  needs them; `finish_reason` keeps the provider-reported value.
- No request-scoped session: routes do not persist anything yet, and explicit short sessions
  avoid holding transactions during model calls or SSE streams.

**Defects found and fixed during the increment**

1. The draft migration's CHECK constraint names were prefixed twice
   (`ck_executions_ck_executions_...`) because Alembic applies the naming convention to names
   inside migrations. `alembic check` does **not** detect this; the catalog-comparison test
   did. Fixed with `op.f()`.
2. A readiness test assumed a wrong password is always rejected; the `postgres` image trusts
   loopback connections, so it passed on Windows (port-forwarded) but failed in the CI
   reproduction. It now uses a nonexistent role.
3. mypy 1.9.0 (global) crashes inside SQLAlchemy 2.1's Oracle dialect; type checking was run
   with mypy 2.4.0 instead.

**Verification (all actually run, 2026-10-12)**

| Check | Result |
|---|---|
| `docker compose config --quiet` | valid (`--quiet` so `.env` values are never printed) |
| `docker compose up -d db` | `postgres:17` healthy on `127.0.0.1:5433` |
| Clean migration of the empty local `forge` DB via CLI | `current` empty → `upgrade head` → `0001 (head)`; second `upgrade head` ran nothing; `alembic check`: "No new upgrade operations detected" (done with the draft migration; see known issue) |
| `pytest` with PostgreSQL (Windows host: global Py 3.11 and clean venv in require mode) | **389 passed, 1 skipped** each (skip: gunicorn loader on Windows) |
| `pytest` without `TEST_DATABASE_URL` | 346 passed, 44 skipped with reason |
| `FORGE_REQUIRE_DB_TESTS=1` without URL | errors (cannot skip silently) |
| Database tests (70): config 23, migrations 6, models/constraints 28, session/readiness 13 | upgrade from empty, head recorded, repeat upgrade schema-identical, `alembic check`, migrated catalog == models incl. CHECKs, downgrade/upgrade round trip, CLI, JSONB/defaults/timestamps, uniqueness, FK + RESTRICT, 13 CHECK cases, rollback, pool release, no idle-in-transaction, persistence across engine restart, `/ready` states, no credential leakage |
| CI reproduction (`postgres:17` + `python:3.10/3.11/3.12-slim` sharing its network; workflow commands verbatim) | ruff clean; migrations: 1 upgrade, 0 on repeat, check clean; **388 passed, 1 skipped** each (run before the `/ready` docs test was added; skip: UI test, no Node) |
| Production image (unchanged Dockerfile) on the Compose network | `alembic current` → `0001 (head)`; Gunicorn `/health` 200, `/ready` 200 `ok`, `/` 200; unmigrated DB → 503 `migrations_pending`; password absent from logs |
| Render path (fresh venv, `requirements.txt` only, no `DATABASE_URL`) | `/health` 200, `/` 200, `/ready` 503 `not_configured` |
| Wheel installed outside the repo | contains `forge/db/**` incl. migrations; migrated a throwaway DB; `readiness()` → `ok` |
| `ruff check` / `ruff format --check` (0.3.5 and 0.17.0) | clean / 47 files formatted |
| `mypy src/forge` (2.4.0) | no issues in 27 source files |
| Hosted databases / real model calls | **none** |

All throwaway databases (`forge_test_*` and one probe DB) were dropped; the CI-reproduction
PostgreSQL container and verification images/containers were removed.

**Known issue (resolved 2026-10-12, see "Step 4 database reconciliation").** The local Compose `forge` database was migrated
with the *draft* `0001` before defect 1 was fixed: its 13 CHECK constraints have
doubled-prefix names (behaviour identical; 0 rows in every table). It was not reset, because
resets need explicit authorization. Fix when convenient:
`alembic downgrade base && alembic upgrade head` (or `docker compose down -v`).

**Limitations**

- No hosted database (Neon/Supabase) has been connected; `DATABASE_POOL_MODE=transaction`
  is unit-tested only.
- Concurrent `alembic upgrade` runs are not coordinated.
- `/ready` uses one pooled connection per call and can take up to `DATABASE_CONNECT_TIMEOUT`
  when the database is down.
- Connection limits are per process (workers × (pool size + overflow)).
- No privacy deletion path yet (history is `RESTRICT`-protected).
- The CI workflow change was reproduced locally but has not run on GitHub (nothing pushed).

### Step 4 database reconciliation (2026-10-12, owner-authorized)

**Inspection (read-only, `default_transaction_read_only=on`).** Target: container
`forge-db-1` (`postgres:17`, 17.11), published `127.0.0.1:5433`, volume
`forge_forge_pgdata`, database `forge`, user `forge`. Revision `0001`. Rows: 0 in
`workspaces`, `runs`, `executions`, `evaluations` (only the `alembic_version` row); no other
schemas, views, sequences or functions. 10/23 constraint names matched the models; all 13
CHECK constraints had the doubled prefix. `alembic check` passed despite this (it does not
compare constraint names). A full catalog snapshot was saved before any change.

**Authorized action.** Reset only the `forge` database's schema objects with
`alembic downgrade base` then `alembic upgrade head`, after a guarded pre-check that aborted
on any mismatch: resolved target `127.0.0.1:5433/forge` via the same `Settings.from_env()`
path as Alembic's `env.py`; server IP equal to the `forge-db-1` container IP
(`172.18.0.2:5432`); server version 17 (the native PostgreSQL is 18); database/user
`forge`; tables still empty; revision `0001`; constraint names unchanged since the snapshot.
Not used: `docker compose down -v`, volume deletion, dropping any database. The native
PostgreSQL on 5432 and hosted databases were not contacted.

**Result**

| Check | Result |
|---|---|
| Snapshot comparison (before vs after, names normalized) | exactly 13 constraints renamed (doubled prefix removed); constraint definitions, kinds and tables identical; columns (43), indexes (10), `alembic_version` identical |
| Constraint names vs corrected models | 23/23 match; none missing or unexpected |
| Table contents | still 0 rows in all four tables |
| `alembic current` / `alembic check` | `0001 (head)` / "No new upgrade operations detected" |
| `/ready` | 200 `{"status": "ready", "checks": {"database": "ok"}}` |
| Database integration tests (`tests/db`, run on a separate ephemeral `postgres:17` on `127.0.0.1:55433`, removed afterwards, so no other database on the project server was created or dropped) | 70 passed |
| Full suite (same ephemeral server, `FORGE_REQUIRE_DB_TESTS=1`) | 389 passed, 1 skipped (gunicorn loader on Windows) |
| ruff / format | clean / 47 files formatted |
| mypy 2.4.0 | no issues in 27 source files |
| Databases on the project server afterwards | `forge, postgres, template0, template1` (unchanged) |

Unresolved: none.

### Cumulative review of Steps 1–4 (2026-10-12, read-only checkpoint preparation)

Git at review time: branch `main`, HEAD `131d0df` (= `origin/main`); staged: only the
template rename; 13 tracked files modified (unstaged); 60 untracked files; no commits made.

**Findings**

| Severity | Finding | Action |
|---|---|---|
| High | The test-database guard checked only the host: `TEST_DATABASE_URL=…@127.0.0.1:5432/…` (the native PostgreSQL 18 on this machine) or a URL without a port was accepted, so the fixtures could have created/dropped databases there. The Step 4 claim that this was impossible was wrong. | **Fixed:** `tests/db/safety.py` refuses port 5432 (and port-less URLs) before connecting, keeps the local-host rule, and refuses servers holding databases other than `postgres`, `template0/1`, `forge`, `forge_test_*` (read-only inventory). CI's PostgreSQL service moved to 5433. 15 regression tests in `tests/db/test_safety.py`; a run pointed at `127.0.0.1:5432` under a socket guard was refused with **0 connection attempts** to port 5432. |
| Medium | The test session loads the developer's `.env` (via the root `app` import), so real credentials such as `GROQ_API_KEY` are present in the test process environment. | Not changed (loading `.env` is also how `TEST_DATABASE_URL` reaches tests). Verified that no test reaches the network: full suite under a socket guard blocking non-loopback DNS/connections → **0 attempts**. Recommendation for increment 8: a permanent network guard in the test suite and a hermetic test environment. |
| Low | `target-architecture.md` listed a `cli.py` "(doctor, db, benchmark)" and a `forge db upgrade` command that do not exist. | Fixed (marked as planned for increment 6; migrations use `alembic`). |
| Low | No test asserted that `/enhance` is independent of the database. | Regression test added (`test_enhance_does_not_depend_on_the_database`). |
| Low | README, `docs/setup.md`, `docs/deployment.md` do not mention the database or `/ready`. | Deferred to increment 8 (`docs/implementation/database.md` covers it). |
| Low | CI runs ruff check and pytest but not `ruff format --check` or mypy; `requirements-dev.txt` has no mypy; the globally installed mypy 1.9.0 crashes on SQLAlchemy 2.1 (mypy 2.4.0 is clean). | Deferred to increment 8. |
| Info | Tests that spawn subprocesses (root import, Alembic CLI) run outside the in-process network guard; neither calls a model. | Noted. |

Verified unchanged: Step 1 entry points (`gunicorn app:app`, `python app.py`, Render
install, wheel); Step 2 provider behaviour (mutation-checked in the Steps 1–3 review); Step 3
contracts (docs-drift tests); Step 4 schema (migration uses `op.f()` for all 27 names; local
`forge` DB: 23/23 names, 0 rows, `0001 (head)`, `alembic check` clean, `/ready` 200 — read-only).

**Verification**

| Check | Result |
|---|---|
| Full suite, DB tests required (ephemeral `postgres:17` on 127.0.0.1:55433), external network + port 5432 blocked | PASS — 405 passed, 1 skipped (gunicorn loader, Windows); 0 blocked attempts |
| Same in a clean venv (latest resolved dependencies) | PASS — 405 passed, 1 skipped |
| Without `TEST_DATABASE_URL` | PASS — 362 passed, 44 skipped with reason |
| Updated CI workflow reproduced (PostgreSQL on 5433; Python 3.10/3.11/3.12) | PASS — ruff ok; `0001 (head)`; 0 repeat upgrades; check clean; 405 passed, 1 skipped (UI test: no Node in image) each |
| ruff check / format (0.3.5 and 0.17.0) | PASS — 49 files formatted |
| mypy 2.4.0 | PASS — no issues in 27 files; mypy 1.9.0: internal error (tooling) |
| Alembic on local `forge` DB (read-only session) | PASS — `0001 (head)`, no differences |
| Docker image (unchanged Dockerfile), Gunicorn on the Compose network | PASS — `/health` 200 + `X-Request-ID`, `/ready` 200, `/` 200, `/enhance` documented errors, 400 for invalid input, 9/9 JSON log lines, no password/prompt in logs, health check `healthy` |
| `python app.py` (in a container) | PASS — `/health` 200, `/ready` 200 |
| Render path (fresh venv, `requirements.txt` only) | PASS — `/health` 200, `/` 200, `/ready` 503 `not_configured` |
| Wheel | PASS — 30 package files incl. 3 migration files, template, default config; no tests |
| UI export test (Node 24, local) | PASS (part of the suite); Node 18 last verified in the Steps 1–3 review |
| GitHub Actions on GitHub | NOT RUN (nothing pushed) |
| Real providers, hosted databases | NOT RUN (by instruction) |

Ephemeral PostgreSQL servers and review images/containers were removed. The project server
still holds only `forge, postgres, template0, template1`; no destructive migration ran.

### Increment 5 — response cache and per-run budgets (completed 2026-10-13, committed `d101e71`)

Base: local commit `eb126f0`. Owner decisions taken before coding (ADR-018, ADR-019): every
provider attempt counts against `max_model_calls`; token budgets reserve then reconcile;
cache is opt-in for run executions only with a 30-day default TTL; cache store failures fail
open, budget reservation fails closed.

**What changed**

- `src/forge/infrastructure/cache.py`: canonical key (`CACHE_KEY_VERSION`), `CachePolicy`,
  `MemoryCacheStore`, `PostgresCacheStore` (first valid writer wins, DB-clock expiry,
  `purge_expired`, fail-open), `postgres_cache_policy`.
- `src/forge/infrastructure/budgets.py`: `BudgetLimits` (strict, `max_model_calls`
  required), `check_plan`/`RunPlan`/`BudgetEstimate`, token estimate, `MemoryRunBudget`,
  `PostgresRunBudget` (single conditional `UPDATE` reservation), error types with stable
  codes (`budget_exceeded`, `run_not_active`, `budget_confirmation_required`,
  `invalid_budget`).
- Provider contract: `GenerationResult.cache_hit`; `ProviderAdapter.cache_identity()`
  implemented by the Google, OpenAI-compatible and fake adapters.
- `ProviderRouter.generate(..., budget=, cache=)` and `stream(..., budget=)`; both optional,
  so `/enhance` is unchanged.
- `Settings.cache_ttl_seconds` (`FORGE_CACHE_TTL_SECONDS`, validated).
- `repositories.create_run` validates budgets and requires `max_model_calls`.
- Models + Alembic `0002_cache_and_budgets` (`0001` untouched).
- Docs: target architecture §5 (rewritten as implemented), ADR-007/008 status, ADR-018,
  ADR-019, database guide (schema + 0002 upgrade/rollback), `docs/api.md` (one sentence:
  `/enhance` never cached or budgeted), `.env.example`, `CHANGELOG.md`.

**Tests added (123)**: `tests/infrastructure/test_cache_key.py` (51),
`test_router_cache.py` (13), `test_budgets.py` (38), `tests/db/test_cache_and_budgets.py`
(21). Existing tests updated: migration head `0001` → `0002` (3 assertions) and the
`test_models.py` run fixture now passes `budget_limits` (required).

**Verification (all actually run, 2026-10-13)**

| Check | Result |
|---|---|
| Full suite, DB tests required (ephemeral `postgres:17`, 127.0.0.1:55433), external network + port 5432 blocked | PASS — 528 passed, 1 skipped (gunicorn loader, Windows); 0 blocked attempts (re-run after the local DB upgrade: same) |
| Same in a clean venv | PASS — 528 passed, 1 skipped |
| Without `TEST_DATABASE_URL` | PASS — 466 passed, 63 skipped with reason |
| Mutation check (7 injected Step 5 regressions: reservation ignoring the call limit, expired entries served, valid entries overwritten, namespace dropped from key, cache hits charged, stream reservations never settled, failures cached) | 7/7 caught; source restored byte-identical |
| Alembic: `0001` → `0002` with existing data, repeat upgrade, `alembic check`, catalog == models incl. CHECKs, downgrade to `0001` (data kept) and back, full base↔head round trip | PASS (tests) |
| CI reproduction (`postgres:17` on 5433; Python 3.10/3.11/3.12; workflow commands verbatim) | PASS — `0002 (head)`, 0 repeat upgrades, check clean, 528 passed, 1 skipped (UI test: no Node) each |
| ruff (0.3.5 and 0.17.0) | `ruff check .` (the CI lint step) PASS repo-wide; `ruff format --check` PASS for all 19 changed/new Step 5 Python files. Repo-wide format check is not clean: 3 pre-existing files untouched by Step 5 (`scripts/verify_environment.py`, `tests/conftest.py`, `tests/test_app.py`, identical to `eb126f0`) would be reformatted; CI does not run a format check |
| mypy 2.4.0 | PASS — no issues in 31 source files (one variable-reuse type error found and fixed) |
| Docker image (unchanged Dockerfile), Gunicorn against a throwaway DB at `0002` | PASS — `/health` 200, `/` 200, `/ready` 200 `ok`, `alembic current` `0002 (head)` |
| Persistent local `forge` DB (owner-approved upgrade, 2026-10-13) | PASS — target positively identified before connecting (127.0.0.1:5433, db `forge`, PostgreSQL 17.11, same `system_identifier` as container `forge-db-1`), at `0001` with the expected schema and 0 rows in every table; `alembic upgrade head` ran `0001 -> 0002` only; `alembic current` `0002 (head)`; repeat upgrade ran 0 migrations; `alembic check` clean; live catalog == ORM `create_all` (53 columns, 31 constraints incl. CHECK definitions, 11 indexes); row counts unchanged (all 0); real HTTP `/ready` 200 `{"database": "ok"}`, `/health` 200, `/` 200. No downgrade, reset or drop |
| Real providers, hosted databases | NOT RUN |

**Limitations**

- No single-flight: concurrent misses for the same key each call the provider (each charged).
- A crash between reservation and settlement leaves tokens reserved (conservative); no
  automatic reconciliation until the job system (Phase 2).
- Token estimates use a chars/4 heuristic; there is no tokenizer and no cost estimation
  (no pricing configuration; costs are never fabricated).
- Budget errors have stable codes but no HTTP mapping yet (no run endpoint exists).
- Expired cache rows are only removed by an explicit `purge_expired()` call.
- `RunPlan`/`check_plan` are not yet called by anything: the runner arrives in increment 6.
- Repeated samples of an identical request share one cache entry; the runner must put the
  sample index in the cache namespace when samples must be independent (increment 6).
- Outstanding token reservations count against the budget, so with parallel workers a token
  budget can be declared exhausted although actual usage would have fit (conservative).

### Increment 5 — acceptance audit (2026-10-13, committed `d101e71`)

Read-only review of the actual Step 5 diff against spec §19, ADR-018 and ADR-019, then fixes
with regression tests for the defects found. Each new database test was shown to fail on the
pre-audit code (the source was restored byte-identical afterwards).

| # | Severity | Finding | Fix |
|---|---|---|---|
| 1 | Medium | `router.generate` stored *any* returned result, including empty text (e.g. a Gemini prompt block with no candidates) and abnormal finish reasons (`SAFETY`, `RECITATION`, `content_filter`, …), replaying them for the TTL as hits — contrary to "only complete, successful results" | `cache.is_cacheable` (non-empty text and finish reason `stop`/`length`/`max_tokens` or none); others are returned but not stored (`cache.not_stored`). 13 tests |
| 2 | Low | `PostgresCacheStore.get` parsed rows outside its fail-open handler: a malformed entry raised `KeyError` out of `router.generate` instead of being a miss | `CachedResponse.from_json` validates types; invalid entries are a logged miss (`cache.invalid_entry`). 5 tests |
| 3 | Low | `PostgresRunBudget.reserve`: when the conditional `UPDATE` failed, the locked fallback assumed `tokens` without re-checking, so a settlement committed in between could get a run that still had budget marked `budget_exceeded` (permanent) | Re-check both limits under `FOR UPDATE`; reserve if it fits. 2 tests |
| 4 | Coverage | No test asserted that cache logs and stored rows exclude prompts, responses, namespace values and the full key | 2 tests (router logs; PostgreSQL row) |
| 5 | Docs | Stale `router.py` layout comment; "token counts are labelled" overstated (`runs.tokens_used` mixes provider and estimated counts); sampling, concurrency-dependent token exhaustion, cache hits on inactive runs and Memory/Postgres error-code difference undocumented | Target architecture §2/§5, ADR-018/019, CHANGELOG, database guide |

**Verification**

| Check | Result |
|---|---|
| Full suite, DB tests required, network + port-5432 guard (disposable PostgreSQL **18.6** cluster created with `initdb` in the scratch directory on 127.0.0.1:55433; Docker Desktop failed to start on the host) | PASS — 550 passed, 1 skipped (gunicorn loader, Windows); 0 blocked attempts |
| Without a database | PASS — 480 passed, 71 skipped with reason |
| New tests against pre-audit code | 6 of 6 defect tests fail (5 malformed-entry, 1 lock re-check) and the router storage tests fail 8 of 8; control test passes |
| `alembic upgrade 0001:0002 --sql` (offline) | Additive only: 1 CREATE TABLE, 1 CREATE INDEX, 4 ADD COLUMN, 3 ADD CONSTRAINT, version stamp |
| Disposable DB via CLI: empty → `0001` → `0002`; current; repeat; check | PASS — `0002 (head)`, 0 repeat migrations, no new operations |
| Real app over loopback HTTP (Werkzeug), disposable DB | empty / `0001`: `/ready` 503 `migrations_pending`; head: `/ready` 200 `ok`, `/health` 200, `/` 200 |
| ruff 0.3.5 and 0.17.0: `check .`; `format --check` on the 19 Step 5 Python files | PASS |
| mypy 2.4.0 (`src/forge --ignore-missing-imports --check-untyped-defs`) | PASS — no issues in 31 source files |
| Docker image / Gunicorn | NOT RUN — Docker Desktop failed to start on the host |
| Persistent local `forge` DB (in `forge-db-1`) | NOT RE-VERIFIED in the audit (Docker down); last verified `0002 (head)`, `alembic check` clean, catalog == ORM earlier on 2026-10-13. The audit changed no schema or model, so no further migration is needed |
| PostgreSQL 17 (CI version) after the audit fixes | NOT RUN — previous PostgreSQL 17 runs predate the fixes |
| GitHub Actions, real providers, hosted databases | NOT RUN |

### Increment 6 — pilot benchmark (implemented 2026-10-13, uncommitted)

Base: local commit `d101e71`. Protocol: [`docs/benchmark/pilot-protocol.md`](../benchmark/pilot-protocol.md);
decisions: ADR-020. No real model calls, no hosted database, no migration.

**What changed**

- `src/forge/benchmark/`: `dataset.py` (strict task schema; every check tied to a verbatim
  prompt phrase; task/dataset hashes), `checks.py` (L0 rules, `forge.l0` v1),
  `conditions.py` (B0, B1 generic rewrite, F-legacy via `forge.legacy.enhance`),
  `manifest.py`, `records.py` (record schema, aggregates with denominators), `runner.py`
  (router + Step 5 budget/cache; files + optional PostgreSQL; explicit failure semantics),
  `verify.py` (integrity, recomputation), `report.py`.
- `src/forge/cli.py`, `src/forge/__main__.py`; `pyproject.toml` `[project.scripts] forge`.
- `benchmarks/pilot-v0/`: `dataset.json`, `tasks.jsonl` (30 tasks, 50 checks),
  `offline-providers.json` (fake providers only), `README.md`.
- `.gitignore`: `benchmark-runs/` (default output directory).
- Docs: protocol, ADR-020, target architecture §2/§7, database guide note, feature status,
  CHANGELOG.

Deviations from the plan row: module names (`dataset`, `conditions`, `manifest`,
`records`, `verify`, `report` instead of `tasks`, `systems`, `manifests`, `reporting`);
F-legacy uses non-streaming generation and records failures (both written into every
manifest); no schema change was needed (existing `runs`/`executions`/`evaluations` hold
the manifest, every call and every evaluation).

**Tests added (124)**: `tests/benchmark/` — dataset 28, checks 38, conditions 8, runner 21,
verify 17, CLI 6; `tests/db/test_benchmark_db.py` 6 (PostgreSQL).

**Verification (all actually run, 2026-10-13)**

| Check | Result |
|---|---|
| Full suite, DB tests required, network + port-5432 guard, disposable **PostgreSQL 18.6** cluster (`initdb` in the scratch directory, 127.0.0.1:55433; identity checked first; removed afterwards) | PASS — 674 passed, 1 skipped (gunicorn loader, Windows); 0 blocked attempts; no test databases left |
| Without a database | PASS — 598 passed, 77 skipped with reason |
| Mutation check (10 injected regressions: incomplete run marked completed, evaluation recomputation skipped, fixture labelled as measurement, condition dropped from cache namespace, not-evaluated checks hidden from denominators, empty output passing upper bounds, cancellation ignored, requirement-in-prompt rule removed, B0 prompt normalized, cache hits counted as fresh calls) | 10/10 caught; sources restored byte-identical |
| Offline pilot via the CLI (fake providers): `run` then `verify --dataset` | completed, 90 records, valid and complete, evaluations recomputed — **synthetic** (identical fixture text for every condition) |
| ruff 0.3.5 and 0.17.0: `check .`; `format --check` on the 20 changed/new Python files | PASS |
| mypy 2.4.0 (`src/forge --ignore-missing-imports --check-untyped-defs`) | PASS — 42 source files |
| Pilot on a real model; PostgreSQL 17 / Docker / Gunicorn after Step 6; GitHub Actions | NOT RUN (no authorization for real calls; Docker unavailable) |

**Limitations**

- Results are INCONCLUSIVE by design; L0 checks do not measure quality, and upper-bound
  checks pass for any short answer. No judge, rubric, human or semantic scoring; no cost.
- Offline fixture outputs are identical for all conditions; they validate the harness only.
- Sequential execution; runs cannot be resumed (a stopped run is kept for audit and a new
  run is started). Cancellation takes effect between task × condition pairs.
- One sample per task; the cache namespace includes `sample_index` for future sampling.
- F-legacy's transport differs from `/enhance` (non-streaming); its request and cleanup do
  not.

### Increment 6 — acceptance fixes (2026-10-13, uncommitted)

Fixes for the seven findings of the Step 6 acceptance review. Production `/enhance`, the
legacy enhancer, providers, cache and budget code are unchanged.

| # | Finding | Fix |
|---|---|---|
| 1 | 0.1.0: six tasks fully passed by "ok"; several more by trivially structured answers | New dataset `benchmarks/pilot-v1` (`forge-pilot` 1.0.0; `pilot-v0` preserved byte for byte): 16 tasks revised (version 2) with prompt-grounded minimum/content requirements; test that no task is fully passed by a fixed list of trivial answers; optional `limited_reason` (excluded from "all checks passed" and paired counts, reported with its reason; none needed in 1.0.0; omitted from task hashes when unset, so 0.1.0 hashes are unchanged) |
| 2 | F-legacy cleanup described as what `/enhance` users get | Protocol, ADR-020, module docs and the manifest (`matches`, `user_facing_path`) now state that F-legacy matches `stream: false` only; the web UI streams uncleaned output. Tests tie F-legacy's cleanup to the JSON path and show the streaming path differs |
| 3 | "Fresh calls" counted executions, not attempts | Per-execution `attempts` from a budget-reservation meter (retries included; cache hits and refusals before dispatch 0) and `budget_tokens` (provider-reported vs estimated); summary separates condition results, executions, provider attempts, cache hits, refusals and token bases; run-level recorded vs budget-counted attempts; format-1 accounting reported as unavailable |
| 4 | `summary.md` could state a stale status | Summary written after the database step with the same status; rewritten if a later step downgrades the run; `summary.json` carries the status; `verify` checks both summaries against `run.json` |
| 5 | Double failure could leave `run.json` saying `completed` | Finalization order `run.json`=`finalizing` → database → summary → `run.json` terminal status; database corrected to `failed` after a late file failure; `consistent: false` and a log event when a correction fails; `verify --database` cross-checks the run row. No cross-store atomicity (documented) |
| 6 | Plan arithmetic "~30 × 3 systems ≈ 150 calls" | Corrected in §6 (90 condition results; 5 attempts per task on the normal path; 150 total; retries and cache; attempts ≠ billable requests) |
| 7 | Cache-hit execution rows kept original token counts as provider usage | Cache hits: `usage.source = "cache"` with no counts and the original usage in `replayed_usage`; database rows store no token counts (`usage_source = 'unknown'`, `cache_hit = true`) |

Record format 2 and summary format 2 (`summary_version`); format-1 runs are verified with the
frozen v1 aggregation (`forge.benchmark.legacy_formats`). The historical offline run made
with 0.1.0 still verifies as valid and complete against `pilot-v0` (its files unchanged) and
is rejected against `pilot-v1`.

**Verification (all actually run, 2026-10-13)**

| Check | Result |
|---|---|
| Full suite, DB tests required, network + port-5432 guard, disposable **PostgreSQL 18.6** cluster (fresh `initdb` in the scratch directory, 127.0.0.1:55433, identity checked, removed afterwards) | PASS — 722 passed, 1 skipped (gunicorn loader, Windows); 0 blocked attempts; no test databases left |
| Without a database | PASS — 641 passed, 82 skipped with reason |
| Benchmark verification tests for `pilot-v0` and `pilot-v1` (offline runs, format-1 compatibility, tampering) | PASS |
| Mutation check (16 injected regressions, including the 7 new: cache-hit usage counted, retries not counted, limited tasks counted, `completed` written before finalization, stale summary not corrected, `finalizing` accepted, database status ignored) | 16/16 caught; sources restored byte-identical |
| ruff 0.3.5 and 0.17.0 (`check .`, `format --check` on the 24 changed/new Python files); mypy 2.4.0 (43 files) | PASS |
| Real providers, PostgreSQL 17, Docker/Gunicorn, GitHub Actions | NOT RUN |

### Increment 7 — real-model pilot design (2026-10-13, uncommitted; no live run)

Base: local commit `60cf680`. Scope per the owner's Step 7 brief: design, minimal
infrastructure and offline validation only; no provider call of any kind.

**What changed**

- Protocol `docs/benchmark/step-7-experimental-protocol.md` (`forge-step7-pilot` 1.1.0):
  research question, primary outcome (blinded human task success 0–3, F-legacy vs B0),
  secondary outcomes, design controls, failure classification, rubric, statistical plan,
  provider facts with public sources, budget and fail-closed gates, privacy, procedure and
  decisions D1–D10.
- `src/forge/benchmark/experiment.py` (config + offline plan), `blinding.py` (export,
  ratings), `analysis.py` (paired analysis); CLI `plan`, `export-blind`, `analyze`;
  runner `pace_seconds`; CLI output encoding and file-error handling.
- `benchmarks/experiments/` (pilot and one-task smoke configs with
  `live_execution_approved: false` and every owner check unset, offline rehearsal, provider
  files), `benchmarks/evaluation/` (rubric, rater notes).
- Tests: `tests/benchmark/test_step7.py` (75 after the review fixes).

**Offline verification (2026-10-13)**: full suite without a database 668 passed, 82
skipped (network and port-5432 guard: 0 attempts); ruff (both versions) and mypy (46
files) pass; offline plan and fake-provider rehearsal as recorded in the protocol §9. No
database test was needed (no database code changed). Smoke test, live pilot and human
ratings: **NOT RUN**.

**Review fixes (2026-10-14, uncommitted; no live run).** A final review found that an
unknown price passed the cost check when the ceiling was 0, a missing token budget was not
a failure, analysis compared profile names but not providers/models, and the key was
written into the rater folder. Fixed: F1 fail-closed pricing (published price with source,
date, model and tier; unknown never free; ceiling checked against the enforced token
budget; nonzero Gemini prices refused because thought tokens are uncounted) with separate
owner checks for tier/billing, rate limits, data use and thinking, enforced by
`run --experiment` before credentials are read and re-checked by the runner; F2 token budget
required for real providers; F3 experiment identity recorded in the manifest and checked by
analysis together with dataset, conditions, profiles, providers, models and execution
mapping; F4 key written outside the rater folder; F5 protocol 1.1.0 with cited provider
facts. Offline fake-provider runs no longer load `.env`. Earlier test runs and rehearsals
did load `.env` into process memory through the app factory and CLI settings (never printed
or sent); the 2026-10-14 checks ran with a guard that blocks `.env` reads.

**Offline verification (2026-10-14)**, with the network/port-5432 guard and the `.env` guard
(0 network attempts, 0 `.env` reads): Step 7 tests 75 passed; benchmark tests 236 passed;
full suite without a database 716 passed, 82 skipped; ruff 0.3.5 and 0.17.0 (check and
format) and mypy (46 files) pass. Rehearsal: plan PASS → `run --experiment` completed (90
records, experiment identity in the manifest) → verify valid and complete → export-blind
(rater folder: `items.jsonl` and `rating-template.jsonl` only; key outside; key inside the
folder refused) → analyze refused without `--allow-synthetic`, then SYNTHETIC,
INCONCLUSIVE. Live and smoke configs: plan and run refused on exactly the owner checks; no
run directory created. `pilot-v0`/`pilot-v1` hashes and the historical Step 6 run unchanged.
Smoke test, live pilot and human ratings: **NOT RUN**.

**Cost-integrity fix (2026-10-14, uncommitted; no live run).** The staged-diff audit found
that a published price was resolved by model ID alone, so Gemini's zero price could be
applied to another provider exposing the same model name, and owner confirmations covered
only one provider. Fixed: prices are bound to the exact provider entry (name, type and, for
OpenAI-compatible providers, endpoint URL) and model, compared exactly; duplicate
provider/model prices are rejected; `accounts` holds one owner-confirmation entry per real
provider and every real provider needs its own. The protocol (§7) now states that the token
budget refuses the next call once exhausted but does not cap a call's provider-reported
usage, so the total can exceed the limit by the final call's excess and cost figures are
estimates, not hard caps. Budget implementation unchanged. Verification (guards: 0 network
attempts, 0 `.env` reads): Step 7 tests 89 passed; benchmark tests 250 passed; full suite
without a database 730 passed, 82 skipped; ruff 0.3.5/0.17.0 and mypy (46 files) pass;
rehearsal and live/smoke refusals as above; datasets and the historical run unchanged.

**Endpoint-identity fix (2026-10-14, uncommitted; no live run).** The runner gate now also
compares each profile's endpoint (`base_url`, exactly as the providers config stores it)
with the config's providers file and refuses a difference before any request; the
manifest's experiment identity records each role's effective endpoint (no credentials,
headers or query strings); analysis rejects a run whose recorded endpoints are missing or
differ from the providers file. Tests use an in-process HTTP mock (`httpx.MockTransport`):
matching endpoint accepted and recorded with no secret in artifacts, analysis output or
logs; changed endpoint refused by the runner with zero requests; tampered or missing
recorded endpoint and changed providers-file endpoint rejected by analysis (a host-case
difference is not equated; one trailing `/` is removed by the providers config); URLs with
credentials, a query or a fragment refused without echoing them.
