"""In-memory engine behind /stock/{symbol}, /stock/{symbol}/recent and /stocks.

A user request never waits for the data source once a symbol is cached:
- each symbol's daily sessions (+ today's session from the last trade) are kept in memory;
- a stale entry is still answered right away and refreshed in the background;
- PRIORITY_SYMBOLS are refreshed on a timer even when nobody asks;
- UpstreamBudget caps calls per minute so a burst cannot use up the DNSE key's limits.

Run ONE worker: cache and budget live in the process.
"""
import asyncio
import json
import logging
import math
import os
import re
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from typing import Dict, Optional
from zoneinfo import ZoneInfo

from fastapi import HTTPException

import sources
from config import settings

logger = logging.getLogger("viet-nam-stock.engine")

TTL_NOT_FOUND = 3600
HISTORY_CALENDAR_DAYS = 70       # enough for MAX_RECENT sessions + 1 reference session
FIRST_FETCH_TIMEOUT = 12         # a first request for an uncached symbol waits at most this long
RETRY_AFTER_FAILURE = 15         # after a failed refresh, wait this long before trying again
RETRY_AFTER_THROTTLE = 120       # ...and this long when the source said "too many requests" / quota
THROTTLE_ERRORS = {"RateLimited", "QuotaExceeded", "AuthFailed", "NotConfigured"}
SNAPSHOT_EVERY = 30              # seconds between snapshot writes (only when something changed)
LISTED_TRADE_MAX_AGE = 600       # a last trade older than this is not "current"
LISTING_REFRESH_SECONDS = 24 * 3600
LISTING_COST = 25                # ~2,100 instruments / 100 per page

SYMBOL_PATTERN = re.compile(r"^[A-Z0-9]{3,8}$")
PRICE_BAND = {"HOSE": 0.07, "HNX": 0.10, "UPCOM": 0.15}
VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


def now() -> datetime:
    """Vietnam wall-clock time, naive, whatever the server/container timezone is. Tests replace this."""
    return datetime.now(VN_TZ).replace(tzinfo=None)


def vn_time(stamp: float) -> str:
    """Unix time -> ISO string in Vietnam time (naive, like the rest of the API)."""
    return datetime.fromtimestamp(stamp, VN_TZ).replace(tzinfo=None).isoformat()


def is_trading_time(at: Optional[datetime] = None) -> bool:
    at = at or now()
    if at.weekday() >= 5:
        return False
    minutes = at.hour * 60 + at.minute
    return 8 * 60 + 45 <= minutes <= 15 * 60 + 5


class UpstreamBudget:
    """Counts upstream calls in the last 60 seconds."""

    def __init__(self, per_minute: int, reserved: int):
        self.per_minute = per_minute
        self.reserved = reserved
        self.calls = deque()

    def _trim(self):
        cutoff = time.time() - 60
        while self.calls and self.calls[0] < cutoff:
            self.calls.popleft()

    def used(self) -> int:
        self._trim()
        return len(self.calls)

    def take(self, cost: int, priority: bool) -> bool:
        limit = self.per_minute if priority else self.per_minute - self.reserved
        if self.used() + cost > limit:
            return False
        stamp = time.time()
        self.calls.extend([stamp] * cost)
        return True


budget = UpstreamBudget(settings.BUDGET_PER_MINUTE, settings.BUDGET_RESERVED_FOR_PRIORITY)
executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="upstream")

CACHE: Dict[str, dict] = {}            # symbol -> {"sessions", "current_price", "fetched_at", "failed_at"}
NOT_FOUND: Dict[str, float] = {}       # symbol -> when the source said it has no data
IN_FLIGHT: Dict[str, asyncio.Task] = {}
LAST_FAILURE: Dict[str, float] = {}   # symbol -> last failed refresh, also for symbols not cached yet
RETRY_AFTER: Dict[str, float] = {}    # symbol -> seconds to wait after LAST_FAILURE
LISTING: Dict[str, dict] = {}          # symbol -> {"name", "nameEn", "exchange", "type"}
LISTING_LOADED_AT = 0.0
NAME_OVERRIDES: Dict[str, dict] = {}
STARTED_AT = time.time()


