# Nguồn dữ liệu, khoá và giấy phép

Project này lấy dữ liệu qua [vnstock thế hệ 6](https://vnstocks.com/docs/vnstock/v6). Khác với các bản trước, vnstock 6 **không có nguồn dùng chung**: bạn chọn nguồn, dùng khoá Open API mà chính nguồn đó cấp cho bạn, và dữ liệu đi thẳng từ máy bạn tới nguồn. vnstock lo phần kết nối, đối chiếu và chuẩn hoá cột.

## Nguồn nào cho dữ liệu nào

| Nguồn | Biến trong `.env` | Lấy khoá ở đâu | Project dùng cho |
|---|---|---|---|
| **DNSE** | `DNSE_API_KEY`, `DNSE_API_SECRET` | Trang quản lý Open API trong tài khoản DNSE. Secret chỉ hiện **một lần**, lưu ngay | Giá theo ngày và trong phiên, lệnh khớp, bảng giá (tham chiếu/trần/sàn + 3 bước giá), chỉ số, danh mục mã, khối ngoại |
| SSI | `SSI_API_KEY`, `SSI_API_SECRET` | Cổng nhà phát triển SSI (FastConnect) | Thành phần chỉ số, nhóm mã (VN30, VN100...), danh sách chỉ số |
| FHSC | `FHSC_API_KEY` | Trang quản lý API trong tài khoản FHSC | Hồ sơ doanh nghiệp, cổ đông, sở hữu, giao dịch nội bộ, sự kiện, báo cáo tài chính, bảng giá đầy đủ |
| TCBS | `TCBS_API_KEY` | TCInvest, khoá có hạn dùng | Bảng giá. Phiên mở bằng Smart OTP và hết sau tối đa 8 giờ, nên không hợp chạy trên server |

**Bắt đầu với DNSE là đủ** cho `/stock/*`, `/stocks`, `/quote`, `/trades`, `/foreign-flow`, `/index/*/history`, `/symbols`. Các nhóm khác cần thêm khoá tương ứng; chưa có thì endpoint đó trả **403** và `hint` ghi rõ biến cần đặt.

Đổi nguồn bằng biến trong `.env`:

| Biến | Mặc định | Nhận |
|---|---|---|
| `DATA_SOURCE` | `dnse` | `dnse`, `ssi`, `tcbs`, `fhsc` (giá theo ngày); lệnh khớp chỉ có ở `dnse`, `tcbs` |
| `QUOTE_SOURCE` | `dnse` | `dnse` (ghép từ giá trần/sàn chính thức + sổ lệnh 3 bước), `fhsc`, `tcbs` (bảng giá đầy đủ của nguồn) |
| `COMPANY_SOURCE` | `fhsc` | `fhsc` |
| `INDEX_SOURCE` | `ssi` | `ssi` (danh sách chỉ số có cả ở `fhsc`) |

Bảng đầy đủ hàm nào có ở nguồn nào: chạy `vnstock tools` trong môi trường đã cài, hoặc xem [tài liệu vnstock 6](https://vnstocks.com/docs/vnstock/v6/tham-khao).

## Gắn khoá

1. Trong thư mục project: `cp .env.example .env` (Windows: `copy .env.example .env`).
2. Mở `.env`, điền khoá, ví dụ:
   ```
   DNSE_API_KEY=key_cua_ban
   DNSE_API_SECRET=secret_cua_ban
   ```
3. `docker compose up -d` (PM2: `pm2 restart viet-nam-stock`).
4. Mở http://localhost:8000/status. Mục `"keys"` cho biết nguồn nào API đã đọc được khoá. `/status` không bao giờ in giá trị khoá.

**Giữ khoá bí mật.** `.env` đã nằm trong `.gitignore`. Trên server, `chmod 600 .env`. vnstock 6 cũng đọc được khoá từ keyring của hệ điều hành (`vnstock keys set dnse`), nhưng server và Docker thường không có keyring nên project dùng `.env`.

## Hạn mức

Mỗi nguồn tự đặt hạn mức và điều khoản cho khoá của nó. Project tự giới hạn thêm ở phía mình:

- `BUDGET_PER_MINUTE` (mặc định 30): trần số lượt gọi nguồn mỗi phút của cả API, tính chung mọi endpoint. Hết thì `/stock/*` trả 503 "Hệ thống đang bận", các endpoint khác trả 429, cả hai kèm `Retry-After`.
- `BUDGET_RESERVED_FOR_PRIORITY` (mặc định 6): phần dành riêng cho `PRIORITY_SYMBOLS`, để mã quan trọng nhất vẫn được làm mới khi có nhiều người gọi mã lạ.
- Cache: `/stock/*` giữ mỗi mã 20–30 giây trong giờ giao dịch, 5 phút ngoài giờ; mã không tồn tại bị nhớ 1 giờ, không tốn lượt gọi lại.

Một lượt làm mới `/stock/{symbol}` tốn 2 lượt gọi trong giờ giao dịch (giá ngày + lệnh khớp gần nhất), 1 lượt ngoài giờ.

## Phiên bản vnstock hết hạn

vnstock 6 đang ở bản thử (rc). Mỗi bản chỉ dùng được một thời gian: 6.0.0rc5 dùng được đến hết **09/12/2026**. Xem hạn của bản đang chạy ở `releaseExpiresAt` trong `/status`. Gần hạn:

```bash
git pull
docker compose up -d --build
```

Nếu project chưa kịp cập nhật, sửa dòng `vnstock==...` trong `requirements.txt` thành bản mới (xem `vnstock version`) rồi build lại. Gửi Pull Request cho mọi người dùng chung càng tốt.

## Giấy phép

- **Code của project này:** MIT, không chứa vnstock.
- **vnstock:** tải về máy bạn khi build, theo [giấy phép riêng của vnstock](https://vnstocks.com/onboard/giay-phep-su-dung). Quyền dùng phần mềm vnstock theo gói quyền sử dụng của vnstocks.com. Đọc kỹ nếu bạn định mở API cho người khác dùng hoặc phân phối lại image có sẵn vnstock.
- **Dữ liệu:** thuộc về nguồn và đi theo điều khoản của khoá bạn đăng ký với nguồn. Có quyền dùng vnstock không có nghĩa là có quyền lấy dữ liệu của một nguồn, và ngược lại.
- ❌ Không tạo nhiều khoá hay can thiệp để vượt hạn mức của nguồn; không bán hoặc phân phối lại dữ liệu.

Liên hệ tác giả vnstock: support@vnstocks.com.
