# Tài khoản vnstock, hạn mức và giấy phép

Project này lấy dữ liệu qua thư viện [vnstock](https://vnstocks.com). Từ thế hệ 5, vnstock tính lượt gọi và quyền xem dữ liệu theo **tài khoản**.

## Các cấp tài khoản

| Cấp | Cách có | Ghi chú |
|---|---|---|
| **Khách** | Mặc định, không cần làm gì | 10 lượt/phút · 100/giờ · 300/ngày · 1.000/tháng. Dùng được 8 chức năng, lịch sử giá ngày tối đa 365 ngày |
| **Cộng đồng** | Đăng ký miễn phí tại vnstocks.com | Hạn mức cao hơn và thêm chức năng. Xem con số chính xác tại trang giá của vnstocks |
| **Tài trợ** | Trả phí cho tác giả vnstock | Mở thêm dữ liệu: tài chính, vĩ mô, lệnh khớp... và được dùng cho công việc có thu nhập |

Số liệu cấp Khách ở trên đo ngày 30/10/2026 với vnstock 5.2.1. vnstocks có thể thay đổi, hãy xem số hiện tại tại `GET /status`.

### Tài khoản Khách dùng được gì

| Chức năng vnstock | API trong project |
|---|---|
| `market.equity.ohlcv` | `/stock/{symbol}`, `/recent`, `/day-range`, `/history` |
| `market.equity.quote` | `/stock/{symbol}/quote`, `/quotes` |
| `market.index.ohlcv` | `/index/{symbol}/history` |
| `fundamental.company.info` / `overview` | `/stock/{symbol}/company` |
| `reference.equity.list` | `/symbols` |
| `reference.index.list` | `/indices`, `/index/{symbol}/members` |
| `reference.market.symbols_by_group` | `/groups/{group}/symbols` |

Mọi API khác trả **403** cho đến khi bạn dùng API key có cấp phù hợp.

## Gắn API key

1. Đăng ký và đăng nhập tại [vnstocks.com](https://vnstocks.com).
2. Vào trang tài khoản, copy **API key**.
3. Trong thư mục project:
   ```bash
   cp .env.example .env        # Windows: copy .env.example .env
   ```
4. Mở file `.env` bằng Notepad hoặc TextEdit, điền:
   ```
   VNSTOCK_API_KEY=key_cua_ban
   ```
5. Chạy lại `docker compose up -d`.
6. Mở http://localhost:8000/status. Nếu `"tier"` không còn là `"guest"` thì đã gắn thành công.

Khi khởi động, log có dòng `vnstock login OK, tier=...`. Nếu key sai, log báo `vnstock login failed` và API tiếp tục chạy với tài khoản Khách.

**Giữ API key bí mật.** File `.env` đã nằm trong `.gitignore`, đừng commit hay gửi file này cho ai.

## Thiết bị

vnstock gắn tài khoản với **thiết bị**. Docker lưu thông tin đăng nhập và mã thiết bị trong volume `vnstock-data`, nên tắt bật hay cập nhật container vẫn là cùng một thiết bị.

- `docker compose down` **không** xoá volume.
- `docker compose down -v` **có** xoá volume, và lần chạy sau sẽ thành thiết bị mới. Chỉ dùng khi bạn thật sự muốn làm lại từ đầu.

## Phiên bản vnstock hết hạn

Mỗi bản vnstock chỉ dùng được khoảng 365 ngày. Bản 5.2.1 hết hạn ngày **27/10/2027**. Trước hạn khoảng 30 ngày, vnstock sẽ in cảnh báo trong log. Khi đó:

```bash
git pull
docker compose up -d --build
```

Nếu project chưa kịp cập nhật, bạn tự sửa dòng `vnstock==...` trong `requirements.txt` thành bản mới rồi build lại. Gửi Pull Request cho mọi người dùng chung càng tốt.

## Giấy phép vnstock: tóm tắt cho người dùng project này

Bản gốc: [vnstocks.com/onboard/giay-phep-su-dung](https://vnstocks.com/onboard/giay-phep-su-dung). Nếu có khác biệt, theo bản gốc.

- ✅ **Được:** cá nhân tự cài, tự chạy để học tập, nghiên cứu, theo dõi danh mục của chính mình. Bản Cộng đồng miễn phí cho các mục đích này.
- ✅ **Được:** đọc, sửa, chia sẻ **code của project này**. Code này là MIT và không chứa vnstock.
- ⚠️ **Cần thoả thuận bằng văn bản với tác giả vnstock**, kể cả khi miễn phí:
  - mở API này cho **người khác** truy cập dữ liệu, ví dụ một server công khai;
  - phân phối lại vnstock, ví dụ đăng Docker image đã cài sẵn vnstock lên Docker Hub.
- ❌ **Không được:** tạo nhiều tài khoản, giả mã thiết bị hay can thiệp để vượt hạn mức; bán hoặc phân phối lại dữ liệu; dịch ngược vnstock.

Liên hệ tác giả vnstock: support@vnstocks.com.
