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
  const title=running?'正在重新检查方案':!complete?'本次重新检查尚未完成':unchanged?'重新检查完成，结果与上次一致':'重新检查已完成';
  return <section className={'check-feedback '+(running?'check-feedback-running':complete?'check-feedback-complete':'check-feedback-incomplete')}
    role="status" aria-live="polite" aria-label="本次重新检查">
    <div className="check-feedback-heading">{running&&<span className="progress-pulse" aria-hidden="true"/>}<h2>{title}</h2></div>
    <p>{running?`${stageNames[data.run?.stage??'']??'处理检查任务'}，完成后会自动更新。`
      :!complete?'行程仍然保留。请查看执行提示，尚未完成的检查不能用于确认方案。'
      :unchanged?'装备与费用评估、安全检查的结果及依据与上次一致。'
      :changed?`${feedback.changed_sections.map(kind=>kind==='LOGISTICS'?'装备与费用':'安全检查').join('、')}的结果或依据已有更新，请核对下方内容。`
      :'本次装备、费用与安全检查结果已保存。'}</p>
    <div className="check-feedback-meta"><span>行程保持不变</span><span>{complete&&feedback.completed_at?'完成于 '+when(feedback.completed_at):'开始于 '+when(feedback.started_at)}（悉尼时间）</span></div>
    {complete&&!data.current_inputs_error&&!data.finalisation_available&&data.version?.status!=='FINALISED'&&<p className="check-feedback-followup">检查已执行完毕，方案仍有待处理事项，请查看下方说明。</p>}
    {complete&&data.current_inputs_error&&<p className="check-feedback-followup">这是本轮已保存的结果；当前确认前仍需处理下方的检查更新提示。</p>}
  </section>;
}
