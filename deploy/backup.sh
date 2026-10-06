#!/bin/sh
# Nightly pg_dump of the Corp Library database.
# Runs inside the `backup` container; dumps land in BACKUP_DIR on the host.
set -eu

: "${BACKUP_HOUR:=1}"
: "${BACKUP_KEEP_DAYS:=14}"

echo "Backup service started: daily at ${BACKUP_HOUR}:00, keeping ${BACKUP_KEEP_DAYS} days."

while true; do
    now=$(date +%s)
    next=$(date -d "today ${BACKUP_HOUR}:00" +%s)
    [ "$next" -le "$now" ] && next=$(date -d "tomorrow ${BACKUP_HOUR}:00" +%s)
    sleep $((next - now))

    file="/backups/corplib-$(date +%Y%m%d-%H%M).dump"
    if pg_dump --format=custom --file="$file.tmp"; then
        mv "$file.tmp" "$file"
        echo "$(date -Iseconds) Backup written: $file ($(du -h "$file" | cut -f1))"
        find /backups -name 'corplib-*.dump' -mtime "+${BACKUP_KEEP_DAYS}" -delete
    else
        rm -f "$file.tmp"
        echo "$(date -Iseconds) Backup FAILED" >&2
    fi
done
