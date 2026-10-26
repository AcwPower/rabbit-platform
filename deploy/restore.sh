#!/usr/bin/env bash
set -euo pipefail
backup_dir=${1:?Provide backup directory}
if [ "${2:-}" != '--confirm-replace-rabbit-database' ]; then
  echo 'Restoring replaces ONLY rabbit_platform data. Supply --confirm-replace-rabbit-database after reviewing the backup.' >&2
  exit 2
fi
case "$backup_dir" in /var/backups/rabbit/*) ;; *) echo 'Invalid backup location' >&2; exit 2;; esac
sha256sum -c "$backup_dir/SHA256SUMS"
systemctl stop rabbit-api rabbit-cleanup.timer
gzip -dc "$backup_dir/database.sql.gz" | mysql rabbit_platform
release=$(cat "$backup_dir/release.txt")
test -d "$release/backend"
ln -sfn "$release" /opt/rabbit-platform/current
systemctl start rabbit-api rabbit-cleanup.timer
curl --fail --silent http://127.0.0.1:8101/api/health
