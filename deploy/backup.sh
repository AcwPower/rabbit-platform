#!/usr/bin/env bash
set -euo pipefail
umask 077
backup_dir=/var/backups/rabbit/$(date -u +%Y%m%dT%H%M%SZ)
mkdir -p "$backup_dir"
mysqldump --single-transaction --routines --triggers --no-tablespaces rabbit_platform | gzip > "$backup_dir/database.sql.gz"
tar -czf "$backup_dir/config.tgz" /etc/rabbit /etc/nginx/sites-available/rabbit-platform /etc/systemd/system/rabbit-*.service /etc/systemd/system/rabbit-*.timer
readlink -f /opt/rabbit-platform/current > "$backup_dir/release.txt"
sha256sum "$backup_dir/database.sql.gz" "$backup_dir/config.tgz" > "$backup_dir/SHA256SUMS"
printf '%s\n' "$backup_dir"
