# Vietnam Stock API

[![Tests](https://github.com/tran-minh-khoi/viet-nam-stock/actions/workflows/test.yml/badge.svg)](https://github.com/tran-minh-khoi/viet-nam-stock/actions/workflows/test.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

API chứng khoán Việt Nam **chạy trên máy của bạn**: giá cổ phiếu, chỉ số VNINDEX/VN30, bảng giá, khối ngoại, báo cáo tài chính... trả về dạng JSON để dùng cho web, app, bot, Google Sheets hay script phân tích.

Xây trên [vnstock thế hệ 6](https://vnstocks.com/docs/vnstock/v6): bạn chọn nguồn dữ liệu (DNSE, SSI, TCBS, FHSC), dùng **khoá API của chính bạn** do nguồn đó cấp, và nhận dữ liệu đã chuẩn hoá. Có trang thử API ngay trên trình duyệt.

Đây là **dự án mã nguồn mở phi lợi nhuận**, làm vì cộng đồng nhà đầu tư và lập trình viên Việt Nam. Không bán gì, không quảng cáo. Code của project không thu thập dữ liệu của bạn. Riêng vnstock có gửi thống kê sử dụng ẩn danh, tắt được bằng `VNSTOCK_TELEMETRY=0` trong `.env`.

> 🇬🇧 *A self-hosted REST API for Vietnamese stock market data, built on vnstock 6. Get an Open API key from a broker (DNSE is enough to start), put it in `.env`, run `docker compose up -d`, open http://localhost:8000/docs. Docs are in Vietnamese; endpoint reference: [docs/API.md](docs/API.md).*

---

## Mục lục

- [Có gì trong này](#có-gì-trong-này)
- [Chạy thử](#chạy-thử)
- [Dùng API](#dùng-api)
- [Nguồn dữ liệu và khoá](#nguồn-dữ-liệu-và-khoá)
- [Cấu hình](#cấu-hình)
- [Câu hỏi thường gặp](#câu-hỏi-thường-gặp)
- [Lưu ý về giấy phép](#lưu-ý-về-giấy-phép)
- [Đóng góp](#đóng-góp)

## Có gì trong này

| Nhóm | Bạn lấy được | Nguồn cần khoá |
|---|---|---|
| Cổ phiếu | Phiên hôm nay + giá đang khớp, N phiên gần nhất, khoảng ngày, nến 1 phút → 1 tháng | **DNSE** |
| Bảng giá | Giá tham chiếu/trần/sàn chính thức, 3 bước giá mua/bán | **DNSE** (hoặc FHSC, TCBS) |
| Giao dịch | Lệnh khớp trong phiên, khối ngoại theo ngày | **DNSE** |
| Chỉ số | VNINDEX, VN30, HNXINDEX...: lịch sử giá | **DNSE** |
| Danh mục | Toàn bộ mã niêm yết | **DNSE** |
| Thành phần chỉ số, nhóm mã | Mã thuộc VN30, VN100, HNX30... và danh sách chỉ số | SSI |
| Doanh nghiệp | Hồ sơ, cổ đông lớn, cơ cấu sở hữu, giao dịch nội bộ, sự kiện | FHSC |
| Tài chính | Kết quả kinh doanh, cân đối kế toán, lưu chuyển tiền tệ | FHSC |

**Chỉ cần một khoá DNSE là dùng được phần lớn API.** Nhóm nào chưa có khoá thì trả lỗi 403 kèm tên biến cần đặt, không treo hay sập.

Ngoài ra:
- **Không bao giờ bắt người dùng chờ nguồn:** `/stock/*` giữ dữ liệu từng mã trong bộ nhớ, hết hạn vẫn trả ngay rồi làm mới ở nền. Mã ưu tiên (`PRIORITY_SYMBOLS`) được làm mới định kỳ kể cả khi không ai gọi.
- **Luôn có bản tốt gần nhất:** nguồn chậm, lỗi, trả rỗng, trả dữ liệu cũ hơn hay báo vượt hạn mức đều không làm mất dữ liệu đang có; vượt hạn mức thì tự giãn thời gian thử lại. Bật `SNAPSHOT_FILE` để giữ cả qua lần khởi động lại.
- **Bảo vệ khoá của bạn:** tự đặt trần số lượt gọi nguồn mỗi phút (`BUDGET_PER_MINUTE`). 100 người cùng xem VCB vẫn chỉ tốn 1 lượt gọi.
- **Báo lỗi dễ hiểu:** thiếu khoá 403, nguồn giới hạn tốc độ 429, sai mã 404, nguồn lỗi 503, kèm `hint` tiếng Việt.
- **Trang thử API** tại `/docs`: bấm và xem kết quả, không cần viết code.

## Chạy thử

Bạn cần **Docker** và **một khoá Open API của DNSE**. Không cần cài Python hay biết lập trình.

### Bước 1: Lấy khoá DNSE

1. Mở tài khoản chứng khoán DNSE nếu chưa có (miễn phí, làm online).
2. Đăng nhập DNSE, vào phần quản lý **Open API**, tạo **API Key** và **API Secret**.
3. **Lưu Secret ngay**: DNSE chỉ hiện Secret một lần.

Chi tiết từng nguồn và cách kiểm tra khoá: [docs/data-sources.md](docs/data-sources.md).

### Bước 2: Cài Docker Desktop

Tải tại [docker.com/products/docker-desktop](https://www.docker.com/products/docker-desktop/), cài như phần mềm bình thường, rồi **mở Docker Desktop lên** (đợi biểu tượng cá voi báo *running*).

- **Windows:** nếu được hỏi cài WSL 2 thì chọn đồng ý, rồi khởi động lại máy.
- **Mac:** chọn đúng bản *Apple Silicon* (M1/M2/M3/M4) hoặc *Intel*.

### Bước 3: Tải code về và điền khoá

**Cách dễ:** trên trang GitHub của project, bấm nút xanh **Code → Download ZIP**, rồi giải nén. Hoặc nếu có git:

```bash
git clone https://github.com/tran-minh-khoi/viet-nam-stock.git
```

Trong thư mục vừa tải, copy file `.env.example` thành `.env`, mở bằng Notepad hoặc TextEdit và điền:

```
DNSE_API_KEY=key_cua_ban
DNSE_API_SECRET=secret_cua_ban
```

**Giữ file `.env` bí mật.** File này đã nằm trong `.gitignore`, đừng commit hay gửi cho ai.

### Bước 4: Chạy

Mở Terminal tại thư mục project:
- **Mac:** chuột phải vào thư mục `viet-nam-stock` → *Services* → **New Terminal at Folder**.
- **Windows:** mở thư mục, bấm vào thanh địa chỉ, gõ `powershell`, nhấn Enter.

```bash
docker compose up -d
```

Lần đầu mất khoảng 1–2 phút để tải và cài. Thấy `Container viet-nam-stock Started` là xong.

### Bước 5: Mở trình duyệt

👉 **http://localhost:8000/docs**

Chọn một API, ví dụ `GET /stock/{symbol}`, bấm **Try it out**, gõ `VCB`, bấm **Execute**. Hoặc mở thẳng: http://localhost:8000/stock/VCB

Kiểm tra khoá: http://localhost:8000/status, mục `"keys"` phải có `"dnse": true`.

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
| `GET /stock/VCB` | Phiên mới nhất, phiên trước, giá đang khớp, giá trần/sàn |
| `GET /stock/VCB/recent?days=10` | 10 phiên gần nhất (tối đa 30) |
| `GET /stocks?symbols=VCB,FPT,HPG` | Như `/stock/VCB` cho nhiều mã một lượt (tối đa 10) |
| `GET /stock/VCB/day-range?start_date=2026-01-01&end_date=2026-01-31` | Các phiên trong khoảng ngày |
| `GET /stock/VCB/history?interval=1H&limit=50` | Nến 1m, 5m, 15m, 30m, 1H, 1D, 1W, 1M |
| `GET /stock/VCB/quote` | Bảng giá: tham chiếu, trần, sàn, dư mua/bán |
| `GET /stock/VCB/trades` | Lệnh khớp trong phiên |
| `GET /stock/VCB/foreign-flow` | Khối ngoại mua/bán theo ngày |
| `GET /index/VNINDEX/history` | Lịch sử chỉ số |
| `GET /symbols` | Toàn bộ mã niêm yết |
| `GET /index/VN30/members`, `GET /groups/VN30/symbols`, `GET /indices` | Thành phần chỉ số, nhóm mã (cần SSI) |
| `GET /stock/VCB/company`, `/company/shareholders`, `/financials/income_statement` | Doanh nghiệp, tài chính (cần FHSC) |
| `GET /status` | Bản vnstock, hạn dùng, nguồn nào đã có khoá |

> **Đơn vị giá:** mọi giá tính bằng **nghìn đồng** (57.2 = 57.200đ). Khối lượng tính bằng cổ phiếu.

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
curl "http://localhost:8000/stocks?symbols=VCB,FPT"
```

## Nguồn dữ liệu và khoá

vnstock thế hệ 6 không còn nguồn "mặc định" dùng chung: dữ liệu đi thẳng từ máy bạn tới nguồn bạn chọn, bằng khoá của bạn. vnstock lo phần kết nối và chuẩn hoá cột.

| Nguồn | Khoá | Project dùng cho |
|---|---|---|
| **DNSE** | `DNSE_API_KEY`, `DNSE_API_SECRET` | Giá, lệnh khớp, bảng giá, chỉ số, danh mục, khối ngoại (`DATA_SOURCE`, `QUOTE_SOURCE`) |
| SSI | `SSI_API_KEY`, `SSI_API_SECRET` | Thành phần chỉ số, nhóm mã, danh sách chỉ số (`INDEX_SOURCE`) |
| FHSC | `FHSC_API_KEY` | Doanh nghiệp, báo cáo tài chính (`COMPANY_SOURCE`); bảng giá đầy đủ (`QUOTE_SOURCE=fhsc`) |
| TCBS | `TCBS_API_KEY` | Bảng giá (`QUOTE_SOURCE=tcbs`). Phiên TCBS cần Smart OTP và hết sau 8 giờ, không hợp chạy server |

Mỗi nguồn có hạn mức và điều khoản riêng, do nguồn quyết định. Chi tiết: [docs/data-sources.md](docs/data-sources.md).

> ⚠️ **vnstock 6 đang ở bản thử (rc) và mỗi bản chỉ dùng được một thời gian** (6.0.0rc5 dùng được đến hết 09/12/2026, xem `releaseExpiresAt` trong `/status`). Gần hạn thì cập nhật project bằng `git pull` và `docker compose up -d --build`.

## Cấu hình

Copy `.env.example` thành `.env` rồi sửa. Ngoài khoá nguồn, mọi dòng đều không bắt buộc:

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `DNSE_API_KEY`, `DNSE_API_SECRET` | *(trống)* | Khoá DNSE. Thiếu thì phần lớn API không có dữ liệu |
| `DATA_SOURCE` | `dnse` | Nguồn giá, lệnh khớp, danh mục, chỉ số (`dnse`, `ssi`, `tcbs`, `fhsc`) |
| `QUOTE_SOURCE` | `dnse` | Nguồn bảng giá (`dnse`, `fhsc`, `tcbs`) |
| `COMPANY_SOURCE` | `fhsc` | Nguồn doanh nghiệp, tài chính |
| `INDEX_SOURCE` | `ssi` | Nguồn thành phần chỉ số, nhóm mã |
| `BUDGET_PER_MINUTE` | `30` | Trần số lượt gọi nguồn mỗi phút của cả API |
| `PRIORITY_SYMBOLS` | *(trống)* | Mã luôn được làm mới ở nền, ví dụ `VCB,FPT` |
| `SHORT_NAMES` | *(trống)* | Tên ngắn thay cho `name`, ví dụ `"VCB=Vietcombank;FPT=FPT"` |
| `NAMES_FILE` | *(trống)* | File JSON tên công ty dùng thay tên của nguồn (giữ tên không đổi khi đổi nguồn) |
| `SNAPSHOT_FILE` | *(trống)* | File lưu dữ liệu tốt gần nhất, ví dụ `state/snapshot.json`: khởi động lại vẫn trả ngay kể cả khi nguồn đang lỗi |
| `PORT` | `8000` | Cổng trên máy bạn (Docker) |
| `CORS_ORIGINS` | `*` | Các website được gọi API từ trình duyệt, cách nhau bằng dấu phẩy |
| `ENABLE_DOCS` | `true` | Bật trang `/docs` |
| `CACHE_TTL`, `CACHE_TTL_HISTORY`, `CACHE_TTL_REFERENCE` | `15`, `300`, `86400` | Số giây cache của các API ngoài `/stock/*` |
| `REDIS_URL` | *(trống)* | Redis để cache không mất khi restart (không bắt buộc) |
| `LOG_LEVEL` | `INFO` | Mức log |

Sửa `.env` xong thì chạy lại `docker compose up -d`.

Muốn chạy trên VPS, chạy không dùng Docker (PM2) hoặc gắn tên miền và HTTPS: xem [docs/deploy.md](docs/deploy.md). Đang dùng bản 3.x (vnstock 5): xem [CHANGELOG.md](CHANGELOG.md) mục 4.0.0.

## Câu hỏi thường gặp

<details>
<summary><b>Mọi API đều trả 502 hoặc 403 "Chưa có khoá"</b></summary>

Chưa điền khoá DNSE, hoặc điền sai. Mở http://localhost:8000/status: `"keys": {"dnse": false}` nghĩa là API chưa đọc được khoá. Kiểm tra lại `.env` (không có dấu cách thừa) rồi chạy `docker compose up -d`. Log (`docker compose logs -f`) ghi rõ lý do.
</details>

<details>
<summary><b>Báo lỗi <code>Cannot connect to the Docker daemon</code></b></summary>

Docker Desktop chưa mở. Mở Docker Desktop, đợi nó báo *running*, rồi chạy lại lệnh.
</details>

<details>
<summary><b>Báo lỗi <code>port is already allocated</code></b></summary>

Cổng 8000 đang bị phần mềm khác dùng. Thêm dòng `PORT=8080` vào `.env`, chạy lại `docker compose up -d`, rồi mở http://localhost:8080/docs.
</details>

<details>
<summary><b>Nhận lỗi 503 "Hệ thống đang bận" hoặc 429</b></summary>

API đã chạm trần lượt gọi nguồn mỗi phút mà bạn đặt (`BUDGET_PER_MINUTE`), hoặc nguồn đang giới hạn tốc độ. Thử lại sau ít giây. Để đỡ bị: gọi `/stocks?symbols=A,B,C` thay vì từng mã, đặt các mã hay xem vào `PRIORITY_SYMBOLS`.
</details>

<details>
<summary><b>Ngoài giờ giao dịch, giá hiện tại bằng giá đóng cửa</b></summary>

Bình thường. Ngoài 8:45–15:05 các ngày làm việc, API không gọi lệnh khớp, `currentPrice` là giá đóng cửa của phiên gần nhất.
</details>

<details>
<summary><b>Làm sao cho máy khác hoặc điện thoại trong cùng mạng Wi-Fi gọi được?</b></summary>

Dùng IP của máy đang chạy Docker, ví dụ `http://192.168.1.10:8000`. Xem [lưu ý về giấy phép](#lưu-ý-về-giấy-phép) trước khi mở cho người khác dùng.
</details>

## Lưu ý về giấy phép

- **Code của project này:** giấy phép [MIT](LICENSE). Bạn được tự do dùng, sửa và chia sẻ.
- **vnstock:** **không** nằm trong repo này. Khi bạn build Docker hoặc `pip install`, máy của bạn tự tải vnstock theo [giấy phép riêng của vnstock](https://vnstocks.com/onboard/giay-phep-su-dung). Đọc kỹ giấy phép đó nếu bạn định mở API cho người khác dùng hoặc đăng Docker image có sẵn vnstock.
- **Dữ liệu** thuộc về các nguồn (công ty chứng khoán, sở giao dịch) và đi theo điều khoản của khoá bạn đăng ký. Quyền dùng vnstock và quyền lấy dữ liệu là hai thứ riêng. Không bán hay phân phối lại dữ liệu.
- **Không phải tư vấn đầu tư.** Dữ liệu có thể trễ hoặc sai. Bạn tự chịu trách nhiệm với quyết định của mình.

## Đóng góp

Mọi đóng góp đều được hoan nghênh: báo lỗi, đề xuất tính năng, sửa tài liệu, gửi code. Có câu hỏi hoặc muốn khoe thứ bạn làm từ API này? Vào [Discussions](https://github.com/tran-minh-khoi/viet-nam-stock/discussions). Xem [CONTRIBUTING.md](CONTRIBUTING.md) và [Quy tắc ứng xử](CODE_OF_CONDUCT.md). Phát hiện lỗ hổng bảo mật thì xem [SECURITY.md](SECURITY.md).

Lịch sử thay đổi: [CHANGELOG.md](CHANGELOG.md).

## Tác giả

Tran Minh Khoi · [tranminhkhoi.dev](https://tranminhkhoi.dev) · contact@tranminhkhoi.dev

Cảm ơn tác giả [vnstock](https://vnstocks.com) (Thịnh Vũ) đã xây dựng và duy trì thư viện.
