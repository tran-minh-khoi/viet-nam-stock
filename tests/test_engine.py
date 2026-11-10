"""Behaviour of the /stock/* engine: cache, budget, failures, market hours."""
import json
import time
from datetime import datetime, timedelta

import engine
import sources
from config import settings

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


def test_outside_market_hours_price_is_the_close(fake, clock, client):
    clock.set(datetime(2026, 11, 9, 20, 0))
    fake.bars["PDR"] = BARS
    fake.trade["PDR"] = (99.0, clock.value)
    listed(fake, "PDR")
    body = client.get("/stock/PDR").json()
    assert body["currentPrice"] == 11.5 and body["marketOpen"] is False


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
    assert "PDR" in engine.LISTING and engine.budget.used() == engine.LISTING_COST


# ---------------------------------------------------------------- DNSE sessions: today from the last trade

TODAY = {"date": "2026-11-10", "open": 11.75, "high": 11.9, "low": 11.7, "close": 11.85, "volume": 3_218_900}


def test_today_comes_from_the_last_trade_during_the_session(fake, clock, client):
    clock.set(datetime(2026, 11, 10, 10, 50))
    fake.bars["PDR"] = BARS                      # DNSE daily history stops at yesterday
    fake.today["PDR"] = (TODAY, datetime(2026, 11, 10, 10, 49, 58))
    listed(fake, "PDR")
    body = client.get("/stock/PDR").json()
    assert body["todayDate"] == "2026-11-10" and body["previousDate"] == "2026-11-09"
    assert body["referencePrice"] == 11.5 and body["currentPrice"] == 11.85
    assert (body["upperPrice"], body["lowerPrice"]) == (12.3, 10.7)
    assert body["change"] == 0.35 and body["todayVolume"] == 3_218_900
    assert body["data"]["today"]["is_today"] is True


def test_today_kept_after_the_close_until_dnse_has_the_daily_bar(fake, clock, client):
    clock.set(datetime(2026, 11, 10, 16, 0))
    fake.bars["PDR"] = BARS
    fake.today["PDR"] = (TODAY, datetime(2026, 11, 10, 14, 45))
    listed(fake, "PDR")
    body = client.get("/stock/PDR").json()
    assert body["todayDate"] == "2026-11-10" and body["currentPrice"] == 11.85
    recent = client.get("/stock/PDR/recent?days=2").json()["sessions"]
    assert [s["date"] for s in recent] == ["2026-11-09", "2026-11-10"] and recent[1]["reference_price"] == 11.5


def test_before_the_first_match_yesterday_is_the_latest_session(fake, clock, client):
    clock.set(datetime(2026, 11, 10, 9, 5))
    fake.bars["PDR"] = BARS
    fake.trade["PDR"] = (11.5, datetime(2026, 11, 9, 14, 45))   # last match is yesterday's
    listed(fake, "PDR")
    body = client.get("/stock/PDR").json()
    assert body["todayDate"] == "2026-11-09" and body["currentPrice"] == 11.5


def test_a_trade_from_another_day_never_adds_a_session(fake, clock, client):
    clock.set(datetime(2026, 11, 11, 8, 0))     # DNSE has not published 11-10 yet, last trade is 11-10
    fake.bars["PDR"] = BARS
    fake.today["PDR"] = (TODAY, datetime(2026, 11, 10, 14, 45))
    listed(fake, "PDR")
    assert client.get("/stock/PDR").json()["todayDate"] == "2026-11-09"


def test_last_trade_failure_still_answers_with_daily_bars(fake, clock, client, monkeypatch):
    fake.bars["PDR"] = BARS
    listed(fake, "PDR")

    def boom(_symbol):
        raise RuntimeError("DNSE 500")
    monkeypatch.setattr(sources, "latest_trade", boom)
    assert client.get("/stock/PDR").json()["currentPrice"] == 11.5


# ---------------------------------------------------------------- sources.py against real DNSE answers (shapes from 2026-11-10)

