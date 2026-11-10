# Vietnam Stock API

[![Tests](https://github.com/tran-minh-khoi/viet-nam-stock/actions/workflows/test.yml/badge.svg)](https://github.com/tran-minh-khoi/viet-nam-stock/actions/workflows/test.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

API chứng khoán Việt Nam gọn nhẹ, **tự chạy trên máy bạn**, lấy dữ liệu thẳng từ [DNSE Lightspeed API](https://developers.dnse.com.vn/docs) bằng khoá của chính bạn. Giá cổ phiếu, phiên hôm nay, bảng giá, khối ngoại, chỉ số VNINDEX/VN30, trả về JSON.

- 3 thư viện: `fastapi`, `uvicorn`, `httpx`. Không vnstock, không pandas, không cơ sở dữ liệu.
- Người dùng không bao giờ phải chờ nguồn: dữ liệu giữ trong bộ nhớ, hết hạn vẫn trả ngay rồi làm mới ở nền.
- Tự giới hạn số lượt gọi DNSE mỗi phút. 100 người cùng xem một mã chỉ tốn 1 lượt.

> 🇬🇧 *A small self-hosted REST API for Vietnamese stock data, straight from DNSE's Lightspeed API with your own key. Get a key (steps below), put it in `.env`, run `docker compose up -d`, open http://localhost:8000/docs. Endpoint reference: [docs/API.md](docs/API.md).*

## 1. Lấy khoá DNSE (5 phút, miễn phí)

1. Có tài khoản chứng khoán DNSE (mở online tại [dnse.com.vn](https://www.dnse.com.vn)), đã bật Smart OTP hoặc xác thực email.
2. Đăng nhập trang giao dịch DNSE → **Họ tên → Thông tin tài khoản → LightSpeed API** → **Đăng ký**, chọn cách nhận OTP, nhập OTP.
3. Trang hiện **API Key** và **API Secret**. **Chép Secret ngay**, DNSE chỉ hiện một lần.

Hướng dẫn gốc của DNSE: [Đăng ký & quản lý dịch vụ](https://developers.dnse.com.vn/docs/guide/intro/register_guide/) · [Xác thực](https://developers.dnse.com.vn/docs/guide/intro/authentication/) · [Hạn mức gọi](https://developers.dnse.com.vn/docs/guide/ratelimits/)

## 2. Chạy

```bash
git clone https://github.com/tran-minh-khoi/viet-nam-stock.git
cd viet-nam-stock
cp .env.example .env        # điền DNSE_API_KEY, DNSE_API_SECRET
docker compose up -d
```

Mở http://localhost:8000/docs để bấm thử, hoặc:

```bash
curl http://localhost:8000/stock/VCB
```

Không dùng Docker:

```bash
python3 -m venv venv && ./venv/bin/pip install -r requirements.txt
./start.sh                  # hoặc: pm2 start ecosystem.config.js
```

## 3. Dùng

| Endpoint | Trả về |
|---|---|
| `GET /stock/{mã}` | Phiên hôm nay, giá đang khớp, tham chiếu/trần/sàn, phiên trước |
| `GET /stock/{mã}/recent?days=7` | N phiên gần nhất (tối đa 30) |
| `GET /stocks?symbols=VCB,FPT` | Nhiều mã một lượt (tối đa 10) |
| `GET /stock/{mã}/history?interval=1D` | Nến `1m 5m 15m 30m 1H 1D 1W`, theo `start`/`end` hoặc `limit` |
| `GET /stock/{mã}/day-range?start_date=&end_date=` | Các phiên trong khoảng ngày |
| `GET /stock/{mã}/quote`, `GET /quotes?symbols=` | Bảng giá: tham chiếu/trần/sàn chính thức, 3 bước giá mua/bán |
| `GET /stock/{mã}/foreign-flow` | Khối ngoại mua/bán theo ngày |
| `GET /index/{chỉ số}/history` | Nến VNINDEX, VN30, HNXINDEX, UPCOMINDEX... |
| `GET /symbols` | Mã cổ phiếu và chứng chỉ quỹ đang niêm yết |
| `GET /health`, `GET /status` | Tình trạng dịch vụ, hạn mức DNSE còn lại |

Giá tính bằng **nghìn đồng** (`57.2` = 57.200đ), khối lượng tính bằng **cổ phiếu**. Ví dụ và đủ các trường: [docs/API.md](docs/API.md).

## 4. Cấu hình

Mọi thứ nằm trong `.env`, xem [.env.example](.env.example). Hay dùng nhất:

| Biến | Ý nghĩa |
|---|---|
| `DNSE_API_KEY`, `DNSE_API_SECRET` | Khoá DNSE (bắt buộc) |
| `PRIORITY_SYMBOLS` | Mã luôn được làm mới ở nền, ví dụ `VCB,FPT` |
| `BUDGET_PER_MINUTE` | Trần lượt gọi DNSE mỗi phút (mặc định 60) |
| `SNAPSHOT_FILE` | Lưu dữ liệu tốt gần nhất ra đĩa, khởi động lại là có ngay |
| `CORS_ORIGINS` | Website được gọi API từ trình duyệt |

## Lưu ý

- **Điều khoản DNSE:** dữ liệu Lightspeed API chỉ dùng cho mục đích giao dịch của chính chủ tài khoản. Muốn cung cấp dữ liệu cho người khác (website, app công khai...) cần DNSE chấp thuận bằng văn bản ([§2(đ) điều khoản](https://hdsd.dnse.com.vn/die-u-khoa-n-di-ch-vu-dnse/dieu-khoan-san-pham-dich-vu/dieu-khoan-san-pham-lightspeed-api)). Bạn tự chịu trách nhiệm với khoá của mình.
- Giữ `.env` riêng tư (`chmod 600 .env`), không commit. Đồng hồ server phải đúng giờ (DNSE từ chối chữ ký lệch quá 1 phút).
- Chạy **một** tiến trình: bộ nhớ đệm và trần lượt gọi nằm trong tiến trình.
- Không phải tư vấn đầu tư. Dữ liệu có thể trễ hoặc sai, hãy đối chiếu trước khi giao dịch.
- Dự án độc lập, không liên kết với DNSE.

## Đóng góp

Xem [CONTRIBUTING.md](CONTRIBUTING.md). Chạy test: `pip install -r requirements-dev.txt && pytest` (không cần khoá, không gọi mạng).

Giấy phép [MIT](LICENSE).
