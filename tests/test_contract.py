"""The answers of /stock/* must stay byte-for-byte what apps already read.

tests/fixtures/prod-20261109 holds real responses of the previous service (vnstock 3, KBS)
captured on 2026-11-09 during market hours. Each test rebuilds the same market data,
feeds it to this service and compares every field. Only fields that depend on when the
request ran (timestamp, lastUpdated, stale) are left out.
"""
import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures" / "prod-20261109"
SYMBOLS = ["PDR", "VNM", "FPT", "SHS", "BSR", "E1VFVN30"]
VOLATILE = {"timestamp", "lastUpdated", "stale"}


def load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def strip(obj):
    if isinstance(obj, dict):
        return {k: strip(v) for k, v in obj.items() if k not in VOLATILE}
    if isinstance(obj, list):
        return [strip(v) for v in obj]
    return obj


def seed(fake, clock, symbol):
    """Market data identical to what the old service had for `symbol`."""
    quote = load(f"stock_{symbol}.json")
    recent = load(f"recent_{symbol}.json")
    sessions = recent["sessions"]
    first_day = datetime.strptime(sessions[0]["date"], "%Y-%m-%d")
    # One session before the window, so the first one has its real reference price
    bars = [{"date": (first_day - timedelta(days=1)).strftime("%Y-%m-%d"), "open": sessions[0]["reference_price"],
             "high": sessions[0]["reference_price"], "low": sessions[0]["reference_price"],
             "close": sessions[0]["reference_price"], "volume": 1}]
    bars += [{k: s[k] for k in ("date", "open", "high", "low", "close", "volume")} for s in sessions]
    fake.bars[symbol] = bars
    taken_at = datetime.fromisoformat(quote["timestamp"])
    clock.set(taken_at)
    fake.trade[symbol] = (quote["currentPrice"], taken_at - timedelta(seconds=30))
    fake.listing[symbol] = {"name": quote["fullName"], "nameEn": quote["nameEn"],
                            "exchange": quote["exchange"], "type": "stock"}
    return quote, recent


def with_listing(fake, extra=("PDR", "VNM")):
    import engine
    for s in extra:
        fake.listing.setdefault(s, {"name": s, "nameEn": None, "exchange": "HOSE", "type": "stock"})
    engine.LISTING = dict(fake.listing)


@pytest.mark.parametrize("symbol", SYMBOLS)
def test_stock_matches_previous_service(fake, clock, client, symbol):
    quote, _ = seed(fake, clock, symbol)
    with_listing(fake)
    r = client.get(f"/stock/{symbol}")
    assert r.status_code == 200
    assert strip(r.json()) == strip(quote)
    assert r.headers["cache-control"] == "public, max-age=5"


@pytest.mark.parametrize("symbol", SYMBOLS)
def test_recent_30_matches_previous_service(fake, clock, client, symbol):
    _, recent = seed(fake, clock, symbol)
    with_listing(fake)
    r = client.get(f"/stock/{symbol}/recent?days=30")
    assert r.status_code == 200
    assert strip(r.json()) == strip(recent)


def test_recent_param_on_stock_and_clamping(fake, clock, client):
    seed(fake, clock, "PDR")
    with_listing(fake)
    assert strip(client.get("/stock/PDR?recent=5").json()) == strip(load("stock_PDR_recent5.json"))
    assert strip(client.get("/stock/PDR/recent?days=999").json()) == strip(load("recent_PDR_999.json"))
    assert strip(client.get("/stock/PDR/recent?days=0").json()) == strip(load("recent_PDR_0.json"))
    # lowercase symbol from the mobile app
    assert strip(client.get("/stock/pdr").json()) == strip(load("stock_PDR.json"))


def test_batch_matches_previous_service(fake, clock, client):
    seed(fake, clock, "PDR")
    expected = load("stocks_mix.json")
    # VNM was captured a few seconds later in the batch; reuse its own snapshot values
    fake.bars["VNM"] = [{k: s[k] for k in ("date", "open", "high", "low", "close", "volume")}
                        for s in load("recent_VNM.json")["sessions"]]
    fake.bars["VNM"].insert(0, {**fake.bars["VNM"][0], "date": "2026-09-01",
                                "close": load("recent_VNM.json")["sessions"][0]["reference_price"]})
    fake.trade["VNM"] = (expected["data"]["VNM"]["currentPrice"], clock.value)
    v = expected["data"]["VNM"]
    fake.listing["VNM"] = {"name": v["fullName"], "nameEn": v["nameEn"], "exchange": v["exchange"], "type": "stock"}
    with_listing(fake)
    r = client.get("/stocks?symbols=PDR,vnm,XXXX,PDR")
    body = r.json()
    assert list(body["data"]) == list(expected["data"])
    assert strip(body["data"]["PDR"]) == strip(expected["data"]["PDR"])
    assert strip(body["data"]["VNM"]) == strip(expected["data"]["VNM"])
    assert body["errors"] == expected["errors"]


def test_error_bodies_match_previous_service(fake, clock, client):
    seed(fake, clock, "PDR")
    with_listing(fake)
    unknown = client.get("/stock/XXXX")
    assert (unknown.status_code, unknown.text) == (404, (FIXTURES / "stock_XXXX.txt").read_text().rsplit("\n", 1)[0])
    invalid = client.get("/stock/a%20b")
    assert (invalid.status_code, invalid.text) == (400, (FIXTURES / "stock_invalid.txt").read_text().rsplit("\n", 1)[0])


def test_health_and_root_keep_their_keys(fake, clock, client):
    old_health = load("health.json")
    assert set(old_health) <= set(client.get("/health").json())
    old_root = load("root.json")
    new_root = client.get("/").json()
    assert set(old_root) <= set(new_root)
    assert new_root["endpoints"] == old_root["endpoints"]
