#!/usr/bin/env bash
# Run as root on 43.161.232.10 with an archive produced by package.py.
set -euo pipefail
umask 022
archive=${1:?Provide a release tar.gz}
release_id=${2:?Provide a release ID}
[[ "$release_id" =~ ^[A-Za-z0-9._-]+$ ]] || exit 2
release=/opt/rabbit-platform/releases/$release_id
test ! -e "$release"
install -d -m 755 "$release"
tar --no-same-owner -xzf "$archive" -C "$release"
python3 "$release/deploy/provision.py"
python3 -m venv "$release/venv"
"$release/venv/bin/pip" install --disable-pip-version-check --index-url https://pypi.org/simple -r "$release/backend/requirements.txt"
if [ -L /opt/rabbit-platform/current ]; then
  /opt/rabbit-platform/current/deploy/backup.sh
  readlink -f /opt/rabbit-platform/current > /opt/rabbit-platform/previous-release
fi
install -d -m 700 /etc/rabbit/tls
if [ ! -f /etc/rabbit/tls/backend.key ]; then
  openssl req -x509 -newkey rsa:3072 -sha256 -days 3650 -nodes \
    -keyout /etc/rabbit/tls/backend.key -out /etc/rabbit/tls/backend.crt \
    -subj '/CN=rabbit-backend.internal' \
    -addext 'subjectAltName=DNS:rabbit-backend.internal,IP:10.5.0.5' \
    -addext 'extendedKeyUsage=serverAuth' 2>/dev/null
  chmod 600 /etc/rabbit/tls/backend.key
  chmod 644 /etc/rabbit/tls/backend.crt
fi
set -a
. /etc/rabbit/app.env
set +a
cd "$release/backend"
"$release/venv/bin/python" -m app.ocr_engine --prepare
"$release/venv/bin/alembic" upgrade head
"$release/venv/bin/python" -m app.admin_cli bootstrap
ln -sfn "$release" /opt/rabbit-platform/current
install -m 644 "$release/deploy/"rabbit-*.service /etc/systemd/system/
install -m 644 "$release/deploy/"rabbit-*.timer /etc/systemd/system/
install -m 644 "$release/deploy/nginx-app.conf" /etc/nginx/sites-available/rabbit-platform
ln -sfn /etc/nginx/sites-available/rabbit-platform /etc/nginx/sites-enabled/rabbit-platform
nginx -t
systemctl daemon-reload
systemctl enable rabbit-api rabbit-ocr rabbit-cleanup.timer rabbit-backup.timer rabbit-health.timer
systemctl restart rabbit-api rabbit-ocr
systemctl start rabbit-cleanup.timer rabbit-backup.timer rabbit-health.timer
systemctl reload nginx
for n in {1..15}; do
  if curl --silent --fail http://127.0.0.1:8101/api/health; then exit 0; fi
  sleep 1
done
echo 'Health check failed. Inspect journalctl -u rabbit-api and previous-release.' >&2
exit 1
