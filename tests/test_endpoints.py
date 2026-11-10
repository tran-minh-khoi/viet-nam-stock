"""The other endpoints: caching, DNSE answers -> JSON, error mapping."""
import httpx
import pytest

import api
import dnse
import engine
import sources
from config import settings

SECDEF = [{"marketId": "STO", "boardId": "G4", "basicPrice": 11.6, "ceilingPrice": 12.4, "floorPrice": 10.8,
           "securityStatus": "NO_HALT", "time": "2026-11-10 08:00:27.155"},
          {"marketId": "STO", "boardId": "G1", "basicPrice": 11.6, "ceilingPrice": 12.4, "floorPrice": 10.8,
           "securityStatus": "NO_HALT", "time": "2026-11-10 08:00:27.145"}]
QUOTES = {"quotes": [
    {"boardId": "G1", "marketId": "STO", "time": "2026-11-10 10:54:20.320",
     "bid": [{"price": 11.75, "quantity": 10840}, {"price": 11.7, "quantity": 9630}],
     "offer": [{"price": 11.8, "quantity": 18510}]},
    {"boardId": "G4", "marketId": "STO", "time": "2026-11-10 10:52:47.673",
     "bid": [{"price": 11.75, "quantity": 49}], "offer": []}]}


def test_history_is_cached_and_daily_times_are_dates(client, clock, fake_dnse):
    dnse_ = fake_dnse({"/price/ohlc": {"t": [1794189600], "o": [11.75], "h": [11.9], "l": [11.45],
                                       "c": [11.6], "v": [5237000]}})
    a = client.get("/stock/pdr/history?interval=1D").json()
    b = client.get("/stock/PDR/history?interval=1D").json()
    assert a == b == {"symbol": "PDR", "interval": "1D", "count": 1, "data": [
        {"time": "2026-11-09", "open": 11.75, "high": 11.9, "low": 11.45, "close": 11.6, "volume": 5237000}]}
    assert len(dnse_.calls) == 1


def test_intraday_history_and_index_names(client, clock, fake_dnse):
    dnse_ = fake_dnse({"/price/ohlc": {"t": [1794282600], "o": [1700.0], "h": [1701.0], "l": [1699.0],
                                       "c": [1700.5], "v": [95600]}})
    body = client.get("/index/hnxindex/history?interval=1m&start=2026-11-10").json()
    assert body["symbol"] == "HNXINDEX" and body["data"][0]["time"] == "2026-11-10T10:50:00"
    assert dnse_.calls[0][1]["symbol"] == "HNX" and dnse_.calls[0][1]["type"] == "INDEX"
    assert dnse_.calls[0][1]["resolution"] == "1"


def test_history_limit_keeps_the_newest(client, clock, fake_dnse):
    fake_dnse({"/price/ohlc": {"t": [1793844000, 1793930400, 1794189600], "o": [1, 2, 3], "h": [1, 2, 3],
                               "l": [1, 2, 3], "c": [1, 2, 3], "v": [1, 2, 3]}})
    body = client.get("/stock/PDR/history?limit=2").json()
    assert [c["close"] for c in body["data"]] == [2, 3]


def test_history_rejects_bad_interval(client):
    assert client.get("/stock/PDR/history?interval=1M").status_code == 422


def test_day_range_uses_exchange_band(client, clock, monkeypatch):
    engine.LISTING = {"SHS": {"name": "SHS", "nameEn": None, "exchange": "HNX", "type": "stock"}}
    monkeypatch.setattr(sources, "daily_bars", lambda s, a, b: [
        {"date": "2026-11-05", "open": 20, "high": 20, "low": 20, "close": 20.0, "volume": 1},
        {"date": "2026-11-06", "open": 20, "high": 21, "low": 19, "close": 21.0, "volume": 1}])
    body = client.get("/stock/SHS/day-range?start_date=2026-11-06&end_date=2026-11-06").json()
    assert body["total_sessions"] == 1
    assert body["sessions"][0] | {} == {**body["sessions"][0], "reference_price": 20.0, "ceiling": 22.0, "floor": 18.0}
    assert client.get("/stock/SHS/day-range?start_date=06-11-2026&end_date=2026-11-06").status_code == 400


