# =============================================================================
# Containerized Microservices Orchestrator - Worker Service
# =============================================================================
# Multi-stage build for the background worker service that processes
# asynchronous tasks using Celery with Redis as the message broker.
# =============================================================================

# ---------------------------------------------------------------------------
# STAGE 1: Builder
# ---------------------------------------------------------------------------
FROM python:3.11-slim AS builder

# Set Python environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment for isolation
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install Python dependencies
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# ---------------------------------------------------------------------------
# STAGE 2: Production
# ---------------------------------------------------------------------------
FROM python:3.11-slim AS production

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_HOME=/app \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONFAULTHANDLER=1 \
    CELERY_WORKER_CONCURRENCY=4 \
    CELERY_WORKER_PREFETCH_MULTIPLIER=1 \
    CELERY_TASK_TIME_LIMIT=300 \
    CELERY_TASK_SOFT_TIME_LIMIT=240

# Create non-root user for security
RUN groupadd --gid 1000 workeruser && \
    useradd --uid 1000 --gid workeruser --shell /bin/false --create-home workeruser

# Install runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv

# Set working directory
WORKDIR ${APP_HOME}

# Copy application source with proper ownership
COPY --chown=workeruser:workeruser src/ ./src/
COPY --chown=workeruser:workeruser tests/ ./tests/

# Switch to non-root user
USER workeruser

# Expose health check port
EXPOSE 5001

# Health check to verify worker process is responsive
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:5001/health || exit 1

# Graceful shutdown with SIGTERM
STOPSIGNAL SIGTERM

# Default command starts Celery worker
# Uses --uid to drop privileges, --without-heartbeat for clean shutdown
CMD ["celery", "-A", "src.worker", "worker", \
     "--loglevel=info", \
     "--concurrency=4", \
     "--prefetch-multiplier=1", \
     "--without-heartbeat", \
     "--without-gossip", \
     "--without-mingle", \
     "-Q", "default,high-priority,low-priority", \
     "-n", "worker@%h"]

# ---------------------------------------------------------------------------
# STAGE 3: Development
# ---------------------------------------------------------------------------
FROM production AS development

USER root

# Install development tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    vim \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir pytest pytest-cov black flake8

USER workeruser

# Development runs with more verbose logging
CMD ["celery", "-A", "src.worker", "worker", \
     "--loglevel=debug", \
     "--concurrency=2", \
     "-Q", "default,high-priority,low-priority", \
     "-n", "dev-worker@%h"]
