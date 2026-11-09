"""Vietnam Stock API: a small self-hosted REST API over vnstock 6."""
import asyncio
import json
import logging
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Callable, Dict, Literal, Optional

import re

import pandas as pd
from fastapi import FastAPI, HTTPException, Path, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import engine
import sources
from config import settings

try:
    import redis
except ImportError:  # pragma: no cover
    redis = None

__version__ = "4.0.0"
SERVICE_NAME = os.getenv("SERVICE_NAME", "Vietnam Stock API")

logging.basicConfig(level=settings.LOG_LEVEL, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("viet-nam-stock")
# vnstock 6 talks to sources through httpx, which logs every request at INFO
logging.getLogger("httpx").setLevel(logging.WARNING)

Symbol = Path(..., pattern=r"^[A-Za-z0-9]{2,12}$", description="Mã chứng khoán, ví dụ VCB")
Interval = Literal["1m", "5m", "15m", "30m", "1H", "1D", "1W", "1M"]
def DateStr():
    # A new Query per parameter: sharing one instance between `start` and `end` made FastAPI
    # read `start` for both, so ?start=X returned only day X.
    return Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$", description="YYYY-MM-DD")
KEY_ENV = {
    "dnse": "DNSE_API_KEY, DNSE_API_SECRET", "ssi": "SSI_API_KEY, SSI_API_SECRET",
    "tcbs": "TCBS_API_KEY", "fhsc": "FHSC_API_KEY", "fmp": "FMP_API_KEY",
}


# ---------------------------------------------------------------- cache for the non-engine endpoints

REDIS_CLIENT = None
if redis is not None and settings.REDIS_URL:
    try:
        REDIS_CLIENT = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True,
                                            socket_connect_timeout=1, socket_timeout=1)
        REDIS_CLIENT.ping()
    except Exception as exc:
        logger.warning("Redis unavailable (%s), using in-memory cache", exc)
        REDIS_CLIENT = None

MEMORY_CACHE: Dict[str, tuple] = {}
_locks: Dict[str, asyncio.Lock] = {}


def read_cache(key: str):
    key = f"{settings.CACHE_NAMESPACE}:{key}"
    if REDIS_CLIENT is not None:
        try:
            raw = REDIS_CLIENT.get(key)
            return None if raw is None else json.loads(raw)
        except Exception as exc:
            logger.warning("Redis read failed: %s", exc)
    hit = MEMORY_CACHE.get(key)
    if hit and hit[0] > time.time():
        return hit[1]
    return None


def write_cache(key: str, value, ttl: int):
    key = f"{settings.CACHE_NAMESPACE}:{key}"
    if REDIS_CLIENT is not None:
        try:
            REDIS_CLIENT.setex(key, ttl, json.dumps(value, default=str))
            return
        except Exception as exc:
            logger.warning("Redis write failed: %s", exc)
    if len(MEMORY_CACHE) > 5000:          # crude bound: drop expired entries first, then everything
        stamp = time.time()
        for k in [k for k, (exp, _) in MEMORY_CACHE.items() if exp <= stamp]:
            MEMORY_CACHE.pop(k, None)
        if len(MEMORY_CACHE) > 5000:
            MEMORY_CACHE.clear()
    MEMORY_CACHE[key] = (time.time() + ttl, value)


async def cached(key: str, ttl: int, fn: Callable, cost: int = 1):
    """Cached value, or run fn in a worker thread. Concurrent requests for the same key
    share one upstream call, and every call is counted against the upstream budget."""
    hit = read_cache(key)
    if hit is not None:
        return hit
    lock = _locks.setdefault(key, asyncio.Lock())
    async with lock:
        hit = read_cache(key)
        if hit is not None:
            return hit
        if not engine.budget.take(cost, False):
            raise HTTPException(status_code=429, detail="Đã chạm hạn mức gọi nguồn mỗi phút, thử lại sau ít giây",
                                headers={"Retry-After": "15"})
        value = await engine.run_upstream(fn)
        write_cache(key, value, ttl)
        return value


