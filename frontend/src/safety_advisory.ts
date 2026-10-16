// Presentation only; official safety results and server guards stay authoritative.
export type SafetyAudit = {
  kind:'SAFETY';run_id:string;plan_version_id:string;assessment_id:string;
  depends_on_assessment_id:string;input_fingerprint:string;
  plan:{findings:{finding_key:string;fact_refs:string[];action_code:string;
    interpretation_unverified:string;action_unverified:string}[];
    action_priority:string[];decision_summary_unverified:string};
};

export type SafetyAdviceBinding = {runId:string;versionId:string;assessmentId:string;
  logisticsId:string;inputFingerprint:string};

const actionTitles:Record<string,string>={
  ACKNOWLEDGE_INFORMATION:'了解出行注意事项',CHECK_NEAR_DEPARTURE:'临近出发时再检查',
  OBTAIN_APPLICABLE_INFORMATION:'补齐适用的安全资料',RESOLVE_SOURCE_CONFLICT:'核实相互冲突的资料',
  REQUEST_HUMAN_REVIEW:'等待审核员核对',CHANGE_TRIP:'调整营地、日期或活动',
  RESOLVE_LOGISTICS:'完善装备或交通安排',CONFIRM_ACTIVITY_DETAILS:'确认活动安排',
};

export function safetyAdvice(value:SafetyAudit|null|undefined,binding:SafetyAdviceBinding|null){
  if(!value||!binding||value.kind!=='SAFETY'||value.run_id!==binding.runId
      ||value.plan_version_id!==binding.versionId||value.assessment_id!==binding.assessmentId
      ||value.depends_on_assessment_id!==binding.logisticsId||value.input_fingerprint!==binding.inputFingerprint)return null;
  const plan=value.plan;
  if(!plan||!Array.isArray(plan.findings)||!Array.isArray(plan.action_priority)
      ||!plan.findings.length||plan.findings.length>64||plan.action_priority.length!==plan.findings.length
      ||plan.findings.some(item=>!item||typeof item.finding_key!=='string'||!item.finding_key)
      ||typeof plan.decision_summary_unverified!=='string'||!plan.decision_summary_unverified.trim())return null;
  const byKey=new Map(plan.findings.map(item=>[item.finding_key,item]));
  if(byKey.size!==plan.findings.length||new Set(plan.action_priority).size!==plan.findings.length)return null;
  const ordered=plan.action_priority.map(key=>byKey.get(key));
  if(ordered.some(item=>!item||!Object.hasOwn(actionTitles,item.action_code)
      ||typeof item.action_unverified!=='string'||!item.action_unverified.trim()
      ||typeof item.interpretation_unverified!=='string'||!item.interpretation_unverified.trim()))return null;
  return {summary:plan.decision_summary_unverified,items:ordered.map(item=>({
    key:item!.finding_key,title:actionTitles[item!.action_code],
    explanation:item!.interpretation_unverified,action:item!.action_unverified,
    informational:item!.action_code==='ACKNOWLEDGE_INFORMATION',
  }))};
}
