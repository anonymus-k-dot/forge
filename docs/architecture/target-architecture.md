# FORGE 2.0 — Target Architecture

Authoritative product spec: [`docs/FORGE_2.0_MASTER_SPEC.md`](../FORGE_2.0_MASTER_SPEC.md).
This document describes how that spec maps onto this repository. Sections marked
**(Phase 0)** are being built now; everything else is the intended shape for later phases
and must not be read as implemented. Current status lives in
[`docs/implementation/feature-status.md`](../implementation/feature-status.md).

## 1. Shape: modular monolith

```text
Browser ── legacy UI (templates/index.html)        ← retained, served by Flask
        └─ React + TS + Vite (web/)                ← Phase 1+
               │
               ▼
Flask (create_app) under Gunicorn
  ├─ /enhance, /health, /                          ← legacy compatibility surface (Phase 0)
  ├─ /ready                                        ← DB + provider config readiness (Phase 0)
  └─ /api/v1/...                                   ← versioned API (Phase 1+)
        │ thin routes: validate → service → response
        ▼
  services/ ── domain/ ── analysis/ optimization/ evaluation/ benchmark/
        │
        ├─ providers/ProviderRouter ── google_genai | openai_compatible | fake   (Phase 0)
        │       timeouts · bounded retries · per-provider concurrency · cache · budget · usage
        │
        └─ db/ (SQLAlchemy 2.x, psycopg 3, Alembic) ──► PostgreSQL               (Phase 0)
                local Docker  |  Neon (primary hosted)  |  Supabase (documented)

Worker process (same package, `forge worker` entry point)                         (Phase 2)
  claims jobs with SELECT … FOR UPDATE SKIP LOCKED, heartbeats, cancellation
```

No Redis, Celery, Kafka, Kubernetes or microservices.

## 2. Package layout

`src/` layout, installable with `pip install -e .`. Only modules needed by the current
phase are created.

```text
app.py                      # compatibility shim: `app = create_app()` for `gunicorn app:app`
alembic.ini
src/forge/
  __init__.py               # __version__
  app.py                    # create_app(settings=None)        (Phase 0)
  settings.py               # single source of configuration   (Phase 0)
  errors.py                 # ForgeError hierarchy + HTTP error envelope (Phase 0)
  logging.py                # JSON logging, request IDs        (Phase 0)
  cli.py                    # `forge` command — not created yet; planned with the benchmark
                            # runner (increment 6). Migrations use the `alembic` CLI.
  api/
    health.py               # /health, /ready                  (Phase 0)
    legacy.py               # /, /enhance                      (Phase 0)
  legacy/enhance.py         # FORGE 1.x system prompt, builder, cleaner (Phase 0)
  providers/
    base.py                 # ProviderAdapter protocol, request/response types, capabilities
    errors.py               # normalized ProviderError categories
    router.py               # ProviderRouter: profiles, retries, concurrency, cache + budget hooks
    retry.py                # RetryPolicy, Retry-After parsing
    config.py               # provider/model-profile config loading (no secrets in files)
    default_providers.json  # packaged default: Gemini legacy profile
    google_genai.py         # retained adapter
    openai_compatible.py    # Groq / Ollama / llama.cpp / other compatible endpoints (httpx)
    fake.py                 # deterministic adapter for tests and CI
  infrastructure/           # (increment 5)
    cache.py                # cache key, CachePolicy, memory + PostgreSQL stores
    budgets.py              # BudgetLimits, check_plan, memory + PostgreSQL run budgets
  db/                       # (increment 4)
    config.py               # DATABASE_* parsing, URL redaction
    models.py               # SQLAlchemy 2 models + naming convention
    session.py              # lazy engine, session() unit of work, readiness()
    migrate.py              # Alembic helpers without alembic.ini
    repositories.py         # workspace/run helpers (create_run validates budgets)
    migrations/             # Alembic env + versions (0001_initial_schema)
  benchmark/
    tasks.py                # task file schema + loading + hashing
    systems.py              # B0 raw, B1 generic rewrite, F-current (legacy FORGE)
    checks.py               # L0 deterministic checks used by the pilot
    runner.py               # executes a manifest, persists results
    manifests.py            # manifest building + canonical hashing
    reporting.py            # JSON + Markdown reports
benchmarks/pilot-v0/        # version-controlled task set (~30 tasks)
tests/
  unit/  integration/  (postgres-marked tests require TEST_DATABASE_URL)
```

