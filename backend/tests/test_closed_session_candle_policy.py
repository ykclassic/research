from datetime import datetime, timezone

from app.services.market_sessions import closed_session_candle_is_usable


def utc(year, month, day, hour, minute=0, second=0):
    return datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)


def test_fx_closed_session_admits_completed_candle_within_60_hour_cap():
    # Latest candle closed Wednesday 17:00 ET; observed Saturday 05:00 ET.
    assert closed_session_candle_is_usable(
        "EUR/USD",
        utc(2026, 11, 18, 20),
        3600,
        at=utc(2026, 11, 21, 10),
    )


def test_fx_closed_session_rejects_candle_older_than_60_hour_cap():
    # Latest candle closed Wednesday 16:00 ET; observed Saturday 05:00 ET.
    assert not closed_session_candle_is_usable(
        "EUR/USD",
        utc(2026, 11, 18, 21),
        3600,
        at=utc(2026, 11, 21, 10),
    )


def test_fx_weekend_exception_ends_when_market_reopens():
    # Sunday 17:00 ET is the conventional FX reopen.
    assert not closed_session_candle_is_usable(
        "EUR/USD",
        utc(2026, 11, 20, 21),
        3600,
        at=utc(2026, 11, 22, 22),
    )


def test_us_equity_closed_session_admits_candle_within_72_hour_cap():
    # Latest candle closed Thursday 16:00 ET; observed Sunday 16:00 ET.
    assert closed_session_candle_is_usable(
        "AAPL",
        utc(2026, 11, 19, 20),
        3600,
        at=utc(2026, 11, 22, 21),
    )


def test_us_equity_closed_session_rejects_candle_older_than_72_hour_cap():
    # Latest candle closed Thursday 15:00 ET; observed Sunday 16:00 ET.
    assert not closed_session_candle_is_usable(
        "AAPL",
        utc(2026, 11, 19, 19),
        3600,
        at=utc(2026, 11, 22, 21),
    )


def test_crypto_never_receives_closed_session_exception():
    assert not closed_session_candle_is_usable(
        "BTC/USD",
        utc(2026, 11, 20, 21),
        3600,
        at=utc(2026, 11, 21, 16),
    )


def test_future_dated_completed_candle_is_rejected():
    assert not closed_session_candle_is_usable(
        "EUR/USD",
        utc(2026, 11, 21, 16),
        3600,
        at=utc(2026, 11, 21, 16),
    )
