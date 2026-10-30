#!/bin/bash
# Deploy/redeploy on a VPS with PM2 (no Docker). Usage: bash deploy.sh
set -e
VENV_DIR=${VENV_DIR:-venv}

[ -f "$VENV_DIR/bin/activate" ] || { echo "🔧 Creating virtualenv..."; python3 -m venv "$VENV_DIR"; }

echo "📦 Installing dependencies..."
./"$VENV_DIR"/bin/pip install -q -r requirements.txt

pm2 restart viet-nam-stock --update-env || pm2 start ecosystem.config.js
pm2 save
echo "✅ Deploy done"
pm2 status
