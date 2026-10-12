# FORGE — Current State (pre-2.0 audit)

**Audit date:** 2026-10-12
**Audited commit:** `131d0df` (branch `main`, remote `origin/main`)
**Auditor scope:** every tracked file (21 files), git history, local toolchain.

Each statement is tagged:

- **[V]** Verified — observed directly in code, by running a command, or in git history.
- **[A]** Assumption — inferred, not verified (usually because it needs a live external service).

---

## 1. Repository inventory [V]

| Path | Lines | Role |
|---|---:|---|
| `app.py` | 211 | Entire backend: Flask app object, Gemini client, system prompt, routes |
| `templates/index.html` | 2586 | Entire frontend: HTML + inline CSS + inline JS + WebGL fluid background |
| `tests/conftest.py`, `tests/test_app.py` | 43 + 147 | 12 tests, all using a mocked Gemini client |
| `scripts/verify_environment.py` | 89 | Pre-flight check (Python version, packages, `GEMINI_API_KEY`) |
| `Dockerfile` | 40 | Single-stage `python:3.11-slim`, non-root user, curl healthcheck, Gunicorn |
| `docker-compose.yml` | 20 | One service (`forge`), port 5000, requires `.env` |
| `.github/workflows/ci.yml` | 41 | Ruff + pytest on Python 3.10 / 3.11 / 3.12 |
| `pyproject.toml` | 26 | Metadata + ruff/pytest config only; **not an installable package** (no packages declared) |
| `requirements.txt` | 5 | `flask==3.0.3`, `gunicorn==22.0.0`, `groq==0.5.0`, `httpx==0.27.0`, `python-dotenv`, `google-genai>=1.0.0` |
| `docs/*.md` | ~485 | api, architecture, deployment, setup |

Not present [V]: Python package structure, database, ORM, migrations, provider abstraction,
caching, budgets, structured logging, request IDs, frontend build tooling, frontend tests,
Nginx config, worker process, benchmark code.

## 2. Runtime architecture [V]

```text
Browser (templates/index.html, vanilla JS, Tailwind via CDN)
   │  POST /enhance {"prompt": str, "stream": bool=true}
   ▼
Flask module-level `app` (app.py) ── google.genai.Client (module-level, created at import)
   │  model = "gemma-4-31b-it" (hardcoded constant GEMMA_MODEL)
   │  system_instruction = _FORGE_ROLE, temperature 0.5, top_p 0.85, max_output_tokens 1280
   ▼
SSE frames or a JSON body
```

- `load_dotenv()` runs at import. If `GEMINI_API_KEY` is unset the module raises
  `ValueError` **at import time**, so the app, its tests and Gunicorn cannot start without
  a Gemini key. Reproduced: `import app` without the key → `ValueError: GEMINI_API_KEY is not set`.
- The non-streaming path (`enhance_prompt`) also calls the *streaming* SDK method and
  concatenates chunks.
- No timeouts, retries, rate limits, request-size limits, or logging are configured.
  Gunicorn `--timeout 120` is the only bound.

## 3. Existing API contracts (must stay backward compatible) [V]

### `GET /`
Renders `templates/index.html` (200, HTML).

### `GET /health`
```json
{"status": "ok", "templates_loaded": 0, "model": "gemma-4-31b-it"}
```
`templates_loaded` is a leftover from the removed 90-template architecture (commit
`d8bf830 update: removed templates`) and is always `0`. Used by the Dockerfile and
docker-compose health checks (status code only).

### `POST /enhance`
Request: `{"prompt": string (required, non-blank), "stream": bool (default true)}`.

| Case | Status | Body |
|---|---|---|
| blank / missing prompt | 400 | `{"error": "Empty prompt. Please send a non-empty 'prompt' field."}` |
| `stream: true` | 200 `text/event-stream` | `data: {"chunk": "..."}` frames, then `data: {"done": true}` |
| `stream: true`, provider error | 200 (stream already open) | `data: {"error": "<raw exception text>"}` |
| `stream: false`, success | 200 JSON | `success, template_id "", template_name "", template_matched "Direct Enhancement", domain "General", confidence "98%", score 0.98, enhanced_prompt, result, raw` |
| `stream: false`, provider error | 500 JSON | `success false, template_id "ERROR", template_matched "Error", confidence "N/A", score 0, enhanced_prompt/result/raw = "Error: <raw exception text>"` |

Notes:
- Streaming output is **not** passed through `_clean_output`; only the non-streaming path is
  cleaned. The frontend uses streaming only, so the cleaner never runs for UI users.
- Raw exception strings are returned to the client in both paths (information leakage risk).
- No request body size limit (the UI enforces a client-side `MAX_CHARS`; the server does not).

## 4. Data formats and persistence [V]

- No server-side persistence of any kind. Nothing survives a restart; there is nothing to migrate.
- Frontend: no `localStorage` use. Clipboard export as Markdown or JSON.

## 5. Misleading or fake values [V]

