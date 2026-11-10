# Tài liệu API

Gốc: `http://localhost:8000`. Trang thử: `/docs`. File OpenAPI: `/openapi.json` (nhập được vào Postman).

- Mã không phân biệt hoa thường (`pdr` = `PDR`). Ngày dạng `YYYY-MM-DD`, giờ Việt Nam.
- **Giá tính bằng nghìn đồng** (11.6 = 11.600đ). Khối lượng tính bằng cổ phiếu. Giá trị (`*_value`) tính bằng đồng.
- Chỉ có `GET`, không cần đăng nhập. Trường không có dữ liệu là `null`.

Ví dụ là kết quả thật của PDR ngày 10/11/2026, lúc đang giao dịch.

---

## Cổ phiếu

`/stock/{mã}`, `/stock/{mã}/recent`, `/stocks` trả từ bộ nhớ (vài mili giây). Dữ liệu cũ được làm mới ở nền: 20 giây với `PRIORITY_SYMBOLS`, 30 giây với mã khác trong giờ giao dịch, 5 phút ngoài giờ. Mã không niêm yết trả 404 mà không tốn lượt gọi DNSE.

DNSE chỉ thêm nến ngày của một phiên sau khi phiên kết thúc. Trong phiên, phiên hôm nay (mở cửa, cao, thấp, khối lượng, giá khớp) lấy từ lệnh khớp lô chẵn mới nhất.

### `GET /stock/{mã}`

Phiên mới nhất, phiên trước, giá hiện tại, tham chiếu/trần/sàn. `?recent=N` thì trả như `/recent?days=N`.

```json
{
  "symbol": "PDR",
  "name": "PHÁT ĐẠT",
  "fullName": "CTCP Phát triển Bất động sản Phát Đạt",
  "nameEn": "Phat Dat Real Estate Development Corporation",
  "exchange": "HOSE",
  "currentPrice": 11.95,
  "referencePrice": 11.6,
  "upperPrice": 12.4,
  "lowerPrice": 10.8,
  "change": 0.35,
  "changePercent": 3.02,
  "todayOpen": 11.75,
  "todayHigh": 11.95,
  "todayLow": 11.7,
  "todayVolume": 3939000,
  "todayDate": "2026-11-10",
  "previousClose": 11.6,
  "previousVolume": 5237000,
  "previousDate": "2026-11-09",
  "lastUpdated": "2026-11-10T11:04:43.950598",
  "data": {
    "today": {
      "date": "2026-11-10", "open": 11.75, "close": 11.95, "high": 11.95, "low": 11.7,
      "volume": 3939000, "current_price": 11.95, "reference_price": 11.6,
      "ceiling": 12.4, "floor": 10.8, "is_today": true
    },
    "previous": { "date": "2026-11-09", "close": 11.6, "volume": 5237000 }
  },
  "marketOpen": true,
  "stale": false,
  "timestamp": "2026-11-10T11:04:56.191568"
}
```

| Trường | Ý nghĩa |
|---|---|
| `name` | Tên ngắn nếu đặt trong `SHORT_NAMES`, không thì như `fullName` |
| `nameEn` | Tên tiếng Anh, chỉ có khi đặt `NAMES_FILE` (DNSE không có) |
| `currentPrice` | Giá khớp gần nhất trong phiên (≤ 10 phút trước), ngoài giờ là giá đóng cửa |
| `referencePrice` | Giá đóng cửa phiên trước |
| `upperPrice`, `lowerPrice` | Trần/sàn theo biên độ sàn: HOSE ±7%, HNX ±10%, UPCOM ±15%, làm tròn theo bước giá. Trần/sàn chính thức của sàn: xem `/quote` |
| `marketOpen` | Đang trong giờ giao dịch (thứ 2–6, 8:45–15:05) |
| `stale` | Dữ liệu cũ hơn 3 lần chu kỳ làm mới (DNSE đang lỗi), vẫn là bản tốt gần nhất |

### `GET /stock/{mã}/recent?days=7`