def test_quote_has_official_limits_and_round_lot_book(client, fake_dnse):
    fake_dnse({"/price/PDR/secdef": SECDEF, "/price/PDR/quotes/latest": QUOTES})
    q = client.get("/stock/PDR/quote").json()
    assert q == {"symbol": "PDR", "exchange": "HOSE", "trading_date": "2026-11-10",
                 "reference_price": 11.6, "ceiling_price": 12.4, "floor_price": 10.8, "status": "NO_HALT",
                 "bid": [{"price": 11.75, "volume": 108400}, {"price": 11.7, "volume": 96300}],
                 "ask": [{"price": 11.8, "volume": 185100}], "time": "2026-11-10T10:54:20"}
    assert client.get("/quotes?symbols=PDR").json()["count"] == 1


def test_quote_unknown_symbol_is_404(client, fake_dnse):
    fake_dnse({"/price/XYZ/secdef": [], "/price/XYZ/quotes/latest": {"quotes": []}})
    assert client.get("/stock/XYZ/quote").status_code == 404


def test_foreign_flow_one_call_per_weekday(client, fake_dnse):
    row = {"totalBuyVolume": 594000, "totalSellVolume": 260500, "totalBuyTradedAmount": 7011200000,
           "totalSellTradedAmount": 3074775000, "foreignerBuyPossibleQuantity": 49890000}
    dnse_ = fake_dnse({"/price/PDR/foreign-trading": {"foreigners": [row]}})
    body = client.get("/stock/PDR/foreign-flow?start=2026-11-06&end=2026-11-09").json()
    assert [d["date"] for d in body["data"]] == ["2026-11-06", "2026-11-09"]      # weekend skipped
    assert body["data"][0] | {} == {**body["data"][0], "net_volume": 333500, "net_value": 3936425000}
    assert len(dnse_.calls) == 2 and dnse_.calls[0][1]["limit"] == 1


def test_symbols_come_from_the_listing(client):
    engine.LISTING = {"VNM": {"name": "Vinamilk", "nameEn": None, "exchange": "HOSE", "type": "stock"},
                      "PDR": {"name": "Phát Đạt", "nameEn": None, "exchange": "HOSE", "type": "stock"}}
    body = client.get("/symbols").json()
    assert body["count"] == 2 and body["data"][0]["symbol"] == "PDR"


@pytest.mark.parametrize("exc, status, hint_part", [
    (dnse.NotConfigured("DNSE_API_KEY / DNSE_API_SECRET chưa được đặt"), 503, "DNSE_API_KEY"),
    (dnse.AuthFailed("DNSE 401: bad signature"), 503, "đồng hồ server"),
    (dnse.RateLimited("DNSE 429: Rate Limit Exceeded"), 429, "theo giờ"),
    (dnse.QuotaExceeded("DNSE 403: OA-401"), 429, "trong ngày"),
    (dnse.DnseError("DNSE 500: internal"), 503, "thử lại sau"),
])
def test_dnse_errors_map_to_http(client, monkeypatch, exc, status, hint_part):
    def boom(*_):
        raise exc
    monkeypatch.setattr(sources, "candles", boom)
    r = client.get("/stock/PDR/history")
    assert r.status_code == status
    assert r.json()["detail"] == str(exc) and hint_part in r.json()["hint"]


def test_unexpected_error_is_500_without_details(client, monkeypatch):
    monkeypatch.setattr(sources, "candles", lambda *_: {}["boom"])
    r = client.get("/stock/PDR/history")
    assert r.status_code == 500 and "boom" not in r.text


def test_shared_budget_protects_the_key(client, monkeypatch, fake_dnse):
    monkeypatch.setattr(engine.budget, "per_minute", 7)
    monkeypatch.setattr(engine.budget, "reserved", 6)
    fake_dnse({"/price/ohlc": {"t": [], "o": [], "h": [], "l": [], "c": [], "v": []}})
    assert client.get("/stock/PDR/history").status_code == 200
    r = client.get("/stock/VNM/history")
    assert r.status_code == 429 and r.headers["retry-after"] == "15"


