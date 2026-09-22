import time
import json
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
import logging
import asyncio
import math
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import pandas as pd
from vnstock import Vnstock
from config import settings

try:
    import redis
except ImportError:  # pragma: no cover
    redis = None

STOCK_CACHE: Dict[str, Dict[str, object]] = {}

if redis is not None:
    try:
        REDIS_CLIENT = redis.Redis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=1,
            socket_timeout=1,
        )
        REDIS_CLIENT.ping()
    except Exception:
        REDIS_CLIENT = None
else:
    REDIS_CLIENT = None


def cache_key_name(key: str) -> str:
    return f"{settings.CACHE_NAMESPACE}:{key}"


def read_cache(key: str):
    full_key = cache_key_name(key)
    if REDIS_CLIENT is not None:
        try:
            raw = REDIS_CLIENT.get(full_key)
            if raw is None:
                return None
            payload = json.loads(raw)
            if isinstance(payload, dict) and "timestamp" in payload and "data" in payload:
                return payload
            return {"timestamp": time.time(), "data": payload}
        except Exception as exc:
            logger.warning(f"Redis cache read failed for {full_key}: {exc}")

    cached = STOCK_CACHE.get(full_key)
    if not cached:
        return None
    return cached


def write_cache(key: str, payload: dict, ttl: int = None):
    full_key = cache_key_name(key)
    ttl = ttl if ttl is not None else settings.CACHE_TTL
    if REDIS_CLIENT is not None:
        try:
            REDIS_CLIENT.setex(full_key, ttl, json.dumps(payload, default=str))
            return True
        except Exception as exc:
            logger.warning(f"Redis cache write failed for {full_key}: {exc}")

    STOCK_CACHE[full_key] = payload
    return True

# Cấu hình logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Stock Data API",
    description="Real-time stock data API for Vietnamese stock market",
    version="2.1.0"
)

# Cấu hình CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
SOURCE = "KBS"  # KBS, VCI, TCBS, SSI, VNDIRECT,


def is_fast_symbol(symbol: str) -> bool:
    return symbol.upper() in set(settings.FAST_SYMBOLS)


def get_history_window(days: int = 7):
    """Trả về khoảng thời gian mặc định tối ưu cho màn hình stock"""
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=max(7, days))).strftime('%Y-%m-%d')
    return start_date, end_date


def calculate_ceiling_floor(ref_price):
    """
    Tính giá trần sàn theo quy định thị trường chứng khoán Việt Nam
    - Giá trần: làm tròn xuống (floor) để không vượt quá mức cho phép
    - Giá sàn: làm tròn lên (ceil) để không thấp hơn mức cho phép
    """
    if ref_price < 10:
        tick_size = 0.01
    elif ref_price < 50:
        tick_size = 0.05
    elif ref_price < 100:
        tick_size = 0.1
    elif ref_price < 500:
        tick_size = 0.5
    else:
        tick_size = 1.0

    ceiling_raw = ref_price * 1.07
    floor_raw = ref_price * 0.93
    ceiling = math.floor(ceiling_raw / tick_size) * tick_size
    floor = math.ceil(floor_raw / tick_size) * tick_size

    return round(ceiling, 2), round(floor, 2)


def build_stock_snapshot(symbol: str, history_df: pd.DataFrame, current_price: Optional[float] = None) -> dict:
    """Chuẩn hóa payload để trả về đúng business fields cho UI."""
    if history_df is None or history_df.empty:
        return {}

    data = history_df.sort_values('time', ascending=False).copy()
    latest = data.iloc[0]
    previous = data.iloc[1] if len(data) > 1 else latest
    today_str = datetime.now().strftime('%Y-%m-%d')
    today_row = latest if pd.to_datetime(latest['time']).strftime('%Y-%m-%d') == today_str else previous

    reference_price = float(previous['close']) if len(data) > 1 else float(latest['close'])
    if current_price is None:
        current_price = float(latest['close'])

    upper_price, lower_price = calculate_ceiling_floor(reference_price)
    stock_name = "PHÁT ĐẠT" if symbol.upper() == "PDR" else symbol.upper()

    return {
        "name": stock_name,
        "symbol": symbol.upper(),
        "exchange": "HOSE",
        "currentPrice": round(float(current_price), 2),
        "referencePrice": round(reference_price, 2),
        "upperPrice": round(upper_price, 2),
        "lowerPrice": round(lower_price, 2),
        "todayOpen": float(today_row['open']),
        "todayHigh": float(today_row['high']),
        "todayLow": float(today_row['low']),
        "todayVolume": int(today_row['volume']),
        "todayDate": pd.to_datetime(today_row['time']).strftime('%Y-%m-%d'),
        "previousClose": float(previous['close']),
        "previousVolume": int(previous['volume']),
        "previousDate": pd.to_datetime(previous['time']).strftime('%Y-%m-%d'),
        "lastUpdated": datetime.now().isoformat(),
    }


