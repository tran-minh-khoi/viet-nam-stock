"""Vietnam Stock API: a small self-hosted REST API over vnstock."""
import asyncio
import json
import logging
import math
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Callable, Dict, Literal, Optional

import pandas as pd
import vnstock
from fastapi import FastAPI, HTTPException, Path, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from vnstock import Fundamental, Macro, Market, Reference

from config import settings

try:
    import redis
except ImportError:  # pragma: no cover
    redis = None

__version__ = "3.0.0"

logging.basicConfig(level=settings.LOG_LEVEL, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("viet-nam-stock")

SOURCE = settings.DATA_SOURCE
Symbol = Path(..., pattern=r"^[A-Za-z0-9]{2,12}$", description="Mã chứng khoán, ví dụ VCB")
Interval = Literal["1m", "5m", "15m", "30m", "1H", "1D", "1W", "1M"]
DateStr = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$", description="YYYY-MM-DD")


# ---------------------------------------------------------------- cache

REDIS_CLIENT = None
if redis is not None and settings.REDIS_URL:
    try:
        REDIS_CLIENT = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True,
                                            socket_connect_timeout=1, socket_timeout=1)
        REDIS_CLIENT.ping()
    except Exception as exc:
        logger.warning("Redis unavailable (%s), using in-memory cache", exc)
        REDIS_CLIENT = None

# ponytail: unbounded dict, fine for a personal watchlist; set REDIS_URL if it grows
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
    MEMORY_CACHE[key] = (time.time() + ttl, value)


async def cached(key: str, ttl: int, fn: Callable):
    """Return the cached value or run fn in a thread. Concurrent requests for the
    same key wait for one vnstock call instead of each spending quota."""
    hit = read_cache(key)
    if hit is not None:
        return hit
    lock = _locks.setdefault(key, asyncio.Lock())
    async with lock:
        hit = read_cache(key)
        if hit is not None:
            return hit
        value = await asyncio.to_thread(fn)
        write_cache(key, value, ttl)
        return value


# ---------------------------------------------------------------- helpers

def records(df: Optional[pd.DataFrame]) -> list:
    """DataFrame -> JSON-safe list of dicts (NaN -> null)."""
    if df is None or df.empty:
        return []
    df = df.copy()
    # to_json would shift tz-aware times to UTC (VN midnight -> previous day 17:00Z)
    for col in df.select_dtypes(include=["datetimetz"]).columns:
        df[col] = df[col].dt.tz_convert("Asia/Ho_Chi_Minh").map(lambda x: None if pd.isna(x) else x.isoformat())
    return json.loads(df.to_json(orient="records", date_format="iso", force_ascii=False))


def ohlcv_records(df: pd.DataFrame, interval: str) -> list:
    if df.empty:
        return []
    df = df.copy()
    t = pd.to_datetime(df["time"])
    df["time"] = t.dt.strftime("%Y-%m-%d") if interval in ("1D", "1W", "1M") else t.map(lambda x: x.isoformat())
    return records(df)


def get_history_window(days: int = 7):
    """(start, end) dates covering at least `days` calendar days back from today."""
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=max(7, days))).strftime('%Y-%m-%d')
    return start_date, end_date


def calculate_ceiling_floor(ref_price):
    """Giá trần/sàn HOSE (±7%), làm tròn theo bước giá: trần làm tròn xuống, sàn làm tròn lên."""
    if ref_price < 10:
        tick_size = 0.01
    elif ref_price < 50:
        tick_size = 0.05
    elif ref_price < 100:
        tick_size = 0.1
    elif ref_price < 500:
        tick_size = 0.5
    else:
        tick_size = 1.0
    ceiling = math.floor(ref_price * 1.07 / tick_size) * tick_size
    floor = math.ceil(ref_price * 0.93 / tick_size) * tick_size
    return round(ceiling, 2), round(floor, 2)


def daily_sessions(symbol: str, start: str, end: str) -> list:
    """Daily bars (oldest first) with reference price = previous session's close."""
    df = Market().equity(symbol).ohlcv(start=start, end=end, interval="1D", source=SOURCE)
    if df.empty:
        return []
    df = df.sort_values("time")
    df["reference_price"] = df["close"].shift(1).fillna(df["close"])
    out = []
    for row in df.itertuples():
        ceiling, floor = calculate_ceiling_floor(float(row.reference_price))
        out.append({
            "date": pd.to_datetime(row.time).strftime("%Y-%m-%d"),
            "open": float(row.open), "close": float(row.close),
            "high": float(row.high), "low": float(row.low),
            "volume": int(row.volume),
            "reference_price": float(row.reference_price),
            "ceiling": ceiling, "floor": floor,
        })
    return out


