from dataclasses import dataclass


@dataclass(frozen=True)
class SymbolMapping:
    internal: str
    twelve_data: str
    alpha_vantage: str
    finnhub: str
    asset_class: str


SYMBOLS: dict[str, SymbolMapping] = {
    "BTC/USD": SymbolMapping("BTC/USD", "BTC/USD", "BTC/USD", "BINANCE:BTCUSDT", "crypto"),
    "ETH/USD": SymbolMapping("ETH/USD", "ETH/USD", "ETH/USD", "BINANCE:ETHUSDT", "crypto"),
    "SOL/USD": SymbolMapping("SOL/USD", "SOL/USD", "SOL/USD", "BINANCE:SOLUSDT", "crypto"),
    "EUR/USD": SymbolMapping("EUR/USD", "EUR/USD", "EURUSD", "OANDA:EUR_USD", "forex"),
    "GBP/USD": SymbolMapping("GBP/USD", "GBP/USD", "GBPUSD", "OANDA:GBP_USD", "forex"),
    "USD/JPY": SymbolMapping("USD/JPY", "USD/JPY", "USDJPY", "OANDA:USD_JPY", "forex"),
    "NVDA": SymbolMapping("NVDA", "NVDA", "NVDA", "NVDA", "stock"),
    "AAPL": SymbolMapping("AAPL", "AAPL", "AAPL", "AAPL", "stock"),
    "MSFT": SymbolMapping("MSFT", "MSFT", "MSFT", "MSFT", "stock"),
    "SPY": SymbolMapping("SPY", "SPY", "SPY", "SPY", "etf"),
}


def normalize_symbol(symbol: str) -> SymbolMapping:
    key = symbol.strip().upper()
    if key not in SYMBOLS:
        raise ValueError(f"Unsupported symbol: {symbol}")
    return SYMBOLS[key]
