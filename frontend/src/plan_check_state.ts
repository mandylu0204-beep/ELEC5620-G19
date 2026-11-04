import type { PlanDetail } from './plans';
import {boundReview} from './review_revision';

export type CheckKey='itinerary'|'logistics'|'safety';
export type CheckStep={key:CheckKey;title:string;state:'pending'|'running'|'passed'|'attention'|'review'|'incomplete';text:string};
export type PlanCheckState={kind:'incomplete'|'adjustment'|'review'|'confirm'|'saved'|'cancelled';title:string;tone:'neutral'|'warning'|'danger'|'success';detail:string;running:boolean;choicePending:boolean};
const stageText:Record<string,string>={RECOMMENDING:'Filtering campsites',GENERATING:'Generating and validating itinerary',SAVING_VERSION:'Saving itinerary',ASSESSING_LOGISTICS:'Checking costs and equipment',ASSESSING_SAFETY:'Checking trip safety',ROUTING:'Validating and saving check results',COMPLETED:'Confirming the outcome of this run'};
const stages=['RECOMMENDING','GENERATING','SAVING_VERSION','ASSESSING_LOGISTICS','ASSESSING_SAFETY','ROUTING','COMPLETED'];
export function pendingRevision(data:PlanDetail){return data.trip_series?.is_current!==false&&data.revision_comparison&&!data.revision_comparison.decision?data.revision_comparison:null;}
export function currentCheckRun(data:PlanDetail){return pendingRevision(data)?.after.run??data.run;}
export function exactApproval(data:PlanDetail,snapshot=false){
  const context=data.version?.version_context;
  const savedScope=data.version?.status==='FINALISED'&&data.run?.status==='SUCCEEDED'&&(snapshot
    ||data.last_final?.is_current===true&&data.last_final.run_id===context?.run_id&&data.last_final.plan_version_id===context?.plan_version_id);
  return data.reviews.some(item=>item.decision==='APPROVE'&&(item.review_id===data.eligibility?.valid_review_id
    ||savedScope&&(!item.version_context||!!context&&(['plan_id','plan_version_id','run_id','input_fingerprint'] as const).every(key=>item.version_context![key]===context[key]))));
}
// Presentation only. In particular, neither a badge nor a passed model response enables saving.
export function planCheckState(data:PlanDetail,{snapshot=false,readError=false}:{snapshot?:boolean;readError?:boolean}={}):PlanCheckState{
  const choice=snapshot?null:pendingRevision(data),run=snapshot?data.run:currentCheckRun(data);
  const state=(kind:PlanCheckState['kind'],detail:string,running=false):PlanCheckState=>({kind,
    title:({incomplete:'Checks incomplete',adjustment:'Plan changes needed',review:'Awaiting human review',confirm:'To be confirmed',saved:'Final plan saved',cancelled:'Checks cancelled'})[kind],
    tone:kind==='saved'||kind==='confirm'&&!choice?'success':kind==='adjustment'||kind==='review'||!!choice?'warning':run?.status==='FAILED'?'danger':'neutral',detail,running,choicePending:!!choice});
  if(snapshot&&data.version?.status==='FINALISED')return state('saved','This is the saved final snapshot.');
  if(run&&['PENDING','RUNNING'].includes(run.status))return state('incomplete',run.status==='PENDING'?'Waiting to start this check.':(stageText[run.stage]??'Running checks')+'.',true);
  if(run?.status==='FAILED')return state('incomplete',choice?'Checks for the proposed plan stopped. The original plan is retained. Use the action in the revision comparison.':'This check stopped. View recovery information. A system error does not mean you need to change your camping arrangements.');
  if(run?.status==='CANCELLED')return state('cancelled','This check was cancelled. Existing records are retained.');
  if(readError)return state('incomplete','The latest result cannot be read. Displaying the most recently read record. Refresh before taking action.');
  if(data.current_inputs_error)return state('incomplete',data.current_inputs_state==='UNAVAILABLE'?'The checking service is temporarily unavailable. Existing plans are retained; review them when service resumes.':'The evidence for the previous check has changed. A new check is needed but has not started automatically.');
  if(choice)return state('confirm','Compare and choose the new plan or keep the original. This choice does not save a final plan or mean safety checks passed.');
  if(run?.status==='SUCCEEDED'&&data.version?.status==='FINALISED')return state('saved','The saved final plan is retained. Updating this trip requires a new confirmation and checks.');
  if(data.recommendations?.result.search_outcome==='NO_MATCH')return state('adjustment','Itinerary: no campsite meets the required conditions. Adjust the trip conditions.');
  if(run?.status!=='SUCCEEDED')return state('incomplete','This check has not been confirmed complete. View run records.');
  const review=boundReview(data);
  if(review?.decision==='REQUEST_REVISION'||review?.decision==='REJECT')return {...state('adjustment','Read the reviewer feedback, adjust the plan and complete the required checks.'),title:review.decision==='REJECT'?'Review rejected':'Revision requested'};
  if(data.finalisation_available&&data.eligibility?.eligible&&checkSteps(data).every(item=>item.state==='passed'))return state('confirm','Current checks passed. Confirm and save, or modify the plan and reassess.');
  const reasons=data.eligibility?.blocking_reasons??[];
  const safety=data.assessments.find(item=>item.kind==='SAFETY')?.result;
  const reviewOnly=reasons.length>0&&reasons.every(item=>item.code==='REVIEW_REQUIRED');
  if(reviewOnly&&data.eligibility?.review_required&&(data.assessments.some(item=>item.result.outcome==='REVIEW')||safety&&'requires_human_review' in safety&&safety.requires_human_review))return state('review','This result requires reviewer judgement. You can confirm and save only after approval and all other conditions are met.');
  if(data.logistics_issues?.length&&data.logistics_issues.every(item=>item.code==='UNCLASSIFIED'))return state('incomplete','The check has not identified a specific cause. Contact the project maintainer; do not repeatedly change unrelated information.');
  if((data.logistics_issues?.length??0)>0||reasons.some(item=>!['REVIEW_REQUIRED','RUN_NOT_SUCCEEDED','ASSESSMENTS_MISSING'].includes(item.code))
    ||['BLOCKED','REVISION_REQUIRED','REJECTED','ESCALATED'].includes(data.version?.status??'')
    ||['NEEDS_USER_INPUT','NEEDS_EVIDENCE','NEEDS_REVISION','CANNOT_RELEASE'].includes(data.display_status??''))return state('adjustment','Address itinerary, costs and equipment, and safety issues, then run checks again.');
  if(data.run?.is_active===false&&data.version?.status==='ELIGIBLE_FOR_FINALISATION')return state('confirm','This historical check is read-only and cannot be used to save the current plan.');
  return state('incomplete','Results or save eligibility are not fully verified. Refresh or view run records.');
}
export function checkSteps(data:PlanDetail,snapshot=false):CheckStep[]{
  const run=data.run,index=stages.indexOf(run?.stage??'');
  const saved=!!data.version?.content.itinerary_entries.length&&!!data.version.content.selected_campsite_ids.length;
  const incomplete=!snapshot&&!!data.current_inputs_error;
  const active=!!run&&['PENDING','RUNNING'].includes(run.status);
  const context=data.version?.version_context;
  const result=(key:CheckKey)=>data.assessments.find(item=>item.kind===(key==='logistics'?'LOGISTICS':'SAFETY')&&!!context&&(['plan_id','plan_version_id','run_id','input_fingerprint'] as const).every(field=>item.version_context[field]===context[field]))?.result;
  return (['itinerary','logistics','safety'] as CheckKey[]).map(key=>{
    const title={itinerary:'Itinerary Agent',logistics:'Costs and equipment Agent',safety:'Safety Agent'}[key];
    const value=(state:CheckStep['state'],text:string):CheckStep=>({key,title,state,text});
    if(incomplete)return value('incomplete','Results need verification');
    const start=key==='itinerary'?0:key==='logistics'?3:4,end=key==='itinerary'?2:start;
    if(active&&run?.status==='PENDING')return value('pending','Not started');
    if(active&&index>=start&&index<=end&&!(key==='itinerary'&&run?.operation==='REASSESS'))return value('running','In progress');
    if(active&&index<start)return value('pending','Not started');
    if(key==='itinerary'){
      if(data.recommendations?.result.search_outcome==='NO_MATCH')return value('attention','Changes needed');
      return saved?value('passed',run?.operation==='REASSESS'?'Reuse saved itinerary':'Passed'):value('incomplete',run?.status==='FAILED'?'Incomplete':'Not started');
    }
    const assessment=result(key);
    if(!assessment)return value('incomplete',run?.status==='FAILED'?'Incomplete':'Not started');
    if(key==='safety'&&'requires_human_review' in assessment&&(assessment.requires_human_review||assessment.outcome==='REVIEW')){
      if(exactApproval(data,snapshot))return value('passed',snapshot?'Approved in the earlier review':'Review approved');
      const reasons=data.eligibility?.blocking_reasons??[];
      return reasons.length&&reasons.every(item=>item.code==='REVIEW_REQUIRED')?value('review','Human judgement required'):value('attention','Action needed');
    }
    if(assessment.outcome==='REVIEW'&&exactApproval(data,snapshot))return value('passed','Review approved');
    return assessment.outcome==='PASSED'?value('passed','Passed'):value('attention','Action needed');
  });
}
