# Vietnam Stock

[![Tests](https://github.com/tran-minh-khoi/viet-nam-stock/actions/workflows/test.yml/badge.svg)](https://github.com/tran-minh-khoi/viet-nam-stock/actions/workflows/test.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A lightweight FastAPI service that serves real-time and historical Vietnamese stock market data, built on top of [vnstock](https://github.com/thinh-vu/vnstock). Point it at a ticker and get today's price action, recent sessions, or any date range back as JSON.

## Quick start

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python api.py
```

The API starts at `http://localhost:8000` (interactive docs at `http://localhost:8000/docs`).

### Configuration

All settings are optional environment variables (see `config.py` for defaults):

| Variable | Default | Purpose |
|---|---|---|
| `API_HOST` | `0.0.0.0` | Bind address |
| `API_PORT` | `8000` | Bind port |
| `CORS_ORIGINS` | `*` | Comma-separated list of allowed origins |
| `CACHE_TTL` | `15` | Seconds to cache a response before refetching |
| `CACHE_NAMESPACE` | `stock_api` | Prefix for cache keys |
| `REDIS_URL` | `redis://127.0.0.1:6379/0` | Redis connection for shared caching (falls back to an in-process dict if Redis isn't reachable) |
| `LOG_LEVEL` | `INFO` | Logging verbosity |

## API Endpoints

### 1. Today's data for a symbol

```
GET /stock/{symbol}
```

Returns today's session plus the previous session's close/volume for comparison.

```
GET /stock/VCB
GET /stock/VNM
```

### 2. Recent sessions for a symbol

```
GET /stock/{symbol}/recent?days={days}
GET /stock/{symbol}?recent={days}
```

- `days`: number of trading sessions to return (default: 7)

```
GET /stock/VCB/recent?days=10
GET /stock/PDR?recent=5
```

### 3. A specific date range

```
GET /stock/{symbol}/day-range?start_date={start_date}&end_date={end_date}
```

- Dates use `YYYY-MM-DD` format.

```
GET /stock/VCB/day-range?start_date=2025-01-01&end_date=2025-01-31
```

### 4. Health check

```
GET /health
```

## Response shapes

### `GET /stock/{symbol}`

```json
{
  "symbol": "VCB",
  "name": "VCB",
  "exchange": "HOSE",
  "currentPrice": 61.2,
  "referencePrice": 60.3,
  "upperPrice": 64.5,
  "lowerPrice": 56.1,
  "todayOpen": 60.4,
  "todayHigh": 61.3,
  "todayLow": 60.3,
  "todayVolume": 1774600,
  "todayDate": "2025-07-16",
  "previousClose": 60.3,
  "previousVolume": 2522300,
  "previousDate": "2025-07-15",
  "lastUpdated": "2025-07-16T12:34:56.789012",
  "data": {
    "today": {
      "date": "2025-07-16",
      "open": 60.4,
      "close": 61.2,
      "high": 61.3,
      "low": 60.3,
      "volume": 1774600,
      "current_price": 61.2,
      "reference_price": 60.3,
      "ceiling": 64.5,
      "floor": 56.1,
      "is_today": true
    },
    "previous": {
      "date": "2025-07-15",
      "close": 60.3,
      "volume": 2522300
    }
  },
  "timestamp": "2025-07-16T12:34:56.789012"
}
```

`ceiling`/`floor` are the day's price limits, computed from the previous close per HOSE tick-size rules (±7%, rounded to the valid tick).

### `GET /stock/{symbol}/recent`

```json
{
  "symbol": "VCB",
  "days": 7,
  "actual_sessions": 7,
  "sessions": [
    {
      "date": "2025-07-10",
      "open": 19.25,
      "close": 19.1,
      "high": 19.65,
      "low": 19.0,
      "volume": 18183200,
      "reference_price": 19.4,
      "ceiling": 20.44,
      "floor": 17.76,
      "is_today": false
    }
  ],
  "timestamp": "2025-07-16T12:34:56.789012"
}
```

## Deploying

### Railway (or any Procfile-based platform)

`Procfile`, `requirements.txt`, and `runtime.txt` are already set up — push to GitHub and connect the repo on Railway; it builds and deploys automatically.

### VPS with PM2

```bash
cp .env.example .env   # fill in APP_MODULE, APP_PORT, etc.
bash deploy.sh
```

`deploy.sh` creates a virtualenv, installs dependencies, and starts/restarts the app under PM2 using `ecosystem.config.js` (which runs `start.sh`, a gunicorn + uvicorn-worker server).

## Testing

```bash
pip install pytest
pytest tests/
```

## About

Built on [vnstock](https://github.com/thinh-vu/vnstock). Contributions welcome — open an issue or a PR.

### License

[MIT](LICENSE)

### Author

Created by Tran Minh Khoi — [tranminhkhoi.dev](https://tranminhkhoi.dev)
