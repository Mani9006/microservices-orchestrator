#!/bin/bash
# =============================================================================
# Setup Script - Microservices Orchestrator
# =============================================================================
# This script initializes the project environment for first-time setup.
# It creates directories, sets permissions, and validates prerequisites.
# =============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
DATA_DIR="${PROJECT_DIR}/data"
LOGS_DIR="${PROJECT_DIR}/logs"
BACKUPS_DIR="${PROJECT_DIR}/backups"
CERTS_DIR="${PROJECT_DIR}/certs"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# ---------------------------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------------------------

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_step() {
    echo -e "${CYAN}[STEP]${NC} $1"
}

# ---------------------------------------------------------------------------
# Check Prerequisites
# ---------------------------------------------------------------------------

check_prerequisites() {
    log_step "Checking prerequisites..."
    
    local has_error=0
    
    # Check Docker
    if command -v docker &> /dev/null; then
        DOCKER_VERSION=$(docker --version | awk '{print $3}' | tr -d ',')
        log_success "Docker: ${DOCKER_VERSION}"
    else
        log_error "Docker is not installed or not in PATH"
        has_error=1
    fi
    
    # Check Docker Compose
    if command -v docker &> /dev/null && docker compose version &> /dev/null; then
        COMPOSE_VERSION=$(docker compose version --short)
        log_success "Docker Compose: ${COMPOSE_VERSION}"
    else
        log_error "Docker Compose (v2) is not installed"
        has_error=1
    fi
    
    # Check available memory
    if command -v free &> /dev/null; then
        AVAILABLE_MB=$(free -m | awk '/^Mem:/{print $7}')
        if [ "$AVAILABLE_MB" -lt 1024 ]; then
            log_warning "Available memory is low (${AVAILABLE_MB}MB). Recommended: 2048MB+"
        else
            log_success "Available memory: ${AVAILABLE_MB}MB"
        fi
    fi
    
    # Check disk space
    AVAILABLE_GB=$(df -BG "$PROJECT_DIR" | awk 'NR==2{print $4}' | tr -d 'G')
    if [ "$AVAILABLE_GB" -lt 5 ]; then
        log_warning "Low disk space (${AVAILABLE_GB}GB). Recommended: 10GB+"
    else
        log_success "Available disk: ${AVAILABLE_GB}GB"
    fi
    
    if [ $has_error -eq 1 ]; then
        log_error "Prerequisites check failed. Please install missing tools."
        exit 1
    fi
    
    log_success "All prerequisites met!"
}

# ---------------------------------------------------------------------------
# Create Directories
# ---------------------------------------------------------------------------

create_directories() {
    log_step "Creating project directories..."
    
    local dirs=(
        "$DATA_DIR/postgres"
        "$DATA_DIR/redis"
        "$LOGS_DIR"
        "$BACKUPS_DIR"
        "$CERTS_DIR"
    )
    
    for dir in "${dirs[@]}"; do
        if [ ! -d "$dir" ]; then
            mkdir -p "$dir"
            log_info "Created: $dir"
        else
            log_info "Exists:  $dir"
        fi
    done
    
    log_success "Directories ready!"
}

# ---------------------------------------------------------------------------
# Setup Environment File
# ---------------------------------------------------------------------------

setup_environment() {
    log_step "Setting up environment configuration..."
    
    cd "$PROJECT_DIR"
    
    if [ ! -f ".env" ]; then
        if [ -f ".env.example" ]; then
            cp .env.example .env
            log_success "Created .env from .env.example"
            log_warning "Please review and update .env with your actual values!"
        else
            log_error ".env.example not found!"
            exit 1
        fi
    else
        log_warning ".env already exists. Skipping creation."
    fi
    
    # Check for default secrets
    if grep -q "change-me" .env 2>/dev/null; then
        log_warning "Default secrets detected in .env. Please update them!"
    fi
}

# ---------------------------------------------------------------------------
# Generate SSL Certificates (Development)
# ---------------------------------------------------------------------------