def test_status_reports_key_and_limits(client, monkeypatch, fake_dnse):
    monkeypatch.setenv("DNSE_API_KEY", "k")
    monkeypatch.setenv("DNSE_API_SECRET", "s")
    fake = fake_dnse({})
    fake.limits["/price/ohlc"] = {"limit": 100000, "remaining": 99006}
    body = client.get("/status").json()
    assert body["keyConfigured"] is True and body["dnseLimits"]["/price/ohlc"]["remaining"] == 99006


def test_removed_endpoints_are_gone(client):
    for path in ("/stock/PDR/company", "/stock/PDR/financials/income_statement", "/indices",
                 "/index/VN30/members", "/groups/VN30/symbols", "/stock/PDR/trades"):
        assert client.get(path).status_code == 404, path


def test_docs_toggle():
    assert api.app.docs_url == ("/docs" if settings.ENABLE_DOCS else None)


@pytest.mark.parametrize("path, fn", [
    ("/stock/PDR/foreign-flow", "foreign_flow"),
    ("/stock/PDR/history", "candles"),
    ("/index/VNINDEX/history", "candles"),
])
def test_start_and_end_are_separate_parameters(client, monkeypatch, path, fn):
    seen = []

    def spy(*args):
        seen.append(args)
        return []
    monkeypatch.setattr(sources, fn, spy)
    client.get(f"{path}?start=2026-11-03")
    client.get(f"{path}?start=2026-11-03&end=2026-11-06")
    start_end = [a[1:3] if fn == "foreign_flow" else a[2:4] for a in seen]
    assert start_end == [("2026-11-03", None), ("2026-11-03", "2026-11-06")]


# ---------------------------------------------------------------- the DNSE client itself

def test_signature_follows_dnse_docs():
    import base64, hashlib, hmac
    date, nonce = "Fri, 15 May 2026 07:11:30 GMT", "0123456789abcdef0123456789abcdef"
    headers = dnse.signed_headers("KEY", "SECRET", "GET", "/price/ohlc", date=date, nonce=nonce)
    expected = base64.b64encode(hmac.new(b"SECRET", (
        "(request-target): get /price/ohlc\ndate: " + date + "\nnonce: " + nonce).encode(), hashlib.sha256).digest()).decode()
    expected = expected.replace("+", "%2B").replace("/", "%2F").replace("=", "%3D")
    assert headers["x-api-key"] == "KEY" and headers["Date"] == date and headers["version"] == dnse.API_VERSION
    assert headers["X-Signature"] == (f'Signature keyId="KEY",algorithm="hmac-sha256",headers="(request-target) date",'
                                      f'signature="{expected}",nonce="{nonce}"')


@pytest.mark.parametrize("status, body, error", [
    (429, '{"error": "Rate Limit Exceeded"}', dnse.RateLimited),
    (403, '{"status": "error", "message": "Quota exceeded", "code": "OA-401"}', dnse.QuotaExceeded),
    (400, '{"code": "OA-400", "message": "Authorization field missing, malformed or invalid"}', dnse.AuthFailed),
    (502, "bad gateway", dnse.DnseError),
])
def test_client_maps_dnse_status_codes(status, body, error):
    transport = httpx.MockTransport(lambda request: httpx.Response(status, text=body))
    with pytest.raises(error):
        dnse.Client("k", "s", transport=transport).get("/price/ohlc")


def test_client_signs_the_path_and_records_limits():
    seen = {}

    def handler(request):
        seen["path"], seen["sig"] = request.url.path, request.headers["X-Signature"]
        return httpx.Response(200, json={"ok": 1}, headers={"X-RateLimit-Limit": "10000", "X-RateLimit-Remaining": "9993"})
    client = dnse.Client("k", "s", transport=httpx.MockTransport(handler))
    assert client.get("/price/PDR/secdef", {"boardId": "G1"}) == {"ok": 1}
    assert seen["path"] == "/price/PDR/secdef" and 'keyId="k"' in seen["sig"]
    assert client.limits == {"/price/{symbol}/secdef": {"limit": 10000, "remaining": 9993}}


def test_client_without_key_fails_clearly():
    with pytest.raises(dnse.NotConfigured):
        dnse.Client("", "").get("/price/ohlc")
