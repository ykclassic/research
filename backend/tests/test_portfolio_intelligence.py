from types import SimpleNamespace

from app.models.portfolio import PortfolioSummary, PortfolioPositionSnapshot, PortfolioPosition, PositionSide
from app.models.portfolio_intelligence import ScenarioRequestV2
from app.services.portfolio_intelligence import scenario


def _summary():
    position = PortfolioPosition(
        id="p1", user_id="u1", symbol="BTC/USD", side=PositionSide.LONG, quantity=1,
        average_entry_price=100, asset_class="CRYPTO", sector="CRYPTO", category="DIGITAL_ASSET",
        notes=None, created_at="2026-09-25T00:00:00Z", updated_at="2026-09-25T00:00:00Z"
    )
    snap = PortfolioPositionSnapshot(position=position,current_price=100,market_value=100,unrealized_pnl=0,pnl_percent=0,quote_status="LIVE",quote_timestamp=None)
    return PortfolioSummary(calculated_at="2026-09-25T00:00:00Z",position_count=1,invested_value=100,gross_exposure=100,net_exposure=100,unrealized_pnl=0,unrealized_pnl_percent=0,max_position_concentration_percent=100,portfolio_drawdown_percent=0,risk_flags=(),positions=(snap,))


def test_asset_shock_is_deterministic():
    result=scenario(_summary(),ScenarioRequestV2(scenario_type="ASSET_SHOCK",symbol="BTC/USD",shock_percent=-15))
    assert result.projected_pnl_delta == -15
    assert result.projected_gross_exposure == 85
    assert result.affected_positions == 1


def test_usd_strength_scenario_maps_major_fx_pairs():
    position = _summary().positions[0].model_copy(update={"position": _summary().positions[0].position.model_copy(update={"symbol":"EUR/USD"})})
    summary=_summary().model_copy(update={"positions":(position,)})
    result=scenario(summary,ScenarioRequestV2(scenario_type="USD_STRENGTHENS"))
    assert result.impacts[0].shock_percent == -5
    assert result.projected_pnl_delta == -5


def test_high_volatility_applies_directional_shock():
    result=scenario(_summary(),ScenarioRequestV2(scenario_type="HIGH_VOLATILITY"))
    assert result.impacts[0].shock_percent == -8
    assert result.projected_pnl_delta == -8
