from app.models.portfolio import PositionSide, RiskRewardRequest, ScenarioResult
from app.services.portfolio import risk_reward, scenario


def test_long_risk_reward_is_auditable():
    result = risk_reward(RiskRewardRequest(entry_price=100, stop_loss=95, take_profit=110, side=PositionSide.LONG))
    assert result.risk_per_unit == 5
    assert result.reward_per_unit == 10
    assert result.reward_risk_ratio == 2
    assert result.valid is True


def test_short_risk_reward_rejects_bad_levels():
    result = risk_reward(RiskRewardRequest(entry_price=100, stop_loss=95, take_profit=80, side=PositionSide.SHORT))
    assert result.valid is False
    assert result.reward_risk_ratio == 0


def test_scenario_applies_directional_shock():
    class Position:
        def __init__(self, side, value, price=100):
            self.side = side
            self.market_value = value
            self.current_price = price

    class Snapshot:
        def __init__(self, side, value):
            self.position = Position(side, value)
            self.market_value = value
            self.current_price = 100

    class Summary:
        positions = (Snapshot(PositionSide.LONG, 1000), Snapshot(PositionSide.SHORT, 500))
        unrealized_pnl = 25
        gross_exposure = 1500

    result = scenario(Summary(), -10)
    assert isinstance(result, ScenarioResult)
    assert result.projected_pnl_delta == -50
    assert result.projected_unrealized_pnl == -25
    assert result.affected_positions == 2
