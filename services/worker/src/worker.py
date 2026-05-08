#!/usr/bin/env python3
# =============================================================================
# Worker Service - Celery Application Configuration
# =============================================================================
# This module configures the Celery application instance with Redis as the
# message broker and result backend. It defines task routing, queues, beat
# scheduler configuration, and error handling hooks.
# =============================================================================

import os
import sys
import logging
from datetime import datetime, timezone

from celery import Celery
from celery.signals import (
    task_prerun, task_postrun, task_failure, task_success,
    worker_ready, worker_shutdown
)
from kombu import Queue, Exchange

# ---------------------------------------------------------------------------
# Logging Configuration
# ---------------------------------------------------------------------------

def configure_logging() -> logging.Logger:
    """Configure structured logging for the worker service.
    
    Returns:
        Configured logger instance for the worker.
    """
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    log_format = os.getenv("LOG_FORMAT", "json").lower()
    
    logger = logging.getLogger("worker")
    logger.setLevel(getattr(logging, log_level, logging.INFO))
    
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        
        if log_format == "json":
            from pythonjsonlogger import jsonlogger
            formatter = jsonlogger.JsonFormatter(
                "%(asctime)s %(levelname)s %(name)s %(message)s"
            )
        else:
            formatter = logging.Formatter(
                "%(asctime)s [%(levelname)s] %(name)s - %(message)s"
            )
        
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    
    return logger


logger = configure_logging()

# ---------------------------------------------------------------------------
# Celery Application Factory
# ---------------------------------------------------------------------------

def create_celery_app() -> Celery:
    """Create and configure the Celery application instance.
    
    Configures broker (Redis), result backend, task routing, queues,
    serialization, and retry policies.
    
    Returns:
        Configured Celery application instance.
    """
    # Get configuration from environment
    redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
    broker_url = os.getenv("CELERY_BROKER_URL", redis_url)
    result_backend = os.getenv("CELERY_RESULT_BACKEND", redis_url)
    
    # Create Celery app
    app = Celery("microservices-worker")
    
    # -----------------------------------------------------------------------
    # Broker and Backend Configuration
    # -----------------------------------------------------------------------
    app.conf.broker_url = broker_url
    app.conf.result_backend = result_backend
    
    # Serialization
    app.conf.task_serializer = "json"
    app.conf.result_serializer = "json"
    app.conf.accept_content = ["json"]
    
    # Task execution settings
    app.conf.task_track_started = True
    app.conf.task_time_limit = int(os.getenv("CELERY_TASK_TIME_LIMIT", "300"))
    app.conf.task_soft_time_limit = int(os.getenv("CELERY_TASK_SOFT_TIME_LIMIT", "240"))
    app.conf.worker_prefetch_multiplier = int(os.getenv("CELERY_WORKER_PREFETCH_MULTIPLIER", "1"))
    app.conf.worker_concurrency = int(os.getenv("CELERY_WORKER_CONCURRENCY", "4"))
    
    # Result settings
    app.conf.result_expires = int(os.getenv("CELERY_RESULT_EXPIRES", "3600"))
    app.conf.result_extended = True
    
    # Retry configuration
    app.conf.task_default_retry_delay = int(os.getenv("CELERY_RETRY_DELAY", "60"))
    app.conf.task_max_retries = int(os.getenv("CELERY_MAX_RETRIES", "3"))
    app.conf.broker_connection_retry_on_startup = True
    
    # Task acknowledgment - acknowledge after task completes, not before
    app.conf.task_acks_late = True
    app.conf.task_reject_on_worker_lost = True
    
    # Visibility timeout (must exceed longest task duration)
    app.conf.broker_transport_options = {
        "visibility_timeout": 43200,  # 12 hours
        "queue_order_strategy": "priority"
    }
    
    # Redis result backend settings
    app.conf.result_backend_transport_options = {
        "retry_on_timeout": True
    }
    
    # -----------------------------------------------------------------------
    # Queue and Routing Configuration
    # -----------------------------------------------------------------------
    default_exchange = Exchange("default", type="direct")
    priority_exchange = Exchange("priority", type="direct")
    
    app.conf.task_queues = (
        Queue("default", default_exchange, routing_key="default"),
        Queue("high-priority", priority_exchange, routing_key="high"),
        Queue("low-priority", priority_exchange, routing_key="low"),
    )
    
    app.conf.task_default_queue = "default"
    app.conf.task_default_exchange = "default"
    app.conf.task_default_routing_key = "default"
    
    # Task routing rules
    app.conf.task_routes = {
        "worker.tasks.process_task": {"queue": "default"},
        "worker.tasks.send_email": {"queue": "low-priority"},
        "worker.tasks.generate_report": {"queue": "low-priority"},
        "worker.tasks.process_high_priority": {"queue": "high-priority"},
    }
    
    # -----------------------------------------------------------------------
    # Beat Scheduler Configuration (Periodic Tasks)
    # -----------------------------------------------------------------------
    app.conf.beat_schedule = {
        "cleanup-old-tasks": {
            "task": "worker.tasks.cleanup_old_tasks",
            "schedule": 3600.0,  # Every hour
            "options": {"queue": "low-priority"}
        },
        "health-check-report": {
            "task": "worker.tasks.send_health_report",
            "schedule": 300.0,  # Every 5 minutes
            "options": {"queue": "low-priority"}
        },
        "heartbeat": {
            "task": "worker.tasks.worker_heartbeat",
            "schedule": 60.0,  # Every minute
            "options": {"queue": "low-priority"}
        }
    }
    
    # Use local timezone for scheduling
    app.conf.timezone = os.getenv("TZ", "UTC")
    app.conf.enable_utc = True
    
    # -----------------------------------------------------------------------
    # Event and Monitoring Settings
    # -----------------------------------------------------------------------
    app.conf.worker_send_task_events = True
    app.conf.task_send_sent_event = True
    
    # Prevent memory leaks by restarting worker after N tasks
    app.conf.worker_max_tasks_per_child = int(os.getenv("WORKER_MAX_TASKS", "1000"))
    
    logger.info(
        "Celery application configured",
        extra={
            "broker": broker_url.replace("//", "//***@"),  # Mask credentials
            "concurrency": app.conf.worker_concurrency,
            "queues": ["default", "high-priority", "low-priority"]
        }
    )
    
    return app


