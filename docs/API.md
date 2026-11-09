# Tài liệu API

Địa chỉ gốc khi chạy trên máy: `http://localhost:8000`. Trang thử trực tiếp: `http://localhost:8000/docs`. File OpenAPI: `/openapi.json`, nhập được vào Postman hoặc Insomnia.

**Quy ước chung**
- Mã chứng khoán không phân biệt hoa thường (`pdr` = `PDR`).
- Ngày có dạng `YYYY-MM-DD`. Giờ theo múi giờ Việt Nam.
- **Mọi giá tính bằng nghìn đồng** (11.6 = 11.600đ). Khối lượng tính bằng cổ phiếu. Giá trị giao dịch (`*_val`) tính bằng đồng.
- Mọi API chỉ dùng `GET`. Không cần đăng nhập.
- Trường không có dữ liệu trả về `null`.
- Cột "Nguồn" cho biết khoá cần có. Thiếu khoá thì API đó trả **403** kèm tên biến cần đặt, xem [data-sources.md](data-sources.md).

Ví dụ trong tài liệu này là kết quả thật của mã PDR ngày 09/11/2026, nguồn DNSE.

**Mục lục:** [Cổ phiếu](#cổ-phiếu) · [Bảng giá và giao dịch](#bảng-giá-và-giao-dịch) · [Chỉ số và danh mục](#chỉ-số-và-danh-mục) · [Doanh nghiệp](#doanh-nghiệp) · [Hệ thống](#hệ-thống) · [Mã lỗi](#mã-lỗi) · [Cache và hạn mức](#cache-và-hạn-mức)

---

## Cổ phiếu

`/stock/{symbol}`, `/stock/{symbol}/recent` và `/stocks` chạy trên engine giữ dữ liệu trong bộ nhớ: khi một mã đã được hỏi, các lần sau trả ngay (vài mili giây), dữ liệu cũ được làm mới ở nền. Mã phải có trong danh mục niêm yết, mã lạ trả 404 mà không tốn lượt gọi nguồn.

### `GET /stock/{symbol}` · DNSE

Phiên mới nhất, phiên liền trước, giá hiện tại, giá tham chiếu/trần/sàn.

| Tham số | Kiểu | Mô tả |
|---|---|---|
| `recent` | số, tuỳ chọn | Truyền vào thì trả kết quả như `/stock/{symbol}/recent?days=` |

```json
{
  "symbol": "PDR",
  "name": "PHÁT ĐẠT",
  "fullName": "CTCP Phát triển Bất động sản Phát Đạt",
  "nameEn": "Phat Dat Real Estate Development Corporation",
  "exchange": "HOSE",
  "currentPrice": 11.6,
  "referencePrice": 11.75,
  "upperPrice": 12.55,
  "lowerPrice": 10.95,
  "change": -0.15,
  "changePercent": -1.28,
  "todayOpen": 11.75, "todayHigh": 11.9, "todayLow": 11.45,
  "todayVolume": 5237000,
  "todayDate": "2026-11-09",
  "previousClose": 11.75,
  "previousVolume": 7325400,
  "previousDate": "2026-11-06",
  "lastUpdated": "2026-11-09T16:27:27.737871",
  "data": {
    "today": { "date": "2026-11-09", "open": 11.75, "close": 11.6, "high": 11.9, "low": 11.45,
               "volume": 5237000, "current_price": 11.6, "reference_price": 11.75,
               "ceiling": 12.55, "floor": 10.95, "is_today": true },
    "previous": { "date": "2026-11-06", "close": 11.75, "volume": 7325400 }
  },
  "marketOpen": false,
  "stale": false,
  "timestamp": "2026-11-09T16:28:13.891752"
}
```

- `today*` là **phiên mới nhất**. Trước giờ mở cửa hoặc ngày nghỉ, đó là phiên gần nhất trước đó và `data.today.is_today` là `false`.
- `currentPrice`: trong giờ giao dịch (8:45–15:05, thứ 2–6) là giá khớp gần nhất (nến 1 phút cuối, nếu chưa quá 10 phút); ngoài giờ là giá đóng cửa phiên mới nhất.
- `referencePrice` là giá đóng cửa phiên trước. `upperPrice`/`lowerPrice` tính theo sàn của mã: HOSE ±7%, HNX ±10%, UPCOM ±15%, làm tròn vào trong theo bước giá. Giá trần/sàn chính thức của sở: `/stock/{symbol}/quote`.
- `name` có thể là tên ngắn đặt bằng `SHORT_NAMES`; `fullName` luôn là tên niêm yết.
- `lastUpdated`: lúc API lấy dữ liệu từ nguồn. `stale: true` nghĩa là lần làm mới gần nhất đã lâu (nguồn đang lỗi), dữ liệu vẫn là bản tốt gần nhất.

### `GET /stock/{symbol}/recent` · DNSE

N phiên gần nhất, cũ trước mới sau. Phiên cuối có thêm `current_price`.

| Tham số | Kiểu | Mặc định | Mô tả |
|---|---|---|---|
| `days` | số | 7 | Số phiên, tối đa `MAX_RECENT` (30). Ngoài khoảng thì tự kẹp về 1–30 |

```json
{
  "symbol": "PDR", "name": "PHÁT ĐẠT", "exchange": "HOSE",
  "days": 2, "actual_sessions": 2,
  "sessions": [
    { "date": "2026-11-06", "open": 11.3, "close": 11.75, "high": 11.9, "low": 11.25, "volume": 7325400,
      "reference_price": 11.55, "ceiling": 12.35, "floor": 10.75, "is_today": false },
    { "date": "2026-11-09", "open": 11.75, "close": 11.6, "high": 11.9, "low": 11.45, "volume": 5237000,
      "reference_price": 11.75, "ceiling": 12.55, "floor": 10.95, "is_today": true, "current_price": 11.6 }
  ],
  "lastUpdated": "2026-11-09T16:27:27.737871",
  "timestamp": "2026-11-09T16:28:13.902257"
}
```

### `GET /stocks?symbols=PDR,VNM` · DNSE

Như `/stock/{symbol}` cho tối đa `MAX_BATCH` (10) mã một lượt. Mã trùng chỉ tính một lần. Mã lỗi không làm hỏng cả lượt mà nằm trong `errors`:

```json
{
  "data": { "PDR": { "symbol": "PDR", "currentPrice": 11.6, "...": "như /stock/PDR" } },
  "errors": { "XXXX": { "status": 404, "message": "Không tìm thấy mã XXXX" } },
  "timestamp": "2026-11-09T16:28:13.912235"
}
```

### `GET /stock/{symbol}/day-range` · DNSE

Các phiên trong một khoảng ngày, kèm giá tham chiếu/trần/sàn của từng phiên.

| Tham số | Bắt buộc | Mô tả |
|---|---|---|
| `start_date` | ✅ | Ngày bắt đầu |
| `end_date` | ✅ | Ngày kết thúc |

```json
{
  "symbol": "PDR", "start_date": "2026-11-06", "end_date": "2026-11-09", "total_sessions": 2,
  "sessions": [
    { "date": "2026-11-06", "open": 11.3, "high": 11.9, "low": 11.25, "close": 11.75, "volume": 7325400,
      "reference_price": 11.55, "ceiling": 12.35, "floor": 10.75 }
  ],
  "timestamp": "2026-11-09T16:28:29.583094"
}
```

### `GET /stock/{symbol}/history` · DNSE

Nến OHLCV thô theo khung thời gian, phù hợp để vẽ biểu đồ.

| Tham số | Mặc định | Mô tả |
|---|---|---|
| `interval` | `1D` | `1m`, `5m`, `15m`, `30m`, `1H`, `1D`, `1W`, `1M` |
| `start`, `end` | | Khoảng ngày. Chỉ có `start` thì lấy đến hôm nay |
| `limit` | | Số nến mới nhất (1–1000), dùng khi không truyền `start` |

```json
{
  "symbol": "PDR", "interval": "1H", "count": 2,
  "data": [
    { "time": "2026-11-09T13:00:00+07:00", "open": 11.7, "high": 11.7, "low": 11.45, "close": 11.55, "volume": 1702300 },
    { "time": "2026-11-09T14:00:00+07:00", "open": 11.55, "high": 11.6, "low": 11.45, "close": 11.6, "volume": 1423600 }
  ]
}
```

Khung `1D`/`1W`/`1M` có `time` dạng `YYYY-MM-DD` (`1W` là ngày đầu tuần). Khung trong ngày có `time` dạng ISO kèm `+07:00`.

---

## Bảng giá và giao dịch

### `GET /stock/{symbol}/quote` · DNSE (`QUOTE_SOURCE`)

Với nguồn `dnse`: giá tham chiếu/trần/sàn **chính thức của sở** (bảng G1) và 3 bước giá mua/bán tốt nhất của bảng lô chẵn.

```json
{
  "symbol": "PDR", "exchange": "HOSE", "trading_date": "2026-11-09T00:00:00+07:00",
  "reference_price": 11.75, "ceiling_price": 12.55, "floor_price": 10.95,
  "bid_price_1": 11.6, "bid_vol_1": 3970, "bid_price_2": 11.55, "bid_vol_2": 12440, "bid_price_3": 11.5, "bid_vol_3": 8820,
  "ask_price_1": 11.65, "ask_vol_1": 48090, "ask_price_2": 11.7, "ask_vol_2": 32210, "ask_price_3": 11.75, "ask_vol_3": 14690,
  "time": "2026-11-09T14:45:03.278000+07:00",
  "total_bid_volume": 0, "total_ask_volume": 0
}
```

Với `QUOTE_SOURCE=fhsc` hoặc `tcbs`: trả nguyên bảng giá đầy đủ của nguồn (giá, khối lượng phiên, 3 bước giá, khối ngoại); tên cột theo nguồn.

### `GET /quotes?symbols=PDR,SHS` · DNSE (`QUOTE_SOURCE`)

Bảng giá nhiều mã: `{"count": 2, "data": [ ...như /quote... ]}`. Nguồn `dnse` tối đa 10 mã mỗi lượt (mỗi mã tốn 2 lượt gọi); `fhsc`/`tcbs` tối đa 50 mã trong 1 lượt gọi.

### `GET /stock/{symbol}/trades` · DNSE

Lệnh khớp trong phiên, mới nhất trước.

| Tham số | Mặc định | Mô tả |
|---|---|---|
| `limit` | 100 | 1–1000 |

```json
{
  "symbol": "PDR", "count": 2,
  "data": [
    { "time": "2026-11-09T14:45:03.273000+07:00", "price": 11.6, "volume": 100, "match_type": "ATC", "id": "1", "accumulated_volume": 523700 },
    { "time": "2026-11-09T14:45:03.272000+07:00", "price": 11.6, "volume": 300, "match_type": "ATC", "id": "10", "accumulated_volume": 517280 }
  ]
}
```

DNSE phân trang lệnh khớp từ đầu phiên, nên cuối phiên một lượt gọi có thể mất vài giây.

### `GET /stock/{symbol}/foreign-flow` · DNSE

Khối ngoại mua/bán theo ngày. `*_vol` là cổ phiếu, `*_val` là đồng.

| Tham số | Mô tả |
|---|---|
| `start`, `end` | Khoảng ngày. Chỉ có `start` thì lấy đến hôm nay. Không truyền thì là phiên gần nhất |

```json
{
  "symbol": "PDR", "count": 2,
  "data": [
    { "time": "2026-11-06T00:00:00+07:00", "buy_vol": 330187.0, "buy_val": 3766673550.0, "sell_vol": 84600.0,
      "sell_val": 1001005000.0, "net_vol": 245587.0, "net_val": 2765668550.0 },
    { "time": "2026-11-09T00:00:00+07:00", "buy_vol": 40200.0, "buy_val": 469195000.0, "sell_vol": 496300.0,
      "sell_val": 6044025000.0, "net_vol": -456100.0, "net_val": -5574830000.0 }
  ]
}
```

---

## Chỉ số và danh mục

| API | Nguồn | Tham số | Kết quả |
|---|---|---|---|
| `GET /index/{symbol}/history` | DNSE | như `/stock/{symbol}/history` | Nến của `VNINDEX`, `VN30`, `HNXINDEX`, `UPCOMINDEX`... |
| `GET /symbols` | DNSE | | Mọi cổ phiếu niêm yết: `symbol`, `exchange`, `type`, `organ_name`, `listing_date`... |
| `GET /index/{symbol}/members` | SSI | | `{"index": "VN30", "count": 30, "symbols": ["ACB", ...]}` |
| `GET /groups/{group}/symbols` | SSI | | Mã theo nhóm `VN30`, `VN100`, `HNX30`... |
| `GET /indices` | SSI | | Danh sách chỉ số |

```json
{ "symbol": "VNINDEX", "interval": "1D", "count": 2,
  "data": [
    { "time": "2026-11-06", "open": 1713.46, "high": 1734.42, "low": 1713.46, "close": 1725.36, "volume": 972595584 },
    { "time": "2026-11-09", "open": 1728.27, "high": 1728.27, "low": 1701.9, "close": 1714.32, "volume": 670101248 }
  ] }
```

Giá trị chỉ số tính bằng điểm, không phải nghìn đồng.

---

## Doanh nghiệp

Cần khoá **FHSC** (`COMPANY_SOURCE`).

| API | Tham số | Ghi chú |
|---|---|---|
| `GET /stock/{symbol}/company` | | Hồ sơ: tên, ngành, giới thiệu |
| `GET /stock/{symbol}/company/{section}` | | `section`: `shareholders` (cổ đông lớn), `ownership` (cơ cấu sở hữu), `insider_trading` (giao dịch nội bộ), `events` (sự kiện) |
| `GET /stock/{symbol}/financials/{report}` | `period=quarter\|year` | `report`: `income_statement`, `balance_sheet`, `cash_flow` (chuẩn VAS) |

Kết quả dạng `{"symbol", "count", "data": [...]}` với cột theo vnstock 6.

---

## Hệ thống

### `GET /health`

Trạng thái engine. Dùng cho healthcheck: luôn trả 200 khi API còn chạy, kể cả khi nguồn đang lỗi.

```json
{ "status": "ok", "uptimeSeconds": 68, "marketOpen": false, "cachedSymbols": 1, "listedSymbols": 1541,
  "upstreamCallsLastMinute": 4, "upstreamLimitPerMinute": 30, "priorityAgeSeconds": 61 }
```

`priorityAgeSeconds`: số giây từ lần làm mới gần nhất của mã ưu tiên đầu tiên (`PRIORITY_SYMBOLS`). Số này tăng mãi nghĩa là nguồn đang lỗi.

### `GET /status`

Bản vnstock, hạn dùng của bản đó, nguồn nào đã có khoá (không bao giờ in giá trị khoá).

```json
{ "vnstock": "6.0.0rc5", "releaseExpiresAt": "2026-12-08T23:40:04Z", "tier": "guest",
  "serverMessage": null, "serverWarning": null,
  "keys": { "dnse": true, "ssi": false, "tcbs": false, "fhsc": false, "fmp": false },
  "sources": { "data": "dnse", "quote": "dnse", "company": "fhsc", "index": "ssi" },
  "upstreamCallsLastMinute": 4, "upstreamLimitPerMinute": 30 }
```

### `GET /`

Tên dịch vụ, phiên bản, các endpoint chính và đường dẫn `/docs`.

---

## Mã lỗi

Lỗi trả về dạng `{"detail": "...", "hint": "..."}` (`hint` có khi lỗi đến từ nguồn).

| Mã | Khi nào | Nên làm |
|---|---|---|
| `400` | Mã sai định dạng, ngày sai định dạng, quá số mã cho phép | Sửa tham số |
| `403` | Chưa có khoá cho nguồn của API này, hoặc khoá không có quyền | Đặt biến trong `hint` vào `.env`, xem [data-sources.md](data-sources.md) |
| `404` | Mã không niêm yết, hoặc nguồn không có dữ liệu | Kiểm tra mã |
| `422` | Tham số ngoài danh sách cho phép (ví dụ `interval=7X`) | Sửa tham số |
| `429` | Chạm trần lượt gọi nguồn mỗi phút của API, hoặc nguồn đang giới hạn tốc độ | Đợi theo `Retry-After`, gộp mã bằng `/stocks` |
| `502` | `/stock/*`: lần đầu hỏi mã này mà nguồn lỗi | Thử lại sau `Retry-After` |
| `503` | `/stock/*`: hết lượt gọi hoặc nguồn phản hồi chậm ở lần đầu hỏi một mã; API khác: nguồn lỗi | Thử lại sau `Retry-After` |
| `500` | Lỗi của API | Báo lỗi kèm log |

---

## Cache và hạn mức

| Dữ liệu | Giữ trong |
|---|---|
| `/stock/*`, `/stocks` | 20 giây (mã ưu tiên) hoặc 30 giây trong giờ giao dịch, 5 phút ngoài giờ. Hết hạn vẫn trả ngay, làm mới ở nền |
| Mã không có dữ liệu | 1 giờ |
| Bảng giá, lệnh khớp, nến trong phiên | `CACHE_TTL` (15 giây) |
| Lịch sử đã qua, khoảng ngày, khối ngoại | `CACHE_TTL_HISTORY` (5 phút) |
| Danh mục, doanh nghiệp, tài chính | `CACHE_TTL_REFERENCE` (1 ngày) |

Mọi lượt gọi nguồn của cả API đều tính vào trần `BUDGET_PER_MINUTE` (mặc định 30/phút), trong đó `BUDGET_RESERVED_FOR_PRIORITY` (6) dành cho mã ưu tiên. Một lượt làm mới `/stock/{symbol}` tốn 2 lượt trong giờ giao dịch, 1 lượt ngoài giờ. Nhiều request cùng lúc cho cùng một dữ liệu chỉ tốn 1 lượt gọi.
