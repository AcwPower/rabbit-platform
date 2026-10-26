#!/usr/bin/env bash
# Code-only rollback is permitted only when the target's migration head matches the database.
set -euo pipefail
rollback_release=${1:?Provide an existing absolute release path}
case "$rollback_release" in /opt/rabbit-platform/releases/*) ;; *) exit 2;; esac
test -x "$rollback_release/venv/bin/python"
set -a
. /etc/rabbit/app.env
set +a
previous=$(readlink -f /opt/rabbit-platform/current)
cd /opt/rabbit-platform/current/backend
current_revision=$(/opt/rabbit-platform/current/venv/bin/alembic current | cut -d' ' -f1)
cd "$rollback_release/backend"
target_revision=$("$rollback_release/venv/bin/alembic" heads | cut -d' ' -f1)
if [ "$current_revision" != "$target_revision" ]; then
  echo 'Database revision differs. Review schema compatibility and use a verified pre-release backup if required.' >&2
  exit 2
fi
ln -sfn "$rollback_release" /opt/rabbit-platform/current
systemctl restart rabbit-api rabbit-ocr
for n in {1..15}; do
  if /opt/rabbit-platform/current/deploy/health.sh; then
    echo "Code switched to $rollback_release"
    exit 0
  fi
  sleep 1
done
ln -sfn "$previous" /opt/rabbit-platform/current
systemctl restart rabbit-api rabbit-ocr
echo 'Target health check failed; previous code restored.' >&2
exit 1
