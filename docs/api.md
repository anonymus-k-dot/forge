# FORGE API Specification

This document details the REST API endpoints provided by the FORGE application.

---

## Base URL

```text
http://localhost:5000
```

---

## Endpoints

### 1. Render Application UI

Returns the single-page application interface.

- **URL**: `/`
- **Method**: `GET`
- **Content-Type**: `text/html; charset=utf-8`
- **Response**: `200 OK` (HTML Document)

---

### 2. Health & Liveness Check

Returns the operational status of the service, template count, and active model identifier.

- **URL**: `/health`
- **Method**: `GET`
- **Response**: `200 OK`
- **Response Headers**: `Content-Type: application/json`

#### Example Response
```json
{
  "status": "ok",
  "templates_loaded": 0,
  "model": "gemma-4-31b-it"
}
```

---

### 3. Enhance Prompt

Submits a raw user prompt for AI refinement and structuring. Supports both Server-Sent Events (SSE) streaming and synchronous JSON response modes.

- **URL**: `/enhance`
- **Method**: `POST`
- **Request Headers**: `Content-Type: application/json`

#### Request Schema

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `prompt` | `string` | **Yes** | — | Raw prompt text to enhance. Must be non-empty. |
| `stream` | `boolean` | No | `true` | When `true`, returns an SSE stream. When `false`, returns a JSON object. |

#### Request Example (Streaming)
```json
{
  "prompt": "Create a python script to analyze log files and detect anomalies.",
  "stream": true
}
```

#### Request Example (Non-Streaming)
```json
{
  "prompt": "Create a python script to analyze log files and detect anomalies.",
  "stream": false
}
```

---

#### Response — Streaming Mode (`stream: true`)

- **Status Code**: `200 OK`
- **Content-Type**: `text/event-stream`

Streamed event chunks are formatted as SSE data frames:

```text
data: {"chunk": "Act as a senior DevOps engineer and Python developer. "}

data: {"chunk": "Develop a high-performance log analysis tool capable of parsing standard Apache and Nginx access logs..."}

data: {"done": true}
```

If an error occurs mid-stream:
```text
data: {"error": "Error description"}
```

---

#### Response — Non-Streaming Mode (`stream: false`)

- **Status Code**: `200 OK`
- **Content-Type**: `application/json`

```json
{
  "confidence": "98%",
  "domain": "General",
  "enhanced_prompt": "Act as a senior DevOps engineer and Python developer...\n\n### Objective\nDevelop a modular log anomaly detection script...",
  "raw": "Act as a senior DevOps engineer and Python developer...\n\n### Objective\nDevelop a modular log anomaly detection script...",
  "result": "Act as a senior DevOps engineer and Python developer...\n\n### Objective\nDevelop a modular log anomaly detection script...",
  "score": 0.98,
  "success": true,
  "template_id": "",
  "template_matched": "Direct Enhancement",
  "template_name": ""
}
```

---

#### Error Responses

##### 400 Bad Request (Missing or Empty Prompt)
```json
{
  "error": "Empty prompt. Please send a non-empty 'prompt' field."
}
```

##### 500 Internal Server Error (Upstream API Failure in Non-Streaming Mode)
```json
{
  "confidence": "N/A",
  "enhanced_prompt": "Error: Connection timeout from upstream provider",
  "raw": "Error: Connection timeout from upstream provider",
  "result": "Error: Connection timeout from upstream provider",
  "score": 0,
  "success": false,
  "template_id": "ERROR",
  "template_matched": "Error"
}
```
