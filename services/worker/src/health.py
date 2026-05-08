#!/usr/bin/env python3
# =============================================================================
# Worker Service - Health Check Server
# =============================================================================
# This module implements a lightweight Flask health check server for the
# worker service. It runs alongside the Celery worker to provide HTTP
# endpoints for load balancers and orchestrators to verify worker health.
# =============================================================================

import os
import sys
import time
import socket
import logging
import threading
from datetime import datetime, timezone
from typing import Dict, Any, Tuple

from flask import Flask, jsonify
from redis import Redis, ConnectionError, TimeoutError
from celery.app.control import Control

# ---------------------------------------------------------------------------
# Logging Configuration
# ---------------------------------------------------------------------------

def configure_logging() -> logging.Logger:
    """Configure structured logging for the health server."""
    logger = logging.getLogger("worker.health")
    logger.setLevel(logging.INFO)
    
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s - %(message)s"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    
    return logger


logger = configure_logging()

# ---------------------------------------------------------------------------
# Flask Health Check Application
# ---------------------------------------------------------------------------

def create_health_app() -> Flask:
    """Create the Flask health check application.
    
    Returns:
        Configured Flask application for health checks.
    """
    app = Flask(__name__)
    
    # -----------------------------------------------------------------------
    # Configuration
    # -----------------------------------------------------------------------
    app.config["REDIS_URL"] = os.getenv("REDIS_URL", "redis://redis:6379/0")
    app.config["CELERY_BROKER_URL"] = os.getenv("CELERY_BROKER_URL", app.config["REDIS_URL"])
    app.config["HEALTH_PORT"] = int(os.getenv("WORKER_PORT", "5001"))
    
    # Track application start time for uptime calculation
    _APP_START_TIME = time.time()
    
    def get_uptime() -> float:
        """Calculate worker uptime in seconds."""
        return time.time() - _APP_START_TIME
    
    def format_duration(seconds: float) -> str:
        """Format duration in human-readable format."""
        if seconds < 60:
            return f"{seconds:.0f}s"
        elif seconds < 3600:
            return f"{seconds / 60:.0f}m"
        elif seconds < 86400:
            return f"{seconds / 3600:.1f}h"
        else:
            return f"{seconds / 86400:.1f}d"
    
    # -----------------------------------------------------------------------
    # Health Check Functions
    # -----------------------------------------------------------------------
    
    def check_redis() -> Dict[str, Any]:
        """Check Redis broker connectivity."""
        result = {
            "component": "redis_broker",
            "status": "unhealthy",
            "response_time_ms": None,
            "message": ""
        }
        
        try:
            start = time.time()
            client = Redis.from_url(
                app.config["REDIS_URL"],
                socket_connect_timeout=5,
                socket_timeout=5
            )
            client.ping()
            info = client.info()
            client.close()
            
            elapsed_ms = (time.time() - start) * 1000
            
            result["status"] = "healthy"
            result["response_time_ms"] = round(elapsed_ms, 2)
            result["message"] = "Redis broker connection successful"
            result["redis_version"] = info.get("redis_version", "unknown")
            
        except ConnectionError as e:
            result["message"] = f"Redis connection failed: {str(e)}"
            logger.warning(f"Health check: Redis connection failed: {e}")
        except TimeoutError as e:
            result["status"] = "degraded"
            result["message"] = f"Redis connection timeout: {str(e)}"
            logger.warning(f"Health check: Redis timeout: {e}")
        except Exception as e:
            result["message"] = f"Unexpected error: {str(e)}"
            logger.error(f"Health check: Redis error: {e}")
        
        return result
    
    def check_celery() -> Dict[str, Any]:
        """Check Celery worker status."""
        result = {
            "component": "celery_worker",
            "status": "unhealthy",
            "message": ""
        }
        
        try:
            # We can't easily inspect ourselves, so we check if we can
            # connect to the broker, which is the critical dependency
            redis_check = check_redis()
            
            if redis_check["status"] == "healthy":
                result["status"] = "healthy"
                result["message"] = "Celery worker broker connection active"
                result["hostname"] = os.getenv("HOSTNAME", "unknown")
                result["concurrency"] = os.getenv("CELERY_WORKER_CONCURRENCY", "4")
            else:
                result["message"] = "Broker unavailable, worker may be offline"
                
        except Exception as e:
            result["message"] = f"Celery check error: {str(e)}"
        
        return result
    
    def check_system_resources() -> Dict[str, Any]:
        """Check system resource availability."""
        result = {
            "component": "system_resources",
            "status": "healthy",
            "message": "Resources available"
        }
        
        try:
            import psutil
            
            memory = psutil.virtual_memory()
            cpu_percent = psutil.cpu_percent(interval=0.5)
            disk = psutil.disk_usage("/")
            
            result["memory"] = {
                "total_mb": round(memory.total / (1024 * 1024)),
                "available_mb": round(memory.available / (1024 * 1024)),
                "percent_used": memory.percent
            }
            result["cpu"] = {"percent_used": cpu_percent}
            result["disk"] = {
                "total_gb": round(disk.total / (1024 ** 3)),
                "free_gb": round(disk.free / (1024 ** 3)),
                "percent_used": round((disk.used / disk.total) * 100, 1)
            }
            
            # Flag degraded if memory or disk is critical
            if memory.percent > 90 or disk.percent > 90:
                result["status"] = "degraded"
                result["message"] = "Critical resource usage detected"
            elif memory.percent > 80 or disk.percent > 80:
                result["status"] = "degraded"
                result["message"] = "High resource usage detected"
                
        except ImportError:
            result["message"] = "psutil not available, skipping resource check"
        except Exception as e:
            result["status"] = "degraded"
            result["message"] = f"Resource check error: {str(e)}"
        
        return result
    
    # -----------------------------------------------------------------------
    # Health Check Endpoints
    # -----------------------------------------------------------------------
    
    @app.route("/health", methods=["GET"])
    def basic_health() -> Tuple[dict, int]:
        """Basic health endpoint for load balancer probes.
        
        Returns:
            Simple health status with 200 OK.
        """
        return jsonify({
            "status": "healthy",
            "service": "worker",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }), 200
    
    @app.route("/health/ready", methods=["GET"])
    def readiness_check() -> Tuple[dict, int]:
        """Readiness check: verify all dependencies are available.
        
        Returns:
            200 if ready, 503 if critical dependencies are down.
        """
        checks = {
            "redis_broker": check_redis(),
            "celery_worker": check_celery(),
            "system_resources": check_system_resources()
        }
        
        # Redis is critical; other checks are warnings
        overall = "healthy" if checks["redis_broker"]["status"] == "healthy" else "unhealthy"
        status_code = 200 if overall == "healthy" else 503
        
        return jsonify({
            "status": overall,
            "service": "worker",
            "uptime_seconds": round(get_uptime(), 2),
            "uptime_human": format_duration(get_uptime()),
            "checks": checks,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }), status_code
    
    @app.route("/health/live", methods=["GET"])
    def liveness_check() -> Tuple[dict, int]:
        """Liveness check: verify the process is responsive.
        
        Returns:
            200 OK if the process is alive.
        """
        return jsonify({
            "status": "alive",
            "service": "worker",
            "uptime_seconds": round(get_uptime(), 2),
            "uptime_human": format_duration(get_uptime()),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }), 200
    
    @app.route("/health/metrics", methods=["GET"])
    def prometheus_metrics() -> Tuple[str, int]:
        """Prometheus metrics endpoint.
        
        Returns:
            Metrics in Prometheus text format.
        """
        uptime = get_uptime()
        
        try:
            import psutil
            memory = psutil.virtual_memory()
            memory_used = memory.percent
            cpu = psutil.cpu_percent(interval=0.1)
        except:
            memory_used = 0
            cpu = 0
        
        metrics = f"""# HELP worker_uptime_seconds Worker uptime in seconds
# TYPE worker_uptime_seconds gauge
worker_uptime_seconds {uptime:.2f}

# HELP worker_info Worker information
# TYPE worker_info gauge
worker_info{{version="1.0.0"}} 1

# HELP worker_memory_usage_percent Memory usage percentage
# TYPE worker_memory_usage_percent gauge
worker_memory_usage_percent {memory_used}

# HELP worker_cpu_usage_percent CPU usage percentage
# TYPE worker_cpu_usage_percent gauge
worker_cpu_usage_percent {cpu}
"""
        return metrics, 200, {"Content-Type": "text/plain; charset=utf-8"}
    
    @app.route("/", methods=["GET"])
    def index() -> Tuple[dict, int]:
        """Root endpoint with service information."""
        return jsonify({
            "service": "microservices-worker",
            "version": "1.0.0",
            "status": "operational",
            "endpoints": {
                "health": "/health",
                "ready": "/health/ready",
                "live": "/health/live",
                "metrics": "/health/metrics"
            }
        }), 200
    
    return app


# ---------------------------------------------------------------------------
# Standalone Server Runner
# ---------------------------------------------------------------------------

def run_health_server():
    """Run the health check server as a standalone process.
    
    This function can be called from a separate thread or process
    to run the health check server alongside the Celery worker.
    """
    app = create_health_app()
    port = int(os.getenv("WORKER_PORT", "5001"))
    
    logger.info(f"Starting health check server on port {port}")
    
    app.run(
        host="0.0.0.0",
        port=port,
        debug=False,
        threaded=True
    )


def run_health_server_threaded():
    """Run the health check server in a background thread.
    
    This is useful when running the health server alongside
    the Celery worker in the same container.
    """
    thread = threading.Thread(target=run_health_server, daemon=True)
    thread.start()
    logger.info("Health check server started in background thread")
    return thread


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    run_health_server()