@app.get("/")
async def root():
    return {"message": "Stock Data API is running", "version": "2.1.0"}


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "stock-api"}


@app.get("/stock/{symbol}")
async def get_stock_today(symbol: str = "PDR", recent: Optional[int] = None):
    """
    Lấy dữ liệu ngày hôm nay của một mã chứng khoán
    Nếu có tham số recent, sẽ lấy dữ liệu của n phiên gần đây
    """
    if recent:
        return await get_stock_recent(symbol, recent)

    try:
        symbol = symbol.upper()

        loop = asyncio.get_event_loop()

        def get_stock_data():
            try:
                stock = Vnstock().stock(symbol=symbol, source=SOURCE)
                start_date, end_date = get_history_window(days=settings.PDR_HISTORY_DAYS if is_fast_symbol(symbol) else settings.DEFAULT_HISTORY_DAYS)
                data = stock.quote.history(start=start_date, end=end_date, interval='1D')

                if data.empty:
                    return {}

                current_price = None
                if is_fast_symbol(symbol):
                    try:
                        intraday = stock.quote.intraday()
                        if not intraday.empty:
                            intraday_last = float(intraday['price'].iloc[-1])
                            if 'time' in intraday.columns:
                                last_ts = pd.to_datetime(intraday['time'].iloc[-1])
                                minutes_ago = (datetime.now() - last_ts).total_seconds() / 60.0
                                if minutes_ago <= 10:
                                    current_price = intraday_last
                            else:
                                current_price = intraday_last
                    except Exception:
                        current_price = None

                if current_price is None:
                    current_price = float(data.sort_values('time', ascending=False).iloc[0]['close'])

                result = build_stock_snapshot(symbol, data, current_price)
                if not result:
                    return {}

                result["data"] = {
                    "today": {
                        "date": result["todayDate"],
                        "open": result["todayOpen"],
                        "close": result["currentPrice"],
                        "high": result["todayHigh"],
                        "low": result["todayLow"],
                        "volume": result["todayVolume"],
                        "current_price": result["currentPrice"],
                        "reference_price": result["referencePrice"],
                        "ceiling": result["upperPrice"],
                        "floor": result["lowerPrice"],
                        "is_today": True,
                    },
                    "previous": {
                        "date": result["previousDate"],
                        "close": result["previousClose"],
                        "volume": result["previousVolume"],
                    }
                }

                return result
            except Exception:
                logger.exception("Lỗi khi lấy dữ liệu chứng khoán")
                return {}

        cache_key = f"stock:{symbol.upper()}"
        cached = read_cache(cache_key)
        if cached and (time.time() - cached["timestamp"]) < settings.CACHE_TTL:
            stock_data = cached["data"]
        else:
            stock_data = await loop.run_in_executor(None, get_stock_data)
            write_cache(cache_key, {
                "timestamp": time.time(),
                "data": stock_data,
            })

        if not stock_data:
            raise HTTPException(
                status_code=404, detail=f"Không tìm thấy dữ liệu cho mã {symbol}")

        payload = {
            "symbol": symbol,
            "name": stock_data.get("name", symbol.upper()),
            "exchange": stock_data.get("exchange", "HOSE"),
            "currentPrice": stock_data.get("currentPrice"),
            "referencePrice": stock_data.get("referencePrice"),
            "upperPrice": stock_data.get("upperPrice"),
            "lowerPrice": stock_data.get("lowerPrice"),
            "todayOpen": stock_data.get("todayOpen"),
            "todayHigh": stock_data.get("todayHigh"),
            "todayLow": stock_data.get("todayLow"),
            "todayVolume": stock_data.get("todayVolume"),
            "todayDate": stock_data.get("todayDate"),
            "previousClose": stock_data.get("previousClose"),
            "previousVolume": stock_data.get("previousVolume"),
            "previousDate": stock_data.get("previousDate"),
            "lastUpdated": stock_data.get("lastUpdated"),
            "data": stock_data.get("data", {}),
            "timestamp": datetime.now().isoformat()
        }

        return payload
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi lấy dữ liệu cho {symbol}: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Lỗi nội bộ server: {str(e)}")


