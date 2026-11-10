"""Small read-only client for the DNSE Lightspeed API (market data).

Written from DNSE's public docs:
- authentication: https://developers.dnse.com.vn/docs/guide/intro/authentication/
- rate limits:    https://developers.dnse.com.vn/docs/guide/ratelimits/

Every request is signed with HMAC-SHA256 over "(request-target)", "date" and "nonce", using your
API secret. No session, no OTP: market data only needs the key and secret.
"""
import base64
import hashlib
import hmac
import os
import threading
import uuid
from email.utils import formatdate
from typing import Optional

import httpx

BASE_URL = os.getenv("DNSE_BASE_URL", "https://openapi.dnse.com.vn")
API_VERSION = os.getenv("DNSE_API_VERSION", "2026-07-23")
TIMEOUT = float(os.getenv("DNSE_TIMEOUT", "10"))


class DnseError(Exception):
    """Any failure talking to DNSE. `status` is the HTTP status this API answers with."""
    status = 503
    hint = "DNSE đang lỗi hoặc không truy cập được, thử lại sau."


class NotConfigured(DnseError):
    status = 503
    hint = "Chưa có khoá DNSE. Đặt DNSE_API_KEY và DNSE_API_SECRET trong .env rồi khởi động lại."


class AuthFailed(DnseError):
    status = 503
    hint = "DNSE từ chối khoá: kiểm tra DNSE_API_KEY/DNSE_API_SECRET và đồng hồ server (lệch tối đa 1 phút)."


class RateLimited(DnseError):
    status = 429
    hint = "Đã chạm hạn mức gọi DNSE theo giờ, thử lại sau ít phút."


class QuotaExceeded(DnseError):
    status = 429
    hint = "Đã hết hạn mức gọi DNSE trong ngày."


def signature(secret: str, method: str, path: str, date: str, nonce: str) -> str:
    """Base64 HMAC-SHA256 of the signing string, with only + / = percent-encoded (per the docs)."""
    message = f"(request-target): {method.lower()} {path}\ndate: {date}\nnonce: {nonce}"
    raw = base64.b64encode(hmac.new(secret.encode(), message.encode(), hashlib.sha256).digest()).decode()
    return raw.replace("+", "%2B").replace("/", "%2F").replace("=", "%3D")


def signed_headers(key: str, secret: str, method: str, path: str,
                   date: Optional[str] = None, nonce: Optional[str] = None) -> dict:
    date = date or formatdate(usegmt=True)
    nonce = nonce or uuid.uuid4().hex
    sig = signature(secret, method, path, date, nonce)
    return {
        "x-api-key": key,
        "Date": date,
        "version": API_VERSION,
        "X-Signature": (f'Signature keyId="{key}",algorithm="hmac-sha256",'
                        f'headers="(request-target) date",signature="{sig}",nonce="{nonce}"'),
    }


class Client:
    def __init__(self, key: str, secret: str, base_url: str = BASE_URL, transport=None):
        self.key, self.secret = key, secret
        self.http = httpx.Client(base_url=base_url, timeout=TIMEOUT, transport=transport)
        # Last X-RateLimit-* headers seen, per path, for /status
        self.limits: dict = {}
        self._lock = threading.Lock()

    def get(self, path: str, params: Optional[dict] = None):
        if not (self.key and self.secret):
            raise NotConfigured("DNSE_API_KEY / DNSE_API_SECRET chưa được đặt")
        try:
            r = self.http.get(path, params=params, headers=signed_headers(self.key, self.secret, "GET", path))
        except httpx.HTTPError as exc:
            raise DnseError(f"DNSE không phản hồi: {type(exc).__name__}") from exc

        if "x-ratelimit-remaining" in r.headers:
            with self._lock:
                self.limits[_route(path)] = {"limit": _int(r.headers.get("x-ratelimit-limit")),
                                             "remaining": _int(r.headers.get("x-ratelimit-remaining"))}
        if r.status_code == 200:
            return r.json()
        body = r.text[:200]
        if r.status_code == 429:
            raise RateLimited(f"DNSE 429: {body}")
        if r.status_code == 403 and "OA-401" in body:
            raise QuotaExceeded(f"DNSE 403: {body}")
        if r.status_code in (400, 401, 403):
            raise AuthFailed(f"DNSE {r.status_code}: {body}")
        raise DnseError(f"DNSE {r.status_code}: {body}")


def _route(path: str) -> str:
    """/price/PDR/secdef -> /price/{symbol}/secdef, so /status lists one line per endpoint."""
    parts = path.strip("/").split("/")
    if len(parts) >= 3 and parts[0] == "price":
        parts[1] = "{symbol}"
    return "/" + "/".join(parts)


def _int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


_client: Optional[Client] = None


def client() -> Client:
    global _client
    if _client is None:
        _client = Client(os.getenv("DNSE_API_KEY", ""), os.getenv("DNSE_API_SECRET", ""))
    return _client
