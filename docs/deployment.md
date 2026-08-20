# FORGE Production Deployment Guide

This guide covers deploying **FORGE** in production environments using Docker, Gunicorn, and containerized platforms.

---

## 1. Docker Deployment

### 1.1 Building the Docker Image

The repository includes a production-optimized `Dockerfile` configured with a non-root user and an automated health check:

```bash
docker build -t forge:latest .
```

### 1.2 Running the Container

Run the container by passing your `GEMINI_API_KEY`:

```bash
docker run -d \
  --name forge_app \
  -p 5000:5000 \
  -e GEMINI_API_KEY="your_gemini_api_key_here" \
  --restart unless-stopped \
  forge:latest
```

Verify the container status and health check:
```bash
docker ps
```

---

## 2. Docker Compose Deployment

To manage the application lifecycle using Docker Compose:

1. Ensure `.env` contains your `GEMINI_API_KEY`.
2. Start the service in the background:
   ```bash
   docker compose up -d --build
   ```
3. Check container logs:
   ```bash
   docker compose logs -f
   ```
4. Stop the service:
   ```bash
   docker compose down
   ```

---

## 3. Production WSGI Configuration (Gunicorn)

FORGE utilizes **Server-Sent Events (SSE)** for real-time prompt streaming. When configuring Gunicorn:

- **Worker Class & Threads**: Use threaded workers (`--threads 4`) or async workers (`gevent` / `eventlet`) to avoid blocking single-process worker loops during streaming connections.
- **Timeout**: Set `--timeout 120` or higher to prevent premature worker termination during long generations.

Example command:
```bash
gunicorn --bind 0.0.0.0:5000 --workers 2 --threads 4 --timeout 120 app:app
```

---

## 4. Reverse Proxy Setup (Nginx)

When placing FORGE behind an Nginx reverse proxy, disable proxy buffering for SSE streaming to work properly:

```nginx
server {
    listen 80;
    server_name forge.yourdomain.com;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Critical settings for Server-Sent Events (SSE) streaming:
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 120s;
        proxy_http_version 1.1;
        proxy_set_header Connection '';
        chunked_transfer_encoding on;
    }
}
```

---

## 5. Cloud Platform Deployments

### Render / Railway / Fly.io

1. **Build Command**: `pip install -r requirements.txt`
2. **Start Command**: `gunicorn --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 120 app:app`
3. **Environment Variables**:
   - `GEMINI_API_KEY`: Set as a secret in your platform dashboard.
   - `PORT`: Handled automatically by the platform or defaults to 5000.
