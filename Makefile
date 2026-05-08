# =============================================================================
# Makefile - Containerized Microservices Orchestrator
# =============================================================================
# Common commands for managing the microservices platform.
# Usage: make <target>
# =============================================================================

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
PROJECT_NAME := microservices-orchestrator
COMPOSE_FILE := docker-compose.yml
COMPOSE_PROD := docker-compose.prod.yml
COMPOSE_OVERRIDE := docker-compose.override.yml
COMPOSE_MONITORING := monitoring/docker-compose.monitoring.yml

# ---------------------------------------------------------------------------
# Colors for output
# ---------------------------------------------------------------------------
BLUE := \033[36m
GREEN := \033[32m
YELLOW := \033[33m
RED := \033[31m
RESET := \033[0m

# ---------------------------------------------------------------------------
# Default Target
# ---------------------------------------------------------------------------
.PHONY: help
help: ## Display this help message
	@echo ""
	@echo "$(BLUE)Containerized Microservices Orchestrator$(RESET)"
	@echo "=========================================="
	@echo ""
	@echo "$(GREEN)Setup & Configuration:$(RESET)"
	@echo "  $(YELLOW)setup$(RESET)            - Initialize project (create dirs, copy .env)"
	@echo "  $(YELLOW)config$(RESET)           - Validate and display compose configuration"
	@echo ""
	@echo "$(GREEN)Development:$(RESET)"
	@echo "  $(YELLOW)build$(RESET)            - Build all Docker images"
	@echo "  $(YELLOW)up$(RESET)               - Start all services (detached)"
	@echo "  $(YELLOW)up-fg$(RESET)            - Start all services (foreground)"
	@echo "  $(YELLOW)down$(RESET)             - Stop and remove all services"
	@echo "  $(YELLOW)restart$(RESET)          - Restart all services"
	@echo "  $(YELLOW)logs$(RESET)             - View logs from all services"
	@echo "  $(YELLOW)logs-api$(RESET)         - View API service logs"
	@echo "  $(YELLOW)logs-worker$(RESET)      - View worker service logs"
	@echo "  $(YELLOW)logs-db$(RESET)          - View database logs"
	@echo "  $(YELLOW)logs-nginx$(RESET)       - View nginx logs"
	@echo "  $(YELLOW)logs-follow$(RESET)      - Follow logs from all services"
	@echo ""
	@echo "$(GREEN)Production:$(RESET)"
	@echo "  $(YELLOW)prod-build$(RESET)       - Build production images"
	@echo "  $(YELLOW)prod-up$(RESET)          - Start production deployment"
	@echo "  $(YELLOW)prod-down$(RESET)        - Stop production deployment"
	@echo "  $(YELLOW)prod-logs$(RESET)        - View production logs"
	@echo ""
	@echo "$(GREEN)Tools & Services:$(RESET)"
	@echo "  $(YELLOW)tools-up$(RESET)         - Start development tools (Flower, Adminer, etc.)"
	@echo "  $(YELLOW)tools-down$(RESET)       - Stop development tools"
	@echo "  $(YELLOW)monitoring-up$(RESET)    - Start monitoring stack (Prometheus, Grafana)"
	@echo "  $(YELLOW)monitoring-down$(RESET)  - Stop monitoring stack"
	@echo ""
	@echo "$(GREEN)Testing:$(RESET)"
	@echo "  $(YELLOW)test$(RESET)             - Run all tests"
	@echo "  $(YELLOW)test-api$(RESET)         - Run API service tests"
	@echo "  $(YELLOW)test-worker$(RESET)      - Run worker service tests"
	@echo "  $(YELLOW)test-coverage$(RESET)    - Run tests with coverage report"
	@echo "  $(YELLOW)lint$(RESET)             - Run code linting"
	@echo "  $(YELLOW)format$(RESET)           - Format code with Black"
	@echo ""
	@echo "$(GREEN)Maintenance:$(RESET)"
	@echo "  $(YELLOW)shell-api$(RESET)        - Open shell in API container"
	@echo "  $(YELLOW)shell-worker$(RESET)     - Open shell in worker container"
	@echo "  $(YELLOW)shell-db$(RESET)         - Open PostgreSQL shell"
	@echo "  $(YELLOW)shell-redis$(RESET)      - Open Redis CLI"
	@echo "  $(YELLOW)backup$(RESET)           - Create database backup"
	@echo "  $(YELLOW)restore$(RESET)          - Restore database from backup"
	@echo "  $(YELLOW)migrate$(RESET)          - Run database migrations"
	@echo "  $(YELLOW)clean$(RESET)            - Remove all containers, volumes, and images"
	@echo "  $(YELLOW)clean-all$(RESET)        - Full cleanup including data"
	@echo ""
	@echo "$(GREEN)Health & Status:$(RESET)"
	@echo "  $(YELLOW)status$(RESET)           - Show running containers status"
	@echo "  $(YELLOW)health$(RESET)           - Check health of all services"
	@echo "  $(YELLOW)ps$(RESET)               - List running containers"
	@echo "  $(YELLOW)top$(RESET)              - Show resource usage"
	@echo ""

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
.PHONY: setup
setup: ## Initialize project - create directories and copy .env
	@echo "$(BLUE)Setting up project...$(RESET)"
	@mkdir -p data/postgres data/redis logs certs
	@if [ ! -f .env ]; then \
		cp .env.example .env; \
		echo "$(GREEN)Created .env from .env.example$(RESET)"; \
	else \
		echo "$(YELLOW).env already exists, skipping$(RESET)"; \
	fi
	@echo "$(GREEN)Setup complete!$(RESET)"
	@echo "$(YELLOW)Please edit .env with your actual configuration values.$(RESET)"

.PHONY: config
config: ## Validate and display compose configuration
	@echo "$(BLUE)Development configuration:$(RESET)"
	@docker compose -f $(COMPOSE_FILE) -f $(COMPOSE_OVERRIDE) config

.PHONY: config-prod
config-prod: ## Display production configuration
	@echo "$(BLUE)Production configuration:$(RESET)"
	@docker compose -f $(COMPOSE_FILE) -f $(COMPOSE_PROD) config

# ---------------------------------------------------------------------------
# Development
# ---------------------------------------------------------------------------
.PHONY: build
build: ## Build all Docker images
	@echo "$(BLUE)Building all services...$(RESET)"
	@docker compose -f $(COMPOSE_FILE) -f $(COMPOSE_OVERRIDE) build --parallel

.PHONY: build-no-cache
build-no-cache: ## Build all Docker images without cache
	@echo "$(BLUE)Building all services (no cache)...$(RESET)"
	@docker compose -f $(COMPOSE_FILE) -f $(COMPOSE_OVERRIDE) build --no-cache --parallel

.PHONY: up
up: ## Start all services in detached mode
	@echo "$(GREEN)Starting all services...$(RESET)"
	@docker compose -f $(COMPOSE_FILE) -f $(COMPOSE_OVERRIDE) up -d
	@echo "$(GREEN)Services started!$(RESET)"
	@echo "API: http://localhost:5000"
	@echo "Nginx: http://localhost"
	@echo "Worker Health: http://localhost:5001/health"

.PHONY: up-fg
up-fg: ## Start all services in foreground mode
	@echo "$(GREEN)Starting all services in foreground...$(RESET)"
	@docker compose -f $(COMPOSE_FILE) -f $(COMPOSE_OVERRIDE) up

.PHONY: down
down: ## Stop and remove all services
	@echo "$(YELLOW)Stopping all services...$(RESET)"
	@docker compose -f $(COMPOSE_FILE) -f $(COMPOSE_OVERRIDE) down

.PHONY: down-volumes
down-volumes: ## Stop services and remove volumes
	@echo "$(RED)Stopping services and removing volumes...$(RESET)"
	@docker compose -f $(COMPOSE_FILE) -f $(COMPOSE_OVERRIDE) down -v

.PHONY: restart
restart: ## Restart all services
	@echo "$(YELLOW)Restarting all services...$(RESET)"
	@docker compose -f $(COMPOSE_FILE) -f $(COMPOSE_OVERRIDE) restart

.PHONY: pull
pull: ## Pull latest images
	@echo "$(BLUE)Pulling latest images...$(RESET)"
	@docker compose -f $(COMPOSE_FILE) -f $(COMPOSE_OVERRIDE) pull

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
.PHONY: logs
logs: ## View logs from all services
	@docker compose -f $(COMPOSE_FILE) -f $(COMPOSE_OVERRIDE) logs --tail=100

.PHONY: logs-api
logs-api: ## View API service logs
	@docker compose -f $(COMPOSE_FILE) -f $(COMPOSE_OVERRIDE) logs --tail=100 -f api

.PHONY: logs-worker
logs-worker: ## View worker service logs
	@docker compose -f $(COMPOSE_FILE) -f $(COMPOSE_OVERRIDE) logs --tail=100 -f worker

.PHONY: logs-db
logs-db: ## View database logs
	@docker compose -f $(COMPOSE_FILE) -f $(COMPOSE_OVERRIDE) logs --tail=100 -f postgres

.PHONY: logs-nginx
logs-nginx: ## View nginx logs
	@docker compose -f $(COMPOSE_FILE) -f $(COMPOSE_OVERRIDE) logs --tail=100 -f nginx

.PHONY: logs-follow
logs-follow: ## Follow logs from all services
	@docker compose -f $(COMPOSE_FILE) -f $(COMPOSE_OVERRIDE) logs -f

.PHONY: logs-beat
logs-beat: ## View beat scheduler logs
	@docker compose -f $(COMPOSE_FILE) -f $(COMPOSE_OVERRIDE) logs --tail=100 -f beat

# ---------------------------------------------------------------------------
# Production
# ---------------------------------------------------------------------------
.PHONY: prod-build
prod-build: ## Build production images
	@echo "$(BLUE)Building production images...$(RESET)"
	@docker compose -f $(COMPOSE_FILE) -f $(COMPOSE_PROD) build --parallel

.PHONY: prod-up
prod-up: ## Start production deployment
	@echo "$(GREEN)Starting production deployment...$(RESET)"
	@docker compose -f $(COMPOSE_FILE) -f $(COMPOSE_PROD) up -d
	@echo "$(GREEN)Production deployment started!$(RESET)"

.PHONY: prod-down
prod-down: ## Stop production deployment
	@echo "$(YELLOW)Stopping production deployment...$(RESET)"
	@docker compose -f $(COMPOSE_FILE) -f $(COMPOSE_PROD) down

.PHONY: prod-logs
prod-logs: ## View production logs
	@docker compose -f $(COMPOSE_FILE) -f $(COMPOSE_PROD) logs --tail=100 -f

.PHONY: prod-restart
prod-restart: ## Restart production deployment
	@echo "$(YELLOW)Restarting production deployment...$(RESET)"
	@docker compose -f $(COMPOSE_FILE) -f $(COMPOSE_PROD) restart

# ---------------------------------------------------------------------------
# Development Tools
# ---------------------------------------------------------------------------
.PHONY: tools-up
tools-up: ## Start development tools (Flower, Adminer, Redis Commander)
	@echo "$(GREEN)Starting development tools...$(RESET)"
	@docker compose -f $(COMPOSE_FILE) -f $(COMPOSE_OVERRIDE) --profile tools up -d
	@echo "$(GREEN)Tools started!$(RESET)"
	@echo "Flower (Celery Monitoring): http://localhost:5555"
	@echo "Adminer (Database Admin): http://localhost:8082"
	@echo "Redis Commander: http://localhost:8081"
	@echo "Mailhog (Email): http://localhost:8025"

.PHONY: tools-down
tools-down: ## Stop development tools
	@echo "$(YELLOW)Stopping development tools...$(RESET)"
	@docker compose -f $(COMPOSE_FILE) -f $(COMPOSE_OVERRIDE) --profile tools down

# ---------------------------------------------------------------------------
# Monitoring
# ---------------------------------------------------------------------------
.PHONY: monitoring-up
monitoring-up: ## Start monitoring stack
	@echo "$(GREEN)Starting monitoring stack...$(RESET)"
	@docker compose -f $(COMPOSE_MONITORING) up -d
	@echo "$(GREEN)Monitoring started!$(RESET)"
	@echo "Prometheus: http://localhost:9090"
	@echo "Grafana: http://localhost:3000"

.PHONY: monitoring-down
monitoring-down: ## Stop monitoring stack
	@echo "$(YELLOW)Stopping monitoring stack...$(RESET)"
	@docker compose -f $(COMPOSE_MONITORING) down

.PHONY: monitoring-logs
monitoring-logs: ## View monitoring logs
	@docker compose -f $(COMPOSE_MONITORING) logs -f

# ---------------------------------------------------------------------------
# Testing
# ---------------------------------------------------------------------------
.PHONY: test
test: ## Run all tests
	@echo "$(BLUE)Running all tests...$(RESET)"
	@$(MAKE) test-api
	@$(MAKE) test-worker
	@echo "$(GREEN)All tests complete!$(RESET)"

.PHONY: test-api
test-api: ## Run API service tests
	@echo "$(BLUE)Running API tests...$(RESET)"
	@docker compose -f $(COMPOSE_FILE) -f $(COMPOSE_OVERRIDE) exec api pytest tests/ -v --tb=short

.PHONY: test-worker
test-worker: ## Run worker service tests
	@echo "$(BLUE)Running worker tests...$(RESET)"
	@docker compose -f $(COMPOSE_FILE) -f $(COMPOSE_OVERRIDE) exec worker pytest tests/ -v --tb=short

.PHONY: test-coverage
test-coverage: ## Run tests with coverage report
	@echo "$(BLUE)Running tests with coverage...$(RESET)"
	@docker compose -f $(COMPOSE_FILE) -f $(COMPOSE_OVERRIDE) exec api pytest tests/ -v --cov=src --cov-report=term-missing --cov-report=html
	@docker compose -f $(COMPOSE_FILE) -f $(COMPOSE_OVERRIDE) exec worker pytest tests/ -v --cov=src --cov-report=term-missing --cov-report=html

.PHONY: lint
lint: ## Run code linting
	@echo "$(BLUE)Running linting...$(RESET)"
	@docker compose -f $(COMPOSE_FILE) -f $(COMPOSE_OVERRIDE) exec api flake8 src/ tests/
	@docker compose -f $(COMPOSE_FILE) -f $(COMPOSE_OVERRIDE) exec worker flake8 src/ tests/
	@echo "$(GREEN)Linting complete!$(RESET)"

.PHONY: format
format: ## Format code with Black
	@echo "$(BLUE)Formatting code...$(RESET)"
	@docker compose -f $(COMPOSE_FILE) -f $(COMPOSE_OVERRIDE) exec api black src/ tests/
	@docker compose -f $(COMPOSE_FILE) -f $(COMPOSE_OVERRIDE) exec worker black src/ tests/
	@echo "$(GREEN)Formatting complete!$(RESET)"

.PHONY: typecheck
typecheck: ## Run type checking with mypy
	@echo "$(BLUE)Running type checks...$(RESET)"
	@docker compose -f $(COMPOSE_FILE) -f $(COMPOSE_OVERRIDE) exec api mypy src/
	@docker compose -f $(COMPOSE_FILE) -f $(COMPOSE_OVERRIDE) exec worker mypy src/

# ---------------------------------------------------------------------------
# Shell Access
# ---------------------------------------------------------------------------
.PHONY: shell-api
shell-api: ## Open shell in API container
	@docker compose -f $(COMPOSE_FILE) -f $(COMPOSE_OVERRIDE) exec api /bin/sh

.PHONY: shell-worker
shell-worker: ## Open shell in worker container
	@docker compose -f $(COMPOSE_FILE) -f $(COMPOSE_OVERRIDE) exec worker /bin/sh

.PHONY: shell-db
shell-db: ## Open PostgreSQL shell
	@docker compose -f $(COMPOSE_FILE) -f $(COMPOSE_OVERRIDE) exec postgres psql -U postgres -d microservices

.PHONY: shell-redis
shell-redis: ## Open Redis CLI
	@docker compose -f $(COMPOSE_FILE) -f $(COMPOSE_OVERRIDE) exec redis redis-cli

.PHONY: shell-nginx
shell-nginx: ## Open shell in Nginx container
	@docker compose -f $(COMPOSE_FILE) -f $(COMPOSE_OVERRIDE) exec nginx /bin/sh

# ---------------------------------------------------------------------------
# Database Operations
# ---------------------------------------------------------------------------
.PHONY: migrate
migrate: ## Run database migrations
	@echo "$(BLUE)Running database migrations...$(RESET)"
	@docker compose -f $(COMPOSE_FILE) -f $(COMPOSE_OVERRIDE) exec api flask db upgrade

.PHONY: migrate-init
migrate-init: ## Initialize database migrations
	@echo "$(BLUE)Initializing migrations...$(RESET)"
	@docker compose -f $(COMPOSE_FILE) -f $(COMPOSE_OVERRIDE) exec api flask db init

.PHONY: migrate-create
migrate-create: ## Create a new migration
	@echo "$(BLUE)Creating migration...$(RESET)"
	@docker compose -f $(COMPOSE_FILE) -f $(COMPOSE_OVERRIDE) exec api flask db migrate -m "$(MSG)"

.PHONY: db-seed
db-seed: ## Seed database with initial data
	@echo "$(BLUE)Seeding database...$(RESET)"
	@docker compose -f $(COMPOSE_FILE) -f $(COMPOSE_OVERRIDE) exec postgres psql -U postgres -d microservices -f /docker-entrypoint-initdb.d/01-init.sql

# ---------------------------------------------------------------------------
# Backup & Restore
# ---------------------------------------------------------------------------
.PHONY: backup
backup: ## Create database backup
	@echo "$(BLUE)Creating database backup...$(RESET)"
	@mkdir -p backups
	@docker compose -f $(COMPOSE_FILE) -f $(COMPOSE_OVERRIDE) exec postgres pg_dump -U postgres -d microservices -F c -f /tmp/backup-$$(date +%Y%m%d-%H%M%S).dump
	@echo "$(GREEN)Backup created!$(RESET)"

.PHONY: restore
restore: ## Restore database from backup
	@echo "$(RED)Restoring database from backup...$(RESET)"
	@echo "$(YELLOW)Usage: make restore FILE=backups/backup-YYYYMMDD-HHMMSS.dump$(RESET)"
	@if [ -z "$(FILE)" ]; then \
		echo "$(RED)Error: FILE parameter required$(RESET)"; \
		exit 1; \
	fi
	@docker compose -f $(COMPOSE_FILE) -f $(COMPOSE_OVERRIDE) exec postgres pg_restore -U postgres -d microservices --clean -F c $(FILE)
	@echo "$(GREEN)Database restored!$(RESET)"

# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------
.PHONY: clean
clean: ## Remove all containers, networks, and images
	@echo "$(RED)Cleaning up containers and images...$(RESET)"
	@docker compose -f $(COMPOSE_FILE) -f $(COMPOSE_OVERRIDE) down --rmi local --remove-orphans
	@docker compose -f $(COMPOSE_PROD) down --rmi local --remove-orphans 2>/dev/null || true
	@docker compose -f $(COMPOSE_MONITORING) down --remove-orphans 2>/dev/null || true
	@echo "$(GREEN)Cleanup complete!$(RESET)"

.PHONY: clean-all
clean-all: ## Full cleanup including data volumes
	@echo "$(RED)WARNING: This will remove all data!$(RESET)"
	@read -p "Are you sure? [y/N] " confirm && [ $$confirm = y ] || exit 1
	@docker compose -f $(COMPOSE_FILE) -f $(COMPOSE_OVERRIDE) down -v --rmi all --remove-orphans
	@docker system prune -f
	@rm -rf data/ logs/ backups/
	@echo "$(GREEN)Full cleanup complete!$(RESET)"

# ---------------------------------------------------------------------------
# Health & Status
# ---------------------------------------------------------------------------
.PHONY: status
status: ## Show running containers status
	@echo "$(BLUE)Container Status:$(RESET)"
	@docker compose -f $(COMPOSE_FILE) -f $(COMPOSE_OVERRIDE) ps

.PHONY: health
health: ## Check health of all services
	@echo "$(BLUE)Checking service health...$(RESET)"
	@echo ""
	@echo "$(GREEN)Nginx:$(RESET)"
	@curl -s http://localhost:8080/health | python3 -m json.tool 2>/dev/null || echo "Nginx health check failed"
	@echo ""
	@echo "$(GREEN)API:$(RESET)"
	@curl -s http://localhost:5000/health | python3 -m json.tool 2>/dev/null || echo "API health check failed"
	@echo ""
	@echo "$(GREEN)Worker:$(RESET)"
	@curl -s http://localhost:5001/health | python3 -m json.tool 2>/dev/null || echo "Worker health check failed"

.PHONY: ps
ps: ## List running containers
	@docker compose -f $(COMPOSE_FILE) -f $(COMPOSE_OVERRIDE) ps

.PHONY: top
top: ## Show resource usage
	@docker compose -f $(COMPOSE_FILE) -f $(COMPOSE_OVERRIDE) top

.PHONY: stats
stats: ## Show container statistics
	@docker stats --no-stream --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}\t{{.BlockIO}}\t{{.PIDs}}"

# ---------------------------------------------------------------------------
# Task Queue Operations
# ---------------------------------------------------------------------------
.PHONY: queue-status
queue-status: ## Show Celery queue status
	@docker compose -f $(COMPOSE_FILE) -f $(COMPOSE_OVERRIDE) exec worker celery -A src.worker inspect active --timeout 10
	@echo ""
	@docker compose -f $(COMPOSE_FILE) -f $(COMPOSE_OVERRIDE) exec worker celery -A src.worker inspect scheduled --timeout 10
	@echo ""
	@docker compose -f $(COMPOSE_FILE) -f $(COMPOSE_OVERRIDE) exec worker celery -A src.worker inspect reserved --timeout 10

.PHONY: queue-purge
queue-purge: ## Purge all Celery queues
	@echo "$(RED)Purging all queues...$(RESET)"
	@docker compose -f $(COMPOSE_FILE) -f $(COMPOSE_OVERRIDE) exec worker celery -A src.worker purge -f

.PHONY: queue-report
queue-report: ## Generate queue status report
	@echo "$(BLUE)Queue Status Report$(RESET)"
	@echo "==================="
	@echo ""
	@docker compose -f $(COMPOSE_FILE) -f $(COMPOSE_OVERRIDE) exec worker celery -A src.worker inspect stats --timeout 10 2>/dev/null || echo "Worker not responding"

# ---------------------------------------------------------------------------
# Release / Deployment
# ---------------------------------------------------------------------------
.PHONY: version
version: ## Display version information
	@echo "$(BLUE)Microservices Orchestrator$(RESET)"
	@echo "Version: 1.0.0"
	@echo "Docker: $$(docker --version)"
	@echo "Compose: $$(docker compose version)"

.PHONY: validate
validate: ## Validate all configuration files
	@echo "$(BLUE)Validating configurations...$(RESET)"
	@echo "Development config..."
	@docker compose -f $(COMPOSE_FILE) -f $(COMPOSE_OVERRIDE) config > /dev/null && echo "$(GREEN)OK$(RESET)" || echo "$(RED)FAILED$(RESET)"
	@echo "Production config..."
	@docker compose -f $(COMPOSE_FILE) -f $(COMPOSE_PROD) config > /dev/null && echo "$(GREEN)OK$(RESET)" || echo "$(RED)FAILED$(RESET)"
	@echo "Monitoring config..."
	@docker compose -f $(COMPOSE_MONITORING) config > /dev/null && echo "$(GREEN)OK$(RESET)" || echo "$(RED)FAILED$(RESET)"
