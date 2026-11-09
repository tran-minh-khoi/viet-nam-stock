# Changelog

Định dạng theo [Keep a Changelog](https://keepachangelog.com/vi/1.1.0/), đánh số phiên bản theo [SemVer](https://semver.org/lang/vi/).

## [4.1.0] - 2026-11-09

### Thêm
- `SNAPSHOT_FILE`: lưu dữ liệu tốt gần nhất của mọi mã đang giữ và danh mục mã xuống đĩa (ghi nguyên tử, tối đa 30 giây một lần, và khi tắt). Khởi động lại thì trả ngay bản đã lưu, kể cả khi nguồn đang lỗi. Docker mặc định lưu ở `/data/snapshot.json` trong volume.

### Sửa
- Nguồn trả rỗng cho một mã đang có dữ liệu không còn làm mã đó báo 404 suốt 1 giờ: coi là lỗi tạm thời, giữ bản cũ.
- Nguồn trả dữ liệu cũ hơn bản đang giữ (phiên mới nhất lùi lại) thì bỏ qua, giữ bản mới hơn.
- Nguồn báo vượt hạn mức (429, hết quota, không đủ quyền) thì đợi 120 giây mới thử lại thay vì 15 giây; người dùng vẫn nhận bản tốt gần nhất trong lúc đó.

## [4.0.0] - 2026-11-09

### Thay đổi lớn
- Chuyển sang **vnstock 6** (6.0.0rc5). vnstock 5 và các thế hệ trước ngừng hoạt động từ 10/11/2026.
- Không còn tài khoản Khách hay nguồn dùng chung: mỗi nguồn (DNSE, SSI, FHSC, TCBS) cần **khoá Open API do chính nguồn đó cấp**. Bỏ `VNSTOCK_API_KEY`; thêm `DNSE_API_KEY`, `DNSE_API_SECRET`, `SSI_API_KEY`, `SSI_API_SECRET`, `FHSC_API_KEY`. Xem [docs/data-sources.md](docs/data-sources.md).
- Chọn nguồn theo nhóm dữ liệu: `DATA_SOURCE` (mặc định `dnse`), `QUOTE_SOURCE` (`dnse`), `COMPANY_SOURCE` (`fhsc`), `INDEX_SOURCE` (`ssi`). Bỏ nguồn `KBS`, `VCI`.
- `/stock/{symbol}`, `/stock/{symbol}/recent`, `/stocks` chạy trên engine mới (`engine.py`): giữ dữ liệu từng mã trong bộ nhớ, hết hạn vẫn trả ngay rồi làm mới ở nền, mã ưu tiên tự làm mới, trần lượt gọi nguồn mỗi phút. Kết quả giữ đúng định dạng đang được app dùng thật, kiểm bằng `tests/test_contract.py`.
- `/stock/{symbol}` thêm `fullName`, `nameEn`, `change`, `changePercent`, `marketOpen`, `stale`; `currentPrice` lấy từ lệnh khớp mới nhất trong giờ giao dịch cho mọi mã. Giá trần/sàn tính theo sàn của mã (HOSE ±7%, HNX ±10%, UPCOM ±15%). `?recent` và `/recent?days` tối đa `MAX_RECENT` (30) phiên.
- **Mọi giá tính bằng nghìn đồng**, kể cả `/quote`, `/quotes`.
- Bỏ `FAST_SYMBOLS` (giờ mọi mã đều lấy giá khớp), thêm `PRIORITY_SYMBOLS`, `SHORT_NAMES`, `NAMES_FILE`, `BUDGET_PER_MINUTE`, `BUDGET_RESERVED_FOR_PRIORITY`, `MAX_RECENT`, `MAX_BATCH`, `ENABLE_DOCS`, `SERVICE_NAME`.
- `/health` trả trạng thái engine (`status: "ok"`, số mã đang giữ, lượt gọi trong phút...). `/status` trả bản vnstock, hạn dùng, nguồn nào đã có khoá.

### Thêm
- `GET /stocks?symbols=A,B,C`: như `/stock/{symbol}` cho tối đa 10 mã, mã lỗi nằm trong `errors`.
- `/stock/{symbol}/quote` với nguồn `dnse`: giá tham chiếu/trần/sàn chính thức của sở + 3 bước giá mua/bán.
- `/stock/{symbol}/company/{section}`: thêm `ownership`, `insider_trading`.
- `scripts/compare_live.py`: so từng trường giữa hai bản đang chạy, dùng khi chuyển đổi.

### Bỏ (vnstock 6 chưa có nguồn cho dữ liệu này)
- `/macro/*` (GDP, CPI, FDI, tỷ giá, lãi suất...).
- `/stock/{symbol}/company/officers`, `/company/subsidiaries`.
- `/stock/{symbol}/financials/ratio`.

## [3.0.0] - 2026-10-30

### Thay đổi lớn
- Chuyển sang **vnstock 5.2.1**. Bản 3.x đã bị gỡ khỏi PyPI và không cài được nữa. vnstock 5 cài từ index riêng của vnstocks, đã khai báo trong `requirements.txt`.
- Mặc định chạy với tài khoản Khách của vnstock (10 lượt/phút). Điền `VNSTOCK_API_KEY` để có hạn mức cao hơn.
- `exchange` lấy theo sàn thật của mã (HOSE/HNX/UPCOM), không còn luôn là `HOSE`.
- Bỏ `gunicorn`. Server chạy bằng `uvicorn` với 1 worker.

### Thêm
- Docker: `Dockerfile`, `docker-compose.yml`, healthcheck, chạy bằng user thường, volume giữ thông tin đăng nhập vnstock.
- API mới: `/stock/{symbol}/history` (nến 1m → 1M), `/stock/{symbol}/quote`, `/quotes`, `/stock/{symbol}/company`, `/index/{symbol}/history`, `/index/{symbol}/members`, `/indices`, `/symbols`, `/groups/{group}/symbols`, `/status`.
- API cho tài khoản có cấp phù hợp: báo cáo tài chính, cổ đông, ban lãnh đạo, công ty con, sự kiện, lệnh khớp, khối ngoại, vĩ mô.
- Báo lỗi rõ ràng: 403 khi chưa đủ quyền, 429 khi hết lượt, 404 khi sai mã, 503 khi nguồn lỗi, kèm `hint` tiếng Việt.
- Cache theo loại dữ liệu (`CACHE_TTL`, `CACHE_TTL_HISTORY`, `CACHE_TTL_REFERENCE`). Các request trùng nhau dùng chung một lượt gọi.
- Tài liệu: README cho người mới, `docs/API.md`, `docs/data-sources.md`, `docs/deploy.md`, CONTRIBUTING, SECURITY, CODE_OF_CONDUCT.

### Sửa
- `/stock/{symbol}` trước giờ mở cửa trả cùng một phiên cho cả `today` lẫn `previous`. Giờ `today` là phiên mới nhất, `previous` là phiên liền trước.
- `/stock/{symbol}/recent?days=N` đôi khi trả ít hơn N phiên do khoảng ngày quá ngắn.
- Ngày giờ trong kết quả giữ múi giờ Việt Nam, không còn bị lệch sang ngày hôm trước do đổi sang UTC.
- `FAST_SYMBOLS` cấu hình được qua biến môi trường, không còn gắn cứng `PDR`.

## [2.1.0]
- Bản dùng vnstock 3.5.1: `/stock/{symbol}`, `/recent`, `/day-range`, `/health`.
