#!/bin/bash
# =============================================================================
# Backup & Restore Script - Microservices Orchestrator
# =============================================================================
# Automated backup and restore for PostgreSQL database with S3 upload support.
# Supports full database dumps, selective table backups, and scheduled backups.
# =============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
BACKUP_DIR="${PROJECT_DIR}/backups"
RETENTION_DAYS=${BACKUP_RETENTION_DAYS:-7}
S3_BUCKET=${S3_BACKUP_BUCKET:-""}
S3_PREFIX=${S3_BACKUP_PREFIX:-"backups/"}
DATE_FORMAT="%Y%m%d-%H%M%S"
TIMESTAMP=$(date +$DATE_FORMAT)

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_step() { echo -e "${CYAN}[STEP]${NC} $1"; }

# ---------------------------------------------------------------------------
# Usage
# ---------------------------------------------------------------------------

usage() {
    cat << EOF
Usage: $(basename "$0") [COMMAND] [OPTIONS]

Database backup and restore operations for the microservices orchestrator.

Commands:
    backup              Create a full database backup
    backup-tables       Backup specific tables (comma-separated)
    restore             Restore from a backup file
    list                List available backups
    cleanup             Remove old backups (respects retention policy)
    verify              Verify a backup file integrity
    schedule            Setup scheduled backup (cron)
    upload-s3           Upload backup to S3
    download-s3         Download backup from S3

Options:
    -f, --file FILE     Specify backup file path
    -t, --tables TBL    Comma-separated table names
    -d, --days N        Retention period in days (default: 7)
    -c, --container     Docker container name (default: ms-postgres)
    -h, --help          Show this help message

Examples:
    $(basename "$0") backup
    $(basename "$0") backup-tables -t tasks,users
    $(basename "$0") restore -f backups/backup-20240101-120000.sql.gz
    $(basename "$0") list
    $(basename "$0") cleanup -d 30
    $(basename "$0") verify -f backups/latest.dump
    $(basename "$0") upload-s3 -f backups/backup-20240101-120000.dump

EOF
}

# ---------------------------------------------------------------------------
# Configuration Helpers
# ---------------------------------------------------------------------------

get_db_config() {
    # Read from environment or .env file
    if [ -f "$PROJECT_DIR/.env" ]; then
        DB_USER=$(grep "^POSTGRES_USER=" "$PROJECT_DIR/.env" | cut -d '=' -f2)
        DB_PASSWORD=$(grep "^POSTGRES_PASSWORD=" "$PROJECT_DIR/.env" | cut -d '=' -f2)
        DB_NAME=$(grep "^POSTGRES_DB=" "$PROJECT_DIR/.env" | cut -d '=' -f2)
    fi
    
    DB_USER=${DB_USER:-postgres}
    DB_PASSWORD=${DB_PASSWORD:-postgres}
    DB_NAME=${DB_NAME:-microservices}
    DB_HOST=${DB_HOST:-postgres}
    DB_PORT=${DB_PORT:-5432}
    CONTAINER_NAME=${CONTAINER_NAME:-ms-postgres}
    
    export PGPASSWORD="$DB_PASSWORD"
}

ensure_backup_dir() {
    if [ ! -d "$BACKUP_DIR" ]; then
        mkdir -p "$BACKUP_DIR"
        log_info "Created backup directory: $BACKUP_DIR"
    fi
}

# ---------------------------------------------------------------------------
# Backup Commands
# ---------------------------------------------------------------------------

cmd_backup() {
    log_step "Creating full database backup..."
    get_db_config
    ensure_backup_dir
    
    local backup_file="${BACKUP_DIR}/backup-${TIMESTAMP}.dump"
    local compressed_file="${backup_file}.gz"
    
    log_info "Backup target: $compressed_file"
    log_info "Database: $DB_NAME on $DB_HOST"
    
    # Check if database container is running
    if ! docker ps | grep -q "$CONTAINER_NAME"; then
        log_error "Database container '$CONTAINER_NAME' is not running!"
        exit 1
    fi
    
    # Create backup using pg_dump inside the container
    log_info "Dumping database (this may take a while)..."
    docker exec "$CONTAINER_NAME" pg_dump \
        -U "$DB_USER" \
        -d "$DB_NAME" \
        -F c \
        -v \
        -f "/tmp/backup-${TIMESTAMP}.dump" 2>&1 | while read line; do
            log_info "$line"
        done
    
    # Copy from container and compress
    docker cp "${CONTAINER_NAME}:/tmp/backup-${TIMESTAMP}.dump" "$backup_file"
    docker exec "$CONTAINER_NAME" rm "/tmp/backup-${TIMESTAMP}.dump"
    
    # Compress
    log_info "Compressing backup..."
    gzip -f "$backup_file"
    
    local file_size=$(du -h "$compressed_file" | cut -f1)
    log_success "Backup completed: $compressed_file ($file_size)"
    
    # Create 'latest' symlink
    ln -sf "$compressed_file" "${BACKUP_DIR}/latest.dump.gz"
    
    # Cleanup old backups
    cmd_cleanup
}

