# FORGE API Specification

This document describes the HTTP endpoints FORGE currently serves. It reflects the code as of
FORGE 2.0 Phase 0 Step 3; see [`CHANGELOG.md`](../CHANGELOG.md) for changes.

---

## Base URL

```text
http://localhost:5000
```

---

## Common behavior

### Request IDs (`X-Request-ID`)

Every response carries an `X-Request-ID` header.

- If the request includes `X-Request-ID` matching `^[A-Za-z0-9._-]{1,128}$`, that value is
  echoed back.
- Otherwise (missing, too long, or containing other characters) the server generates a new
  32-character hex ID. Invalid client values are never echoed or logged.
- The same ID appears as `request_id` in the server's JSON log lines for that request, so a
  client can quote it when reporting a problem.

Response bodies are unchanged; the ID is only in the header.

---

## Endpoints

### 1. Render Application UI

- **URL**: `/`
- **Method**: `GET`
- **Response**: `200 OK`, `text/html; charset=utf-8`

---

### 2. Health & Liveness Check

Process liveness only. Does not contact the model provider and works without credentials.

- **URL**: `/health`
- **Method**: `GET`
- **Response**: `200 OK`, `application/json`

```json
{
  "status": "ok",
  "templates_loaded": 0,
  "model": "gemma-4-31b-it"
}
```

| Field | Meaning |
|---|---|
| `status` | Always `"ok"` when the process is serving requests |
| `model` | Model ID of the default provider profile (configurable via `FORGE_PROVIDERS_FILE`) |
| `templates_loaded` | **Deprecated.** Leftover from the removed template library; always `0` |

---

### 3. Readiness Check

Whether the instance can serve persistence-backed features. Unlike `/health`, this contacts
PostgreSQL. It never returns connection details or error text.

- **URL**: `/ready`
- **Method**: `GET`
- **Response**: `200 OK` when ready, `503 Service Unavailable` otherwise, `application/json`

```json
{
  "status": "ready",
  "checks": { "database": "ok" }
}
```

| `checks.database` | Status | Meaning |
|---|---|---|
| `ok` | 200 | Connected, and the schema is at the migration head shipped with this code |
| `not_configured` | 503 | `DATABASE_URL` is not set |
| `unavailable` | 503 | Connection or authentication failed (details only in server logs, without credentials) |
| `migrations_pending` | 503 | Connected, but the schema is not at the shipped head; run `alembic upgrade head` |

When not ready, `status` is `"not_ready"`. `/` and `/health` do not depend on the database.

---

### 4. Enhance Prompt

Rewrites a raw prompt using the FORGE 1.x enhancement instructions, via the configured
default model. Supports Server-Sent Events (SSE) streaming and a single JSON response.
Every request is a fresh model call: `/enhance` never uses the response cache and is not
subject to run budgets (both apply to benchmark/evaluation runs only).

- **URL**: `/enhance`
- **Method**: `POST`
- **Request Headers**: `Content-Type: application/json`

#### Request Schema

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `prompt` | `string` | **Yes** | — | Raw prompt text to enhance. Must be non-blank. |
| `stream` | `boolean` | No | `true` | `true`: SSE stream. `false`: one JSON object. |

```json
{ "prompt": "Create a python script to analyze log files and detect anomalies.", "stream": true }
```

#### Response — Streaming (`stream: true`)

- **Status**: `200 OK`, `text/event-stream`

```text
data: {"chunk": "Act as a senior DevOps engineer and Python developer. "}

data: {"chunk": "Develop a log analysis tool..."}

data: {"done": true}
```

If generation fails — before or after the first chunk — the stream ends with a single error
frame (still HTTP 200, because headers have already been sent):

```text
data: {"error": "The model provider is currently unavailable. Please try again later."}
```

Streamed chunks are the model's raw output; the cleanup applied to the JSON response's
`enhanced_prompt` is not applied to the stream (unchanged FORGE 1.x behavior).

#### Response — Non-Streaming (`stream: false`)

- **Status**: `200 OK`, `application/json`

```json
{
  "success": true,
  "enhanced_prompt": "Act as a senior DevOps engineer and Python developer...",
  "result": "Act as a senior DevOps engineer and Python developer...",
  "raw": "Act as a senior DevOps engineer and Python developer...",
  "template_id": "",
  "template_name": "",
  "template_matched": "Direct Enhancement",
  "domain": "General",
  "confidence": null,
  "score": null
}
```

| Field | Meaning |
|---|---|
| `success` | `true` |
| `enhanced_prompt` | Enhanced prompt after output cleanup |
| `result` | Same as `enhanced_prompt` (kept for compatibility) |
| `raw` | Model output before cleanup |
| `confidence` | **Deprecated, always `null`.** Was the constant `"98%"`; never measured |
| `score` | **Deprecated, always `null`.** Was the constant `0.98`; never measured |
| `template_id`, `template_name`, `template_matched`, `domain` | **Deprecated static labels** (`""`, `""`, `"Direct Enhancement"`, `"General"`); not classification results |

Deprecated fields will be removed in a future release; see the deprecation schedule in
[`CHANGELOG.md`](../CHANGELOG.md).

---

#### Error Responses

##### 400 Bad Request — missing or blank prompt

Also returned for `"prompt": null` and for falsy bodies (`[]`, `""`, `0`, `false`), as in
FORGE 1.x.

```json
{ "error": "Empty prompt. Please send a non-empty 'prompt' field." }
```

##### 400 Bad Request — wrong JSON types

A body that is not a JSON object, or a `prompt` that is not a string. (Before this release
these crashed the route and returned a `500` HTML page.)

```json
{ "error": "Invalid request. Send a JSON object with a string 'prompt' field." }
```

`stream` is interpreted by JSON truthiness, unchanged from FORGE 1.x: for example the
*string* `"false"` is truthy and therefore streams. Send a JSON boolean.

##### 500 Internal Server Error — generation failed (non-streaming)

```json
{
  "success": false,
  "template_id": "ERROR",
  "template_matched": "Error",
  "confidence": null,
  "score": null,
  "enhanced_prompt": "Error: The model provider's rate limit was reached (rate_limit). Please wait and try again.",
  "result": "Error: The model provider's rate limit was reached (rate_limit). Please wait and try again.",
  "raw": "Error: The model provider's rate limit was reached (rate_limit). Please wait and try again."
}
```

Error messages are fixed, safe strings chosen by failure category; raw upstream error text is
never returned. Possible messages:

| Category | Message |
|---|---|
| configuration | e.g. `GEMINI_API_KEY is not set. Add it to your environment or .env file (provider 'gemini').` |
| authentication | `The model provider rejected the server's credentials.` |
| invalid_request | `The model provider rejected the request as invalid.` |
| rate_limit | `The model provider's rate limit was reached (rate_limit). Please wait and try again.` |
| unavailable | `The model provider is currently unavailable. Please try again later.` |
| unavailable (local limit) | `Too many requests are in progress for this model provider. Please try again shortly.` |
| timeout | `The model provider did not respond in time (timeout). Please try again.` |
| server_error | `The model provider returned a server error. Please try again later.` |
| malformed_response | `The model provider returned an invalid response.` |
| unsupported_capability | `The selected model does not support this request.` |
| unknown | `The model provider request failed unexpectedly.` |
| internal | `An internal error occurred while enhancing the prompt.` |

Transient failures (rate limits with a short `Retry-After`, 5xx, timeouts, connection errors)
are retried up to twice by the server before an error is returned.
