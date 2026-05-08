-- =============================================================================
-- PostgreSQL Database Initialization Script
-- =============================================================================
-- This script initializes the microservices database with:
-- - Application user and database
-- - Schema creation
-- - Initial seed data for development/testing
-- - Performance optimization settings
-- =============================================================================

-- =============================================================================
-- Database and User Setup
-- =============================================================================

-- Create application user (if not exists)
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'appuser') THEN
        CREATE USER appuser WITH PASSWORD 'changeme-strong-password';
    END IF;
END
$$;

-- Grant privileges to application user
GRANT CONNECT ON DATABASE microservices TO appuser;

-- =============================================================================
-- Schema Setup
-- =============================================================================

-- Connect to the microservices database
\c microservices;

-- Grant schema usage
GRANT USAGE ON SCHEMA public TO appuser;
GRANT CREATE ON SCHEMA public TO appuser;

-- =============================================================================
-- Extensions
-- =============================================================================

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Enable pgcrypto for enhanced cryptographic functions
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Enable pg_stat_statements for query performance monitoring
CREATE EXTENSION IF NOT EXISTS "pg_stat_statements";

-- =============================================================================
-- Performance Settings (per-database)
-- =============================================================================

-- Set statement timeout to prevent runaway queries
ALTER DATABASE microservices SET statement_timeout = '60s';

-- Enable logging of slow queries
ALTER DATABASE microservices SET log_min_duration_statement = 1000;

-- =============================================================================
-- Audit Log Trigger Setup
-- =============================================================================

-- Create audit logging function
CREATE OR REPLACE FUNCTION audit_log_trigger()
RETURNS TRIGGER AS $$
BEGIN
    IF (TG_OP = 'DELETE') THEN
        INSERT INTO audit_logs (action, entity_type, entity_id, details, created_at)
        VALUES ('delete', TG_TABLE_NAME, OLD.id, row_to_json(OLD)::text, NOW());
        RETURN OLD;
    ELSIF (TG_OP = 'UPDATE') THEN
        INSERT INTO audit_logs (action, entity_type, entity_id, details, created_at)
        VALUES ('update', TG_TABLE_NAME, NEW.id, 
                json_build_object('old', row_to_json(OLD), 'new', row_to_json(NEW))::text,
                NOW());
        RETURN NEW;
    ELSIF (TG_OP = 'INSERT') THEN
        INSERT INTO audit_logs (action, entity_type, entity_id, details, created_at)
        VALUES ('create', TG_TABLE_NAME, NEW.id, row_to_json(NEW)::text, NOW());
        RETURN NEW;
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

-- =============================================================================
-- Initial Seed Data (Development Environment)
-- =============================================================================

-- Only seed data if the tables exist (they will be created by SQLAlchemy migrations)
-- This is a fallback for when migrations haven't run yet

DO $$
BEGIN
    -- Check if tasks table exists (created by application)
    IF EXISTS (SELECT FROM pg_tables WHERE tablename = 'tasks') THEN
        -- Seed users
        IF NOT EXISTS (SELECT 1 FROM users LIMIT 1) THEN
            INSERT INTO users (id, username, email, full_name, is_active, created_at, updated_at)
            VALUES 
                (uuid_generate_v4(), 'admin', 'admin@example.com', 'System Administrator', true, NOW(), NOW()),
                (uuid_generate_v4(), 'developer', 'dev@example.com', 'Developer User', true, NOW(), NOW()),
                (uuid_generate_v4(), 'tester', 'qa@example.com', 'QA Engineer', true, NOW(), NOW());
        END IF;

        -- Seed sample tasks
        IF NOT EXISTS (SELECT 1 FROM tasks LIMIT 1) THEN
            INSERT INTO tasks (
                id, name, description, status, priority, 
                payload, max_retries, retry_count, created_by, 
                is_deleted, created_at
            )
            VALUES 
                (uuid_generate_v4(), 'sample-data-processing', 
                 'Sample data processing task for testing', 
                 'pending', 'normal', 
                 '{"input": [1, 2, 3, 4, 5], "operation": "sum"}', 
                 3, 0, 'admin', false, NOW()),
                
                (uuid_generate_v4(), 'sample-email-digest', 
                 'Daily email digest generation', 
                 'completed', 'low', 
                 '{"recipients": ["admin@example.com"], "template": "daily_digest"}', 
                 3, 0, 'admin', false, NOW()),
                
                (uuid_generate_v4(), 'sample-report-generation', 
                 'Weekly performance report', 
                 'running', 'high', 
                 '{"report_type": "weekly", "format": "pdf"}', 
                 3, 0, 'developer', false, NOW()),
                
                (uuid_generate_v4(), 'sample-cleanup-job', 
                 'Clean up old temporary files', 
                 'pending', 'low', 
                 '{"retention_days": 7, "directories": ["/tmp", "/var/tmp"]}', 
                 3, 0, 'admin', false, NOW()),
                
                (uuid_generate_v4(), 'sample-health-check', 
                 'System health verification', 
                 'completed', 'normal', 
                 '{"checks": ["database", "redis", "disk_space"]}', 
                 3, 0, 'tester', false, NOW());
        END IF;

        -- Seed audit logs
        IF NOT EXISTS (SELECT 1 FROM audit_logs LIMIT 1) THEN
            INSERT INTO audit_logs (action, entity_type, entity_id, user_id, details, created_at)
            VALUES 
                ('create', 'user', (SELECT id FROM users WHERE username = 'admin' LIMIT 1), 
                 NULL, 'Initial admin user created during setup', NOW()),
                ('create', 'task', (SELECT id FROM tasks WHERE name = 'sample-data-processing' LIMIT 1), 
                 (SELECT id FROM users WHERE username = 'admin' LIMIT 1), 
                 'Sample task created during initialization', NOW());
        END IF;
    END IF;
END
$$;

-- =============================================================================
-- Grant Table Permissions
-- =============================================================================

-- Grant privileges on all existing and future tables
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO appuser;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE ON SEQUENCES TO appuser;

-- Grant privileges on existing tables if they exist
DO $$
DECLARE
    tbl_name text;
BEGIN
    FOR tbl_name IN 
        SELECT tablename FROM pg_tables 
        WHERE schemaname = 'public' 
    LOOP
        EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON %I TO appuser', tbl_name);
    END LOOP;
END
$$;

-- =============================================================================
-- Database Maintenance
-- =============================================================================

-- Run ANALYZE to update statistics
ANALYZE;
