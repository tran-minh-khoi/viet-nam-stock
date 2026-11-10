# Đóng góp

Mọi đóng góp đều quý: báo lỗi, sửa tài liệu, thêm endpoint.

## Báo lỗi

- Tìm trong [Issues](https://github.com/tran-minh-khoi/viet-nam-stock/issues) trước.
- Ghi rõ URL đã gọi, kết quả mong đợi, kết quả thực tế, log (`docker compose logs --tail 50`).
- **Đừng dán API key/secret.** Lỗ hổng bảo mật: xem [SECURITY.md](SECURITY.md).

## Phát triển

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
pytest           # không cần khoá, không gọi mạng
./start.sh       # http://localhost:8000/docs (cần .env có khoá DNSE)
```

Cấu trúc:

| File | Việc |
|---|---|
| `dnse.py` | Client DNSE: ký HMAC, gọi HTTP, đổi mã lỗi thành exception |
| `sources.py` | Đổi câu trả lời DNSE thành dict của API (file duy nhất biết tên trường của DNSE) |
| `engine.py` | Bộ nhớ đệm `/stock/*`, làm mới nền, trần lượt gọi, snapshot |
| `api.py` | Endpoint FastAPI |

`tests/test_contract.py` so từng trường của `/stock/*` với phản hồi thật đã chụp (`tests/fixtures/`). Test này đỏ nghĩa là app đang dùng API sẽ thấy khác.

## Thêm endpoint

1. Tìm endpoint DNSE trong [tài liệu DNSE](https://developers.dnse.com.vn/docs), viết hàm trong `sources.py`.
2. Thêm route trong `api.py` qua `cached(key, ttl, fn, cost)` để có cache, gộp request trùng và tính vào trần lượt gọi.
3. Thêm test với `fake_dnse` (xem `tests/test_endpoints.py`), cập nhật `docs/API.md` và `CHANGELOG.md`.

## Quy ước

- Mỗi PR một việc. Không đổi định dạng trả về của endpoint đang có.
- Thông báo lỗi cho người dùng bằng tiếng Việt.
- Không thêm thư viện nếu vài dòng code tự viết được.
- Không thêm code né hạn mức hay điều khoản của DNSE.

Đóng góp được phát hành theo giấy phép [MIT](LICENSE).
