# Build stage
FROM python:3.12-alpine AS builder

WORKDIR /build

# Install build deps (only what pip needs to compile wheels)
RUN apk add --no-cache gcc musl-dev libffi-dev

COPY app/requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# Runtime stage
FROM python:3.12-alpine AS runtime

# Non-root user with explicit UID/GID
RUN addgroup -g 1001 -S appgroup \
 && adduser  -u 1001 -S appuser  -G appgroup

# Copy installed packages from builder
COPY --from=builder /install /usr/local

WORKDIR /app

# Application code
COPY app/ .

# Log directory owned by app user
RUN mkdir -p /logs && chown appuser:appgroup /logs

USER appuser

# Runtime ENV defaults (overridden at compose level)
ENV MODE=stable \
    APP_VERSION=1.0.0 \
    APP_PORT=3000 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 3000

HEALTHCHECK --interval=10s --timeout=5s --start-period=15s --retries=3 \
  CMD python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:'+__import__('os').environ.get('APP_PORT','3000')+'/healthz')"

# Gunicorn: 2 workers × 4 threads, port from env
CMD sh -c "gunicorn \
      --bind 0.0.0.0:${APP_PORT} \
      --workers 2 \
      --threads 4 \
      --timeout 120 \
      --access-logfile - \
      --error-logfile  - \
      main:app"
