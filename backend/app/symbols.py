from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SymbolMapping:
    internal: str
    twelve_data: str
    asset_class: str
    display_name: str
    kraken: str | None = None


CRYPTO_PAIRS: tuple[str, ...] = (
    "BTC/USDT",
    "ETH/USDT",
    "BNB/USDT",
    "XRP/USDT",
    "LINK/USDT",
    "SOL/USDT",
    "DOGE/USDT",
    "ADA/USDT",
    "SUI/USDT",
    "LTC/USDT",
)

FOREX_PAIRS: tuple[str, ...] = (
    "NZDUSD",
    "EURUSD",
    "GBPUSD",
    "USDJPY",
    "AUDUSD",
    "USDCAD",
    "USDCHF",
    "EURGBP",
    "GBPJPY",
    "XAUUSD",
)

STOCKS: tuple[str, ...] = (
    "NVDA",
    "AAPL",
    "MSFT",
    "SPY",
    "AMZN",
    "GOOGL",
    "META",
    "TSLA",
    "JPM",
    "AVGO",
)


SYMBOLS: dict[str, SymbolMapping] = {
    "BTC/USDT": SymbolMapping("BTC/USDT", "BTC/USDT", "crypto", "Bitcoin / Tether", "XBTUSDT"),
    "ETH/USDT": SymbolMapping("ETH/USDT", "ETH/USDT", "crypto", "Ethereum / Tether", "ETHUSDT"),
    "BNB/USDT": SymbolMapping("BNB/USDT", "BNB/USDT", "crypto", "BNB / Tether", "BNBUSDT"),
    "XRP/USDT": SymbolMapping("XRP/USDT", "XRP/USDT", "crypto", "XRP / Tether", "XRPUSDT"),
    "LINK/USDT": SymbolMapping("LINK/USDT", "LINK/USDT", "crypto", "Chainlink / Tether", "LINKUSDT"),
    "SOL/USDT": SymbolMapping("SOL/USDT", "SOL/USDT", "crypto", "Solana / Tether", "SOLUSDT"),
    "DOGE/USDT": SymbolMapping("DOGE/USDT", "DOGE/USDT", "crypto", "Dogecoin / Tether", "DOGEUSDT"),
    "ADA/USDT": SymbolMapping("ADA/USDT", "ADA/USDT", "crypto", "Cardano / Tether", "ADAUSDT"),
    "SUI/USDT": SymbolMapping("SUI/USDT", "SUI/USDT", "crypto", "Sui / Tether", "SUIUSDT"),
    "LTC/USDT": SymbolMapping("LTC/USDT", "LTC/USDT", "crypto", "Litecoin / Tether", "LTCUSDT"),
    "NZDUSD": SymbolMapping("NZDUSD", "NZD/USD", "forex", "New Zealand Dollar / US Dollar"),
    "EURUSD": SymbolMapping("EURUSD", "EUR/USD", "forex", "Euro / US Dollar"),
    "GBPUSD": SymbolMapping("GBPUSD", "GBP/USD", "forex", "British Pound / US Dollar"),
    "USDJPY": SymbolMapping("USDJPY", "USD/JPY", "forex", "US Dollar / Japanese Yen"),
    "AUDUSD": SymbolMapping("AUDUSD", "AUD/USD", "forex", "Australian Dollar / US Dollar"),
    "USDCAD": SymbolMapping("USDCAD", "USD/CAD", "forex", "US Dollar / Canadian Dollar"),
    "USDCHF": SymbolMapping("USDCHF", "USD/CHF", "forex", "US Dollar / Swiss Franc"),
    "EURGBP": SymbolMapping("EURGBP", "EUR/GBP", "forex", "Euro / British Pound"),
    "GBPJPY": SymbolMapping("GBPJPY", "GBP/JPY", "forex", "British Pound / Japanese Yen"),
    "XAUUSD": SymbolMapping("XAUUSD", "XAU/USD", "forex", "Gold / US Dollar"),
    "NVDA": SymbolMapping("NVDA", "NVDA", "stock", "NVIDIA"),
    "AAPL": SymbolMapping("AAPL", "AAPL", "stock", "Apple"),
    "MSFT": SymbolMapping("MSFT", "MSFT", "stock", "Microsoft"),
    "SPY": SymbolMapping("SPY", "SPY", "etf", "SPDR S&P 500 ETF"),
    "AMZN": SymbolMapping("AMZN", "AMZN", "stock", "Amazon"),
    "GOOGL": SymbolMapping("GOOGL", "GOOGL", "stock", "Alphabet"),
    "META": SymbolMapping("META", "META", "stock", "Meta Platforms"),
    "TSLA": SymbolMapping("TSLA", "TSLA", "stock", "Tesla"),
    "JPM": SymbolMapping("JPM", "JPM", "stock", "JPMorgan Chase"),
    "AVGO": SymbolMapping("AVGO", "AVGO", "stock", "Broadcom"),
}


MARKET_UNIVERSE: dict[str, tuple[str, ...]] = {
    "crypto": CRYPTO_PAIRS,
    "forex": FOREX_PAIRS,
    "stocks": STOCKS,
}


def normalize_symbol(symbol: str) -> SymbolMapping:
    key = symbol.strip().upper()
    if key not in SYMBOLS:
        raise ValueError(f"Unsupported symbol: {symbol}")
    return SYMBOLS[key]


def symbols_for_asset_classes(*, crypto: bool, forex: bool, stocks: bool) -> tuple[str, ...]:
    enabled_classes = {
        "crypto": crypto,
        "forex": forex,
        "stocks": stocks,
    }
    return tuple(
        symbol
        for asset_class, symbols in MARKET_UNIVERSE.items()
        if enabled_classes[asset_class]
        for symbol in symbols
    )


def asset_class_for_symbol(symbol: str) -> str:
    return normalize_symbol(symbol).asset_class
