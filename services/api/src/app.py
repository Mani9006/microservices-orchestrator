#!/usr/bin/env python3
# =============================================================================
# API Service Application Factory
# =============================================================================
# This module implements the Flask application factory pattern, allowing
# flexible configuration for different environments (dev, test, prod).
# The factory creates and configures the Flask app with database connections,
# request handlers, logging, and error management.
# =============================================================================

import os
import sys
import logging
from datetime import datetime
from flask import Flask, jsonify, request
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_marshmallow import Marshmallow
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from sqlalchemy.exc import SQLAlchemyError

# ---------------------------------------------------------------------------
# Extension Instances (initialized in app factory)
# ---------------------------------------------------------------------------
db = SQLAlchemy()
migrate = Migrate()
ma = Marshmallow()
limiter = Limiter(key_func=get_remote_address)


def setup_logging(app: Flask) -> None:
    """Configure structured JSON logging for the application.
    
    Sets up logging handlers for both console (development) and file
    (production) output with appropriate formatting and log levels.
    """
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    log_format = os.getenv("LOG_FORMAT", "json").lower()
    
    # Create formatter based on configuration
    if log_format == "json":
        from pythonjsonlogger import jsonlogger
        formatter = jsonlogger.JsonFormatter(
            "%(asctime)s %(levelname)s %(name)s %(message)s %(pathname)s %(lineno)d"
        )
    else:
        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s - %(message)s"
        )
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(getattr(logging, log_level, logging.INFO))
    
    # Configure root logger for the app
    app.logger.handlers.clear()
    app.logger.addHandler(console_handler)
    app.logger.setLevel(getattr(logging, log_level, logging.INFO))
    
    # Set log levels for third-party libraries to reduce noise
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    
    app.logger.info("Logging configured", extra={"level": log_level, "format": log_format})


def register_error_handlers(app: Flask) -> None:
    """Register global error handlers for the application.
    
    Provides consistent JSON error responses for common HTTP errors
    and unhandled exceptions.
    """
    
    @app.errorhandler(400)
    def bad_request(error):
        app.logger.warning("Bad request", extra={"path": request.path, "error": str(error)})
        return jsonify({
            "error": "Bad Request",
            "message": str(error.description if hasattr(error, "description") else "Invalid request"),
            "status_code": 400
        }), 400
    
    @app.errorhandler(404)
    def not_found(error):
        return jsonify({
            "error": "Not Found",
            "message": f"The requested resource '{request.path}' was not found",
            "status_code": 404
        }), 404
    
    @app.errorhandler(429)
    def rate_limit_exceeded(error):
        return jsonify({
            "error": "Too Many Requests",
            "message": "Rate limit exceeded. Please try again later.",
            "status_code": 429,
            "retry_after": error.description if hasattr(error, "description") else "60"
        }), 429
    
    @app.errorhandler(500)
    def internal_error(error):
        app.logger.error("Internal server error", exc_info=True, extra={"path": request.path})
        db.session.rollback()
        return jsonify({
            "error": "Internal Server Error",
            "message": "An unexpected error occurred. Please try again later.",
            "status_code": 500
        }), 500
    
    @app.errorhandler(SQLAlchemyError)
    def database_error(error):
        app.logger.error("Database error", exc_info=True, extra={"path": request.path})
        db.session.rollback()
        return jsonify({
            "error": "Database Error",
            "message": "A database error occurred. Please try again later.",
            "status_code": 500
        }), 500


def register_request_hooks(app: Flask) -> None:
    """Register before/after request hooks for request tracking and cleanup.
    
    Adds request timing, logging, and database session management.
    """
    
    @app.before_request
    def before_request():
        request.start_time = datetime.utcnow()
        request.request_id = os.urandom(8).hex()
    
    @app.after_request
    def after_request(response):
        # Calculate request duration
        duration = (datetime.utcnow() - request.start_time).total_seconds()
        
        # Add custom headers
        response.headers["X-Request-ID"] = getattr(request, "request_id", "unknown")
        response.headers["X-Response-Time"] = f"{duration:.4f}s"
        
        # Log request completion
        app.logger.info(
            "Request completed",
            extra={
                "method": request.method,
                "path": request.path,
                "status_code": response.status_code,
                "duration_seconds": duration,
                "request_id": getattr(request, "request_id", "unknown"),
                "remote_addr": request.remote_addr
            }
        )
        return response


def create_app(config_name: str = None) -> Flask:
    """Application factory: creates and configures the Flask application.
    
    Args:
        config_name: Configuration environment name (development, production, testing).
                    Defaults to value from FLASK_ENV or 'production'.
    
    Returns:
        Configured Flask application instance.
    """
    config_name = config_name or os.getenv("FLASK_ENV", "production")
    
    # Create Flask app instance
    app = Flask(__name__)
    
    # -----------------------------------------------------------------------
    # Configuration
    # -----------------------------------------------------------------------
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret-change-in-production")
    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv(
        "DATABASE_URL",
        "postgresql://postgres:postgres@postgres:5432/microservices"
    )
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "pool_size": int(os.getenv("DB_POOL_SIZE", "10")),
        "max_overflow": int(os.getenv("DB_MAX_OVERFLOW", "20")),
        "pool_timeout": int(os.getenv("DB_POOL_TIMEOUT", "30")),
        "pool_recycle": int(os.getenv("DB_POOL_RECYCLE", "1800")),
        "pool_pre_ping": True  # Verify connections before use
    }
    
    # Rate limiting configuration
    app.config["RATELIMIT_STORAGE_URI"] = os.getenv(
        "REDIS_URL",
        "redis://redis:6379/0"
    )
    app.config["RATELIMIT_STRATEGY"] = "fixed-window"
    app.config["RATELIMIT_DEFAULT"] = "100/minute"
    app.config["RATELIMIT_HEADERS_ENABLED"] = True
    
    # Redis configuration for caching and task queue
    app.config["REDIS_URL"] = os.getenv("REDIS_URL", "redis://redis:6379/0")
    
    # -----------------------------------------------------------------------
    # Initialize Extensions
    # -----------------------------------------------------------------------
    db.init_app(app)
    migrate.init_app(app, db)
    ma.init_app(app)
    limiter.init_app(app)
    
    # -----------------------------------------------------------------------
    # Setup Application Components
    # -----------------------------------------------------------------------
    setup_logging(app)
    register_error_handlers(app)
    register_request_hooks(app)
    
    # -----------------------------------------------------------------------
    # Register Blueprints
    # -----------------------------------------------------------------------
    from src.health import health_bp
    from src.routes import api_bp
    
    app.register_blueprint(health_bp)
    app.register_blueprint(api_bp, url_prefix="/api/v1")
    
    # Root endpoint
    @app.route("/")
    def index():
        return jsonify({
            "service": "microservices-api",
            "version": "1.0.0",
            "status": "operational",
            "environment": config_name,
            "documentation": "/api/v1/docs",
            "endpoints": {
                "health": "/health",
                "api": "/api/v1"
            }
        })
    
    # Create database tables if they don't exist (for dev/testing)
    with app.app_context():
        try:
            db.create_all()
            app.logger.info("Database tables verified/created")
        except SQLAlchemyError as e:
            app.logger.warning(f"Could not create tables: {e}")
    
    app.logger.info(
        "Application initialized",
        extra={"environment": config_name, "debug": app.debug}
    )
    
    return app


# Entry point for direct execution
if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0", port=int(os.getenv("APP_PORT", "5000")))
