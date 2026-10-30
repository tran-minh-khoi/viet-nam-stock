#!/bin/bash
# Started by PM2 (see ecosystem.config.js). Docker users don't need this file.
set -e
set -a; [ -f .env ] && source .env; set +a
exec ./"${VENV_DIR:-venv}"/bin/uvicorn api:app --host "${API_HOST:-0.0.0.0}" --port "${API_PORT:-8000}" --proxy-headers