def live_price(symbol: str) -> float:
    """Last matched price for FAST_SYMBOLS on tiers that allow the trade tape; 0 = unavailable."""
    if symbol not in settings.FAST_SYMBOLS:
        return 0.0
    try:
        tape = Market().equity(symbol).trades(limit=1)
        return 0.0 if tape.empty else float(tape["price"].iloc[-1])
    except Exception as exc:
        logger.debug("live price unavailable for %s: %s", symbol, exc)
        return 0.0


async def exchange_of(symbol: str) -> Optional[str]:
    """HOSE / HNX / UPCOM, looked up once a day per symbol."""
    try:
        return await cached(f"exchange:{symbol}", settings.CACHE_TTL_REFERENCE,
                            lambda: (records(Market().equity(symbol).quote()) or [{}])[0].get("exchange"))
    except Exception:
        return None


# ---------------------------------------------------------------- app

@asynccontextmanager
async def lifespan(_app):
    if settings.VNSTOCK_API_KEY:
        try:
            info = await asyncio.to_thread(vnstock.login, settings.VNSTOCK_API_KEY)
            logger.info("vnstock login OK, tier=%s", info.get("tier"))
        except Exception as exc:
            logger.error("vnstock login failed, running as guest: %s", str(exc).splitlines()[0])
    else:
        logger.info("No VNSTOCK_API_KEY set, running as guest (10 calls/min)")
    yield


app = FastAPI(
    title="Vietnam Stock API",
    description=(
        "API tự host cho dữ liệu chứng khoán Việt Nam, dựa trên [vnstock](https://vnstocks.com).\n\n"
        "- Giá trong `/stock/*` và `/history`: **nghìn đồng** (57.2 = 57.200đ). "
        "Giá trong `/quote`, `/quotes`: **đồng**.\n"
        "- Nhóm **Cần tài khoản vnstock** chỉ chạy khi bạn điền `VNSTOCK_API_KEY` có cấp phù hợp; "
        "nếu không sẽ trả lỗi 403 kèm lý do.\n"
        "- Không phải tư vấn đầu tư."
    ),
    version=__version__,
    lifespan=lifespan,
)
app.add_middleware(CORSMiddleware, allow_origins=settings.CORS_ORIGINS,
                   allow_credentials=False, allow_methods=["GET"], allow_headers=["*"])


@app.exception_handler(Exception)
async def vnstock_errors(_request: Request, exc: Exception):
    """Turn vnstock errors into clear HTTP errors instead of a bare 500."""
    kinds = {c.__name__ for c in type(exc).__mro__}
    msg = str(exc).splitlines()[0] if str(exc) else type(exc).__name__
    if "EntitlementError" in kinds:
        if "hạn mức" in msg or "quota" in msg.lower():
            status, hint = 429, "Đã hết lượt gọi của tài khoản vnstock. Đợi một lúc hoặc dùng VNSTOCK_API_KEY có hạn mức cao hơn."
        else:
            status, hint = 403, "Tài khoản vnstock hiện tại chưa có quyền dùng dữ liệu này. Xem GET /status và docs/vnstock-account.md."
    elif "RateLimitedError" in kinds:
        status, hint = 429, "Nguồn dữ liệu đang giới hạn tốc độ, thử lại sau ít phút."
    elif "InputError" in kinds:
        status, hint = (404, "Kiểm tra lại mã chứng khoán.") if "không có mã" in msg else (400, "Kiểm tra lại tham số.")
    elif "UnsupportedError" in kinds:
        status, hint = 400, "Nguồn dữ liệu không hỗ trợ yêu cầu này."
    elif "AuthError" in kinds:
        status, hint = 503, "VNSTOCK_API_KEY không hợp lệ hoặc đã hết hạn."
    elif kinds & {"NetworkError", "ProviderError", "SchemaError"}:
        status, hint = 503, "Nguồn dữ liệu đang lỗi hoặc không truy cập được, thử lại sau."
    else:
        logger.exception("Unhandled error")
        return JSONResponse(status_code=500, content={"detail": "Lỗi nội bộ server."})
    logger.warning("%s -> %s: %s", type(exc).__name__, status, msg)
    return JSONResponse(status_code=status, content={"detail": msg, "hint": hint})


