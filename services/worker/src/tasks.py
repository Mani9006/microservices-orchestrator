#!/usr/bin/env python3
# =============================================================================
# Worker Service - Task Definitions
# =============================================================================
# This module defines all Celery tasks for the background worker.
# Tasks include data processing, report generation, email sending,
# scheduled maintenance jobs, and system health checks.
# =============================================================================

import os
import json
import time
import random
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

import requests
from celery.exceptions import MaxRetriesExceededError, SoftTimeLimitExceeded

from src.worker import celery_app, logger

# ---------------------------------------------------------------------------
# Task Base Configuration
# ---------------------------------------------------------------------------

# Default task configuration
DEFAULT_TASK_CONFIG = {
    "bind": True,  # Bind task instance for self access
    "max_retries": 3,
    "default_retry_delay": 60,
    "time_limit": 300,
    "soft_time_limit": 240,
    "acks_late": True,
}


# ---------------------------------------------------------------------------
# Core Task Processing
# ---------------------------------------------------------------------------

@celery_app.task(**DEFAULT_TASK_CONFIG)
def process_task(self, task_id: str, task_name: str, payload: Optional[str] = None) -> Dict[str, Any]:
    """Process a generic background task.
    
    This is the main entry point for task processing. It handles different
    task types by dispatching to appropriate sub-processors based on task name.
    
    Args:
        self: Celery task instance (bound)
        task_id: Unique database task identifier
        task_name: Name/type of the task to process
        payload: Optional JSON payload containing task-specific data
    
    Returns:
        Dictionary containing task result metadata.
    
    Raises:
        SoftTimeLimitExceeded: When task exceeds soft time limit
    """
    start_time = time.time()
    
    logger.info(
        "Processing task",
        extra={"task_id": task_id, "task_name": task_name, "celery_task_id": self.request.id}
    )
    
    try:
        # Parse payload
        data = json.loads(payload) if payload else {}
        
        # Route to appropriate processor based on task name
        if task_name.startswith("data-processing"):
            result = _process_data_task(task_id, data)
        elif task_name.startswith("report"):
            result = _process_report_task(task_id, data)
        elif task_name.startswith("email"):
            result = _process_email_task(task_id, data)
        elif task_name.startswith("cleanup"):
            result = _process_cleanup_task(task_id, data)
        else:
            # Generic processing
            result = _process_generic_task(task_id, task_name, data)
        
        duration = time.time() - start_time
        
        logger.info(
            "Task processing completed",
            extra={"task_id": task_id, "duration": f"{duration:.2f}s", "status": "success"}
        )
        
        return {
            "task_id": task_id,
            "task_name": task_name,
            "status": "completed",
            "result": result,
            "duration_seconds": round(duration, 2),
            "processed_at": datetime.now(timezone.utc).isoformat()
        }
        
    except SoftTimeLimitExceeded:
        logger.warning(f"Task soft time limit exceeded: {task_id}")
        _update_task_status(task_id, "failed", "Task timed out")
        raise
    
    except Exception as exc:
        logger.error(f"Task processing failed: {exc}", exc_info=True)
        
        # Retry the task if retries are available
        retry_count = self.request.retries
        if retry_count < self.max_retries:
            logger.info(f"Retrying task {task_id}, attempt {retry_count + 1}/{self.max_retries}")
            raise self.retry(exc=exc, countdown=60 * (retry_count + 1))
        else:
            logger.error(f"Max retries exceeded for task {task_id}")
            _update_task_status(task_id, "failed", str(exc))
            raise MaxRetriesExceededError(f"Task {task_id} failed after {self.max_retries} retries")


# ---------------------------------------------------------------------------
# High Priority Task
# ---------------------------------------------------------------------------

