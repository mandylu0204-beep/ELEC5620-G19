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
  let title='调整方案后再确认';
  let description='按列出的问题调整安排。修改日期、人数、预算、偏好或露营资料时，需要重新确认需求。';
  if(data.current_inputs_error){
    title='此前的检查结果需要更新';
    description=/变化|不同|不一致|漂移/.test(data.current_inputs_error)
      ? '用于检查方案的资料或服务设置已更新，此前的费用和安全结果仅供参考。可以保留行程重新检查；如修改日期、人数或预算，请重新确认需求。'
      : '当前暂时无法核对这份方案此前的检查结果，请先恢复检查服务。原行程仍然保留。';
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
    title='先确认此次行程的安全信息';description='查看安全页的具体问题和适用日期。可调整日期或营地；若资料本身需要补充或更新，请由项目负责人维护后再检查。重新检查不会自动补齐资料。';
  }else if(review?.decision==='REQUEST_REVISION'||review?.decision==='REJECT'){
    title=review.decision==='REJECT'?'审核未通过，请调整方案':'审核员要求调整方案';
    description='按审核理由调整安排。更换营地可修改方案；更改日期、预算、人数或偏好时，请重新确认需求。';
  }else if(reasons.size===1&&reasons.has('REVIEW_REQUIRED')){
    title='等待审核员处理';description='这份方案需要人工核对风险，审核完成后可继续。';
  }
  return <section className="panel next-steps" aria-label="接下来怎么做"><h2>{title}</h2><p>{description}</p>
    {data.current_inputs_error&&<><p className="muted">重新检查会更新装备、费用和安全结果，保留当前行程；资料仍不适用时，方案仍需调整。</p>
      {data.reassessment_available&&onRecheck?<button className="secondary-button" onClick={onRecheck}>前往重新检查 ↓</button>:<p className="muted">当前暂不能重新检查，请联系项目负责人更新资料或恢复服务。</p>}
      <details className="source-details"><summary>查看系统详情</summary><p>{data.current_inputs_error}</p></details></>}
    {review&&<div className="clarifications"><strong>审核理由</strong><p>{review.reason}</p></div>}
    <div className="plan-actions"><Link className="text-link" to={'/request?copy_from='+encodeURIComponent(data.plan.request_id)}>调整需求并重新确认 ↗</Link><Link className="text-link" to="/profile">修改露营资料 ↗</Link></div>
  </section>;
}
