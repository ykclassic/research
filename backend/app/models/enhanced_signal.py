from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


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
    failed_gates: tuple[str, ...] = ()


class EnhancedSignalResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    signal: object
    checks: EnhancedSignalChecks
    strategy: str = "enhanced_smc"
    methodology_version: str
    risk_policy: dict[str, object]
    research_note: str