# ---------------------------------------------------------------- helpers

def records(df: Optional[pd.DataFrame]) -> list:
    """DataFrame -> JSON-safe list of dicts (NaN -> null, times in Vietnam time)."""
    if df is None or df.empty:
        return []
    df = df.copy()
    # to_json would shift tz-aware times to UTC (VN midnight -> previous day 17:00Z)
    for col in df.select_dtypes(include=["datetimetz"]).columns:
        df[col] = df[col].dt.tz_convert("Asia/Ho_Chi_Minh").map(lambda x: None if pd.isna(x) else x.isoformat())
    return json.loads(df.to_json(orient="records", date_format="iso", force_ascii=False))


def ohlcv_records(df: Optional[pd.DataFrame], interval: str) -> list:
    if df is None or df.empty:
        return []
    df = df.copy()
    t = pd.to_datetime(df["time"])
    if getattr(t.dt, "tz", None) is not None:
        t = t.dt.tz_convert("Asia/Ho_Chi_Minh")
    df["time"] = t.dt.strftime("%Y-%m-%d") if interval in ("1D", "1W", "1M") else t.map(lambda x: x.isoformat())
    return records(df)


def daily_sessions(symbol: str, start: str, end: str) -> list:
    """Daily bars (oldest first) with reference = previous close and the exchange's ceiling/floor."""
    bars = sources.daily_bars(symbol, start, end)
    exchange = engine.info_of(symbol)["exchange"]
    out = []
    for i, bar in enumerate(bars):
        reference = bars[i - 1]["close"] if i > 0 else bar["close"]
        ceiling, floor = engine.ceiling_floor(exchange, reference)
        out.append({**bar, "reference_price": reference, "ceiling": ceiling, "floor": floor})
    return out


def not_found(what: str):
    raise HTTPException(status_code=404, detail=f"Không tìm thấy dữ liệu {what}")


def cache_headers(response: Response):
    response.headers["Cache-Control"] = "public, max-age=5"


# ---------------------------------------------------------------- app

@asynccontextmanager
async def lifespan(_app):
    engine.load_name_overrides(settings.NAMES_FILE)
    task = asyncio.create_task(engine.background_loop())
    logger.info("vnstock 6, sources: data=%s quote=%s company=%s index=%s",
                settings.DATA_SOURCE, settings.QUOTE_SOURCE, settings.COMPANY_SOURCE, settings.INDEX_SOURCE)
    yield
    task.cancel()


docs = {} if settings.ENABLE_DOCS else {"docs_url": None, "redoc_url": None, "openapi_url": None}
app = FastAPI(
    title=SERVICE_NAME,
    description=(
        "API tự host cho dữ liệu chứng khoán Việt Nam, dựa trên [vnstock 6](https://vnstocks.com/docs/vnstock/v6).\n\n"
        "- Mọi giá tính bằng **nghìn đồng** (57.2 = 57.200đ).\n"
        "- Mỗi nguồn dữ liệu cần khoá riêng do nguồn đó cấp. Thiếu khoá thì endpoint trả 403 kèm tên biến cần đặt.\n"
        "- Không phải tư vấn đầu tư."
    ),
    version=__version__,
    lifespan=lifespan,
    **docs,
)
app.add_middleware(CORSMiddleware, allow_origins=settings.CORS_ORIGINS,
                   allow_credentials=False, allow_methods=["GET"], allow_headers=["*"])


