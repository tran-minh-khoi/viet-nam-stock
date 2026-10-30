# Đóng góp cho Vietnam Stock API

Cảm ơn bạn đã muốn đóng góp! Project hoan nghênh mọi đóng góp: báo lỗi, đề xuất tính năng, sửa tài liệu, viết thêm API.

## Báo lỗi và đề xuất

- Tìm trong [Issues](https://github.com/tran-minh-khoi/viet-nam-stock/issues) trước, có thể đã có người báo.
- Báo lỗi thì ghi: lệnh hoặc URL bạn gọi, kết quả mong đợi, kết quả thực tế, log (`docker compose logs`), và cấp tài khoản vnstock (lấy từ `/status`).
- **Đừng dán API key** vào issue.
- Lỗ hổng bảo mật thì **không** mở issue công khai, xem [SECURITY.md](SECURITY.md).

## Môi trường phát triển

```bash
git clone https://github.com/<ban>/viet-nam-stock.git
cd viet-nam-stock
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
python api.py        # http://localhost:8000/docs
pytest               # phải pass hết trước khi gửi PR
```

Test không gọi vnstock thật, nên không tốn lượt và chạy được offline sau khi đã cài xong.

## Thêm một API mới

1. Kiểm tra chức năng vnstock tương ứng có ở cấp nào: gọi thử, hoặc xem `rule.routes` trong `/status`.
2. Thêm endpoint trong `api.py`, gọi vnstock qua `cached(key, ttl, fn)` để có cache và gộp request trùng.
3. Chọn TTL hợp lý: giá trong phiên dùng `CACHE_TTL`, dữ liệu ít đổi dùng `CACHE_TTL_REFERENCE`.
4. Gắn tag `Cần tài khoản vnstock` nếu tài khoản Khách không dùng được.
5. Thêm test trong `tests/` với vnstock giả lập, như `tests/test_api.py`.
6. Cập nhật `docs/API.md` và `CHANGELOG.md`.

## Quy ước

- Mỗi PR làm một việc, mô tả ngắn gọn cái gì đổi và vì sao.
- Giữ nguyên định dạng trả về của các API đang có. Đổi định dạng sẽ làm hỏng app của người khác.
- Thông báo lỗi cho người dùng viết bằng tiếng Việt. Code và comment viết bằng tiếng Anh hoặc tiếng Việt đều được.
- Không thêm thư viện mới nếu vài dòng code tự viết được.
- Không thêm code né hạn mức hay giấy phép của vnstock (nhiều tài khoản, giả thiết bị...). PR kiểu này sẽ bị từ chối.

Khi gửi đóng góp, bạn đồng ý để đóng góp đó được phát hành theo giấy phép [MIT](LICENSE) của project.
