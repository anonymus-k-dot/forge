# Feature Status

Legend: **Implemented** (code exists) · **Tested-fake** (automated tests with fake/mocked
providers pass) · **Tested-real** (verified against a real provider/database) ·
**Benchmarked** · **Not started** · **NOT RUN** (designed but never executed).

Last updated: 2026-10-13 — increments 1–4 committed locally (`eb126f0`); increment 5 done, uncommitted.
Details and evidence: [phase-0-plan.md §7](phase-0-plan.md#7-progress-log).

## Legacy (FORGE 1.x) compatibility

| Capability | Status | Evidence |
|---|---|---|
| `POST /enhance` streaming (SSE) | Implemented via `ProviderRouter`, Tested-fake; frames unchanged | `tests/test_app.py`, `tests/test_enhance_providers.py`; Docker run |
| `POST /enhance` non-streaming JSON | Implemented, Tested-fake | same |
| `/enhance` `confidence` / `score` | **Deprecated: always `null`** (no fabricated values); keys kept for one release | `CHANGELOG.md`, `docs/api.md`, ADR-009 |
| `/enhance` error messages | Safe per-category messages (Step 2); same status codes/keys/frames | `tests/test_enhance_providers.py::TestErrors`, `tests/test_api_docs.py` |
| `/enhance` type-invalid input (non-object body, non-string `prompt`) | **Fixed in review:** `400` JSON (was `500` HTML since FORGE 1.x) | `tests/test_enhance_providers.py::TestInputValidation` |
| CI matrix (Py 3.10/3.11/3.12) | Reproduced in Docker: 318 passed, 1 skipped each | phase-0-plan §7 cumulative review |
| `GET /health` | Implemented, Tested-fake; works without credentials | `tests/test_package.py`; Docker run |
| `GET /` legacy UI | Implemented; template changed only to fix the JSON export | template diff vs HEAD: +2/−5 lines |
| UI "Copy as JSON" | **Fixed**: exports `{"enhanced_prompt": ...}` | `tests/test_legacy_ui.py` (Node; fails on the original template); one-off real-browser check |
| `X-Request-ID` header | Implemented, Tested; verified under real Gunicorn | `tests/test_observability.py`; Docker run |
| Structured JSON logs (no prompts/outputs/secrets) | Implemented, Tested; verified under real Gunicorn | `tests/test_observability.py`; Docker logs |
| `gunicorn app:app` | Verified on Linux (Docker, Gunicorn 22.0.0) | phase-0-plan §7 |
| `pip install -r requirements.txt` (Render build) | Verified in a clean venv | phase-0-plan §7 |
| Docker image (unchanged Dockerfile) | Built and run (Steps 2 and 3) | phase-0-plan §7 |
| Real Gemini call with `gemma-4-31b-it` | **Not verified** | no real call made |

## Provider layer

| Item | Status |
|---|---|
| Provider interface, capabilities, normalized errors | Implemented, Tested-fake |
| Fake adapter | Implemented, Tested |
| Google GenAI adapter | Implemented; tested with stubbed SDK **and** through the real google-genai 1.2.0 code with HTTP intercepted (wire request equals the original call) — **not Tested-real** |
| OpenAI-compatible adapter | Implemented; mocked HTTP only — **no real endpoint exercised** |
| Config-driven selection, secrets outside config | Implemented, Tested |
| Retries, `Retry-After`, per-process concurrency limits | Implemented, Tested |

## Phase 0

| Item | Status |
|---|---|
| Repository audit + architecture docs | Done |
| 1. Package structure / app factory / entry-point shim | **Done** |
| 2. Provider abstraction (+ review fixes) | **Done** — real providers unverified |
| 3. Fake-metric deprecation, JSON export fix, structured logging, request IDs | **Done** |
| 4. PostgreSQL + Alembic | **Done** — Tested-real against local PostgreSQL 17 (Docker); hosted DBs not connected; local dev DB reconciled to the corrected `0001` (23/23 constraint names match) |
| 5. Cache + budgets | **Done, uncommitted; acceptance audit done (3 defects fixed)** — Tested-real on PostgreSQL 17 (ephemeral) before the audit and PostgreSQL 18 (disposable cluster) after it; persistent local DB upgraded to `0002` (owner-approved, verified before the audit); Docker/Gunicorn not re-run after the audit; not yet used by a runner (increment 6) |
| 6. Pilot benchmark (~30 tasks) | Not started — real run **NOT RUN** |
| 7. Real-provider verification | Not started — needs your permission to use keys |
| 8. CI with PostgreSQL, docs, README | Not started |

Phase 0 acceptance: **not met** (increments 6–8 outstanding).

## Cache and budgets (increment 5)

| Item | Status |
|---|---|
| Canonical cache key over adapter `cache_identity` (no secrets) | Implemented, Tested (51 tests) |
| Response cache (opt-in, non-streaming, TTL, fail-open), memory + PostgreSQL stores | Implemented, Tested-real |
| Only complete, successful results stored (no empty/blocked/filtered); malformed entries are misses | Implemented in the audit, Tested-real |
| No prompts, responses, namespace values or full keys in cache logs or stored rows | Tested |
| Per-run budgets (attempt-based calls, token reserve/reconcile, structural limits, confirmation threshold) | Implemented, Tested-real |
| Atomic, concurrency-safe reservation; DB-level call-limit CHECK | Tested-real (20 concurrent workers, limit 5); refused reservations re-checked under the row lock (audit fix) |
| Budget fails closed on database errors | Tested |
| `/enhance` unaffected (never cached, never budgeted) | Tested |
| Used by a benchmark/evaluation runner | **Not yet** — increment 6 |
| Cost estimation | Not implemented (no pricing config; never fabricated) |

## Persistence (increment 4)

| Item | Status |
|---|---|
| `DATABASE_*` configuration, redaction, PostgreSQL-only | Implemented, Tested |
| Models + revision `0001` (workspaces, runs, executions, evaluations) | Implemented, Tested-real (PostgreSQL 17) |
| Migration from empty DB, repeat, `alembic check`, catalog equality incl. CHECKs, round trip | Tested-real |
| Constraints (unique, FK `RESTRICT`, 13 CHECKs) and persistence across engine restart | Tested-real |
| Session lifecycle (commit/rollback/close, pool release) | Tested-real |
| `/ready` (`ok`, `not_configured`, `unavailable`, `migrations_pending`) | Implemented, Tested-real; verified under Gunicorn in Docker |
| Docker Compose `db` service | Validated; healthy |
| CI database job | Configured; reproduced locally on Py 3.10/3.11/3.12; **not yet run on GitHub** |
| Test-database safety guard (local hosts only, never port 5432, disposable-server inventory) | Implemented, Tested (15 tests; refusal verified with 0 connections to 5432) |
| Cache table | Created in revision `0002` |
| Hosted PostgreSQL (Neon/Supabase) | **Not connected** |


## Phases 1–8

Not started.
