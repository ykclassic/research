from datetime import datetime, timezone

import httpx

from scripts.verify_production_mtf import completed_candle_age_seconds, request_mtf
from scripts.verify_production_regime import completed_candle_close


def test_mtf_daily_age_is_measured_from_completed_close() -> None:
    candle_open = datetime(2026, 9, 4, 0, 0, tzinfo=timezone.utc)
    now = datetime(2026, 9, 5, 4, 0, tzinfo=timezone.utc)

    assert completed_candle_age_seconds(candle_open, "1d", now) == 4 * 60 * 60


def test_mtf_hourly_age_is_measured_from_completed_close() -> None:
    candle_open = datetime(2026, 9, 5, 3, 0, tzinfo=timezone.utc)
    now = datetime(2026, 9, 5, 4, 30, tzinfo=timezone.utc)

    assert completed_candle_age_seconds(candle_open, "1h", now) == 30 * 60


def test_regime_completed_close_matches_timeframe_duration() -> None:
    candle_open = datetime(2026, 9, 4, 0, 0, tzinfo=timezone.utc)

    assert completed_candle_close(candle_open, "1d") == datetime(
        2026, 9, 5, 0, 0, tzinfo=timezone.utc
    )


def test_mtf_request_retries_transient_read_timeouts(monkeypatch) -> None:
    class FlakyClient:
        def __init__(self) -> None:
            self.calls = 0

        def get(self, url, *, params, headers):
            self.calls += 1
            if self.calls < 3:
                raise httpx.ReadTimeout("temporary Render read timeout")
            return httpx.Response(200, request=httpx.Request("GET", url), json={"timeframes": []})

    monkeypatch.setattr("scripts.verify_production_mtf.time.sleep", lambda _: None)

    client = FlakyClient()
    response = request_mtf(client, "https://example.test/api/mtf/BTC/USD", headers={})

    assert response.status_code == 200
    assert client.calls == 3