## 3. Configuration (single source of truth)

`forge.settings.Settings` is built once from the environment (and `.env` in development).
Nothing else reads `os.environ`.

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | `postgresql+psycopg://…` (plain `postgresql://` / `postgres://` are normalized; other schemes rejected). **(implemented, increment 4)** |
| `DATABASE_POOL_SIZE`, `DATABASE_MAX_OVERFLOW`, `DATABASE_POOL_TIMEOUT` | SQLAlchemy pool |
| `DATABASE_CONNECT_TIMEOUT` | psycopg `connect_timeout` |
| `DATABASE_SSLMODE` | overrides `sslmode`; if the URL already has one, URL wins only when this is unset |
| `DATABASE_POOL_MODE` | `session` (default) or `transaction` — disables server-side prepared statements for PgBouncer/Supavisor transaction pooling |
| `FORGE_PROVIDERS_FILE` | JSON file with provider + model-profile definitions (no secrets). Unset = packaged `forge/providers/default_providers.json` (Gemini only). Relative paths resolve against the working directory. **(implemented, Step 2)** |
| `GEMINI_API_KEY` | Credential for the default `gemini` provider (named by `api_key_env`). Optional at startup. **(implemented)** |
| any `api_key_env` name, e.g. `GROQ_API_KEY` | Credentials for other configured providers, read on first use. **(implemented)** |
| `FORGE_MAX_REQUEST_BYTES` | Request size limit |
| `FORGE_LOG_LEVEL` | JSON log level for the `forge` logger (default `INFO`). **(implemented, Step 3)** Prompt/response bodies are never logged; an opt-in `FORGE_LOG_PROMPTS` is *not* implemented and will only be added with a documented retention policy. |

The web app starts without `DATABASE_URL` (legacy enhancement needs no database);
`/ready` then reports `database: not_configured` with HTTP 503. Commands that require a
database (`alembic` via `env.py`; later `forge benchmark run`) fail with a `ConfigurationError`
naming the missing variable. No database I/O happens at import time.

## 4. Provider layer — implemented in Phase 0 Step 2

Dependency direction: `api/legacy.py` (route) → `legacy/enhance.py` (`LegacyEnhancer`,
provider-independent) → `providers/router.py` (`ProviderRouter`) → adapter. Provider SDKs,
HTTP, auth and response parsing exist only inside the adapter modules.

### 4.1 Types (`providers/base.py`)

- `GenerationRequest(messages, system, params)`; `GenerationParams(temperature, top_p,
  max_output_tokens, seed)` — `None` means "not set", never a guessed default.
- `GenerationResult(provider, model, text, reported_model, finish_reason, usage)`.
- Streams yield `TextDelta(text)` events and then exactly one `StreamEnd(reported_model,
  finish_reason, usage)`. Each adapter parses its own wire format into these events.
- `Usage(input_tokens, output_tokens)` holds **provider-reported** counts only; it is `None`
  when the provider reports nothing. No token estimation, latency, cost, or quality values
  exist in this layer yet.
- `Capabilities(streaming, system_instruction, seed, usage_reporting)`: adapter-type
  defaults, overridable per provider in config. The router rejects requests needing an
  unsupported capability with `UnsupportedCapabilityError` before any call.

### 4.2 Adapters

