from __future__ import annotations

from typing import Literal

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.signal import CryptoSignal


class EnhancedSignalEvidence(BaseModel):
    model_config = ConfigDict(frozen=True)

    key: str
    label: str
    category: Literal["hard_gate", "quality_factor"]
    passed: bool
    value: str
    detail: str


class EnhancedSignalEvidence(BaseModel):
    model_config = ConfigDict(frozen=True)

    key: str
    label: str
    category: Literal["hard_gate", "quality_factor"]
    passed: bool
    value: str
    detail: str


class EnhancedSignalChecks(BaseModel):
    model_config = ConfigDict(frozen=True)

    htf_bias: str
    htf_aligned: bool
    setup_structure_aligned: bool
    valid_poi: bool
    premium_discount_valid: bool
    liquidity_sweep_confirmed: bool
    displacement_confirmed: bool
    micro_structure_confirmed: bool
    entry_location_valid: bool
    structural_stop_valid: bool
    opposing_liquidity_target: bool
    path_to_target_clear: bool
    minimum_rr_met: bool
    session_valid: bool
    volatility_valid: bool
    news_filter_passed: bool
    hard_gate_passed: bool
    quality_score: float = Field(ge=0, le=1)
    decision_status: Literal["NO_TRADE", "WAIT", "QUALIFIED"]
    hard_gate_passed: bool
    hard_gate_failures: tuple[str, ...] = ()
    quality_factor_failures: tuple[str, ...] = ()
    decision_status: Literal["NO_TRADE", "WAIT", "QUALIFIED"]
    hard_gate_passed: bool
    hard_gate_failures: tuple[str, ...] = ()
    quality_factor_failures: tuple[str, ...] = ()
    failed_gates: tuple[str, ...] = ()
    next_confirmation: str
    evidence: tuple[EnhancedSignalEvidence, ...] = ()
    calibration_sample_size: int = 0
    calibration_minimum_sample_size: int = 20
    calibrated_probability_available: bool = False
    calibrated_probability: float | None = Field(default=None, ge=0, le=1)
    expected_value_r: float | None = None
    calibration_note: str = "Calibration is unavailable until at least 20 resolved, chronologically aligned outcomes are available."
    next_confirmation: str
    evidence: tuple[EnhancedSignalEvidence, ...] = ()
    calibration_sample_size: int = 0
    calibration_minimum_sample_size: int = 20
    calibrated_probability_available: bool = False
    calibrated_probability: float | None = Field(default=None, ge=0, le=1)
    expected_value_r: float | None = None
    calibration_note: str = "Calibration is unavailable until at least 20 resolved, chronologically aligned outcomes are available."


class EnhancedSignalResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    signal: CryptoSignal
    checks: EnhancedSignalChecks
    strategy: str = "enhanced_smc"
    methodology_version: str
    risk_policy: dict[str, object]
    research_note: str