# ---------------------------------------------------------------------------
# Create the Celery Application Instance
# ---------------------------------------------------------------------------
celery_app = create_celery_app()

# ---------------------------------------------------------------------------
# Signal Handlers for Monitoring and Logging
# ---------------------------------------------------------------------------

@task_prerun.connect
def on_task_prerun(sender=None, task_id=None, task=None, args=None, kwargs=None, **extras):
    """Handle task pre-run event: log task start and update database status.
    
    Args:
        sender: Task class
        task_id: Unique task UUID
        task: Task instance
        args: Task positional arguments
        kwargs: Task keyword arguments
    """
    logger.info(
        "Task started",
        extra={
            "task_id": task_id,
            "task_name": task.name,
            "args": str(args),
            "kwargs": str(kwargs)
        }
    )


@task_postrun.connect
def on_task_postrun(sender=None, task_id=None, task=None, retval=None, state=None, **extras):
    """Handle task post-run event: log task completion.
    
    Args:
        sender: Task class
        task_id: Unique task UUID
        task: Task instance
        retval: Task return value
        state: Final task state
    """
    logger.info(
        "Task completed",
        extra={
            "task_id": task_id,
            "task_name": task.name,
            "state": state,
            "result_length": len(str(retval)) if retval else 0
        }
    )


@task_success.connect
def on_task_success(sender=None, result=None, **kwargs):
    """Handle task success event.
    
    Args:
        sender: Task instance
        result: Task return value
    """
    logger.info(
        "Task succeeded",
        extra={"task_name": sender.name, "task_id": sender.request.id}
    )


@task_failure.connect
def on_task_failure(sender=None, task_id=None, exception=None, args=None, kwargs=None, traceback=None, einfo=None, **extras):
    """Handle task failure event: log error and trigger retry if applicable.
    
    Args:
        sender: Task instance
        task_id: Unique task UUID
        exception: Exception that caused the failure
        args: Task arguments
        kwargs: Task keyword arguments
        traceback: Exception traceback
        einfo: Exception info object
    """
    logger.error(
        "Task failed",
        extra={
            "task_id": task_id,
            "task_name": sender.name if sender else "unknown",
            "exception": str(exception),
            "exception_type": type(exception).__name__,
            "retry_count": sender.request.retries if sender else 0
        },
        exc_info=True
    )


@worker_ready.connect
def on_worker_ready(sender=None, **kwargs):
    """Handle worker ready event.
    
    Called when the worker process has started and is ready to process tasks.
    
    Args:
        sender: Worker instance
    """
    hostname = sender.hostname if sender else "unknown"
    logger.info(
        "Worker ready",
        extra={
            "hostname": hostname,
            "concurrency": sender.concurrency if sender else "unknown",
            "queues": list(sender.app.amqp.queues.keys()) if sender else []
        }
    )


@worker_shutdown.connect
def on_worker_shutdown(sender=None, **kwargs):
    """Handle worker shutdown event for graceful cleanup.
    
    Args:
        sender: Worker instance
    """
    hostname = sender.hostname if sender else "unknown"
    logger.info("Worker shutting down", extra={"hostname": hostname})


# ---------------------------------------------------------------------------
# Auto-discover Tasks
# ---------------------------------------------------------------------------

# Import task modules to register tasks with Celery
from src import tasks

logger.info("Worker module loaded, tasks registered")


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    celery_app.start()
