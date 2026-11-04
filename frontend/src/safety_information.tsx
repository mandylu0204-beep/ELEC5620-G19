import {safetyConcerns,safetyNextAction} from './safety_overview';
import {visitorText} from './visitor_text.ts';
import type { ReactNode } from 'react';
import type { Safety, Source } from './plans';
import type { Requirements } from './api';
import { checkNames,safetyCondition,safetySummary,safetyRegulations } from './plan_language';
import { TripCoveragePanel, type TripCoverage } from './trip_coverage';

export function SafetyInformation({value,requirements,approved,review,outdated,blockers,notes,rawWarnings,sources,label,coverage,requestId,planId,readOnly=false,historical=false,saved=false,readyForFinalSave=false,decision}:{
  value:Safety|undefined;requirements:Requirements|undefined;approved:boolean;review:boolean;outdated:boolean;
  blockers:ReactNode;notes:ReactNode;rawWarnings:{code:string;message:string}[];sources:(refs:Source[])=>ReactNode;label:(value:string)=>string;
  coverage?:TripCoverage|null;requestId?:string;planId?:string;readOnly?:boolean;historical?:boolean;saved?:boolean;readyForFinalSave?:boolean;decision?:string|null}){
  if(!value)return <section className="panel"><h2>Trip safety information</h2><p>Safety checks will appear here after planning.</p></section>;
  const codes=value.mandatory_blockers.map(item=>item.code);
  const hazards=[...new Set(value.hazards)].map(original=>({original,text:safetySummary(original)??safetyRegulations(original)}));
  const states=Object.keys(checkNames).map(kind=>({kind,...safetyCondition(kind,value.data_quality[kind]??'MISSING',value.evidence,requirements,codes)}));
  return <section className="panel"><div className="section-title"><span className="eyebrow">Verify before departure</span><h2>Trip safety information</h2></div>
    <dl className="safety-overview" aria-label="Safety result and next steps">
      <div><dt>Risk level</dt><dd><strong className={['HIGH','MEDIUM','UNKNOWN'].includes(value.risk_level)?'safety-risk-attention':undefined}>{value.risk_level}</strong>{value.risk_level==='UNKNOWN'&&<span> · Needs confirmation</span>}</dd></div>
      <div><dt>Main concern</dt><dd>{safetyConcerns(value,requirements).map(text=><p key={text}>{text}</p>)}</dd></div>
      <div><dt>Required action</dt><dd>{safetyNextAction(value,{approved,outdated,historical,saved,readyForFinalSave,decision})}</dd></div>
      <div><dt>Before departure</dt><dd>Recheck weather, road access and campsite notices. Confirm any unresolved equipment or transport arrangements.</dd></div>
    </dl>{review&&<p className="muted">Evidence completeness: {label(value.confidence)}</p>}
    {outdated&&<p className="mode-notice">This is the previous check result. Update checks.</p>}
    {!outdated&&requestId&&<TripCoveragePanel value={coverage} planId={planId} readOnly={readOnly}/>}
    <div className="safety-quality">{states.map(state=><div className={state.attention?'quality-issue':'quality-available'} key={state.kind}><span>{checkNames[state.kind]}</span><strong>{state.title}</strong><span>{state.detail}</span></div>)}</div>
    {blockers}
    {(value.evidence.length>0||value.hazards.length>0)&&<details className="artifact-notes"><summary>View safety details and campsite rules</summary>
      {hazards.length>0&&<><h3>Risks to note</h3><ul>{hazards.map(({original,text})=><li key={original}>{text??'Some risks require verification. View the saved explanation.'}
        {!text&&<details><summary>View the saved original risk explanation</summary><p>{visitorText(original)}</p></details>}
      </li>)}</ul></>}
      {value.evidence.map((item,index)=>{const state=safetyCondition(item.kind,item.status,[item],requirements);const text=safetySummary(item.summary)??safetyRegulations(item.summary);return <article className="evidence-item" key={index}><h3>{checkNames[item.kind]??'Safety information'} · {state.title}</h3>
        {text&&<p>{text}</p>}
        {!review&&!text&&item.summary&&<details><summary>View the saved original safety explanation</summary><p>{visitorText(item.summary)}</p></details>}
        {review&&<details className="source-details"><summary>View sources and original text</summary>{item.summary&&<p>{visitorText(item.summary)}</p>}{sources(item.source_refs)}</details>}
      </article>;})}
    </details>}
    {review&&<details className="artifact-notes"><summary>Full check details</summary><p>Saved assessment result: {label(value.outcome)} · Evidence completeness:{label(value.confidence)}</p>
      {value.hazards.length>0&&<><h3>Original risk explanation</h3><ul>{value.hazards.map((item,index)=><li key={index}>{visitorText(item)}</li>)}</ul></>}
      {value.unresolved_conflicts.length>0&&<><h3>Conflicting information</h3><ul>{value.unresolved_conflicts.map((item,index)=><li key={index}>{visitorText(item)}</li>)}</ul></>}
      {value.recommended_actions.length>0&&<><h3>Original check suggestions</h3><ul>{value.recommended_actions.map((item,index)=><li key={index}>{visitorText(item)}</li>)}</ul></>}
      {rawWarnings.map((item,index)=><p key={index}><strong>{item.code}</strong> · {visitorText(item.message)}</p>)}{notes}
    </details>}
  </section>;
}