def not_found(what: str):
    raise HTTPException(status_code=404, detail=f"Không tìm thấy dữ liệu {what}")


# ---------------------------------------------------------------- system

@app.get("/", tags=["Hệ thống"])
async def root():
    return {"message": "Vietnam Stock API is running", "version": __version__, "docs": "/docs"}


@app.get("/health", tags=["Hệ thống"])
async def health_check():
    return {"status": "healthy", "service": "stock-api"}


@app.get("/status", tags=["Hệ thống"], summary="Cấp tài khoản vnstock và số lượt gọi đã dùng")
async def status():
    return await cached("status", 10, vnstock.account.usage)


# ---------------------------------------------------------------- stocks (guest tier)

@app.get("/stock/{symbol}", tags=["Cổ phiếu"], summary="Phiên mới nhất + phiên trước, kèm giá trần/sàn")
async def get_stock_today(symbol: str = Symbol, recent: Optional[int] = Query(None, ge=1, le=250)):
    if recent:
        return await get_stock_recent(symbol, recent)
    symbol = symbol.upper()
    start, end = get_history_window(settings.DEFAULT_HISTORY_DAYS)
    sessions = await cached(f"daily:{symbol}:{start}:{end}", settings.CACHE_TTL,
                            lambda: daily_sessions(symbol, start, end))
    if not sessions:
        not_found(f"cho mã {symbol}")
    latest = sessions[-1]
    previous = sessions[-2] if len(sessions) > 1 else latest
    current = await cached(f"live:{symbol}", settings.CACHE_TTL, lambda: live_price(symbol)) or latest["close"]
    is_today = latest["date"] == datetime.now().strftime("%Y-%m-%d")
    now = datetime.now().isoformat()
    return {
        "symbol": symbol,
        "name": symbol,
        "exchange": await exchange_of(symbol),
        "currentPrice": round(current, 2),
        "referencePrice": latest["reference_price"],
        "upperPrice": latest["ceiling"],
        "lowerPrice": latest["floor"],
        "todayOpen": latest["open"],
        "todayHigh": latest["high"],
        "todayLow": latest["low"],
        "todayVolume": latest["volume"],
        "todayDate": latest["date"],
        "previousClose": previous["close"],
        "previousVolume": previous["volume"],
        "previousDate": previous["date"],
        "lastUpdated": now,
        "data": {
            "today": {**{k: latest[k] for k in ("date", "open", "high", "low", "volume")},
                      "close": round(current, 2), "current_price": round(current, 2),
                      "reference_price": latest["reference_price"],
                      "ceiling": latest["ceiling"], "floor": latest["floor"], "is_today": is_today},
            "previous": {"date": previous["date"], "close": previous["close"], "volume": previous["volume"]},
        },
        "timestamp": now,
    }


@app.get("/stock/{symbol}/recent", tags=["Cổ phiếu"], summary="N phiên giao dịch gần nhất")
async def get_stock_recent(symbol: str = Symbol, days: int = Query(7, ge=1, le=250)):
    symbol = symbol.upper()
    # ~2 calendar days per trading session covers weekends and holidays
    start, end = get_history_window(days * 2 + 7)
    sessions = await cached(f"daily:{symbol}:{start}:{end}", settings.CACHE_TTL,
                            lambda: daily_sessions(symbol, start, end))
    today = datetime.now().strftime("%Y-%m-%d")
    data = [{**s, "is_today": s["date"] == today} for s in sessions[-days:]]
    if not data:
        not_found(f"cho mã {symbol} trong {days} phiên gần đây")
    return {"symbol": symbol, "days": days, "actual_sessions": len(data),
            "sessions": data, "timestamp": datetime.now().isoformat()}


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
            "total_sessions": len(data), "sessions": data, "timestamp": datetime.now().isoformat()}