N phiên gần nhất, cũ trước mới sau, tối đa `MAX_RECENT` (30). Phiên cuối có thêm `current_price`.

```json
{
  "symbol": "PDR", "name": "PHÁT ĐẠT", "exchange": "HOSE", "days": 2, "actual_sessions": 2,
  "sessions": [
    { "date": "2026-11-09", "open": 11.75, "close": 11.6, "high": 11.9, "low": 11.45, "volume": 5237000,
      "reference_price": 11.75, "ceiling": 12.55, "floor": 10.95, "is_today": false },
    { "date": "2026-11-10", "open": 11.75, "close": 11.95, "high": 11.95, "low": 11.7, "volume": 3939000,
      "reference_price": 11.6, "ceiling": 12.4, "floor": 10.8, "is_today": true, "current_price": 11.95 }
  ],
  "lastUpdated": "2026-11-10T11:04:43.950598",
  "timestamp": "2026-11-10T11:04:56.232395"
}
```

### `GET /stocks?symbols=PDR,VNM`

Tối đa `MAX_BATCH` (10) mã. Mỗi mã như `/stock/{mã}`, mã lỗi nằm trong `errors`:

```json
{
  "data": { "PDR": { "symbol": "PDR", "currentPrice": 11.95, "...": "..." } },
  "errors": { "XXXX": { "status": 404, "message": "Không tìm thấy mã XXXX" } },
  "timestamp": "2026-11-10T11:04:56.272173"
}
```

### `GET /stock/{mã}/history`

Nến OHLCV, cũ trước mới sau.

| Tham số | Mô tả |
|---|---|
| `interval` | `1m` `5m` `15m` `30m` `1H` `1D` (mặc định) `1W` |
| `start`, `end` | Khoảng ngày. Không có `start` thì lấy `limit` nến mới nhất |
| `limit` | Số nến mới nhất, 1–1000 (mặc định 100 khi không có `start`) |

Nến ngày (`1D`, `1W`) có `time` là ngày, nến trong ngày là giờ đầy đủ. Nến ngày của phiên đang chạy chưa có (xem trên).

```json
{
  "symbol": "PDR", "interval": "1D", "count": 2,
  "data": [
    { "time": "2026-11-06", "open": 11.3, "high": 11.9, "low": 11.25, "close": 11.75, "volume": 7325400 },
    { "time": "2026-11-09", "open": 11.75, "high": 11.9, "low": 11.45, "close": 11.6, "volume": 5237000 }
  ]
}
```

### `GET /stock/{mã}/day-range?start_date=&end_date=`

Các phiên đã kết thúc trong khoảng ngày, kèm `reference_price`, `ceiling`, `floor` tính như `/recent`.

```json
{
  "symbol": "PDR", "start_date": "2026-11-06", "end_date": "2026-11-09", "total_sessions": 2,
  "sessions": [
    { "date": "2026-11-06", "open": 11.3, "high": 11.9, "low": 11.25, "close": 11.75, "volume": 7325400,
      "reference_price": 11.55, "ceiling": 12.35, "floor": 10.75 }
  ],
  "timestamp": "2026-11-10T11:04:56.622585"
}
```

## Bảng giá và khối ngoại

### `GET /stock/{mã}/quote` · `GET /quotes?symbols=PDR,VNM`

Tham chiếu/trần/sàn **chính thức** của sàn trong ngày và 3 bước giá mua/bán tốt nhất (lô chẵn). `/quotes` tối đa 10 mã. Cache 15 giây.

```json
{
  "symbol": "PDR", "exchange": "HOSE", "trading_date": "2026-11-10",
  "reference_price": 11.6, "ceiling_price": 12.4, "floor_price": 10.8, "status": "NO_HALT",
  "bid": [ { "price": 11.9, "volume": 83000 }, { "price": 11.85, "volume": 142900 }, { "price": 11.8, "volume": 34500 } ],
  "ask": [ { "price": 11.95, "volume": 136700 }, { "price": 12, "volume": 515300 }, { "price": 12.05, "volume": 87900 } ],
  "time": "2026-11-10T11:03:31"
}
```