| Adapter | Responsibility | Defaults |
|---|---|---|
| `google_genai` | `google-genai` SDK; client created on first use with `HttpOptions(timeout=ms)`; a single user message is sent as a plain string, exactly like FORGE 1.x; classifies `APIError` by HTTP status (400 + `API_KEY_INVALID` → authentication), `Retry-After` header or `RetryInfo.retryDelay`, and `requests`/`httpx` timeout/connection errors | streaming, system, seed, usage: supported |
| `openai_compatible` | `POST {base_url}/chat/completions` via httpx; bearer or no auth; own incremental line splitter + SSE parser (CR/LF/CRLF across chunk boundaries, multi-line `data:`, comments, `event: error`, `[DONE]`, 1 MB line cap); validates JSON structure; closes the response when the consumer stops | streaming, system: yes; seed, usage: **off unless configured** |
| `fake` | Deterministic scripted responses/errors for tests and offline runs; no network | all supported |

The OpenAI-compatible adapter is tested **only against mocked HTTP**; no Groq, Ollama,
llama.cpp or other server has been exercised.

### 4.3 Errors (`providers/errors.py`)

| Category | Class | Retried |
|---|---|---|
| configuration | `ProviderConfigurationError` (also a `ConfigurationError`) | no |
| authentication | `AuthenticationError` (401/403, Gemini `API_KEY_INVALID`) | no |
| invalid_request | `InvalidRequestError` (other 4xx) | no |
| rate_limit | `RateLimitError` (429) | yes |
| unavailable | `ProviderUnavailableError` (503, connection failures); `ConcurrencyLimitError` (local) | yes / **no** for the local limit |
| timeout | `ProviderTimeoutError` (408, client timeouts) | yes |
| server_error | `UpstreamServerError` (other 5xx, upstream error events in a stream) | yes |
| malformed_response | `MalformedResponseError` | no |
| unsupported_capability | `UnsupportedCapabilityError` | no |
| unknown | `UnknownProviderError` (anything else; the router wraps non-provider exceptions) | no |

Internal messages contain only provider name, HTTP status, or exception *type*; the original
exception is kept as `__cause__`. Clients only ever see `safe_message`, a fixed string per
category (configuration messages are FORGE-authored and name variables, never values).

### 4.4 Retries and concurrency (`providers/retry.py`, `providers/router.py`)

- `max_attempts` (default 3, counting the first call). Exponential backoff with full jitter:
  `uniform(0, min(max_delay, base × 2^(attempt-1)))`, defaults base 0.5 s, max 8 s.
- `Retry-After` (seconds or HTTP-date) is used exactly when ≤ `max_retry_after_seconds`
  (default 20 s); a longer requested delay stops retrying immediately.
- Streams are retried only if no text has been delivered yet.
- Per-provider `threading.BoundedSemaphore(max_concurrency)` (default 4); acquiring waits at
  most `acquire_timeout_seconds` (default 10 s), then `ConcurrencyLimitError`. The slot is
  released before backoff sleeps, after errors, and when a stream is closed early (client
  disconnect → Flask closes the generator chain → adapter closes its HTTP response).
- **Scope:** limits are per process. With Gunicorn `--workers 2` the effective limit per
  provider is 2 × `max_concurrency`. There is no cross-process or cross-instance limit.
- Request timeouts: `timeout_seconds` per provider (default 60 s), passed to the SDK/httpx.
  For streams this bounds each read, not the total duration; the Gunicorn `--timeout 120`
  remains the outer bound.

### 4.5 Configuring providers

Provider file (validated with pydantic; unknown keys rejected; validation messages never echo
values). Full example: [`config/providers.example.json`](../../config/providers.example.json).

```json
{
  "default_model": "legacy-enhancer",
  "providers": {
    "gemini": {"type": "google_genai", "api_key_env": "GEMINI_API_KEY"},
    "groq":   {"type": "openai_compatible", "base_url": "https://api.groq.com/openai/v1",
               "auth": "bearer", "api_key_env": "GROQ_API_KEY"},
    "ollama": {"type": "openai_compatible", "base_url": "http://localhost:11434/v1", "auth": "none"}
  },
  "models": {
    "legacy-enhancer": {"provider": "gemini", "model": "gemma-4-31b-it"},
    "groq-example":    {"provider": "groq",   "model": "<model id from the provider>"}
  }
}
```

