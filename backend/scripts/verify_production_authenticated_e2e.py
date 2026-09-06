from __future__ import annotations

import os
import sys
from urllib.parse import quote

import requests


API_URL = os.environ.get("TEST_API_URL", "https://research-76vr.onrender.com").rstrip("/")
EMAIL = os.environ.get("TEST_EMAIL")
PASSWORD = os.environ.get("TEST_PASSWORD")


def require_env() -> None:
    missing = [name for name, value in (("TEST_EMAIL", EMAIL), ("TEST_PASSWORD", PASSWORD)) if not value]
    if missing:
        raise RuntimeError(f"Missing required GitHub Actions secrets: {', '.join(missing)}")


def check(response: requests.Response, expected: int, label: str) -> dict:
    if response.status_code != expected:
        try:
            detail = response.json()
        except ValueError:
            detail = response.text[:500]
        raise RuntimeError(f"{label}: expected HTTP {expected}, got {response.status_code}: {detail}")
    try:
        return response.json()
    except ValueError:
        return {}


def main() -> int:
    require_env()
    session = requests.Session()
    session.headers.update({"User-Agent": "research-production-auth-e2e/1.0"})

    before = session.get(f"{API_URL}/api/auth/me", timeout=30)
    if before.status_code != 401:
        raise RuntimeError(f"Unauthenticated /api/auth/me expected HTTP 401, got {before.status_code}")

    login = session.post(
        f"{API_URL}/api/auth/login",
        json={"email": EMAIL, "password": PASSWORD},
        timeout=30,
    )
    user = check(login, 200, "Production login")
    if user.get("email", "").lower() != EMAIL.lower():
        raise RuntimeError("Production login returned an unexpected user email")

    me = check(session.get(f"{API_URL}/api/auth/me", timeout=30), 200, "Authenticated /api/auth/me")
    if me.get("email", "").lower() != EMAIL.lower():
        raise RuntimeError("Authenticated /api/auth/me returned an unexpected user")

    csrf_response = session.get(f"{API_URL}/api/auth/csrf", timeout=30)
    check(csrf_response, 200, "Authenticated CSRF issuance")
    csrf_token = csrf_response.headers.get("X-CSRF-Token") or session.cookies.get("mr_csrf")
    if not csrf_token:
        raise RuntimeError("Production CSRF token was not issued")

    history = check(
        session.get(f"{API_URL}/api/research-history?limit=10", timeout=30),
        200,
        "Authenticated research history",
    )
    if not isinstance(history.get("items"), list):
        raise RuntimeError("Research history response does not contain an items array")

    market = check(
        session.get(
            f"{API_URL}/api/market/quotes",
            params={"symbols": "BTC/USD", "refresh": "false"},
            timeout=30,
        ),
        200,
        "Authenticated market data",
    )
    quotes = market.get("quotes")
    if not isinstance(quotes, list) or not quotes:
        raise RuntimeError("Authenticated market data returned no quotes")

    regime_path = f"/api/regime/{quote('BTC/USD', safe='')}"
    regime = check(
        session.get(f"{API_URL}{regime_path}", params={"timeframe": "1h", "limit": 250}, timeout=60),
        200,
        "Authenticated regime API",
    )
    if regime.get("symbol") != "BTC/USD":
        raise RuntimeError("Authenticated regime API returned an unexpected symbol")

    print("PRODUCTION AUTHENTICATED E2E: PASS")
    print(f"Authenticated user: {EMAIL}")
    print("/api/auth/me: 200")
    print("/api/auth/csrf: 200")
    print(f"/api/research-history: 200 ({len(history['items'])} records returned)")
    print("/api/market/quotes: 200")
    print("/api/regime/BTC%2FUSD: 200")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"PRODUCTION AUTHENTICATED E2E: FAIL — {exc}", file=sys.stderr)
        raise SystemExit(1)
