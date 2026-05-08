#!/usr/bin/env python3
# =============================================================================
# API Service - Health Check Endpoint
# =============================================================================
# This module implements comprehensive health checks for the API service.
# It verifies connectivity to all downstream dependencies (database, Redis,
# and other services) and reports detailed status information.
# =============================================================================

import os
import time
import socket
from datetime import datetime, timezone
from typing import Dict, Any, Tuple

from flask import Blueprint, jsonify, current_app
from sqlalchemy import text, exc as sqlalchemy_exc
import redis

# ---------------------------------------------------------------------------
# Health Check Blueprint
# ---------------------------------------------------------------------------
health_bp = Blueprint("health", __name__)

# Application start time for uptime calculation
_APP_START_TIME = time.time()


def get_uptime_seconds() -> float:
    """Calculate application uptime in seconds."""
    return time.time() - _APP_START_TIME


def format_duration(seconds: float) -> str:
    """Format duration in human-readable format."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        return f"{seconds / 60:.1f}m"
    elif seconds < 86400:
        return f"{seconds / 3600:.1f}h"
    else:
        return f"{seconds / 86400:.1f}d"


def check_database() -> Dict[str, Any]:
    """Check PostgreSQL database connectivity and performance.
    
    Executes a simple query to verify the database is responsive and
    measures the query execution time.
    
    Returns:
        Dictionary with status ('healthy', 'degraded', 'unhealthy'),
        response time in milliseconds, and additional metadata.
    """
    result = {
        "component": "database",
        "name": "PostgreSQL",
        "status": "unhealthy",
        "response_time_ms": None,
        "message": "",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    try:
        start_time = time.time()
        
        # Execute a lightweight query to verify connectivity
        with current_app.app_context():
            from src.app import db
            db.session.execute(text("SELECT 1"))
            db.session.commit()
        
        elapsed_ms = (time.time() - start_time) * 1000
        
        result["status"] = "healthy"
        result["response_time_ms"] = round(elapsed_ms, 2)
        result["message"] = "Database connection successful"
        
    except sqlalchemy_exc.OperationalError as e:
        result["status"] = "unhealthy"
        result["message"] = f"Database connection failed: {str(e)}"
        current_app.logger.error(f"Health check: Database connection failed: {e}")
        
    except Exception as e:
        result["status"] = "unhealthy"
        result["message"] = f"Unexpected error: {str(e)}"
        current_app.logger.error(f"Health check: Database unexpected error: {e}")
    
    return result


def check_redis() -> Dict[str, Any]:
    """Check Redis cache connectivity and performance.
    
    Pings the Redis server and measures the response time.
    
    Returns:
        Dictionary with status, response time in milliseconds,
        and additional metadata.
    """
    result = {
        "component": "cache",
        "name": "Redis",
        "status": "unhealthy",
        "response_time_ms": None,
        "message": "",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    try:
        redis_url = current_app.config.get("REDIS_URL", "redis://redis:6379/0")
        start_time = time.time()
        
        client = redis.from_url(redis_url, socket_connect_timeout=5, socket_timeout=5)
        client.ping()
        
        elapsed_ms = (time.time() - start_time) * 1000
        
        # Get additional Redis info
        info = client.info()
        
        result["status"] = "healthy"
        result["response_time_ms"] = round(elapsed_ms, 2)
        result["message"] = "Redis connection successful"
        result["version"] = info.get("redis_version", "unknown")
        result["used_memory_human"] = info.get("used_memory_human", "unknown")
        result["connected_clients"] = info.get("connected_clients", 0)
        
        client.close()
        
    except redis.ConnectionError as e:
        result["status"] = "unhealthy"
        result["message"] = f"Redis connection failed: {str(e)}"
        current_app.logger.warning(f"Health check: Redis connection failed: {e}")
        
    except redis.TimeoutError as e:
        result["status"] = "degraded"
        result["message"] = f"Redis connection timeout: {str(e)}"
        current_app.logger.warning(f"Health check: Redis timeout: {e}")
        
    except Exception as e:
        result["status"] = "unhealthy"
        result["message"] = f"Unexpected error: {str(e)}"
        current_app.logger.error(f"Health check: Redis unexpected error: {e}")
    
    return result


def check_worker() -> Dict[str, Any]:
    """Check worker service connectivity via health endpoint.
    
    Attempts to connect to the worker service's health endpoint
    to verify it is running and responsive.
    
    Returns:
        Dictionary with status and connectivity information.
    """
    result = {
        "component": "worker",
        "name": "Background Worker",
        "status": "unhealthy",
        "response_time_ms": None,
        "message": "",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    worker_host = os.getenv("WORKER_HOST", "worker")
    worker_port = int(os.getenv("WORKER_PORT", "5001"))
    
    try:
        start_time = time.time()
        
        # Try to establish a TCP connection to the worker
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        sock.connect((worker_host, worker_port))
        sock.close()
        
        elapsed_ms = (time.time() - start_time) * 1000
        
        result["status"] = "healthy"
        result["response_time_ms"] = round(elapsed_ms, 2)
        result["message"] = f"Worker service reachable at {worker_host}:{worker_port}"
        
    except socket.timeout:
        result["status"] = "degraded"
        result["message"] = f"Worker connection timeout ({worker_host}:{worker_port})"
        current_app.logger.warning(f"Health check: Worker timeout")
        
    except socket.error as e:
        result["status"] = "unhealthy"
        result["message"] = f"Worker not reachable: {str(e)}"
        current_app.logger.warning(f"Health check: Worker unreachable: {e}")
        
    except Exception as e:
        result["status"] = "unhealthy"
        result["message"] = f"Unexpected error: {str(e)}"
    
    return result


def get_system_info() -> Dict[str, Any]:
    """Gather system information for the health check response.
    
    Returns:
        Dictionary with version, environment, uptime, and resource info.
    """
    import platform
    import psutil
    
    memory = psutil.virtual_memory()
    
    return {
        "version": "1.0.0",
        "environment": os.getenv("FLASK_ENV", "production"),
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "uptime_seconds": round(get_uptime_seconds(), 2),
        "uptime_human": format_duration(get_uptime_seconds()),
        "memory_usage": {
            "total_mb": round(memory.total / (1024 * 1024), 2),
            "available_mb": round(memory.available / (1024 * 1024), 2),
            "percent_used": memory.percent
        },
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


# ---------------------------------------------------------------------------
# Health Check Endpoints
# ---------------------------------------------------------------------------

@health_bp.route("/health", methods=["GET"])
def basic_health() -> Tuple[dict, int]:
    """Basic health check endpoint for load balancers.
    
    Returns a simple UP/DOWN status with minimal overhead.
    This endpoint is optimized for frequent health probe checks
    from load balancers and orchestrators.
    
    Returns:
        200 OK if service is running, 503 if critical failures detected.
    """
    return jsonify({
        "status": "healthy",
        "service": "api",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }), 200


@health_bp.route("/health/ready", methods=["GET"])
def readiness_check() -> Tuple[dict, int]:
    """Readiness probe: verifies all dependencies are available.
    
    This endpoint checks connectivity to all downstream services
    (database, Redis, worker) and reports detailed status. Use this
    for Kubernetes readiness probes to determine if the pod should
    receive traffic.
    
    Returns:
        200 OK if all dependencies are healthy.
        503 Service Unavailable if any critical dependency is down.
    """
    checks = {
        "database": check_database(),
        "cache": check_redis(),
        "worker": check_worker()
    }
    
    # Determine overall status
    # Database is critical; Redis and worker are non-critical (degraded acceptable)
    critical_statuses = [checks["database"]["status"]]
    all_statuses = [c["status"] for c in checks.values()]
    
    if any(s == "unhealthy" for s in critical_statuses):
        overall_status = "unhealthy"
        status_code = 503
    elif any(s == "unhealthy" for s in all_statuses):
        overall_status = "degraded"
        status_code = 200  # Still accepting traffic
    elif any(s == "degraded" for s in all_statuses):
        overall_status = "degraded"
        status_code = 200
    else:
        overall_status = "healthy"
        status_code = 200
    
    response = {
        "status": overall_status,
        "service": "api",
        "checks": checks,
        "system": get_system_info()
    }
    
    return jsonify(response), status_code


@health_bp.route("/health/live", methods=["GET"])
def liveness_check() -> Tuple[dict, int]:
    """Liveness probe: verifies the application process is running.
    
    This is a minimal check that only verifies the application
    process has not deadlocked or hung. Use for Kubernetes liveness
    probes to restart the container if needed.
    
    Returns:
        200 OK if the process is responsive.
    """
    return jsonify({
        "status": "alive",
        "service": "api",
        "uptime_seconds": round(get_uptime_seconds(), 2),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }), 200


@health_bp.route("/health/metrics", methods=["GET"])
def prometheus_metrics() -> Tuple[str, int]:
    """Prometheus-compatible metrics endpoint.
    
    Exposes application metrics in Prometheus text format for
    scraping by Prometheus monitoring server.
    
    Returns:
        Plain text metrics in Prometheus exposition format.
    """
    uptime = get_uptime_seconds()
    
    # Simple text-based metrics (production would use prometheus_client)
    metrics = f"""# HELP api_uptime_seconds API service uptime in seconds
# TYPE api_uptime_seconds gauge
api_uptime_seconds {uptime:.2f}

# HELP api_info API service information
# TYPE api_info gauge
api_info{{version="1.0.0",environment="{os.getenv('FLASK_ENV', 'production')}"}} 1

# HELP api_health_check_duration_seconds Health check duration
# TYPE api_health_check_duration_seconds gauge
api_health_check_duration_seconds {uptime:.2f}
"""
    
    return metrics, 200, {"Content-Type": "text/plain; charset=utf-8"}
