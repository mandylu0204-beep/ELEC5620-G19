import { useEffect,useState } from 'react';
import { Link,useLocation,useNavigate,useParams,useSearchParams } from 'react-router-dom';
import { ApiFailure } from './api';
import { type Profile } from './profile';
import { profileChanges } from './profile_changes';
import { privateApi,useSession } from './session';
import { type SuccessorSource } from './replan_session';
import { forgetDeletedTripUpdate,openTripUpdate,tripUpdatePath } from './trip_update';

export function ProfileAdoptionPreview({before,after,revision,sourceRevision}:{before:Profile;after:Profile;revision:number|null;sourceRevision:number|null}){
  const changes=profileChanges(before,after);
  return <section aria-label="Profile differences"><h3>Profile used for this update revision {revision??'Unknown'}</h3>
    <p>Profile used for original plan revision: {sourceRevision??'Not recorded in history'}.This is a profile comparison only, not a formal check result.</p>
    {changes.length?changes.map(change=><details key={change.section} open><summary>{change.section}Changed</summary><div className="bottom-grid">
      <div><h4>Original plan used</h4><ul>{change.before.map((line,index)=><li key={index}>{line}</li>)}</ul></div>
      <div><h4>Proposed for this update</h4><ul>{change.after.map((line,index)=><li key={index}>{line}</li>)}</ul></div>
    </div></details>):<p>The profile matches the original. Replanning still creates a successor plan and runs formal checks.</p>}
  </section>;
}

export function ReplanFromProfile({source}:{source:SuccessorSource;previousProfile:Profile;refreshSource:()=>void}) {
  return <section className="panel replan-panel" aria-label="Adjust camping plan">
    <h2>Adjust camping plan</h2><p>Change trip requirements or replan with the latest profile.</p>
    <Link className="primary-button" to={tripUpdatePath(source.plan_id)}>Change requirements and profile ↗</Link>
  </section>;
}

export function TripUpdateEntry(){
  const {planId}=useParams();const [search]=useSearchParams();const navigate=useNavigate();const location=useLocation();const {session}=useSession();
  const [error,setError]=useState('');const [retry,setRetry]=useState(0);const [deletedDraft,setDeletedDraft]=useState(false);
  const focus=['request-meal','request-budget'].includes(search.get('focus')??'')?search.get('focus'):null;
  useEffect(()=>{
    if(!session||!planId)return;let cancelled=false;setError('');setDeletedDraft(false);
    const api=<T,>(path:string,body?:unknown)=>privateApi<T>(path,body===undefined?{}:{method:'POST',
      headers:{'Content-Type':'application/json','X-CampMate-Client':'1','X-CSRF-Token':session.csrf_token},body:JSON.stringify(body)});
    // Opening/refreshing prepares an idempotent draft only. No interpret,
    // confirm or model dispatch runs until an explicit action on the next page.
    async function open(){
      try{
        const record=await openTripUpdate(api,window.sessionStorage,session!.user.user_id,planId!,()=>crypto.randomUUID());
        if(!cancelled)navigate('/request/'+encodeURIComponent(record.request_id)+(focus?'?focus='+focus:''),{replace:true,state:{profileSaved:location.state?.profileSaved===true}});
      }catch(reason){if(!cancelled){setDeletedDraft((reason as {deletedUpdateDraft?:boolean})?.deletedUpdateDraft===true);setError(reason instanceof ApiFailure?reason.message:reason instanceof Error?reason.message:'Could not prepare the update. Please try again.');}}
    }
    void open();
    return()=>{cancelled=true;};
  },[planId,session,navigate,focus,retry,location.state?.profileSaved]);
  async function newDraft(){
    if(!session||!planId)return;
    try{await forgetDeletedTripUpdate(<T,>(path:string)=>privateApi<T>(path),window.sessionStorage,session.user.user_id,planId);setRetry(value=>value+1);}
    catch(reason){setError(reason instanceof Error?reason.message:'The source cannot be verified. Return to the current plan.');}
  }
  return <section className="panel"><h1>Review this update</h1><p>Keep the original requirements and prepare an update draft for the same trip. No model or check starts automatically.</p>
    {error?<><p className="error-box" role="alert">{error}</p>{deletedDraft?<><p>The previous update draft may have been deleted. Deleted records are not restored automatically. If the source is still valid, you can explicitly create another update draft.</p><button onClick={newDraft}>Create another update draft</button></>:<button onClick={()=>setRetry(value=>value+1)}>Retry original update command</button>}</>:<p role="status">Loading…</p>}
    <Link className="text-link" to={'/plans/'+encodeURIComponent(planId??'')}>Cancel and return to original plan ↗</Link></section>;
}
