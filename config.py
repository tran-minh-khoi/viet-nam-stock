import os
from typing import List

class Settings:
    # API Configuration
    API_HOST: str = os.getenv("API_HOST", "0.0.0.0")
    API_PORT: int = int(os.getenv("API_PORT", "8000"))

    # CORS Configuration - public read-only API, no cookies/auth, so a plain
    # wildcard is enough (mixing "*" with allow_credentials=True is invalid per spec)
    CORS_ORIGINS: List[str] = os.getenv("CORS_ORIGINS", "*").split(",")

    # Cache Configuration
    CACHE_TTL: int = int(os.getenv("CACHE_TTL", "15"))  # seconds
    CACHE_NAMESPACE: str = os.getenv("CACHE_NAMESPACE", "stock_api")
    CACHE_BACKEND: str = os.getenv("CACHE_BACKEND", "redis")
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
    FAST_SYMBOLS: List[str] = ["PDR"]
    DEFAULT_HISTORY_DAYS: int = 14
    PDR_HISTORY_DAYS: int = 14

    # Logging
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

settings = Settings()