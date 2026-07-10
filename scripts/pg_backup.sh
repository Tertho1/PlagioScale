#!/usr/bin/env bash
# PlagioScale PostgreSQL backup script
# Usage: ./scripts/pg_backup.sh [output_dir]
set -euo pipefail

OUTPUT_DIR="${1:-./backups}"
mkdir -p "$OUTPUT_DIR"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
DB_HOST="${PGHOST:-postgres}"
DB_PORT="${PGPORT:-5432}"
DB_NAME="${PGDATABASE:-plagioscale}"
DB_USER="${PGUSER:-plagioscale}"
BACKUP_FILE="${OUTPUT_DIR}/plagioscale_${TIMESTAMP}.sql.gz"

echo "Backing up $DB_NAME@$DB_HOST:$DB_PORT → $BACKUP_FILE"
PGPASSWORD="${PGPASSWORD:-plagioscale}" pg_dump \
    -h "$DB_HOST" \
    -p "$DB_PORT" \
    -U "$DB_USER" \
    -d "$DB_NAME" \
    --no-owner \
    --no-acl \
    | gzip > "$BACKUP_FILE"

echo "Done: $(du -h "$BACKUP_FILE" | cut -f1)"
