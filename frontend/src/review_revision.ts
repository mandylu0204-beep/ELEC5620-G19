import type {PlanDetail} from './plans';

// Read-only presentation binding. Eligibility and operation permissions remain server-owned.
export function boundReview(data:PlanDetail){
  const context=data.version?.version_context;
  if(!context||data.run?.run_id!==context.run_id||data.plan.plan_id!==context.plan_id)return null;
  return [...data.reviews].reverse().find(review=>review.version_context&&
    (['plan_id','plan_version_id','run_id','input_fingerprint'] as const).every(key=>review.version_context![key]===context[key]))??null;
}

// A display/preparation helper only. The server validates the immutable source again.
export function revisionReview(data:PlanDetail){
  if(!data.revision_available||!data.run?.is_active||data.trip_series?.is_current===false||!data.version)return null;
  const review=boundReview(data);const context=data.version.version_context;
  if(data.plan.current_version_id!==context.plan_version_id||data.plan.active_run_id!==context.run_id||data.run.run_id!==context.run_id)return null;
  if(!review||!['REQUEST_REVISION','REJECT'].includes(review.decision)||!review.reason.trim()||!review.version_context)return null;
  return ['plan_id','plan_version_id','run_id','input_fingerprint'].every(key=>
    review.version_context![key as keyof typeof context]===context[key as keyof typeof context])?review:null;
}