@celery_app.task(
    bind=True, max_retries=5, default_retry_delay=30,
    time_limit=60, soft_time_limit=45
)
def process_high_priority(self, task_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """Process high-priority tasks with tighter resource constraints.
    
    These tasks get dedicated queue resources and faster retry cycles.
    
    Args:
        self: Celery task instance
        task_id: Database task identifier
        data: Task processing data
    
    Returns:
        Processing result dictionary
    """
    logger.info(f"Processing high-priority task: {task_id}")
    
    try:
        # Simulate high-priority work
        result = _execute_priority_work(data)
        
        return {
            "task_id": task_id,
            "status": "completed",
            "result": result,
            "processed_at": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as exc:
        logger.error(f"High-priority task failed: {exc}")
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=30)
        raise


# ---------------------------------------------------------------------------
# Email Sending Task
# ---------------------------------------------------------------------------

@celery_app.task(
    bind=True, max_retries=3, default_retry_delay=300,
    time_limit=120, soft_time_limit=90
)
def send_email(self, to_address: str, subject: str, body: str, 
               html_body: Optional[str] = None, 
               from_address: Optional[str] = None) -> Dict[str, Any]:
    """Send an email asynchronously.
    
    In production, this integrates with an email service provider.
    For development, it logs the email content.
    
    Args:
        self: Celery task instance
        to_address: Recipient email address
        subject: Email subject line
        body: Plain text email body
        html_body: Optional HTML email body
        from_address: Sender email address
    
    Returns:
        Dictionary with send status and metadata.
    """
    from_address = from_address or os.getenv("DEFAULT_FROM_EMAIL", "noreply@example.com")
    
    logger.info(
        "Sending email",
        extra={"to": to_address, "subject": subject, "from": from_address}
    )
    
    try:
        # In production, integrate with SendGrid, AWS SES, etc.
        # For this demo, we simulate the email send
        email_provider = os.getenv("EMAIL_PROVIDER", "mock")
        
        if email_provider == "sendgrid":
            result = _send_via_sendgrid(to_address, from_address, subject, body, html_body)
        elif email_provider == "ses":
            result = _send_via_ses(to_address, from_address, subject, body, html_body)
        else:
            # Mock email for development/testing
            result = _send_mock_email(to_address, from_address, subject, body, html_body)
        
        logger.info(f"Email sent successfully to {to_address}")
        
        return {
            "status": "sent",
            "to": to_address,
            "subject": subject,
            "provider": email_provider,
            "message_id": result.get("message_id", "mock-id"),
            "sent_at": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as exc:
        logger.error(f"Failed to send email: {exc}")
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=300)
        raise


# ---------------------------------------------------------------------------
# Report Generation Task
# ---------------------------------------------------------------------------

@celery_app.task(
    bind=True, max_retries=2, default_retry_delay=120,
    time_limit=600, soft_time_limit=480
)
def generate_report(self, report_type: str, parameters: Dict[str, Any],
                    output_format: str = "json") -> Dict[str, Any]:
    """Generate various types of reports asynchronously.
    
    Supports task reports, system health reports, and audit reports.
    
    Args:
        self: Celery task instance
        report_type: Type of report (task-summary, health, audit)
        parameters: Report-specific parameters
        output_format: Output format (json, csv, pdf)
    
    Returns:
        Dictionary with report metadata and content URL.
    """
    logger.info(
        "Generating report",
        extra={"report_type": report_type, "format": output_format}
    )
    
    try:
        start_time = time.time()
        
        # Generate report based on type
        if report_type == "task-summary":
            report_data = _generate_task_summary_report(parameters)
        elif report_type == "health":
            report_data = _generate_health_report(parameters)
        elif report_type == "audit":
            report_data = _generate_audit_report(parameters)
        else:
            report_data = {"error": f"Unknown report type: {report_type}"}
        
        duration = time.time() - start_time
        
        # Store report result
        report_id = f"report-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{random.randint(1000, 9999)}"
        
        # In production, store in S3 or similar
        logger.info(f"Report {report_id} generated in {duration:.2f}s")
        
        return {
            "report_id": report_id,
            "report_type": report_type,
            "format": output_format,
            "status": "completed",
            "data": report_data,
            "generation_time_seconds": round(duration, 2),
            "generated_at": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as exc:
        logger.error(f"Report generation failed: {exc}")
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=120)
        raise


# ---------------------------------------------------------------------------
# Scheduled Maintenance Tasks
# ---------------------------------------------------------------------------

@celery_app.task(
    bind=True, max_retries=2, default_retry_delay=60,
    time_limit=300, soft_time_limit=240
)
def cleanup_old_tasks(self, retention_days: int = 30) -> Dict[str, Any]:
    """Clean up completed tasks older than retention period.
    
    This scheduled task runs periodically to prevent database bloat.
    
    Args:
        self: Celery task instance
        retention_days: Number of days to retain completed tasks
    
    Returns:
        Cleanup statistics.
    """
    logger.info(f"Starting task cleanup (retention: {retention_days} days)")
    
    try:
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=retention_days)
        
        # In production, this would delete from PostgreSQL
        # For this implementation, we log and track
        
        logger.info(f"Cleaned up tasks older than {cutoff_date.isoformat()}")
        
        return {
            "status": "completed",
            "action": "cleanup",
            "retention_days": retention_days,
            "cutoff_date": cutoff_date.isoformat(),
            "cleaned_at": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as exc:
        logger.error(f"Task cleanup failed: {exc}")
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc)
        raise


