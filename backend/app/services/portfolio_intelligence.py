from __future__ import annotations

import asyncio
import math
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from app.models.portfolio import PositionSide, PortfolioSummary
from app.models.portfolio_intelligence import (
    CorrelationCluster,
    CorrelationEntry,
    PortfolioExposure,
    PortfolioIntelligence,
    PortfolioScenarioV2,
    RegimeAlignment,
    RiskContribution,
    ScenarioImpact,
    SignalExposure,
)
from app.services.news_research_resilient import news_research
from app.services.portfolio import list_positions
from app.services.quote_service import QuoteService
from app.services.supabase_data import DataServiceError, _request

quote_service = QuoteService()
RETURN_CANDLES = 90
CORRELATION_THRESHOLD = 0.70
CONCENTRATION_ALERT = 35.0
EXPOSURE_CHANGE_ALERT = 15.0


def _classification(position: Any) -> tuple[str, str, str]:
    symbol = position.symbol.upper()
    asset_class = getattr(position, "asset_class", None) or (
        "CRYPTO" if "/" in symbol and symbol.split("/")[0] in {"BTC","ETH","SOL","XRP","ADA","DOGE"} else
        "FOREX" if "/" in symbol else
        "ETF" if symbol in {"SPY","QQQ","IWM","GLD","TLT"} else
        "STOCK"
    )
    sector = getattr(position, "sector", None) or (
        "CRYPTO" if asset_class == "CRYPTO" else
        "FX" if asset_class == "FOREX" else
        "TECHNOLOGY" if symbol in {"NVDA","AAPL","MSFT","AMD","GOOGL","META","AMZN"} else
        "DIVERSIFIED" if asset_class == "ETF" else "OTHER"
    )
    category = getattr(position, "category", None) or (
        "DIGITAL_ASSET" if asset_class == "CRYPTO" else
        "CURRENCY_PAIR" if asset_class == "FOREX" else
        "EQUITY" if asset_class == "STOCK" else
        "FUND" if asset_class == "ETF" else "OTHER"
    )
    return asset_class, sector, category


async def _series(symbol: str) -> list[float]:
    try:
        mapping = __import__("app.symbols", fromlist=["normalize_symbol"]).normalize_symbol(symbol)
        dataset = await asyncio.wait_for(quote_service.orchestrator.get_candles(mapping.internal, "1d", RETURN_CANDLES), timeout=20)
        closes = [float(c.close) for c in dataset.completed_candles if c.close > 0]
        return closes[-RETURN_CANDLES:]
    except Exception:
        return []


def _returns(closes: list[float]) -> list[float]:
    return [(b / a) - 1.0 for a, b in zip(closes, closes[1:]) if a > 0 and b > 0]


def _corr(left: list[float], right: list[float]) -> float | None:
    n = min(len(left), len(right))
    if n < 20:
        return None
    x, y = left[-n:], right[-n:]
    mx, my = sum(x)/n, sum(y)/n
    vx = sum((v-mx)**2 for v in x)
    vy = sum((v-my)**2 for v in y)
    if vx <= 1e-18 or vy <= 1e-18:
        return None
    return max(-1.0, min(1.0, sum((a-mx)*(b-my) for a,b in zip(x,y)) / math.sqrt(vx*vy)))


def _clusters(symbols: list[str], matrix: dict[str, dict[str, float]]) -> tuple[CorrelationCluster, ...]:
    seen: set[str] = set()
    groups: list[tuple[str, ...]] = []
    for symbol in symbols:
        if symbol in seen:
            continue
        stack=[symbol]; group=[]
        while stack:
            current=stack.pop()
            if current in seen: continue
            seen.add(current); group.append(current)
            for other in symbols:
                if other not in seen and matrix.get(current, {}).get(other, 0.0) >= CORRELATION_THRESHOLD:
                    stack.append(other)
        groups.append(tuple(sorted(group)))
    result=[]
    for idx, group in enumerate(groups, 1):
        pairs=[matrix[a][b] for i,a in enumerate(group) for b in group[i+1:] if b in matrix.get(a,{})]
        result.append(CorrelationCluster(cluster_id=f"C{idx}", symbols=group, average_pairwise_correlation=(sum(pairs)/len(pairs) if pairs else None)))
    return tuple(result)


def _direction(signals: list[Any]) -> str:
    buys=sum(str(s.direction).upper() in {"BUY","STRONG_BUY","LONG"} for s in signals)
    sells=sum(str(s.direction).upper() in {"SELL","STRONG_SELL","SHORT"} for s in signals)
    if buys and sells: return "MIXED"
    if buys: return "LONG"
    if sells: return "SHORT"
    return "NEUTRAL"