_snapshot_state = {"dirty": False, "written_at": 0.0}


def save_snapshot(path: str):
    """Write the cache + symbol list to `path` atomically, so a restart can answer at once."""
    if not path:
        return
    payload = {"saved_at": time.time(), "listing": LISTING, "listing_loaded_at": LISTING_LOADED_AT,
               "entries": {s: {k: e[k] for k in ("sessions", "current_price", "fetched_at")} for s, e in CACHE.items()}}
    tmp = f"{path}.tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False)
        os.replace(tmp, path)
        _snapshot_state.update(dirty=False, written_at=time.time())
    except Exception as exc:
        logger.warning("cannot write snapshot %s: %s", path, exc)


def load_snapshot(path: str):
    """Restore the last good data written by save_snapshot. Entries keep their real age, so they are
    answered right away (stale if old) and refreshed in the background as usual."""
    global LISTING, LISTING_LOADED_AT
    if not path or not os.path.exists(path):
        return
    try:
        with open(path, encoding="utf-8") as fh:
            payload = json.load(fh)
        for symbol, entry in (payload.get("entries") or {}).items():
            if entry.get("sessions"):
                CACHE[symbol] = {**entry, "failed_at": 0.0}
        if payload.get("listing"):
            LISTING = payload["listing"]
            LISTING_LOADED_AT = float(payload.get("listing_loaded_at") or 0.0)
        logger.info("snapshot restored: %d symbols, %d listed, saved %ds ago", len(CACHE), len(LISTING),
                    int(time.time() - float(payload.get("saved_at") or time.time())))
    except Exception as exc:
        logger.warning("cannot read snapshot %s: %s", path, exc)


def load_name_overrides(path: str):
    global NAME_OVERRIDES
    if not path:
        return
    try:
        with open(path, encoding="utf-8") as fh:
            raw = json.load(fh)
        # Only text values: a NaN written by a pandas export would break every JSON answer
        NAME_OVERRIDES = {k.upper(): {f: x for f, x in v.items() if isinstance(x, str) and x.strip()}
                          for k, v in raw.items() if isinstance(v, dict)}
        logger.info("name overrides: %d symbols from %s", len(NAME_OVERRIDES), path)
    except Exception as exc:
        logger.warning("cannot read NAMES_FILE %s: %s", path, exc)


def reset():
    """Forget everything (tests)."""
    global LISTING, LISTING_LOADED_AT
    CACHE.clear()
    NOT_FOUND.clear()
    IN_FLIGHT.clear()
    LAST_FAILURE.clear()
    RETRY_AFTER.clear()
    _snapshot_state["dirty"] = False
    LISTING = {}
    LISTING_LOADED_AT = 0.0
    budget.calls.clear()


def ttl_for(symbol: str) -> int:
    if not is_trading_time():
        return settings.TTL_OFF_HOURS
    return settings.TTL_TRADING_PRIORITY if symbol in settings.PRIORITY_SYMBOLS else settings.TTL_TRADING


def fetch_cost() -> int:
    return 2   # daily history + last trade


# ---------------------------------------------------------------- upstream (worker threads)

def fetch_symbol(symbol: str, with_trade: bool) -> Optional[dict]:
    """Daily sessions + today's session from the last trade. None if DNSE has no data for the symbol.

    DNSE adds a session's daily bar only after it ends, so while it runs (and for a while after
    the close) today's open/high/low/volume and the current price come from the last trade.
    """
    end = now()
    start = end - timedelta(days=HISTORY_CALENDAR_DAYS)
    sessions = sources.daily_bars(symbol, start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))
    if not sessions:
        return None

    current_price = None
    try:
        trade = sources.latest_trade(symbol)
    except Exception as exc:
        trade = None
        logger.warning("last trade %s failed: %s", symbol, exc)
    if trade is not None:
        at = trade.pop("at")
        if trade["date"] > sessions[-1]["date"] and trade["date"] == end.strftime("%Y-%m-%d"):
            sessions.append(trade)
        if with_trade and trade["date"] == sessions[-1]["date"] and \
                (end - at).total_seconds() <= LISTED_TRADE_MAX_AGE:
            current_price = trade["close"]

    return {"sessions": sessions, "current_price": current_price}


