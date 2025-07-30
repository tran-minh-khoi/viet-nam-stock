# Stock Data API

API providing Vietnamese stock market data, focusing on recent trading sessions.

## API Endpoints

### 1. Get today's data for a stock symbol

```
GET /stock/{symbol}
```

- `{symbol}`: Stock symbol (default: PDR)

Returns today's and yesterday's data, including price and trading volume.

Example:
```
GET /stock/VCB
GET /stock/PDR
```

### 2. Get data for multiple recent days of a stock symbol

Two ways:

```
GET /stock/{symbol}?recent={days}
GET /stock/{symbol}/recent?days={days}
```

- `{symbol}`: Stock symbol (default: PDR)
- `{days}`: Number of sessions to retrieve (default: 7)

Example:
```
GET /stock/VCB?recent=10
GET /stock/PDR/recent?days=5
```

### 3. Get data for a specific date range

```
GET /stock/{symbol}/day-range?start_date={start_date}&end_date={end_date}
```

- `{symbol}`: Stock symbol
- `{start_date}`: Start date (format YYYY-MM-DD)
- `{end_date}`: End date (format YYYY-MM-DD)

Example:
```
GET /stock/VCB/day-range?start_date=2025-01-01&end_date=2025-01-31
```

### 4. Check API status

```
GET /health
```

## Response Data Description

### Today's data `/stock/{symbol}`

```json
{
  "symbol": "PDR",
  "data": {
    "today": {
      "date": "2025-07-16",
      "open": 19.35,
      "close": 20.05,
      "high": 20.2,
      "low": 19.3,
      "volume": 13756700,
      "current_price": 20.05
    },
    "yesterday": {
      "date": "2025-07-15",
      "close": 19.4,
      "volume": 15996300
    }
  },
  "timestamp": "2025-07-16T12:34:56.789012"
}
```

### Multiple days data `/stock/{symbol}/recent`

```json
{
  "symbol": "PDR",
  "days": 7,
  "sessions": [
    {
      "date": "2025-07-10",
      "open": 19.25,
      "close": 19.1,
      "high": 19.65,
      "low": 19.0,
      "volume": 18183200,
      "ceiling": 20.44,
      "floor": 17.76,
      "is_today": false
    },
    // ... other sessions
    {
      "date": "2025-07-16",
      "open": 19.35,
      "close": 20.05,
      "high": 20.2,
      "low": 19.3,
      "volume": 13756700,
      "ceiling": 21.45,
      "floor": 18.65,
      "is_today": true,
      "current_price": 20.05
    }
  ],
  "timestamp": "2025-07-16T12:34:56.789012"
}
```

## Running the API locally

```bash
# Setup Python virtual environment and install dependencies
bash setup.sh

# Run the API
python api.py
```

The API will run at `http://localhost:8000`

## Deploying to Railway

1. Ensure configuration files are in place: `Procfile`, `requirements.txt`, `runtime.txt`
2. Push code to GitHub
3. Connect with Railway and deploy from GitHub repository
4. Railway will automatically build and deploy the application

## About

This API is built with vnstock integration, ready to run right out of the box.

### Author
Created by Tran Minh Khoi

Portfolio: [tranminhkhoi.dev](https://tranminhkhoi.dev)

### Support the Project
If you find this API useful, you can buy me a coffee via PayPal.
[PayPal link will be added] 