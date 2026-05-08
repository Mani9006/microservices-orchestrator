#!/usr/bin/env python3
# =============================================================================
# API Service - Health Check Tests
# =============================================================================
# Dedicated test suite for health check endpoints covering all scenarios
# including healthy states, degraded states, and failure conditions.
# =============================================================================

import json
import pytest
from unittest.mock import patch, MagicMock

from src.app import create_app, db


class TestConfig:
    """Test-specific configuration."""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SECRET_KEY = "test-secret"
    RATELIMIT_ENABLED = False


@pytest.fixture
def app():
    """Create test Flask application."""
    app = create_app("testing")
    app.config.from_object(TestConfig)
    
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    """Create test client."""
    return app.test_client()


# ---------------------------------------------------------------------------
# Basic Health Tests
# ---------------------------------------------------------------------------

class TestBasicHealth:
    """Test the /health endpoint."""
    
    def test_returns_200_status(self, client):
        """Health endpoint returns HTTP 200."""
        response = client.get("/health")
        assert response.status_code == 200
    
    def test_returns_healthy_status(self, client):
        """Health endpoint returns healthy status."""
        response = client.get("/health")
        data = json.loads(response.data)
        assert data["status"] == "healthy"
    
    def test_returns_service_name(self, client):
        """Health endpoint includes service identifier."""
        response = client.get("/health")
        data = json.loads(response.data)
        assert data["service"] == "api"
    
    def test_returns_timestamp(self, client):
        """Health endpoint includes timestamp."""
        response = client.get("/health")
        data = json.loads(response.data)
        assert "timestamp" in data
    
    def test_returns_json_content_type(self, client):
        """Health endpoint returns JSON content type."""
        response = client.get("/health")
        assert response.content_type == "application/json"


# ---------------------------------------------------------------------------
# Liveness Tests
# ---------------------------------------------------------------------------

class TestLiveness:
    """Test the /health/live endpoint."""
    
    def test_returns_200_status(self, client):
        """Liveness endpoint returns HTTP 200."""
        response = client.get("/health/live")
        assert response.status_code == 200
    
    def test_returns_alive_status(self, client):
        """Liveness endpoint returns alive status."""
        response = client.get("/health/live")
        data = json.loads(response.data)
        assert data["status"] == "alive"
    
    def test_returns_uptime(self, client):
        """Liveness endpoint includes uptime."""
        response = client.get("/health/live")
        data = json.loads(response.data)
        assert "uptime_seconds" in data
        assert data["uptime_seconds"] >= 0
    
    def test_returns_service_name(self, client):
        """Liveness endpoint includes service name."""
        response = client.get("/health/live")
        data = json.loads(response.data)
        assert data["service"] == "api"


# ---------------------------------------------------------------------------
# Readiness Tests
# ---------------------------------------------------------------------------

class TestReadiness:
    """Test the /health/ready endpoint with various dependency states."""
    
    def test_returns_200_or_503(self, client):
        """Readiness endpoint returns 200 or 503."""
        response = client.get("/health/ready")
        assert response.status_code in [200, 503]
    
    def test_returns_checks_structure(self, client):
        """Readiness endpoint returns checks for all dependencies."""
        response = client.get("/health/ready")
        data = json.loads(response.data)
        assert "checks" in data
        assert "database" in data["checks"]
        assert "cache" in data["checks"]
        assert "worker" in data["checks"]
    
    def test_database_check_structure(self, client):
        """Database check has required fields."""
        response = client.get("/health/ready")
        data = json.loads(response.data)
        db_check = data["checks"]["database"]
        assert "component" in db_check
        assert "status" in db_check
        assert db_check["component"] == "database"
    
    def test_redis_check_structure(self, client):
        """Redis check has required fields."""
        response = client.get("/health/ready")
        data = json.loads(response.data)
        redis_check = data["checks"]["cache"]
        assert "component" in redis_check
        assert "status" in redis_check
        assert redis_check["component"] == "cache"
    
    def test_worker_check_structure(self, client):
        """Worker check has required fields."""
        response = client.get("/health/ready")
        data = json.loads(response.data)
        worker_check = data["checks"]["worker"]
        assert "component" in worker_check
        assert "status" in worker_check
        assert worker_check["component"] == "worker"
    
    def test_returns_system_info(self, client):
        """Readiness endpoint includes system information."""
        response = client.get("/health/ready")
        data = json.loads(response.data)
        assert "system" in data
        assert "version" in data["system"]
        assert "uptime_seconds" in data["system"]
    
    def test_overall_status_field(self, client):
        """Readiness endpoint includes overall status."""
        response = client.get("/health/ready")
        data = json.loads(response.data)
        assert "status" in data
        assert data["status"] in ["healthy", "degraded", "unhealthy"]
    
    @patch("src.health.check_redis")
    def test_degraded_when_redis_down(self, mock_redis, client):
        """Test degraded status when Redis is unavailable."""
        mock_redis.return_value = {
            "component": "cache",
            "status": "unhealthy",
            "message": "Connection refused",
            "timestamp": "2024-01-01T00:00:00+00:00"
        }
        
        response = client.get("/health/ready")
        data = json.loads(response.data)
        # Should be degraded but still 200 (still accepting traffic)
        assert data["status"] in ["healthy", "degraded"]


