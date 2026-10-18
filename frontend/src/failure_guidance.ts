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
  const titles:Record<string,string>={RECOMMENDING:'营地筛选暂未完成',GENERATING:'行程生成暂未完成',
    SAVING_VERSION:'行程保存暂未完成',ASSESSING_LOGISTICS:'装备与费用检查暂未完成',
    ASSESSING_SAFETY:'安全检查暂未完成',ROUTING:'方案结果尚未确认完成',COMPLETED:'方案结果尚未确认完成'};
  const saved=[...(data.recommendations?['营地筛选结果']:[]),
    ...(data.version?[run.operation==='PLAN'?'行程': '原有行程']:[]),
    ...(logistics?['本次装备与费用检查结果']:[]),...(safety?['本次安全检查结果']:[])];
  const canRetry=run.is_active&&data.retry_available===true;
  const label=run.stage==='ASSESSING_SAFETY'&&!safety?'继续安全检查'
    :run.stage==='ASSESSING_LOGISTICS'&&!logistics?'继续装备与费用检查':'继续未完成的步骤';
  const code=run.error?.code;
  const explanation=code==='INPUT_INVALID'||code==='REQUEST_NOT_CONFIRMED'
    ?'本次需求需要核对并重新确认，请按提示补充资料。'
    :code==='PERSISTENCE_FAILURE'
    ?'本次结果未能完整保存。无需因此重新填写露营请求。'
    :code==='AGENT_FAILURE'||code==='ADAPTER_FAILURE'||code==='CONTRACT_INVALID'
    ?'本次服务处理未能完成。无需仅为此重新填写露营请求。'
    :code==='STALE_CONTEXT'
    ?'本次执行所用资料已变化，请核对最新资料后再继续。'
    :'本次执行未完成，已有内容会继续保留。';
  return {title:noMatch?'搜索结果尚未确认完成':titles[run.stage]??'本次执行尚未完成',saved,canRetry,retryLabel:label,
    explanation,
    retryDescription:run.operation==='REASSESS'
      ?'继续本次检查会保留原行程，复用已保存的检查结果；尚未保存的检查可能重新执行。'
      :'继续本次执行会复用已保存的行程与检查结果；尚未保存的步骤可能重新执行。',
    completionNote:!run.is_active?'这是一次未完成的历史执行，已保存内容仅供查看。':noMatch?'未找到满足条件的营地，搜索结果已保留；此次执行尚未确认完成。':safety?'检查结果已保留，但本次执行尚未确认完成；当前不能保存最终方案。'
      :'尚未完成全部必要检查，当前不能保存最终方案。'};
}
