from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timezone
from math import isfinite
from zoneinfo import ZoneInfo

from app.models.market import OHLCVDataset


@dataclass(frozen=True)
class SessionState:
    asset_class: str
    label: str
    phase: str
    status: str
    market_open: bool
    volatility_score: float | None
    volatility_state: str
    activity_score: float | None
    liquidity_state: str
    starts_at: datetime | None
    ends_at: datetime | None
    next_transition_at: datetime | None
    volatility_source: str | None
    timestamp: datetime


SESSION_ZONE = ZoneInfo("America/New_York")
LONDON_ZONE = ZoneInfo("Europe/London")
TOKYO_ZONE = ZoneInfo("Asia/Tokyo")
SYDNEY_ZONE = ZoneInfo("Australia/Sydney")


def _in_window(now: datetime, start: time, end: time) -> bool:
    local = now.astimezone(SESSION_ZONE).time()
    if start <= end:
        return start <= local < end
    return local >= start or local < end


def _volatility(dataset: OHLCVDataset) -> tuple[float | None, str, float | None]:
    candles = [c for c in dataset.completed_candles if c.close > 0 and c.high >= c.low]
    if len(candles) < 20:
        return None, "UNKNOWN", None

    tr_percent: list[float] = []
    previous_close: float | None = None
    for candle in candles:
        reference = previous_close if previous_close and previous_close > 0 else candle.open
        true_range = max(candle.high - candle.low, abs(candle.high - reference), abs(candle.low - reference))
        value = true_range / reference * 100
        if isfinite(value):
            tr_percent.append(value)
        previous_close = candle.close

    if len(tr_percent) < 20:
        return None, "UNKNOWN", None

    atr_period = min(14, len(tr_percent))
    atr_values = [
        sum(tr_percent[index - atr_period + 1:index + 1]) / atr_period
        for index in range(atr_period - 1, len(tr_percent))
    ]
    if len(atr_values) < 10:
        return None, "UNKNOWN", None

    current = atr_values[-1]
    history = atr_values[:-1] or atr_values
    lower = min(history)
    upper = max(history)
    if upper <= lower:
        score = 50.0
    else:
        score = 100.0 * (current - lower) / (upper - lower)
        score = max(0.0, min(100.0, score))

    if score >= 80:
        state = "VERY_HIGH"
    elif score >= 60:
        state = "HIGH"
    elif score >= 40:
        state = "MODERATE"
    elif score >= 20:
        state = "LOW"
    else:
        state = "VERY_LOW"

    return round(score, 1), state, current


def _forex_phase(now: datetime) -> tuple[str, str, datetime | None, datetime | None]:
    london = now.astimezone(LONDON_ZONE)
    new_york = now.astimezone(SESSION_ZONE)
    tokyo = now.astimezone(TOKYO_ZONE)
    sydney = now.astimezone(SYDNEY_ZONE)

    # Session windows are represented in their local market time. DST is handled
    # by ZoneInfo rather than fixed UTC offsets.
    london_open = time(8, 0)
    london_close = time(17, 0)
    new_york_open = time(8, 0)
    new_york_close = time(17, 0)
    tokyo_open = time(9, 0)
    tokyo_close = time(18, 0)
    sydney_open = time(8, 0)
    sydney_close = time(17, 0)

    london_active = london.weekday() < 5 and london_open <= london.time() < london_close
    new_york_active = new_york.weekday() < 5 and new_york_open <= new_york.time() < new_york_close
    tokyo_active = tokyo.weekday() < 5 and tokyo_open <= tokyo.time() < tokyo_close
    sydney_active = sydney.weekday() < 5 and sydney_open <= sydney.time() < sydney_close

    if london_active and new_york_active:
        return "London / New York Overlap", "OVERLAP", None, None
    if new_york_active:
        return "New York", "NEW_YORK", None, None
    if london_active:
        return "London", "LONDON", None, None
    if tokyo_active:
        return "Tokyo", "TOKYO", None, None
    if sydney_active:
        return "Sydney", "SYDNEY", None, None
    return "Market Closed", "CLOSED", None, None