generate_ssl_certs() {
    log_step "Checking SSL certificates..."
    
    if [ ! -f "$CERTS_DIR/server.crt" ] || [ ! -f "$CERTS_DIR/server.key" ]; then
        if command -v openssl &> /dev/null; then
            log_info "Generating self-signed SSL certificates..."
            openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
                -keyout "$CERTS_DIR/server.key" \
                -out "$CERTS_DIR/server.crt" \
                -subj "/C=US/ST=State/L=City/O=Organization/CN=localhost" \
                2>/dev/null
            chmod 600 "$CERTS_DIR/server.key"
            log_success "SSL certificates generated"
        else
            log_warning "OpenSSL not found. SSL certificates not generated."
        fi
    else
        log_info "SSL certificates already exist"
    fi
}

# ---------------------------------------------------------------------------
# Set Permissions
# ---------------------------------------------------------------------------

set_permissions() {
    log_step "Setting permissions..."
    
    # Ensure data directories are writable
    chmod -R 755 "$DATA_DIR" 2>/dev/null || true
    chmod -R 755 "$LOGS_DIR" 2>/dev/null || true
    chmod -R 755 "$BACKUPS_DIR" 2>/dev/null || true
    
    log_success "Permissions set"
}

# ---------------------------------------------------------------------------
# Pull Images
# ---------------------------------------------------------------------------

pull_images() {
    log_step "Pulling Docker images..."
    
    cd "$PROJECT_DIR"
    docker compose -f docker-compose.yml pull
    
    log_success "Images pulled"
}

# ---------------------------------------------------------------------------
# Validate Configuration
# ---------------------------------------------------------------------------

validate_config() {
    log_step "Validating Docker Compose configuration..."
    
    cd "$PROJECT_DIR"
    
    if docker compose -f docker-compose.yml -f docker-compose.override.yml config > /dev/null 2>&1; then
        log_success "Development configuration is valid"
    else
        log_error "Development configuration validation failed"
        exit 1
    fi
    
    log_success "Configuration validated"
}

# ---------------------------------------------------------------------------
# Print Summary
# ---------------------------------------------------------------------------

print_summary() {
    echo ""
    echo "=========================================="
    echo -e "${GREEN}  Setup Complete!${NC}"
    echo "=========================================="
    echo ""
    echo -e "${CYAN}Project Directory:${NC}  $PROJECT_DIR"
    echo -e "${CYAN}Data Directory:${NC}     $DATA_DIR"
    echo -e "${CYAN}Logs Directory:${NC}     $LOGS_DIR"
    echo ""
    echo -e "${YELLOW}Next Steps:${NC}"
    echo "  1. Review and update the .env file with your configuration"
    echo "  2. Run: make build     (Build all Docker images)"
    echo "  3. Run: make up        (Start all services)"
    echo "  4. Run: make health    (Check service health)"
    echo ""
    echo -e "${YELLOW}Useful Commands:${NC}"
    echo "  make help              Show all available commands"
    echo "  make build             Build all services"
    echo "  make up                Start all services"
    echo "  make down              Stop all services"
    echo "  make logs              View service logs"
    echo "  make test              Run all tests"
    echo "  make status            Check container status"
    echo ""
    echo -e "${YELLOW}Development URLs:${NC}"
    echo "  API:             http://localhost:5000"
    echo "  API (via Nginx): http://localhost"
    echo "  Worker Health:   http://localhost:5001/health"
    echo "  Nginx Health:    http://localhost:8080/health"
    echo ""
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

main() {
    echo -e "${BLUE}"
    echo "  __  __ _                                    _           _"
    echo " |  \/  (_) __ _ _ __ ___   ___ _ __ ___  ___| | ___  ___| |_ ___"
    echo " | |\\/| | |/ _\\\| '_ \\`_ \\ / _ \\ '__/ __|/ _ \\ |/ _ \\/ __| __/ _ \\"
    echo " | |  | | | (_| | | | | | |  __/ |  \\__ \\  __/ |  __/ (__| ||  __/"
    echo " |_|  |_|_|\\__, |_| |_| |_|\\___|_|  |___/\\___|_|\\___|\\___|\\__\\___|"
    echo "           |___/                                                   "
    echo -e "${NC}"
    echo -e "${GREEN}                    Setup Script${NC}"
    echo ""
    
    check_prerequisites
    create_directories
    setup_environment
    generate_ssl_certs
    set_permissions
    pull_images
    validate_config
    print_summary
}

# Run main if executed directly
if [ "${BASH_SOURCE[0]}" == "${0}" ]; then
    main "$@"
fi