# ---------------------------------------------------------------------------
# Prometheus Metrics Tests
# ---------------------------------------------------------------------------

class TestPrometheusMetrics:
    """Test the /health/metrics endpoint."""
    
    def test_returns_200(self, client):
        """Metrics endpoint returns HTTP 200."""
        response = client.get("/health/metrics")
        assert response.status_code == 200
    
    def test_returns_plain_text(self, client):
        """Metrics endpoint returns plain text content type."""
        response = client.get("/health/metrics")
        assert response.content_type == "text/plain; charset=utf-8"
    
    def test_contains_uptime_metric(self, client):
        """Metrics include uptime gauge."""
        response = client.get("/health/metrics")
        text = response.data.decode()
        assert "api_uptime_seconds" in text
    
    def test_contains_info_metric(self, client):
        """Metrics include info gauge."""
        response = client.get("/health/metrics")
        text = response.data.decode()
        assert "api_info" in text
    
    def test_prometheus_format(self, client):
        """Metrics follow Prometheus exposition format."""
        response = client.get("/health/metrics")
        text = response.data.decode()
        assert text.startswith("# HELP")


# ---------------------------------------------------------------------------
# Health Check Component Tests
# ---------------------------------------------------------------------------

class TestDatabaseCheck:
    """Test database health check function."""
    
    def test_check_database_with_sqlite(self, app, client):
        """Database check works with SQLite test database."""
        with app.app_context():
            from src.health import check_database
            result = check_database()
            assert result["component"] == "database"
            assert "status" in result
            assert "response_time_ms" in result
    
    def test_database_check_timestamp(self, app, client):
        """Database check includes timestamp."""
        with app.app_context():
            from src.health import check_database
            result = check_database()
            assert "timestamp" in result


class TestRedisCheck:
    """Test Redis health check function."""
    
    def test_check_redis_returns_dict(self, app, client):
        """Redis check returns dictionary structure."""
        with app.app_context():
            from src.health import check_redis
            result = check_redis()
            assert isinstance(result, dict)
            assert result["component"] == "cache"
    
    def test_check_redis_has_status(self, app, client):
        """Redis check includes status field."""
        with app.app_context():
            from src.health import check_redis
            result = check_redis()
            assert "status" in result
            assert result["status"] in ["healthy", "unhealthy"]


class TestWorkerCheck:
    """Test worker health check function."""
    
    def test_check_worker_returns_dict(self, app, client):
        """Worker check returns dictionary structure."""
        with app.app_context():
            from src.health import check_worker
            result = check_worker()
            assert isinstance(result, dict)
            assert result["component"] == "worker"
    
    def test_check_worker_has_status(self, app, client):
        """Worker check includes status."""
        with app.app_context():
            from src.health import check_worker
            result = check_worker()
            assert "status" in result
            assert result["status"] in ["healthy", "degraded", "unhealthy"]


# ---------------------------------------------------------------------------
# Error Scenario Tests
# ---------------------------------------------------------------------------

class TestHealthErrorScenarios:
    """Test health check behavior under error conditions."""
    
    @patch("src.health.db")
    def test_database_error_handling(self, mock_db, client):
        """Health check handles database errors gracefully."""
        from sqlalchemy.exc import OperationalError
        mock_db.session.execute.side_effect = OperationalError(
            "Connection failed", None, None
        )
        
        with patch("src.health.db", mock_db):
            response = client.get("/health/ready")
            # Should return 503 since database is critical
            assert response.status_code == 503
    
    def test_invalid_health_subpath(self, client):
        """Test invalid health subpath returns 404."""
        response = client.get("/health/invalid")
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Performance Tests
# ---------------------------------------------------------------------------

class TestHealthPerformance:
    """Test health check performance characteristics."""
    
    def test_basic_health_response_time(self, client):
        """Basic health check responds within acceptable time."""
        import time
        start = time.time()
        response = client.get("/health")
        elapsed = time.time() - start
        
        assert response.status_code == 200
        assert elapsed < 1.0  # Should respond within 1 second
    
    def test_liveness_response_time(self, client):
        """Liveness check responds quickly."""
        import time
        start = time.time()
        response = client.get("/health/live")
        elapsed = time.time() - start
        
        assert response.status_code == 200
        assert elapsed < 0.5  # Should respond within 500ms


# Run with: pytest tests/test_health.py -v
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
