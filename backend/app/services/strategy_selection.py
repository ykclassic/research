from __future__ import annotations

from datetime import datetime, timezone

from app.models.mtf import MTFBias, MTFState, MultiTimeframeResult
from app.models.strategy import SignalDirection, StrategyPortfolioResult, StrategySignal, StrategyStatus
from app.models.strategy_selection import QualificationStatus, StrategyQualification, StrategySelectionResult

GATE_VERSION = "1.0.0"
MIN_ALIGNMENT = 3


def _bias_for(direction: SignalDirection) -> MTFBias:
    if direction is SignalDirection.LONG:
        return MTFBias.BULLISH
    if direction is SignalDirection.SHORT:
        return MTFBias.BEARISH
    return MTFBias.NEUTRAL


def _qualify(signal: StrategySignal, mtf: MultiTimeframeResult) -> StrategyQualification:
    target = _bias_for(signal.direction)
    alignment = mtf.research.alignment_count
    reasons: list[str] = []

    if signal.status is StrategyStatus.INSUFFICIENT_DATA:
        return StrategyQualification(strategy_id=signal.strategy_id, strategy_version=signal.strategy_version, direction=signal.direction, status=QualificationStatus.INSUFFICIENT_DATA, score=0.0, mtf_bias=mtf.research.bias, mtf_alignment_count=alignment, mtf_gate_passed=False, reasons=("Strategy does not have sufficient completed-candle data.",))
    if signal.status is StrategyStatus.ERROR:
        return StrategyQualification(strategy_id=signal.strategy_id, strategy_version=signal.strategy_version, direction=signal.direction, status=QualificationStatus.ERROR, score=0.0, mtf_bias=mtf.research.bias, mtf_alignment_count=alignment, mtf_gate_passed=False, reasons=("Strategy evaluation returned an error state.",))
    if signal.direction is SignalDirection.NEUTRAL:
        return StrategyQualification(strategy_id=signal.strategy_id, strategy_version=signal.strategy_version, direction=signal.direction, status=QualificationStatus.REJECTED, score=0.0, mtf_bias=mtf.research.bias, mtf_alignment_count=alignment, mtf_gate_passed=False, reasons=("No directional strategy signal is present.",))
    if not signal.regime_compatible:
        reasons.append("Strategy regime compatibility gate failed.")
    if mtf.research.bias is not target:
        reasons.append(f"Strategy direction conflicts with MTF bias ({mtf.research.bias.value}).")
    if alignment < MIN_ALIGNMENT:
        reasons.append(f"MTF alignment {alignment}/4 is below the {MIN_ALIGNMENT}/4 minimum gate.")

    m15 = next(item for item in mtf.timeframes if item.timeframe.value == "15m")
    h1 = next(item for item in mtf.timeframes if item.timeframe.value == "1h")
    confirmation = (target is MTFBias.BULLISH and m15.state is MTFState.M15_BULLISH_BOS) or (target is MTFBias.BEARISH and m15.state is MTFState.M15_BEARISH_BOS)
    if alignment == 4 and not confirmation:
        reasons.append("Full 4/4 alignment still requires a directional M15 BOS for final qualification.")
    if h1.bias is not target:
        reasons.append("H1 does not agree with the strategy direction.")

    gate_passed = not reasons
    if gate_passed:
        score = signal.confidence * (0.50 + 0.50 * alignment / 4.0)
        if confirmation:
            score += 0.05
        score = min(1.0, score)
        reasons.append(f"MTF gate passed: {alignment}/4 alignment, H1 agreement, and directional M15 confirmation.")
        return StrategyQualification(strategy_id=signal.strategy_id, strategy_version=signal.strategy_version, direction=signal.direction, status=QualificationStatus.QUALIFIED, score=score, mtf_bias=mtf.research.bias, mtf_alignment_count=alignment, mtf_gate_passed=True, reasons=tuple(reasons))
    return StrategyQualification(strategy_id=signal.strategy_id, strategy_version=signal.strategy_version, direction=signal.direction, status=QualificationStatus.REJECTED, score=0.0, mtf_bias=mtf.research.bias, mtf_alignment_count=alignment, mtf_gate_passed=False, reasons=tuple(reasons))


def select_strategy(portfolio: StrategyPortfolioResult, mtf: MultiTimeframeResult) -> StrategySelectionResult:
    if portfolio.symbol != mtf.symbol:
        raise ValueError("Strategy portfolio and MTF result symbols must match.")
    qualifications = tuple(_qualify(signal, mtf) for signal in portfolio.strategies)
    qualified = [item for item in qualifications if item.status is QualificationStatus.QUALIFIED]
    selected = max(qualified, key=lambda item: (item.score, item.strategy_id), default=None)
    if selected is None:
        decision = "NO_QUALIFIED_STRATEGY"
        return StrategySelectionResult(symbol=portfolio.symbol, generated_at=datetime.now(timezone.utc), mtf=mtf, qualifications=qualifications, decision=decision, gate_version=GATE_VERSION)
    return StrategySelectionResult(symbol=portfolio.symbol, generated_at=datetime.now(timezone.utc), mtf=mtf, qualifications=qualifications, selected_strategy_id=selected.strategy_id, selected_direction=selected.direction, selected_score=selected.score, decision="STRATEGY_SELECTED", gate_version=GATE_VERSION)
