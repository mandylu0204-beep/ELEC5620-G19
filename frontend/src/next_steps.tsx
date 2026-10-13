import { Link } from 'react-router-dom';
import type { PlanDetail } from './plans';

// These are navigation hints. Only the server's saved eligibility and action
// flags decide whether review, revision or finalisation is allowed.
export function NextSteps({ data }: { data: PlanDetail }) {
  const run = data.run;
  if (!run?.is_active || ['PENDING', 'RUNNING'].includes(run.status)) return null;
  const reasons = new Set(data.eligibility?.blocking_reasons.map(item => item.code));
  const review = data.reviews.at(-1);
  const safety = data.assessments.find(item => item.kind === 'SAFETY')?.result;
  const quality = safety && 'data_quality' in safety ? Object.values(safety.data_quality) : [];
  let title = '先处理当前方案的问题';
  let description = '查看下面的具体原因。修改行程会生成新版本；修改日期、人数、预算或偏好需重新确认需求。';
  if (data.current_inputs_error) {
    title = '当前输入已变化';
    description = '当前数据或运行配置与这次评估不同。先核对配置和需求，再按当前输入重新确认或评估。旧结果不能直接放行。';
  } else if (run.status === 'FAILED') {
    if (run.error?.code === 'REQUEST_NOT_CONFIRMED') {
      title = '需要重新确认需求';
      description = '本次修改涉及已确认的预算、日期或约束。原需求没有被改写；请新建需求，核对新摘要并明确确认后再规划。';
    } else if (run.error?.code === 'INPUT_INVALID') {
      title = '本次要求未能执行';
      description = '当前模式不支持本次输入或修改意见。请查看执行原因，调整需求并重新确认；重复重试不会改变不支持的要求。';
    } else {
      title = '规划执行中断';
      description = data.retry_available
        ? '已保存的产物仍然保留。可使用下方“重试规划”从中断阶段继续；重试不会解除业务阻止条件。'
        : data.retry_unavailable_reason ?? '请核对服务与当前输入，再刷新记录。尚未完成的执行不能保存为最终方案。';
    }
  } else if (data.recommendations?.result.search_outcome === 'NO_MATCH') {
    title = '没有满足需求的营地';
    description = '这是本次需求的搜索结果。请查看被排除的营地和原因，调整预算、日期或必须条件后重新确认需求。';
  } else if (data.version?.status === 'FINALISED') {
    return null;
  } else if (data.finalisation_available && data.eligibility?.eligible) {
    title = review?.decision === 'APPROVE' ? '本次审核已批准，可以最终保存' : '当前方案可以最终保存';
    description = '阅读行程、费用、装备与安全依据，在页面下方勾选确认并保存。只有最终保存成功后，方案才会标为已最终化。';
  } else if (quality.some(value => ['MISSING', 'STALE', 'CONFLICTING'].includes(value))) {
    title = quality.includes('CONFLICTING') ? '先解决证据冲突' : quality.includes('STALE') ? '先更新过期证据' : '先补齐安全证据';
    description = '查看“安全与证据”中的具体类别、来源和适用日期。Founder 批准不能补齐或替代这些证据；证据更新后需开启新的评估。';
  } else if (reasons.has('ROAD_CLOSED') || reasons.has('ROAD_UNAVAILABLE') || reasons.has('FIRE_PROHIBITED') || reasons.has('CAMPSITE_CLOSED')) {
    title = '先解决强制阻止条件';
    description = '道路关闭、营地关闭或禁止营火不能由人工批准解除。更换可用营地，或调整需求并重新确认，再生成和评估新方案。';
  } else if (review?.decision === 'REQUEST_REVISION' || review?.decision === 'REJECT') {
    title = review.decision === 'REJECT' ? '审核未通过，请调整方案' : 'Founder 要求修订';
    description = '按审核理由调整。若只更换营地，可使用方案修订；若改变日期、预算、人数或偏好，请新建并确认需求。';
  } else if (reasons.size === 1 && reasons.has('REVIEW_REQUIRED')) {
    title = '等待 Founder 审核';
    description = '当前评估需要人工判断，尚不能最终保存。页面会定期读取审核状态；审核只适用于本次版本和评估。';
  } else if (reasons.has('REVISION_REQUIRED')) {
    title = '需要修订后再检查';
    description = '按费用差额、装备缺口和审核理由处理。补充露营资料不会改写本次快照；资料变化后需新建并确认需求。';
  }
  return <section className="panel next-steps" aria-label="接下来怎么做"><h2>{title}</h2><p>{description}</p>
    {review && <div className="clarifications"><strong>本次审核理由</strong><p>{review.reason}</p></div>}
    <div className="plan-actions"><Link className="text-link" to={'/request?copy_from=' + encodeURIComponent(data.plan.request_id)}>调整需求并重新确认 ↗</Link>
      <Link className="text-link" to="/profile">修改露营资料 ↗</Link></div>
    <p className="muted">调整需求入口只载入可编辑表单，不会自动保存、确认或覆盖已有方案。</p>
  </section>;
}
