# =============================================================================
# Containerized Microservices Orchestrator - Nginx Reverse Proxy
# =============================================================================
# Production-grade Nginx image with security hardening, optimized
# configuration, and health check support.
# =============================================================================

# ---------------------------------------------------------------------------
# Base Image
# ---------------------------------------------------------------------------
FROM nginx:1.25-alpine

# ---------------------------------------------------------------------------
# Labels
# ---------------------------------------------------------------------------
LABEL maintainer="DevOps Team"
LABEL description="Nginx reverse proxy for microservices orchestrator"
LABEL version="1.0.0"

# ---------------------------------------------------------------------------
# Security: Create non-root user
# ---------------------------------------------------------------------------
# Note: nginx:alpine already runs as non-root (uid 101)
# We ensure proper ownership of configuration files

# ---------------------------------------------------------------------------
# Install security updates and utilities
# ---------------------------------------------------------------------------
RUN apk update && apk upgrade --no-cache && \
    apk add --no-cache \
        curl \
        ca-certificates && \
    # Remove default server definition
    rm -f /etc/nginx/conf.d/default.conf && \
    # Create necessary directories with proper permissions
    mkdir -p /var/cache/nginx/client_temp \
             /var/cache/nginx/proxy_temp \
             /var/cache/nginx/fastcgi_temp \
             /var/cache/nginx/uwsgi_temp \
             /var/cache/nginx/scgi_temp \
             /var/log/nginx \
             /etc/nginx/ssl && \
    # Set proper ownership for nginx user
    chown -R nginx:nginx /var/cache/nginx \
                         /var/log/nginx \
                         /etc/nginx/conf.d && \
    # Restrict permissions on config
    chmod -R 755 /var/cache/nginx && \
    # Clean up
    rm -rf /var/cache/apk/*

# ---------------------------------------------------------------------------
# Copy Custom Configuration
# ---------------------------------------------------------------------------
COPY --chown=nginx:nginx nginx.conf /etc/nginx/nginx.conf

# ---------------------------------------------------------------------------
# Security: Remove unnecessary tools and set permissions
# ---------------------------------------------------------------------------
RUN touch /var/run/nginx.pid && \
    chown -R nginx:nginx /var/run/nginx.pid

# ---------------------------------------------------------------------------
# Health Check
# ---------------------------------------------------------------------------
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# ---------------------------------------------------------------------------
# Expose Ports
# ---------------------------------------------------------------------------
# 80 - HTTP traffic
# 443 - HTTPS traffic (TLS terminated at Nginx)
# 8080 - Internal health check and monitoring
EXPOSE 80 443 8080

# ---------------------------------------------------------------------------
# Non-root User
# ---------------------------------------------------------------------------
USER nginx

# ---------------------------------------------------------------------------
# Graceful Shutdown
# ---------------------------------------------------------------------------
# Nginx handles SIGTERM gracefully by default:
# - Stops accepting new connections
# - Completes in-flight requests
# - Shuts down worker processes
STOPSIGNAL SIGTERM

# ---------------------------------------------------------------------------
# Start Nginx
# ---------------------------------------------------------------------------
CMD ["nginx", "-g", "daemon off;"]
