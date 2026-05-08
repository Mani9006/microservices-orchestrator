# Microservices Orchestrator - Architecture Documentation

## Table of Contents

1. [Overview](#overview)
2. [Architecture Diagram](#architecture-diagram)
3. [Service Descriptions](#service-descriptions)
4. [Data Flow](#data-flow)
5. [Communication Patterns](#communication-patterns)
6. [Security Architecture](#security-architecture)
7. [Scalability Design](#scalability-design)
8. [Disaster Recovery](#disaster-recovery)
9. [Technology Stack](#technology-stack)
10. [Future Improvements](#future-improvements)

---

## Overview

The Containerized Microservices Orchestrator is a production-ready platform for deploying, managing, and monitoring containerized services. It demonstrates best practices in Docker containerization, service orchestration, health monitoring, and infrastructure automation.

### Key Design Principles

- **Separation of Concerns**: Each service has a single, well-defined responsibility
- **Network Isolation**: Backend services are isolated from direct external access
- **Health Monitoring**: Every service exposes health endpoints for monitoring
- **Graceful Degradation**: System remains functional when non-critical services fail
- **Security First**: Non-root users, minimal images, secrets management
- **Observability**: Structured logging, metrics, and tracing throughout

---

## Architecture Diagram

```
                                    +------------------+
                                    |     Client       |
                                    +--------+---------+
                                             |
                                             | HTTP/HTTPS
                                             v
+------------------+              +----------+----------+
|   Load Balancer  |<------------>|   Nginx Reverse     |
|   (External)     |              |   Proxy             |
+--------+---------+              |   - SSL Termination |
         |                       |   - Rate Limiting   |
         |                       |   - Request Routing |
         |                       +----------+----------+
         |                                  |
         |                       +----------+----------+
         |                       |                     |
         v                       v                     v
+--------+---------+  +---------+---------+  +-------+--------+
|   Monitoring     |  |     API Service   |  | Worker Health  |
|   Stack          |  |     (Flask)       |  | Endpoint       |
|   (Prometheus +  |  |                   |  |                |
|   Grafana)       |  |  - REST API       |  |  - Celery      |
+------------------+  |  - Task CRUD      |  |    Tasks       |
                      |  - Health Checks  |  +----------------+
                      |  - Rate Limiting  |
                      +---------+---------+
                                |
                     +----------+----------+
                     |                     |
                     v                     v
         +-----------+---------+  +--------+--------+
         |   PostgreSQL DB     |  |   Redis Cache   |
         |   - Task Storage    |  |   & Message     |
         |   - User Data       |  |   Broker        |
         |   - Audit Logs      |  |   - Task Queue  |
         +---------------------+  |   - Rate Limit  |
                                  |   - Sessions    |
                                  +--------+--------+
                                           |
                                           v
                                 +---------+--------+
                                 |  Celery Worker   |
                                 |  - Task Process  |
                                 |  - Email Send    |
                                 |  - Report Gen    |
                                 +------------------+

+--------------------------------------------------------------+
|                        Networks                              |
|  frontend: Nginx <-> API (172.28.1.0/24)                   |
|  backend:  API, Worker, DB, Redis (172.28.2.0/24)           |
|  monitoring: Prometheus, Grafana (172.28.3.0/24)           |
+--------------------------------------------------------------+
```

---

## Service Descriptions

### Nginx Reverse Proxy

The entry point for all external traffic. Handles SSL termination, rate limiting, request routing, and security headers.

| Aspect | Detail |
|--------|--------|
| **Base Image** | nginx:1.25-alpine |
| **User** | nginx (non-root, uid 101) |
| **Ports** | 80 (HTTP), 443 (HTTPS), 8080 (Health) |
| **Health** | `/health` on port 8080 |

**Key Features:**
- Least-connections load balancing to API backends
- Rate limiting (100 req/min general, 10 req/min auth)
- Gzip compression
- Security headers (X-Frame-Options, HSTS, CSP)
- CORS support
- Request ID tracking

### API Service (Flask)

The main REST API providing endpoints for task management, user management, and system operations.

| Aspect | Detail |
|--------|--------|
| **Base Image** | python:3.11-slim |
| **User** | appuser (uid 1000) |
| **Port** | 5000 |
| **Framework** | Flask 2.3.3 + Gunicorn |

**Key Features:**
- RESTful API with JSON responses
- SQLAlchemy ORM with connection pooling
- Rate limiting via Flask-Limiter
- Request/response logging with request IDs
- Comprehensive error handling
- Prometheus metrics endpoint
- Multi-stage Docker build (builder/production/development)

### Celery Worker

Background task processor using Celery with Redis as the broker.

| Aspect | Detail |
|--------|--------|
| **Base Image** | python:3.11-slim |
| **User** | workeruser (uid 1000) |
| **Port** | 5001 (health) |
| **Concurrency** | 4 workers (configurable) |

**Key Features:**
- Task routing across multiple queues
- Retry logic with exponential backoff
- Task prioritization (high/normal/low)
- Signal handlers for monitoring
- Health check HTTP server
- Graceful shutdown on SIGTERM

### PostgreSQL Database

Primary data store for the application.

| Aspect | Detail |
|--------|--------|
| **Base Image** | postgres:16-alpine |
| **Port** | 5432 |
| **Storage** | Named volume with bind mount |

**Key Features:**
- Persistent data via Docker volumes
- Initialization script with seed data
- Connection pooling configuration
- Audit logging triggers
- pg_stat_statements for query monitoring

### Redis Cache & Broker

Caching layer and message broker for Celery.

| Aspect | Detail |
|--------|--------|
| **Base Image** | redis:7-alpine |
| **Port** | 6379 |
| **Memory** | 256MB max with LRU eviction |

**Key Features:**
- Password authentication
- AOF persistence
- Memory management with LRU policy
- Connection keepalive
- Health check via `redis-cli ping`

### Celery Beat Scheduler

Periodic task scheduler for recurring jobs.

**Scheduled Tasks:**
- `cleanup_old_tasks` - Every hour
- `send_health_report` - Every 5 minutes
- `worker_heartbeat` - Every minute

### Monitoring Stack

- **Prometheus**: Metrics collection and alerting
- **Grafana**: Visualization dashboards
- **cAdvisor**: Container resource metrics
- **Node Exporter**: Host system metrics

---

## Data Flow

### Task Creation Flow

```
Client -> Nginx -> API -> PostgreSQL (store task)
                          -> Redis (enqueue task)
                               -> Celery Worker (process task)
                                    -> PostgreSQL (update status)
                                    -> Redis (store result)
```

### Health Check Flow

```
Client -> Nginx -> API /health
                   -> API /health/ready (checks DB + Redis + Worker)
                   -> API /health/live (liveness probe)
                   -> API /health/metrics (Prometheus)
```

### Log Aggregation Flow

```
API/Worker/Beat -> Log Files -> Fluent Bit -> Centralized Storage
Nginx -> Access/Error Logs -> Fluent Bit -> Centralized Storage
```

---

## Communication Patterns

### Synchronous (HTTP)

- Client <-> Nginx <-> API
- Health checks between services
- Status updates

### Asynchronous (Message Queue)

- API -> Redis -> Celery Worker
- Scheduled tasks via Celery Beat
- Event-driven processing

### Shared Data (Database)

- All services read/write to PostgreSQL
- Tasks table tracks job state
- Audit logs record operations

---

## Security Architecture

### Container Security

- Non-root users in all containers
- Minimal base images (Alpine/Debian slim)
- No unnecessary packages
- Read-only filesystems where possible
- `no-new-privileges` security option

### Network Security

- Backend network is internal (no external access)
- Only Nginx exposes ports externally
- Service-to-service communication via Docker networks

### Secrets Management

- Passwords in `.env` file (never committed)
- `.env.example` documents all variables
- Redis password authentication
- PostgreSQL password authentication

### Application Security

- Rate limiting on all endpoints
- Input validation with Marshmallow schemas
- SQL injection prevention via ORM
- XSS protection headers
- CSRF protection

---

## Scalability Design

### Horizontal Scaling

```
                  +--------+
                  | Nginx  |
                  +---+----+
                      |
           +----------+----------+
           |          |          |
           v          v          v
      +----+---+ +----+---+ +----+---+
      | API 1  | | API 2  | | API 3  |
      +----+---+ +----+---+ +----+---+
           |          |          |
           +----------+----------+
                      |
              +-------+-------+
              |   PostgreSQL  |
              +---------------+
```

### Scaling Strategies

| Service | Scaling Strategy |
|---------|-----------------|
| Nginx | Multiple instances with external LB |
| API | Stateless - scale replicas horizontally |
| Worker | Scale based on queue depth |
| PostgreSQL | Read replicas, connection pooling |
| Redis | Redis Cluster or Sentinel |

---

## Disaster Recovery

### Backup Strategy

- **Database**: Daily automated backups via `scripts/backup.sh`
- **Retention**: 7 days default, 30 days production
- **S3 Upload**: Optional S3-compatible storage
- **Verification**: Backup integrity verification

### Recovery Procedures

1. **Database Restore**: `make restore FILE=backup.dump`
2. **Service Restart**: `make restart`
3. **Full Recovery**: `make down && make up`

---

## Technology Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| Reverse Proxy | Nginx 1.25 | Load balancing, SSL, routing |
| API Framework | Flask 2.3.3 | REST API |
| WSGI Server | Gunicorn 21.2 | Production WSGI |
| ORM | SQLAlchemy 2.0 | Database abstraction |
| Database | PostgreSQL 16 | Primary data store |
| Cache/Broker | Redis 7 | Caching, task queue |
| Task Queue | Celery 5.3 | Background processing |
| Monitoring | Prometheus 2.48 | Metrics collection |
| Visualization | Grafana 10.2 | Dashboards |
| Metrics | Prometheus Client | App metrics |
| Logging | Python JSON Logger | Structured logging |
| Validation | Marshmallow 3.20 | Request validation |
| Rate Limiting | Flask-Limiter | API rate limiting |
| Testing | pytest 7.4 | Unit/integration tests |
| Formatting | Black 23.11 | Code formatting |

---

## Future Improvements

1. **Kubernetes Deployment**: Helm charts and K8s manifests
2. **Service Mesh**: Istio or Linkerd for mTLS and traffic management
3. **Distributed Tracing**: Jaeger or Zipkin integration
4. **Schema Registry**: Avro/Protobuf for message serialization
5. **Event Sourcing**: Apache Kafka for event streaming
6. **Multi-region**: Geographic distribution with failover
7. **GitOps**: ArgoCD for declarative deployments
8. **Policy Engine**: OPA for admission control
9. **Secret Management**: HashiCorp Vault integration
10. **Cost Optimization**: Spot instances and autoscaling policies
