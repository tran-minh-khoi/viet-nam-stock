#!/bin/bash

# Stop script nếu có lỗi
set -e
set -a
source .env
set +a

VENV_DIR=${VENV_DIR:-venv}

echo "🚀 Kiểm tra và tạo môi trường ảo nếu chưa có..."
if [ ! -f "$VENV_DIR/bin/activate" ]; then
  echo "🔧 Tạo virtual environment..."
  python3 -m venv "$VENV_DIR"
fi

# echo "🚀 Kiểm tra môi trường ảo..."
# if [ ! -d "$VENV_DIR" ]; then
#   echo "🔧 Đang tạo môi trường ảo bằng python3 -m venv..."
#   python3 -m venv "$VENV_DIR"
# else
#   echo "✅ Môi trường ảo đã tồn tại."
# fi

# echo "🔒 [2/5] Tạo môi trường ảo nếu chưa có..."
# if [ ! -d "$VENV_DIR" ]; then
#   virtualenv $VENV_DIR
# fi

echo "📦 [3/5] Cài đặt dependencies..."
./$VENV_DIR/bin/pip install -r requirements.txt

pm2 restart viet-nam-stock --update-env || pm2 start ecosystem.config.js
pm2 save

echo "✅ [5/5] Deploy hoàn tất!"
pm2 status
