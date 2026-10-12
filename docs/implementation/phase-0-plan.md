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
| 5 | **Cache + budgets.** Cache key, memory + Postgres stores, router integration, `BudgetGuard`. | add `src/forge/infrastructure/{cache,budgets}.py`, `db/repositories/cache.py` | Unit: key differs when any of provider/model/params/system/messages/schema change; identical inputs → identical key; failures not cached; `cache_hit` flagged. Budget stops the N+1th call. Postgres: unique key under concurrent insert |
| 6 | **Pilot benchmark.** ~30 tasks, systems B0/B1/F-legacy, L0 checks, manifest hashing, runner, reports, persistence, `forge benchmark run`. | add `src/forge/benchmark/*`, `benchmarks/pilot-v0/{tasks.jsonl,README.md}` | Task-file schema validation; manifest hash stable across runs and changes when any input changes; fake-provider end-to-end run writes manifest + results + summary and DB rows; replay from cache flagged as cached |
| 7 | **Real-provider verification** (needs your go-ahead, see §6). Single smoke request; then optionally the pilot on one real target model. | — | Recorded command output, model ID, usage; or marked **NOT RUN** |
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
   (b) the ~30-task pilot (~30 × 3 systems ≈ 150 calls on a free tier).
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