@app.exception_handler(Exception)
async def vnstock_errors(_request: Request, exc: Exception):
    """vnstock errors -> clear HTTP errors instead of a bare 500."""
    kinds = {c.__name__ for c in type(exc).__mro__}
    msg = str(exc).splitlines()[0] if str(exc) else type(exc).__name__
    source = getattr(exc, "source", None)
    if not source:
        found = re.search(r"source=(\w+)", str(exc))
        source = found.group(1) if found else None
    if "CredentialError" in kinds:
        env = KEY_ENV.get(str(source or "").lower(), "<NGUON>_API_KEY")
        status, hint = 403, f"Chưa có khoá cho nguồn {source or '?'}. Đặt {env} trong .env rồi khởi động lại."
    elif kinds & {"EntitlementError", "AccessDeniedError", "PolicyError", "DataSourceBlockedError"}:
        status, hint = 403, "Khoá hiện tại không có quyền dùng dữ liệu này, hoặc nguồn đang tạm dừng. Xem GET /status."
    elif kinds & {"RateLimitedError", "RateLimitError"}:
        status, hint = 429, "Nguồn dữ liệu đang giới hạn tốc độ, thử lại sau ít phút."
    elif "InputError" in kinds:
        status, hint = 400, "Kiểm tra lại mã chứng khoán và tham số."
    elif "UnsupportedError" in kinds:
        status, hint = 400, "Nguồn dữ liệu đang chọn không hỗ trợ yêu cầu này."
    elif "AuthError" in kinds:
        status, hint = 503, "Khoá nguồn không hợp lệ, hết hạn, hoặc phiên cần đăng nhập lại."
    elif kinds & {"NetworkError", "ProviderError", "SourceError", "SchemaError", "PayloadError", "EnvelopeError", "ClockSkewError"}:
        status, hint = 503, "Nguồn dữ liệu đang lỗi hoặc không truy cập được, thử lại sau."
    else:
        logger.exception("Unhandled error")
        return JSONResponse(status_code=500, content={"detail": "Lỗi nội bộ server."})
    logger.warning("%s -> %s: %s", type(exc).__name__, status, msg)
    return JSONResponse(status_code=status, content={"detail": msg, "hint": hint})


try:
    from vnstock.errors import VnstockError
    app.add_exception_handler(VnstockError, vnstock_errors)   # expected errors: answered without a traceback
except ImportError:  # pragma: no cover
    pass


# ---------------------------------------------------------------- system

@app.get("/", tags=["Hệ thống"])
async def root():
    return {"service": SERVICE_NAME, "version": __version__,
            "endpoints": ["/stock/{symbol}", "/stock/{symbol}/recent?days=7", "/stocks?symbols=PDR,VNM", "/health"],
            "docs": "/docs" if settings.ENABLE_DOCS else None}


@app.get("/health", tags=["Hệ thống"])
async def health():
    return engine.health()


@app.get("/status", tags=["Hệ thống"], summary="Bản vnstock, hạn dùng, nguồn nào đã có khoá")
async def status():
    def collect():
        import vnstock
        account = vnstock.account.status() or {}
        release = account.get("release") or {}
        keys = {name: all(os.getenv(v.strip()) for v in env.split(",")) for name, env in KEY_ENV.items()}
        return {
            "vnstock": vnstock.__version__,
            "releaseExpiresAt": release.get("expires_at"),
            "tier": account.get("tier"),
            "serverMessage": account.get("server_message"),
            "serverWarning": account.get("server_warning"),
            "keys": keys,
            "sources": {"data": settings.DATA_SOURCE, "quote": settings.QUOTE_SOURCE,
                        "company": settings.COMPANY_SOURCE, "index": settings.INDEX_SOURCE},
        }

    data = read_cache("status")
    if data is None:
        data = await engine.run_upstream(collect)
        write_cache("status", data, 60)
    return {**data, "upstreamCallsLastMinute": engine.budget.used(), "upstreamLimitPerMinute": settings.BUDGET_PER_MINUTE}


# ---------------------------------------------------------------- stocks (engine: these answers never wait on the source once cached)

@app.get("/stocks", tags=["Cổ phiếu"], summary="Nhiều mã một lượt (tối đa MAX_BATCH)")
async def get_stocks(response: Response, symbols: str = Query(..., description="Danh sách mã, cách nhau dấu phẩy")):
    requested = []
    for raw in symbols.split(","):
        code = raw.strip().upper()
        if code and code not in requested:
            requested.append(code)
    if not requested or len(requested) > settings.MAX_BATCH:
        raise HTTPException(status_code=400, detail=f"Cần từ 1 đến {settings.MAX_BATCH} mã")

    async def one(code: str):
        try:
            symbol = engine.validate_symbol(code)
            return code, engine.build_quote(symbol, await engine.get_entry(symbol)), None
        except HTTPException as exc:
            return code, None, {"status": exc.status_code, "message": exc.detail}

    results = await asyncio.gather(*(one(code) for code in requested))
    cache_headers(response)
    return {
        "data": {code: quote for code, quote, error in results if quote},
        "errors": {code: error for code, quote, error in results if error},
        "timestamp": engine.now().isoformat(),
    }


@app.get("/stock/{symbol}/recent", tags=["Cổ phiếu"], summary="N phiên gần nhất (tối đa MAX_RECENT)")
async def get_stock_recent(symbol: str, response: Response, days: int = 7):
    days = min(max(days, 1), settings.MAX_RECENT)
    code = engine.validate_symbol(symbol)
    entry = await engine.get_entry(code)
    cache_headers(response)
    return engine.build_recent(code, entry, days)


# ---------------------------------------------------------------- stocks (direct, cached)

@app.get("/stock/{symbol}/day-range", tags=["Cổ phiếu"], summary="Các phiên trong khoảng ngày, kèm giá tham chiếu/trần/sàn")
async def get_stock_range(symbol: str = Symbol,
                          start_date: str = Query(..., description="YYYY-MM-DD"),
                          end_date: str = Query(..., description="YYYY-MM-DD")):
    symbol = symbol.upper()
    try:
        start = datetime.strptime(start_date, "%Y-%m-%d")
        datetime.strptime(end_date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="Định dạng ngày không hợp lệ. Sử dụng định dạng YYYY-MM-DD")
    # A few extra days so the first session in range still has a reference price
    ext_start = (start - timedelta(days=10)).strftime("%Y-%m-%d")
    sessions = await cached(f"daily:{symbol}:{ext_start}:{end_date}", settings.CACHE_TTL_HISTORY,
                            lambda: daily_sessions(symbol, ext_start, end_date))
    data = [s for s in sessions if start_date <= s["date"] <= end_date]
    if not data:
        not_found(f"cho mã {symbol} từ {start_date} đến {end_date}")
    return {"symbol": symbol, "start_date": start_date, "end_date": end_date,
            "total_sessions": len(data), "sessions": data, "timestamp": engine.now().isoformat()}


def _ohlcv_ttl(interval: str, end: Optional[str]) -> int:
    # Closed daily+ windows don't change; anything touching today does
    past = end is not None and end < engine.now().strftime("%Y-%m-%d")
    return settings.CACHE_TTL_HISTORY if past or interval in ("1W", "1M") else settings.CACHE_TTL


@app.get("/stock/{symbol}/history", tags=["Cổ phiếu"], summary="Nến OHLCV theo khung thời gian (1m → 1M)")
async def stock_history(symbol: str = Symbol, start: Optional[str] = DateStr(), end: Optional[str] = DateStr(),
                        interval: Interval = "1D",
                        limit: Optional[int] = Query(None, ge=1, le=1000, description="Số nến mới nhất (khi không truyền start)")):
    symbol = symbol.upper()
    data = await cached(f"ohlcv:{symbol}:{start}:{end}:{interval}:{limit}", _ohlcv_ttl(interval, end),
                        lambda: ohlcv_records(sources.ohlcv("equity", symbol, start, end, interval, limit), interval))
    return {"symbol": symbol, "interval": interval, "count": len(data), "data": data}


def _dnse_quote(symbol: str) -> Optional[dict]:
    """Price board row built from DNSE: official reference/ceiling/floor (main board G1) + 3 bid/ask levels."""
    limits = records(sources.price_limits(symbol))
    row = next((r for r in limits if r.get("board") == "G1"), limits[0] if limits else None)
    book = records(sources.order_book(symbol))
    if row is None and not book:
        return None
    out = {"symbol": symbol}
    if row:
        out.update({"exchange": sources.normalize_exchange(row.get("exchange")) or row.get("exchange"),
                    "trading_date": row.get("trading_date"),
                    "reference_price": row.get("reference_price"),
                    "ceiling_price": row.get("ceiling_price"), "floor_price": row.get("floor_price")})
    if book:
        out.update(book[0])
    return out


@app.get("/stock/{symbol}/quote", tags=["Cổ phiếu"], summary="Bảng giá: tham chiếu, trần, sàn, 3 bước giá mua/bán")
async def stock_quote(symbol: str = Symbol):
    symbol = symbol.upper()
    if settings.QUOTE_SOURCE == "dnse":
        data = await cached(f"quote:{symbol}", settings.CACHE_TTL, lambda: _dnse_quote(symbol), cost=2)
    else:
        data = await cached(f"quote:{symbol}", settings.CACHE_TTL,
                            lambda: (records(sources.board([symbol])) or [None])[0])
    if not data:
        not_found(f"bảng giá cho mã {symbol}")
    return data


@app.get("/quotes", tags=["Cổ phiếu"], summary="Bảng giá nhiều mã")
async def quotes(symbols: str = Query(..., pattern=r"^[A-Za-z0-9]{2,12}(,[A-Za-z0-9]{2,12}){0,49}$",
                                      description="Tối đa 50 mã (10 mã với nguồn dnse), cách nhau bằng dấu phẩy")):
    syms = sorted({s.upper() for s in symbols.split(",")})
    if settings.QUOTE_SOURCE == "dnse":
        if len(syms) > settings.MAX_BATCH:
            raise HTTPException(status_code=400, detail=f"Nguồn dnse: tối đa {settings.MAX_BATCH} mã mỗi lượt")
        rows = [await stock_quote(s) for s in syms]
        return {"count": len(rows), "data": rows}
    data = await cached(f"quotes:{','.join(syms)}", settings.CACHE_TTL, lambda: records(sources.board(syms)))
    return {"count": len(data), "data": data}


@app.get("/stock/{symbol}/trades", tags=["Cổ phiếu"], summary="Lệnh khớp trong phiên (tick-by-tick)")
async def trades(symbol: str = Symbol, limit: int = Query(100, ge=1, le=1000)):
    symbol = symbol.upper()
    data = await cached(f"trades:{symbol}:{limit}", settings.CACHE_TTL, lambda: records(sources.trades(symbol, limit)))
    return {"symbol": symbol, "count": len(data), "data": data}


@app.get("/stock/{symbol}/foreign-flow", tags=["Cổ phiếu"], summary="Giao dịch khối ngoại theo ngày")
async def foreign_flow(symbol: str = Symbol, start: Optional[str] = DateStr(), end: Optional[str] = DateStr()):
    symbol = symbol.upper()
    data = await cached(f"foreign:{symbol}:{start}:{end}", settings.CACHE_TTL_HISTORY,
                        lambda: records(sources.foreign_flow(symbol, start, end)))
    return {"symbol": symbol, "count": len(data), "data": data}


# ---------------------------------------------------------------- company (COMPANY_SOURCE, fhsc)

CompanySection = Literal["shareholders", "ownership", "insider_trading", "events"]
FinancialReport = Literal["income_statement", "balance_sheet", "cash_flow"]


@app.get("/stock/{symbol}/company", tags=["Doanh nghiệp"], summary="Hồ sơ doanh nghiệp")
async def company_info(symbol: str = Symbol):
    symbol = symbol.upper()
    data = await cached(f"company:{symbol}", settings.CACHE_TTL_REFERENCE,
                        lambda: records(sources.company(symbol, "info")))
    if not data:
        not_found(f"doanh nghiệp cho mã {symbol}")
    return data[0]


