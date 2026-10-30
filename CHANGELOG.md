# Changelog

Định dạng theo [Keep a Changelog](https://keepachangelog.com/vi/1.1.0/), đánh số phiên bản theo [SemVer](https://semver.org/lang/vi/).

## [3.0.0] - 2026-10-30

### Thay đổi lớn
- Chuyển sang **vnstock 5.2.1**. Bản 3.x đã bị gỡ khỏi PyPI và không cài được nữa. vnstock 5 cài từ index riêng của vnstocks, đã khai báo trong `requirements.txt`.
- Mặc định chạy với tài khoản Khách của vnstock (10 lượt/phút). Điền `VNSTOCK_API_KEY` để có hạn mức cao hơn.
- `exchange` lấy theo sàn thật của mã (HOSE/HNX/UPCOM), không còn luôn là `HOSE`.
- Bỏ `gunicorn`. Server chạy bằng `uvicorn` với 1 worker.

### Thêm
- Docker: `Dockerfile`, `docker-compose.yml`, healthcheck, chạy bằng user thường, volume giữ thông tin đăng nhập vnstock.
- API mới: `/stock/{symbol}/history` (nến 1m → 1M), `/stock/{symbol}/quote`, `/quotes`, `/stock/{symbol}/company`, `/index/{symbol}/history`, `/index/{symbol}/members`, `/indices`, `/symbols`, `/groups/{group}/symbols`, `/status`.
- API cho tài khoản có cấp phù hợp: báo cáo tài chính, cổ đông, ban lãnh đạo, công ty con, sự kiện, lệnh khớp, khối ngoại, vĩ mô.
- Báo lỗi rõ ràng: 403 khi chưa đủ quyền, 429 khi hết lượt, 404 khi sai mã, 503 khi nguồn lỗi, kèm `hint` tiếng Việt.
- Cache theo loại dữ liệu (`CACHE_TTL`, `CACHE_TTL_HISTORY`, `CACHE_TTL_REFERENCE`). Các request trùng nhau dùng chung một lượt gọi.
- Tài liệu: README cho người mới, `docs/API.md`, `docs/vnstock-account.md`, `docs/deploy.md`, CONTRIBUTING, SECURITY, CODE_OF_CONDUCT.

### Sửa
- `/stock/{symbol}` trước giờ mở cửa trả cùng một phiên cho cả `today` lẫn `previous`. Giờ `today` là phiên mới nhất, `previous` là phiên liền trước.
- `/stock/{symbol}/recent?days=N` đôi khi trả ít hơn N phiên do khoảng ngày quá ngắn.
- Ngày giờ trong kết quả giữ múi giờ Việt Nam, không còn bị lệch sang ngày hôm trước do đổi sang UTC.
- `FAST_SYMBOLS` cấu hình được qua biến môi trường, không còn gắn cứng `PDR`.

## [2.1.0]
- Bản dùng vnstock 3.5.1: `/stock/{symbol}`, `/recent`, `/day-range`, `/health`.