cmd_backup_tables() {
    local tables="${1:-}"
    
    if [ -z "$tables" ]; then
        log_error "No tables specified. Use -t option."
        exit 1
    fi
    
    log_step "Backing up tables: $tables"
    get_db_config
    ensure_backup_dir
    
    IFS=',' read -ra TABLE_LIST <<< "$tables"
    local backup_file="${BACKUP_DIR}/tables-${TIMESTAMP}.sql.gz"
    
    # Build table flags
    local table_flags=""
    for table in "${TABLE_LIST[@]}"; do
        table_flags="$table_flags -t $table"
    done
    
    # Create backup
    docker exec "$CONTAINER_NAME" pg_dump \
        -U "$DB_USER" \
        -d "$DB_NAME" \
        --data-only \
        $table_flags \
        | gzip > "$backup_file"
    
    local file_size=$(du -h "$backup_file" | cut -f1)
    log_success "Table backup completed: $backup_file ($file_size)"
}

cmd_restore() {
    local file="${1:-}"
    
    if [ -z "$file" ]; then
        log_error "No backup file specified. Use -f option."
        exit 1
    fi
    
    if [ ! -f "$file" ]; then
        log_error "Backup file not found: $file"
        exit 1
    fi
    
    log_step "Restoring database from backup..."
    get_db_config
    
    log_warning "This will overwrite the current database!"
    read -p "Are you sure? [y/N] " confirm
    if [ "$confirm" != "y" ] && [ "$confirm" != "Y" ]; then
        log_info "Restore cancelled."
        exit 0
    fi
    
    log_info "Restoring from: $file"
    
    # Handle compressed files
    if [[ "$file" == *.gz ]]; then
        # Decompress and restore
        gunzip -c "$file" > "/tmp/restore-${TIMESTAMP}.dump"
        file="/tmp/restore-${TIMESTAMP}.dump"
        trap "rm -f /tmp/restore-${TIMESTAMP}.dump" EXIT
    fi
    
    # Copy to container
    docker cp "$file" "${CONTAINER_NAME}:/tmp/restore.dump"
    
    # Drop and recreate database
    log_info "Recreating database..."
    docker exec "$CONTAINER_NAME" dropdb -U "$DB_USER" --if-exists "$DB_NAME"
    docker exec "$CONTAINER_NAME" createdb -U "$DB_USER" "$DB_NAME"
    
    # Restore
    log_info "Restoring data..."
    docker exec "$CONTAINER_NAME" pg_restore \
        -U "$DB_USER" \
        -d "$DB_NAME" \
        -v \
        "/tmp/restore.dump" 2>&1 | while read line; do
            log_info "$line"
        done
    
    # Cleanup
    docker exec "$CONTAINER_NAME" rm "/tmp/restore.dump"
    
    log_success "Database restored successfully!"
}

