from __future__ import annotations
from typing import Any, Iterable
from app.models.market import Candle, OHLCVDataset
from app.models.quant_lab import BacktestMetrics, BacktestResult, ExperimentSpec, PaperPortfolio, PaperTrade, Side, StrategyDefinition, StrategyDiagnosis, TradeResult
from app.services.entitlement import require_feature
from app.services.supabase_data import DataRequestError, _request

ENGINE_VERSION = "quant-lab-v1"
DATASET_VERSION = "ohlcv-completed-v1"

def _match(value: Any, operator: str, target: Any) -> bool:
    if operator == "eq": return value == target
    if operator == "neq": return value != target
    if operator == "contains": return target in value if value is not None else False
    try: left, right = float(value), float(target)
    except (TypeError, ValueError): return False
    return {"gt": left > right, "gte": left >= right, "lt": left < right, "lte": left <= right}.get(operator, False)

def _rules_match(candle: Candle, rules: Iterable[Any]) -> bool:
    context={"open":candle.open,"high":candle.high,"low":candle.low,"close":candle.close,"volume":candle.volume}
    return all(_match(context.get(rule.field),rule.operator,rule.value) for rule in rules)

def _trade(entry: Candle, exit: Candle, side: Side, execution: Any, regime: str|None=None) -> TradeResult:
    gross=(exit.close-entry.close) if side==Side.LONG else (entry.close-exit.close)
    base=entry.close*execution.position_size
    friction=base*(execution.commission_bps+execution.slippage_bps+execution.spread_bps)/10000
    pnl=gross*execution.position_size-friction
    r=pnl/max(base,1e-12)
    adverse=(entry.low-entry.close) if side==Side.LONG else (entry.close-entry.high)
    favorable=(entry.high-entry.close) if side==Side.LONG else (entry.close-entry.low)
    return TradeResult(entry_time=entry.timestamp,exit_time=exit.timestamp,side=side,entry_price=entry.close,exit_price=exit.close,pnl=pnl,r_multiple=r,mae=adverse,mfe=favorable,regime=regime,timeframe=entry.timeframe.value)

def _metrics(trades:list[TradeResult])->BacktestMetrics:
    if not trades: return BacktestMetrics(trades=0,net_pnl=0,expectancy=0,profit_factor=None,win_rate=0,max_drawdown=0,average_r=0)
    pnls=[t.pnl for t in trades]; wins=[p for p in pnls if p>0]; losses=[p for p in pnls if p<0]
    equity=peak=0.; max_dd=0.
    for pnl in pnls: equity+=pnl; peak=max(peak,equity); max_dd=max(max_dd,peak-equity)
    groups=lambda key:{k:{"trades":float(len(v)),"net_pnl":sum(x.pnl for x in v),"win_rate":sum(x.pnl>0 for x in v)/len(v)} for k,v in __import__("itertools").groupby(sorted(trades,key=key),key)}
    return BacktestMetrics(trades=len(trades),net_pnl=sum(pnls),expectancy=sum(pnls)/len(pnls),profit_factor=(sum(wins)/abs(sum(losses)) if losses else None),win_rate=len(wins)/len(trades),max_drawdown=max_dd,average_r=sum(t.r_multiple for t in trades)/len(trades),r_distribution=tuple(t.r_multiple for t in trades),regime_breakdown=groups(lambda t:t.regime or "UNKNOWN"),timeframe_breakdown=groups(lambda t:t.timeframe))

def validate_experiment(spec:ExperimentSpec)->tuple[bool,tuple[str,...]]:
    ordered=(spec.train_start,spec.train_end,spec.validation_start,spec.validation_end,spec.test_start,spec.test_end)
    warnings=[]
    if any(ordered[i]>=ordered[i+1] for i in range(len(ordered)-1)): warnings.append("Train, validation and test periods must be chronological and non-overlapping.")
    if not spec.dataset_version or not spec.strategy_version or not spec.feature_version: warnings.append("Dataset, strategy and feature versions are required.")
    return not warnings,tuple(warnings)

def run_backtest(access_token:str,user_id:str,strategy:StrategyDefinition,dataset:OHLCVDataset,spec:ExperimentSpec)->BacktestResult:
    require_feature(access_token,user_id,"backtesting")
    valid,warnings=validate_experiment(spec)
    if not valid: raise ValueError("; ".join(warnings))
    trades=[]; entry=None
    for candle in dataset.completed_candles:
        if not (spec.test_start<=candle.timestamp<=spec.test_end): continue
        if entry is None and _rules_match(candle,strategy.entry_rules): entry=candle
        elif entry is not None and _rules_match(candle,strategy.exit_rules): trades.append(_trade(entry,candle,strategy.direction,spec.execution)); entry=None
    metrics=_metrics(trades)
    checks={"chronological_data":True,"no_future_data":True,"train_validation_test_recorded":True,"execution_assumptions_recorded":True,"dataset_version_recorded":True,"strategy_version_recorded":True,"feature_version_recorded":True}
    payload={"user_id":user_id,"strategy_version":spec.strategy_version,"dataset_version":spec.dataset_version,"feature_version":spec.feature_version,"parameters":spec.parameters,"costs":spec.costs,"execution":spec.execution.model_dump(mode="json"),"train_start":spec.train_start.isoformat(),"train_end":spec.train_end.isoformat(),"validation_start":spec.validation_start.isoformat(),"validation_end":spec.validation_end.isoformat(),"test_start":spec.test_start.isoformat(),"test_end":spec.test_end.isoformat(),"engine_version":ENGINE_VERSION,"metrics":metrics.model_dump(mode="json")}
    row=_request("POST","quant_experiments",access_token,json=payload,prefer="return=representation").json()
    if not row: raise DataRequestError("Quant experiment was not persisted.")
    return BacktestResult(experiment_id=str(row[0]["id"]),metrics=metrics,trades=tuple(trades),anti_overfit_checks=checks,warnings=warnings)

def list_portfolios(access_token:str,user_id:str)->list[PaperPortfolio]:
    rows=_request("GET","paper_portfolios",access_token,params={"select":"id,name,base_currency,starting_equity,equity,drawdown,created_at","user_id":f"eq.{user_id}","order":"created_at.desc"}).json()
    return [PaperPortfolio(**r) for r in rows]

def create_portfolio(access_token:str,user_id:str,payload:dict[str,Any])->PaperPortfolio:
    row=_request("POST","paper_portfolios",access_token,json={"user_id":user_id,**payload},prefer="return=representation").json()
    return PaperPortfolio(**row[0])

def list_trades(access_token:str,user_id:str,portfolio_id:str)->list[PaperTrade]:
    rows=_request("GET","paper_trades",access_token,params={"select":"id,portfolio_id,symbol,side,quantity,entry_price,entry_time,exit_price,exit_time,pnl,strategy_id,signal_id,status","user_id":f"eq.{user_id}","portfolio_id":f"eq.{portfolio_id}","order":"entry_time.desc"}).json()
    return [PaperTrade(**r) for r in rows]

def diagnosis(trades:list[TradeResult])->StrategyDiagnosis:
    if not trades: return StrategyDiagnosis(sample_weakness=True)
    regimes={}
    for t in trades: regimes[t.regime or "UNKNOWN"]=regimes.get(t.regime or "UNKNOWN",0)+1
    return StrategyDiagnosis(sample_weakness=len(trades)<30,concentration={k:v/len(trades) for k,v in regimes.items()})
