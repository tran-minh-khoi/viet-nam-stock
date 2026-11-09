"""Behaviour of the /stock/* engine: cache, budget, failures, market hours."""
import json
import time
from datetime import datetime, timedelta

import pandas as pd

import engine
import sources
from config import settings
from tests.conftest import frame

BARS = [
    {"date": "2026-11-05", "open": 11.6, "high": 11.9, "low": 11.5, "close": 11.8, "volume": 5_000_000},
    {"date": "2026-11-06", "open": 11.8, "high": 11.9, "low": 11.6, "close": 11.75, "volume": 7_325_400},
    {"date": "2026-11-09", "open": 11.75, "high": 11.9, "low": 11.45, "close": 11.5, "volume": 4_358_500},
]


def listed(fake, *symbols, exchange="HOSE"):
    for s in symbols:
        fake.listing[s] = {"name": f"Công ty {s}", "nameEn": None, "exchange": exchange, "type": "stock"}
    engine.LISTING = dict(fake.listing)


def test_first_request_fetches_then_cache_answers(fake, clock, client):
    fake.bars["PDR"] = BARS
    fake.trade["PDR"] = (11.45, clock.value - timedelta(seconds=20))
    listed(fake, "PDR")
    assert client.get("/stock/PDR").json()["currentPrice"] == 11.45
    calls = len(fake.calls)
    for _ in range(5):
        assert client.get("/stock/PDR").status_code == 200
    assert len(fake.calls) == calls          # fresh cache: no new upstream call


def test_stale_entry_is_answered_at_once_and_refreshed(fake, clock, client):
    fake.bars["PDR"] = BARS
    listed(fake, "PDR")
    client.get("/stock/PDR")
    engine.CACHE["PDR"]["fetched_at"] -= 3600       # make it stale
    fake.bars["PDR"] = BARS[:-1] + [{**BARS[-1], "close": 11.3}]
    first = client.get("/stock/PDR").json()          # old value right away
    assert first["todayDate"] == "2026-11-09"
    time.sleep(0.05)
    assert client.get("/stock/PDR").json()["data"]["today"]["close"] in (11.3, 11.45, 11.5)
    assert engine.CACHE["PDR"]["sessions"][-1]["close"] == 11.3


def test_old_trade_is_not_the_current_price(fake, clock, client):
    fake.bars["PDR"] = BARS
    fake.trade["PDR"] = (99.0, clock.value - timedelta(minutes=30))
    listed(fake, "PDR")
    assert client.get("/stock/PDR").json()["currentPrice"] == 11.5


def test_outside_market_hours_no_trade_call(fake, clock, client):
    clock.set(datetime(2026, 11, 9, 20, 0))
    fake.bars["PDR"] = BARS
    fake.trade["PDR"] = (99.0, clock.value)
    listed(fake, "PDR")
    body = client.get("/stock/PDR").json()
    assert body["currentPrice"] == 11.5 and body["marketOpen"] is False
    assert ("last_trade", "PDR") not in fake.calls


def test_unknown_symbol_costs_nothing(fake, clock, client):
    listed(fake, "PDR")
    r = client.get("/stock/ABCD")
    assert r.status_code == 404 and r.json()["detail"] == "Không tìm thấy mã ABCD"
    assert fake.calls == []


def test_no_data_is_remembered(fake, clock, client):
    listed(fake, "PDR", "XYZ")
    r1 = client.get("/stock/XYZ")
    r2 = client.get("/stock/XYZ")
    assert r1.status_code == r2.status_code == 404
    assert r2.json()["detail"] == "Không tìm thấy dữ liệu cho mã XYZ"
    assert fake.calls.count(("daily_bars", "XYZ")) == 1


def test_source_failure_on_first_fetch_is_502(fake, clock, client):
    listed(fake, "PDR")
    fake.fail = RuntimeError("boom")
    r = client.get("/stock/PDR")
    assert r.status_code == 502 and r.headers["retry-after"] == "15"