@app.get("/stock/{symbol}/recent")
async def get_stock_recent(symbol: str, days: int = 7):
    """
    Lấy dữ liệu n phiên giao dịch gần đây của một mã chứng khoán
    """
    try:
        symbol = symbol.upper()

        # Giữ khoảng dữ liệu tối thiểu cho màn hình đầu tiên, ưu tiên tốc độ
        start_date, end_date = get_history_window(days=max(7, days))

        # Chuyển hàm blocking sang async để không chặn event loop
        loop = asyncio.get_event_loop()

        def get_recent_data():
            try:
                # Lấy dữ liệu lịch sử
                stock = Vnstock().stock(symbol=symbol, source=SOURCE)
                history_df = stock.quote.history(
                    start=start_date, end=end_date, interval='1D')

                if history_df.empty:
                    return []

                # Sort theo thời gian giảm dần và chỉ lấy N phiên gần nhất
                recent_df = history_df.sort_values(
                    'time', ascending=False).head(days)

                # Sort lại theo thời gian tăng dần để hiển thị
                recent_df = recent_df.sort_values('time', ascending=True)

                # Format lại dữ liệu để trả về
                result = []
                today = datetime.now().strftime('%Y-%m-%d')

                # Lấy giá tham chiếu cho từng phiên (giá đóng cửa phiên trước đó)
                all_sessions = history_df.sort_values('time', ascending=False)

                for i, row in recent_df.iterrows():
                    session_date = pd.to_datetime(
                        row['time']).strftime('%Y-%m-%d')

                    # Tìm giá tham chiếu (giá đóng cửa phiên trước đó)
                    reference_price = float(row['close'])  # Mặc định
                    session_index = None

                    for j, prev_row in all_sessions.iterrows():
                        if prev_row['time'].strftime('%Y-%m-%d') == session_date:
                            session_index = j
                            break

                    if session_index is not None:
                        # Tìm phiên trước đó trong all_sessions
                        for k in range(len(all_sessions)):
                            if all_sessions.iloc[k]['time'].strftime('%Y-%m-%d') == session_date:
                                if k + 1 < len(all_sessions):
                                    reference_price = float(
                                        all_sessions.iloc[k + 1]['close'])
                                break

                    ceiling, floor = calculate_ceiling_floor(reference_price)

                    session_data = {
                        'date': session_date,
                        'open': float(row['open']),
                        'close': float(row['close']),
                        'high': float(row['high']),
                        'low': float(row['low']),
                        'volume': int(row['volume']),
                        'reference_price': reference_price,
                        'ceiling': ceiling,
                        'floor': floor,
                        'is_today': session_date == today
                    }

                    # Nếu là phiên hôm nay, lấy thêm giá hiện tại
                    if session_date == today:
                        try:
                            intraday = stock.quote.intraday()
                            if not intraday.empty:
                                session_data['current_price'] = float(
                                    intraday['price'].iloc[-1])
                            else:
                                session_data['current_price'] = float(
                                    row['close'])
                        except:
                            session_data['current_price'] = float(row['close'])

                    result.append(session_data)

                return result
            except Exception as e:
                logger.error(f"Lỗi khi lấy dữ liệu gần đây: {str(e)}")
                return []

        cache_key = f"stock_recent:{symbol.upper()}:{days}"
        cached = read_cache(cache_key)
        if cached and (time.time() - cached["timestamp"]) < settings.CACHE_TTL:
            data = cached["data"]
        else:
            data = await loop.run_in_executor(None, get_recent_data)
            write_cache(cache_key, {
                "timestamp": time.time(),
                "data": data,
            })

        if not data:
            raise HTTPException(
                status_code=404, detail=f"Không tìm thấy dữ liệu cho mã {symbol} trong {days} phiên gần đây")

        return {
            "symbol": symbol,
            "days": days,
            "actual_sessions": len(data),
            "sessions": data,
            "timestamp": datetime.now().isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Lỗi khi lấy dữ liệu phiên giao dịch cho {symbol}: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Lỗi nội bộ server: {str(e)}")


@app.get("/stock/{symbol}/day-range")
async def get_stock_range(
    symbol: str,
    start_date: str = Query(..., description="Ngày bắt đầu (YYYY-MM-DD)"),
    end_date: str = Query(..., description="Ngày kết thúc (YYYY-MM-DD)")
):
    """
    Lấy dữ liệu từ ngày start_date đến ngày end_date
    """
    try:
        symbol = symbol.upper()

        # Xác thực ngày tháng
        try:
            datetime.strptime(start_date, "%Y-%m-%d")
            datetime.strptime(end_date, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(
                status_code=400, detail="Định dạng ngày không hợp lệ. Sử dụng định dạng YYYY-MM-DD")

        # Lấy dữ liệu trong khoảng thời gian
        loop = asyncio.get_event_loop()

        def get_range_data():
            try:
                stock = Vnstock().stock(symbol=symbol, source=SOURCE)

                # Lấy dữ liệu mở rộng để có thể tính giá tham chiếu
                extended_start = (datetime.strptime(
                    start_date, "%Y-%m-%d") - timedelta(days=30)).strftime('%Y-%m-%d')
                all_data = stock.quote.history(
                    start=extended_start, end=end_date, interval='1D')

                if all_data.empty:
                    return []

                # Lọc dữ liệu trong khoảng thời gian yêu cầu
                data = all_data[(all_data['time'] >= start_date)
                                & (all_data['time'] <= end_date)]

                if data.empty:
                    return []

                # Sort theo thời gian tăng dần
                data = data.sort_values('time', ascending=True)
                all_data = all_data.sort_values('time', ascending=False)

                # Chuyển đổi dữ liệu
                result = []
                for _, row in data.iterrows():
                    session_date = row['time'].strftime('%Y-%m-%d')

                    # Tìm giá tham chiếu (giá đóng cửa phiên trước đó)
                    reference_price = float(row['close'])  # Mặc định

                    for j, prev_row in all_data.iterrows():
                        if prev_row['time'].strftime('%Y-%m-%d') == session_date:
                            # Tìm phiên trước đó trong all_data
                            for k in range(len(all_data)):
                                if all_data.iloc[k]['time'].strftime('%Y-%m-%d') == session_date:
                                    if k + 1 < len(all_data):
                                        reference_price = float(
                                            all_data.iloc[k + 1]['close'])
                                    break
                            break

                    ceiling, floor = calculate_ceiling_floor(reference_price)

                    session_data = {
                        'date': session_date,
                        'open': float(row['open']),
                        'close': float(row['close']),
                        'high': float(row['high']),
                        'low': float(row['low']),
                        'volume': int(row['volume']),
                        'reference_price': reference_price,
                        'ceiling': ceiling,
                        'floor': floor
                    }
                    result.append(session_data)

                return result
            except Exception as e:
                logger.error(f"Lỗi khi lấy dữ liệu khoảng thời gian: {str(e)}")
                return []

        cache_key = f"stock_range:{symbol.upper()}:{start_date}:{end_date}"
        cached = read_cache(cache_key)
        if cached and (time.time() - cached["timestamp"]) < settings.CACHE_TTL:
            range_data = cached["data"]
        else:
            range_data = await loop.run_in_executor(None, get_range_data)
            write_cache(cache_key, {
                "timestamp": time.time(),
                "data": range_data,
            })

        if not range_data:
            raise HTTPException(
                status_code=404, detail=f"Không tìm thấy dữ liệu cho mã {symbol} từ {start_date} đến {end_date}")

        return {
            "symbol": symbol,
            "start_date": start_date,
            "end_date": end_date,
            "total_sessions": len(range_data),
            "sessions": range_data,
            "timestamp": datetime.now().isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Lỗi khi lấy dữ liệu khoảng thời gian cho {symbol}: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Lỗi nội bộ server: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.API_HOST, port=settings.API_PORT)
