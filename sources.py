"""Every call to vnstock lives here, so tests can swap this module for fakes.

Functions run in worker threads (vnstock is synchronous). Prices from Market.*.ohlcv and
trades are in thousand VND, like vnstock 5.
"""
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import pandas as pd
from vnstock import Fundamental, Market, Reference

from config import settings

# Exchange names vary by source; the API always answers with these three
EXCHANGE_ALIASES = {"HSX": "HOSE", "HOSE": "HOSE", "HNX": "HNX", "UPCOM": "UPCOM", "UPC": "UPCOM"}
LISTED_TYPES = {"stock", "etf", "fund", "fund_certificate"}

_market: Dict[str, Market] = {}
_reference: Dict[str, Reference] = {}


def market(source: str) -> Market:
    if source not in _market:
        _market[source] = Market(source)
    return _market[source]


def reference(source: str) -> Reference:
    if source not in _reference:
        _reference[source] = Reference(source)
    return _reference[source]


def _naive_local(value) -> datetime:
    """Timestamp -> naive datetime in Vietnam time (the server clock the API compares with)."""
    ts = pd.Timestamp(value)
    if ts.tzinfo is not None:
        ts = ts.tz_convert("Asia/Ho_Chi_Minh").tz_localize(None)
    return ts.to_pydatetime()


# ---------------------------------------------------------------- /stock/* engine

def daily_bars(symbol: str, start: str, end: str) -> List[dict]:
    """Daily sessions, oldest first. Empty list = the source has no data for this symbol."""
    df = market(settings.DATA_SOURCE).equity(symbol).ohlcv(start=start, end=end, interval="1D")
    if df is None or df.empty:
        return []
    df = df.sort_values("time", ascending=True)
    return [{
        "date": _naive_local(row["time"]).strftime("%Y-%m-%d"),
        "open": float(row["open"]),
        "high": float(row["high"]),
        "low": float(row["low"]),
        "close": float(row["close"]),
        "volume": int(row["volume"]),
    } for _, row in df.iterrows()]


def last_trade(symbol: str) -> Optional[Tuple[float, Optional[datetime]]]:
    """(price, time) of the latest match, from the last 1-minute candle.

    Not from trades(): DNSE pages the tape from the start of the session, so reaching the last
    trade takes seconds (up to 500 pages late in the day). The last 1m candle's close is the
    last matched price and costs one small call.
    """
    df = market(settings.DATA_SOURCE).equity(symbol).ohlcv(interval="1m", limit=1)
    if df is None or df.empty:
        return None
    df = df.sort_values("time", ascending=True)
    return float(df["close"].iloc[-1]), _naive_local(df["time"].iloc[-1])


def text(value) -> Optional[str]:
    """Cell -> stripped string, or None for empty / NaN / pd.NA (vnstock 6 uses nullable dtypes)."""
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return None
    value = str(value).strip()
    return value or None


def normalize_exchange(raw) -> Optional[str]:
    return EXCHANGE_ALIASES.get((text(raw) or "").upper())


def listing() -> Dict[str, dict]:
    """Listed stocks and ETFs: symbol -> {"name", "nameEn", "exchange", "type"}."""
    ref = reference(settings.DATA_SOURCE)
    frames = [ref.equity.list(), ref.etf.list()]
    out: Dict[str, dict] = {}
    for frame in frames:
        if frame is None or frame.empty:
            continue
        for _, row in frame.iterrows():
            kind = (text(row.get("type")) or "").lower()
            exchange = normalize_exchange(row.get("exchange"))
            symbol = (text(row.get("symbol")) or "").upper()
            if kind not in LISTED_TYPES or exchange is None or not symbol:
                continue
            out[symbol] = {
                "name": text(row.get("organ_name")) or symbol,
                "nameEn": text(row.get("name_en")),
                "exchange": exchange,
                "type": "stock" if kind == "stock" else "fund",
            }
    return out


# ---------------------------------------------------------------- other endpoints (DataFrames)

def ohlcv(kind: str, symbol: str, start=None, end=None, interval="1D", limit=None) -> pd.DataFrame:
    target = getattr(market(settings.DATA_SOURCE), kind)(symbol)
    kwargs = {"start": start, "end": end, "interval": interval}
    if limit:
        kwargs["limit"] = limit
    return target.ohlcv(**kwargs)


def price_limits(symbol: str) -> pd.DataFrame:
    """Official reference/ceiling/floor for today, one row per board (G1 = main board)."""
    return reference(settings.DATA_SOURCE).equity(symbol).price_limits()


ORDER_BOOK_PRICES = [f"{side}_price_{i}" for side in ("bid", "ask") for i in (1, 2, 3)]
ORDER_BOOK_VOLUMES = [f"{side}_vol_{i}" for side in ("bid", "ask") for i in (1, 2, 3)]


def order_book(symbol: str) -> pd.DataFrame:
    """3 best bid/ask levels of the main board, prices in thousand VND.

    DNSE returns one row per board (odd lot and round lot) without naming it, and prices in VND:
    keep the row with the most volume (round lot) and divide prices by 1000.
    """
    df = market(settings.QUOTE_SOURCE).equity(symbol).order_book()
    if df is None or df.empty or settings.QUOTE_SOURCE != "dnse":
        return df
    df = df.copy()
    volumes = [c for c in ORDER_BOOK_VOLUMES if c in df.columns]
    if volumes and len(df) > 1:
        df = df.loc[[df[volumes].fillna(0).sum(axis=1).idxmax()]]
    for col in ORDER_BOOK_PRICES:
        if col in df.columns:
            df[col] = (df[col] / 1000).round(2)
    return df.reset_index(drop=True)


def board(symbols: List[str]) -> pd.DataFrame:
    """Full price board (fhsc/tcbs only)."""
    return market(settings.QUOTE_SOURCE).equity.quote(",".join(symbols))


def trades(symbol: str, limit: int) -> pd.DataFrame:
    return market(settings.DATA_SOURCE).equity(symbol).trades(limit=limit)


def foreign_flow(symbol: str, start=None, end=None) -> pd.DataFrame:
    """Foreign buy/sell per day. DNSE sends the day's total first, then the day's single trades:
    keep the first row of each day."""
    df = market(settings.DATA_SOURCE).equity(symbol).foreign_flow(start=start, end=end, interval="1D")
    if df is None or df.empty or "time" not in df.columns:
        return df
    return df.drop_duplicates(subset=["time"], keep="first").sort_values("time").reset_index(drop=True)


def symbols() -> pd.DataFrame:
    return reference(settings.DATA_SOURCE).equity.list()


def company(symbol: str, section: str) -> pd.DataFrame:
    return getattr(reference(settings.COMPANY_SOURCE).company(symbol), section)()


def financial(symbol: str, report: str, period: Optional[str]) -> pd.DataFrame:
    return getattr(Fundamental(settings.COMPANY_SOURCE).equity(symbol), report)(period=period)


def index_list() -> pd.DataFrame:
    return reference(settings.INDEX_SOURCE).index.list()


def index_members(symbol: str) -> pd.DataFrame:
    return reference(settings.INDEX_SOURCE).index(symbol).members()


def group_members(group: str) -> pd.DataFrame:
    return reference(settings.INDEX_SOURCE).equity.by_group(group)
