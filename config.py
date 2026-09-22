import os
from typing import List

class Settings:
    # API Configuration
    API_HOST: str = os.getenv("API_HOST", "0.0.0.0")
    API_PORT: int = int(os.getenv("API_PORT", "8000"))

    # CORS Configuration
    CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:8080",
        "https://your-frontend-domain.com",
        "*"  # Cho phép tất cả origins (chỉ dùng cho development)
    ]

    # API Keys và Authentication
    API_KEY: str = os.getenv("API_KEY", "your-secret-api-key")

    # External APIs
    VIETSTOCK_API_URL: str = "https://finance.vietstock.vn/data/financeinfo"
    CAFEF_API_URL: str = "https://s.cafef.vn/Ajax/PageNew/DataHistory/PriceHistory.ashx"
    TCBS_API_URL: str = "https://apipubaws.tcbs.com.vn/stock-insight/v1/stock"

    # Request Configuration
    REQUEST_TIMEOUT: int = 10
    MAX_RETRIES: int = 3

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

    # Stock Market Hours (Vietnam timezone)
    MARKET_OPEN_MORNING: str = "09:00"
    MARKET_CLOSE_MORNING: str = "11:30"
    MARKET_OPEN_AFTERNOON: str = "13:00"
    MARKET_CLOSE_AFTERNOON: str = "15:00"

    # Default symbols
    DEFAULT_SYMBOLS: List[str] = [
        "PDR",  # Phát Đạt Real Estate
        "VIC",  # Vingroup
        "VHM",  # Vinhomes
        "VNM",  # Vinamilk
        "HPG",  # Hoa Phat Group
    ]

settings = Settings()