def test_daily_bars_from_dnse_ohlc(fake_dnse):
    dnse = fake_dnse({"/price/ohlc": {"t": [1793844000, 1793930400], "o": [11.6, 11.3], "h": [11.7, 11.9],
                                      "l": [11.35, 11.25], "c": [11.55, 11.75], "v": [6312500, 7325400], "nextTime": 0}})
    bars = sources.daily_bars("PDR", "2026-11-01", "2026-11-06")
    assert bars == [{"date": "2026-11-05", "open": 11.6, "high": 11.7, "low": 11.35, "close": 11.55, "volume": 6312500},
                    {"date": "2026-11-06", "open": 11.3, "high": 11.9, "low": 11.25, "close": 11.75, "volume": 7325400}]
    path, params = dnse.calls[0]
    assert params == {"symbol": "PDR", "type": "STOCK", "resolution": "1D",
                      "from": 1793466000, "to": 1793984399}   # 2026-11-01 00:00 → 2026-11-06 23:59:59 Vietnam time


def test_latest_trade_uses_the_main_board_and_lot_unit(fake_dnse):
    fake_dnse({"/price/PDR/trades/latest": {"trades": [
        {"boardId": "G4", "matchPrice": 11.75, "openPrice": 11.6, "highestPrice": 11.9, "lowestPrice": 11.6,
         "totalVolumeTraded": 1074, "time": "2026-11-10 10:50:05.799"},
        {"boardId": "G1", "matchPrice": 11.8, "openPrice": 11.75, "highestPrice": 11.9, "lowestPrice": 11.7,
         "totalVolumeTraded": 310520, "time": "2026-11-10 10:51:59.953"},
        {"boardId": "T1", "matchPrice": 11.2, "openPrice": 0, "highestPrice": 0, "lowestPrice": 0,
         "totalVolumeTraded": 30000, "time": "2026-10-08 10:00:44.824"}]}})
    assert sources.latest_trade("PDR") == {"date": "2026-11-10", "open": 11.75, "high": 11.9, "low": 11.7,
                                           "close": 11.8, "volume": 3_105_200, "at": datetime(2026, 11, 10, 10, 51, 59)}


def test_latest_trade_without_a_round_lot_match(fake_dnse):
    fake_dnse({"/price/XYZ/trades/latest": {"trades": [{"boardId": "G1", "matchPrice": 0, "openPrice": 0,
                                                        "time": "2026-11-10 09:00:00.000"}]}})
    assert sources.latest_trade("XYZ") is None


def test_listing_pages_and_keeps_stocks_and_funds(fake_dnse):
    page1 = {"data": [
        {"symbol": "PDR", "marketId": "STO", "securityGroupId": "ST", "name": "CTCP Phát triển Bất động sản Phát Đạt"},
        {"symbol": "41I1GB000", "marketId": "DVX", "securityGroupId": "FU", "name": "HĐTL VN30"},
        {"symbol": "SHS", "marketId": "STX", "securityGroupId": "ST", "name": "CTCP Chứng khoán Sài Gòn - Hà Nội"}],
        "total": 104, "page": 1, "pageSize": 100}
    page2 = {"data": [{"symbol": "E1VFVN30", "marketId": "STO", "securityGroupId": "EF", "name": "Quỹ ETF DCVFMVN30"},
                      {"symbol": "BSR", "marketId": "UPX", "securityGroupId": "ST", "name": "Lọc hoá dầu Bình Sơn"},
                      {"symbol": "VBA", "marketId": "HCX", "securityGroupId": "BS", "name": "Trái phiếu"}],
             "total": 104, "page": 2, "pageSize": 100}
    dnse = fake_dnse({"/market/instruments": lambda p: page1 if p["page"] == 1 else page2})
    out = sources.listing()
    assert sorted(out) == ["BSR", "E1VFVN30", "PDR", "SHS"]
    assert out["SHS"] == {"name": "CTCP Chứng khoán Sài Gòn - Hà Nội", "nameEn": None, "exchange": "HNX", "type": "stock"}
    assert out["E1VFVN30"]["type"] == "fund" and out["BSR"]["exchange"] == "UPCOM"
    assert [p["page"] for _, p in dnse.calls] == [1, 2]


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


# ---------------------------------------------------------------- production safety: always have the last good answer

