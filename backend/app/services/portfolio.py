from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.models.portfolio import PortfolioPosition, PortfolioPositionCreate, PortfolioPositionSnapshot, PortfolioPositionUpdate, PortfolioSummary, PositionSide, RiskRewardRequest, RiskRewardResult, ScenarioResult
from app.services.quote_service import QuoteService
from app.services.supabase_data import _request

quote_service = QuoteService()


def _rows(access_token: str, user_id: str) -> list[dict[str, Any]]:
    response = _request("GET", "portfolio_positions", access_token, params={"select": "id,user_id,symbol,side,quantity,average_entry_price,notes,created_at,updated_at", "user_id": f"eq.{user_id}", "order": "created_at.asc"})
    return response.json()


def list_positions(access_token: str, user_id: str) -> list[PortfolioPosition]:
    return [PortfolioPosition.model_validate(row) for row in _rows(access_token, user_id)]


def create_position(access_token: str, user_id: str, payload: PortfolioPositionCreate) -> PortfolioPosition:
    response = _request("POST", "portfolio_positions", access_token, json={**payload.model_dump(mode="json"), "user_id": user_id}, prefer="return=representation")
    return PortfolioPosition.model_validate(response.json()[0])


def update_position(access_token: str, user_id: str, position_id: str, payload: PortfolioPositionUpdate) -> PortfolioPosition:
    changes = payload.model_dump(exclude_unset=True, mode="json")
    if not changes:
        raise ValueError("At least one position field must be supplied for update.")
    response = _request("PATCH", "portfolio_positions", access_token, params={"id": f"eq.{position_id}", "user_id": f"eq.{user_id}"}, json=changes, prefer="return=representation")
    rows = response.json()
    if not rows:
        raise KeyError(position_id)
    return PortfolioPosition.model_validate(rows[0])


def delete_position(access_token: str, user_id: str, position_id: str) -> None:
    _request("DELETE", "portfolio_positions", access_token, params={"id": f"eq.{position_id}", "user_id": f"eq.{user_id}"})


async def summarize(access_token: str, user_id: str) -> PortfolioSummary:
    positions = list_positions(access_token, user_id)
    symbols = sorted({p.symbol for p in positions})
    quotes = {q.symbol: q for q in (await quote_service.get_quotes(symbols, force_refresh=False))} if symbols else {}
    snapshots: list[PortfolioPositionSnapshot] = []
    invested = gross = net = pnl = 0.0
    for position in positions:
        quote = quotes.get(position.symbol)
        current = quote.price if quote else None
        value = position.quantity * (current if current is not None else position.average_entry_price)
        signed_value = value if position.side == PositionSide.LONG else -value
        invested += position.quantity * position.average_entry_price
        gross += abs(value)
        net += signed_value
        position_pnl = None if current is None else ((current - position.average_entry_price) * position.quantity if position.side == PositionSide.LONG else (position.average_entry_price - current) * position.quantity)
        if position_pnl is not None:
            pnl += position_pnl
        snapshots.append(PortfolioPositionSnapshot(position=position, current_price=current, market_value=value, unrealized_pnl=position_pnl, pnl_percent=(position_pnl / (position.quantity * position.average_entry_price) * 100) if position_pnl is not None else None, quote_status=quote.status if quote else "UNAVAILABLE", quote_timestamp=quote.timestamp if quote else None))
    concentration = max(((s.market_value / gross) * 100 for s in snapshots), default=0.0) if gross else 0.0
    pnl_pct = (pnl / invested * 100) if invested else None
    flags: list[str] = []
    if concentration > 40: flags.append("HIGH_CONCENTRATION")
    if concentration > 60: flags.append("CRITICAL_CONCENTRATION")
    if any(s.quote_status not in {"LIVE", "DELAYED"} for s in snapshots): flags.append("STALE_OR_UNAVAILABLE_MARKET_DATA")
    return PortfolioSummary(calculated_at=datetime.now(timezone.utc), position_count=len(positions), invested_value=invested, gross_exposure=gross, net_exposure=net, unrealized_pnl=pnl, unrealized_pnl_percent=pnl_pct, max_position_concentration_percent=concentration, portfolio_drawdown_percent=max(0.0, -pnl_pct) if pnl_pct is not None else 0.0, risk_flags=tuple(flags), positions=tuple(snapshots))


def scenario(summary: PortfolioSummary, change_percent: float) -> ScenarioResult:
    delta = 0.0
    affected = 0
    for snapshot in summary.positions:
        if snapshot.current_price is None: continue
        affected += 1
        signed = 1 if snapshot.position.side == PositionSide.LONG else -1
        delta += snapshot.market_value * (change_percent / 100) * signed
    return ScenarioResult(price_change_percent=change_percent, projected_unrealized_pnl=summary.unrealized_pnl + delta, projected_pnl_delta=delta, projected_gross_exposure=summary.gross_exposure * (1 + change_percent / 100), affected_positions=affected)


def risk_reward(payload: RiskRewardRequest) -> RiskRewardResult:
    if payload.side == PositionSide.LONG:
        risk, reward = payload.entry_price - payload.stop_loss, payload.take_profit - payload.entry_price
    else:
        risk, reward = payload.stop_loss - payload.entry_price, payload.entry_price - payload.take_profit
    if risk <= 0 or reward <= 0:
        return RiskRewardResult(risk_per_unit=max(0.0, risk), reward_per_unit=max(0.0, reward), reward_risk_ratio=0.0, valid=False, reason="Stop-loss and take-profit must be on the correct side of the entry price.")
    ratio = reward / risk
    return RiskRewardResult(risk_per_unit=risk, reward_per_unit=reward, reward_risk_ratio=ratio, valid=ratio >= 2.0, reason="Meets the 2.0 minimum reward/risk threshold." if ratio >= 2.0 else "Below the 2.0 minimum reward/risk threshold.")
