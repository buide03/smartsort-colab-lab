#!/usr/bin/env bash
# Consistent backup: briefly stop the app so background jobs cannot write files.
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
docker compose --env-file .env config --quiet
backup_root="${SMARTSORT_BACKUP_DIR:-/opt/smartsort/backups}"
mkdir -p -- "$backup_root"
chmod 700 "$backup_root"
backup_root="$(cd -- "$backup_root" && pwd -P)"
backup_name="smartsort-$(date -u +%Y%m%dT%H%M%SZ)-$$.tar.gz"
echo 'Stop only after students finish validation/test. Interrupted jobs must be retried.'
docker compose --env-file .env stop smartsort
trap 'docker compose --env-file .env start smartsort' EXIT
docker compose --env-file .env run --rm --no-deps -T \
  -v "$backup_root:/backup" --entrypoint tar smartsort \
  -czf "/backup/$backup_name" -C /data .
chmod 600 "$backup_root/$backup_name"
echo "Backup: $backup_root/$backup_name"