@celery_app.task(
    bind=True, max_retries=2, default_retry_delay=30,
    time_limit=60, soft_time_limit=45
)
def send_health_report(self) -> Dict[str, Any]:
    """Send periodic health status report.
    
    Generates and optionally emails a health status summary.
    
    Args:
        self: Celery task instance
    
    Returns:
        Health report status.
    """
    logger.info("Generating health report")
    
    try:
        # Gather health metrics
        health_data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "worker": _get_worker_health(),
            "queue_depths": _get_queue_depths(),
            "recent_tasks": _get_recent_task_stats()
        }
        
        logger.info("Health report generated", extra=health_data)
        
        return {
            "status": "completed",
            "health_data": health_data,
            "generated_at": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as exc:
        logger.error(f"Health report failed: {exc}")
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc)
        raise


@celery_app.task(
    bind=True, max_retries=1, time_limit=10
)
def worker_heartbeat(self) -> Dict[str, Any]:
    """Emit a heartbeat signal to indicate worker is alive.
    
    This task runs on a schedule and updates a heartbeat key in Redis
    that monitoring systems can check to verify worker health.
    
    Args:
        self: Celery task instance
    
    Returns:
        Heartbeat status.
    """
    try:
        import redis
        
        redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
        client = redis.from_url(redis_url, socket_connect_timeout=2)
        
        heartbeat_key = "worker:heartbeat"
        heartbeat_data = json.dumps({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "worker": os.getenv("HOSTNAME", "unknown"),
            "task_id": self.request.id
        })
        
        client.setex(heartbeat_key, 120, heartbeat_data)
        client.close()
        
        return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}
        
    except Exception as exc:
        logger.warning(f"Heartbeat update failed: {exc}")
        return {"status": "error", "error": str(exc)}


# ---------------------------------------------------------------------------
# Task Processors (Internal)
# ---------------------------------------------------------------------------

