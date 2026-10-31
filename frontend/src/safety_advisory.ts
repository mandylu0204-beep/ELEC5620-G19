// Presentation only; official safety results and server guards stay authoritative.
export type SafetyAudit = {
  advice_format?:'separate-advice-v1'|'single-advice-v1';
  kind:'SAFETY';run_id:string;plan_version_id:string;assessment_id:string;
  depends_on_assessment_id:string;input_fingerprint:string;
  plan:{findings:{finding_key:string;fact_refs:string[];action_code:string;
    interpretation_unverified:string;action_unverified:string}[];
    action_priority:string[];decision_summary_unverified:string};
};

export type SafetyAdviceBinding = {runId:string;versionId:string;assessmentId:string;
  logisticsId:string;inputFingerprint:string};

const actionTitles:Record<string,string>={
  ACKNOWLEDGE_INFORMATION:'Review trip notices',CHECK_NEAR_DEPARTURE:'Recheck near departure',
  OBTAIN_APPLICABLE_INFORMATION:'Obtain applicable safety evidence',RESOLVE_SOURCE_CONFLICT:'Verify conflicting information',
  REQUEST_HUMAN_REVIEW:'Wait for reviewer verification',CHANGE_TRIP:'Change campsite, dates or activities',
  RESOLVE_LOGISTICS:'Resolve equipment or transport arrangements',CONFIRM_ACTIVITY_DETAILS:'Confirm activity arrangements',
};

export function safetyAdvice(value:SafetyAudit|null|undefined,binding:SafetyAdviceBinding|null){
  if(!value||!binding||value.kind!=='SAFETY'||value.run_id!==binding.runId
      ||value.plan_version_id!==binding.versionId||value.assessment_id!==binding.assessmentId
      ||value.depends_on_assessment_id!==binding.logisticsId||value.input_fingerprint!==binding.inputFingerprint)return null;
  if(value.advice_format!==undefined&&!['separate-advice-v1','single-advice-v1'].includes(value.advice_format))return null;
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
      ||typeof item.interpretation_unverified!=='string'||!item.interpretation_unverified.trim()
      ||value.advice_format==='single-advice-v1'&&item.interpretation_unverified!==item.action_unverified))return null;
  return {summary:plan.decision_summary_unverified,items:ordered.map(item=>({
    key:item!.finding_key,actionCode:item!.action_code,title:actionTitles[item!.action_code],
    explanation:item!.interpretation_unverified,action:item!.action_unverified,
    informational:item!.action_code==='ACKNOWLEDGE_INFORMATION',
  }))};
}

export type SafetyAdviceItem=NonNullable<ReturnType<typeof safetyAdvice>>['items'][number];
export type SafetyAdviceGroup={key:string;title:string;items:SafetyAdviceItem[]};

export function groupSafetyAdvice(items:readonly SafetyAdviceItem[]):SafetyAdviceGroup[]{
  const groups=new Map<string,SafetyAdviceGroup>();
  // Use the validated action code, not model prose or a translated title.
  // Groups follow their first saved priority; members retain relative order.
  for(const item of items){
    let group=groups.get(item.actionCode);
    if(!group){group={key:item.actionCode,title:item.title,items:[]};groups.set(item.actionCode,group);}
    group.items.push(item);
  }
  return [...groups.values()];
}
