import {planCheckState,pendingRevision} from './plan_check_state';
import { useRef, useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { ApiFailure } from './api';
import type { PlanDetail } from './plans';
import { privateApi, useSession } from './session';

export function FinalisePanel({data,readError=false,onModify}:{data:PlanDetail;readError?:boolean;onModify?:()=>void}){
  const {session,reload}=useSession();const navigate=useNavigate();
  const [acknowledged,setAcknowledged]=useState(false);const [busy,setBusy]=useState(false);const [error,setError]=useState('');
  const saveAvailable=!readError&&planCheckState(data).kind==='confirm'&&!pendingRevision(data)&&data.finalisation_available&&data.eligibility?.eligible===true&&data.run?.status==='SUCCEEDED'&&data.run.is_active&&data.trip_series?.is_current!==false;
  const pending=useRef<{key:string;payload:string}|null>(null);const submitting=useRef(false);
  async function submit(event:FormEvent){
    event.preventDefault();if(!data.version||!data.run||!saveAvailable||!acknowledged||!session||submitting.current)return;
    const input={version_context:data.version.version_context,assessment_ids:data.assessments.map(item=>item.assessment_id).sort(),expected_review_id:data.eligibility?.valid_review_id??null,expected_version_revision:data.version.revision,expected_run_revision:data.run.revision,acknowledged:true};
    const payload=JSON.stringify(input);if(pending.current?.payload!==payload)pending.current={key:crypto.randomUUID(),payload};
    submitting.current=true;setBusy(true);setError('');
    try{const value=await privateApi<{final_id:string}>('/plans/'+data.plan.plan_id+'/finalise',{method:'POST',headers:{'Content-Type':'application/json','X-CampMate-Client':'1','X-CSRF-Token':session.csrf_token},body:JSON.stringify({...input,command_key:pending.current!.key})});navigate('/plans/'+data.plan.plan_id+'/finals/'+value.final_id);}
    catch(reason){setError(reason instanceof ApiFailure?`${reason.message}(Trace ID ${reason.envelope.trace_id})`:'The save result is unconfirmed. Retry with the same content or refresh to view saved records.');if(reason instanceof ApiFailure&&reason.envelope.error.code==='UNAUTHENTICATED')reload();}
    finally{submitting.current=false;setBusy(false);}
  }
  if(data.run&&['PENDING','RUNNING'].includes(data.run.status))return <div className="finalise-panel" role="status"><p>{data.run.operation==='REASSESS'?'Updating check results. Save eligibility will be shown when complete.':'Generating the itinerary and completing checks. Please wait.'}</p><button className="disabled-action" disabled>{data.run.operation==='REASSESS'?'Rechecking…':'Planning…'}</button></div>;
  if(data.version?.status==='FINALISED')return <p>The final plan for this run is saved. View the final record for its complete snapshot.</p>;
  return <div className="finalise-panel">{error&&<p className="error-box" role="alert">{error}</p>}{readError&&<p className="error-box" role="alert">Refresh and review the latest result before confirming save.</p>}{saveAvailable?<form onSubmit={submit}><label className="confirmation-choice"><input type="checkbox" checked={acknowledged} disabled={busy} onChange={event=>setAcknowledged(event.target.checked)}/>I have read the itinerary, costs, equipment and safety evidence and confirm saving this plan.</label><button className="primary-button" disabled={busy||!acknowledged}>{busy?'Saving final plan…':'Save as final plan'}</button>{onModify&&<button type="button" className="secondary-button" disabled={busy} onClick={onModify}>Modify plan and reassess</button>}</form>:<><button className="disabled-action" disabled>This plan cannot be saved yet</button><p className="muted">Address the issues listed above first.</p></>}</div>;
}