def _ohlcv_ttl(interval: str, end: Optional[str]) -> int:
    # Closed daily+ windows don't change; anything touching today does
    past = end is not None and end < datetime.now().strftime("%Y-%m-%d")
    return settings.CACHE_TTL_HISTORY if past or interval in ("1W", "1M") else settings.CACHE_TTL


@app.get("/stock/{symbol}/history", tags=["Cổ phiếu"], summary="Nến OHLCV theo khung thời gian (1m → 1M)")
async def stock_history(symbol: str = Symbol, start: Optional[str] = DateStr, end: Optional[str] = DateStr,
                        interval: Interval = "1D",
                        limit: Optional[int] = Query(None, ge=1, le=1000, description="Số nến mới nhất (khi không truyền start)")):
    symbol = symbol.upper()
    data = await cached(f"ohlcv:{symbol}:{start}:{end}:{interval}:{limit}", _ohlcv_ttl(interval, end), lambda: ohlcv_records(
        Market().equity(symbol).ohlcv(start=start, end=end, interval=interval, limit=limit, source=SOURCE), interval))
    return {"symbol": symbol, "interval": interval, "count": len(data), "data": data}


@app.get("/stock/{symbol}/quote", tags=["Cổ phiếu"], summary="Bảng giá: tham chiếu, trần, sàn, 3 bước giá mua/bán (đồng)")
async def stock_quote(symbol: str = Symbol):
    symbol = symbol.upper()
    data = await cached(f"quote:{symbol}", settings.CACHE_TTL, lambda: records(Market().equity(symbol).quote()))
    if not data:
        not_found(f"bảng giá cho mã {symbol}")
    return data[0]


@app.get("/quotes", tags=["Cổ phiếu"], summary="Bảng giá nhiều mã trong 1 lượt gọi (tiết kiệm hạn mức)")
async def quotes(symbols: str = Query(..., pattern=r"^[A-Za-z0-9]{2,12}(,[A-Za-z0-9]{2,12}){0,49}$",
                                      description="Tối đa 50 mã, cách nhau bằng dấu phẩy: VCB,FPT,HPG")):
    syms = sorted({s.upper() for s in symbols.split(",")})
    data = await cached(f"quotes:{','.join(syms)}", settings.CACHE_TTL, lambda: records(Market().quote(syms)))
    return {"count": len(data), "data": data}


@app.get("/stock/{symbol}/company", tags=["Cổ phiếu"], summary="Thông tin doanh nghiệp")
async def company_info(symbol: str = Symbol):
    symbol = symbol.upper()
    data = await cached(f"company:{symbol}", settings.CACHE_TTL_REFERENCE,
                        lambda: records(Reference().company(symbol).info()))
    if not data:
        not_found(f"doanh nghiệp cho mã {symbol}")
    return data[0]


# ---------------------------------------------------------------- indices & lists (guest tier)

@app.get("/index/{symbol}/history", tags=["Chỉ số"], summary="Nến OHLCV của chỉ số (VNINDEX, VN30, HNXINDEX...)")
async def index_history(symbol: str = Symbol, start: Optional[str] = DateStr, end: Optional[str] = DateStr,
                        interval: Interval = "1D", limit: Optional[int] = Query(None, ge=1, le=1000)):
    symbol = symbol.upper()
    data = await cached(f"index:{symbol}:{start}:{end}:{interval}:{limit}", _ohlcv_ttl(interval, end), lambda: ohlcv_records(
        Market().index(symbol).ohlcv(start=start, end=end, interval=interval, limit=limit), interval))
    return {"symbol": symbol, "interval": interval, "count": len(data), "data": data}


@app.get("/index/{symbol}/members", tags=["Chỉ số"], summary="Danh sách mã thuộc chỉ số")
async def index_members(symbol: str = Symbol):
    symbol = symbol.upper()
    data = await cached(f"members:{symbol}", settings.CACHE_TTL_REFERENCE,
                        lambda: [r["symbol"] for r in records(Reference().index(symbol).members())])
    return {"index": symbol, "count": len(data), "symbols": data}


@app.get("/indices", tags=["Danh mục"], summary="Danh sách các chỉ số")
async def indices():
    data = await cached("indices", settings.CACHE_TTL_REFERENCE, lambda: records(Reference().index.list()))
    return {"count": len(data), "data": data}


