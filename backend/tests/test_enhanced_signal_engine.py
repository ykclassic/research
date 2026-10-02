from types import SimpleNamespace

import pytest

from app.services.enhanced_signal_engine import (
    MINIMUM_RR,
    _direction_from_structure,
    _path_clear,
)


def event(kind: str, price: float, status: str = "CONFIRMED"):
    return SimpleNamespace(
        type=kind,
        price=price,
        status=SimpleNamespace(value=status),
    )


def test_direction_uses_latest_structure_break():
    events = [
        event("BOS_BULLISH", 100.0),
        event("CHOCH_BEARISH", 99.0),
    ]
    events[0] = SimpleNamespace(**events[0].__dict__, time=1)
    events[1] = SimpleNamespace(**events[1].__dict__, time=2)

    assert _direction_from_structure(events) == "BEARISH"


def test_path_is_rejected_when_opposing_zone_blocks_target():
    events = [event("ORDER_BLOCK_BEARISH", 110.0, "ACTIVE")]
    assert not _path_clear(events, "BULLISH", 100.0, 120.0)


def test_path_is_clear_without_opposing_zone():
    events = [event("LIQUIDITY_POOL_HIGH", 130.0, "BROKEN")]
    assert _path_clear(events, "BULLISH", 100.0, 120.0)


def test_minimum_rr_is_two():
    assert MINIMUM_RR == 2.0


def test_direction_returns_none_without_structure_evidence():
    assert _direction_from_structure([event("FVG_BULLISH", 100.0)]) is None
