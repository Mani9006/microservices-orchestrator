#!/usr/bin/env python3
# =============================================================================
# API Service - Database Models
# =============================================================================
# This module defines SQLAlchemy ORM models for the microservices application.
# Models include Task (for background job tracking), User (for authentication),
# and AuditLog (for operation tracking).
# =============================================================================

import uuid
from datetime import datetime, timezone
from typing import Optional, List

from sqlalchemy import String, Text, DateTime, Boolean, Integer, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.app import db


def utc_now() -> datetime:
    """Return the current UTC datetime with timezone awareness."""
    return datetime.now(timezone.utc)


class Task(db.Model):
    """Represents a background task/job submitted to the worker service.
    
    Tracks the lifecycle of asynchronous tasks from creation through completion,
    including status, priority, input parameters, and results.
    """
    
    __tablename__ = "tasks"
    
    # Create indexes for common query patterns
    __table_args__ = (
        Index("ix_tasks_status_created", "status", "created_at"),
        Index("ix_tasks_user_created", "created_by", "created_at"),
    )
    
    id: Mapped[str] = mapped_column(
        String(36), primary_key=True,
        default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Task status tracking
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending",
        index=True
    )
    priority: Mapped[str] = mapped_column(
        String(10), nullable=False, default="normal"
    )  # low, normal, high, critical
    
    # Task input/output data (stored as JSON strings)
    payload: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    result: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Timing information
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    
    # Retry configuration
    max_retries: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    
    # Ownership
    created_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    # Soft delete support
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    
    def __repr__(self) -> str:
        return f"<Task(id='{self.id}', name='{self.name}', status='{self.status}')>"
    
    def to_dict(self) -> dict:
        """Serialize task to dictionary for API responses."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "status": self.status,
            "priority": self.priority,
            "payload": self.payload,
            "result": self.result,
            "error_message": self.error_message,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "max_retries": self.max_retries,
            "retry_count": self.retry_count,
            "created_by": self.created_by,
            "duration_seconds": self._calculate_duration()
        }
    
    def _calculate_duration(self) -> Optional[float]:
        """Calculate task execution duration in seconds."""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None
    
    def mark_started(self) -> None:
        """Mark the task as started."""
        self.status = "running"
        self.started_at = utc_now()
    
    def mark_completed(self, result: Optional[str] = None) -> None:
        """Mark the task as completed with optional result."""
        self.status = "completed"
        self.result = result
        self.completed_at = utc_now()
    
    def mark_failed(self, error_message: str) -> None:
        """Mark the task as failed with an error message."""
        self.status = "failed"
        self.error_message = error_message
        self.completed_at = utc_now()
    
    def mark_for_retry(self) -> bool:
        """Mark the task for retry if retries remain. Returns True if retried."""
        if self.retry_count < self.max_retries:
            self.retry_count += 1
            self.status = "pending"
            self.started_at = None
            self.completed_at = None
            return True
        self.mark_failed("Max retries exceeded")
        return False


class User(db.Model):
    """Represents a user in the system for task ownership and auditing.
    
    Minimal user model for tracking who created and owns tasks.
    """
    
    __tablename__ = "users"
    
    id: Mapped[str] = mapped_column(
        String(36), primary_key=True,
        default=lambda: str(uuid.uuid4())
    )
    username: Mapped[str] = mapped_column(
        String(100), nullable=False, unique=True, index=True
    )
    email: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True
    )
    full_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=utc_now, onupdate=utc_now
    )
    
    def __repr__(self) -> str:
        return f"<User(username='{self.username}', email='{self.email}')>"
    
    def to_dict(self) -> dict:
        """Serialize user to dictionary for API responses."""
        return {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "full_name": self.full_name,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }


class AuditLog(db.Model):
    """Tracks all significant operations in the system for audit purposes.
    
    Provides a complete audit trail of task lifecycle events and API access.
    """
    
    __tablename__ = "audit_logs"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    action: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)  # 'task', 'user', etc.
    entity_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    user_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    
    def __repr__(self) -> str:
        return f"<AuditLog(action='{self.action}', entity='{self.entity_type}:{self.entity_id}')>"
    
    def to_dict(self) -> dict:
        """Serialize audit log entry to dictionary."""
        return {
            "id": self.id,
            "action": self.action,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "user_id": self.user_id,
            "details": self.details,
            "ip_address": self.ip_address,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }
