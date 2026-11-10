"""Vietnam Stock API: a small self-hosted REST API over the DNSE Lightspeed API."""
import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Callable, Dict, Literal, Optional

from fastapi import FastAPI, HTTPException, Path, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import dnse
import engine
import sources
from config import settings

__version__ = "5.0.0"
SERVICE_NAME = os.getenv("SERVICE_NAME", "Vietnam Stock API")

logging.basicConfig(level=settings.LOG_LEVEL, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("viet-nam-stock")
logging.getLogger("httpx").setLevel(logging.WARNING)   # httpx logs every request at INFO

Symbol = Path(..., pattern=r"^[A-Za-z0-9]{2,12}$", description="Mã chứng khoán, ví dụ VCB")
Interval = Literal["1m", "5m", "15m", "30m", "1H", "1D", "1W"]


def DateStr():
    # One Query per parameter: a shared instance made FastAPI read `start` for `end` too
    return Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$", description="YYYY-MM-DD")


# ---------------------------------------------------------------- cache for the non-engine endpoints

MEMORY_CACHE: Dict[str, tuple] = {}
_locks: Dict[str, asyncio.Lock] = {}
MAX_CACHE_KEYS = 5000


def read_cache(key: str):
    hit = MEMORY_CACHE.get(key)
    return hit[1] if hit and hit[0] > time.time() else None


def write_cache(key: str, value, ttl: int):
    if len(MEMORY_CACHE) > MAX_CACHE_KEYS:
        stamp = time.time()
        for k in [k for k, (exp, _) in MEMORY_CACHE.items() if exp <= stamp]:
            MEMORY_CACHE.pop(k, None)
        if len(MEMORY_CACHE) > MAX_CACHE_KEYS:
            MEMORY_CACHE.clear()
    MEMORY_CACHE[key] = (time.time() + ttl, value)


async def cached(key: str, ttl: int, fn: Callable, cost: int = 1):
    """Cached value, or run fn in a worker thread. Concurrent requests for the same key
    share one upstream call, and every call is counted against the upstream budget."""
    hit = read_cache(key)
    if hit is not None:
        return hit
    async with _locks.setdefault(key, asyncio.Lock()):
        hit = read_cache(key)
        if hit is not None:
            return hit
        if not engine.budget.take(cost, False):
            raise HTTPException(status_code=429, detail="Đã chạm hạn mức gọi nguồn mỗi phút, thử lại sau ít giây",
                                headers={"Retry-After": "15"})
        value = await engine.run_upstream(fn)
        write_cache(key, value, ttl)
        return value


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
    engine.load_snapshot(settings.SNAPSHOT_FILE)
    task = asyncio.create_task(engine.background_loop())
    logger.info("source: DNSE Lightspeed API %s (key %s)", dnse.API_VERSION,
                "set" if os.getenv("DNSE_API_KEY") else "MISSING")
    yield
    task.cancel()
    engine.save_snapshot(settings.SNAPSHOT_FILE)


docs = {} if settings.ENABLE_DOCS else {"docs_url": None, "redoc_url": None, "openapi_url": None}
app = FastAPI(
    title=SERVICE_NAME,
    description=(
        "API tự host cho dữ liệu chứng khoán Việt Nam, lấy thẳng từ "
        "[DNSE Lightspeed API](https://developers.dnse.com.vn/docs) bằng khoá của bạn.\n\n"
        "- Mọi giá tính bằng **nghìn đồng** (57.2 = 57.200đ), khối lượng tính bằng cổ phiếu.\n"
        "- Không phải tư vấn đầu tư."
    ),
    version=__version__,
    lifespan=lifespan,
    **docs,
)
app.add_middleware(CORSMiddleware, allow_origins=settings.CORS_ORIGINS,
                   allow_credentials=False, allow_methods=["GET"], allow_headers=["*"])


@app.exception_handler(dnse.DnseError)
async def dnse_errors(_request: Request, exc: dnse.DnseError):
    """DNSE failures -> a clear HTTP error with a hint, instead of a bare 500."""
    logger.warning("%s -> %s: %s", type(exc).__name__, exc.status, exc)
    return JSONResponse(status_code=exc.status, content={"detail": str(exc), "hint": exc.hint})


# ---------------------------------------------------------------- system

@app.get("/", tags=["Hệ thống"])
async def root():
    return {"service": SERVICE_NAME, "version": __version__,
            "endpoints": ["/stock/{symbol}", "/stock/{symbol}/recent?days=7", "/stocks?symbols=PDR,VNM", "/health"],
            "docs": "/docs" if settings.ENABLE_DOCS else None}


@app.get("/health", tags=["Hệ thống"])
async def health():
    return engine.health()


@app.get("/status", tags=["Hệ thống"], summary="Khoá DNSE, phiên bản API và hạn mức DNSE còn lại")
async def status():
    return {
        "source": "dnse",
        "apiVersion": dnse.API_VERSION,
        "keyConfigured": bool(os.getenv("DNSE_API_KEY") and os.getenv("DNSE_API_SECRET")),
        # Last X-RateLimit-* headers DNSE sent, per endpoint
        "dnseLimits": dict(dnse.client().limits),
        "upstreamCallsLastMinute": engine.budget.used(),
        "upstreamLimitPerMinute": settings.BUDGET_PER_MINUTE,
    }


# ---------------------------------------------------------------- stocks (engine: never wait on DNSE once cached)

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


def _candles_ttl(interval: str, end: Optional[str]) -> int:
    # Closed windows don't change; anything touching today does
    past = end is not None and end < engine.now().strftime("%Y-%m-%d")
    return settings.CACHE_TTL_HISTORY if past or interval == "1W" else settings.CACHE_TTL


async def _history(kind: str, symbol: str, start, end, interval, limit):
    symbol = symbol.upper()
    data = await cached(f"{kind}:{symbol}:{start}:{end}:{interval}:{limit}", _candles_ttl(interval, end),
                        lambda: sources.candles(kind, symbol, start, end, interval, limit))
    return {"symbol": symbol, "interval": interval, "count": len(data), "data": data}


@app.get("/stock/{symbol}/history", tags=["Cổ phiếu"], summary="Nến OHLCV (1m → 1W)")
async def stock_history(symbol: str = Symbol, start: Optional[str] = DateStr(), end: Optional[str] = DateStr(),
                        interval: Interval = "1D",
                        limit: Optional[int] = Query(None, ge=1, le=1000, description="Số nến mới nhất (mặc định 100 khi không truyền start)")):
    return await _history("stock", symbol, start, end, interval, limit)


@app.get("/index/{symbol}/history", tags=["Chỉ số"], summary="Nến OHLCV của chỉ số (VNINDEX, VN30, HNXINDEX, UPCOMINDEX...)")
async def index_history(symbol: str = Symbol, start: Optional[str] = DateStr(), end: Optional[str] = DateStr(),
                        interval: Interval = "1D", limit: Optional[int] = Query(None, ge=1, le=1000)):
    return await _history("index", symbol, start, end, interval, limit)


@app.get("/stock/{symbol}/quote", tags=["Cổ phiếu"], summary="Bảng giá: tham chiếu, trần, sàn chính thức + 3 bước giá mua/bán")
async def stock_quote(symbol: str = Symbol):
    symbol = symbol.upper()
    data = await cached(f"quote:{symbol}", settings.CACHE_TTL, lambda: sources.price_board(symbol), cost=2)
    if not data:
        not_found(f"bảng giá cho mã {symbol}")
    return data


@app.get("/quotes", tags=["Cổ phiếu"], summary="Bảng giá nhiều mã (tối đa MAX_BATCH)")
async def quotes(symbols: str = Query(..., pattern=r"^[A-Za-z0-9]{2,12}(,[A-Za-z0-9]{2,12}){0,49}$")):
    syms = sorted({s.upper() for s in symbols.split(",")})
    if len(syms) > settings.MAX_BATCH:
        raise HTTPException(status_code=400, detail=f"Tối đa {settings.MAX_BATCH} mã mỗi lượt")
    rows = [await stock_quote(s) for s in syms]
    return {"count": len(rows), "data": rows}


@app.get("/stock/{symbol}/foreign-flow", tags=["Cổ phiếu"], summary="Khối ngoại mua/bán theo ngày (tối đa 31 ngày)")
async def foreign_flow(symbol: str = Symbol, start: Optional[str] = DateStr(), end: Optional[str] = DateStr()):
    symbol = symbol.upper()
    data = await cached(f"foreign:{symbol}:{start}:{end}", settings.CACHE_TTL_HISTORY,
                        lambda: sources.foreign_flow(symbol, start, end), cost=sources.foreign_days(start, end))
    return {"symbol": symbol, "count": len(data), "data": data}


@app.get("/symbols", tags=["Danh mục"], summary="Toàn bộ mã cổ phiếu và chứng chỉ quỹ niêm yết")
async def symbols():
    def row(symbol):
        info = engine.info_of(symbol)   # NAMES_FILE applied, without SHORT_NAMES
        return {"symbol": symbol, "name": info["fullName"], "nameEn": info["nameEn"],
                "exchange": info["exchange"], "type": info["type"]}
    data = [row(s) for s in sorted(engine.LISTING)]
    return {"count": len(data), "data": data}


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
