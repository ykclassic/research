from __future__ import annotations

import os
import sys
import time
from typing import Any

import requests


API_URL = os.getenv("TEST_API_URL", "https://research-76vr.onrender.com").rstrip("/")
EMAIL = os.getenv("TEST_EMAIL", "").strip()
PASSWORD = os.getenv("TEST_PASSWORD", "")
TIMEOUT = float(os.getenv("TEST_TIMEOUT_SECONDS", "30"))


def fail(message: str) -> None:
    print(f"FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def expect(response: requests.Response, status: int, label: str) -> dict[str, Any]:
    if response.status_code != status:
        body = response.text[:500].replace("\n", " ")
        fail(f"{label}: expected HTTP {status}, got {response.status_code}: {body}")
    try:
        return response.json() if response.content else {}
    except ValueError as exc:
        fail(f"{label}: response was not valid JSON")
        raise exc


def csrf_headers(session: requests.Session) -> dict[str, str]:
    response = session.get(f"{API_URL}/api/auth/csrf", timeout=TIMEOUT)
    expect(response, 200, "/api/auth/csrf")
    token = response.headers.get("X-CSRF-Token") or session.cookies.get("mr_csrf")
    if not token:
        fail("/api/auth/csrf: no CSRF token returned")
    # Deliberately omit Origin: this verifies the signed-CSRF API-client path.
    return {"X-CSRF-Token": token}


def main() -> None:
    if not EMAIL or not PASSWORD:
        fail("TEST_EMAIL and TEST_PASSWORD GitHub Actions secrets are required")

    session = requests.Session()
    session.headers.update({"Accept": "application/json", "User-Agent": "production-portfolio-e2e/1.0"})

    response = session.get(f"{API_URL}/api/portfolio/positions", timeout=TIMEOUT)
    expect(response, 401, "unauthenticated portfolio access")

    response = session.post(
        f"{API_URL}/api/auth/login",
        json={"email": EMAIL, "password": PASSWORD},
        timeout=TIMEOUT,
    )
    user = expect(response, 200, "/api/auth/login")
    if user.get("email", "").lower() != EMAIL.lower():
        fail("/api/auth/login: authenticated email does not match TEST_EMAIL")

    response = session.get(f"{API_URL}/api/auth/me", timeout=TIMEOUT)
    me = expect(response, 200, "/api/auth/me")
    if me.get("email", "").lower() != EMAIL.lower():
        fail("/api/auth/me: authenticated email does not match TEST_EMAIL")

    headers = csrf_headers(session)
    payload = {
        "symbol": "BTC/USD",
        "side": "LONG",
        "quantity": 0.0001,
        "average_entry_price": 100000.0,
        "notes": "production E2E verification - safe test position",
    }
    position_id: str | None = None
    try:
        response = session.post(f"{API_URL}/api/portfolio/positions", json=payload, timeout=TIMEOUT)
        expect(response, 403, "create portfolio position without CSRF")

        response = session.post(f"{API_URL}/api/portfolio/positions", json=payload, headers=headers, timeout=TIMEOUT)
        created = expect(response, 201, "create portfolio position")
        position_id = created.get("id")
        if not position_id:
            fail("create portfolio position: response did not contain an id")
        if created.get("symbol") != "BTC/USD" or created.get("side") != "LONG":
            fail("create portfolio position: normalized position fields are incorrect")

        update_payload = {
            "quantity": 0.0002,
            "average_entry_price": 101000.0,
            "notes": "production E2E update verification",
        }
        response = session.patch(f"{API_URL}/api/portfolio/positions/{position_id}", json=update_payload, timeout=TIMEOUT)
        expect(response, 403, "update portfolio position without CSRF")

        response = session.patch(f"{API_URL}/api/portfolio/positions/{position_id}", json=update_payload, headers=headers, timeout=TIMEOUT)
        updated = expect(response, 200, "update portfolio position")
        if updated.get("id") != position_id:
            fail("update portfolio position: returned position id changed")
        if updated.get("user_id") != user.get("id"):
            fail("update portfolio position: ownership changed")
        if updated.get("quantity") != 0.0002 or updated.get("average_entry_price") != 101000.0:
            fail("update portfolio position: updated numeric fields were not persisted")
        if updated.get("notes") != update_payload["notes"]:
            fail("update portfolio position: updated notes were not persisted")

        response = session.patch(
            f"{API_URL}/api/portfolio/positions/00000000-0000-0000-0000-000000000000",
            json={"notes": "must not update another row"},
            headers=headers,
            timeout=TIMEOUT,
        )
        expect(response, 404, "owner-scoped update of non-owned/nonexistent position")

        response = session.get(f"{API_URL}/api/portfolio/positions", timeout=TIMEOUT)
        positions = expect(response, 200, "list portfolio positions").get("positions")
        if not isinstance(positions, list) or not any(
            p.get("id") == position_id and p.get("quantity") == 0.0002 and p.get("average_entry_price") == 101000.0
            for p in positions
        ):
            fail("list portfolio positions: updated position was not returned")

        response = session.get(f"{API_URL}/api/portfolio/summary", timeout=TIMEOUT)
        summary = expect(response, 200, "portfolio summary")
        if summary.get("position_count", 0) < 1:
            fail("portfolio summary: expected at least one position")
        if not isinstance(summary.get("positions"), list):
            fail("portfolio summary: positions snapshot missing")
        snapshot = next((p for p in summary["positions"] if p.get("position", {}).get("id") == position_id), None)
        if snapshot is None:
            fail("portfolio summary: created position missing from snapshots")
        if snapshot.get("current_price") is None:
            fail("portfolio summary: current provider-backed price was unavailable")
        if snapshot.get("quote_status") not in {"LIVE", "DELAYED"}:
            fail(f"portfolio summary: unexpected quote status {snapshot.get('quote_status')!r}")
        if not snapshot.get("quote_timestamp"):
            fail("portfolio summary: provider quote timestamp missing")

        response = session.post(f"{API_URL}/api/portfolio/scenario", json={"price_change_percent": 10}, headers=headers, timeout=TIMEOUT)
        scenario = expect(response, 200, "portfolio scenario")
        if scenario.get("affected_positions", 0) < 1:
            fail("portfolio scenario: created position was not affected")
        if scenario.get("price_change_percent") != 10:
            fail("portfolio scenario: requested shock was not preserved")

        response = session.post(f"{API_URL}/api/portfolio/risk-reward", json={"entry_price": 100000, "stop_loss": 99000, "take_profit": 102000, "side": "LONG"}, headers=headers, timeout=TIMEOUT)
        rr = expect(response, 200, "portfolio risk-reward")
        if rr.get("reward_risk_ratio") != 2 or rr.get("valid") is not True:
            fail("portfolio risk-reward: expected valid 2:1 setup")

    finally:
        if position_id:
            response = session.delete(f"{API_URL}/api/portfolio/positions/{position_id}", headers=headers, timeout=TIMEOUT)
            if response.status_code != 204:
                fail(f"delete portfolio position: expected HTTP 204, got {response.status_code}: {response.text[:300]}")
            for _ in range(3):
                response = session.get(f"{API_URL}/api/portfolio/positions", timeout=TIMEOUT)
                positions = expect(response, 200, "verify portfolio cleanup").get("positions", [])
                if not any(p.get("id") == position_id for p in positions):
                    break
                time.sleep(0.5)
            else:
                fail("verify portfolio cleanup: test position is still present")

    print("PRODUCTION PORTFOLIO E2E: PASS")
    print(f"/api/auth/me: {me.get('email')}")
    print("/api/portfolio/positions: create/list/update/delete 200/201/204")
    print("/api/portfolio/update: CSRF required; owner-scoped")
    print("/api/portfolio/summary: 200 with provider-backed quote")
    print("/api/portfolio/scenario: 200")
    print("/api/portfolio/risk-reward: 200")
    print("production test position: cleaned up")


if __name__ == "__main__":
    main()
