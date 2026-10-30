import type { PlanDetail } from './plans';

const stageNames:Record<string,string>={RECOMMENDING:'准备检查',GENERATING:'准备检查',SAVING_VERSION:'读取行程',
  ASSESSING_LOGISTICS:'检查装备与费用',ASSESSING_SAFETY:'检查出行安全',ROUTING:'整理检查结果',COMPLETED:'整理检查结果'};
function when(value:string){
  const parsed=new Date(value);
  return Number.isNaN(parsed.getTime())?value:new Intl.DateTimeFormat('zh-CN',{timeZone:'Australia/Sydney',dateStyle:'short',timeStyle:'medium'}).format(parsed);
}

export function CheckFeedback({data}:{data:PlanDetail}){
  const feedback=data.check_feedback;
  if(!feedback)return null;
  const running=feedback.status==='IN_PROGRESS';
  const complete=feedback.status==='COMPLETED';
  const unchanged=complete&&feedback.comparison==='UNCHANGED';
  const changed=complete&&feedback.comparison==='CHANGED';
  const title=running?'正在重新检查方案':!complete?'本次重新检查尚未完成':'重新检查已完成';
  return <section className={'check-feedback '+(running?'check-feedback-running':complete?'check-feedback-complete':'check-feedback-incomplete')}
    role="status" aria-live="polite" aria-label="本次重新检查">
    <div className="check-feedback-heading">{running&&<span className="progress-pulse" aria-hidden="true"/>}<h2>{title}</h2></div>
    <p>{running?`${stageNames[data.run?.stage??'']??'处理检查任务'}，完成后会自动更新。`
      :!complete?'行程仍然保留。请查看执行提示，尚未完成的检查不能用于确认方案。'
      :unchanged?'检查结果与上次一致。'
      :changed?`${feedback.changed_sections.map(kind=>kind==='LOGISTICS'?'装备与费用':'安全检查').join('、')}已更新，请查看下方结果。`
      :'检查结果已保存。'}</p>
    <div className="check-feedback-meta"><span>行程保持不变</span><span>{complete&&feedback.completed_at?'完成于 '+when(feedback.completed_at):'开始于 '+when(feedback.started_at)}（悉尼时间）</span></div>
    {complete&&!data.current_inputs_error&&!data.finalisation_available&&data.version?.status!=='FINALISED'&&<p className="check-feedback-followup">保存前，请处理下方待办。</p>}
    {complete&&data.current_inputs_error&&<p className="check-feedback-followup">保存前，请先处理下方提示。</p>}
  </section>;
}
