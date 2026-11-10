"""DNSE answers -> the plain dicts this API works with. The only module that knows DNSE's field names.

Prices are in thousand VND (11.75 = 11,750 VND), like DNSE returns them. Volumes are in shares.
"""
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from zoneinfo import ZoneInfo

import dnse

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
EXCHANGES = {"STO": "HOSE", "STX": "HNX", "UPX": "UPCOM"}
LISTED_GROUPS = {"ST": "stock", "EF": "fund", "MF": "fund"}   # stocks, ETFs, closed-end funds
MAIN_BOARD = "G1"            # round lots; G4 odd lots, T* put-through
# Round-lot quantities in trades/latest and quotes/latest come in units of 10 shares
# (checked against the 1-minute candles on HOSE and HNX, 2026-11-10)
LOT_UNIT = 10
INDEX_NAMES = {"HNXINDEX": "HNX", "UPCOMINDEX": "UPCOM"}
RESOLUTIONS = {"1m": "1", "5m": "5", "15m": "15", "30m": "30", "1H": "1H", "1D": "1D", "1W": "1W"}
# How far back to look when only `limit` is given
LOOKBACK_DAYS = {"1m": 5, "5m": 20, "15m": 45, "30m": 90, "1H": 180, "1D": 1500, "1W": 3650}
INSTRUMENT_PAGE = 100        # DNSE's largest page
MAX_FOREIGN_DAYS = 31        # one request per day


def _epoch(day: str, end_of_day: bool = False) -> int:
    start = datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=VN_TZ)
    return int((start + timedelta(days=1, seconds=-1) if end_of_day else start).timestamp())


def _local(epoch: int) -> datetime:
    return datetime.fromtimestamp(epoch, VN_TZ).replace(tzinfo=None)


