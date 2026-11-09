"""Settings, read once from environment variables (or a .env file next to this one)."""
import os
from typing import Dict, List


def _list(name: str, default: str = "") -> List[str]:
    return [s.strip().upper() for s in os.getenv(name, default).split(",") if s.strip()]


def _pairs(name: str, default: str = "") -> Dict[str, str]:
    """"PDR=PHÁT ĐẠT;VCB=Vietcombank" -> {"PDR": "PHÁT ĐẠT", "VCB": "Vietcombank"}"""
    out = {}
    for part in os.getenv(name, default).split(";"):
        if "=" in part:
            key, value = part.split("=", 1)
            if key.strip() and value.strip():
                out[key.strip().upper()] = value.strip()
    return out


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    return default if raw is None else raw.strip().lower() in ("1", "true", "yes", "on")


class Settings:
    API_HOST: str = os.getenv("API_HOST", "0.0.0.0")
    API_PORT: int = int(os.getenv("API_PORT", "8000"))
    # Public read-only API with no cookies/auth, so a wildcard is fine
    CORS_ORIGINS: List[str] = os.getenv("CORS_ORIGINS", "*").split(",")
    # /docs, /redoc and /openapi.json. Turn off if you only need the JSON endpoints.
    ENABLE_DOCS: bool = _bool("ENABLE_DOCS", True)
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()

    # ── Data sources (vnstock 6) ──────────────────────────────────────
    # Each source needs its own key, issued by that broker. See docs/vnstock-account.md.
    # Prices, trade tape, symbol list, index candles, foreign flow:
    DATA_SOURCE: str = os.getenv("DATA_SOURCE", "dnse").lower()
    # Price board with 3 bid/ask levels (/quote, /quotes): fhsc or tcbs, or dnse (built from its order book)
    QUOTE_SOURCE: str = os.getenv("QUOTE_SOURCE", "dnse").lower()
    # Company profile, shareholders, financial statements: only fhsc has these
    COMPANY_SOURCE: str = os.getenv("COMPANY_SOURCE", "fhsc").lower()
    # Index list/members and symbol groups (VN30, HNX30...): only ssi has members/groups
    INDEX_SOURCE: str = os.getenv("INDEX_SOURCE", "ssi").lower()

    # ── Upstream budget ───────────────────────────────────────────────
    # Calls per minute this API allows itself across all sources, so a burst of users
    # cannot get your key throttled. Part of it is kept for PRIORITY_SYMBOLS.
    BUDGET_PER_MINUTE: int = int(os.getenv("BUDGET_PER_MINUTE", "30"))
    BUDGET_RESERVED_FOR_PRIORITY: int = int(os.getenv("BUDGET_RESERVED_FOR_PRIORITY", "6"))

    # ── /stock/* engine ───────────────────────────────────────────────
    # Symbols refreshed in the background even when nobody asks (first one is reported in /health)
    PRIORITY_SYMBOLS: List[str] = _list("PRIORITY_SYMBOLS")
    # Short display names that replace "name" in /stock/* ("fullName" keeps the listed name)
    SHORT_NAMES: Dict[str, str] = _pairs("SHORT_NAMES")
    # Optional JSON file {"SYMBOL": {"name", "nameEn", "exchange"}} that wins over the source's names,
    # to keep names identical when you switch sources
    NAMES_FILE: str = os.getenv("NAMES_FILE", "")
    # Seconds a cached symbol counts as fresh
    TTL_TRADING_PRIORITY: int = int(os.getenv("TTL_TRADING_PRIORITY", "20"))
    TTL_TRADING: int = int(os.getenv("TTL_TRADING", "30"))
    TTL_OFF_HOURS: int = int(os.getenv("TTL_OFF_HOURS", "300"))
    MAX_RECENT: int = int(os.getenv("MAX_RECENT", "30"))
    MAX_BATCH: int = int(os.getenv("MAX_BATCH", "10"))

    # ── Cache for the other endpoints (seconds) ───────────────────────
    CACHE_TTL: int = int(os.getenv("CACHE_TTL", "15"))
    CACHE_TTL_HISTORY: int = int(os.getenv("CACHE_TTL_HISTORY", "300"))
    CACHE_TTL_REFERENCE: int = int(os.getenv("CACHE_TTL_REFERENCE", "86400"))
    CACHE_NAMESPACE: str = os.getenv("CACHE_NAMESPACE", "stock_api")
    # Optional. Without Redis the cache lives in memory (lost on restart).
    REDIS_URL: str = os.getenv("REDIS_URL", "")


settings = Settings()
