import { useMemo } from "react";
import type { TechnicalAnalysis } from "./api";
import type { ChartEvent } from "./phase10Api";

type Props = { analysis: TechnicalAnalysis; events: ChartEvent[] };

const CATEGORY: Record<string,string> = {
  REGIME: "regime", SMC: "smc", BOS: "structure", CHOCH: "structure", LIQUIDITY: "liquidity",
  SIGNAL: "signal", ENTRY: "entry", EXIT: "exit", SL: "risk", TP: "target", OUTCOME: "outcome", RESEARCH: "research", CATALYST: "catalyst",
};

function fmt(value: number): string { return value.toLocaleString(undefined,{maximumFractionDigits:value>=1000?2:8}); }
function time(value: string): number { const parsed=Date.parse(value); return Number.isFinite(parsed)?parsed:NaN; }
function label(value: string): string { return value.replaceAll("_"," "); }

export default function AdvancedResearchChart({analysis,events}: Props){
  const candles=useMemo(()=>analysis.candles.filter(c=>c.is_complete).slice(-180),[analysis]);
  const mapped=useMemo(()=>{
    if(candles.length<2)return [];
    const first=time(candles[0].timestamp),last=time(candles[candles.length-1].timestamp);
    const closeAt=(timestamp:string)=>{
      const t=time(timestamp); let best=candles[0]; let distance=Math.abs(time(best.timestamp)-t);
      for(const candle of candles.slice(1)){const next=Math.abs(time(candle.timestamp)-t);if(next<distance){best=candle;distance=next;}}
      return best.close;
    };
    return events.map(event=>{
      const t=time(event.occurred_at); const ratio=(last===first||!Number.isFinite(t))?0:(t-first)/(last-first);
      return {...event,ratio,plotPrice:typeof event.price==="number"?event.price:closeAt(event.occurred_at)};
    }).filter(event=>event.ratio>=0&&event.ratio<=1);
  },[candles,events]);
  if(candles.length<2)return <div className="phase10-chart-empty">Not enough completed candles to render the advanced research chart.</div>;
  const width=1200,height=520,pad={left:58,right:18,top:24,bottom:38};
  const min=Math.min(...candles.map(c=>c.low)); const max=Math.max(...candles.map(c=>c.high)); const range=Math.max(max-min,Number.EPSILON);
  const x=(i:number)=>pad.left+(i/(candles.length-1))*(width-pad.left-pad.right);
  const y=(price:number)=>pad.top+((max-price)/range)*(height-pad.top-pad.bottom);
  return <div className="phase10-chart-shell">
    <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`${analysis.symbol} ${analysis.timeframe} advanced research chart`} className="phase10-chart">
      {[0,.25,.5,.75,1].map(v=><line key={v} x1={pad.left} x2={width-pad.right} y1={y(max-range*v)} y2={y(max-range*v)} className="phase10-grid"/>)}
      {candles.map((c,i)=>{const cx=x(i), bodyTop=y(Math.max(c.open,c.close)), bodyBottom=y(Math.min(c.open,c.close)); return <g key={c.timestamp}><line x1={cx} x2={cx} y1={y(c.high)} y2={y(c.low)} className="phase10-wick"/><rect x={cx-2.4} y={bodyTop} width={4.8} height={Math.max(1,bodyBottom-bodyTop)} className={c.close>=c.open?"phase10-up":"phase10-down"}/></g>})}
      {mapped.map((event,index)=>{const cx=pad.left+event.ratio*(width-pad.left-pad.right); const cy=y(event.plotPrice); const above=/SL|TP|EXIT|OUTCOME|CATALYST|BOS|CHOCH|LIQUIDITY|REGIME/.test(event.event_type); const markerY=above?cy-18:cy+18; const category=CATEGORY[event.event_type]??"research"; return <g key={`${event.id}-${index}`} className={`phase10-marker phase10-marker-${category}`}><line x1={cx} x2={cx} y1={cy} y2={markerY} className="phase10-marker-stem"/><circle cx={cx} cy={cy} r="5"/><text x={cx+7} y={markerY} className="phase10-marker-label">{label(event.event_type)}</text><title>{label(event.event_type)} · {fmt(event.plotPrice)} · {new Date(event.occurred_at).toLocaleString()}</title></g>})}
      <text x={pad.left} y={height-12} className="phase10-axis-label">{new Date(candles[0].timestamp).toLocaleString()}</text><text x={width-pad.right} y={height-12} textAnchor="end" className="phase10-axis-label">{new Date(candles[candles.length-1].timestamp).toLocaleString()}</text>
      <text x={pad.left-8} y={pad.top+4} textAnchor="end" className="phase10-axis-label">{fmt(max)}</text><text x={pad.left-8} y={height-pad.bottom} textAnchor="end" className="phase10-axis-label">{fmt(min)}</text>
    </svg>
    <div className="phase10-chart-legend">{Object.entries(CATEGORY).map(([key,value])=><span key={key} className={`phase10-legend phase10-marker-${value}`}><i/> {label(key)}</span>)}</div>
  </div>;
}
