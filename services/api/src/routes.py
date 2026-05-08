#!/usr/bin/env python3
# =============================================================================
# API Service - RESTful Route Definitions
# =============================================================================
# This module defines all REST API endpoints for the microservices platform.
# Endpoints are organized by resource type and include comprehensive validation,
# error handling, and audit logging.
# =============================================================================

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from flask import Blueprint, jsonify, request, current_app
from marshmallow import Schema, fields, validate, ValidationError
from sqlalchemy import desc, func
from sqlalchemy.exc import SQLAlchemyError

from src.app import db
from src.models import Task, User, AuditLog

# ---------------------------------------------------------------------------
# API Blueprint
# ---------------------------------------------------------------------------
api_bp = Blueprint("api", __name__)


# ---------------------------------------------------------------------------
# Request/Response Schemas (using Marshmallow)
# ---------------------------------------------------------------------------

class TaskCreateSchema(Schema):
    """Schema for validating task creation requests."""
    name = fields.String(
        required=True, validate=validate.Length(min=1, max=255),
        metadata={"description": "Task name"}
    )
    description = fields.String(
        allow_none=True, validate=validate.Length(max=1000)
    )
    priority = fields.String(
        validate=validate.OneOf(["low", "normal", "high", "critical"]),
        missing="normal"
    )
    payload = fields.String(allow_none=True)
    max_retries = fields.Integer(
        validate=validate.Range(min=0, max=10), missing=3
    )
    created_by = fields.String(allow_none=True)


class TaskUpdateSchema(Schema):
    """Schema for validating task update requests."""
    name = fields.String(validate=validate.Length(min=1, max=255))
    description = fields.String(allow_none=True, validate=validate.Length(max=1000))
    priority = fields.String(validate=validate.OneOf(["low", "normal", "high", "critical"]))
    status = fields.String(validate=validate.OneOf(["pending", "running", "completed", "failed", "cancelled"]))


class UserCreateSchema(Schema):
    """Schema for validating user creation requests."""
    username = fields.String(
        required=True, validate=validate.Length(min=3, max=100)
    )
    email = fields.Email(required=True)
    full_name = fields.String(allow_none=True, validate=validate.Length(max=200))


task_create_schema = TaskCreateSchema()
task_update_schema = TaskUpdateSchema()
user_create_schema = UserCreateSchema()


# ---------------------------------------------------------------------------
# Audit Logging Helper
# ---------------------------------------------------------------------------

def log_audit(
    action: str,
    entity_type: str,
    entity_id: Optional[str] = None,
    details: Optional[str] = None
) -> None:
    """Create an audit log entry for tracking operations.
    
    Args:
        action: The action being performed (create, update, delete, etc.)
        entity_type: The type of entity affected
        entity_id: The ID of the affected entity
        details: Additional details about the action
    """
    try:
        log_entry = AuditLog(
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            user_id=request.headers.get("X-User-ID"),
            details=details,
            ip_address=request.remote_addr,
            user_agent=request.user_agent.string if request.user_agent else None
        )
        db.session.add(log_entry)
        db.session.commit()
    except Exception as e:
        current_app.logger.error(f"Failed to create audit log: {e}")
        db.session.rollback()


# ---------------------------------------------------------------------------
# Task Endpoints
# ---------------------------------------------------------------------------

