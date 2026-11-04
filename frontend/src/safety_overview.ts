// Display only. All decisions and saving permissions come from the server.
import {safetyCondition,checkNames} from './plan_language.ts';
import type {Safety} from './plans';
import type {Requirements} from './api';
export type SafetyOverviewState={approved:boolean;outdated:boolean;historical?:boolean;saved?:boolean;
 readyForFinalSave?:boolean;decision?:string|null};

export function safetyConcerns(value:Safety,requirements?:Requirements):string[]{
 const codes=value.mandatory_blockers.map(item=>item.code);
 const concerns=Object.keys(checkNames).map(kind=>({kind,...safetyCondition(kind,value.data_quality[kind]??'MISSING',value.evidence,requirements,codes)}))
  .filter(item=>item.attention).map(item=>`${checkNames[item.kind]}: ${item.title}`);
 if(concerns.length)return [...new Set(concerns)];
 return [value.hazards.length||value.risk_level==='HIGH'||value.risk_level==='UNKNOWN'
  ?'Review the saved risks and safety details below.'
  :'No specific safety concern was identified in the saved checks.'];
}

export function safetyNextAction(value:Safety,state:SafetyOverviewState):string{
 if(state.outdated)return 'Checks need updating. Review the current information before final saving.';
 if(state.saved)return state.approved?'Review approval is recorded for this saved version. The saved risk level still applies.'
  :'This final plan is already saved. The saved risk level still applies.';
 if(state.historical)return 'Historical check result. View the current plan for next steps.';
 const incomplete=value.mandatory_blockers.length>0||Object.values(value.data_quality).some(item=>item!=='AVAILABLE');
 if(incomplete)return 'Resolve the outstanding safety issues before final saving.';
 if(state.decision==='REJECT')return 'Review rejected. This plan cannot be saved as final.';
 if(state.decision==='REQUEST_REVISION')return 'Changes requested. Revise the plan and complete the required checks.';
 if(state.approved)return state.readyForFinalSave?'Review approved. The camper can confirm and save the final plan.'
  :'Review approved for this version. Other checks must be resolved before final saving.';
 if(value.requires_human_review||value.outcome==='REVIEW')return 'Founder review is required before final saving.';
 return state.readyForFinalSave?'Review the plan and confirm final saving.':'Complete the remaining checks before final saving.';
}
