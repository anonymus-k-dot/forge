# syntax=docker/dockerfile:1

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