async def run_upstream(func, *args):
    """Run a blocking DNSE call in a worker thread; SystemExit from a library never kills the API."""
    loop = asyncio.get_running_loop()

    def guarded():
        try:
            return func(*args)
        except SystemExit as exc:
            raise RuntimeError(f"data source refused: {str(exc)[:120]}")

    return await loop.run_in_executor(executor, guarded)


# ---------------------------------------------------------------- cache

class SuspiciousData(Exception):
    """The source answered, but with data we would rather not replace a good copy with."""


def _record_failure(symbol: str, exc: Exception):
    kinds = {c.__name__ for c in type(exc).__mro__}
    LAST_FAILURE[symbol] = time.time()
    RETRY_AFTER[symbol] = RETRY_AFTER_THROTTLE if kinds & THROTTLE_ERRORS else RETRY_AFTER_FAILURE
    if symbol in CACHE:
        CACHE[symbol]["failed_at"] = time.time()


def may_retry(symbol: str) -> bool:
    return time.time() - LAST_FAILURE.get(symbol, 0) > RETRY_AFTER.get(symbol, RETRY_AFTER_FAILURE)


async def _refresh(symbol: str):
    try:
        data = await run_upstream(fetch_symbol, symbol, is_trading_time())
        known = CACHE.get(symbol)
        if data is None:
            if known:
                # A symbol we have good data for does not vanish: treat an empty answer as a hiccup
                raise SuspiciousData("source returned no sessions for a known symbol")
            NOT_FOUND[symbol] = time.time()
            return
        if known and data["sessions"][-1]["date"] < known["sessions"][-1]["date"]:
            raise SuspiciousData(f"source went back to {data['sessions'][-1]['date']}, "
                                 f"keeping {known['sessions'][-1]['date']}")
        NOT_FOUND.pop(symbol, None)
        LAST_FAILURE.pop(symbol, None)
        RETRY_AFTER.pop(symbol, None)
        data["fetched_at"] = time.time()
        data["failed_at"] = 0.0
        CACHE[symbol] = data
        _snapshot_state["dirty"] = True
    except Exception as exc:
        logger.warning("refresh %s failed: %s: %s", symbol, type(exc).__name__, str(exc).splitlines()[0] if str(exc) else "")
        _record_failure(symbol, exc)
        raise
    finally:
        IN_FLIGHT.pop(symbol, None)


def start_refresh(symbol: str) -> Optional[asyncio.Task]:
    """Start a background refresh unless one is running. None = no budget left."""
    task = IN_FLIGHT.get(symbol)
    if task:
        return task
    if not budget.take(fetch_cost(), symbol in settings.PRIORITY_SYMBOLS):
        return None
    task = asyncio.create_task(_refresh(symbol))
    task.add_done_callback(lambda t: t.cancelled() or t.exception())  # already logged in _refresh
    IN_FLIGHT[symbol] = task
    return task


def is_fresh(symbol: str, entry: dict) -> bool:
    return time.time() - entry["fetched_at"] < ttl_for(symbol)


def validate_symbol(raw: str) -> str:
    symbol = (raw or "").strip().upper()
    if not SYMBOL_PATTERN.match(symbol):
        raise HTTPException(status_code=400, detail="Mã chứng khoán không hợp lệ")
    # With a symbol list loaded, unknown symbols are rejected without spending budget
    if LISTING and symbol not in LISTING:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy mã {symbol}")
    if symbol in NOT_FOUND and time.time() - NOT_FOUND[symbol] < TTL_NOT_FOUND:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy dữ liệu cho mã {symbol}")
    return symbol


