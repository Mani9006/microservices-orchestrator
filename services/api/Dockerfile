# =============================================================================
# Containerized Microservices Orchestrator - API Service
# =============================================================================
# Multi-stage build for optimized production image
# Stage 1: Builder - installs dependencies and compiles requirements
# Stage 2: Production - minimal runtime image with security hardening
# =============================================================================

# ---------------------------------------------------------------------------
# STAGE 1: Builder
# ---------------------------------------------------------------------------
FROM python:3.11-slim AS builder

# Set environment variables for Python behavior
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install build dependencies for compiling Python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Create a virtual environment for isolation
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install Python dependencies
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# ---------------------------------------------------------------------------
# STAGE 2: Production
# ---------------------------------------------------------------------------
FROM python:3.11-slim AS production

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONFAULTHANDLER=1 \
    APP_HOME=/app \
    PATH="/opt/venv/bin:$PATH" \
    # Default to production; override for development
    FLASK_ENV=production \
    APP_PORT=5000

# Create a non-root user for security
RUN groupadd --gid 1000 appuser && \
    useradd --uid 1000 --gid appuser --shell /bin/false --create-home appuser

# Install only runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Copy virtual environment from builder stage
COPY --from=builder /opt/venv /opt/venv

# Set working directory
WORKDIR ${APP_HOME}

# Copy application source code with proper ownership
COPY --chown=appuser:appuser src/ ./src/
COPY --chown=appuser:appuser tests/ ./tests/

# Switch to non-root user
USER appuser

# Expose the application port
EXPOSE ${APP_PORT}

# Health check to verify API responsiveness
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${APP_PORT}/health || exit 1

# Graceful shutdown handling with proper signal forwarding
STOPSIGNAL SIGTERM

# Start the application using Gunicorn WSGI server
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "4", \
     "--worker-class", "sync", "--access-logfile", "-", \
     "--error-logfile", "-", "--capture-output", \
     "--enable-stdio-inheritance", "--timeout", "30", \
     "--graceful-timeout", "10", "--keep-alive", "2", \
     "src.app:create_app()"]

# ---------------------------------------------------------------------------
# STAGE 3: Development (extends production with hot-reload)
# ---------------------------------------------------------------------------
FROM production AS development

# Switch back to root to install dev dependencies
USER root

# Install development and debugging tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    vim \
    && rm -rf /var/lib/apt/lists/*

# Install development Python packages
RUN pip install --no-cache-dir \
    pytest \
    pytest-cov \
    black \
    flake8 \
    mypy \
    debugpy

# Switch back to appuser
USER appuser

# Override environment for development
ENV FLASK_ENV=development \
    FLASK_DEBUG=1

# Use Flask development server with hot-reload for local development
CMD ["flask", "--app", "src/app.py", "run", "--host=0.0.0.0", "--port=5000", "--reload"]
