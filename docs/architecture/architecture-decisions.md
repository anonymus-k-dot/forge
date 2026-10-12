# Architecture Decision Records

Format: context → decision → consequences. Status: **Accepted** unless noted. Decisions
marked *reversible* were chosen as the simplest option under spec §31 and can be revisited.

---

## ADR-001 — Keep the Flask modular monolith, add an application factory

**Context.** All backend code is one module with a module-level app and a Gemini client
created at import, which makes the app impossible to import without credentials and hard
to test without monkeypatching SDK internals.
**Decision.** Move code into an installable `src/forge` package with `create_app(settings)`.
Keep root `app.py` as a 3-line shim exposing `app = create_app()` so `gunicorn app:app`
(Render, Dockerfile, docs) keeps working.
**Consequences.** Tests construct apps with explicit settings and a fake provider. Root
`app.py` re-exports the legacy helper names (`build_forge_prompt`, `_clean_output`,
`GEMMA_MODEL`, `enhance_prompt`) for compatibility.

## ADR-002 — PostgreSQL from Phase 0 via SQLAlchemy 2.x + psycopg 3 + Alembic

**Status:** implemented in increment 4 (revision `0001`, verified against PostgreSQL 17).

**Context.** Spec §5 mandates PostgreSQL from the start. psycopg 3 is maintained, supports
`sslmode`, `connect_timeout`, and `prepare_threshold` (needed for transaction poolers).
**Decision.** `postgresql+psycopg` driver, SQLAlchemy 2.x typed declarative models,
Alembic migrations under `src/forge/db/migrations`. No SQLite anywhere in application
code. Unit tests that need no database use in-memory fakes of *repositories/caches*, not
SQLite. All DB-behavior tests run on real PostgreSQL.
**Consequences.** Running the full suite locally needs a Postgres (Docker or other).
Postgres tests are marked `postgres` and **skip with an explicit reason** when
`TEST_DATABASE_URL` is unset; CI always provides one, so CI never silently skips them.

## ADR-003 — Primary hosted database: Neon; Supabase documented (reversible)

**Context.** Spec asks for one primary hosted provider, provider-independent code.
**Decision.** Document Neon as primary (plain Postgres, pooled `-pooler` hostname,
`sslmode=require`). Document Supabase with its direct and Supavisor pooler endpoints.
Both reduce to `DATABASE_URL` + `DATABASE_SSLMODE` + `DATABASE_POOL_MODE`; no provider SDK.
Free-tier quotas are **not** restated in our docs — we link to the providers' official
pricing pages, because terms change.
**Consequences.** Switching provider is a configuration change. Transaction-mode poolers
require `DATABASE_POOL_MODE=transaction`, which sets psycopg `prepare_threshold=None`.

## ADR-004 — Web app does not require a database to start

**Context.** Spec §5: start without DB credentials in a documented local mode; fail clearly
when a runtime *requires* a DB. The legacy enhancement flow needs no database.
**Decision.** Engine creation is lazy; no I/O at import. `/health` = process liveness only.
`/ready` checks DB connectivity and migration head and returns 503 when unconfigured or
unreachable. DB-requiring commands raise `ConfigurationError("DATABASE_URL is not set …")`.
**Consequences.** Existing Render deployment keeps working with only `GEMINI_API_KEY`.

## ADR-005 — Provider abstraction: Google GenAI (retained) + OpenAI-compatible + fake