async def build_intelligence(access_token: str, user_id: str, summary: PortfolioSummary) -> PortfolioIntelligence:
    exposures=[]
    allocation=defaultdict(float); sectors=defaultdict(float); categories=defaultdict(float)
    gross=max(summary.gross_exposure, 0.0)
    for snapshot in summary.positions:
        ac, sector, category=_classification(snapshot.position)
        weight=(abs(snapshot.market_value)/gross*100) if gross else 0.0
        signed=(snapshot.market_value if snapshot.position.side == PositionSide.LONG else -snapshot.market_value)
        net_weight=(signed/gross*100) if gross else 0.0
        exposures.append(PortfolioExposure(symbol=snapshot.position.symbol, market_value=snapshot.market_value, weight_percent=weight, net_weight_percent=net_weight, side=snapshot.position.side.value, asset_class=ac, sector=sector, category=category))
        allocation[ac]+=weight; sectors[sector]+=weight; categories[category]+=weight

    symbols=[e.symbol for e in exposures]
    series=dict(zip(symbols, await asyncio.gather(*[_series(s) for s in symbols])))
    returns={s:_returns(v) for s,v in series.items()}
    matrix: dict[str,dict[str,float]]={s:{} for s in symbols}
    for i,left in enumerate(symbols):
        for right in symbols[i+1:]:
            c=_corr(returns.get(left,[]),returns.get(right,[]))
            if c is not None:
                matrix[left][right]=matrix[right][left]=c
    corr_out={s:tuple(CorrelationEntry(symbol=o, correlation=matrix[s][o]) for o in sorted(matrix.get(s,{}))) for s in symbols}
    clusters=_clusters(symbols,matrix)

    risks=[]
    raw=[]
    for e in exposures:
        r=returns.get(e.symbol,[])
        vol=(math.sqrt(sum((x-(sum(r)/len(r)))**2 for x in r)/(len(r)-1))*math.sqrt(252)*100) if len(r)>=20 else None
        raw.append((e,vol, (e.weight_percent*(vol or 0.0))))
    total_risk=sum(v for _,_,v in raw)
    for e,vol,contrib in raw:
        risks.append(RiskContribution(symbol=e.symbol, exposure_percent=e.weight_percent, volatility_percent=vol, risk_contribution_percent=(contrib/total_risk*100 if total_risk else None)))

    regimes=[]
    for e in exposures:
        try:
            from app.services.regime_detection import detect_regime
            mapping=__import__("app.symbols", fromlist=["normalize_symbol"]).normalize_symbol(e.symbol)
            dataset=await asyncio.wait_for(quote_service.orchestrator.get_candles(mapping.internal,"1h",120),timeout=20)
            regime=detect_regime(dataset).regime
            confidence=float(detect_regime(dataset).confidence)
            regimes.append(RegimeAlignment(symbol=e.symbol,timeframe="1h",regime=regime.value,confidence=confidence,alignment="OBSERVED"))
        except Exception:
            regimes.append(RegimeAlignment(symbol=e.symbol,timeframe="1h",regime="UNKNOWN",confidence=0.0,alignment="UNAVAILABLE"))

    signal_items=[]
    try:
        from app.services.signal_intelligence import explorer
        for e in exposures:
            try:
                result=explorer(access_token,user_id,{"symbol":e.symbol})
                active=[s for s in result.signals if s.outcome == "PENDING"]
                signal_items.append(SignalExposure(symbol=e.symbol,active_signals=len(active),net_direction=_direction(active),average_confidence=(sum(s.confidence for s in active)/len(active) if active else None),regimes=tuple(sorted({s.regime for s in active if s.regime}))))
            except Exception:
                signal_items.append(SignalExposure(symbol=e.symbol,active_signals=0,net_direction="UNAVAILABLE",average_confidence=None,regimes=()))
    except Exception:
        signal_items=[SignalExposure(symbol=e.symbol,active_signals=0,net_direction="UNAVAILABLE",average_confidence=None,regimes=()) for e in exposures]

    changes=[]
    drivers=[]
    alerts=[]
    quality=[]
    if exposures:
        top=max(exposures,key=lambda x:x.weight_percent)
        if top.weight_percent >= CONCENTRATION_ALERT:
            alerts.append(f"Concentration threshold breached: {top.symbol} is {top.weight_percent:.1f}% of gross exposure.")
            drivers.append(f"{top.symbol} is the largest exposure at {top.weight_percent:.1f}%.")
    for cluster in clusters:
        if len(cluster.symbols)>1 and (cluster.average_pairwise_correlation or 0) >= 0.80:
            alerts.append(f"Correlation cluster {cluster.cluster_id} is tightly coupled ({cluster.average_pairwise_correlation:.2f} average correlation).")
            drivers.append(f"Correlation cluster {cluster.cluster_id} contains {', '.join(cluster.symbols)}.")
    for e in exposures:
        if e.weight_percent >= EXPOSURE_CHANGE_ALERT:
            changes.append(f"{e.symbol} represents {e.weight_percent:.1f}% of gross exposure.")
    for r in risks:
        if r.risk_contribution_percent is not None and r.risk_contribution_percent >= 30:
            drivers.append(f"{r.symbol} contributes {r.risk_contribution_percent:.1f}% of volatility-weighted risk.")
    if any(r.regime == "HIGH_VOLATILITY" for r in regimes):
        alerts.append("Portfolio regime shift: at least one holding is currently in a high-volatility regime.")
        changes.append("High-volatility regime detected in the portfolio.")
    if not symbols:
        quality.append("No positions are available for portfolio intelligence.")
    if any(not returns.get(s) or len(returns.get(s,[]))<20 for s in symbols):
        quality.append("Correlation and volatility are partial where fewer than 20 daily returns are available.")

    relevant_signals=tuple(f"{s.symbol}: {s.active_signals} active {s.net_direction.lower()} signal(s)" for s in signal_items if s.active_signals)
    catalysts=[]
    for symbol in symbols:
        try:
            news=await news_research.research(symbol=symbol,days=2,limit=5)
            for item in news.news[:2]:
                catalysts.append(f"{symbol}: {item.headline} ({item.sentiment.value.lower()})")
            for event in news.fundamental_events[:2]:
                catalysts.append(f"{symbol}: {event.title}")
        except Exception:
            quality.append(f"Catalyst coverage unavailable for {symbol}.")
    return PortfolioIntelligence(
        calculated_at=datetime.now(timezone.utc).isoformat(),
        exposures=tuple(exposures), asset_allocation=dict(allocation), sector_exposure=dict(sectors), category_exposure=dict(categories),
        correlation_matrix=corr_out, correlation_clusters=clusters, risk_contribution=tuple(risks),
        regime_alignment=tuple(regimes), signal_exposure=tuple(signal_items), changes=tuple(dict.fromkeys(changes)),
        risk_drivers=tuple(dict.fromkeys(drivers)), alerts=tuple(dict.fromkeys(alerts)), relevant_signals=relevant_signals,
        relevant_catalysts=tuple(catalysts[:12]), data_quality=tuple(dict.fromkeys(quality)),
    )


