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

    # ── Upstream budget ───────────────────────────────────────────────
    # DNSE calls per minute this API allows itself, so a burst of users cannot use up the key's
    # hourly/daily limits. Part of it is kept for PRIORITY_SYMBOLS.
    BUDGET_PER_MINUTE: int = int(os.getenv("BUDGET_PER_MINUTE", "60"))
    BUDGET_RESERVED_FOR_PRIORITY: int = int(os.getenv("BUDGET_RESERVED_FOR_PRIORITY", "6"))

    # ── /stock/* engine ───────────────────────────────────────────────
    # Symbols refreshed in the background even when nobody asks (first one is reported in /health)
    PRIORITY_SYMBOLS: List[str] = _list("PRIORITY_SYMBOLS")
    # Short display names that replace "name" in /stock/* ("fullName" keeps the listed name)
    SHORT_NAMES: Dict[str, str] = _pairs("SHORT_NAMES")
    # Optional JSON file {"SYMBOL": {"name", "nameEn", "exchange"}} that wins over DNSE's names
    # (DNSE has no English names)
    NAMES_FILE: str = os.getenv("NAMES_FILE", "")
    # Optional JSON file where the last good data of every cached symbol (+ the symbol list) is kept,
    # so a restart answers at once even if the source is down. Written at most every 30 s.
    SNAPSHOT_FILE: str = os.getenv("SNAPSHOT_FILE", "")
    # Seconds a cached symbol counts as fresh
    TTL_TRADING_PRIORITY: int = int(os.getenv("TTL_TRADING_PRIORITY", "20"))
    TTL_TRADING: int = int(os.getenv("TTL_TRADING", "30"))
    TTL_OFF_HOURS: int = int(os.getenv("TTL_OFF_HOURS", "300"))
    MAX_RECENT: int = int(os.getenv("MAX_RECENT", "30"))
    MAX_BATCH: int = int(os.getenv("MAX_BATCH", "10"))

    # ── Cache for the other endpoints (seconds) ───────────────────────
    CACHE_TTL: int = int(os.getenv("CACHE_TTL", "15"))
    CACHE_TTL_HISTORY: int = int(os.getenv("CACHE_TTL_HISTORY", "300"))
    CACHE_TTL_REFERENCE: int = int(os.getenv("CACHE_TTL_REFERENCE", "3600"))


settings = Settings()
