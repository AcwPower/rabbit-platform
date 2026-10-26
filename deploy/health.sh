#!/usr/bin/env bash
set -euo pipefail
systemctl is-active --quiet rabbit-api rabbit-ocr mysql nginx
curl --silent --show-error --fail --max-time 10 http://127.0.0.1:8101/api/health >/dev/null
curl --silent --show-error --fail --max-time 10 --cacert /etc/rabbit/tls/backend.crt --resolve rabbit-backend.internal:443:127.0.0.1 https://rabbit-backend.internal/party/ >/dev/null
printf 'Rabbit API, OCR, MySQL and HTTPS routing healthy\n'