def _parse_time(value: str) -> Optional[datetime]:
    """DNSE time strings ("2026-11-10 10:51:59.953") are Vietnam time."""
    try:
        return datetime.strptime(value[:19], "%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError):
        return None


def _main_board(rows: list) -> Optional[dict]:
    return next((r for r in rows or [] if r.get("boardId") == MAIN_BOARD), None)


def _ohlc(symbol: str, kind: str, resolution: str, start: int, end: int) -> List[dict]:
    body = dnse.client().get("/price/ohlc", {"symbol": symbol, "type": kind, "resolution": resolution,
                                             "from": start, "to": end})
    keys = ("t", "o", "h", "l", "c", "v")
    columns = [body.get(k) or [] for k in keys]
    return [{"t": t, "open": o, "high": h, "low": l, "close": c, "volume": int(v)}
            for t, o, h, l, c, v in zip(*columns)]


# ---------------------------------------------------------------- /stock/* engine

def daily_bars(symbol: str, start: str, end: str) -> List[dict]:
    """Daily sessions, oldest first. DNSE adds a session's bar only after it ends."""
    rows = _ohlc(symbol, "STOCK", "1D", _epoch(start), _epoch(end, True))
    return [{"date": _local(r["t"]).strftime("%Y-%m-%d"), "open": float(r["open"]), "high": float(r["high"]),
             "low": float(r["low"]), "close": float(r["close"]), "volume": r["volume"]} for r in rows]


def latest_trade(symbol: str) -> Optional[dict]:
    """The session of the last round-lot match: open/high/low so far, last price, volume, time.

    One call gives today's bar while the session runs (the daily history stops at yesterday).
    None if the symbol has no match yet.
    """
    row = _main_board(dnse.client().get(f"/price/{symbol}/trades/latest").get("trades"))
    at = _parse_time(row.get("time")) if row else None
    if not row or at is None or not row.get("openPrice") or not row.get("matchPrice"):
        return None
    return {"date": at.strftime("%Y-%m-%d"), "open": float(row["openPrice"]), "high": float(row["highestPrice"]),
            "low": float(row["lowestPrice"]), "close": float(row["matchPrice"]),
            "volume": int(row["totalVolumeTraded"]) * LOT_UNIT, "at": at}


def listing() -> Dict[str, dict]:
    """Listed stocks and funds: symbol -> {"name", "nameEn", "exchange", "type"}."""
    out: Dict[str, dict] = {}
    page = 1
    while True:
        body = dnse.client().get("/market/instruments", {"page": page, "pageSize": INSTRUMENT_PAGE})
        for row in body.get("data") or []:
            exchange = EXCHANGES.get(row.get("marketId"))
            kind = LISTED_GROUPS.get(row.get("securityGroupId"))
            symbol = (row.get("symbol") or "").strip().upper()
            if exchange and kind and symbol:
                out[symbol] = {"name": (row.get("name") or row.get("shortName") or symbol).strip(),
                               "nameEn": None, "exchange": exchange, "type": kind}
        total = body.get("total") or 0
        if page * INSTRUMENT_PAGE >= total or not body.get("data"):
            return out
        page += 1


# ---------------------------------------------------------------- other endpoints

def candles(kind: str, symbol: str, start: Optional[str], end: Optional[str], interval: str,
            limit: Optional[int]) -> List[dict]:
    """OHLCV candles, oldest first. kind = "stock" or "index"."""
    today = datetime.now(VN_TZ).strftime("%Y-%m-%d")
    end = end or today
    if not start:
        start = (datetime.strptime(end, "%Y-%m-%d") - timedelta(days=LOOKBACK_DAYS[interval])).strftime("%Y-%m-%d")
        limit = limit or 100
    if kind == "index":
        symbol = INDEX_NAMES.get(symbol, symbol)
    rows = _ohlc(symbol, "INDEX" if kind == "index" else "STOCK", RESOLUTIONS[interval],
                 _epoch(start), _epoch(end, True))
    daily = interval in ("1D", "1W")
    out = [{"time": _local(r["t"]).strftime("%Y-%m-%d") if daily else _local(r["t"]).isoformat(),
            "open": r["open"], "high": r["high"], "low": r["low"], "close": r["close"], "volume": r["volume"]}
           for r in rows]
    return out[-limit:] if limit else out


def price_board(symbol: str) -> Optional[dict]:
    """Official reference/ceiling/floor of the day + 3 best bid/ask levels (main board)."""
    limits = _main_board(dnse.client().get(f"/price/{symbol}/secdef"))
    book = _main_board(dnse.client().get(f"/price/{symbol}/quotes/latest").get("quotes"))
    if not limits and not book:
        return None

    def levels(side):
        return [{"price": x["price"], "volume": int(x["quantity"]) * LOT_UNIT} for x in (book or {}).get(side) or []]

    stamp = _parse_time((limits or {}).get("time"))
    return {
        "symbol": symbol,
        "exchange": EXCHANGES.get((limits or book).get("marketId")),
        "trading_date": stamp.strftime("%Y-%m-%d") if stamp else None,
        "reference_price": (limits or {}).get("basicPrice"),
        "ceiling_price": (limits or {}).get("ceilingPrice"),
        "floor_price": (limits or {}).get("floorPrice"),
        "status": (limits or {}).get("securityStatus"),
        "bid": levels("bid"),
        "ask": levels("offer"),
        "time": _parse_time(book["time"]).isoformat() if book and _parse_time(book.get("time")) else None,
    }


def foreign_flow(symbol: str, start: Optional[str], end: Optional[str]) -> List[dict]:
    """Foreign buy/sell per day (shares and VND), oldest first. One request per weekday."""
    last = datetime.strptime(end, "%Y-%m-%d") if end else datetime.now(VN_TZ).replace(tzinfo=None)
    first = datetime.strptime(start, "%Y-%m-%d") if start else last - timedelta(days=9)
    first = max(first, last - timedelta(days=MAX_FOREIGN_DAYS - 1))
    out = []
    day = first
    while day <= last:
        if day.weekday() < 5:
            stamp = day.strftime("%Y-%m-%d")
            body = dnse.client().get(f"/price/{symbol}/foreign-trading",
                                     {"from": _epoch(stamp), "to": _epoch(stamp, True), "limit": 1})
            rows = body.get("foreigners") or []
            if rows:   # newest first, totals are cumulative for the day
                r = rows[0]
                buy, sell = int(r.get("totalBuyVolume") or 0), int(r.get("totalSellVolume") or 0)
                buy_value, sell_value = int(r.get("totalBuyTradedAmount") or 0), int(r.get("totalSellTradedAmount") or 0)
                out.append({"date": stamp, "buy_volume": buy, "sell_volume": sell, "net_volume": buy - sell,
                            "buy_value": buy_value, "sell_value": sell_value, "net_value": buy_value - sell_value,
                            "room": r.get("foreignerBuyPossibleQuantity")})
        day += timedelta(days=1)
    return out


def foreign_days(start: Optional[str], end: Optional[str]) -> int:
    """Upstream calls foreign_flow will make (for the budget)."""
    last = datetime.strptime(end, "%Y-%m-%d") if end else datetime.now(VN_TZ).replace(tzinfo=None)
    first = datetime.strptime(start, "%Y-%m-%d") if start else last - timedelta(days=9)
    first = max(first, last - timedelta(days=MAX_FOREIGN_DAYS - 1))
    return max(1, sum(1 for i in range((last - first).days + 1) if (first + timedelta(days=i)).weekday() < 5))