Per-provider options: `timeout_seconds`, `max_concurrency`, `acquire_timeout_seconds`,
`retry {max_attempts, base_delay_seconds, max_delay_seconds, max_retry_after_seconds}`,
`capabilities {streaming, system_instruction, seed, usage_reporting}`, and for
`openai_compatible` also `max_tokens_field` (`max_tokens` | `max_completion_tokens`).
Model profiles may set default `params`; explicit request params take precedence.

- **Credentials:** only the *name* of an environment variable (`api_key_env`, pattern
  `^[A-Z_][A-Z0-9_]*$`) appears in the file; the value is read from the environment / `.env`
  when the provider is first used. `base_url` must not contain credentials or a query string.
- **Switching the enhancer to another provider:** point `default_model` at another profile
  and set `FORGE_PROVIDERS_FILE`. The FORGE 1.x system prompt and parameters (T 0.5,
  top-p 0.85, 1280 max output tokens) are sent to whichever provider is selected.
- An invalid file fails app startup with a `ConfigurationError`; a missing credential fails
  only the request that needs it.

### 4.6 Not yet implemented (later steps)

Logical roles (generator/critic/judge/target), cache, budgets, latency/usage persistence,
provider health endpoints, `context_overflow`/`cancelled` categories, Ollama-native or
llama.cpp-native APIs, and closing adapters at process shutdown (clients live for the
process lifetime).

## 5. Cache and budgets — implemented in Phase 0 Step 5

Code: `src/forge/infrastructure/cache.py`, `src/forge/infrastructure/budgets.py`, router
integration in `src/forge/providers/router.py`, schema in revision `0002`.

### 5.1 Response cache

- **Opt-in per call** (`router.generate(..., cache=CachePolicy(...))`). Used for non-streaming
  run executions (benchmarks/evaluations from increment 6). `/enhance` never uses it, so its
  results stay fresh samples. Streams never use it (no partial or re-chunked replay).
- **Key** = SHA-256 hex of canonical JSON (sorted keys, no whitespace, UTF-8, no ASCII
  escaping, NaN/Infinity rejected, JSON types preserved so `1` ≠ `1.0`, no Unicode
  normalization) over `{key_version, request: adapter.cache_identity(model, request),
  namespace}`. `cache_identity` is the exact request the adapter would send — endpoint (base
  URL/path or API), model, messages, system, all parameters with their wire names, and any
  response-format fields once supported — and never headers or credentials. Profile default
  params are merged before keying. `namespace` carries caller context such as an evaluator
  version. Bump `CACHE_KEY_VERSION` or an adapter's `CACHE_IDENTITY_VERSION` to invalidate.
- **Repeated samples**: identical requests share one entry, so with caching, N samples of the
  same request would all replay the first sample. A caller that needs independent samples
  (e.g. `samples_per_case > 1`) must put the sample index in `namespace`, or not cache.
  Enforcing this is the runner's job (increment 6).
- **Stored**: only complete, successful `generate` results (`is_cacheable`: non-empty text and
  finish reason `stop`/`length`/`max_tokens` in any case, or none reported) — text, reported
  model, finish reason, provider-reported usage. Empty, blocked, filtered or otherwise
  abnormal results are returned to the caller but not stored (`cache.not_stored`). Never
  failures, retries-exhausted errors or streams. The request content is not stored.
- **TTL**: `FORGE_CACHE_TTL_SECONDS` (default 2,592,000 = 30 days; 1 s – 365 days). Expiry is
  evaluated on the database clock; expired entries are misses and are replaced by the next
  successful call. `PostgresCacheStore.purge_expired()` deletes expired rows (not scheduled).
- **Concurrency**: one row per key (primary key). Writes are `INSERT … ON CONFLICT DO UPDATE
  … WHERE expires_at <= now()` — the first valid entry wins, readers only ever see a complete
  row. There is no single-flight: concurrent misses for the same key each call the provider
  (and each is charged to the budget), because coordinating them would require holding a
  lock or transaction during the model call.
- **Database unavailable / table missing**: fail open — lookup is a miss, write is skipped,
  `cache.unavailable` is logged (operation + error type only). A malformed stored entry is
  also a miss (`cache.invalid_entry`); it stays until it expires.
