type Context={plan_id:string;plan_version_id:string;run_id:string;input_fingerprint:string};
type FailedPlan={run:{run_id:string;status:string;stage:string;operation:string;is_active:boolean;error?:{code:string}|null}|null;
  version:{version_context:Context}|null;recommendations:{result?:{search_outcome?:string}}|null;
  assessments:{kind:string;version_context:Context}[];retry_available?:boolean};

// Describes saved artifacts, never whether an assessment passed or permits travel.
export function failureGuidance(data:FailedPlan){
  const run=data.run;
  if(!run||run.status!=='FAILED')return null;
  const current=(kind:string)=>!!data.version&&data.assessments.some(item=>item.kind===kind
    &&item.version_context.run_id===run.run_id
    &&['plan_id','plan_version_id','input_fingerprint'].every(key=>
      item.version_context[key as keyof Context]===data.version!.version_context[key as keyof Context]));
  const logistics=current('LOGISTICS'),safety=current('SAFETY');
  const noMatch=data.recommendations?.result?.search_outcome==='NO_MATCH';
  const titles:Record<string,string>={RECOMMENDING:'Campsite filtering incomplete',GENERATING:'Itinerary generation incomplete',
    SAVING_VERSION:'Itinerary saving incomplete',ASSESSING_LOGISTICS:'Equipment and cost checks incomplete',
    ASSESSING_SAFETY:'Safety checks incomplete',ROUTING:'Plan result is not yet confirmed complete',COMPLETED:'Plan result is not yet confirmed complete'};
  const saved=[...(data.recommendations?['Campsite filtering results']:[]),
    ...(data.version?[run.operation==='PLAN'?'Itinerary': 'Original itinerary']:[]),
    ...(logistics?['Current equipment and cost check results']:[]),...(safety?['Current safety check results']:[])];
  const canRetry=run.is_active&&data.retry_available===true;
  const label=run.stage==='ASSESSING_SAFETY'&&!safety?'Continue safety checks'
    :run.stage==='ASSESSING_LOGISTICS'&&!logistics?'Continue equipment and cost checks':'Continue unfinished steps';
  const code=run.error?.code;
  const explanation=code==='INPUT_INVALID'||code==='REQUEST_NOT_CONFIRMED'
    ?'Review and reconfirm this request. Complete the information indicated.'
    :code==='PERSISTENCE_FAILURE'
    ?'The result was not fully saved. You do not need to re-enter the camping request for this reason.'
    :code==='AGENT_FAILURE'||code==='ADAPTER_FAILURE'||code==='CONTRACT_INVALID'
    ?'The service could not complete this run. You do not need to re-enter the camping request for this reason.'
    :code==='STALE_CONTEXT'
    ?'Information used by this run changed. Review the latest information before continuing.'
    :'This run is incomplete. Saved results will be retained.';
  return {title:noMatch?'Search results are not yet confirmed complete':titles[run.stage]??'This run is incomplete',saved,canRetry,retryLabel:label,
    explanation,
    retryDescription:run.operation==='REASSESS'
      ?'Continuing keeps the original itinerary and reuses saved check results. Unsaved checks may run again.'
      :'Continuing reuses the saved itinerary and check results. Unsaved steps may run again.',
    completionNote:!run.is_active?'This is an incomplete historical run. Saved content is read-only.':noMatch?'No campsite met the conditions. Search results are retained; this run is not yet confirmed complete.':safety?'Check results are retained but the run is not confirmed complete. The final plan cannot be saved yet.'
      :'Required checks are incomplete. The final plan cannot be saved yet.'};
}
