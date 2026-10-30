# Triển khai

Có 3 cách. Nếu không chắc nên chọn cách nào, hãy dùng **Docker**.

| Cách | Hợp với |
|---|---|
| [Docker](#docker-trên-máy-hoặc-vps) | Máy cá nhân, VPS. Dễ nhất |
| [PM2 không dùng Docker](#vps-với-pm2-không-docker) | VPS đã có sẵn Python và PM2 |
| [Railway hoặc nền tảng dùng Procfile](#railway--paas) | Không muốn tự quản lý server |

> Dù chọn cách nào, đây là API **cho riêng bạn**. Mở công khai cho người khác lấy dữ liệu cần thoả thuận với tác giả vnstock, xem [vnstock-account.md](vnstock-account.md#giấy-phép-vnstock-tóm-tắt-cho-người-dùng-project-này).

## Docker trên máy hoặc VPS

Yêu cầu: Docker Engine kèm Compose v2.24 trở lên. Trên VPS Ubuntu, cài nhanh bằng:

```bash
curl -fsSL https://get.docker.com | sh
```

Sau đó:

```bash
git clone https://github.com/tran-minh-khoi/viet-nam-stock.git
cd viet-nam-stock
cp .env.example .env     # sửa nếu cần
docker compose up -d
```

- Cập nhật: `git pull && docker compose up -d --build`
- Xem log: `docker compose logs -f`
- Container tự khởi động lại khi server reboot (`restart: unless-stopped`) và có healthcheck tại `/health`.

### Chỉ cho máy của bạn truy cập

Mặc định cổng 8000 mở cho mọi máy nhìn thấy server của bạn. Trên VPS, nếu chỉ dùng trên chính server đó hoặc qua reverse proxy, hãy giới hạn chỉ cho localhost truy cập. Trong `docker-compose.yml`:

```yaml
    ports:
      - "127.0.0.1:${PORT:-8000}:8000"
```

### Thêm Redis để cache không mất khi restart (tuỳ chọn)

Thêm vào `docker-compose.yml`:

```yaml
  redis:
    image: redis:7-alpine
    restart: unless-stopped
```

Trong `.env`, điền `REDIS_URL=redis://redis:6379/0`, rồi chạy `docker compose up -d`.

### Tên miền và HTTPS

Đặt [Caddy](https://caddyserver.com) phía trước. Caddy tự lấy chứng chỉ HTTPS. Ví dụ `Caddyfile`:

```
stock.example.com {
    reverse_proxy 127.0.0.1:8000
}
```

Nên bật xác thực (ví dụ `basic_auth` của Caddy) để chỉ bạn dùng được.

## VPS với PM2 (không Docker)

Yêu cầu: Python 3.10 trở lên, Node.js và PM2 (`npm install -g pm2`).

```bash
git clone https://github.com/tran-minh-khoi/viet-nam-stock.git
cd viet-nam-stock
cp .env.example .env
bash deploy.sh
```

`deploy.sh` tạo virtualenv, cài thư viện (kể cả vnstock từ index của vnstocks), rồi chạy hoặc khởi động lại app dưới PM2 qua `start.sh`. Mỗi lần cập nhật: `git pull && bash deploy.sh`.

```bash
pm2 status
pm2 logs viet-nam-stock
```

Thông tin đăng nhập vnstock lưu ở `~/.vnstock` của user chạy PM2.

## Railway / PaaS

Repo có sẵn `Procfile` và `runtime.txt`. Kết nối repo GitHub với Railway hoặc nền tảng tương tự là nền tảng tự build. Thêm biến môi trường `VNSTOCK_API_KEY` trong phần cài đặt nếu có.

Lưu ý: nhiều nền tảng PaaS xoá ổ đĩa mỗi lần deploy, nên vnstock có thể coi mỗi lần deploy là một thiết bị mới. Nếu nền tảng hỗ trợ ổ đĩa lâu dài (volume), hãy gắn volume và đặt `VNSTOCK_HOME` trỏ vào đó.

## Chạy trực tiếp bằng Python (cho người phát triển)

```bash
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt
python api.py                     # http://localhost:8000/docs
pytest                            # chạy test
```