def test_source_failure_keeps_serving_cached_data(fake, clock, client):
    fake.bars["PDR"] = BARS
    listed(fake, "PDR")
    client.get("/stock/PDR")
    engine.CACHE["PDR"]["fetched_at"] -= 3600
    fake.fail = RuntimeError("boom")
    assert client.get("/stock/PDR").status_code == 200
    time.sleep(0.05)
    assert client.get("/stock/PDR").status_code == 200


def test_budget_exhausted_is_503(fake, clock, client, monkeypatch):
    fake.bars["VNM"] = BARS
    listed(fake, "PDR", "VNM")
    monkeypatch.setattr(engine.budget, "per_minute", 2)
    monkeypatch.setattr(engine.budget, "reserved", 1)
    r = client.get("/stock/VNM")                     # costs 2 in market hours, only 1 left for non-priority
    assert r.status_code == 503 and r.json()["detail"].startswith("Hệ thống đang bận")


def test_batch_limits(fake, clock, client):
    assert client.get("/stocks?symbols=").status_code == 400
    many = ",".join(f"AA{i}" for i in range(11))
    assert client.get(f"/stocks?symbols={many}").json()["detail"] == "Cần từ 1 đến 10 mã"


def test_name_overrides_and_short_names(fake, clock, client, tmp_path):
    fake.bars["PDR"] = BARS
    listed(fake, "PDR")
    fake.listing["PDR"]["name"] = "Phat Dat (tên nguồn mới)"
    engine.LISTING = dict(fake.listing)
    path = tmp_path / "names.json"
    path.write_text(json.dumps({"PDR": {"name": "CTCP Phát triển Bất động sản Phát Đạt", "nameEn": "Phat Dat"}}), encoding="utf-8")
    engine.load_name_overrides(str(path))
    body = client.get("/stock/PDR").json()
    assert body["name"] == "PHÁT ĐẠT"
    assert body["fullName"] == "CTCP Phát triển Bất động sản Phát Đạt" and body["nameEn"] == "Phat Dat"


def test_listing_loads_through_budget(fake, clock):
    import asyncio
    listed(fake, "PDR")
    engine.LISTING = {}
    asyncio.run(engine.load_listing())
    assert "PDR" in engine.LISTING and engine.budget.used() == 2


# ---------------------------------------------------------------- sources.py against vnstock-shaped frames

class FakeEquity:
    def __init__(self, ohlcv=None, trades=None):
        self._ohlcv, self._trades = ohlcv, trades

    def ohlcv(self, **_):
        return self._ohlcv

    def trades(self, **_):
        return self._trades


class FakeMarket:
    def __init__(self, equity):
        self._equity = equity

    def equity(self, _symbol):
        return self._equity


def test_daily_bars_from_vnstock6_frame(monkeypatch):
    df = frame([{"time": "2026-11-06 07:00", "open": 11.8, "high": 11.9, "low": 11.6, "close": 11.75, "volume": 7325400},
                {"time": "2026-11-05 07:00", "open": 11.6, "high": 11.9, "low": 11.5, "close": 11.8, "volume": 5000000}])
    monkeypatch.setattr(sources, "market", lambda _src: FakeMarket(FakeEquity(ohlcv=df)))
    bars = sources.daily_bars("PDR", "2026-11-01", "2026-11-09")
    assert [b["date"] for b in bars] == ["2026-11-05", "2026-11-06"]
    assert bars[1] == {"date": "2026-11-06", "open": 11.8, "high": 11.9, "low": 11.6, "close": 11.75, "volume": 7325400}


