import type { PlanDetail } from './plans';

export type RunProgress = {
  plan_id:string; active_run_id:string|null;
  run:{run_id:string;status:string;stage:string;revision:number;is_active:boolean};
};

export function progressPath(value:PlanDetail):string|null {
  const run=value.run;
  return run?.is_active && ['PENDING','RUNNING'].includes(run.status)
    ? '/runs/'+encodeURIComponent(run.run_id)+'/progress' : null;
}

// A terminal/new run requires the complete, independently validated detail.
// Progress may update the stage, but cannot enable a business action.
export function mergeProgress(value:PlanDetail, progress:RunProgress):PlanDetail|null {
  const run=value.run;
  if(!run || progress.plan_id!==value.plan.plan_id || progress.run.run_id!==run.run_id ||
      progress.active_run_id!==run.run_id || !progress.run.is_active ||
      !['PENDING','RUNNING'].includes(progress.run.status)) return null;
  if(progress.run.revision<run.revision) return value;
  return {...value,run:{...run,...progress.run},retry_available:false,
    revision_available:false,reassessment_available:false,finalisation_available:false};
}