**Context.** Existing behavior depends on Google GenAI. Spec prefers open-weight /
self-hosted models; Groq, Ollama (`/v1`), llama.cpp server and vLLM all expose
OpenAI-compatible chat completions.
**Decision.** Three adapters: `google_genai` (keeps the legacy default), `openai_compatible`
(httpx, no vendor SDK — covers Groq, Ollama, llama.cpp, vLLM, others by configuration),
`fake` (deterministic, scripted). Providers and model profiles come from a JSON config file
that references secret **env var names**, never secret values. No hardcoded model catalog.
**Consequences.** The `groq` SDK becomes unnecessary (removal deferred: Step 2 excluded
dependency cleanup). Ollama-native and llama.cpp-native APIs are not implemented until a
capability we need is missing from their `/v1` endpoints.
**Status (Step 2).** Implemented. The default (Gemini, `gemma-4-31b-it`) ships as packaged
`default_providers.json`; `FORGE_PROVIDERS_FILE` replaces it. Config is validated with
pydantic, now declared in `requirements.txt` (`pydantic>=2,<3`, already a google-genai
dependency). Capabilities that differ between servers (seed, usage in streams, max-tokens
field name) are configuration, defaulting to the conservative choice.

## ADR-006 — Normalized provider errors and bounded retries

**Decision.** Ten error categories (spec §8). Retry only `rate_limit`, `transient`,
`timeout`; exponential backoff with full jitter, cap on attempts and delay, `Retry-After`
honored up to the cap. Client-facing messages are category-based and never include raw
exception text or secrets.
**Status (Step 2).** Implemented with categories `configuration`, `authentication`,
`invalid_request`, `rate_limit`, `unavailable`, `timeout`, `server_error`,
`malformed_response`, `unsupported_capability`, `unknown`. Retried: `rate_limit`,
`unavailable`, `timeout`, `server_error` ("transient" was split into the last three). A
`Retry-After` above `max_retry_after_seconds` ends retrying rather than being capped, so a
web request is never held open for a long upstream-requested delay. `cancelled` and
`context_overflow` are deferred until a caller needs them (overflow currently surfaces as
`invalid_request`).

## ADR-007 — Cache key and storage

**Decision.** Versioned canonical-JSON SHA-256 over every output-affecting input; only
successful results cached; PostgreSQL table with unique key; memory backend for tests.
Cache hits are recorded on every result and every execution row.
**Consequences.** Changing adapter serialization requires bumping `key_version`.

## ADR-008 — Budgets enforced before calls, per run

**Decision.** `BudgetGuard` is consulted by the router before every non-cached call.
Exceeding a limit raises `BudgetExceeded`; the run is marked `budget_exceeded` with partial
results kept. Pre-run estimate = cases × systems × samples × calls-per-system.

## ADR-009 — Remove fabricated `confidence` / `score` from `/enhance` (explicit contract change)

**Context.** `confidence: "98%"` and `score: 0.98` are constants presented as measurements
(spec §9 "DO NOT BUILD", Phase 0 "remove misleading or fake metrics"). Verified use: the
bundled UI never displays them, but leaks them into "Copy as JSON" in place of the prompt.
External API consumers are unknown.
**Decision (pending user confirmation).** Remove both fields from successful and error
responses; keep all other field names and status codes; announce in `CHANGELOG.md` and
`docs/api.md`. Fix the UI JSON export to contain the enhanced prompt.
**Revised and implemented (Step 3, per owner instruction to prefer a deprecation
transition).** Consumer inventory: the bundled UI never reads these fields from the server
(it only uses streaming, which never contained them); its fake values were a client-side
constant, now removed. No other in-repo consumer; external consumers unknown. Therefore the
keys stay in both success and error bodies with value `null` (no invented values) for one
release, are documented as deprecated in `docs/api.md` and `CHANGELOG.md`, and will be
removed afterwards. A `Deprecation` HTTP header was not added because it would mark the
whole `/enhance` resource deprecated, not two fields. Error bodies previously used
`"N/A"`/`0`; these are also `null` now for consistency.
**Alternative considered.** Keep the keys with `null` — still breaks numeric consumers and
keeps a misleading surface, so rejected.

## ADR-010 — Legacy streaming errors: category message instead of raw exception