def test_last_trade_is_last_minute_candle_in_vietnam_time(monkeypatch):
    df = frame([{"time": "2026-11-09 14:45", "open": 11.6, "high": 11.6, "low": 11.6, "close": 11.6, "volume": 754200}])
    df["time"] = df["time"].dt.tz_convert("UTC")      # whatever tz the source uses
    seen = {}

    class E:
        def ohlcv(self, **kw):
            seen.update(kw)
            return df
    monkeypatch.setattr(sources, "market", lambda _src: FakeMarket(E()))
    price, at = sources.last_trade("PDR")
    assert price == 11.6 and at == datetime(2026, 11, 9, 14, 45)
    assert seen == {"interval": "1m", "limit": 1}


def test_listing_normalizes_exchange_and_types(monkeypatch):
    stocks = pd.DataFrame([
        {"symbol": "pdr", "exchange": "HSX", "type": "stock", "organ_name": "CTCP Phát Đạt", "name_en": "Phat Dat"},
        {"symbol": "VN30F1M", "exchange": "DERIVATIVE", "type": "futures", "organ_name": "x", "name_en": None},
        {"symbol": "SHS", "exchange": "HNX", "type": "stock", "organ_name": "CTCP SHS", "name_en": None},
    ]).astype("string")   # vnstock 6 returns nullable dtypes: empty cells are pd.NA
    etfs = pd.DataFrame([{"symbol": "E1VFVN30", "exchange": "HOSE", "type": "etf", "organ_name": "Quỹ ETF DCVFMVN30", "name_en": "DCVFMVN30 ETF"}])

    class Ref:
        class equity:
            @staticmethod
            def list():
                return stocks

        class etf:
            @staticmethod
            def list():
                return etfs

    monkeypatch.setattr(sources, "reference", lambda _src: Ref)
    out = sources.listing()
    assert set(out) == {"PDR", "SHS", "E1VFVN30"}
    assert out["PDR"] == {"name": "CTCP Phát Đạt", "nameEn": "Phat Dat", "exchange": "HOSE", "type": "stock"}
    assert out["E1VFVN30"]["type"] == "fund"
    assert out["SHS"]["nameEn"] is None


def test_listing_keeps_symbols_known_only_from_names_file(fake, clock, tmp_path):
    import asyncio
    path = tmp_path / "names.json"
    path.write_text(json.dumps({"FUCVREIT": {"name": "Quỹ đầu tư bất động sản", "nameEn": None, "exchange": "HOSE", "type": "fund"},
                                "OLD": {"name": "x", "exchange": "DELISTED"}}), encoding="utf-8")
    engine.load_name_overrides(str(path))
    listed(fake, "PDR")
    engine.LISTING = {}
    asyncio.run(engine.load_listing())
    assert "FUCVREIT" in engine.LISTING and "OLD" not in engine.LISTING


def test_background_loop_backs_off_after_failure(fake, clock, monkeypatch):
    import asyncio
    listed(fake, "PDR")
    fake.fail = RuntimeError("no key")

    async def run_two_rounds():
        real_sleep = asyncio.sleep
        rounds = {"n": 0}

        async def short_sleep(_seconds):
            rounds["n"] += 1
            if rounds["n"] >= 3:
                raise asyncio.CancelledError
            await real_sleep(0.01)
        monkeypatch.setattr(engine.asyncio, "sleep", short_sleep)
        try:
            await engine.__dict__["_background_loop_impl"]()
        except asyncio.CancelledError:
            pass
    monkeypatch.setattr(engine, "LISTING_LOADED_AT", time.time())
    asyncio.run(run_two_rounds())
    assert fake.calls.count(("daily_bars", "PDR")) == 1


def test_clock_is_vietnam_time_even_on_a_utc_server(monkeypatch):
    import os
    monkeypatch.setenv("TZ", "UTC")
    time.tzset()
    try:
        from zoneinfo import ZoneInfo
        expected = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).replace(tzinfo=None)
        assert abs((engine.now() - expected).total_seconds()) < 2
        assert engine.vn_time(1793947200) == "2026-11-06T13:40:00"   # 06:40 UTC
    finally:
        monkeypatch.delenv("TZ")
        time.tzset()
