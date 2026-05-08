#!/usr/bin/env python3
# =============================================================================
# Worker Service - Test Suite
# =============================================================================
# Comprehensive tests for the Celery worker including task execution,
# health check endpoints, error handling, and retry logic.
# =============================================================================

import json
import time
import pytest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock, PropertyMock

# Mark all tests that require Celery
celery = pytest.importorskip("celery")

from src.worker import create_celery_app
from src.tasks import (
    process_task, process_high_priority, send_email, generate_report,
    cleanup_old_tasks, send_health_report, worker_heartbeat,
    _process_data_task, _process_generic_task, _matches_condition
)


# ---------------------------------------------------------------------------
# Test Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def celery_app():
    """Create a test Celery application."""
    app = create_celery_app()
    app.conf.update(
        task_always_eager=True,  # Run tasks synchronously for testing
        task_store_eager_result=True,
        broker_url="memory://",
        result_backend="cache+memory://",
    )
    return app


@pytest.fixture
def sample_task_data():
    """Provide sample task data for testing."""
    return {
        "task_id": "test-task-123",
        "task_name": "test-processing",
        "payload": json.dumps({"input": ["a", "b", "c"], "operation": "transform"})
    }


# ---------------------------------------------------------------------------
# Celery App Tests
# ---------------------------------------------------------------------------

class TestCeleryApp:
    """Test Celery application configuration."""
    
    def test_app_creation(self):
        """Test Celery app can be created."""
        app = create_celery_app()
        assert app is not None
        assert app.main == "microservices-worker"
    
    def test_app_has_queues(self, celery_app):
        """Test app is configured with task queues."""
        assert celery_app.conf.task_queues is not None
    
    def test_app_serialization(self, celery_app):
        """Test app uses JSON serialization."""
        assert celery_app.conf.task_serializer == "json"
        assert celery_app.conf.result_serializer == "json"
        assert "json" in celery_app.conf.accept_content
    
    def test_task_routes_configured(self, celery_app):
        """Test task routes are configured."""
        assert celery_app.conf.task_routes is not None
    
    def test_result_expiry(self, celery_app):
        """Test result expiry is configured."""
        assert celery_app.conf.result_expires is not None
    
    def test_beat_schedule(self, celery_app):
        """Test beat schedule has periodic tasks."""
        assert celery_app.conf.beat_schedule is not None
        assert "cleanup-old-tasks" in celery_app.conf.beat_schedule
        assert "health-check-report" in celery_app.conf.beat_schedule


# ---------------------------------------------------------------------------
# Task Processing Tests
# ---------------------------------------------------------------------------

class TestProcessTask:
    """Test the main task processing function."""
    
    def test_task_accepts_valid_input(self, sample_task_data):
        """Test task processing accepts valid input."""
        # Since we're using eager mode, this runs synchronously
        result = process_task.run(
            task_id=sample_task_data["task_id"],
            task_name=sample_task_data["task_name"],
            payload=sample_task_data["payload"]
        )
        
        assert isinstance(result, dict)
        assert result["task_id"] == sample_task_data["task_id"]
        assert result["status"] == "completed"
        assert "result" in result
    
    def test_task_returns_duration(self, sample_task_data):
        """Test task result includes duration."""
        result = process_task.run(
            task_id=sample_task_data["task_id"],
            task_name=sample_task_data["task_name"],
            payload=sample_task_data["payload"]
        )
        
        assert "duration_seconds" in result
        assert result["duration_seconds"] >= 0
    
    def test_task_returns_timestamp(self, sample_task_data):
        """Test task result includes timestamp."""
        result = process_task.run(
            task_id=sample_task_data["task_id"],
            task_name=sample_task_data["task_name"],
            payload=sample_task_data["payload"]
        )
        
        assert "processed_at" in result
    
    def test_task_with_null_payload(self):
        """Test task processing with null payload."""
        result = process_task.run(
            task_id="null-payload-task",
            task_name="test-task",
            payload=None
        )
        
        assert result["status"] == "completed"
    
    def test_task_with_invalid_payload(self):
        """Test task processing with invalid JSON payload."""
        with pytest.raises(Exception):
            process_task.run(
                task_id="invalid-task",
                task_name="test-task",
                payload="not valid json"
            )
    
    def test_data_processing_task(self):
        """Test data processing task type."""
        result = process_task.run(
            task_id="data-task-1",
            task_name="data-processing-transform",
            payload=json.dumps({
                "input": ["hello", "world"],
                "operation": "transform"
            })
        )
        
        assert result["status"] == "completed"
    
    def test_report_task(self):
        """Test report generation task type."""
        result = process_task.run(
            task_id="report-task-1",
            task_name="report-daily",
            payload=json.dumps({
                "report_type": "daily",
                "time_range": "24h"
            })
        )
        
        assert result["status"] == "completed"


