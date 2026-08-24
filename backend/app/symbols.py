from dataclasses import dataclass


@dataclass(frozen=True)
class SymbolMapping:
    internal: str
    twelve_data: str
    asset_class: str


SYMBOLS: dict[str, SymbolMapping] = {
    "BTC/USD": SymbolMapping("BTC/USD", "BTC/USD", "crypto"),
    "ETH/USD": SymbolMapping("ETH/USD", "ETH/USD", "crypto"),
    "SOL/USD": SymbolMapping("SOL/USD", "SOL/USD", "crypto"),
    "EUR/USD": SymbolMapping("EUR/USD", "EUR/USD", "forex"),
    "GBP/USD": SymbolMapping("GBP/USD", "GBP/USD", "forex"),
    "USD/JPY": SymbolMapping("USD/JPY", "USD/JPY", "forex"),
    "NVDA": SymbolMapping("NVDA", "NVDA", "stock"),
    "AAPL": SymbolMapping("AAPL", "AAPL", "stock"),
    "MSFT": SymbolMapping("MSFT", "MSFT", "stock"),
    "SPY": SymbolMapping("SPY", "SPY", "etf"),
}


def normalize_symbol(symbol: str) -> SymbolMapping:
    key = symbol.strip().upper()
    if key not in SYMBOLS:
        raise ValueError(f"Unsupported symbol: {symbol}")
    return SYMBOLS[key]