### `GET /stock/{mã}/foreign-flow?start=&end=`

Khối ngoại mua/bán từng ngày. Mặc định 10 ngày gần nhất, tối đa 31 ngày (mỗi ngày làm việc tốn 1 lượt gọi DNSE). `room` = khối lượng nhà đầu tư nước ngoài còn được mua.

```json
{
  "symbol": "PDR", "count": 1,
  "data": [
    { "date": "2026-11-10", "buy_volume": 690000, "sell_volume": 260500, "net_volume": 429500,
      "buy_value": 8148800000, "sell_value": 3074775000, "net_value": 5074025000, "room": 498904689 }
  ]
}
```

## Chỉ số và danh mục

### `GET /index/{chỉ số}/history`

Như `/stock/{mã}/history`, cho `VNINDEX`, `VN30`, `VN100`, `HNXINDEX` (hoặc `HNX`), `HNX30`, `UPCOMINDEX` (hoặc `UPCOM`)...

```json
{ "symbol": "VN30", "interval": "1D", "count": 1,
  "data": [ { "time": "2026-11-09", "open": 1849.98, "high": 1849.98, "low": 1817.66, "close": 1830.13, "volume": 251037248 } ] }
```

### `GET /symbols`

Mã cổ phiếu, chứng chỉ quỹ ETF và quỹ đóng đang niêm yết trên HOSE, HNX, UPCOM. Làm mới mỗi ngày.

```json
{ "count": 1541, "data": [ { "symbol": "AAA", "name": "CTCP Nhựa An Phát Xanh", "nameEn": null, "exchange": "HOSE", "type": "stock" } ] }
```

## Hệ thống

- `GET /health`: `status`, `uptimeSeconds`, `marketOpen`, `cachedSymbols`, `listedSymbols`, `upstreamCallsLastMinute`, `upstreamLimitPerMinute`, `priorityAgeSeconds` (tuổi dữ liệu của mã ưu tiên đầu tiên).
- `GET /status`: đã có khoá chưa (không in khoá), phiên bản API DNSE, hạn mức DNSE còn lại theo từng endpoint (`dnseLimits`, từ header `X-RateLimit-*` gần nhất).

## Mã lỗi

Lỗi có dạng `{"detail": "..."}`. Lỗi từ DNSE có thêm `hint` gợi ý cách xử lý.

| Mã | Khi nào |
|---|---|
| 400 | Tham số sai (mã chứa ký tự lạ, ngày sai định dạng, quá nhiều mã) |
| 404 | Mã không niêm yết, hoặc không có dữ liệu trong khoảng đã hỏi |
| 422 | Tham số không hợp lệ (ví dụ `interval=1M`) |
| 429 | Chạm trần lượt gọi mỗi phút của API (`Retry-After: 15`), hoặc DNSE báo vượt hạn mức giờ/ngày |
| 502 | Lần đầu hỏi một mã mà DNSE lỗi |
| 503 | Chưa có khoá, khoá bị từ chối, DNSE không phản hồi, hoặc mã mới đang được tải (`Retry-After`) |

## Cache và hạn mức

- Mỗi lần làm mới một mã tốn 2 lượt gọi DNSE (nến ngày + lệnh khớp mới nhất). Danh mục mã tốn khoảng 25 lượt mỗi ngày.
- `BUDGET_PER_MINUTE` (mặc định 60) là trần cho cả API, `BUDGET_RESERVED_FOR_PRIORITY` lượt giữ riêng cho mã ưu tiên. Hạn mức của DNSE rộng hơn nhiều (ví dụ nến 50.000 lượt/giờ), xem [Rate Limits](https://developers.dnse.com.vn/docs/guide/ratelimits/).
- DNSE lỗi, trả rỗng hay trả dữ liệu cũ hơn đều không thay bản đang giữ. DNSE báo vượt hạn mức thì 120 giây sau mới thử lại mã đó.