# ---------------------------------------------------------------------------
# High Priority Task Tests
# ---------------------------------------------------------------------------

class TestHighPriorityTask:
    """Test high-priority task processing."""
    
    def test_high_priority_task(self):
        """Test high-priority task execution."""
        result = process_high_priority.run(
            task_id="priority-task-1",
            data={"operation": "critical-process"}
        )
        
        assert isinstance(result, dict)
        assert result["status"] == "completed"
        assert "result" in result
    
    def test_high_priority_includes_priority(self):
        """Test high-priority result includes priority info."""
        result = process_high_priority.run(
            task_id="priority-task-2",
            data={"operation": "test"}
        )
        
        assert result["result"]["priority"] == "high"


# ---------------------------------------------------------------------------
# Email Task Tests
# ---------------------------------------------------------------------------

class TestSendEmail:
    """Test email sending task."""
    
    def test_email_task_accepts_params(self):
        """Test email task accepts required parameters."""
        result = send_email.run(
            to_address="test@example.com",
            subject="Test Subject",
            body="Test email body"
        )
        
        assert isinstance(result, dict)
        assert result["status"] == "sent"
        assert result["to"] == "test@example.com"
        assert result["subject"] == "Test Subject"
    
    def test_email_with_html(self):
        """Test email task with HTML body."""
        result = send_email.run(
            to_address="test@example.com",
            subject="HTML Test",
            body="Plain text",
            html_body="<html><body>HTML content</body></html>"
        )
        
        assert result["status"] == "sent"
    
    def test_email_includes_timestamp(self):
        """Test email result includes timestamp."""
        result = send_email.run(
            to_address="test@example.com",
            subject="Timestamp Test",
            body="Test"
        )
        
        assert "sent_at" in result
    
    def test_email_with_from_address(self):
        """Test email task with custom from address."""
        result = send_email.run(
            to_address="test@example.com",
            subject="From Test",
            body="Test",
            from_address="sender@example.com"
        )
        
        assert result["status"] == "sent"


# ---------------------------------------------------------------------------
# Report Generation Tests
# ---------------------------------------------------------------------------

class TestGenerateReport:
    """Test report generation task."""
    
    def test_task_summary_report(self):
        """Test task summary report generation."""
        result = generate_report.run(
            report_type="task-summary",
            parameters={"time_range": "24h"}
        )
        
        assert isinstance(result, dict)
        assert result["report_type"] == "task-summary"
        assert result["format"] == "json"
        assert result["status"] == "completed"
        assert "data" in result
    
    def test_health_report(self):
        """Test health report generation."""
        result = generate_report.run(
            report_type="health",
            parameters={"include_metrics": True}
        )
        
        assert result["report_type"] == "health"
        assert "data" in result
        assert "cpu_usage" in result["data"]
    
    def test_audit_report(self):
        """Test audit report generation."""
        result = generate_report.run(
            report_type="audit",
            parameters={"time_range": "7d"}
        )
        
        assert result["report_type"] == "audit"
        assert "events_by_type" in result["data"]
    
    def test_report_includes_generation_time(self):
        """Test report includes generation timing."""
        result = generate_report.run(
            report_type="task-summary",
            parameters={}
        )
        
        assert "generation_time_seconds" in result
        assert result["generation_time_seconds"] >= 0
    
    def test_report_returns_report_id(self):
        """Test report includes unique report ID."""
        result = generate_report.run(
            report_type="task-summary",
            parameters={}
        )
        
        assert "report_id" in result
        assert result["report_id"].startswith("report-")


# ---------------------------------------------------------------------------
# Scheduled Task Tests
# ---------------------------------------------------------------------------

class TestScheduledTasks:
    """Test scheduled/periodic tasks."""
    
    def test_cleanup_old_tasks(self):
        """Test cleanup task execution."""
        result = cleanup_old_tasks.run(retention_days=30)
        
        assert isinstance(result, dict)
        assert result["status"] == "completed"
        assert result["action"] == "cleanup"
        assert result["retention_days"] == 30
    
    def test_cleanup_custom_retention(self):
        """Test cleanup with custom retention period."""
        result = cleanup_old_tasks.run(retention_days=7)
        
        assert result["retention_days"] == 7
    
    def test_health_report_task(self):
        """Test health report scheduled task."""
        result = send_health_report.run()
        
        assert isinstance(result, dict)
        assert result["status"] == "completed"
        assert "health_data" in result
    
    def test_health_report_includes_timestamp(self):
        """Test health report includes timestamps."""
        result = send_health_report.run()
        
        assert "timestamp" in result["health_data"]
    
    def test_worker_heartbeat(self):
        """Test worker heartbeat task."""
        result = worker_heartbeat.run()
        
        assert isinstance(result, dict)
        assert result["status"] in ["ok", "error"]
    
    def test_worker_heartbeat_includes_timestamp(self):
        """Test heartbeat includes timestamp."""
        result = worker_heartbeat.run()
        
        assert "timestamp" in result