- **Observability**: `cache.hit`, `cache.miss`, `cache.store`, `cache.not_stored` log events
  with a 12-character key prefix, provider and model only (never prompts, responses,
  namespace values or the full key). Results carry `cache_hit`; run rows count `cache_hits`.
  A hit returns the original call's provider-reported usage; with `cache_hit=True` it must
  not be counted as fresh usage.

### 5.2 Per-run budgets

- Limits in `runs.budget_limits` (validated by `BudgetLimits`, strict integers, unknown keys
  rejected): **`max_model_calls` (required)**, `max_estimated_tokens`, `max_cases`,
  `max_samples_per_case`, `max_candidates`, `confirm_above_model_calls`.
- **Calls**: every provider *attempt* — first try, each retry, failed attempts — consumes one
  unit *before* it is sent, inside the provider concurrency slot (a slot timeout consumes
  nothing). Nothing is refunded. Cache hits consume nothing and are counted in `cache_hits`.
- **Tokens** (only when `max_estimated_tokens` is set; then every request must set
  `max_output_tokens`): each attempt reserves `ceil(chars(system + messages) / 4) +
  max_output_tokens`. After the attempt the reservation is released and the run is charged
  provider-reported input + output tokens when both are reported, otherwise the estimate
  (also for failed or abandoned attempts).
- **Atomicity**: `PostgresRunBudget.reserve` is one conditional `UPDATE … WHERE status IN
  ('pending','running') AND model_calls_used + 1 <= limit AND tokens_used + tokens_reserved +
  reservation <= token_limit RETURNING …`. PostgreSQL's row lock serialises concurrent
  workers, so the limit cannot be overspent; `ck_runs_model_calls_within_limit` enforces the
  call limit again at the database level. No transaction is held during the model call. If
  the `UPDATE` matches nothing, the row is locked (`FOR UPDATE`) and re-checked: the run is
  marked exhausted only if the reservation still does not fit (a concurrent settlement may
  have released tokens in between).
- **Concurrency and tokens**: outstanding reservations count against the token budget, so
  with parallel workers a run can be refused (and marked `budget_exceeded`) when actual usage
  would have fit; the outcome is conservative but can depend on concurrency.
- **Exhaustion**: the attempt is not made, the run is set to `budget_exceeded` (results kept),
  and `BudgetExceededError` (code `budget_exceeded`, with `dimension`) is raised. Runs not in
  `pending`/`running` raise `RunNotActiveError` (code `run_not_active`) — this is also how a
  cancelled run stops spending. Cache hits spend nothing and are served without checking the
  run status, so the runner must stop scheduling work for an inactive run itself.
  `MemoryRunBudget` has no run status: after exhaustion it keeps raising
  `BudgetExceededError`, where `PostgresRunBudget` raises `RunNotActiveError` with status
  `budget_exceeded`.
- **Pre-run check**: `check_plan(limits, RunPlan, max_attempts, confirmed)` rejects plans
  exceeding structural limits or whose minimum call count exceeds `max_model_calls`, and
  raises `BudgetConfirmationRequiredError` when the worst case (calls × max attempts) exceeds
  `confirm_above_model_calls` without confirmation.
- **Failure behaviour**: reservation fails closed — any database error raises and no call is
  made. If *settling* fails after a call, the reservation stays counted (conservative) and
  `budget.settle_failed` is logged. A crash between reserve and settle leaves tokens reserved
  (conservative; reconciliation belongs to the job system, Phase 2).
- **Cost**: not implemented — no versioned pricing configuration exists, and costs are never
  fabricated (spec §19). Each settlement reports whether it used provider-reported or
  estimated tokens (`Settlement.source`), but `runs.tokens_used` is a budget-accounting total
  that mixes both; per-call usage and its source belong in `executions.usage_source`
  (written by the runner, increment 6). Without a token budget, an attempt with no
  `max_output_tokens` and no provider usage adds 0 to `tokens_used`.

## 6. Data model

Phase 0 schema (minimal, coherent; expanded by later migrations). **Implemented in increment 4
as Alembic revision `0001`** — full column list, constraints and operations in
[`docs/implementation/database.md`](../implementation/database.md).

