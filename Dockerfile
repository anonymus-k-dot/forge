# syntax=docker/dockerfile:1

# Build the React frontend (web/). Only its output, web/dist, is copied into the
# runtime image below: Node and node_modules never reach it. Node version as in CI.
FROM node:24.15.0-slim AS web

WORKDIR /web

# Locked dependencies first, so this layer is reused until package*.json change.
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund

# Unit tests, then the production build (`npm run build` type-checks first).
COPY web/ ./
RUN npm test && npm run build

FROM python:3.11-slim AS base

# Prevent Python from writing .pyc files
# and ensure logs are immediately visible.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install required system dependency for health checks.
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

# Install Python dependencies.
COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application source code.
COPY . .

# Compiled frontend, where Flask serves /app/ from (src/forge/api/web.py: web/dist
# under the application root).
COPY --from=web /web/dist ./web/dist

# Create a non-root user.
RUN useradd -m -u 1000 forgeuser && \
    chown -R forgeuser:forgeuser /app

USER forgeuser

# Render's default expected HTTP port is 10000.
EXPOSE 10000

# Container-level health check.
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${PORT:-10000}/health || exit 1

# Run Gunicorn.
# Use sh -c so ${PORT} is expanded at runtime.
CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:${PORT:-10000} --workers 2 --threads 4 --timeout 120 app:app"]