# ---------------------------------------------------------------------------
# Internal Function Tests
# ---------------------------------------------------------------------------

class TestDataTaskProcessor:
    """Test data task processing functions."""
    
    def test_transform_operation(self):
        """Test transform operation."""
        result = _process_data_task("test-1", {
            "input": ["hello", "world"],
            "operation": "transform"
        })
        
        assert result["operation"] == "transform"
        assert "output" in result
    
    def test_filter_operation(self):
        """Test filter operation."""
        result = _process_data_task("test-2", {
            "input": [{"type": "a"}, {"type": "b"}, {"type": "a"}],
            "operation": "filter",
            "condition": {"type": "a"}
        })
        
        assert result["operation"] == "filter"
        assert result["input_count"] == 3
    
    def test_aggregate_operation(self):
        """Test aggregate operation."""
        result = _process_data_task("test-3", {
            "input": [1, 2, 3, 4, 5],
            "operation": "aggregate"
        })
        
        assert result["operation"] == "aggregate"
        assert result["output"]["count"] == 5
        assert result["output"]["sum"] == 15
    
    def test_unknown_operation(self):
        """Test unknown operation handling."""
        result = _process_data_task("test-4", {
            "input": [],
            "operation": "unknown"
        })
        
        assert result["operation"] == "unknown"


class TestGenericTaskProcessor:
    """Test generic task processing."""
    
    def test_generic_task(self):
        """Test generic task processing."""
        result = _process_generic_task("task-1", "custom-task", {
            "key": "value",
            "processing_time": 0.1
        })
        
        assert result["task_name"] == "custom-task"
        assert result["processed"] is True
        assert "input_keys" in result
    
    def test_generic_task_with_short_processing_time(self):
        """Test generic task with minimal processing time."""
        start = time.time()
        result = _process_generic_task("task-2", "quick-task", {
            "processing_time": 0.01
        })
        duration = time.time() - start
        
        assert result["processed"] is True
        assert duration < 1.0  # Should complete quickly


class TestConditionMatcher:
    """Test condition matching function."""
    
    def test_empty_condition(self):
        """Test empty condition matches everything."""
        assert _matches_condition("anything", {}) is True
        assert _matches_condition({"a": 1}, {}) is True
    
    def test_dict_condition_match(self):
        """Test dictionary condition matching."""
        assert _matches_condition({"type": "a", "value": 1}, {"type": "a"}) is True
        assert _matches_condition({"type": "b", "value": 1}, {"type": "a"}) is False
    
    def test_truthy_value(self):
        """Test truthy value matching."""
        assert _matches_condition("hello", None) is True
        assert _matches_condition(1, None) is True


# ---------------------------------------------------------------------------
# Error Handling Tests
# ---------------------------------------------------------------------------

class TestErrorHandling:
    """Test error handling in tasks."""
    
    def test_task_with_invalid_json_payload(self):
        """Test task handles invalid JSON."""
        with pytest.raises(Exception):
            process_task.run(
                task_id="error-task",
                task_name="test",
                payload="{invalid json"
            )
    
    def test_report_with_unknown_type(self):
        """Test report with unknown type."""
        result = generate_report.run(
            report_type="unknown-type",
            parameters={}
        )
        
        assert "error" in result["data"]


# ---------------------------------------------------------------------------
# Performance Tests
# ---------------------------------------------------------------------------

class TestPerformance:
    """Test task performance characteristics."""
    
    def test_task_execution_time(self, sample_task_data):
        """Test task completes within reasonable time."""
        start = time.time()
        result = process_task.run(
            task_id=sample_task_data["task_id"],
            task_name=sample_task_data["task_name"],
            payload=sample_task_data["payload"]
        )
        duration = time.time() - start
        
        assert result is not None
        assert duration < 5.0  # Should complete within 5 seconds
    
    def test_quick_task_type(self):
        """Test quick task execution."""
        start = time.time()
        result = worker_heartbeat.run()
        duration = time.time() - start
        
        assert result is not None
        assert duration < 2.0


# Run with: pytest tests/test_worker.py -v
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
