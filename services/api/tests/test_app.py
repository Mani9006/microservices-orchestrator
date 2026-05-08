#!/usr/bin/env python3
# =============================================================================
# API Service - Application Tests
# =============================================================================
# Comprehensive test suite for the Flask API application including
# route testing, model validation, error handling, and integration tests.
# =============================================================================

import json
import unittest
from datetime import datetime, timezone

import pytest
from flask import url_for

from src.app import create_app, db
from src.models import Task, User, AuditLog


# ---------------------------------------------------------------------------
# Test Configuration
# ---------------------------------------------------------------------------

class TestConfig:
    """Test-specific configuration."""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SECRET_KEY = "test-secret-key"
    RATELIMIT_ENABLED = False
    WTF_CSRF_ENABLED = False


# ---------------------------------------------------------------------------
# Pytest Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def app():
    """Create and configure a test Flask application."""
    app = create_app("testing")
    app.config.from_object(TestConfig)
    
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    """Create a test client for the app."""
    return app.test_client()


@pytest.fixture
def runner(app):
    """Create a test CLI runner for the app."""
    return app.test_cli_runner()


@pytest.fixture
def sample_task(app):
    """Create a sample task for testing."""
    with app.app_context():
        task = Task(
            name="test-task",
            description="A test task for unit testing",
            priority="normal",
            payload='{"key": "value"}',
            created_by="test-user"
        )
        db.session.add(task)
        db.session.commit()
        return task.id


@pytest.fixture
def sample_user(app):
    """Create a sample user for testing."""
    with app.app_context():
        user = User(
            username="testuser",
            email="test@example.com",
            full_name="Test User"
        )
        db.session.add(user)
        db.session.commit()
        return user.id


# ---------------------------------------------------------------------------
# Application Factory Tests
# ---------------------------------------------------------------------------

class TestAppFactory:
    """Test the Flask application factory."""
    
    def test_create_app_with_default_config(self):
        """Test app factory creates app with default configuration."""
        app = create_app()
        assert app is not None
        assert app.config["TESTING"] == False
    
    def test_create_app_with_test_config(self):
        """Test app factory creates app with test configuration."""
        app = create_app("testing")
        assert app.config["TESTING"] == True
    
    def test_create_app_with_production_config(self):
        """Test app factory creates app with production configuration."""
        app = create_app("production")
        assert app is not None
    
    def test_app_has_database(self, app):
        """Test app is configured with database."""
        assert "sqlalchemy" in app.extensions
    
    def test_app_has_rate_limiter(self, app):
        """Test app is configured with rate limiter."""
        assert "limiter" in app.extensions


# ---------------------------------------------------------------------------
# Root Endpoint Tests
# ---------------------------------------------------------------------------

class TestRootEndpoint:
    """Test the root endpoint."""
    
    def test_root_returns_service_info(self, client):
        """Test root endpoint returns service information."""
        response = client.get("/")
        assert response.status_code == 200
        
        data = json.loads(response.data)
        assert data["service"] == "microservices-api"
        assert data["version"] == "1.0.0"
        assert data["status"] == "operational"
        assert "endpoints" in data
    
    def test_root_content_type(self, client):
        """Test root endpoint returns JSON."""
        response = client.get("/")
        assert response.content_type == "application/json"


# ---------------------------------------------------------------------------
# Health Endpoint Tests
# ---------------------------------------------------------------------------