**Decision.** Keep the SSE frame shape `data: {"error": "<message>"}` and the 500 JSON
shape, but `<message>` becomes a safe normalized message (e.g. `"Provider rate limit
reached (rate_limit). Please retry shortly."`). The UI's friendly-message mapping already
matches `rate_limit` and `timeout` substrings, so it keeps working.
**Status.** Implemented in Step 2 (moved forward from Step 3 because the Step 2 brief
required safe messages). Applies to both `/enhance` modes; status codes, field names and SSE
frame shape are unchanged. Three original tests in `tests/test_app.py` asserted that raw
exception text reached the client; their raw-text assertions were replaced with
"safe message present, raw text absent". All other original assertions are untouched.

## ADR-014 — Per-process concurrency limits

**Context.** Gunicorn runs several worker processes; a global limit would need shared state
(database or Redis), which Phase 0 does not have.
**Decision.** A bounded semaphore per provider per process, with a bounded wait for a slot.
**Consequences.** Effective limit = workers × `max_concurrency`. Documented, not hidden.
Revisit with the database-backed job queue (Phase 2) if measured load requires it.

## ADR-015 — Streamed enhancement output stays uncleaned

**Context.** FORGE 1.x applies `clean_output` only to the non-streaming result; SSE chunks
are sent raw and the UI renders them. Cleaning a stream incrementally would change the bytes
existing clients receive and needs look-ahead buffering across chunk boundaries.
**Decision.** Preserve the existing behavior: clean once, after the full text, in the
non-streaming path only. Revisit when the new frontend defines its own rendering contract.

## ADR-011 — Phase 0 evaluation is L0 deterministic only

**Context.** The full evaluation engine (rubrics, pairwise judges, statistics) is Phase 2.
Phase 0 must still distinguish raw / generic rewrite / current FORGE.
**Decision.** Pilot tasks carry deterministic checks (format, required/forbidden content,
length, JSON validity). Reports show per-system pass counts and paired win/tie/loss with
explicit **INCONCLUSIVE** labelling and a statement that L0 checks do not measure overall
quality. No composite score.

## ADR-012 — Legacy UI retained; React frontend deferred to Phase 1

**Decision.** `templates/index.html` stays as the compatibility UI with a minimal bug fix
(JSON export). React + TS + Vite starts in Phase 1 under `web/`.

## ADR-013 — No job queue/worker in Phase 0

**Decision.** The pilot benchmark runs synchronously from the CLI. The PostgreSQL-backed
job table and worker arrive in Phase 2, when runs are launched from the API.

## ADR-016 — Local database port, credentials and test isolation

**Context.** The development machine already runs a native PostgreSQL 18 on port 5432 (found
in increment 4; the audit had missed it). Tests must never touch a personal or hosted
database. The spec forbids hardcoded production credentials but wants a simple local setup.
**Decision.** The Compose `db` service publishes on `127.0.0.1:5433` (configurable) and uses a
local-only default password (`forge-local-dev-only`, overridable via `POSTGRES_PASSWORD`).
Database tests only create and drop their own `forge_test_<random>` databases through
`TEST_DATABASE_URL`, refuse non-local hosts by default, and cannot be silently skipped in CI
(`FORGE_REQUIRE_DB_TESTS=1`). **Amended in the Steps 1–4 review:** the original guard
checked only the host, so `127.0.0.1:5432` (the native server) was accepted; it now also
refuses port 5432 and servers holding non-test databases (`tests/db/safety.py`), and CI
publishes its PostgreSQL service on 5433.
**Consequences.** No production credential exists in the repository; hosted databases are
configured only through `DATABASE_URL`.

## ADR-017 — Readiness requires the schema to be at the shipped migration head

**Decision.** `/ready` returns 200 only if PostgreSQL answers *and* `alembic_version` equals
the head revision packaged with the running code; otherwise 503 with `unavailable` or
`migrations_pending`. `/health` stays process-only.
**Consequences.** A deploy that forgot to migrate is reported as not ready instead of failing
later on missing tables. The check costs one pooled connection per call.