cmd_list() {
    log_step "Available backups..."
    ensure_backup_dir
    
    if [ ! "$(ls -A "$BACKUP_DIR")" ]; then
        log_warning "No backups found in $BACKUP_DIR"
        return
    fi
    
    echo ""
    printf "%-40s %-12s %-20s\n" "FILE" "SIZE" "DATE"
    printf "%-40s %-12s %-20s\n" "----------------------------------------" "------------" "--------------------"
    
    for f in "$BACKUP_DIR"/*.{dump,dump.gz,sql,sql.gz} 2>/dev/null; do
        if [ -f "$f" ]; then
            local fname=$(basename "$f")
            local fsize=$(du -h "$f" | cut -f1)
            local fdate=$(stat -c %y "$f" 2>/dev/null || stat -f %Sm "$f" 2>/dev/null)
            printf "%-40s %-12s %-20s\n" "$fname" "$fsize" "${fdate:0:16}"
        fi
    done
    echo ""
}

cmd_cleanup() {
    local days="${1:-$RETENTION_DAYS}"
    
    log_step "Cleaning up backups older than $days days..."
    ensure_backup_dir
    
    local count=0
    while IFS= read -r file; do
        rm -f "$file"
        log_info "Removed: $(basename "$file")"
        ((count++)) || true
    done < <(find "$BACKUP_DIR" -name "backup-*.dump*" -type f -mtime +$days 2>/dev/null)
    
    if [ $count -eq 0 ]; then
        log_info "No old backups to clean up."
    else
        log_success "Cleaned up $count old backup(s)."
    fi
}

cmd_verify() {
    local file="${1:-}"
    
    if [ -z "$file" ]; then
        log_error "No backup file specified. Use -f option."
        exit 1
    fi
    
    log_step "Verifying backup: $file"
    
    if [ ! -f "$file" ]; then
        log_error "File not found: $file"
        exit 1
    fi
    
    # Check if file is readable
    if ! gzip -t "$file" 2>/dev/null; then
        log_warning "File is not gzip compressed or is corrupted"
        
        # Try as uncompressed
        if [[ "$file" == *.dump ]]; then
            log_info "Checking as uncompressed dump..."
            # This would need pg_restore to verify properly
            log_success "File exists and is readable (uncompressed dump)"
        fi
    else
        log_success "File is valid gzip compressed"
        
        # Show file info
        local uncompressed_size=$(gunzip -l "$file" 2>/dev/null | awk 'NR==2{print $2}')
        local compressed_size=$(du -h "$file" | cut -f1)
        log_info "Compressed size: $compressed_size"
        log_info "Uncompressed size: $(numfmt --to=iec $uncompressed_size 2>/dev/null || echo "${uncompressed_size} bytes")"
    fi
}

cmd_upload_s3() {
    local file="${1:-}"
    
    if [ -z "$S3_BUCKET" ]; then
        log_error "S3_BACKUP_BUCKET not configured. Set it in .env or environment."
        exit 1
    fi
    
    if [ -z "$file" ]; then
        log_error "No file specified. Use -f option."
        exit 1
    fi
    
    if ! command -v aws &> /dev/null; then
        log_error "AWS CLI not installed. Install it to use S3 features."
        exit 1
    fi
    
    log_step "Uploading to S3: s3://${S3_BUCKET}/${S3_PREFIX}$(basename "$file")"
    
    aws s3 cp "$file" "s3://${S3_BUCKET}/${S3_PREFIX}$(basename "$file")" \
        --storage-class STANDARD_IA
    
    log_success "Upload complete!"
}

cmd_download_s3() {
    local file="${1:-}"
    
    if [ -z "$S3_BUCKET" ]; then
        log_error "S3_BACKUP_BUCKET not configured."
        exit 1
    fi
    
    if ! command -v aws &> /dev/null; then
        log_error "AWS CLI not installed."
        exit 1
    fi
    
    log_step "Listing S3 backups..."
    aws s3 ls "s3://${S3_BUCKET}/${S3_PREFIX}" --recursive | sort
    
    if [ -n "$file" ]; then
        local filename=$(basename "$file")
        log_info "Downloading: $filename"
        ensure_backup_dir
        aws s3 cp "s3://${S3_BUCKET}/${S3_PREFIX}${filename}" "${BACKUP_DIR}/${filename}"
        log_success "Downloaded to: ${BACKUP_DIR}/${filename}"
    fi
}

cmd_schedule() {
    log_step "Setting up scheduled backups..."
    
    local schedule="${BACKUP_SCHEDULE:-0 2 * * *}"
    local cron_entry="$schedule cd $PROJECT_DIR && $SCRIPT_DIR/backup.sh backup >> $PROJECT_DIR/logs/backup.log 2>&1"
    
    # Check if already scheduled
    if crontab -l 2>/dev/null | grep -q "backup.sh backup"; then
        log_warning "Backup already scheduled. Updating..."
        crontab -l 2>/dev/null | grep -v "backup.sh" | crontab -
    fi
    
    # Add new entry
    (crontab -l 2>/dev/null; echo "$cron_entry") | crontab -
    
    log_success "Scheduled backup: $schedule"
    log_info "Current crontab:"
    crontab -l | grep "backup" || true
}

# ---------------------------------------------------------------------------
# Argument Parsing
# ---------------------------------------------------------------------------

main() {
    local command=""
    local file=""
    local tables=""
    local days=""
    
    # Parse command
    if [ $# -eq 0 ]; then
        usage
        exit 1
    fi
    
    command="$1"
    shift
    
    # Parse options
    while [ $# -gt 0 ]; do
        case "$1" in
            -f|--file)
                file="$2"
                shift 2
                ;;
            -t|--tables)
                tables="$2"
                shift 2
                ;;
            -d|--days)
                days="$2"
                shift 2
                ;;
            -c|--container)
                CONTAINER_NAME="$2"
                shift 2
                ;;
            -h|--help)
                usage
                exit 0
                ;;
            *)
                log_error "Unknown option: $1"
                usage
                exit 1
                ;;
        esac
    done
    
    # Execute command
    case "$command" in
        backup)
            cmd_backup
            ;;
        backup-tables)
            cmd_backup_tables "$tables"
            ;;
        restore)
            cmd_restore "$file"
            ;;
        list)
            cmd_list
            ;;
        cleanup)
            cmd_cleanup "${days:-$RETENTION_DAYS}"
            ;;
        verify)
            cmd_verify "$file"
            ;;
        upload-s3)
            cmd_upload_s3 "$file"
            ;;
        download-s3)
            cmd_download_s3 "$file"
            ;;
        schedule)
            cmd_schedule
            ;;
        *)
            log_error "Unknown command: $command"
            usage
            exit 1
            ;;
    esac
}

main "$@"
