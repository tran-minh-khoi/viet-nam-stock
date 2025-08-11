#!/bin/bash

# Dừng nếu có lỗi
set -e
source .env

# Ghi log để debug (nếu cần)
echo "🔧 Starting gunicorn with APP_MODULE=${APP_MODULE}, APP_PORT=${APP_PORT}"

# Kiểm tra biến môi trường bắt buộc
if [ -z "$APP_MODULE" ] || [ -z "$APP_PORT" ]; then
  echo "❌ APP_MODULE hoặc APP_PORT chưa được thiết lập."
  exit 1
fi

# Chạy gunicorn từ môi trường ảo
./"$VENV_DIR"/bin/gunicorn -k uvicorn.workers.UvicornWorker "$APP_MODULE" --workers 4 --bind 0.0.0.0:$APP_PORT
