# FORGE web frontend (React + TypeScript + Vite)

The new FORGE interface, served by Flask at **`/app/`** next to the classic interface at
`/` (unchanged). It talks to the existing `POST /enhance` streaming API; the backend was
not changed for it.

## Requirements

- Node.js 22.18 or newer (the unit tests run TypeScript directly with Node's built-in type
  stripping). Tested with Node 24.15 and npm 11.12.
- The Python environment from [docs/setup.md](../docs/setup.md) for Flask.

## Commands

All npm commands run in `web/`.

| Task | Command |
|---|---|
| Install the locked dependencies | `npm ci` |
| Type-check | `npm run typecheck` |
| Unit tests (stream parser, client, request lifecycle, validation, copy) | `npm test` |
| Production build → `web/dist` | `npm run build` (type-checks first) |
| Development server (hot reload) | `npm run dev` |

### Development

Run Flask and Vite side by side:

```bash
python app.py
```

```bash
cd web && npm run dev
```

Open http://127.0.0.1:5173/app/. Vite forwards `/enhance` and `/health` to Flask at
`http://127.0.0.1:5000` (streaming is passed through as it arrives). For another backend
address set `FORGE_API_ORIGIN`, for example in `web/.env.local` (ignored by Git):

```text
FORGE_API_ORIGIN=http://127.0.0.1:8000
```

No secrets are needed or read by the frontend; provider keys stay in the backend's `.env`.

### Production build served by Flask

```bash
cd web && npm ci && npm run build
```

Then start Flask (`python app.py` or `gunicorn app:app`) and open http://localhost:5000/app/.
`web/dist` is not committed. Without a build, `/app/` returns a 404 page explaining how to
build; nothing else is affected.

### Integration and browser tests

From the repository root:

```bash
pytest tests/test_web_frontend.py
```

This covers the Flask routes (with a stand-in build), runs the unit tests, and, when
`web/dist` exists, checks the real build. A headless-Chrome check of the built app against
Flask with a scripted fake provider is opt-in (it starts Chrome; it uses no network):

```bash
FORGE_BROWSER_TESTS=1 pytest tests/test_web_frontend.py -k headless
```

Set `FORGE_CHROME` if Chrome, Chromium or Edge is not found, and `FORGE_BROWSER_OUT` to
keep the screenshots and log.

## Layout

```text
src/
  api/          sse.ts (incremental SSE parser), enhance.ts (POST /enhance client, errors)
  state/        enhancement.ts (request lifecycle reducer), session.ts (one request at a time, Stop)
  hooks/        useEnhancement, useAnnouncer (live region), useGlobalShortcuts
  components/   PromptEditor, EnhanceControls, OutputPanel, CopyMenu, ShortcutsDialog, Layout, Icon, ErrorBoundary
  utils/        prompt.ts (limits, validation), copy.ts (payloads, clipboard fallback), platform.ts
  styles/       tokens.css, base.css, app.css (local CSS only: no web fonts, icon fonts or CDNs)
tests/unit/     node:test suites (no test framework dependency)
tests/browser/  app.browser.mjs (DevTools-protocol driver, Node built-ins only)
```

## Behaviour notes

- Output is rendered as text only (never as HTML or Markdown); what is shown is what
  "Copy text" copies. Outer whitespace of the final result is trimmed, as in the classic UI.
- **Stop** cancels the browser request and keeps the partial output. Flask then closes the
  provider stream; whether the provider stops generating (and billing) is up to the
  provider, so the UI never claims the model was stopped.
- A failure after partial output keeps that output, marked incomplete. Nothing is retried
  automatically; "Try again" is a new request made by the user.
- The prompt must be 10–2,000 characters (counted as code points); the backend itself does
  not enforce a maximum.

## Deployment and CI

- **Docker:** the `Dockerfile`'s `web` stage (Node 24.15.0) runs `npm ci`, `npm test` and
  `npm run build`; only `web/dist` is copied into the Python image, at `/app/web/dist`.
  See [docs/deployment.md](../docs/deployment.md), including the Render build command for
  a non-Docker service.
- **CI:** the `frontend` job runs `npm ci`, `npm run typecheck`, `npm test`,
  `npm run build` and `pytest tests/test_web_frontend.py` with `FORGE_REQUIRE_WEB_BUILD=1`.
- The classic interface at `/` remains the default; there is no cutover.