def test_empty_answer_for_a_known_symbol_keeps_the_last_good_data(fake, clock, client):
    fake.bars["PDR"] = BARS
    listed(fake, "PDR")
    client.get("/stock/PDR")
    engine.CACHE["PDR"]["fetched_at"] -= 3600
    fake.bars["PDR"] = []                               # source hiccup: no sessions
    assert client.get("/stock/PDR").status_code == 200
    time.sleep(0.05)
    r = client.get("/stock/PDR")
    assert r.status_code == 200 and r.json()["todayDate"] == "2026-11-09"
    assert "PDR" not in engine.NOT_FOUND


def test_older_data_never_replaces_newer(fake, clock, client):
    fake.bars["PDR"] = BARS
    listed(fake, "PDR")
    client.get("/stock/PDR")
    engine.CACHE["PDR"]["fetched_at"] -= 3600
    fake.bars["PDR"] = BARS[:-1]                        # source lags one session behind
    client.get("/stock/PDR")
    time.sleep(0.05)
    assert engine.CACHE["PDR"]["sessions"][-1]["date"] == "2026-11-09"


def test_throttled_source_backs_off_longer(fake, clock, client):
    import dnse
    fake.bars["PDR"] = BARS
    listed(fake, "PDR")
    client.get("/stock/PDR")
    engine.CACHE["PDR"]["fetched_at"] -= 3600
    fake.fail = dnse.RateLimited("DNSE 429: Rate Limit Exceeded")
    client.get("/stock/PDR")
    time.sleep(0.05)
    assert engine.RETRY_AFTER["PDR"] == engine.RETRY_AFTER_THROTTLE
    engine.LAST_FAILURE["PDR"] -= 30                    # 30 s later: still waiting
    assert not engine.may_retry("PDR")
    engine.LAST_FAILURE["PDR"] -= engine.RETRY_AFTER_THROTTLE
    assert engine.may_retry("PDR")
    assert client.get("/stock/PDR").status_code == 200   # meanwhile users still get the last good data


def test_snapshot_survives_a_restart_while_the_source_is_down(fake, clock, client, tmp_path):
    path = str(tmp_path / "snapshot.json")
    fake.bars["PDR"] = BARS
    fake.trade["PDR"] = (11.45, clock.value - timedelta(seconds=10))
    listed(fake, "PDR")
    before = client.get("/stock/PDR").json()
    engine.save_snapshot(path)

    engine.reset()                                      # "restart": memory is gone
    fake.fail = RuntimeError("DNSE down")
    fake.calls.clear()
    engine.load_snapshot(path)
    assert engine.LISTING and "PDR" in engine.CACHE
    after = client.get("/stock/PDR")
    assert after.status_code == 200
    assert {k: v for k, v in after.json().items() if k not in ("timestamp", "stale")} == \
           {k: v for k, v in before.items() if k not in ("timestamp", "stale")}


def test_snapshot_written_atomically_and_bad_file_ignored(tmp_path):
    path = tmp_path / "snapshot.json"
    engine.CACHE["PDR"] = {"sessions": BARS, "current_price": None, "fetched_at": time.time(), "failed_at": 0.0}
    engine.save_snapshot(str(path))
    assert json.loads(path.read_text(encoding="utf-8"))["entries"]["PDR"]["sessions"][-1]["close"] == 11.5
    assert not (tmp_path / "snapshot.json.tmp").exists()
    engine.reset()
    path.write_text("{broken", encoding="utf-8")
    engine.load_snapshot(str(path))                     # logs a warning, starts empty
    assert engine.CACHE == {}


def test_names_file_ignores_non_text_values(fake, clock, client, tmp_path):
    path = tmp_path / "names.json"
    path.write_text('{"FUEPHVNS": {"name": "Quỹ ETF PHFM VNSHINE", "nameEn": NaN, "exchange": "HOSE"}}', encoding="utf-8")
    engine.load_name_overrides(str(path))
    assert engine.NAME_OVERRIDES["FUEPHVNS"] == {"name": "Quỹ ETF PHFM VNSHINE", "exchange": "HOSE"}
    engine.LISTING = {"FUEPHVNS": {"name": "x", "nameEn": None, "exchange": "HOSE", "type": "fund"}}
    assert client.get("/symbols").json()["data"][0]["nameEn"] is None