@api_bp.route("/tasks", methods=["GET"])
def list_tasks() -> Tuple[dict, int]:
    """List all tasks with optional filtering and pagination.
    
    Query Parameters:
        status: Filter by task status (pending, running, completed, failed)
        priority: Filter by priority level (low, normal, high, critical)
        page: Page number (default: 1)
        per_page: Items per page (default: 20, max: 100)
        sort: Sort field and direction (e.g., '-created_at')
    
    Returns:
        JSON response with paginated task list and metadata.
    """
    # Parse query parameters
    status_filter = request.args.get("status")
    priority_filter = request.args.get("priority")
    page = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("per_page", 20, type=int), 100)
    sort_field = request.args.get("sort", "-created_at")
    
    # Build query
    query = Task.query.filter(Task.is_deleted == False)
    
    if status_filter:
        query = query.filter(Task.status == status_filter)
    if priority_filter:
        query = query.filter(Task.priority == priority_filter)
    
    # Apply sorting
    if sort_field.startswith("-"):
        query = query.order_by(desc(getattr(Task, sort_field[1:])))
    else:
        query = query.order_by(getattr(Task, sort_field))
    
    # Execute paginated query
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    
    current_app.logger.info(
        "Tasks listed",
        extra={
            "filters": {"status": status_filter, "priority": priority_filter},
            "page": page, "total": pagination.total
        }
    )
    
    return jsonify({
        "data": [task.to_dict() for task in pagination.items],
        "meta": {
            "page": page,
            "per_page": per_page,
            "total": pagination.total,
            "total_pages": pagination.pages,
            "has_next": pagination.has_next,
            "has_prev": pagination.has_prev
        }
    }), 200


@api_bp.route("/tasks/<string:task_id>", methods=["GET"])
def get_task(task_id: str) -> Tuple[dict, int]:
    """Get a single task by ID.
    
    Args:
        task_id: The unique task identifier (UUID)
    
    Returns:
        JSON response with task details or 404 error.
    """
    task = Task.query.filter_by(id=task_id, is_deleted=False).first()
    
    if not task:
        return jsonify({"error": "Task not found", "task_id": task_id}), 404
    
    log_audit("view", "task", task_id)
    return jsonify({"data": task.to_dict()}), 200


@api_bp.route("/tasks", methods=["POST"])
def create_task() -> Tuple[dict, int]:
    """Create a new background task.
    
    Request Body:
        name (required): Task name
        description (optional): Task description
        priority (optional): Task priority (default: normal)
        payload (optional): JSON payload for task processing
        max_retries (optional): Maximum retry attempts (default: 3)
        created_by (optional): User identifier
    
    Returns:
        JSON response with created task details (201 Created).
    """
    # Validate request body
    try:
        data = task_create_schema.load(request.get_json() or {})
    except ValidationError as err:
        return jsonify({"error": "Validation failed", "details": err.messages}), 400
    
    # Create task record
    task = Task(
        name=data["name"],
        description=data.get("description"),
        priority=data.get("priority", "normal"),
        payload=data.get("payload"),
        max_retries=data.get("max_retries", 3),
        created_by=data.get("created_by"),
        status="pending"
    )
    
    try:
        db.session.add(task)
        db.session.commit()
        
        # Attempt to enqueue task to worker via Redis
        try:
            enqueue_task(task.id, task.name, task.payload)
        except Exception as e:
            current_app.logger.warning(
                f"Could not enqueue task to worker: {e}",
                extra={"task_id": task.id}
            )
        
        log_audit(
            "create", "task", task.id,
            details=f"Created task '{task.name}' with priority {task.priority}"
        )
        
        current_app.logger.info(
            "Task created",
            extra={"task_id": task.id, "name": task.name, "priority": task.priority}
        )
        
        return jsonify({
            "message": "Task created successfully",
            "data": task.to_dict()
        }), 201
        
    except SQLAlchemyError as e:
        db.session.rollback()
        current_app.logger.error(f"Database error creating task: {e}")
        return jsonify({"error": "Failed to create task"}), 500


@api_bp.route("/tasks/<string:task_id>", methods=["PATCH"])
def update_task(task_id: str) -> Tuple[dict, int]:
    """Update an existing task.
    
    Args:
        task_id: The unique task identifier (UUID)
    
    Request Body:
        Fields to update (name, description, priority, status)
    
    Returns:
        JSON response with updated task details.
    """
    task = Task.query.filter_by(id=task_id, is_deleted=False).first()
    
    if not task:
        return jsonify({"error": "Task not found", "task_id": task_id}), 404
    
    # Validate request body
    try:
        data = task_update_schema.load(request.get_json() or {})
    except ValidationError as err:
        return jsonify({"error": "Validation failed", "details": err.messages}), 400
    
    # Update allowed fields
    allowed_fields = ["name", "description", "priority", "status"]
    for field in allowed_fields:
        if field in data:
            setattr(task, field, data[field])
    
    try:
        db.session.commit()
        log_audit("update", "task", task_id, details=f"Updated fields: {list(data.keys())}")
        return jsonify({"message": "Task updated", "data": task.to_dict()}), 200
    except SQLAlchemyError as e:
        db.session.rollback()
        return jsonify({"error": "Failed to update task"}), 500


