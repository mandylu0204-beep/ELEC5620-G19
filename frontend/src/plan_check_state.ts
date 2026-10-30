import type { PlanDetail } from './plans';

export type CheckKey='itinerary'|'logistics'|'safety';
export type CheckStep={key:CheckKey;title:string;state:'pending'|'running'|'passed'|'attention'|'review'|'incomplete';text:string};
export type PlanCheckState={kind:'incomplete'|'adjustment'|'review'|'confirm'|'saved'|'cancelled';title:string;tone:'neutral'|'warning'|'danger'|'success';detail:string;running:boolean;choicePending:boolean};
const stageText:Record<string,string>={RECOMMENDING:'正在筛选营地',GENERATING:'正在生成并校验行程',SAVING_VERSION:'正在保存行程',ASSESSING_LOGISTICS:'正在检查费用和装备',ASSESSING_SAFETY:'正在检查出行安全',ROUTING:'正在校验并保存检查结果',COMPLETED:'正在确认本轮执行结果'};
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
    title:({incomplete:'检查未完成',adjustment:'需要调整方案',review:'等待人工审核',confirm:'待确认',saved:'最终方案已保存',cancelled:'已取消检查'})[kind],
    tone:kind==='saved'||kind==='confirm'&&!choice?'success':kind==='adjustment'||kind==='review'||!!choice?'warning':run?.status==='FAILED'?'danger':'neutral',detail,running,choicePending:!!choice});
  if(snapshot&&data.version?.status==='FINALISED')return state('saved','这里展示的是已保存的最终快照。');
  if(run&&['PENDING','RUNNING'].includes(run.status))return state('incomplete',run.status==='PENDING'?'等待开始本轮检查。':(stageText[run.stage]??'正在执行本轮检查')+'。',true);
  if(run?.status==='FAILED')return state('incomplete',choice?'待选新方案检查中断，原方案仍然保留。请查看修订对比中的处理入口。':'本轮检查中断，请查看恢复说明；系统异常不代表你需要修改露营安排。');
  if(run?.status==='CANCELLED')return state('cancelled','本轮检查已取消，已有记录保留。');
  if(readError)return state('incomplete','暂时无法读取最新结果，当前展示最近一次读取的记录。请刷新核对后再操作。');
  if(data.current_inputs_error)return state('incomplete',data.current_inputs_state==='UNAVAILABLE'?'检查服务暂不可用；已有方案保留，服务恢复后再核对。':'此前检查依据已变化，需要重新检查；这不表示系统已经开始重查。');
  if(choice)return state('confirm','请先对比并选择采用新方案或保留原方案；选择不等于最终保存，也不代表安全检查通过。');
  if(run?.status==='SUCCEEDED'&&data.version?.status==='FINALISED')return state('saved','已保存的最终方案会保留；更新出行需要新一轮确认和检查。');
  if(data.recommendations?.result.search_outcome==='NO_MATCH')return state('adjustment','行程：没有找到满足必要条件的营地，请调整出行条件。');
  if(run?.status!=='SUCCEEDED')return state('incomplete','尚未确认本轮检查完成，请查看执行记录。');
  if(data.finalisation_available&&data.eligibility?.eligible&&checkSteps(data).every(item=>item.state==='passed'))return state('confirm','本轮检查通过。你可以确认保存，也可以修改方案后重新评估。');
  const reasons=data.eligibility?.blocking_reasons??[];
  const safety=data.assessments.find(item=>item.kind==='SAFETY')?.result;
  const reviewOnly=reasons.length>0&&reasons.every(item=>item.code==='REVIEW_REQUIRED');
  if(reviewOnly&&data.eligibility?.review_required&&(data.assessments.some(item=>item.result.outcome==='REVIEW')||safety&&'requires_human_review' in safety&&safety.requires_human_review))return state('review','当前结果需要审核员判断；批准且其他条件满足后，才能确认保存。');
  if(data.logistics_issues?.length&&data.logistics_issues.every(item=>item.code==='UNCLASSIFIED'))return state('incomplete','检查尚未定位具体原因，请联系项目负责人核对；无需反复修改无关资料。');
  if((data.logistics_issues?.length??0)>0||reasons.some(item=>!['REVIEW_REQUIRED','RUN_NOT_SUCCEEDED','ASSESSMENTS_MISSING'].includes(item.code))
    ||['BLOCKED','REVISION_REQUIRED','REJECTED','ESCALATED'].includes(data.version?.status??'')
    ||['NEEDS_USER_INPUT','NEEDS_EVIDENCE','NEEDS_REVISION','CANNOT_RELEASE'].includes(data.display_status??''))return state('adjustment','请按行程、费用和装备、安全三类问题处理；完成后重新检查。');
  if(data.run?.is_active===false&&data.version?.status==='ELIGIBLE_FOR_FINALISATION')return state('confirm','这是历史检查结果，仅供查看，不能用于保存当前方案。');
  return state('incomplete','检查结果或保存资格尚未核实完整，请刷新或查看执行记录。');
}
export function checkSteps(data:PlanDetail,snapshot=false):CheckStep[]{
  const run=data.run,index=stages.indexOf(run?.stage??'');
  const saved=!!data.version?.content.itinerary_entries.length&&!!data.version.content.selected_campsite_ids.length;
  const incomplete=!snapshot&&!!data.current_inputs_error;
  const active=!!run&&['PENDING','RUNNING'].includes(run.status);
  const context=data.version?.version_context;
  const result=(key:CheckKey)=>data.assessments.find(item=>item.kind===(key==='logistics'?'LOGISTICS':'SAFETY')&&!!context&&(['plan_id','plan_version_id','run_id','input_fingerprint'] as const).every(field=>item.version_context[field]===context[field]))?.result;
  return (['itinerary','logistics','safety'] as CheckKey[]).map(key=>{
    const title={itinerary:'行程 Agent',logistics:'费用和装备 Agent',safety:'安全 Agent'}[key];
    const value=(state:CheckStep['state'],text:string):CheckStep=>({key,title,state,text});
    if(incomplete)return value('incomplete','结果需要重新核对');
    const start=key==='itinerary'?0:key==='logistics'?3:4,end=key==='itinerary'?2:start;
    if(active&&run?.status==='PENDING')return value('pending','未开始');
    if(active&&index>=start&&index<=end&&!(key==='itinerary'&&run?.operation==='REASSESS'))return value('running','进行中');
    if(active&&index<start)return value('pending','未开始');
    if(key==='itinerary'){
      if(data.recommendations?.result.search_outcome==='NO_MATCH')return value('attention','需要调整');
      return saved?value('passed',run?.operation==='REASSESS'?'复用已保存行程':'已通过'):value('incomplete',run?.status==='FAILED'?'未完成':'未开始');
    }
    const assessment=result(key);
    if(!assessment)return value('incomplete',run?.status==='FAILED'?'未完成':'未开始');
    if(key==='safety'&&'requires_human_review' in assessment&&(assessment.requires_human_review||assessment.outcome==='REVIEW')){
      if(exactApproval(data,snapshot))return value('passed',snapshot?'当时审核已批准':'审核已批准');
      const reasons=data.eligibility?.blocking_reasons??[];
      return reasons.length&&reasons.every(item=>item.code==='REVIEW_REQUIRED')?value('review','待人工判断'):value('attention','需要处理');
    }
    if(assessment.outcome==='REVIEW'&&exactApproval(data,snapshot))return value('passed','审核已批准');
    return assessment.outcome==='PASSED'?value('passed','已通过'):value('attention','需要处理');
  });
}