| Table | Purpose | Key constraints |
|---|---|---|
| `workspaces` | Isolation boundary from day one | unique `slug` |
| `runs` | One benchmark/pilot run: manifest (JSONB), `manifest_hash`, status, forge version, timestamps, budget limits | FK workspace `RESTRICT`; check on `status` |
| `executions` | One model call: system variant, case ID, **role** (generator/critic/judge/target), **sample index**, provider, requested/reported model, params, request hash, **raw output**, finish reason, usage + usage source, latency, cache_hit, error category | FK run `RESTRICT` (history is not cascade-deleted); unique (run_id, case_id, system, role, sample_index), which also serves as the (run_id, case_id) index; CHECKs on role, usage source, error category, hashes, non-negative counts, output-or-error |
| `evaluations` | Derived results, separate from raw output: evaluator name + version + config, per-check results (JSONB), passed | FK execution `RESTRICT`; unique (execution_id, evaluator, evaluator_version) |
| `llm_cache_entries` | Response cache (revision `0002`) | primary key `cache_key` (SHA-256 hex), `expires_at` index; see §5.1 |

Deferred to the phase that implements them: `prompts`, `prompt_versions` (Phase 1, with a
DB trigger enforcing immutability), `test_suites`, `test_cases`, `suite_revisions`, `jobs`
(Phase 2), `intent_specs` (Phase 3), `optimization_sessions`, `change_records` (Phase 4),
`experiments` (Phase 6). Phase 0 runs reference prompts by content hash inside the manifest.

## 7. Benchmark (Phase 0 pilot)

- Tasks: `benchmarks/pilot-v0/tasks.jsonl`, ~30 tasks, each with `id`, `category`,
  `spec_level` (well / partial / vague), `split` (dev / heldout), `prompt`, and L0
  deterministic `checks`.
- Systems: **B0** raw prompt → target; **B1** generic single-shot rewrite → target;
  **F-legacy** current FORGE enhancement → target. Each system's prompt transformation is
  recorded as its own execution.
- Evaluation in Phase 0 is **L0 deterministic checks only** (format/constraint adherence),
  versioned, stored separately from raw outputs. It does not measure overall quality and the
  report says so. Statistics are counts with paired win/tie/loss; suites this small are
  labeled **INCONCLUSIVE**.
- Output: `manifest.json` (hash-addressed), `results.jsonl` (per case/system),
  `summary.md`, and rows in PostgreSQL. A run with the fake provider is part of CI.

## 8. HTTP conventions

- Error envelope for new endpoints: `{"error": {"code": "...", "message": "...", "request_id": "..."}}`.
- Every response carries `X-Request-ID` (accepted from the client if it matches `^[A-Za-z0-9._-]{1,128}$`, else generated); the ID is attached to every log record of the request. **(implemented, Step 3)**
- Logs: JSON lines on stderr from the `forge` logger only (Gunicorn's loggers untouched). Events: `request.completed` (method, path, status, streamed, duration_ms — time to headers for streams), `provider.retry`, `enhance.failed` (category, provider, status_code), `enhance.internal_error` (with traceback). **(implemented, Step 3)**
- Legacy `/enhance` keeps its historic body shape (see ADR-009 for the one intentional change).

## 9. Deployment

- `docker-compose.yml`: `db` (`postgres:17`, named volume `forge_pgdata`, health check,
  published on `127.0.0.1:5433` only) + `forge` (gets `DATABASE_URL` for `db`, waits for it
  to be healthy). **(implemented, increment 4)**
- Gunicorn entry `app:app` retained. Migrations are an explicit step — `alembic upgrade head`
  (the planned `forge db upgrade` wrapper was not needed; see phase-0-plan) — never run
  automatically on web start.
- CI: GitHub Actions Postgres service container → `alembic upgrade head` / `current` / repeat /
  `alembic check` → full pytest with `FORGE_REQUIRE_DB_TESTS=1` → ruff. **(implemented,
  increment 4; mypy in CI still planned for increment 8)**