def _process_data_task(task_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """Process a data transformation task."""
    logger.info(f"Processing data task {task_id}")
    
    # Simulate data processing
    input_data = data.get("input", [])
    operation = data.get("operation", "transform")
    
    if operation == "transform":
        result = [item.upper() if isinstance(item, str) else item for item in input_data]
    elif operation == "filter":
        condition = data.get("condition", {})
        result = [item for item in input_data if _matches_condition(item, condition)]
    elif operation == "aggregate":
        result = {"count": len(input_data), "sum": sum(x for x in input_data if isinstance(x, (int, float)))}
    else:
        result = {"input": input_data, "operation": operation}
    
    return {"operation": operation, "input_count": len(input_data), "output": result}


def _process_report_task(task_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """Process a report generation task."""
    logger.info(f"Processing report task {task_id}")
    
    report_type = data.get("report_type", "generic")
    time_range = data.get("time_range", "last_24h")
    
    # Simulate report generation
    time.sleep(random.uniform(0.1, 0.5))  # Simulate processing time
    
    return {
        "report_type": report_type,
        "time_range": time_range,
        "generated": True,
        "sections": ["summary", "details", "appendix"]
    }


def _process_email_task(task_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """Process an email sending task."""
    to = data.get("to", "")
    subject = data.get("subject", "")
    body = data.get("body", "")
    
    # Queue the actual email send task
    send_email.delay(to, subject, body)
    
    return {"queued": True, "recipient": to, "subject": subject}


def _process_cleanup_task(task_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """Process a cleanup task."""
    resource = data.get("resource", "temp_files")
    
    return {"cleaned": resource, "status": "completed"}


def _process_generic_task(task_id: str, task_name: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """Process a generic/unknown task type."""
    logger.info(f"Processing generic task {task_name} (ID: {task_id})")
    
    # Simulate some work
    processing_time = data.get("processing_time", random.uniform(0.1, 1.0))
    time.sleep(min(processing_time, 5))  # Cap at 5 seconds
    
    return {
        "task_name": task_name,
        "processed": True,
        "input_keys": list(data.keys()),
        "processing_time": processing_time
    }


def _execute_priority_work(data: Dict[str, Any]) -> Dict[str, Any]:
    """Execute high-priority work."""
    operation = data.get("operation", "default")
    
    return {
        "operation": operation,
        "priority": "high",
        "executed_at": datetime.now(timezone.utc).isoformat()
    }


def _matches_condition(item: Any, condition: Dict[str, Any]) -> bool:
    """Check if an item matches a filter condition."""
    if not condition:
        return True
    
    if isinstance(item, dict):
        for key, value in condition.items():
            if item.get(key) != value:
                return False
        return True
    
    return bool(item)


def _send_via_sendgrid(to: str, from_addr: str, subject: str, body: str, html: Optional[str]) -> Dict[str, str]:
    """Send email via SendGrid API."""
    api_key = os.getenv("SENDGRID_API_KEY", "")
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "personalizations": [{"to": [{"email": to}]}],
        "from": {"email": from_addr},
        "subject": subject,
        "content": [
            {"type": "text/plain", "value": body}
        ]
    }
    
    if html:
        payload["content"].append({"type": "text/html", "value": html})
    
    response = requests.post(
        "https://api.sendgrid.com/v3/mail/send",
        headers=headers,
        json=payload,
        timeout=30
    )
    response.raise_for_status()
    
    return {"message_id": response.headers.get("X-Message-Id", "unknown")}


def _send_via_ses(to: str, from_addr: str, subject: str, body: str, html: Optional[str]) -> Dict[str, str]:
    """Send email via AWS SES API."""
    # In production, use boto3 to call SES
    logger.info(f"Mock SES send to {to}")
    return {"message_id": f"ses-{datetime.now().timestamp()}"}


def _send_mock_email(to: str, from_addr: str, subject: str, body: str, html: Optional[str]) -> Dict[str, str]:
    """Mock email sender for development."""
    logger.info(f"[MOCK EMAIL] To: {to}, Subject: {subject}")
    logger.debug(f"[MOCK EMAIL] Body: {body[:200]}...")
    return {"message_id": f"mock-{datetime.now().timestamp()}"}


def _generate_task_summary_report(parameters: Dict[str, Any]) -> Dict[str, Any]:
    """Generate a task execution summary report."""
    time_range = parameters.get("time_range", "24h")
    
    return {
        "time_range": time_range,
        "total_tasks": random.randint(100, 1000),
        "completed": random.randint(80, 900),
        "failed": random.randint(0, 50),
        "average_duration": random.uniform(1.0, 30.0),
        "top_tasks": ["data-processing", "email", "report-generation"]
    }


def _generate_health_report(parameters: Dict[str, Any]) -> Dict[str, Any]:
    """Generate a system health report."""
    return {
        "cpu_usage": random.uniform(10, 80),
        "memory_usage": random.uniform(30, 90),
        "disk_usage": random.uniform(20, 70),
        "active_workers": random.randint(2, 10),
        "queue_depths": {
            "default": random.randint(0, 100),
            "high-priority": random.randint(0, 20),
            "low-priority": random.randint(0, 200)
        }
    }


def _generate_audit_report(parameters: Dict[str, Any]) -> Dict[str, Any]:
    """Generate an audit log report."""
    time_range = parameters.get("time_range", "7d")
    
    return {
        "time_range": time_range,
        "total_events": random.randint(1000, 10000),
        "events_by_type": {
            "create": random.randint(200, 2000),
            "update": random.randint(100, 1000),
            "delete": random.randint(10, 200),
            "view": random.randint(500, 5000)
        }
    }


def _get_worker_health() -> Dict[str, Any]:
    """Get current worker health status."""
    import psutil
    
    process = psutil.Process()
    memory_info = process.memory_info()
    
    return {
        "status": "healthy",
        "memory_mb": round(memory_info.rss / (1024 * 1024), 2),
        "cpu_percent": process.cpu_percent(),
        "uptime_seconds": int(time.time() - process.create_time()) if hasattr(process, "create_time") else 0
    }


def _get_queue_depths() -> Dict[str, int]:
    """Get current queue depths from Redis."""
    try:
        import redis
        
        redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
        client = redis.from_url(redis_url, socket_connect_timeout=2)
        
        depths = {
            "default": client.llen("celery") or 0,
            "high-priority": client.llen("celery:high-priority") or 0,
            "low-priority": client.llen("celery:low-priority") or 0
        }
        
        client.close()
        return depths
        
    except Exception as e:
        logger.warning(f"Could not get queue depths: {e}")
        return {"default": -1, "high-priority": -1, "low-priority": -1}


def _get_recent_task_stats() -> Dict[str, Any]:
    """Get statistics about recently processed tasks."""
    return {
        "last_hour": random.randint(10, 100),
        "last_24h": random.randint(100, 1000),
        "average_processing_time": random.uniform(1.0, 10.0)
    }


def _update_task_status(task_id: str, status: str, message: str = "") -> None:
    """Update task status in the database.
    
    Args:
        task_id: Database task identifier
        status: New status value
        message: Optional status message
    """
    try:
        # In production, update via API call or direct DB connection
        api_url = os.getenv("API_URL", "http://api:5000")
        
        response = requests.patch(
            f"{api_url}/api/v1/tasks/{task_id}",
            json={"status": status},
            timeout=5
        )
        
        if response.status_code == 200:
            logger.info(f"Updated task {task_id} status to {status}")
        else:
            logger.warning(f"Failed to update task {task_id}: {response.status_code}")
            
    except Exception as e:
        logger.warning(f"Could not update task status: {e}")
