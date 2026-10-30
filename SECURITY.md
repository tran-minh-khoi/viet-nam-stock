# Bảo mật

## Báo cáo lỗ hổng

**Đừng mở issue công khai.** Hãy dùng [GitHub private vulnerability reporting](https://github.com/tran-minh-khoi/viet-nam-stock/security/advisories/new) (tab *Security → Report a vulnerability*), hoặc email **contact@tranminhkhoi.dev** với tiêu đề bắt đầu bằng `[SECURITY]`.

Nêu rõ: mô tả lỗ hổng, cách tái hiện, mức ảnh hưởng. Bạn sẽ nhận phản hồi trong vòng 7 ngày.

## Phiên bản được hỗ trợ

Chỉ bản mới nhất trên nhánh `main` được sửa lỗi bảo mật.

## Lời khuyên khi tự host

- Giữ `VNSTOCK_API_KEY` trong `.env`, không commit và không chia sẻ.
- Trên VPS, chỉ mở cổng cho localhost (`127.0.0.1:8000:8000`) và đặt reverse proxy có xác thực phía trước. Xem [docs/deploy.md](docs/deploy.md).
- Nếu chỉ một website cần gọi API, đặt `CORS_ORIGINS` là đúng tên miền đó thay vì `*`.
- Cập nhật thường xuyên: `git pull && docker compose up -d --build`.
