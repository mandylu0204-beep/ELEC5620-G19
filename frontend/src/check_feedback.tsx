import type { PlanDetail } from './plans';

const stageNames:Record<string,string>={RECOMMENDING:'Prepare checks',GENERATING:'Prepare checks',SAVING_VERSION:'Read itinerary',
  ASSESSING_LOGISTICS:'Check equipment and costs',ASSESSING_SAFETY:'Check trip safety',ROUTING:'Summarise check results',COMPLETED:'Summarise check results'};
function when(value:string){
  const parsed=new Date(value);
  return Number.isNaN(parsed.getTime())?value:new Intl.DateTimeFormat('en-AU',{timeZone:'Australia/Sydney',dateStyle:'short',timeStyle:'medium'}).format(parsed);
}

export function CheckFeedback({data}:{data:PlanDetail}){
  const feedback=data.check_feedback;
  if(!feedback)return null;
  const running=feedback.status==='IN_PROGRESS';
  const complete=feedback.status==='COMPLETED';
  const unchanged=complete&&feedback.comparison==='UNCHANGED';
  const changed=complete&&feedback.comparison==='CHANGED';
  const title=running?'Rechecking plan':!complete?'This recheck is incomplete':'Recheck completed';
  return <section className={'check-feedback '+(running?'check-feedback-running':complete?'check-feedback-complete':'check-feedback-incomplete')}
    role="status" aria-live="polite" aria-label="This recheck">
    <div className="check-feedback-heading">{running&&<span className="progress-pulse" aria-hidden="true"/>}<h2>{title}</h2></div>
    <p>{running?`${stageNames[data.run?.stage??'']??'Handle check tasks'}, Updates automatically when complete.`
      :!complete?'The itinerary is retained. Review run information. Incomplete checks cannot confirm the plan.'
      :unchanged?'Check results match the previous check.'
      :changed?`${feedback.changed_sections.map(kind=>kind==='LOGISTICS'?'Equipment and costs':'Safety checks').join(', ')}Updated. View results below.`
      :'Check results saved.'}</p>
    <div className="check-feedback-meta"><span>Itinerary unchanged</span><span>{complete&&feedback.completed_at?'Completed '+when(feedback.completed_at):'Started '+when(feedback.started_at)}(Sydney time)</span></div>
    {complete&&!data.current_inputs_error&&!data.finalisation_available&&data.version?.status!=='FINALISED'&&<p className="check-feedback-followup">Address the tasks below before saving.</p>}
    {complete&&data.current_inputs_error&&<p className="check-feedback-followup">Address the notices below before saving.</p>}
  </section>;
}
