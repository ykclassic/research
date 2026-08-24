from app.symbols import normalize_symbol


def test_symbol_normalization():
    mapping = normalize_symbol(" btc/usd ")
    assert mapping.internal == "BTC/USD"
    assert mapping.twelve_data == "BTC/USD"


def test_unknown_symbol_rejected():
    try:
        normalize_symbol("NOT_A_REAL_SYMBOL")
    except ValueError:
        pass
    else:
        raise AssertionError("Expected ValueError")
