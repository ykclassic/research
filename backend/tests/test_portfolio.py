from app.models.portfolio import PortfolioPositionUpdate, PositionSide, RiskRewardRequest, ScenarioResult
from app.services import portfolio
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


def test_update_position_is_partial_and_scoped_to_authenticated_owner(monkeypatch):
    calls = []

    class Response:
        def json(self):
            return [{
                "id": "position-1",
                "user_id": "user-1",
                "symbol": "BTC/USD",
                "side": "LONG",
                "quantity": 0.002,
                "average_entry_price": 100000,
                "notes": "updated",
                "created_at": "2026-09-06T00:00:00Z",
                "updated_at": "2026-09-06T00:01:00Z",
            }]

    def fake_request(method, resource, access_token, **kwargs):
        calls.append((method, resource, access_token, kwargs))
        return Response()

    monkeypatch.setattr(portfolio, "_request", fake_request)
    result = portfolio.update_position(
        "session-token",
        "user-1",
        "position-1",
        PortfolioPositionUpdate(quantity=0.002, notes="updated"),
    )

    assert result.quantity == 0.002
    assert result.notes == "updated"
    assert calls == [(
        "PATCH",
        "portfolio_positions",
        "session-token",
        {
            "params": {"id": "eq.position-1", "user_id": "eq.user-1"},
            "json": {"quantity": 0.002, "notes": "updated"},
            "prefer": "return=representation",
        },
    )]


def test_update_position_rejects_empty_patch(monkeypatch):
    called = False

    def fake_request(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("empty update must not reach persistence")

    monkeypatch.setattr(portfolio, "_request", fake_request)
    try:
        portfolio.update_position("session-token", "user-1", "position-1", PortfolioPositionUpdate())
    except ValueError as exc:
        assert "At least one position field" in str(exc)
    else:
        raise AssertionError("expected empty update to be rejected")
    assert called is False


def test_update_position_returns_not_found_when_owner_scoped_update_matches_nothing(monkeypatch):
    class Response:
        def json(self):
            return []

    monkeypatch.setattr(portfolio, "_request", lambda *args, **kwargs: Response())
    try:
        portfolio.update_position("session-token", "user-1", "position-owned-by-someone-else", PortfolioPositionUpdate(notes="nope"))
    except KeyError as exc:
        assert str(exc.value) == "position-owned-by-someone-else"
    else:
        raise AssertionError("expected owner-scoped update to return not found")
