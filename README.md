# Vietnam Stock API

[![Tests](https://github.com/tran-minh-khoi/viet-nam-stock/actions/workflows/test.yml/badge.svg)](https://github.com/tran-minh-khoi/viet-nam-stock/actions/workflows/test.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

API chứng khoán Việt Nam **chạy trên máy của bạn**: giá cổ phiếu, chỉ số VNINDEX/VN30, bảng giá, thông tin doanh nghiệp... trả về dạng JSON để dùng cho web, app, bot, Google Sheets hay script phân tích.

Xây trên thư viện [vnstock](https://vnstocks.com). Một lệnh để chạy, có trang thử API ngay trên trình duyệt.

Đây là **dự án mã nguồn mở phi lợi nhuận**, làm vì cộng đồng nhà đầu tư và lập trình viên Việt Nam. Không bán gì, không quảng cáo. Code của project không thu thập dữ liệu của bạn. Riêng vnstock có gửi thống kê sử dụng ẩn danh, tắt được bằng `VNSTOCK_TELEMETRY=0` trong `.env`.

> 🇬🇧 *A self-hosted REST API for Vietnamese stock market data, built on vnstock. Run `docker compose up -d`, then open http://localhost:8000/docs. Docs are in Vietnamese; endpoint reference: [docs/API.md](docs/API.md).*

---

## Mục lục

- [Có gì trong này](#có-gì-trong-này)
- [Chạy thử trong 5 phút](#chạy-thử-trong-5-phút)
- [Dùng API](#dùng-api)
- [Tài khoản vnstock và hạn mức](#tài-khoản-vnstock-và-hạn-mức)
- [Cấu hình](#cấu-hình)
- [Câu hỏi thường gặp](#câu-hỏi-thường-gặp)
- [Lưu ý về giấy phép](#lưu-ý-về-giấy-phép)
- [Đóng góp](#đóng-góp)

## Có gì trong này

| Nhóm | Bạn lấy được | Tài khoản Khách (không cần đăng ký) |
|---|---|:---:|
| Cổ phiếu | Phiên hôm nay, N phiên gần nhất, khoảng ngày, nến 1 phút → 1 tháng | ✅ |
| Bảng giá | Giá tham chiếu/trần/sàn, 3 bước giá mua/bán, nhiều mã một lúc | ✅ |
| Doanh nghiệp | Tên, ngành, giới thiệu, ngày niêm yết, số cổ phiếu | ✅ |
| Chỉ số | VNINDEX, VN30, HNXINDEX...: lịch sử giá, danh sách mã thành phần | ✅ |
| Danh mục | Toàn bộ mã niêm yết, danh sách chỉ số, mã theo nhóm (VN30, VN100...) | ✅ |
| Tài chính | Báo cáo KQKD, cân đối kế toán, lưu chuyển tiền tệ, chỉ số tài chính | 🔑 |
| Giao dịch | Lệnh khớp trong phiên, khối ngoại | 🔑 |
| Doanh nghiệp (mở rộng) | Cổ đông, ban lãnh đạo, công ty con, sự kiện | 🔑 |
| Vĩ mô | GDP, CPI, FDI, xuất nhập khẩu, tỷ giá, lãi suất | 🔑 |

🔑 = cần API key vnstock có cấp phù hợp. Chưa có thì API trả lỗi 403 kèm lý do, không bị treo hay sập. Xem [tài khoản vnstock](docs/vnstock-account.md).

Ngoài ra:
- **Tiết kiệm lượt gọi:** API tự cache. 100 người cùng xem VCB trong 15 giây vẫn chỉ tốn 1 lượt gọi vnstock.
- **Báo lỗi dễ hiểu:** hết lượt thì trả 429, chưa đủ quyền thì 403, sai mã thì 404, kèm gợi ý cách xử lý bằng tiếng Việt.
- **Trang thử API** tại `/docs`: bấm và xem kết quả, không cần viết code.

## Chạy thử trong 5 phút

Bạn chỉ cần **Docker**. Không cần cài Python hay biết lập trình.

### Bước 1: Cài Docker Desktop

Tải tại [docker.com/products/docker-desktop](https://www.docker.com/products/docker-desktop/), cài như phần mềm bình thường, rồi **mở Docker Desktop lên** (đợi biểu tượng cá voi báo *running*).

- **Windows:** nếu được hỏi cài WSL 2 thì chọn đồng ý, rồi khởi động lại máy.
- **Mac:** chọn đúng bản *Apple Silicon* (M1/M2/M3/M4) hoặc *Intel*.

### Bước 2: Tải code về

**Cách dễ:** trên trang GitHub của project, bấm nút xanh **Code → Download ZIP**, rồi giải nén.

**Nếu bạn có git:**
```bash
git clone https://github.com/tran-minh-khoi/viet-nam-stock.git
```

### Bước 3: Mở Terminal tại thư mục vừa tải

- **Mac:** chuột phải vào thư mục `viet-nam-stock` → *Services* → **New Terminal at Folder**. Hoặc mở Terminal, gõ `cd ` (có dấu cách) rồi kéo thả thư mục vào và nhấn Enter.
- **Windows:** mở thư mục, bấm vào thanh địa chỉ, gõ `powershell`, nhấn Enter.

### Bước 4: Chạy

```bash
docker compose up -d
```

Lần đầu mất khoảng 1–2 phút để tải và cài. Thấy `Container viet-nam-stock Started` là xong.

### Bước 5: Mở trình duyệt

👉 **http://localhost:8000/docs**

Chọn một API, ví dụ `GET /stock/{symbol}`, bấm **Try it out**, gõ `VCB`, bấm **Execute**. Kết quả hiện ngay bên dưới.

Hoặc mở thẳng: http://localhost:8000/stock/VCB

### Các lệnh hay dùng

| Muốn | Gõ lệnh |
|---|---|
| Tắt | `docker compose down` |
| Bật lại | `docker compose up -d` |
| Xem log (khi có lỗi) | `docker compose logs -f` (nhấn `Ctrl+C` để thoát) |
| Cập nhật bản mới | `git pull` rồi `docker compose up -d --build` |

API tự bật lại khi bạn khởi động lại máy, miễn là Docker Desktop đang chạy.

## Dùng API

Danh sách chính, đầy đủ tham số và ví dụ kết quả ở [docs/API.md](docs/API.md):

| API | Dùng để |
|---|---|
| `GET /stock/VCB` | Phiên mới nhất, phiên trước, giá trần/sàn |
| `GET /stock/VCB/recent?days=10` | 10 phiên gần nhất |
| `GET /stock/VCB/day-range?start_date=2026-01-01&end_date=2026-01-31` | Các phiên trong khoảng ngày |
| `GET /stock/VCB/history?interval=1H&limit=50` | Nến 1m, 5m, 15m, 30m, 1H, 1D, 1W, 1M |
| `GET /stock/VCB/quote` | Bảng giá: tham chiếu, trần, sàn, dư mua/bán |
| `GET /quotes?symbols=VCB,FPT,HPG` | Bảng giá nhiều mã, chỉ tốn **1 lượt gọi** |
| `GET /stock/VCB/company` | Thông tin doanh nghiệp |
| `GET /index/VNINDEX/history` | Lịch sử chỉ số |
| `GET /index/VN30/members` | Mã thuộc VN30 |
| `GET /symbols`, `GET /indices`, `GET /groups/VN30/symbols` | Danh mục mã và chỉ số |
| `GET /status` | Tài khoản vnstock đang ở cấp nào, đã dùng bao nhiêu lượt |

> **Đơn vị giá:** `/stock/*`, `/history`, `/index/*` tính bằng **nghìn đồng** (57.2 = 57.200đ). `/quote`, `/quotes` tính bằng **đồng**.

### Ví dụ gọi API từ code

**JavaScript (web):**
```js
const res = await fetch("http://localhost:8000/stock/VCB");
const vcb = await res.json();
console.log(vcb.currentPrice, vcb.upperPrice, vcb.lowerPrice);
```

**Python:**
```python
import requests
vcb = requests.get("http://localhost:8000/stock/VCB").json()
print(vcb["currentPrice"])
```

**Terminal:**
```bash
curl http://localhost:8000/quotes?symbols=VCB,FPT
```

## Tài khoản vnstock và hạn mức

Không đăng ký gì, API chạy với **tài khoản Khách** của vnstock:

| | Tài khoản Khách |
|---|---|
| Lượt gọi | 10/phút · 100/giờ · 300/ngày · 1.000/tháng |
| Dữ liệu | Các nhóm có ✅ ở bảng trên |
| Lịch sử giá ngày | 365 ngày gần nhất |

Nhờ cache, 1.000 lượt/tháng đủ cho một danh mục theo dõi nhỏ. Muốn nhiều hơn thì **đăng ký miễn phí tại [vnstocks.com](https://vnstocks.com)**, lấy API key rồi dán vào file `.env`:

```bash
cp .env.example .env        # Windows: copy .env.example .env
# mở .env, điền: VNSTOCK_API_KEY=key_cua_ban
docker compose up -d
```

Kiểm tra bằng http://localhost:8000/status. Chi tiết: [docs/vnstock-account.md](docs/vnstock-account.md).

> ⚠️ Mỗi bản vnstock chỉ dùng được khoảng 1 năm (bản 5.2.1 hết hạn 27/10/2027). Hết hạn thì cập nhật project bằng `git pull` và `docker compose up -d --build`.

## Cấu hình

Tất cả đều không bắt buộc. Copy `.env.example` thành `.env` rồi sửa:

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `VNSTOCK_API_KEY` | *(trống)* | API key vnstock. Trống = tài khoản Khách |
| `PORT` | `8000` | Cổng trên máy bạn (Docker) |
| `DATA_SOURCE` | `KBS` | Nguồn giá: `KBS` hoặc `VCI` |
| `CORS_ORIGINS` | `*` | Các website được gọi API từ trình duyệt, cách nhau bằng dấu phẩy |
| `CACHE_TTL` | `15` | Số giây cache giá trong phiên |
| `CACHE_TTL_HISTORY` | `300` | Số giây cache lịch sử giá |
| `CACHE_TTL_REFERENCE` | `86400` | Số giây cache thông tin doanh nghiệp, danh mục, báo cáo tài chính |
| `REDIS_URL` | *(trống)* | Redis để cache không mất khi restart (không bắt buộc) |
| `FAST_SYMBOLS` | *(trống)* | Các mã lấy giá khớp lệnh mới nhất (cần cấp có quyền "trades") |
| `LOG_LEVEL` | `INFO` | Mức log |

Sửa `.env` xong thì chạy lại `docker compose up -d`.

Muốn chạy trên VPS, chạy không dùng Docker (PM2) hoặc gắn tên miền và HTTPS: xem [docs/deploy.md](docs/deploy.md).

## Câu hỏi thường gặp

<details>
<summary><b>Báo lỗi <code>Cannot connect to the Docker daemon</code></b></summary>

Docker Desktop chưa mở. Mở Docker Desktop, đợi nó báo *running*, rồi chạy lại lệnh.
</details>

<details>
<summary><b>Báo lỗi <code>port is already allocated</code></b></summary>

Cổng 8000 đang bị phần mềm khác dùng. Tạo file `.env` có dòng `PORT=8080`, chạy lại `docker compose up -d`, rồi mở http://localhost:8080/docs.
</details>

<details>
<summary><b>Nhận lỗi 429 "Đã dùng hết hạn mức"</b></summary>

Bạn đã hết lượt gọi của vnstock. Hạn mức theo phút sẽ hồi sau 1 phút. Để đỡ bị:
- Dùng `/quotes?symbols=A,B,C` thay vì gọi từng mã.
- Tăng `CACHE_TTL` (ví dụ 60).
- Đăng ký API key miễn phí để có hạn mức cao hơn.
</details>

<details>
<summary><b>Nhận lỗi 403 "không thuộc quyền của cấp Khách"</b></summary>

Dữ liệu này cần tài khoản vnstock cấp cao hơn. Xem [docs/vnstock-account.md](docs/vnstock-account.md).
</details>

<details>
<summary><b>Ngoài giờ giao dịch, bảng giá toàn <code>null</code></b></summary>

Bình thường. Ngoài giờ giao dịch, nguồn chỉ trả giá tham chiếu, trần và sàn của phiên kế tiếp. Muốn xem giá đóng cửa gần nhất thì dùng `/stock/{symbol}`.
</details>

<details>
<summary><b>Làm sao cho máy khác hoặc điện thoại trong cùng mạng Wi-Fi gọi được?</b></summary>

Dùng IP của máy đang chạy Docker, ví dụ `http://192.168.1.10:8000`. API này dành cho bạn dùng cá nhân. Đừng mở công khai ra Internet cho người lạ dùng, xem [lưu ý về giấy phép](#lưu-ý-về-giấy-phép).
</details>

## Lưu ý về giấy phép

- **Code của project này:** giấy phép [MIT](LICENSE). Bạn được tự do dùng, sửa và chia sẻ.
- **vnstock:** **không** nằm trong repo này. Khi bạn build Docker hoặc `pip install`, máy của bạn tự tải vnstock theo [giấy phép riêng của vnstock](https://vnstocks.com/onboard/giay-phep-su-dung). Bản Cộng đồng miễn phí chỉ dành cho **cá nhân, học tập, nghiên cứu**. Theo giấy phép đó, hai việc sau **cần thoả thuận bằng văn bản với tác giả vnstock**, kể cả khi bạn không thu tiền:
  - mở API này công khai để **người khác** lấy dữ liệu;
  - đăng Docker image có sẵn vnstock lên Docker Hub hoặc kho image khác.

  Vì vậy project chỉ hướng dẫn **mỗi người tự chạy trên máy mình, bằng tài khoản của mình**.
- **Dữ liệu** thuộc về các nguồn (công ty chứng khoán, sở giao dịch). Không bán hay phân phối lại dữ liệu.
- **Không phải tư vấn đầu tư.** Dữ liệu có thể trễ hoặc sai. Bạn tự chịu trách nhiệm với quyết định của mình.

## Đóng góp

Mọi đóng góp đều được hoan nghênh: báo lỗi, đề xuất tính năng, sửa tài liệu, gửi code. Có câu hỏi hoặc muốn khoe thứ bạn làm từ API này? Vào [Discussions](https://github.com/tran-minh-khoi/viet-nam-stock/discussions). Xem [CONTRIBUTING.md](CONTRIBUTING.md) và [Quy tắc ứng xử](CODE_OF_CONDUCT.md). Phát hiện lỗ hổng bảo mật thì xem [SECURITY.md](SECURITY.md).

Lịch sử thay đổi: [CHANGELOG.md](CHANGELOG.md).

## Tác giả

Tran Minh Khoi · [tranminhkhoi.dev](https://tranminhkhoi.dev) · contact@tranminhkhoi.dev

Cảm ơn tác giả [vnstock](https://vnstocks.com) (Thịnh Vũ) đã xây dựng và duy trì thư viện.