class TestHealthEndpoints:
    """Test health check endpoints."""
    
    def test_basic_health_returns_200(self, client):
        """Test basic health endpoint returns 200."""
        response = client.get("/health")
        assert response.status_code == 200
    
    def test_basic_health_returns_healthy(self, client):
        """Test basic health endpoint returns healthy status."""
        response = client.get("/health")
        data = json.loads(response.data)
        assert data["status"] == "healthy"
        assert data["service"] == "api"
    
    def test_liveness_returns_alive(self, client):
        """Test liveness endpoint returns alive status."""
        response = client.get("/health/live")
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["status"] == "alive"
    
    def test_readiness_returns_checks(self, client):
        """Test readiness endpoint returns dependency checks."""
        response = client.get("/health/ready")
        assert response.status_code in [200, 503]  # May be degraded without Redis
        data = json.loads(response.data)
        assert "checks" in data
        assert "database" in data["checks"]
        assert "cache" in data["checks"]
        assert "worker" in data["checks"]
    
    def test_prometheus_metrics(self, client):
        """Test Prometheus metrics endpoint."""
        response = client.get("/health/metrics")
        assert response.status_code == 200
        assert response.content_type == "text/plain; charset=utf-8"
        assert "api_uptime_seconds" in response.data.decode()


# ---------------------------------------------------------------------------
# Task Endpoint Tests
# ---------------------------------------------------------------------------

