"""The other endpoints: caching, JSON safety, error mapping."""
import pandas as pd
import pytest

import api
import engine
import sources
from config import settings
from tests.conftest import frame


def test_history_is_json_safe_and_cached(client, clock, monkeypatch):
    calls = []

    def fake_ohlcv(kind, symbol, start, end, interval, limit):
        calls.append((kind, symbol))
        return frame([{"time": "2026-11-06 07:00", "open": 11.8, "high": 11.9, "low": 11.6, "close": 11.75, "volume": 1}])
    monkeypatch.setattr(sources, "ohlcv", fake_ohlcv)
    a = client.get("/stock/pdr/history?interval=1D").json()
    b = client.get("/stock/PDR/history?interval=1D").json()
    assert a == b and a["data"][0]["time"] == "2026-11-06" and calls == [("equity", "PDR")]
    assert client.get("/index/vnindex/history").json()["symbol"] == "VNINDEX"


def test_history_rejects_bad_interval(client):
    assert client.get("/stock/PDR/history?interval=7X").status_code == 422


def test_day_range_uses_exchange_band(client, clock, monkeypatch):
    engine.LISTING = {"SHS": {"name": "SHS", "nameEn": None, "exchange": "HNX", "type": "stock"}}
    monkeypatch.setattr(sources, "daily_bars", lambda s, a, b: [
        {"date": "2026-11-05", "open": 20, "high": 20, "low": 20, "close": 20.0, "volume": 1},
        {"date": "2026-11-06", "open": 20, "high": 21, "low": 19, "close": 21.0, "volume": 1}])
    body = client.get("/stock/SHS/day-range?start_date=2026-11-06&end_date=2026-11-06").json()
    assert body["total_sessions"] == 1
    assert body["sessions"][0] | {} == {**body["sessions"][0], "reference_price": 20.0, "ceiling": 22.0, "floor": 18.0}
    assert client.get("/stock/SHS/day-range?start_date=06-11-2026&end_date=2026-11-06").status_code == 400


def test_dnse_quote_combines_limits_and_order_book(client, monkeypatch):
    monkeypatch.setattr(settings, "QUOTE_SOURCE", "dnse")
    monkeypatch.setattr(sources, "price_limits", lambda symbol: pd.DataFrame([
        {"trading_date": "2026-11-09", "symbol": "PDR", "exchange": "HSX", "board": "T1",
         "reference_price": 1, "ceiling_price": 1, "floor_price": 1},
        {"trading_date": "2026-11-09", "symbol": "PDR", "exchange": "HSX", "board": "G1",
         "reference_price": 11.75, "ceiling_price": 12.55, "floor_price": 10.95}]))
    monkeypatch.setattr(sources, "order_book", lambda s: pd.DataFrame([
        {"bid_price_1": 11.45, "bid_vol_1": 1000, "ask_price_1": 11.5, "ask_vol_1": pd.NA}]))
    q = client.get("/stock/PDR/quote").json()
    assert q["exchange"] == "HOSE" and q["ceiling_price"] == 12.55 and q["bid_price_1"] == 11.45
    assert q["ask_vol_1"] is None
    assert client.get("/quotes?symbols=PDR").json()["count"] == 1


class CredentialError(Exception):
    pass


class RateLimitedError(Exception):
    pass


class NetworkError(Exception):
    pass


@pytest.mark.parametrize("exc, status, hint_part", [
    (CredentialError("Chưa có khoá: FHSC_API_KEY (code=VNSTOCK_CREDENTIAL_MISSING, source=fhsc)"), 403, "nguồn fhsc. Đặt FHSC_API_KEY"),
    (RateLimitedError("slow down"), 429, "giới hạn tốc độ"),
    (NetworkError("timeout"), 503, "không truy cập được"),
])
def test_vnstock_errors_map_to_http(client, monkeypatch, exc, status, hint_part):
    def boom(*_):
        raise exc
    monkeypatch.setattr(sources, "company", boom)
    r = client.get("/stock/PDR/company")
    assert r.status_code == status
    assert r.json()["detail"] == str(exc) and hint_part in r.json()["hint"]


