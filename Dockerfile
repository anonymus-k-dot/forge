# syntax=docker/dockerfile:1
FROM python:3.11-slim as base

# Prevents Python from writing pyc files to disc & prevents buffering stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=5000

WORKDIR /app

# Install system dependencies if required
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create non-root user for enhanced security
RUN useradd -m -u 1000 forgeuser && \
    chown -R forgeuser:forgeuser /app

USER forgeuser

EXPOSE 5000

# Healthcheck against Flask /health route
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:5000/health || exit 1

# Production WSGI execution with Gunicorn (threaded for SSE streaming support)
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--threads", "4", "--timeout", "120", "app:app"]