def scenario(summary: PortfolioSummary, payload) -> PortfolioScenarioV2:
    impacts=[]; total_delta=0.0; gross=summary.gross_exposure
    assumptions=[]
    scenario_type=str(payload.scenario_type).upper()
    if scenario_type == "ASSET_SHOCK":
        if not payload.symbol:
            raise ValueError("symbol is required for ASSET_SHOCK.")
        target=payload.symbol.upper()
        assumptions.append(f"{target} moves {payload.shock_percent:+.2f}%.")
        for snapshot in summary.positions:
            if snapshot.position.symbol.upper()!=target or snapshot.current_price is None: continue
            signed=1 if snapshot.position.side==PositionSide.LONG else -1
            delta=snapshot.market_value*(payload.shock_percent/100)*signed
            impacts.append(ScenarioImpact(symbol=snapshot.position.symbol,shock_percent=payload.shock_percent,pnl_delta=delta,exposure_delta=snapshot.market_value*payload.shock_percent/100))
            total_delta+=delta
        name=f"{target} {payload.shock_percent:+.1f}%"
    elif scenario_type == "USD_STRENGTHENS":
        assumptions.append("USD strengthens 5% versus non-USD currencies.")
        for snapshot in summary.positions:
            symbol=snapshot.position.symbol.upper()
            shock=-5.0 if symbol.endswith("/USD") else (5.0 if symbol.startswith("USD/") else 0.0)
            if shock==0 or snapshot.current_price is None: continue
            signed=1 if snapshot.position.side==PositionSide.LONG else -1
            delta=snapshot.market_value*(shock/100)*signed
            impacts.append(ScenarioImpact(symbol=snapshot.position.symbol,shock_percent=shock,pnl_delta=delta,exposure_delta=snapshot.market_value*shock/100)); total_delta+=delta
        name="USD strengthens 5%"
    elif scenario_type == "HIGH_VOLATILITY":
        assumptions.append("High-volatility regime: adverse 8% shock to each position, with long/short direction respected.")
        for snapshot in summary.positions:
            if snapshot.current_price is None: continue
            shock=-8.0
            signed=1 if snapshot.position.side==PositionSide.LONG else -1
            delta=snapshot.market_value*(shock/100)*signed
            impacts.append(ScenarioImpact(symbol=snapshot.position.symbol,shock_percent=shock,pnl_delta=delta,exposure_delta=snapshot.market_value*shock/100)); total_delta+=delta
        name="High-volatility regime"
    else:
        raise ValueError("Unsupported scenario_type.")
    return PortfolioScenarioV2(name=name,assumptions=tuple(assumptions),projected_pnl_delta=total_delta,projected_unrealized_pnl=summary.unrealized_pnl+total_delta,projected_gross_exposure=gross+sum(i.exposure_delta for i in impacts),impacts=tuple(impacts),affected_positions=len(impacts),data_quality=("Scenario applies defined deterministic shocks; it is not a forecast.","Positions without validated current prices are excluded."))