@api_bp.route("/tasks/<string:task_id>", methods=["DELETE"])
def delete_task(task_id: str) -> Tuple[dict, int]:
    """Soft-delete a task by marking it as deleted.
    
    Args:
        task_id: The unique task identifier (UUID)
    
    Returns:
        204 No Content on success.
    """
    task = Task.query.filter_by(id=task_id, is_deleted=False).first()
    
    if not task:
        return jsonify({"error": "Task not found", "task_id": task_id}), 404
    
    # Soft delete
    task.is_deleted = True
    task.deleted_at = datetime.now(timezone.utc)
    task.status = "cancelled"
    
    try:
        db.session.commit()
        log_audit("delete", "task", task_id)
        return jsonify({"message": "Task deleted successfully"}), 200
    except SQLAlchemyError as e:
        db.session.rollback()
        return jsonify({"error": "Failed to delete task"}), 500


@api_bp.route("/tasks/<string:task_id>/retry", methods=["POST"])
def retry_task(task_id: str) -> Tuple[dict, int]:
    """Retry a failed task.
    
    Args:
        task_id: The unique task identifier (UUID)
    
    Returns:
        JSON response with retry result.
    """
    task = Task.query.filter_by(id=task_id, is_deleted=False).first()
    
    if not task:
        return jsonify({"error": "Task not found", "task_id": task_id}), 404
    
    if task.status != "failed":
        return jsonify({
            "error": "Only failed tasks can be retried",
            "current_status": task.status
        }), 400
    
    retried = task.mark_for_retry()
    
    if retried:
        try:
            db.session.commit()
            enqueue_task(task.id, task.name, task.payload)
            log_audit("retry", "task", task_id)
            return jsonify({
                "message": "Task queued for retry",
                "data": task.to_dict()
            }), 200
        except SQLAlchemyError as e:
            db.session.rollback()
            return jsonify({"error": "Failed to retry task"}), 500
    else:
        return jsonify({
            "error": "Max retries exceeded",
            "retry_count": task.retry_count,
            "max_retries": task.max_retries
        }), 400


# ---------------------------------------------------------------------------
# User Endpoints
# ---------------------------------------------------------------------------

@api_bp.route("/users", methods=["GET"])
def list_users() -> Tuple[dict, int]:
    """List all users with optional filtering."""
    users = User.query.filter_by(is_active=True).all()
    return jsonify({"data": [user.to_dict() for user in users]}), 200


@api_bp.route("/users", methods=["POST"])
def create_user() -> Tuple[dict, int]:
    """Create a new user."""
    try:
        data = user_create_schema.load(request.get_json() or {})
    except ValidationError as err:
        return jsonify({"error": "Validation failed", "details": err.messages}), 400
    
    # Check for existing user
    existing = User.query.filter(
        (User.username == data["username"]) | (User.email == data["email"])
    ).first()
    
    if existing:
        return jsonify({"error": "Username or email already exists"}), 409
    
    user = User(
        username=data["username"],
        email=data["email"],
        full_name=data.get("full_name")
    )
    
    try:
        db.session.add(user)
        db.session.commit()
        log_audit("create", "user", user.id)
        return jsonify({"message": "User created", "data": user.to_dict()}), 201
    except SQLAlchemyError as e:
        db.session.rollback()
        return jsonify({"error": "Failed to create user"}), 500