def build_session_state(
    *,
    asset_class: str,
    now: datetime,
    market_open: bool,
    dataset: OHLCVDataset | None,
    symbol: str,
) -> SessionState:
    now = now.astimezone(timezone.utc)
    score, volatility_state, _atr_percent = _volatility(dataset) if dataset else (None, "UNKNOWN", None)

    if asset_class == "crypto":
        # Crypto is continuously tradable. Regional windows describe activity,
        # not exchange opening/closing.
        ny = now.astimezone(SESSION_ZONE)
        if 8 <= ny.hour < 17:
            phase = "US_ACTIVITY"
            label = "US Activity Window"
        elif 2 <= ny.hour < 8:
            phase = "EUROPE_ACTIVITY"
            label = "Europe Activity Window"
        else:
            phase = "ASIA_ACTIVITY"
            label = "Asia Activity Window"
        activity = score
        return SessionState(
            asset_class="crypto",
            label=label,
            phase=phase,
            status="OPEN",
            market_open=True,
            volatility_score=score,
            volatility_state=volatility_state,
            activity_score=activity,
            liquidity_state="HIGH" if activity is not None and activity >= 60 else "MODERATE",
            starts_at=None,
            ends_at=None,
            next_transition_at=None,
            volatility_source=symbol,
            timestamp=now,
        )

    if asset_class == "forex":
        label, phase, _, _ = _forex_phase(now)
        is_open = market_open and now.weekday() < 5
        return SessionState(
            asset_class="forex",
            label=label if is_open else "Market Closed",
            phase=phase if is_open else "CLOSED",
            status="OPEN" if is_open else "CLOSED",
            market_open=is_open,
            volatility_score=score,
            volatility_state=volatility_state,
            activity_score=score,
            liquidity_state="HIGH" if score is not None and score >= 60 else "MODERATE",
            starts_at=None,
            ends_at=None,
            next_transition_at=None,
            volatility_source=symbol,
            timestamp=now,
        )

    # Equities use the core U.S. session for the dashboard state. The quote
    # provider remains authoritative for actual market-open/closed status,
    # including exchange holidays and early closes.
    local = now.astimezone(SESSION_ZONE)
    core_open = time(9, 30) <= local.time() < time(16, 0)
    early = time(4, 0) <= local.time() < time(9, 30)
    late = time(16, 0) <= local.time() < time(20, 0)
    if market_open and core_open:
        phase, label = "CORE", "US Core Session"
    elif market_open and early:
        phase, label = "EARLY", "US Early Session"
    elif market_open and late:
        phase, label = "LATE", "US Late Session"
    else:
        phase, label = "CLOSED", "Market Closed"

    return SessionState(
        asset_class="stocks",
        label=label,
        phase=phase,
        status="OPEN" if market_open else "CLOSED",
        market_open=market_open,
        volatility_score=score,
        volatility_state=volatility_state,
        activity_score=score,
        liquidity_state="VERY_HIGH" if phase == "CORE" else "MODERATE",
        starts_at=None,
        ends_at=None,
        next_transition_at=None,
        volatility_source=symbol,
        timestamp=now,
    )


def session_to_dict(state: SessionState) -> dict[str, object]:
    return {
        "asset_class": state.asset_class,
        "label": state.label,
        "phase": state.phase,
        "status": state.status,
        "market_open": state.market_open,
        "volatility_score": state.volatility_score,
        "volatility_state": state.volatility_state,
        "activity_score": state.activity_score,
        "liquidity_state": state.liquidity_state,
        "starts_at": state.starts_at.isoformat() if state.starts_at else None,
        "ends_at": state.ends_at.isoformat() if state.ends_at else None,
        "next_transition_at": state.next_transition_at.isoformat() if state.next_transition_at else None,
        "volatility_source": state.volatility_source,
        "timestamp": state.timestamp.isoformat(),
    }