async def get_entry(symbol: str) -> dict:
    entry = CACHE.get(symbol)
    if entry:
        if not is_fresh(symbol, entry) and may_retry(symbol):
            start_refresh(symbol)
        return entry

    task = start_refresh(symbol)
    if task is None:
        raise HTTPException(status_code=503, detail="Hệ thống đang bận, vui lòng thử lại sau ít giây",
                            headers={"Retry-After": "15"})
    try:
        await asyncio.wait_for(asyncio.shield(task), timeout=FIRST_FETCH_TIMEOUT)
    except asyncio.TimeoutError:
        raise HTTPException(status_code=503, detail="Nguồn dữ liệu phản hồi chậm, vui lòng thử lại sau ít giây",
                            headers={"Retry-After": "5"})
    except Exception:
        raise HTTPException(status_code=502, detail="Không lấy được dữ liệu từ nguồn, vui lòng thử lại sau",
                            headers={"Retry-After": "15"})

    entry = CACHE.get(symbol)
    if not entry:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy dữ liệu cho mã {symbol}")
    return entry


# ---------------------------------------------------------------- prices

def tick_size(exchange: str, price: float) -> float:
    if exchange != "HOSE":
        return 0.1
    if price < 10:
        return 0.01
    if price < 50:
        return 0.05
    return 0.1


def ceiling_floor(exchange: str, reference: float):
    """Ceiling/floor from the reference price: band by exchange, rounded inward to the tick size."""
    band = PRICE_BAND.get(exchange, 0.07)
    tick = tick_size(exchange, reference)
    ceiling = math.floor(round(reference * (1 + band) / tick, 6)) * tick
    floor = math.ceil(round(reference * (1 - band) / tick, 6)) * tick
    return round(ceiling, 2), round(floor, 2)


def info_of(symbol: str) -> dict:
    info = dict(LISTING.get(symbol) or {"name": symbol, "nameEn": None, "exchange": "HOSE", "type": None})
    override = NAME_OVERRIDES.get(symbol)
    if override:
        for key in ("name", "nameEn", "exchange"):
            if override.get(key):
                info[key] = override[key]
    return {**info, "fullName": info["name"], "name": settings.SHORT_NAMES.get(symbol, info["name"])}


def build_quote(symbol: str, entry: dict) -> dict:
    info = info_of(symbol)
    sessions = entry["sessions"]
    latest = sessions[-1]
    previous = sessions[-2] if len(sessions) > 1 else latest
    reference = previous["close"]
    current = entry["current_price"] if entry["current_price"] is not None else latest["close"]
    upper, lower = ceiling_floor(info["exchange"], reference)
    change = round(current - reference, 2)
    is_today = latest["date"] == now().strftime("%Y-%m-%d")
    age = time.time() - entry["fetched_at"]

    return {
        "symbol": symbol,
        "name": info["name"],
        "fullName": info["fullName"],
        "nameEn": info["nameEn"],
        "exchange": info["exchange"],
        "currentPrice": round(current, 2),
        "referencePrice": round(reference, 2),
        "upperPrice": upper,
        "lowerPrice": lower,
        "change": change,
        "changePercent": round(change / reference * 100, 2) if reference else 0,
        "todayOpen": latest["open"],
        "todayHigh": latest["high"],
        "todayLow": latest["low"],
        "todayVolume": latest["volume"],
        "todayDate": latest["date"],
        "previousClose": previous["close"],
        "previousVolume": previous["volume"],
        "previousDate": previous["date"],
        "lastUpdated": vn_time(entry["fetched_at"]),
        "data": {
            "today": {
                "date": latest["date"],
                "open": latest["open"],
                "close": round(current, 2),
                "high": latest["high"],
                "low": latest["low"],
                "volume": latest["volume"],
                "current_price": round(current, 2),
                "reference_price": round(reference, 2),
                "ceiling": upper,
                "floor": lower,
                "is_today": is_today,
            },
            "previous": {
                "date": previous["date"],
                "close": previous["close"],
                "volume": previous["volume"],
            },
        },
        "marketOpen": is_trading_time(),
        "stale": age > max(ttl_for(symbol) * 3, 90),
        "timestamp": now().isoformat(),
    }