class TestTaskEndpoints:
    """Test task CRUD endpoints."""
    
    def test_list_tasks_empty(self, client):
        """Test listing tasks returns empty list initially."""
        response = client.get("/api/v1/tasks")
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["data"] == []
        assert data["meta"]["total"] == 0
    
    def test_list_tasks_pagination(self, client):
        """Test task listing includes pagination metadata."""
        response = client.get("/api/v1/tasks")
        assert response.status_code == 200
        data = json.loads(response.data)
        assert "page" in data["meta"]
        assert "per_page" in data["meta"]
        assert "total_pages" in data["meta"]
    
    def test_create_task_success(self, client):
        """Test creating a task with valid data."""
        task_data = {
            "name": "integration-test-task",
            "description": "Test task creation",
            "priority": "high",
            "payload": '{"data": "test"}'
        }
        response = client.post(
            "/api/v1/tasks",
            data=json.dumps(task_data),
            content_type="application/json"
        )
        assert response.status_code == 201
        
        data = json.loads(response.data)
        assert data["message"] == "Task created successfully"
        assert data["data"]["name"] == "integration-test-task"
        assert data["data"]["status"] == "pending"
        assert data["data"]["priority"] == "high"
    
    def test_create_task_without_name_fails(self, client):
        """Test creating a task without name returns validation error."""
        task_data = {"description": "Missing name"}
        response = client.post(
            "/api/v1/tasks",
            data=json.dumps(task_data),
            content_type="application/json"
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert "error" in data
    
    def test_create_task_invalid_priority(self, client):
        """Test creating a task with invalid priority fails."""
        task_data = {"name": "test", "priority": "invalid"}
        response = client.post(
            "/api/v1/tasks",
            data=json.dumps(task_data),
            content_type="application/json"
        )
        assert response.status_code == 400
    
    def test_get_task_success(self, client, sample_task):
        """Test getting a task by ID."""
        response = client.get(f"/api/v1/tasks/{sample_task}")
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["data"]["id"] == sample_task
    
    def test_get_task_not_found(self, client):
        """Test getting non-existent task returns 404."""
        response = client.get("/api/v1/tasks/non-existent-id")
        assert response.status_code == 404
        data = json.loads(response.data)
        assert "error" in data
    
    def test_update_task_success(self, client, sample_task):
        """Test updating a task."""
        update_data = {"name": "updated-task-name", "priority": "low"}
        response = client.patch(
            f"/api/v1/tasks/{sample_task}",
            data=json.dumps(update_data),
            content_type="application/json"
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["data"]["name"] == "updated-task-name"
        assert data["data"]["priority"] == "low"
    
    def test_delete_task_success(self, client, sample_task):
        """Test deleting a task (soft delete)."""
        response = client.delete(f"/api/v1/tasks/{sample_task}")
        assert response.status_code == 200
        
        # Verify task is soft-deleted
        get_response = client.get(f"/api/v1/tasks/{sample_task}")
        assert get_response.status_code == 404
    
    def test_filter_tasks_by_status(self, client, sample_task):
        """Test filtering tasks by status."""
        response = client.get("/api/v1/tasks?status=pending")
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["meta"]["total"] >= 1
    
    def test_task_pagination(self, client):
        """Test task pagination parameters."""
        # Create multiple tasks
        for i in range(5):
            client.post(
                "/api/v1/tasks",
                data=json.dumps({"name": f"task-{i}"}),
                content_type="application/json"
            )
        
        # Request first page with 2 items
        response = client.get("/api/v1/tasks?page=1&per_page=2")
        data = json.loads(response.data)
        assert len(data["data"]) == 2
        assert data["meta"]["page"] == 1
        assert data["meta"]["per_page"] == 2


# ---------------------------------------------------------------------------
# User Endpoint Tests
# ---------------------------------------------------------------------------

class TestUserEndpoints:
    """Test user CRUD endpoints."""
    
    def test_list_users_empty(self, client):
        """Test listing users returns empty list initially."""
        response = client.get("/api/v1/users")
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["data"] == []
    
    def test_create_user_success(self, client):
        """Test creating a user with valid data."""
        user_data = {
            "username": "newuser",
            "email": "newuser@example.com",
            "full_name": "New User"
        }
        response = client.post(
            "/api/v1/users",
            data=json.dumps(user_data),
            content_type="application/json"
        )
        assert response.status_code == 201
        data = json.loads(response.data)
        assert data["data"]["username"] == "newuser"
    
    def test_create_user_duplicate_username(self, client, sample_user):
        """Test creating a user with duplicate username fails."""
        user_data = {
            "username": "testuser",
            "email": "different@example.com"
        }
        response = client.post(
            "/api/v1/users",
            data=json.dumps(user_data),
            content_type="application/json"
        )
        assert response.status_code == 409
    
    def test_get_user_success(self, client, sample_user):
        """Test getting a user by ID."""
        response = client.get(f"/api/v1/users/{sample_user}")
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["data"]["id"] == sample_user


# ---------------------------------------------------------------------------
# Statistics Endpoint Tests
# ---------------------------------------------------------------------------

class TestStatisticsEndpoints:
    """Test statistics endpoints."""
    
    def test_get_statistics(self, client):
        """Test getting system statistics."""
        response = client.get("/api/v1/stats")
        assert response.status_code == 200
        data = json.loads(response.data)
        assert "data" in data
        assert "tasks_by_status" in data["data"]
        assert "tasks_by_priority" in data["data"]
    
    def test_stats_after_task_creation(self, client):
        """Test statistics reflect task creation."""
        # Create a task first
        client.post(
            "/api/v1/tasks",
            data=json.dumps({"name": "stats-test", "priority": "high"}),
            content_type="application/json"
        )
        
        response = client.get("/api/v1/stats")
        data = json.loads(response.data)
        assert data["data"]["tasks_by_status"]["pending"] >= 1


# ---------------------------------------------------------------------------
# Error Handling Tests
# ---------------------------------------------------------------------------

class TestErrorHandling:
    """Test error handling and edge cases."""
    
    def test_404_error(self, client):
        """Test 404 error handling."""
        response = client.get("/nonexistent-endpoint")
        assert response.status_code == 404
        data = json.loads(response.data)
        assert "error" in data
    
    def test_invalid_json_body(self, client):
        """Test handling of invalid JSON in request body."""
        response = client.post(
            "/api/v1/tasks",
            data="not valid json",
            content_type="application/json"
        )
        # Flask will handle invalid JSON
        assert response.status_code in [400, 500]
    
    def test_method_not_allowed(self, client):
        """Test handling of HTTP method not allowed."""
        response = client.put("/api/v1/tasks")
        assert response.status_code == 405
    
    def test_request_headers(self, client):
        """Test response contains request tracking headers."""
        response = client.get("/health")
        assert "X-Request-ID" in response.headers
        assert "X-Response-Time" in response.headers


# ---------------------------------------------------------------------------
# Model Tests
# ---------------------------------------------------------------------------

class TestTaskModel:
    """Test Task model methods and behavior."""
    
    def test_task_creation(self, app):
        """Test creating a task in the database."""
        with app.app_context():
            task = Task(name="model-test", description="Testing models")
            db.session.add(task)
            db.session.commit()
            
            assert task.id is not None
            assert task.status == "pending"
            assert task.priority == "normal"
    
    def test_task_mark_started(self, app):
        """Test marking a task as started."""
        with app.app_context():
            task = Task(name="start-test")
            task.mark_started()
            assert task.status == "running"
            assert task.started_at is not None
    
    def test_task_mark_completed(self, app):
        """Test marking a task as completed."""
        with app.app_context():
            task = Task(name="complete-test")
            task.mark_started()
            task.mark_completed('{"result": "success"}')
            assert task.status == "completed"
            assert task.result == '{"result": "success"}'
            assert task.completed_at is not None
    
    def test_task_mark_failed(self, app):
        """Test marking a task as failed."""
        with app.app_context():
            task = Task(name="fail-test")
            task.mark_started()
            task.mark_failed("Something went wrong")
            assert task.status == "failed"
            assert task.error_message == "Something went wrong"
    
    def test_task_to_dict(self, app):
        """Test task serialization to dictionary."""
        with app.app_context():
            task = Task(name="serialize-test", priority="high")
            db.session.add(task)
            db.session.commit()
            
            data = task.to_dict()
            assert data["name"] == "serialize-test"
            assert data["priority"] == "high"
            assert "id" in data
            assert "created_at" in data


class TestUserModel:
    """Test User model methods."""
    
    def test_user_creation(self, app):
        """Test creating a user."""
        with app.app_context():
            user = User(username="modeluser", email="model@example.com")
            db.session.add(user)
            db.session.commit()
            assert user.id is not None
            assert user.is_active == True


# ---------------------------------------------------------------------------
# API Documentation Tests
# ---------------------------------------------------------------------------

class TestApiDocs:
    """Test API documentation endpoint."""
    
    def test_api_docs_returns_documentation(self, client):
        """Test API docs endpoint returns documentation."""
        response = client.get("/api/v1/docs")
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["service"] == "Microservices API"
        assert "endpoints" in data
        assert "tasks" in data["endpoints"]
        assert "users" in data["endpoints"]


# ---------------------------------------------------------------------------
# Integration Tests
# ---------------------------------------------------------------------------

class TestIntegrationFlow:
    """Integration tests covering full workflows."""
    
    def test_full_task_lifecycle(self, client):
        """Test complete task lifecycle: create -> get -> update -> delete."""
        # Create
        create_response = client.post(
            "/api/v1/tasks",
            data=json.dumps({
                "name": "lifecycle-test",
                "description": "Full lifecycle test",
                "priority": "critical"
            }),
            content_type="application/json"
        )
        assert create_response.status_code == 201
        task_id = json.loads(create_response.data)["data"]["id"]
        
        # Get
        get_response = client.get(f"/api/v1/tasks/{task_id}")
        assert get_response.status_code == 200
        
        # Update
        update_response = client.patch(
            f"/api/v1/tasks/{task_id}",
            data=json.dumps({"status": "running"}),
            content_type="application/json"
        )
        assert update_response.status_code == 200
        assert json.loads(update_response.data)["data"]["status"] == "running"
        
        # Delete
        delete_response = client.delete(f"/api/v1/tasks/{task_id}")
        assert delete_response.status_code == 200
        
        # Verify deleted
        verify_response = client.get(f"/api/v1/tasks/{task_id}")
        assert verify_response.status_code == 404
    
    def test_concurrent_task_creation(self, client):
        """Test creating multiple tasks."""
        task_names = [f"concurrent-{i}" for i in range(10)]
        
        for name in task_names:
            response = client.post(
                "/api/v1/tasks",
                data=json.dumps({"name": name, "priority": "normal"}),
                content_type="application/json"
            )
            assert response.status_code == 201
        
        # Verify all were created
        list_response = client.get("/api/v1/tasks")
        data = json.loads(list_response.data)
        assert data["meta"]["total"] >= 10


# Run tests with: pytest tests/ -v --cov=src --cov-report=term-missing
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
