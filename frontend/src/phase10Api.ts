import { request, authenticatedMutation } from "./api";

export type Phase10Overview = {
  model_governance:{models:number;versions_by_status:Record<string,number>;automatic_promotion:boolean};
  advanced_charting:{events:number;event_types:string[]};
  fundamental_intelligence:{observations:number;types:string[]};
  product_intelligence:{tracked_events:number};
  optimization:{cache_namespace:string;maintenance:string};
};
export type ChartEvent = {id:string;symbol:string;timeframe:string;event_type:string;occurred_at:string;price:number|null;payload:Record<string,unknown>;source:string|null;engine_version:string|null};
export type FundamentalObservation = {id:string;symbol:string;observation_type:string;period_start:string|null;period_end:string|null;observed_at:string;source:string|null;source_version:string|null;payload:Record<string,unknown>};
export type ModelVersion = {id:string;model_id:string;version:string;status:string;dataset_version:string;feature_version:string;training_period_start:string;training_period_end:string;validation_period_start:string;validation_period_end:string;test_period_start:string;test_period_end:string;calibration:Record<string,unknown>;test_results:Record<string,unknown>;performance_by_regime:Record<string,unknown>;degradation_monitoring:Record<string,unknown>;test_passed:boolean;promotion_actor_user_id:string|null;promoted_at:string|null;rollback_reason:string|null};
export type ResearchModel = {id:string;name:string;model_type:string;description:string|null;active_version_id:string|null;versions:ModelVersion[]};

export const getPhase10Overview=()=>request<Phase10Overview>("/api/phase10/overview");
export const getChartEvents=(symbol:string,timeframe:string)=>request<{items:ChartEvent[]}>(`/api/phase10/chart-events?symbol=${encodeURIComponent(symbol)}&timeframe=${encodeURIComponent(timeframe)}`);
export const createChartEvent=(payload:Partial<ChartEvent>&{symbol:string;event_type:string})=>authenticatedMutation<{item:ChartEvent}>("/api/phase10/chart-events",{method:"POST",body:JSON.stringify(payload)});
export const getFundamentals=(symbol:string)=>request<{items:FundamentalObservation[]}>(`/api/phase10/fundamentals?symbol=${encodeURIComponent(symbol)}`);
export const createFundamental=(payload:Record<string,unknown>)=>authenticatedMutation<{item:FundamentalObservation}>("/api/phase10/fundamentals",{method:"POST",body:JSON.stringify(payload)});
export const getPhase10Models=()=>request<{items:ResearchModel[]}>("/api/phase10/models");
export const createPhase10Model=(payload:{name:string;model_type:string;description?:string})=>authenticatedMutation<{item:ResearchModel}>("/api/phase10/models",{method:"POST",body:JSON.stringify(payload)});
export const createPhase10ModelVersion=(modelId:string,payload:Record<string,unknown>)=>authenticatedMutation<{item:ModelVersion}>(`/api/phase10/models/${encodeURIComponent(modelId)}/versions`,{method:"POST",body:JSON.stringify(payload)});
export const evaluatePhase10Model=(versionId:string,payload:Record<string,unknown>)=>authenticatedMutation<{item:ModelVersion}>(`/api/phase10/model-versions/${encodeURIComponent(versionId)}/evaluate`,{method:"POST",body:JSON.stringify(payload)});
export const promotePhase10Model=(versionId:string)=>authenticatedMutation<{item:ModelVersion}>(`/api/phase10/model-versions/${encodeURIComponent(versionId)}/promote`,{method:"POST"});
export const rollbackPhase10Model=(versionId:string,reason:string)=>authenticatedMutation<{item:ModelVersion}>(`/api/phase10/model-versions/${encodeURIComponent(versionId)}/rollback`,{method:"POST",body:JSON.stringify({reason})});
export const trackPhase10Event=(payload:{event_name:string;feature?:string;properties?:Record<string,unknown>})=>authenticatedMutation("/api/phase10/events",{method:"POST",body:JSON.stringify(payload)});