def build_recent(symbol: str, entry: dict, days: int) -> dict:
    info = info_of(symbol)
    sessions = entry["sessions"]
    today = now().strftime("%Y-%m-%d")
    first = max(0, len(sessions) - days)
    result = []
    for index in range(first, len(sessions)):
        session = sessions[index]
        reference = sessions[index - 1]["close"] if index > 0 else session["close"]
        ceiling, floor = ceiling_floor(info["exchange"], reference)
        item = {
            "date": session["date"],
            "open": session["open"],
            "close": session["close"],
            "high": session["high"],
            "low": session["low"],
            "volume": session["volume"],
            "reference_price": reference,
            "ceiling": ceiling,
            "floor": floor,
            "is_today": session["date"] == today,
        }
        if index == len(sessions) - 1:
            item["current_price"] = entry["current_price"] if entry["current_price"] is not None else session["close"]
        result.append(item)

    return {
        "symbol": symbol,
        "name": info["name"],
        "exchange": info["exchange"],
        "days": days,
        "actual_sessions": len(result),
        "sessions": result,
        "lastUpdated": vn_time(entry["fetched_at"]),
        "timestamp": now().isoformat(),
    }


# ---------------------------------------------------------------- background

async def load_listing():
    global LISTING, LISTING_LOADED_AT
    if not budget.take(LISTING_COST, True):   # instruments come in pages of 100
        return
    try:
        listing = await run_upstream(sources.listing)
        if listing:
            # Symbols only in NAMES_FILE (e.g. funds a source does not list) stay valid
            for symbol, info in NAME_OVERRIDES.items():
                if symbol not in listing and info.get("exchange") in PRICE_BAND:
                    listing[symbol] = {"name": info.get("name") or symbol, "nameEn": info.get("nameEn"),
                                       "exchange": info["exchange"], "type": info.get("type")}
            LISTING = listing
            LISTING_LOADED_AT = time.time()
            _snapshot_state["dirty"] = True
            logger.info("symbol list loaded: %d symbols", len(listing))
    except Exception as exc:
        logger.warning("loading symbol list failed: %s: %s", type(exc).__name__, str(exc).splitlines()[0] if str(exc) else "")


async def _background_loop_impl():
    last_listing_attempt = 0.0
    while True:
        try:
            stamp = time.time()
            if stamp - LISTING_LOADED_AT > LISTING_REFRESH_SECONDS and stamp - last_listing_attempt > 300:
                last_listing_attempt = stamp
                await load_listing()
            for symbol in settings.PRIORITY_SYMBOLS:
                entry = CACHE.get(symbol)
                if not may_retry(symbol):
                    continue
                if entry is None or not is_fresh(symbol, entry):
                    start_refresh(symbol)
            if _snapshot_state["dirty"] and stamp - _snapshot_state["written_at"] > SNAPSHOT_EVERY:
                await asyncio.get_running_loop().run_in_executor(None, save_snapshot, settings.SNAPSHOT_FILE)
        except Exception:
            logger.exception("background loop error")
        await asyncio.sleep(3)


def health() -> dict:
    first = CACHE.get(settings.PRIORITY_SYMBOLS[0]) if settings.PRIORITY_SYMBOLS else None
    return {
        "status": "ok",
        "uptimeSeconds": int(time.time() - STARTED_AT),
        "marketOpen": is_trading_time(),
        "cachedSymbols": len(CACHE),
        "listedSymbols": len(LISTING),
        "upstreamCallsLastMinute": budget.used(),
        "upstreamLimitPerMinute": settings.BUDGET_PER_MINUTE,
        "priorityAgeSeconds": int(time.time() - first["fetched_at"]) if first else None,
    }


async def background_loop():
    await _background_loop_impl()