@api_bp.route("/users/<string:user_id>", methods=["GET"])
def get_user(user_id: str) -> Tuple[dict, int]:
    """Get a user by ID."""
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404
    return jsonify({"data": user.to_dict()}), 200


# ---------------------------------------------------------------------------
# Statistics Endpoints
# ---------------------------------------------------------------------------

@api_bp.route("/stats", methods=["GET"])
def get_statistics() -> Tuple[dict, int]:
    """Get system statistics including task counts and performance metrics."""
    # Task counts by status
    status_counts = db.session.query(
        Task.status, func.count(Task.id)
    ).filter(Task.is_deleted == False).group_by(Task.status).all()
    
    # Task counts by priority
    priority_counts = db.session.query(
        Task.priority, func.count(Task.id)
    ).filter(Task.is_deleted == False).group_by(Task.priority).all()
    
    # Recent activity (tasks created in last 24 hours)
    from sqlalchemy import text
    recent_tasks = Task.query.filter(
        Task.created_at >= datetime.now(timezone.utc).replace(hour=0, minute=0, second=0)
    ).count()
    
    return jsonify({
        "data": {
            "tasks_by_status": {status: count for status, count in status_counts},
            "tasks_by_priority": {priority: count for priority, count in priority_counts},
            "recent_tasks_today": recent_tasks,
            "total_users": User.query.filter_by(is_active=True).count()
        }
    }), 200


# ---------------------------------------------------------------------------
# Task Queue Helper
# ---------------------------------------------------------------------------

def enqueue_task(task_id: str, task_name: str, payload: Optional[str]) -> None:
    """Enqueue a task to the Celery worker via Redis.
    
    Uses Celery's delay method to asynchronously execute the task.
    Falls back gracefully if Redis/Celery is unavailable.
    
    Args:
        task_id: The database task ID
        task_name: The name/type of task to execute
        payload: Optional JSON payload for the task
    """
    try:
        from celery import Celery
        
        celery_app = Celery("tasks")
        celery_app.conf.broker_url = current_app.config.get("REDIS_URL", "redis://redis:6379/0")
        celery_app.conf.result_backend = current_app.config.get("REDIS_URL", "redis://redis:6379/0")
        
        # Send task to worker
        celery_app.send_task(
            "worker.tasks.process_task",
            args=[task_id, task_name, payload],
            queue="default",
            countdown=0
        )
        
        current_app.logger.info(
            "Task enqueued",
            extra={"task_id": task_id, "task_name": task_name}
        )
        
    except ImportError:
        current_app.logger.warning("Celery not available, task not enqueued")
    except Exception as e:
        current_app.logger.error(f"Failed to enqueue task: {e}")
        raise


# ---------------------------------------------------------------------------
# Documentation Endpoint
# ---------------------------------------------------------------------------

@api_bp.route("/docs", methods=["GET"])
def api_docs() -> Tuple[dict, int]:
    """Return API documentation with available endpoints."""
    return jsonify({
        "service": "Microservices API",
        "version": "1.0.0",
        "documentation": "API Endpoint Reference",
        "base_url": "/api/v1",
        "endpoints": {
            "tasks": {
                "list": {"method": "GET", "path": "/tasks", "description": "List all tasks"},
                "create": {"method": "POST", "path": "/tasks", "description": "Create a new task"},
                "get": {"method": "GET", "path": "/tasks/<id>", "description": "Get task by ID"},
                "update": {"method": "PATCH", "path": "/tasks/<id>", "description": "Update task"},
                "delete": {"method": "DELETE", "path": "/tasks/<id>", "description": "Delete task"},
                "retry": {"method": "POST", "path": "/tasks/<id>/retry", "description": "Retry failed task"}
            },
            "users": {
                "list": {"method": "GET", "path": "/users", "description": "List all users"},
                "create": {"method": "POST", "path": "/users", "description": "Create a new user"},
                "get": {"method": "GET", "path": "/users/<id>", "description": "Get user by ID"}
            },
            "stats": {
                "get": {"method": "GET", "path": "/stats", "description": "Get system statistics"}
            }
        }
    }), 200
