"""API behaviour with vnstock faked out: no network, no quota used."""
import pandas as pd
import pytest
from fastapi.testclient import TestClient

import api

client = TestClient(api.app, raise_server_exceptions=False)


class FakeEquity:
    calls = 0

    def __init__(self, symbol):
        self.symbol = symbol

    def ohlcv(self, **_):
        FakeEquity.calls += 1
        return pd.DataFrame({
            "time": pd.to_datetime(["2026-10-27", "2026-10-28", "2026-10-29"]).tz_localize("Asia/Ho_Chi_Minh"),
            "open": [56.1, 56.2, 57.9], "high": [56.4, 57.6, 58.4], "low": [56.0, 56.1, 57.0],
            "close": [56.1, 57.5, 57.2], "volume": [2438200, 6453700, 4049800],
        })

    def quote(self):
        return pd.DataFrame([{"symbol": self.symbol, "exchange": "HOSE", "reference_price": 57200.0, "bid_vol_1": pd.NA}])


class FakeMarket:
    def equity(self, symbol):
        return FakeEquity(symbol)


@pytest.fixture(autouse=True)
def fake_vnstock(monkeypatch):
    api.MEMORY_CACHE.clear()
    FakeEquity.calls = 0
    monkeypatch.setattr(api, "Market", FakeMarket)
    monkeypatch.setattr(api, "REDIS_CLIENT", None)


def test_daily_sessions_reference_is_previous_close():
    s = api.daily_sessions("VCB", "2026-10-20", "2026-10-29")
    assert [x["reference_price"] for x in s] == [56.1, 56.1, 57.5]
    assert (s[-1]["ceiling"], s[-1]["floor"]) == api.calculate_ceiling_floor(57.5)


def test_stock_today_uses_latest_and_previous_session():
    r = client.get("/stock/vcb")
    assert r.status_code == 200
    body = r.json()
    assert body["todayDate"] == "2026-10-29" and body["previousDate"] == "2026-10-28"
    assert body["currentPrice"] == 57.2 and body["referencePrice"] == 57.5
    assert body["exchange"] == "HOSE"


def test_cache_saves_quota():
    client.get("/stock/VCB/recent?days=2")
    client.get("/stock/VCB/recent?days=2")
    assert FakeEquity.calls == 1


def test_history_and_quote_are_json_safe():
    h = client.get("/stock/VCB/history?interval=1D").json()
    assert h["data"][0]["time"] == "2026-10-27"
    assert client.get("/stock/VCB/quote").json()["bid_vol_1"] is None


def test_records_keep_vietnam_dates():
    df = pd.DataFrame({"listing_date": pd.to_datetime(["2009-06-30"]).tz_localize("Asia/Ho_Chi_Minh")})
    assert api.records(df)[0]["listing_date"].startswith("2009-06-30")


def test_invalid_symbol_rejected_before_vnstock():
    assert client.get("/stock/V$B").status_code in (404, 422)
    assert client.get("/stock/VCB/history?interval=7X").status_code == 422


@pytest.mark.parametrize("name, msg, status", [
    ("EntitlementError", "Chức năng 'x' không thuộc quyền của cấp Khách.", 403),
    ("EntitlementError", "Đã dùng hết hạn mức theo phút (10/10 lượt gọi)", 429),
    ("InputError", "Nguồn 'vci' không có mã 'ZZZ'.", 404),
    ("NetworkError", "timeout", 503),
    ("KeyError", "boom", 500),
])
def test_vnstock_errors_map_to_http(monkeypatch, name, msg, status):
    err = type(name, (Exception,), {})

    def boom(*_):
        raise err(msg)
    monkeypatch.setattr(api, "daily_sessions", boom)
    r = client.get("/stock/VCB")
    assert r.status_code == status
    if status != 500:
        assert r.json()["detail"] == msg