@app.get("/stock/{symbol}/company/{section}", tags=["Doanh nghiệp"], summary="Cổ đông lớn, cơ cấu sở hữu, giao dịch nội bộ, sự kiện")
async def company_section(section: CompanySection, symbol: str = Symbol):
    symbol = symbol.upper()
    data = await cached(f"company:{symbol}:{section}", settings.CACHE_TTL_REFERENCE,
                        lambda: records(sources.company(symbol, section)))
    return {"symbol": symbol, "section": section, "count": len(data), "data": data}


@app.get("/stock/{symbol}/financials/{report}", tags=["Doanh nghiệp"], summary="Báo cáo tài chính")
async def financials(report: FinancialReport, symbol: str = Symbol,
                     period: Literal["quarter", "year"] = "quarter"):
    symbol = symbol.upper()
    data = await cached(f"fin:{symbol}:{report}:{period}", settings.CACHE_TTL_REFERENCE,
                        lambda: records(sources.financial(symbol, report, period)))
    return {"symbol": symbol, "report": report, "period": period, "count": len(data), "data": data}


# ---------------------------------------------------------------- indices & lists

@app.get("/index/{symbol}/history", tags=["Chỉ số"], summary="Nến OHLCV của chỉ số (VNINDEX, VN30, HNXINDEX...)")
async def index_history(symbol: str = Symbol, start: Optional[str] = DateStr(), end: Optional[str] = DateStr(),
                        interval: Interval = "1D", limit: Optional[int] = Query(None, ge=1, le=1000)):
    symbol = symbol.upper()
    data = await cached(f"index:{symbol}:{start}:{end}:{interval}:{limit}", _ohlcv_ttl(interval, end),
                        lambda: ohlcv_records(sources.ohlcv("index", symbol, start, end, interval, limit), interval))
    return {"symbol": symbol, "interval": interval, "count": len(data), "data": data}


@app.get("/index/{symbol}/members", tags=["Chỉ số"], summary="Danh sách mã thuộc chỉ số")
async def index_members(symbol: str = Symbol):
    symbol = symbol.upper()
    data = await cached(f"members:{symbol}", settings.CACHE_TTL_REFERENCE,
                        lambda: [r["symbol"] for r in records(sources.index_members(symbol))])
    return {"index": symbol, "count": len(data), "symbols": data}


@app.get("/indices", tags=["Danh mục"], summary="Danh sách các chỉ số")
async def indices():
    data = await cached("indices", settings.CACHE_TTL_REFERENCE, lambda: records(sources.index_list()))
    return {"count": len(data), "data": data}


@app.get("/symbols", tags=["Danh mục"], summary="Toàn bộ mã cổ phiếu niêm yết")
async def symbols():
    data = await cached("symbols", settings.CACHE_TTL_REFERENCE, lambda: records(sources.symbols()))
    return {"count": len(data), "data": data}


@app.get("/groups/{group}/symbols", tags=["Danh mục"], summary="Mã theo nhóm (VN30, VN100, HNX30...)")
async def group_symbols(group: str = Path(..., pattern=r"^[A-Za-z0-9]{2,20}$")):
    group = group.upper()
    data = await cached(f"group:{group}", settings.CACHE_TTL_REFERENCE,
                        lambda: [r["symbol"] for r in records(sources.group_members(group))])
    return {"group": group, "count": len(data), "symbols": data}


# Registered last so the more specific /stock/{symbol}/... routes above win
@app.get("/stock/{symbol}", tags=["Cổ phiếu"], summary="Phiên mới nhất + phiên trước, giá hiện tại, trần/sàn")
async def get_stock(symbol: str, response: Response, recent: Optional[int] = None):
    code = engine.validate_symbol(symbol)
    entry = await engine.get_entry(code)
    cache_headers(response)
    if recent:
        return engine.build_recent(code, entry, min(max(recent, 1), settings.MAX_RECENT))
    return engine.build_quote(code, entry)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.API_HOST, port=settings.API_PORT)
