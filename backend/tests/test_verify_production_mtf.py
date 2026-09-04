from scripts.verify_production_mtf import DURATION_BY_TIMEFRAME, EXPECTED_TIMEFRAMES


def test_production_mtf_verifier_matches_backend_timeframe_values() -> None:
    assert EXPECTED_TIMEFRAMES == {"1d", "4h", "1h", "15m"}
    assert DURATION_BY_TIMEFRAME == {"15m": 900, "1h": 3600, "4h": 14400, "1d": 86400}
