"""Shared fakes: vnstock is never called, no network, no key needed."""
from datetime import datetime

import pandas as pd
import pytest
from fastapi.testclient import TestClient

import api
import engine
import sources
from config import settings


class FakeSource:
    """Stands in for sources.py. Set .bars / .trade / .listing per test."""

    def __init__(self):
        self.bars = {}        # symbol -> [{"date","open","high","low","close","volume"}]
        self.trade = {}       # symbol -> (price, datetime)
        self.listing = {}     # symbol -> {"name","nameEn","exchange","type"}
        self.calls = []
        self.fail = None      # exception to raise from daily_bars

    def daily_bars(self, symbol, start, end):
        self.calls.append(("daily_bars", symbol))
        if self.fail:
            raise self.fail
        return [b for b in self.bars.get(symbol, []) if start <= b["date"] <= end]

    def last_trade(self, symbol):
        self.calls.append(("last_trade", symbol))
        return self.trade.get(symbol)

    def get_listing(self):
        self.calls.append(("listing", None))
        return dict(self.listing)


@pytest.fixture
def fake(monkeypatch):
    src = FakeSource()
    monkeypatch.setattr(sources, "daily_bars", src.daily_bars)
    monkeypatch.setattr(sources, "last_trade", src.last_trade)
    monkeypatch.setattr(sources, "listing", src.get_listing)
    return src


@pytest.fixture
def clock(monkeypatch):
    """Freeze engine.now(); call clock.set(datetime) to move it."""
    class Clock:
        value = datetime(2026, 11, 9, 14, 32, 0)   # Monday, market open

        def set(self, value):
            self.value = value

    c = Clock()
    monkeypatch.setattr(engine, "now", lambda: c.value)
    return c


@pytest.fixture(autouse=True)
def clean_state(monkeypatch):
    engine.reset()
    engine.NAME_OVERRIDES = {}
    api.MEMORY_CACHE.clear()
    monkeypatch.setattr(api, "REDIS_CLIENT", None)
    monkeypatch.setattr(settings, "PRIORITY_SYMBOLS", ["PDR"])
    monkeypatch.setattr(settings, "SHORT_NAMES", {"PDR": "PHÁT ĐẠT"})
    monkeypatch.setattr(settings, "MAX_RECENT", 30)
    monkeypatch.setattr(settings, "MAX_BATCH", 10)

    async def no_background():
        return None
    monkeypatch.setattr(engine, "background_loop", no_background)
    yield
    engine.reset()


@pytest.fixture
def client():
    with TestClient(api.app, raise_server_exceptions=False) as c:
        yield c


def frame(rows, tz=True):
    df = pd.DataFrame(rows)
    if "time" in df.columns:
        df["time"] = pd.to_datetime(df["time"])
        if tz:
            df["time"] = df["time"].dt.tz_localize("Asia/Ho_Chi_Minh")
    return df