| Item | Where | Actual use |
|---|---|---|
| `confidence: "98%"`, `score: 0.98` | `app.py` `enhance_prompt` | Hardcoded constants; not computed from anything. |
| `defaultMeta = {..., confidence: "98%", score: 0.98}` | `index.html:1611` | `setMeta()` is a no-op, so nothing is displayed — **but** `defaultMeta` becomes `latestOutputData`, so **"Copy as JSON" exports the fake metadata and omits the enhanced prompt** (bug). |
| `domain: "General"`, `template_matched: "Direct Enhancement"` | API + UI | Static labels, not classification results. |
| `templates_loaded: 0` | `/health` | Leftover field, always 0. |
| README "~15 000 tokens vs ~200–300 tokens" | README, app.py docstring, docs | Not measured anywhere in the repo. |
| README "Tests Passing (12/12)" badge | README | Static image; not wired to CI. Currently true. |
| README "Multi-stage Dockerfile", "asynchronous ... Flask backend" | README | Dockerfile is single-stage; Flask is synchronous WSGI. |
| `_FORGE_ROLE` "must be 3–10× more detailed" | system prompt | A design choice, not a validated property; conflicts with FORGE 2.0's "longer ≠ better" principle. Retained only as the *current-FORGE* baseline. |

## 6. Dependencies [V]

| Package | Status |
|---|---|
| `flask`, `gunicorn`, `python-dotenv`, `google-genai` | Used |
| `groq==0.5.0` | **Unused** — not imported anywhere (grep-verified). Leftover from the original Groq implementation in early commits. |
| `httpx==0.27.0` | Not imported directly (transitive dependency of `google-genai`). |
| `pytest-asyncio` | Installed in dev requirements; no async tests exist. |
| No lockfile | Builds are not reproducible across time (`python-dotenv`, `google-genai>=1.0.0` unpinned). |

Locally installed (global Python 3.11.0) [V]: SQLAlchemy 2.1.1, Alembic 1.20.0,
psycopg 3.3.6 (+binary), pydantic 2.13.3, mypy 1.9.0, ruff 0.3.5, pytest 8.1.1.

## 7. Tests and checks — baseline results [V]

Run on 2026-10-12, before any change:

| Command | Result |
|---|---|
| `python -m pytest -v --tb=short` | **12 passed**, 0 failed, 0 skipped (0.23 s) |
| `python -m ruff check .` | **All checks passed** |
| `python -m ruff format --check .` | 4 files would be reformatted (not enforced in CI) |
| `import app` without `GEMINI_API_KEY` | **Fails** with `ValueError` at import |

What the 12 tests cover: prompt builder text, `_clean_output`, success/failure of
`enhance_prompt`, `/`, `/health`, `/enhance` (400, JSON success, JSON 500, SSE success,
SSE error). All provider calls are mocked by monkeypatching
`app.client.models.generate_content_stream`. No test exercises a real model, timeouts,
large inputs, or the frontend.

## 8. Deployment constraints [V unless noted]

- Render (and documented Railway/Fly.io) deployment: build `pip install -r requirements.txt`,
  start `gunicorn --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 120 app:app`.
  **The `app:app` import path and `requirements.txt` install must keep working.**
- Dockerfile: port 10000 default, non-root `forgeuser`, `HEALTHCHECK curl /health`.
- Whether a Render service is currently live is **[A] unknown**; not checked.
- Whether `gemma-4-31b-it` is currently served by the Gemini API for this key is **[A] unverified**
  (no real call made during the audit).

## 9. Local environment observed during audit [V]

- Python 3.11.0 (also 3.14 available via `py`), Node 24.15 / npm 11.12.
- Docker 29.5.2 + Compose 5.1.3 installed; **daemon not running**.
- ~~No native PostgreSQL install.~~ **Correction (increment 4):** a native PostgreSQL 18
  Windows service (`postgresql-x64-18`) listens on port 5432; the audit only checked for
  `psql` on `PATH`. It is the owner's and is not used by FORGE (see ADR-016).
- Ollama 0.32.5 installed; **server not running**.
- `.env` exists (untracked) and defines `GROQ_API_KEY` and `GEMINI_API_KEY` (values not read).

## 10. Security findings [V]

1. **Secrets in git history.** Commits `e14496a`, `db4ec65`, `6d743c3` contain hardcoded
   Groq API keys (3 distinct keys), removed in `d9a480a`. The history is pushed to
   `origin` (`github.com/anonymus-k-dot/forge`). The current `.env` Groq key does **not**
   match any of them (compared by SHA-256, values never printed). **Action for the owner:
   revoke those three keys in the Groq console if not already done.** Rewriting public
   history is out of scope and not attempted.
2. Raw exception text is returned to clients.
3. No server-side request size limit.
4. Frontend escapes `& < >` before inline-markdown substitution; no XSS path was found in the
   output renderer during a focused review [V for the reviewed functions only].
5. Tailwind is loaded from a CDN script at runtime (`cdn.tailwindcss.com`) — a supply-chain
   and CSP consideration, acceptable for the legacy UI.

## 11. Compatibility requirements

Must remain working until a verified replacement exists:

1. `POST /enhance` request schema, SSE frame format (`chunk` / `done` / `error`), JSON
   response field names, and status codes (400 / 200 / 500).
2. `GET /health` returning 200 with `status: "ok"` (container health checks).
3. `GET /` serving the existing UI, including streaming display and copy-to-clipboard.
4. `gunicorn app:app` and `pip install -r requirements.txt` deployment path.
5. The default enhancement behavior: same system prompt, same model ID, same generation
   parameters when only `GEMINI_API_KEY` is configured.

## 12. Removable after verification

| Item | Condition |
|---|---|
| `confidence`, `score` fields | Fabricated values. Removal is an explicit API change (see ADR-009). |
| `groq` dependency | Unused; Groq becomes reachable via the OpenAI-compatible adapter instead. |
| `pytest-asyncio` | No async tests. |
| `templates_loaded` | Kept (harmless, part of `/health` contract) and documented as deprecated. |
| Unverified token-savings claims in README/docs | Replace with measured numbers or remove. |
