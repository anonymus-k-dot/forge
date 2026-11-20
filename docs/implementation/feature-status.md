# Feature Status

Legend: **Implemented** (code exists) · **Tested-fake** (automated tests with fake/mocked
providers pass) · **Tested-real** (verified against a real provider/database) ·
**Benchmarked** · **Not started** · **NOT RUN** (designed but never executed).

Last updated: 2026-10-14 — increments 1–4 (`eb126f0`), 5 (`d101e71`) and 6 (`60cf680`) committed locally; increment 7 designed, review-fixed and validated offline (no live run), uncommitted.
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
| `GET /` legacy UI | Implemented; Phase A usability/accessibility fixes (literal output, no Ctrl+C/Escape hijacks, backend error messages, Stop/cancel, explicit states, accessible dialog and copy menu, AA contrast, native cursor); layout and branding unchanged | `tests/test_legacy_ui.py` + `tests/frontend/` (Node, real template script, fake DOM, Flask stream replay); one-off headless Chrome 155 check (28/28 behaviour checks plus dialog layout at 320×256, 375×812, 1280×900; fake provider; external CSS/fonts blocked, so Tailwind/font styling not verified) |
| `GET /app/` React frontend (`web/`) | Implemented, **preview beside `/`**; Dockerfile builds it (`web` stage) and CI has a `frontend` job, but **the image has not been built and CI has not run** (no Docker engine here; nothing pushed); not deployed; a non-Docker Render service needs the build command in `docs/deployment.md` | `web/tests/unit` (42, mutation-checked), `tests/test_web_frontend.py` (Flask serving, build, legacy unchanged); headless Chrome 155, 75/75 checks (opt-in, fake provider, local CSS so styling verified); Vite dev proxy streaming checked once |
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
| 6. Pilot benchmark (~30 tasks) | **Implemented, uncommitted** — Tested-fake (offline) and Tested-real on PostgreSQL 18.6 (disposable); benchmark against a real model **NOT RUN**; results INCONCLUSIVE by protocol |
| 7. Real-provider verification | **Designed, validated offline, uncommitted** — protocol, experiment config, offline plan, blinded export and analysis; smoke test and pilot **NOT RUN** (need explicit approval) |
| 8. CI with PostgreSQL, docs, README | Not started |

Phase 0 acceptance: **not met** (increments 6–8 outstanding).

## Real-model pilot design (increment 7)

| Item | Status |
|---|---|
| Protocol `forge-step7-pilot` 1.1.0 (outcomes, design, rubric, analysis plan, provider facts with sources, budget, fail-closed gates) | Written; preregistered before any real output (1.1.0 revision also before any real output) |
| Experiment config + `forge benchmark plan` (offline preflight; no adapter, router, socket, settings or `.env` access) | Implemented, Tested |
| Fail-closed cost/token checks (unknown price fails; a price is bound to provider name, type, endpoint and model, with tier, source and date; cost at the token budget vs ceiling - an estimate, not a hard cap) and owner checks per real provider (tier/billing, rate limits, data use) plus thinking risk | Implemented, Tested |
| Live execution gate (`run --experiment`; preflight before credentials; runner conformance check; experiment identity in manifest) | Implemented, Tested-fake; never exercised against a real provider |
| Analysis identity checks (experiment, protocol, dataset, conditions, profiles, providers, models, recorded endpoints, execution mapping) | Implemented, Tested |
| Pacing between model calls (`--pace-seconds`) | Implemented, Tested |
| Blinded export for human rating (key outside the rater folder); ratings schema | Implemented, Tested |
| Paired analysis (one task set, failure classification, bootstrap; synthetic runs refused) | Implemented, Tested-fake (offline rehearsal) |
| Rubric and `pilot-v1` rater notes | Prepared (not yet used by raters) |
| Account tier/billing status, rate limits, model access on the owner's key | **Not verified** (owner checks; FORGE never queries an account) |
| One-task smoke test; 30-task live pilot; human ratings | **NOT RUN** — require owner approval |
| LLM judge | Not implemented (would need separate authorization and calibration) |

## Pilot benchmark (increment 6)

| Item | Status |
|---|---|
| Protocol `forge-pilot` v1 (docs/benchmark/pilot-protocol.md) | Implemented |
| Dataset `benchmarks/pilot-v1` (`forge-pilot` 1.0.0: 30 tasks, 67 checks; no task fully passed by a trivial answer) | Prepared, validated (tests) |
| Dataset `benchmarks/pilot-v0` (0.1.0, 50 checks; preserved byte for byte for earlier runs; 6 tasks fully passed by "ok") | Kept, verifiable |
| Conditions B0 / B1 / F-legacy (same task input; B1 independent of FORGE) | Implemented, Tested-fake |
| L0 deterministic checks (evaluator `forge.l0` v1) | Implemented, Tested (rule-by-rule) |
| Manifest / results / summary files, canonical hashes, `verify` | Implemented, Tested-fake (tampering and fabrication detected) |
| Honest partial runs (budget, cancellation, failures, persistence errors) | Tested-fake; budget, cancellation, cache and DB-failure paths Tested-real (PostgreSQL 18.6) |
| PostgreSQL persistence (existing `runs`/`executions`/`evaluations`, no migration) | Tested-real (PostgreSQL 18.6, disposable cluster) |
| Cache isolation per run scope / condition / task / role; flagged replay | Tested-fake (memory store) and Tested-real (PostgreSQL) |
| `forge benchmark` CLI; real providers refused by default | Implemented, Tested |
| Accounting: condition results, executions, provider attempts (per execution, retries included), cache hits, provider-reported vs estimated tokens | Implemented, Tested-fake; cache-hit token handling Tested-real |
| Finalization order (`finalizing` → database → summary → `run.json`), failure and double-failure handling, `verify --database` | Implemented, Tested-fake and Tested-real (PostgreSQL 18.6); no cross-store atomicity |
| F-legacy vs web-UI streaming path (UI output is not cleaned; benchmark matches `stream: false`) | Documented in manifest and protocol, Tested |
| Offline pilot (fake providers) | Run — **synthetic**, validates the harness only |
| Pilot on a real model | **NOT RUN** (increment 7, needs approval) |
| LLM judge, rubric, human or semantic scoring; cost estimation | Not implemented (out of scope) |

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
