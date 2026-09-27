from __future__ import annotations
from dataclasses import dataclass
from math import exp
from statistics import mean
from typing import Iterable, Sequence

@dataclass(frozen=True)
class CalibrationBin:
    lower: float; upper: float; count: int; predicted: float; observed: float; absolute_error: float
@dataclass(frozen=True)
class CalibrationResult:
    bins: tuple[CalibrationBin, ...]; brier_score: float; sample_size: int; calibrated_probability_available: bool

def sigmoid(value: float) -> float:
    value = max(-40.0, min(40.0, value)); return 1.0 / (1.0 + exp(-value))

def fit_platt_calibration(scores: Sequence[float], outcomes: Sequence[int]) -> tuple[float, float]:
    if len(scores) != len(outcomes) or len(scores) < 20: raise ValueError("At least 20 aligned chronological observations are required for calibration.")
    positives = sum(int(o) == 1 for o in outcomes)
    if positives == 0 or positives == len(outcomes): raise ValueError("Calibration requires both positive and negative outcomes.")
    a, b = 1.0, 0.0
    for _ in range(50):
        p = [sigmoid(a * float(x) + b) for x in scores]
        g1 = sum((int(y)-q)*float(x) for x,y,q in zip(scores,outcomes,p)); g2 = sum(int(y)-q for y,q in zip(outcomes,p))
        h11 = -sum(q*(1-q)*float(x)**2 for x,q in zip(scores,p)); h12 = -sum(q*(1-q)*float(x) for x,q in zip(scores,p)); h22 = -sum(q*(1-q) for q in p)
        det = h11*h22-h12*h12
        if abs(det) < 1e-12: break
        da = (g1*h22-g2*h12)/det; db = (h11*g2-h12*g1)/det
        a = max(-20.0, min(20.0, a-da)); b = max(-20.0, min(20.0, b-db))
        if abs(da)+abs(db) < 1e-8: break
    return a,b

def calibrate(scores: Sequence[float], outcomes: Sequence[int], bins: int = 10) -> CalibrationResult:
    if len(scores) != len(outcomes) or not scores: return CalibrationResult((),0.0,0,False)
    bins=max(2,min(20,bins)); pairs=sorted((max(0.0,min(1.0,float(s))),int(o)) for s,o in zip(scores,outcomes)); step=1.0/bins; result=[]
    for index in range(bins):
        lo,hi=index*step,1.0 if index==bins-1 else (index+1)*step
        values=[(s,o) for s,o in pairs if lo<=s<=hi and (index==bins-1 or s<hi)]
        if not values: continue
        predicted=mean(s for s,_ in values); observed=mean(o for _,o in values); result.append(CalibrationBin(lo,hi,len(values),predicted,observed,abs(predicted-observed)))
    brier=mean((s-o)**2 for s,o in pairs)
    return CalibrationResult(tuple(result),brier,len(pairs),len(pairs)>=20)

def purged_walk_forward_timestamps(timestamps: Sequence[float], train_size: int, validation_size: int, test_size: int, embargo: int = 1):
    if not timestamps or min(train_size,validation_size,test_size)<=0: return ()
    windows=[]; cursor=0
    while cursor+train_size+validation_size+test_size<=len(timestamps):
        train=tuple(timestamps[cursor:cursor+train_size]); validation=tuple(timestamps[cursor+train_size:cursor+train_size+validation_size]); test_start=cursor+train_size+validation_size+max(0,embargo); test=tuple(timestamps[test_start:test_start+test_size])
        if len(test)<test_size: break
        windows.append((train,validation,test)); cursor += test_size
    return tuple(windows)

def regime_conditioned_expectancy(records: Iterable[tuple[str,float]]) -> dict[str,float]:
    grouped={}
    for regime,outcome_r in records: grouped.setdefault(regime or "UNKNOWN",[]).append(float(outcome_r))
    return {regime:mean(values) for regime,values in grouped.items() if values}

def parameter_sensitivity(values: Sequence[tuple[float,float]], tolerance: float=0.25):
    if not values: return {"stable":False,"range":0.0,"relative_range":1.0}
    outcomes=[float(outcome) for _,outcome in values]; baseline=max(abs(mean(outcomes)),1e-12); spread=max(outcomes)-min(outcomes); relative=spread/baseline
    return {"stable":relative<=tolerance,"range":spread,"relative_range":relative}

def similarity_signature(features: dict[str,float], keys: Sequence[str]) -> tuple[float,...]:
    return tuple(round(float(features.get(key,0.0)),6) for key in keys)

def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left)!=len(right) or not left: return 0.0
    numerator=sum(a*b for a,b in zip(left,right)); denom=(sum(a*a for a in left)*sum(b*b for b in right))**0.5
    return numerator/denom if denom else 0.0
