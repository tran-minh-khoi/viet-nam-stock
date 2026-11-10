"""Shared fakes: DNSE is never called, no network, no key needed."""
from datetime import datetime

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
        self.trade = {}       # symbol -> (price, datetime): last match, same session as the bar of that day
        self.today = {}       # symbol -> (bar, datetime): last trade of a session not in the daily bars yet
        self.listing = {}     # symbol -> {"name","nameEn","exchange","type"}
        self.calls = []
        self.fail = None      # exception to raise from daily_bars

    def daily_bars(self, symbol, start, end):
        self.calls.append(("daily_bars", symbol))
        if self.fail:
            raise self.fail
        return [b for b in self.bars.get(symbol, []) if start <= b["date"] <= end]

    def latest_trade(self, symbol):
        self.calls.append(("latest_trade", symbol))
        if symbol in self.today:
            bar, at = self.today[symbol]
            return {**bar, "at": at}
        if symbol in self.trade:
            price, at = self.trade[symbol]
            return {"date": at.strftime("%Y-%m-%d"), "open": price, "high": price, "low": price,
                    "close": price, "volume": 0, "at": at}
        return None

    def get_listing(self):
        self.calls.append(("listing", None))
        return dict(self.listing)


@pytest.fixture
def fake(monkeypatch):
    src = FakeSource()
    monkeypatch.setattr(sources, "daily_bars", src.daily_bars)
    monkeypatch.setattr(sources, "latest_trade", src.latest_trade)
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


class FakeDnse:
    """Stands in for dnse.client(): answers by path from .responses, records every call."""

    def __init__(self, responses):
        self.responses = responses
        self.calls = []
        self.limits = {}

    def get(self, path, params=None):
        self.calls.append((path, dict(params or {})))
        answer = self.responses[path]
        return answer(params or {}) if callable(answer) else answer


@pytest.fixture
def fake_dnse(monkeypatch):
    import dnse

    def install(responses):
        client = FakeDnse(responses)
        monkeypatch.setattr(dnse, "client", lambda: client)
        return client
    return install