@app.get("/symbols", tags=["Danh mục"], summary="Toàn bộ mã cổ phiếu niêm yết")
async def symbols():
    data = await cached("symbols", settings.CACHE_TTL_REFERENCE, lambda: records(Reference().equity.list()))
    return {"count": len(data), "data": data}


@app.get("/groups/{group}/symbols", tags=["Danh mục"], summary="Mã theo nhóm (VN30, VN100, HNX30...)")
async def group_symbols(group: str = Path(..., pattern=r"^[A-Za-z0-9]{2,20}$")):
    group = group.upper()
    data = await cached(f"group:{group}", settings.CACHE_TTL_REFERENCE,
                        lambda: [r["symbol"] for r in records(Reference().equity.by_group(group))])
    return {"group": group, "count": len(data), "symbols": data}


# ---------------------------------------------------------------- registered tiers

FinancialReport = Literal["income_statement", "balance_sheet", "cash_flow", "ratio"]
CompanySection = Literal["shareholders", "officers", "subsidiaries", "events"]
MACRO = {
    "gdp": ("economy", "gdp"), "cpi": ("economy", "cpi"), "fdi": ("economy", "fdi"),
    "import-export": ("economy", "import_export"), "credit": ("economy", "credit"),
    "money-supply": ("economy", "money_supply"), "exchange-rate": ("currency", "exchange_rate"),
    "interbank-rate": ("currency", "interbank_rate"), "deposit-rate": ("currency", "deposit_rate"),
    "policy-rate": ("currency", "policy_rate"),
}
MacroIndicator = Literal[tuple(MACRO)]
PAID = "Cần tài khoản vnstock"


@app.get("/stock/{symbol}/financials/{report}", tags=[PAID], summary="Báo cáo tài chính / chỉ số tài chính")
async def financials(report: FinancialReport, symbol: str = Symbol,
                     period: Literal["quarter", "year"] = "quarter"):
    symbol = symbol.upper()
    data = await cached(f"fin:{symbol}:{report}:{period}", settings.CACHE_TTL_REFERENCE,
                        lambda: records(getattr(Fundamental().equity(symbol), report)(period=period)))
    return {"symbol": symbol, "report": report, "period": period, "count": len(data), "data": data}


@app.get("/stock/{symbol}/company/{section}", tags=[PAID], summary="Cổ đông, ban lãnh đạo, công ty con, sự kiện")
async def company_section(section: CompanySection, symbol: str = Symbol):
    symbol = symbol.upper()
    data = await cached(f"company:{symbol}:{section}", settings.CACHE_TTL_REFERENCE,
                        lambda: records(getattr(Reference().company(symbol), section)()))
    return {"symbol": symbol, "section": section, "count": len(data), "data": data}


@app.get("/stock/{symbol}/trades", tags=[PAID], summary="Lệnh khớp trong phiên (tick-by-tick)")
async def trades(symbol: str = Symbol, limit: int = Query(100, ge=1, le=1000)):
    symbol = symbol.upper()
    data = await cached(f"trades:{symbol}:{limit}", settings.CACHE_TTL,
                        lambda: records(Market().equity(symbol).trades(limit=limit)))
    return {"symbol": symbol, "count": len(data), "data": data}


@app.get("/stock/{symbol}/foreign-flow", tags=[PAID], summary="Giao dịch khối ngoại")
async def foreign_flow(symbol: str = Symbol, start: Optional[str] = DateStr, end: Optional[str] = DateStr):
    symbol = symbol.upper()
    data = await cached(f"foreign:{symbol}:{start}:{end}", settings.CACHE_TTL_HISTORY,
                        lambda: records(Market().equity(symbol).foreign_flow(start=start, end=end)))
    return {"symbol": symbol, "count": len(data), "data": data}


@app.get("/macro/{indicator}", tags=[PAID], summary="Vĩ mô: GDP, CPI, FDI, tỷ giá, lãi suất...")
async def macro(indicator: MacroIndicator, start: Optional[str] = DateStr, end: Optional[str] = DateStr):
    group, method = MACRO[indicator]
    data = await cached(f"macro:{indicator}:{start}:{end}", settings.CACHE_TTL_REFERENCE,
                        lambda: records(getattr(getattr(Macro(), group)(), method)(start=start, end=end)))
    return {"indicator": indicator, "count": len(data), "data": data}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.API_HOST, port=settings.API_PORT)
