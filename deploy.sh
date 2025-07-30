#!/bin/bash

# Stop script nếu có lỗi
set -e
set -a
source .env
set +a

# Cấu hình biến
VENV_DIR=$VENV_DIR
APP_MODULE=$APP_MODULE 
APP_PORT=$APP_PORT

echo "🚀 [1/5] Kiểm tra virtualenv..."
if ! command -v virtualenv &> /dev/null; then
  echo "🔧 Cài đặt virtualenv..."
  pip install virtualenv
fi

echo "🔒 [2/5] Tạo môi trường ảo nếu chưa có..."
if [ ! -d "$VENV_DIR" ]; then
  virtualenv $VENV_DIR
fi

echo "📦 [3/5] Cài đặt dependencies..."
./$VENV_DIR/bin/pip install -r requirements.txt

echo "🛠️ [4/5] Khởi động lại ứng dụng bằng PM2..."
pm2 delete citizen-api || true
pm2 start ecosystem.config.js
pm2 save

echo "✅ [5/5] Deploy hoàn tất!"
pm2 status
