# FORGE Development & Setup Guide

This guide walks through setting up the **FORGE** environment locally for development and testing.

---

## 1. Prerequisites

- **Python**: Version 3.10, 3.11, or 3.12.
- **Git**: For version control.
- **Google Gemini API Key**: Accessible via [Google AI Studio](https://aistudio.google.com/).

---

## 2. Local Installation

### Step 1: Clone the Repository
```bash
git clone https://github.com/your-username/forge.git
cd forge
```

### Step 2: Create and Activate a Virtual Environment
```bash
# macOS/Linux
python3 -m venv .venv
source .venv/bin/activate

# Windows (Command Prompt)
python -m venv .venv
.venv\Scripts\activate.bat

# Windows (PowerShell)
python -m venv .venv
.venv\Scripts\Activate.ps1
```

### Step 3: Install Dependencies
```bash
# Production dependencies
pip install -r requirements.txt

# Or development & test dependencies (includes pytest & ruff)
pip install -r requirements-dev.txt
```

---

## 3. Environment Configuration

1. Copy the example configuration template:
   ```bash
   cp .env.example .env
   ```
2. Open `.env` and add your Google Gemini API key:
   ```env
   GEMINI_API_KEY=AIzaSyYourActualKeyHere
   PORT=5000
   FLASK_DEBUG=true
   ```

---

## 4. Pre-Flight Verification

Run the pre-flight verification script to ensure your environment is configured correctly:

```bash
python scripts/verify_environment.py
```

Expected output:
```text
============================================================
 FORGE - Environment & System Pre-flight Verification
============================================================
[OK] Python version: 3.11.0 (win32)
[OK] Package available: flask
[OK] Package available: gunicorn
[OK] Package available: google.genai
[OK] Package available: dotenv
[OK] UI template found: index.html (89,863 bytes)
[OK] GEMINI_API_KEY is configured (Value: AIza...xxxx)
------------------------------------------------------------
>>> SUCCESS: Environment is ready. You can run 'python app.py'
```

---

## 5. Running the Application

### Development Server
```bash
python app.py
```
Open your browser and navigate to:
```text
http://localhost:5000
```

### Production WSGI Server (Gunicorn)
```bash
gunicorn --bind 0.0.0.0:5000 --workers 2 --threads 4 --timeout 120 app:app
```

---

## 6. Running Tests & Linting

### Run Unit & Integration Tests
```bash
pytest -v
```

### Run Linter
```bash
ruff check .
```

---

## 7. Troubleshooting

| Issue | Cause | Solution |
|---|---|---|
| `ValueError: GEMINI_API_KEY is not set.` | Missing API key in environment or `.env` | Ensure `.env` exists in root and contains a valid `GEMINI_API_KEY`. |
| `ImportError: No module named 'google.genai'` | Missing SDK dependency | Run `pip install -r requirements.txt`. |
| Port 5000 already in use | Another service is using port 5000 | Set `PORT=5001` or run `python app.py` on another port. |
| SSE stream freezes | Proxy or buffering intermediary | Ensure reverse proxies (like Nginx) have `proxy_buffering off;`. |
