from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.models.signal_intelligence import SignalIntelligenceSnapshot
from app.services import signal_intelligence as service


def snapshot(
    *,
    signal_id: str = "s1",
    confidence: float = 0.9,
    outcome: str = "TARGET_HIT",
    version: str = "1.20.0",
    structure: str = "BOS",
    liquidity: str = "SWEEP",
    volatility: float = 0.02,
    momentum: float = 0.5,
    alignment: int = 3,
) -> SignalIntelligenceSnapshot:
    return SignalIntelligenceSnapshot(
        id=f"id-{signal_id}",
        signal_id=signal_id,
        revision=1,
        symbol="BTC/USDT",
        direction="BUY",
        confidence=confidence,
        entry_price=100,
        stop_loss=95,
        target_price=110,
        risk_reward=2.0,
        timeframe="15m",
        mtf_bias="BULLISH",
        mtf_alignment=alignment,
        regime="STRONG_TREND_UP",
        regime_confidence=0.9,
        market_structure=structure,
        liquidity_conditions=liquidity,
        momentum=momentum,
        volatility=volatility,
        session="US Activity Window",
        strategy="signal_engine",
        outcome=outcome,
        dispatched_at=datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc),
        target_timestamp=None,
        stop_timestamp=None,
        first_touch_timestamp=None,
        r_result=(
            2.0
            if outcome == "TARGET_HIT"
            else -1.0
            if outcome == "STOP_LOSS_HIT"
            else None
        ),
        outcome_latency_seconds=900,
        signal_engine_version=version,
        evidence=("BOS confirmed",),
        replay_candles=(),
        structural_conditions={"mtf_primary_setup": "trend"},
    )


def patch_rows(
    monkeypatch: pytest.MonkeyPatch,
    rows: list[SignalIntelligenceSnapshot],
) -> None:
    monkeypatch.setattr(service, "require_feature", lambda *args, **kwargs: {})
    monkeypatch.setattr(service, "consume_usage", lambda *args, **kwargs: {})
    monkeypatch.setattr(service, "_latest_rows", lambda *args, **kwargs: rows)


def test_explorer_applies_both_confidence_bounds(
    monkeypatch: pytest.MonkeyPatch,
):
    rows = [
        snapshot(signal_id="low", confidence=0.80),
        snapshot(signal_id="mid", confidence=0.87),
        snapshot(signal_id="high", confidence=0.96),
    ]
    patch_rows(monkeypatch, rows)

    result = service.explorer(
        "token",
        "user",
        {"min_confidence": "0.85", "max_confidence": "0.90"},
    )

    assert [item.signal_id for item in result.signals] == ["mid"]


def test_explorer_applies_date_and_structure_filters(
    monkeypatch: pytest.MonkeyPatch,
):
    rows = [
        snapshot(signal_id="bos", structure="BOS"),
        snapshot(signal_id="choch", structure="CHOCH"),
    ]
    rows[1] = rows[1].model_copy(
        update={"dispatched_at": datetime(2026, 9, 21, tzinfo=timezone.utc)}
    )
    patch_rows(monkeypatch, rows)

    result = service.explorer(
        "token",
        "user",
        {
            "structure": "bos",
            "from_date": "2026-09-20",
            "to_date": "2026-09-20",
        },
    )

    assert [item.signal_id for item in result.signals] == ["bos"]


def test_calibration_suppresses_small_samples(
    monkeypatch: pytest.MonkeyPatch,
):
    rows = [
        snapshot(signal_id=f"s{i}", confidence=0.82)
        for i in range(29)
    ]
    patch_rows(monkeypatch, rows)

    result = service.calibration("token", "user")

    bucket = next(
        item for item in result.buckets if item.label == "0.80–0.84"
    )
    assert bucket.sample_size == 29
    assert bucket.observed_outcome_rate is None
    assert not bucket.statistically_meaningful


def test_calibration_exposes_rate_at_threshold(
    monkeypatch: pytest.MonkeyPatch,
):
    rows = [
        snapshot(
            signal_id=f"win{i}",
            confidence=0.82,
            outcome="TARGET_HIT",
        )
        for i in range(30)
    ]
    rows.extend(
        snapshot(
            signal_id=f"loss{i}",
            confidence=0.82,
            outcome="STOP_LOSS_HIT",
        )
        for i in range(30)
    )
    patch_rows(monkeypatch, rows)

    result = service.calibration("token", "user")

    bucket = next(
        item for item in result.buckets if item.label == "0.80–0.84"
    )
    assert bucket.sample_size == 60
    assert bucket.observed_outcome_rate == pytest.approx(0.5)
    assert bucket.statistically_meaningful


def test_similarity_includes_setup_characteristics(
    monkeypatch: pytest.MonkeyPatch,
):
    target = snapshot(
        signal_id="target",
        structure="BOS",
        liquidity="SWEEP",
        momentum=0.5,
        alignment=3,
    )
    close = snapshot(
        signal_id="close",
        structure="BOS",
        liquidity="SWEEP",
        momentum=0.5,
        alignment=3,
    )
    far = snapshot(
        signal_id="far",
        structure="CHOCH",
        liquidity="NONE",
        momentum=-0.5,
        alignment=0,
    )
    patch_rows(monkeypatch, [target, close, far])

    result = service.similarity("token", "user", "target")

    assert [item.signal_id for item in result.signals] == ["close", "far"]


def test_engine_version_analytics_does_not_rank_versions(
    monkeypatch: pytest.MonkeyPatch,
):
    rows = [
        snapshot(
            signal_id="a",
            version="1.19.0",
            outcome="TARGET_HIT",
        ),
        snapshot(
            signal_id="b",
            version="1.19.0",
            outcome="STOP_LOSS_HIT",
        ),
        snapshot(
            signal_id="c",
            version="1.20.0",
            outcome="TARGET_HIT",
        ),
    ]
    patch_rows(monkeypatch, rows)

    result = service.engine_version_analytics("token", "user")

    assert [item["engine_version"] for item in result["versions"]] == [
        "1.19.0",
        "1.20.0",
    ]
    assert result["versions"][0]["sample_size"] == 2
    assert result["versions"][1]["sample_size"] == 1
    assert all(
        "statistically_meaningful" in item for item in result["versions"]
    )


def test_latest_rows_paginates_beyond_first_thousand(
    monkeypatch: pytest.MonkeyPatch,
):
    first = [
        snapshot(signal_id=f"s{i}").model_dump()
        for i in range(1000)
    ]
    second = [snapshot(signal_id="s1000").model_dump()]
    calls = []

    class Response:
        def __init__(self, rows):
            self._rows = rows

        def json(self):
            return self._rows

    def fake_request(
        method,
        resource,
        token,
        params=None,
        **kwargs,
    ):
        calls.append(params["offset"])
        return Response(
            first if params["offset"] == "0" else second
        )

    monkeypatch.setattr(service, "_request", fake_request)
    rows = service._latest_rows("token", "user", {})

    assert len(rows) == 1001
    assert calls == ["0", "1000"]
