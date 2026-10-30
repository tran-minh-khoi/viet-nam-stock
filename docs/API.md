# Tài liệu API

Địa chỉ gốc khi chạy trên máy: `http://localhost:8000`. Trang thử trực tiếp: `http://localhost:8000/docs`. File OpenAPI: `/openapi.json`, nhập được vào Postman hoặc Insomnia.

**Quy ước chung**
- Mã chứng khoán không phân biệt hoa thường (`vcb` = `VCB`), dài 2–12 ký tự gồm chữ và số.
- Ngày có dạng `YYYY-MM-DD`.
- Giá ở `/stock/*` và `/index/*` tính bằng **nghìn đồng**. Giá ở `/quote` và `/quotes` tính bằng **đồng**.
- Mọi API chỉ dùng `GET`. Không cần đăng nhập.
- Trường không có dữ liệu trả về `null`.

**Mục lục:** [Cổ phiếu](#cổ-phiếu) · [Chỉ số](#chỉ-số) · [Danh mục](#danh-mục) · [Cần tài khoản vnstock](#cần-tài-khoản-vnstock) · [Hệ thống](#hệ-thống) · [Mã lỗi](#mã-lỗi) · [Cache](#cache)

---

## Cổ phiếu

### `GET /stock/{symbol}`

Phiên giao dịch mới nhất và phiên liền trước, kèm giá tham chiếu, trần và sàn.

| Tham số | Kiểu | Mô tả |
|---|---|---|
| `recent` | số, tuỳ chọn | Truyền vào thì trả kết quả như `/stock/{symbol}/recent?days=` |

```json
{
  "symbol": "VCB",
  "name": "VCB",
  "exchange": "HOSE",
  "currentPrice": 57.2,
  "referencePrice": 57.5,
  "upperPrice": 61.5,
  "lowerPrice": 53.5,
  "todayOpen": 57.9,
  "todayHigh": 58.4,
  "todayLow": 57.0,
  "todayVolume": 4049800,
  "todayDate": "2026-10-29",
  "previousClose": 57.5,
  "previousVolume": 6453700,
  "previousDate": "2026-10-28",
  "lastUpdated": "2026-10-30T08:20:00.000000",
  "data": {
    "today": { "date": "2026-10-29", "open": 57.9, "close": 57.2, "high": 58.4, "low": 57.0,
               "volume": 4049800, "current_price": 57.2, "reference_price": 57.5,
               "ceiling": 61.5, "floor": 53.5, "is_today": false },
    "previous": { "date": "2026-10-28", "close": 57.5, "volume": 6453700 }
  },
  "timestamp": "2026-10-30T08:20:00.000000"
}
```

- `today*` là **phiên giao dịch mới nhất**. Trước giờ mở cửa hoặc vào ngày nghỉ, đó là phiên gần nhất trước đó. Khi đó `data.today.is_today` là `false`.
- `upperPrice`/`lowerPrice` tính từ giá đóng cửa phiên trước, theo biên độ ±7% và bước giá của HOSE. Với mã sàn HNX (±10%) hoặc UPCOM (±15%), lấy giá trần/sàn chính xác ở `/stock/{symbol}/quote`.
- `currentPrice` là giá đóng cửa của phiên mới nhất. Nếu mã nằm trong `FAST_SYMBOLS` và tài khoản có quyền xem lệnh khớp, đây là giá khớp mới nhất.

### `GET /stock/{symbol}/recent`

N phiên gần nhất, cũ trước mới sau.

| Tham số | Kiểu | Mặc định | Mô tả |
|---|---|---|---|
| `days` | 1–250 | 7 | Số phiên |

```json
{
  "symbol": "VCB", "days": 3, "actual_sessions": 3,
  "sessions": [
    { "date": "2026-10-27", "open": 56.1, "close": 56.1, "high": 56.4, "low": 56.0, "volume": 2438200,
      "reference_price": 56.1, "ceiling": 60.0, "floor": 52.2, "is_today": false }
  ],
  "timestamp": "..."
}
```

### `GET /stock/{symbol}/day-range`

Các phiên trong một khoảng ngày, cùng định dạng với `recent` nhưng không có `is_today`.

| Tham số | Bắt buộc | Mô tả |
|---|---|---|
| `start_date` | ✅ | Ngày bắt đầu |
| `end_date` | ✅ | Ngày kết thúc |

Tài khoản Khách chỉ xem được lịch sử 365 ngày gần nhất.

### `GET /stock/{symbol}/history`

Nến OHLCV thô theo khung thời gian, phù hợp để vẽ biểu đồ.

| Tham số | Mặc định | Mô tả |
|---|---|---|
| `interval` | `1D` | `1m`, `5m`, `15m`, `30m`, `1H`, `1D`, `1W`, `1M` |
| `start`, `end` | | Khoảng ngày. Không truyền thì lấy các nến mới nhất |
| `limit` | 100 | Số nến mới nhất (1–1000), dùng khi không truyền `start` |

```json
{
  "symbol": "FPT", "interval": "1H", "count": 2,
  "data": [
    { "time": "2026-10-29T13:00:00+07:00", "open": 52.5, "high": 52.9, "low": 52.5, "close": 52.7, "volume": 2025900 },
    { "time": "2026-10-29T14:00:00+07:00", "open": 52.7, "high": 53.3, "low": 52.5, "close": 52.7, "volume": 2632400 }
  ]
}
```

Khung `1D`/`1W`/`1M` có `time` dạng `YYYY-MM-DD`. Khung trong ngày có `time` dạng ISO kèm múi giờ `+07:00`.

### `GET /stock/{symbol}/quote`

Bảng giá của một mã, **đơn vị đồng**. Ví dụ minh hoạ trong giờ giao dịch:

```json
{
  "symbol": "VCB", "exchange": "HOSE",
  "reference_price": 57200.0, "ceiling_price": 61200.0, "floor_price": 53200.0,
  "open_price": 57300.0, "high_price": 57800.0, "low_price": 57100.0, "close_price": 57600.0,
  "bid_price_1": 57500.0, "bid_vol_1": 12000, "bid_price_2": 57400.0, "bid_vol_2": 30500, "bid_price_3": 57300.0, "bid_vol_3": 8100,
  "ask_price_1": 57600.0, "ask_vol_1": 9800,  "ask_price_2": 57700.0, "ask_vol_2": 21000, "ask_price_3": 57800.0, "ask_vol_3": 15400,
  "foreign_buy_volume": 250000, "foreign_sell_volume": 180000
}
```

Ngoài giờ giao dịch, các trường giá khớp và dư mua/bán là `null`. Chỉ còn tham chiếu, trần và sàn của phiên kế tiếp.

### `GET /quotes?symbols=VCB,FPT,HPG`

Bảng giá của tối đa 50 mã, **chỉ tốn 1 lượt gọi vnstock**. Nên dùng khi làm bảng theo dõi nhiều mã.

```json
{ "count": 3, "data": [ { "symbol": "FPT", "...": "giống /quote" }, { "symbol": "HPG" }, { "symbol": "VCB" } ] }
```

Mã không tồn tại sẽ bị bỏ qua.

### `GET /stock/{symbol}/company`

```json
{
  "symbol": "VCB",
  "name": "Ngân hàng Thương mại Cổ phần Ngoại thương Việt Nam",
  "short_name": "Vietcombank",
  "sector": "Banks",
  "profile": "Ngân hàng Thương mại Cổ phần Ngoại thương Việt Nam (Vietcombank) chính thức đi vào hoạt động ...",
  "listing_date": "2009-06-30T00:00:00+07:00",
  "issued_share": 8355675094.0
}
```

---

## Chỉ số

### `GET /index/{symbol}/history`

Giống `/stock/{symbol}/history` nhưng dùng cho chỉ số: `VNINDEX`, `VN30`, `HNXINDEX`, `HNX30`, `UPCOMINDEX`, `VN100`... Xem danh sách đầy đủ ở `/indices`.

### `GET /index/{symbol}/members`

```json
{ "index": "VN30", "count": 30, "symbols": ["ACB", "BID", "BSR", "CTG", "FPT", "..."] }
```

---

## Danh mục

Dữ liệu ít thay đổi nên được cache 24 giờ.

| API | Trả về |
|---|---|
| `GET /symbols` | Toàn bộ mã niêm yết (~1.700 mã): `symbol`, `org_name` |
| `GET /indices` | Các chỉ số: `symbol`, `name`, `description`, `full_name`, `group` |
| `GET /groups/{group}/symbols` | Mã theo nhóm: `VN30`, `VN100`, `VNMID`, `VNSML`, `HNX30`... |

---

## Cần tài khoản vnstock

Các API dưới đây chỉ chạy khi bạn điền `VNSTOCK_API_KEY` có cấp cho phép. Nếu chưa có quyền, API trả **403** kèm tên chức năng còn thiếu. Kết quả là dữ liệu thô từ vnstock, chuyển sang JSON. Tên cột phụ thuộc vào nguồn và phiên bản vnstock.

| API | Tham số | Dữ liệu |
|---|---|---|
| `GET /stock/{symbol}/financials/{report}` | `period=quarter\|year` | `report`: `income_statement`, `balance_sheet`, `cash_flow`, `ratio` |
| `GET /stock/{symbol}/company/{section}` | | `section`: `shareholders`, `officers`, `subsidiaries`, `events` |
| `GET /stock/{symbol}/trades` | `limit` (1–1000) | Lệnh khớp trong phiên |
| `GET /stock/{symbol}/foreign-flow` | `start`, `end` | Giao dịch khối ngoại |
| `GET /macro/{indicator}` | `start`, `end` | `gdp`, `cpi`, `fdi`, `import-export`, `credit`, `money-supply`, `exchange-rate`, `interbank-rate`, `deposit-rate`, `policy-rate` |

Mỗi API trả về dạng `{ "symbol": ..., "count": N, "data": [ {...}, ... ] }`.

---

## Hệ thống

| API | Trả về |
|---|---|
| `GET /health` | `{"status": "healthy"}`, dùng cho healthcheck |
| `GET /status` | Cấp tài khoản vnstock, hạn mức, số lượt đã dùng (`used`), danh sách chức năng được phép (`rule.routes`) |

---

## Mã lỗi

Lỗi luôn trả về dạng `{ "detail": "...", "hint": "..." }`.

| Mã | Khi nào | Nên làm gì |
|---|---|---|
| `400` | Tham số sai, ví dụ ngày sai định dạng | Sửa tham số |
| `403` | Tài khoản vnstock chưa có quyền với dữ liệu này | Xem [vnstock-account.md](vnstock-account.md) |
| `404` | Mã không tồn tại hoặc không có dữ liệu trong khoảng đã chọn | Kiểm tra mã và ngày |
| `422` | Tham số không hợp lệ: mã có ký tự lạ, `interval` sai | Xem thông báo trong `detail` |
| `429` | Hết lượt gọi vnstock (theo phút, giờ, ngày hoặc tháng) | Đợi, tăng cache, gộp mã bằng `/quotes` |
| `503` | Nguồn dữ liệu lỗi hoặc API key không hợp lệ | Thử lại sau, xem `docker compose logs` |

---

## Cache

Mỗi kết quả được giữ lại một thời gian. Trong khoảng đó, gọi lại không tốn lượt vnstock và trả về gần như ngay lập tức (~1ms).

| Loại dữ liệu | Biến | Mặc định |
|---|---|---|
| Phiên hôm nay, bảng giá, nến trong ngày | `CACHE_TTL` | 15 giây |
| Lịch sử giá đã qua | `CACHE_TTL_HISTORY` | 5 phút |
| Doanh nghiệp, danh mục, báo cáo tài chính, vĩ mô | `CACHE_TTL_REFERENCE` | 24 giờ |

Nhiều request cùng hỏi một dữ liệu tại cùng thời điểm sẽ dùng chung **một** lượt gọi.
