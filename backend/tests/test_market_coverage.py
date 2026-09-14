from app.preferences.models import default_preferences
from app.preferences.schemas import UserPreferences
from app.services.settings_integration import market_coverage
from app.symbols import CRYPTO_PAIRS, FOREX_PAIRS, STOCKS, symbols_for_asset_classes


def test_market_universe_contains_requested_counts_and_symbols() -> None:
    assert len(CRYPTO_PAIRS) == 10
    assert len(FOREX_PAIRS) == 10
    assert len(STOCKS) == 10
    assert "BTC/USDT" in CRYPTO_PAIRS
    assert "ETH/USDT" in CRYPTO_PAIRS
    assert "LTC/USDT" in CRYPTO_PAIRS
    assert "NZDUSD" in FOREX_PAIRS
    assert "USDJPY" in FOREX_PAIRS
    assert "XAUUSD" in FOREX_PAIRS
    assert "NVDA" in STOCKS
    assert "AAPL" in STOCKS
    assert "SPY" in STOCKS
    assert "AVGO" in STOCKS


def test_market_coverage_defaults_enable_every_asset_class() -> None:
    preferences = UserPreferences.model_validate(default_preferences())
    coverage = market_coverage(type("Record", (), {"market_data_preferences": preferences.market_data_preferences})())
    assert coverage.crypto_enabled is True
    assert coverage.forex_enabled is True
    assert coverage.stocks_enabled is True
    assert len(coverage.enabled_symbols) == 30


def test_market_coverage_filters_enabled_classes_before_quote_requests() -> None:
    assert symbols_for_asset_classes(crypto=True, forex=False, stocks=False) == CRYPTO_PAIRS
    assert symbols_for_asset_classes(crypto=False, forex=True, stocks=False) == FOREX_PAIRS
    assert symbols_for_asset_classes(crypto=False, forex=False, stocks=True) == STOCKS
    assert len(symbols_for_asset_classes(crypto=True, forex=True, stocks=False)) == 20
    assert len(symbols_for_asset_classes(crypto=True, forex=False, stocks=True)) == 20
    assert len(symbols_for_asset_classes(crypto=False, forex=True, stocks=True)) == 20
    assert symbols_for_asset_classes(crypto=False, forex=False, stocks=False) == ()


def test_market_data_preferences_validate_three_visibility_toggles() -> None:
    values = default_preferences()
    values["market_data_preferences"]["crypto_enabled"] = False
    values["market_data_preferences"]["forex_enabled"] = True
    values["market_data_preferences"]["stocks_enabled"] = False
    preferences = UserPreferences.model_validate(values)
    assert preferences.market_data_preferences.crypto_enabled is False
    assert preferences.market_data_preferences.forex_enabled is True
    assert preferences.market_data_preferences.stocks_enabled is False