def test_unexpected_error_is_500_without_details(client, monkeypatch):
    monkeypatch.setattr(sources, "company", lambda *_: {}["boom"])
    r = client.get("/stock/PDR/company")
    assert r.status_code == 500 and r.json() == {"detail": "Lỗi nội bộ server."}


def test_shared_budget_protects_the_key(client, monkeypatch):
    monkeypatch.setattr(engine.budget, "per_minute", 7)
    monkeypatch.setattr(engine.budget, "reserved", 6)
    monkeypatch.setattr(sources, "symbols", lambda: pd.DataFrame([{"symbol": "PDR"}]))
    monkeypatch.setattr(sources, "index_list", lambda: pd.DataFrame([{"symbol": "VNINDEX"}]))
    assert client.get("/symbols").status_code == 200
    r = client.get("/indices")
    assert r.status_code == 429 and r.headers["retry-after"] == "15"


def test_dnse_order_book_main_board_in_thousand_vnd(monkeypatch):
    # Real DNSE shape (2026-11-09 PDR): odd-lot row first, round-lot row second, prices in VND
    raw = pd.DataFrame([
        {"bid_price_1": 11600.0, "bid_vol_1": 37, "ask_price_1": 11650.0, "ask_vol_1": 22, "time": "a"},
        {"bid_price_1": 11600.0, "bid_vol_1": 3970, "ask_price_1": 11650.0, "ask_vol_1": 48090, "time": "b"},
    ])

    class M:
        def equity(self, _s):
            return type("E", (), {"order_book": lambda self: raw})()
    monkeypatch.setattr(settings, "QUOTE_SOURCE", "dnse")
    monkeypatch.setattr(sources, "market", lambda _src: M())
    out = sources.order_book("PDR")
    assert len(out) == 1 and out["time"][0] == "b"
    assert out["bid_price_1"][0] == 11.6 and out["ask_vol_1"][0] == 48090


def test_foreign_flow_keeps_daily_total(monkeypatch):
    raw = frame([{"time": "2026-11-06", "buy_vol": 330187.0}, {"time": "2026-11-06", "buy_vol": 46700.0},
                 {"time": "2026-11-05", "buy_vol": 497500.0}, {"time": "2026-11-05", "buy_vol": 0.0}])

    class M:
        def equity(self, _s):
            return type("E", (), {"foreign_flow": lambda self, **_: raw})()
    monkeypatch.setattr(sources, "market", lambda _src: M())
    out = sources.foreign_flow("PDR", "2026-11-05", None)
    assert list(out["buy_vol"]) == [497500.0, 330187.0]


def test_records_keep_vietnam_dates():
    df = pd.DataFrame({"listing_date": pd.to_datetime(["2009-06-30"]).tz_localize("Asia/Ho_Chi_Minh")})
    assert api.records(df)[0]["listing_date"].startswith("2009-06-30")


def test_removed_endpoints_are_gone(client):
    assert client.get("/macro/gdp").status_code == 404
    assert client.get("/stock/PDR/financials/ratio").status_code == 422
    assert client.get("/stock/PDR/company/officers").status_code == 422


def test_docs_toggle():
    assert api.app.docs_url == ("/docs" if settings.ENABLE_DOCS else None)


@pytest.mark.parametrize("path, fn", [
    ("/stock/PDR/foreign-flow", "foreign_flow"),
    ("/stock/PDR/history", "ohlcv"),
    ("/index/VNINDEX/history", "ohlcv"),
])
def test_start_and_end_are_separate_parameters(client, monkeypatch, path, fn):
    seen = []

    def spy(*args):
        seen.append(args)
        return pd.DataFrame()
    monkeypatch.setattr(sources, fn, spy)
    client.get(f"{path}?start=2026-11-03")
    client.get(f"{path}?start=2026-11-03&end=2026-11-06")
    start_end = [a[1:3] if fn == "foreign_flow" else a[2:4] for a in seen]
    assert start_end == [("2026-11-03", None), ("2026-11-03", "2026-11-06")]
