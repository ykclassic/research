from datetime import datetime, timezone
from unittest import IsolatedAsyncioTestCase
from unittest.mock import patch

from app.models import QuoteStatus
from app.providers.twelve_data import TwelveDataProvider


class FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class FakeAsyncClient:
    last_params: dict | None = None
    payload: dict = {}

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url, *, params):
        type(self).last_params = params
        return FakeResponse(type(self).payload)


class TwelveDataQuoteTests(IsolatedAsyncioTestCase):
    async def test_quote_requests_one_minute_interval_and_preserves_provider_timestamp(self):
        provider_timestamp = datetime.now(timezone.utc).replace(microsecond=0)
        FakeAsyncClient.payload = {
            "symbol": "BTC/USD",
            "close": "77507.17",
            "timestamp": int(provider_timestamp.timestamp()),
            "last_update_at": provider_timestamp.isoformat(),
        }
        FakeAsyncClient.last_params = None

        with patch("app.providers.twelve_data.httpx.AsyncClient", FakeAsyncClient), patch.object(
            __import__("app.providers.twelve_data", fromlist=["settings"]).settings,
            "twelve_data_api_key",
            "test-key",
        ), patch.object(
            __import__("app.providers.twelve_data", fromlist=["settings"]).settings,
            "http_max_retries",
            0,
        ), patch.object(
            __import__("app.providers.twelve_data", fromlist=["settings"]).settings,
            "stale_quote_seconds",
            180,
        ):
            quote = await TwelveDataProvider().get_quote("BTC/USD")

        self.assertEqual(quote.status, QuoteStatus.LIVE)
        self.assertEqual(quote.timestamp, provider_timestamp)
        self.assertEqual(quote.provider_timestamp, provider_timestamp)
        self.assertEqual(FakeAsyncClient.last_params["interval"], "1min")

    async def test_stale_provider_quote_is_not_marked_live_or_given_server_timestamp(self):
        stale_timestamp = datetime(2026, 8, 28, 23, 55, tzinfo=timezone.utc)
        FakeAsyncClient.payload = {
            "symbol": "BTC/USD",
            "close": "77507.17",
            "timestamp": int(stale_timestamp.timestamp()),
        }
        FakeAsyncClient.last_params = None

        settings = __import__("app.providers.twelve_data", fromlist=["settings"]).settings
        with patch("app.providers.twelve_data.httpx.AsyncClient", FakeAsyncClient), patch.object(
            settings, "twelve_data_api_key", "test-key"
        ), patch.object(settings, "http_max_retries", 0), patch.object(
            settings, "stale_quote_seconds", 180
        ):
            quote = await TwelveDataProvider().get_quote("BTC/USD")

        self.assertEqual(quote.status, QuoteStatus.UNAVAILABLE)
        self.assertIsNone(quote.provider_timestamp)
        self.assertIn("stale", quote.error.lower())
