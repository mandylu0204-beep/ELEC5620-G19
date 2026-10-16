import { needsMealChoice } from './logistics_guidance';
import { Link } from 'react-router-dom';
import type { PlanDetail } from './plans';

// Navigation guidance only; all operations remain controlled by server flags.
export function NextSteps({data,onRecheck}:{data:PlanDetail;onRecheck?:()=>void}) {
  const run=data.run;
  if(!run?.is_active||['PENDING','RUNNING'].includes(run.status))return null;
  const reasons=new Set(data.eligibility?.blocking_reasons.map(item=>item.code));
  const review=data.reviews.at(-1);
  const safety=data.assessments.find(item=>item.kind==='SAFETY')?.result;
  const quality=safety&&'data_quality' in safety?Object.values(safety.data_quality):[];
  const logistics=data.assessments.find(item=>item.kind==='LOGISTICS')?.result;
  const mealUnknown=!!logistics&&'clarifications' in logistics&&needsMealChoice(logistics.clarifications);
  let title='调整方案后再确认';
  let description='按列出的问题调整安排。修改日期、人数、预算、偏好或露营资料时，需要重新确认需求。';
  if(data.current_inputs_error){
    title=data.current_inputs_state==='CHANGED'?'此前的检查结果需要更新':'检查服务暂不可用';
    description=data.current_inputs_state==='CHANGED'
      ? '用于检查方案的资料或服务设置已更新，此前的费用和安全结果仅供参考。可以保留行程重新检查；如修改日期、人数或预算，请重新确认需求。'
      : '当前无法核对已有检查结果，暂不能确认保存。你的行程和已有结果仍然保留，请在服务恢复后再检查。';
  }else if(run.status==='FAILED'){
    if(run.error?.code==='REQUEST_NOT_CONFIRMED'){
      title='请重新确认需求';description='修改涉及预算、日期或必须条件，请核对新需求并确认后再规划。';
    }else if(run.error?.code==='INPUT_INVALID'){
      title='请调整本次要求';description='本次输入或修改意见暂不支持，请查看原因并调整需求后重新确认。';
    }else{
      title='规划暂未完成';description=data.retry_available?'原方案和已完成的检查已保留，可从中断位置继续规划。':'当前暂时无法继续规划，请联系项目负责人检查服务。';
    }
  }else if(data.recommendations?.result.search_outcome==='NO_MATCH'){
    title='可以参考最接近的营地';description='下方会列出最接近的营地及未满足的条件。参考差异调整预算、日期或必须条件，再重新确认需求。';
  }else if(data.version?.status==='FINALISED')return null;
  else if(data.finalisation_available&&data.eligibility?.eligible){
    title=review?.decision==='APPROVE'?'审核已通过，待你确认保存':'方案已生成，待你确认保存';
    description='核对行程、费用、装备和安全信息，在页面下方勾选确认后保存最终方案。';
  }else if(reasons.has('ROAD_CLOSED')||reasons.has('CAMPSITE_CLOSED')||reasons.has('FIRE_PROHIBITED')){
    title=reasons.has('ROAD_CLOSED')?'请更换可通行的营地':reasons.has('CAMPSITE_CLOSED')?'请更换开放的营地':'请调整营火安排';
    description='按列出的出行限制调整安排，再检查新方案。审核员不能解除道路、营地关闭或禁火规定。';
  }else if(quality.some(value=>['MISSING','STALE','CONFLICTING'].includes(value))){
    const upcomingWeather=data.trip_evidence_coverage?.next_weather_check_on;
    title=upcomingWeather?'行程已生成，天气待临近出发时检查':'当前资料还不能支持完整的安全判断';
    description=upcomingWeather?`你可以先核对行程、装备和费用，方案会继续保留。建议在 ${upcomingWeather} 或之后重新检查；天气及其他安全条件仍以届时结果为准。`:'在安全页查看缺少的资料、日期范围或冲突。你可以调整日期或营地，也可以保留草稿，待资料更新后再检查。同一天重复检查不会延长天气预报范围。';
  }else if((data.logistics_issues??[]).length){
    title='按具体待办完成检查';description='按上方待办补充并保存资料后，可点击“使用最新资料重新规划”。原来的日期、预算和偏好会保留。';
  }else if(mealUnknown){
    title='先确认用餐方式';description='行程已保留。点击下方调整需求，选择即食餐食或自行烹饪，再重新确认。系统会据此计算餐食费用和所需装备；交通已确认时无需重复修改。';
  }else if(review?.decision==='REQUEST_REVISION'||review?.decision==='REJECT'){
    title=review.decision==='REJECT'?'审核未通过，请调整方案':'审核员要求调整方案';
    description='按审核理由调整安排。更换营地可修改方案；更改日期、预算、人数或偏好时，请重新确认需求。';
  }else if(reasons.size===1&&reasons.has('REVIEW_REQUIRED')){
    title='等待审核员处理';description='这份方案需要人工核对风险，审核完成后可继续。';
  }
  return <section className="panel next-steps" aria-label="接下来怎么做"><h2>{title}</h2><p>{description}</p>
    {data.current_inputs_error&&<>{data.current_inputs_state==='CHANGED'&&<p className="muted">重新检查保留当前行程；若资料仍缺失或不适用，问题仍会保留。</p>}
      {data.reassessment_available&&onRecheck?<button className="secondary-button" onClick={onRecheck}>前往重新检查 ↓</button>:<p className="muted">当前暂不能启动检查，原行程已保留。</p>}
      <details className="source-details"><summary>查看系统详情</summary><p>{data.current_inputs_error}</p></details></>}
    {review&&<div className="clarifications"><strong>审核理由</strong><p>{review.reason}</p></div>}
    <div className="plan-actions"><Link className="text-link" to={'/request?copy_from='+encodeURIComponent(data.plan.request_id)}>调整需求并重新确认 ↗</Link><Link className="text-link" to={'/profile?plan_id='+encodeURIComponent(data.plan.plan_id)+'&request_id='+encodeURIComponent(data.plan.request_id)}>修改露营资料 ↗</Link></div>
  </section>;
}
