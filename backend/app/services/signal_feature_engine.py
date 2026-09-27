from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from statistics import mean, pstdev
from typing import Any


@dataclass(frozen=True)
class FeatureFamily:
    name: str
    value: float
    quality: float
    freshness: float = 1.0
    evidence: tuple[str, ...] = ()


def _clip(value: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, float(value)))


def _z(value: float | None, series: list[float], default: float = 0.0) -> float:
    if value is None or not series or not isfinite(float(value)):
        return default
    sigma = pstdev(series)
    if sigma <= 1e-12:
        return default
    return _clip((float(value) - mean(series)) / (3.0 * sigma))


def build_feature_families(indicators: dict[str, Any], *, price: float | None = None, history: list[dict[str, Any]] | None = None) -> tuple[FeatureFamily, ...]:
    history = history or []
    price = float(price if price is not None else indicators.get("price") or 0.0)
    families: list[FeatureFamily] = []

    ema50, ema200 = indicators.get("ema50"), indicators.get("ema200")
    trend = 1.0 if indicators.get("trend") == "BULLISH" else -1.0 if indicators.get("trend") == "BEARISH" else 0.0
    if isinstance(ema50, (int, float)) and isinstance(ema200, (int, float)) and price > 0:
        trend = _clip(0.45 * trend + 0.30 * _clip((price - float(ema50)) / max(abs(price), 1e-12) * 40) + 0.25 * _clip((price - float(ema200)) / max(abs(price), 1e-12) * 20))
    families.append(FeatureFamily("trend", trend, 1.0 if ema50 is not None and ema200 is not None else 0.5, evidence=("Trend family combines EMA stack and normalized price location.",)))

    rsi = indicators.get("rsi14")
    macd = indicators.get("macd_histogram")
    momentum = 0.0
    if isinstance(rsi, (int, float)):
        momentum += _clip((float(rsi) - 50.0) / 25.0) * 0.55
    if isinstance(macd, (int, float)):
        momentum += _clip(float(macd) / max(abs(float(indicators.get("atr14") or 1.0)), 1e-12)) * 0.45
    families.append(FeatureFamily("momentum", _clip(momentum), 1.0 if rsi is not None or macd is not None else 0.0, evidence=("Momentum preserves RSI distance and MACD magnitude instead of binary votes.",)))

    atr = indicators.get("atr14")
    atr_pct = float(atr) / price if isinstance(atr, (int, float)) and price > 0 else 0.0
    families.append(FeatureFamily("volatility", _clip(atr_pct * 100.0 - 1.0), 1.0 if atr is not None else 0.0, evidence=("Volatility is represented as ATR percent of price.",)))

    vwap = indicators.get("vwap")
    location = _clip((price - float(vwap)) / max(abs(float(atr)), 1e-12) / 3.0) if isinstance(vwap, (int, float)) and isinstance(atr, (int, float)) and atr else 0.0
    families.append(FeatureFamily("location", location, 1.0 if vwap is not None and atr else 0.5, evidence=("Location is normalized by ATR rather than a raw price difference.",)))

    volume = indicators.get("obv")
    volume_quality = 1.0 if volume is not None else 0.0
    families.append(FeatureFamily("volume", 0.0, volume_quality, evidence=("Volume family is reserved for incremental volume evidence; OBV alone is not counted as an independent trend vote.",)))

    return tuple(families)


def family_score(families: tuple[FeatureFamily, ...], weights: dict[str, float] | None = None) -> float:
    weights = weights or {"trend": 0.25, "momentum": 0.20, "volatility": 0.10, "location": 0.15, "volume": 0.05}
    weighted = [(family.value, weights.get(family.name, 0.0) * family.quality) for family in families if family.quality > 0]
    denominator = sum(weight for _, weight in weighted)
    return _clip(sum(value * weight for value, weight in weighted) / denominator) if denominator else 0.0
