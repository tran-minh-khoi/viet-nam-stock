import os
from typing import List


def _list(name: str, default: str = "") -> List[str]:
    return [s.strip().upper() for s in os.getenv(name, default).split(",") if s.strip()]


class Settings:
    API_HOST: str = os.getenv("API_HOST", "0.0.0.0")
    API_PORT: int = int(os.getenv("API_PORT", "8000"))

    # Public read-only API with no cookies/auth, so a wildcard is fine
    CORS_ORIGINS: List[str] = os.getenv("CORS_ORIGINS", "*").split(",")

    # vnstock account. Empty = guest tier (10 calls/min, 8 data features).
    # Free key: register at https://vnstocks.com
    VNSTOCK_API_KEY: str = os.getenv("VNSTOCK_API_KEY", "").strip()
    # Data source for prices: KBS or VCI (the two the guest tier allows)
    DATA_SOURCE: str = os.getenv("DATA_SOURCE", "KBS").upper()

    # Cache: every vnstock call counts against your quota, so cache aggressively.
    CACHE_TTL: int = int(os.getenv("CACHE_TTL", "15"))                  # live prices
    CACHE_TTL_HISTORY: int = int(os.getenv("CACHE_TTL_HISTORY", "300"))  # OHLCV history
    CACHE_TTL_REFERENCE: int = int(os.getenv("CACHE_TTL_REFERENCE", "86400"))  # company info, symbol lists
    CACHE_NAMESPACE: str = os.getenv("CACHE_NAMESPACE", "stock_api")
    # Optional. Without Redis the cache lives in memory (lost on restart).
    REDIS_URL: str = os.getenv("REDIS_URL", "")

    # Symbols whose /stock/{symbol} price comes from the live trade tape.
    # Needs a vnstock tier that includes "trades"; ignored on guest tier.
    FAST_SYMBOLS: List[str] = _list("FAST_SYMBOLS")
    DEFAULT_HISTORY_DAYS: int = 14

    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()


settings = Settings()
