import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { ApiFailure } from './api';
import { privateApi, useSession } from './session';
import { campName } from './campsite_names';
import { aud } from './plans';

type ComparedPlan={run:{run_id:string;status:string;stage:string;revision:number};version_id:string|null;version_number:number|null;
  campsite_ids:string[];duration_nights:number;nightly_fee_cents:number|null;camp_fee_cents:number|null;total_cents:number|null;safety_outcome?:string|null};
export type RevisionComparisonData={proposal_id:string;revision:number;decision:'ADOPT'|'KEEP'|null;legacy?:boolean;
  status:'GENERATING'|'READY'|'FAILED'|'ADOPT'|'KEEP';before:ComparedPlan;after:ComparedPlan;
  can_adopt:boolean;can_keep:boolean;camp_saving_cents:number|null;total_saving_cents:number|null};

export function savingsText(value:number|null,subject:string){
  return value===null?`${subject} cannot yet be compared`:value>0?`${subject} estimated saving ${aud(value)}`
    :value<0?`${subject} estimated increase ${aud(-value)}`:`${subject} unchanged`;
}

export function RevisionComparison({value,planId,refresh,readOnly=false}:{value:RevisionComparisonData|null|undefined;planId:string;refresh:()=>void;readOnly?:boolean}){
  const {session,reload}=useSession();
  const navigate=useNavigate();
  const [busy,setBusy]=useState(false);const [error,setError]=useState('');
  const command=useRef<{payload:string;key:string}|null>(null);
  useEffect(()=>setError(''),[value?.proposal_id,value?.decision]);
  if(!value)return null;
  const pending=!value.decision;
  const safety=(outcome:string|null|undefined)=>({PASSED:'Checks passed',REVIEW:'Needs verification',REVISION:'Changes needed',BLOCKED:'Conditions not met'} as Record<string,string>)[outcome??'']??'Not completed';
  const row=(title:string,field:'nightly_fee_cents'|'camp_fee_cents'|'total_cents')=><tr><th scope="row">{title}</th>
    <td>{aud(value.before[field])}</td><td>{aud(value.after[field])}</td></tr>;
  async function choose(decision:'ADOPT'|'KEEP'){
    if(!session||busy||!value)return;
    const body={decision,expected_proposal_revision:value.revision,expected_candidate_run_revision:value.after.run.revision};
    const payload=JSON.stringify({proposal:value.proposal_id,...body});
    if(command.current?.payload!==payload)command.current={payload,key:crypto.randomUUID()};
    setBusy(true);setError('');
    try{
      await privateApi('/plans/'+encodeURIComponent(planId)+'/revision-proposals/'+encodeURIComponent(value.proposal_id)+'/decision',{
        method:'POST',headers:{'Content-Type':'application/json','X-CampMate-Client':'1','X-CSRF-Token':session.csrf_token},
        body:JSON.stringify({...body,command_key:command.current.key})});
      navigate('/plans/'+encodeURIComponent(planId));refresh();
    }catch(reason){
      setError(reason instanceof Error?reason.message:'Your selection is not yet confirmed. Refresh or retry the same selection.');
      if(reason instanceof ApiFailure&&reason.envelope.error.code==='UNAUTHENTICATED')reload();
    }finally{setBusy(false);}
  }
  return <section className="panel revision-comparison" aria-label="Compare original and new plans">
    <div className="section-title"><span className="eyebrow">Plan comparison</span><h2>{value.legacy?'Compare current and previous plans':value.decision==='ADOPT'?'New plan adopted':value.decision==='KEEP'?'Original plan retained':'Choose the plan that suits you'}</h2></div>
    {value.status==='GENERATING'?<p role="status">Generating a proposed plan. The original remains the current plan.</p>
      :value.status==='FAILED'?<p role="status">The new plan is incomplete. The original is unaffected and can be retained.</p>
      :<><p className="revision-campsites">{value.before.campsite_ids.map(campName).join(' / ')||'Original campsite'} → {value.after.campsite_ids.map(campName).join(' / ')||'To be confirmed'}</p>
      <div className="table-scroll"><table><caption>Cost estimate comparison</caption><thead><tr><th>Comparison item</th><th>Original plan</th><th>New plan</th></tr></thead><tbody>
        <tr><th scope="row">Campsite</th><td>{value.before.campsite_ids.map(campName).join(' / ')}</td><td>{value.after.campsite_ids.map(campName).join(' / ')||'To be confirmed'}</td></tr>
        {row('Nightly campsite fee','nightly_fee_cents')}{row(`Total campsite fee (${value.before.duration_nights} nights)`,'camp_fee_cents')}{row('Estimated total cost','total_cents')}
        <tr><th scope="row">Safety checks</th><td>{safety(value.before.safety_outcome)}</td><td>{safety(value.after.safety_outcome)}</td></tr>
      </tbody></table></div>
      <p><strong>{savingsText(value.camp_saving_cents,'Campsite fee')}</strong></p><p>{savingsText(value.total_saving_cents,'Total cost')}</p>
    </>}
    {pending&&value.status==='READY'&&<p>The new plan becomes current only after you adopt it.</p>}
    {value.after.version_id&&<Link className="text-link" to={'/plans/'+encodeURIComponent(planId)+'?run_id='+encodeURIComponent(value.after.run.run_id)}>View new plan details ↗</Link>}
    {pending&&!readOnly&&<div className="plan-actions">
      <button className="primary-button" disabled={busy||!value.can_adopt} onClick={()=>void choose('ADOPT')}>{busy?'Saving selection…':'Use proposed plan'}</button>
      <button className="secondary-button" disabled={busy||!value.can_keep} onClick={()=>void choose('KEEP')}>Keep original plan</button>
    </div>}
    {error&&<p className="error-box" role="alert">{error}</p>}
  </section>;
}
