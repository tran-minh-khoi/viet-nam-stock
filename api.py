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

def calculate_ceiling_floor(ref_price):
    """
    Tính giá trần sàn theo quy định thị trường chứng khoán Việt Nam
    - Giá trần: làm tròn xuống (floor) để không vượt quá mức cho phép  
    - Giá sàn: làm tròn lên (ceil) để không thấp hơn mức cho phép
    """
    # Xác định tick size dựa trên giá tham chiếu
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
    
    # Tính giá trần sàn (±7%)
    ceiling_raw = ref_price * 1.07
    floor_raw = ref_price * 0.93
    
    # Làm tròn theo quy tắc thị trường:
    # - Giá trần: làm tròn xuống (floor)
    # - Giá sàn: làm tròn lên (ceil)
    ceiling = math.floor(ceiling_raw / tick_size) * tick_size
    floor = math.ceil(floor_raw / tick_size) * tick_size
    
    return round(ceiling, 2), round(floor, 2)

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
        
        # Hàm lấy dữ liệu phiên hôm nay và phiên gần nhất trước đó
        def get_stock_data():
            try:
                stock = Vnstock().stock(symbol=symbol, source='VCI')
                
                # Lấy dữ liệu 60 ngày gần đây để đảm bảo có đủ phiên giao dịch
                end_date = datetime.now().strftime('%Y-%m-%d')
                start_date = (datetime.now() - timedelta(days=60)).strftime('%Y-%m-%d')
                
                data = stock.quote.history(start=start_date, end=end_date, interval='1D')
                
                if data.empty:
                    return {}
                
                # Sort theo thời gian giảm dần (phiên mới nhất đầu tiên)
                data = data.sort_values('time', ascending=False)
                
                # Lấy giá realtime nếu có
                current_price = None
                try:
                    intraday = stock.quote.intraday()
                    if not intraday.empty:
                        current_price = intraday['price'].iloc[-1]
                except:
                    pass
                
                result = {}
                today_str = datetime.now().strftime('%Y-%m-%d')
                
                # Tìm phiên hôm nay
                today_data = None
                for i, row in data.iterrows():
                    if row['time'].strftime('%Y-%m-%d') == today_str:
                        today_data = row
                        break
                
                # Nếu không có phiên hôm nay, lấy phiên gần nhất
                if today_data is None:
                    today_data = data.iloc[0]
                
                # Tính giá tham chiếu (là giá đóng cửa phiên trước đó)
                reference_price = float(today_data['close'])
                
                # Tìm phiên trước đó để lấy giá tham chiếu chính xác
                previous_data = None
                today_index = None
                for i, row in data.iterrows():
                    if row['time'].strftime('%Y-%m-%d') == today_data['time'].strftime('%Y-%m-%d'):
                        today_index = i
                        break
                
                if today_index is not None and len(data) > 1:
                    # Tìm phiên gần nhất trước phiên hôm nay
                    for i in range(len(data)):
                        if data.iloc[i]['time'].strftime('%Y-%m-%d') == today_data['time'].strftime('%Y-%m-%d'):
                            if i + 1 < len(data):
                                previous_data = data.iloc[i + 1]
                                reference_price = float(previous_data['close'])
                            break
                
                ceiling, floor = calculate_ceiling_floor(reference_price)
                
                # Dữ liệu phiên hôm nay/gần nhất
                result["today"] = {
                    "date": today_data['time'].strftime('%Y-%m-%d'),
                    "open": float(today_data['open']),
                    "close": float(today_data['close']),
                    "high": float(today_data['high']),
                    "low": float(today_data['low']),
                    "volume": int(today_data['volume']),
                    "current_price": float(current_price) if current_price else float(today_data['close']),
                    "reference_price": reference_price,
                    "ceiling": ceiling,
                    "floor": floor,
                    "is_today": today_data['time'].strftime('%Y-%m-%d') == today_str
                }
                
                # Dữ liệu phiên gần nhất trước đó
                if previous_data is not None:
                    result["previous"] = {
                        "date": previous_data['time'].strftime('%Y-%m-%d'),
                        "close": float(previous_data['close']),
                        "volume": int(previous_data['volume']),
                        "open": float(previous_data['open']),
                        "high": float(previous_data['high']),
                        "low": float(previous_data['low'])
                    }
                
                return result
            except Exception as e:
                logger.error(f"Lỗi khi lấy dữ liệu chứng khoán: {str(e)}")
                return {}
        
        # Lấy dữ liệu
        stock_data = await loop.run_in_executor(None, get_stock_data)
        
        if not stock_data:
            raise HTTPException(status_code=404, detail=f"Không tìm thấy dữ liệu cho mã {symbol}")
        
        return {
            "symbol": symbol,
            "data": stock_data,
            "timestamp": datetime.now().isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi lấy dữ liệu cho {symbol}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Lỗi nội bộ server: {str(e)}")

@app.get("/stock/{symbol}/recent")
async def get_stock_recent(symbol: str, days: int = 7):
    """
    Lấy dữ liệu n phiên giao dịch gần đây của một mã chứng khoán
    """
    try:
        symbol = symbol.upper()
        
        # Lấy dữ liệu trong khoảng thời gian dài để đảm bảo có đủ phiên giao dịch
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=max(60, days * 3))).strftime('%Y-%m-%d')
        
        # Chuyển hàm blocking sang async để không chặn event loop
        loop = asyncio.get_event_loop()
        
        def get_recent_data():
            try:
                # Lấy dữ liệu lịch sử
                stock = Vnstock().stock(symbol=symbol, source='VCI')
                history_df = stock.quote.history(start=start_date, end=end_date, interval='1D')
                
                if history_df.empty:
                    return []
                    
                # Sort theo thời gian giảm dần và chỉ lấy N phiên gần nhất
                recent_df = history_df.sort_values('time', ascending=False).head(days)
                
                # Sort lại theo thời gian tăng dần để hiển thị
                recent_df = recent_df.sort_values('time', ascending=True)
                
                # Format lại dữ liệu để trả về
                result = []
                today = datetime.now().strftime('%Y-%m-%d')
                
                # Lấy giá tham chiếu cho từng phiên (giá đóng cửa phiên trước đó)
                all_sessions = history_df.sort_values('time', ascending=False)
                
                for i, row in recent_df.iterrows():
                    session_date = pd.to_datetime(row['time']).strftime('%Y-%m-%d')
                    
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
                                    reference_price = float(all_sessions.iloc[k + 1]['close'])
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
                                session_data['current_price'] = float(intraday['price'].iloc[-1])
                            else:
                                session_data['current_price'] = float(row['close'])
                        except:
                            session_data['current_price'] = float(row['close'])
                    
                    result.append(session_data)
                    
                return result
            except Exception as e:
                logger.error(f"Lỗi khi lấy dữ liệu gần đây: {str(e)}")
                return []
        
        data = await loop.run_in_executor(None, get_recent_data)
        
        if not data:
            raise HTTPException(status_code=404, detail=f"Không tìm thấy dữ liệu cho mã {symbol} trong {days} phiên gần đây")
        
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
        logger.error(f"Lỗi khi lấy dữ liệu phiên giao dịch cho {symbol}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Lỗi nội bộ server: {str(e)}")

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
            raise HTTPException(status_code=400, detail="Định dạng ngày không hợp lệ. Sử dụng định dạng YYYY-MM-DD")
        
        # Lấy dữ liệu trong khoảng thời gian
        loop = asyncio.get_event_loop()
        
        def get_range_data():
            try:
                stock = Vnstock().stock(symbol=symbol, source='VCI')
                
                # Lấy dữ liệu mở rộng để có thể tính giá tham chiếu
                extended_start = (datetime.strptime(start_date, "%Y-%m-%d") - timedelta(days=30)).strftime('%Y-%m-%d')
                all_data = stock.quote.history(start=extended_start, end=end_date, interval='1D')
                
                if all_data.empty:
                    return []
                
                # Lọc dữ liệu trong khoảng thời gian yêu cầu
                data = all_data[(all_data['time'] >= start_date) & (all_data['time'] <= end_date)]
                
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
                                        reference_price = float(all_data.iloc[k + 1]['close'])
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
        
        # Lấy dữ liệu trong khoảng thời gian
        range_data = await loop.run_in_executor(None, get_range_data)
        
        if not range_data:
            raise HTTPException(status_code=404, detail=f"Không tìm thấy dữ liệu cho mã {symbol} từ {start_date} đến {end_date}")
        
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
        logger.error(f"Lỗi khi lấy dữ liệu khoảng thời gian cho {symbol}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Lỗi nội bộ server: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.API_HOST, port=settings.API_PORT)