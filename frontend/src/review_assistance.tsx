import {useRef,useState} from 'react';
import {Link} from 'react-router-dom';
import type {PlanDetail} from './plans';
import {privateApi,useSession} from './session';
import {helpCommand} from './requirement_help';
import {tripUpdatePath} from './trip_update';

export type AssistanceNote={note_id:string;plan_id:string;run_id:string;plan_version_id:string;assessment_ids:string[];
 reviewer_user_id:string;decision:'WAITING_EVIDENCE'|'NEEDS_CAMPER_INPUT'|'UNSUPPORTED';problem:string;reason:string;next_action:string;
 recheck_on:string|null;created_at:string;is_approval:false};
const titles={WAITING_EVIDENCE:'Wait for information before rechecking',NEEDS_CAMPER_INPUT:'Information or arrangement changes needed',UNSUPPORTED:'This arrangement is currently unsupported'};
export function AssistanceNotes({notes,historical=false}:{notes:AssistanceNote[];historical?:boolean}){
  if(!notes.length)return null;
  const latest=notes.at(-1)!;
  const content=(note:AssistanceNote)=><><h3>{titles[note.decision]}</h3><dl className="assistance-feedback"><dt>Issue</dt><dd>{note.problem}</dd><dt>Reason</dt><dd>{note.reason}</dd><dt>Next</dt><dd>{note.next_action}</dd></dl>{note.recheck_on&&<p>Suggested recheck date: {note.recheck_on}</p>}</>;
  return <section className="panel human-assistance-notes" aria-label="Human assistance feedback"><p className="muted">{historical?'Human assistance records for an earlier result':'Assistance feedback for this result'} · This is not approval and does not remove assessment issues.</p>{content(latest)}
    {notes.length>1&&<details><summary>Previous feedback ({notes.length-1})</summary>{notes.slice(0,-1).map(note=><article key={note.note_id}>{content(note)}</article>)}</details>}
  </section>;
}

export function ReviewAssistanceForm({data,refresh}:{data:PlanDetail&{assistance_available?:boolean};refresh:()=>void}){
  const {session}=useSession();const [decision,setDecision]=useState<AssistanceNote['decision']>('WAITING_EVIDENCE');
  const [problem,setProblem]=useState('');const [reason,setReason]=useState('');const [action,setAction]=useState('');const [date,setDate]=useState('');
  const [busy,setBusy]=useState(false);const [error,setError]=useState('');const [notice,setNotice]=useState('');const locked=useRef(false);
  if(!data.assistance_available||!data.version||!data.run)return null;
  async function save(){
    if(!session||!data.version||!data.run||locked.current)return;
    const body={version_context:data.version.version_context,assessment_ids:data.assessments.map(item=>item.assessment_id).sort(),
      expected_version_revision:data.version.revision,expected_run_revision:data.run.revision,decision,problem:problem.trim(),reason:reason.trim(),next_action:action.trim(),
      recheck_on:decision==='WAITING_EVIDENCE'&&date?date:null};
    locked.current=true;setBusy(true);setError('');setNotice('');
    try{
      const key=helpCommand(window.sessionStorage,`review-assistance:${session.user.user_id}:${data.run.run_id}`,body);
      await privateApi('/review/'+data.plan.plan_id+'/assistance',{method:'POST',headers:{'Content-Type':'application/json','X-CampMate-Client':'1','X-CSRF-Token':session.csrf_token},body:JSON.stringify({...body,command_key:key})});
      setNotice('Feedback saved. Formal assessments and save eligibility are unchanged.');refresh();
    }catch(value){setError(value instanceof Error?value.message:'Save incomplete. Retry the original action.');}finally{locked.current=false;setBusy(false);}
  }
  return <section className="review-assistance-form" aria-label="Record corrective assistance"><h3>Record assistance (not approval)</h3><p>Explain what is missing, why and the next action. Formal checks are still needed after completion.</p>
    <fieldset disabled={busy}><label htmlFor="assistance-decision">Assistance type</label><select id="assistance-decision" value={decision} onChange={event=>setDecision(event.target.value as AssistanceNote['decision'])}>{Object.entries(titles).map(([value,title])=><option key={value} value={value}>{title}</option>)}</select>
    <label htmlFor="assistance-problem">Specific issue</label><textarea id="assistance-problem" maxLength={2000} value={problem} onChange={event=>setProblem(event.target.value)}/>
    <label htmlFor="assistance-reason">Evidence / reason</label><textarea id="assistance-reason" maxLength={4000} value={reason} onChange={event=>setReason(event.target.value)}/>
    <label htmlFor="assistance-action">Your next step</label><textarea id="assistance-action" maxLength={2000} value={action} onChange={event=>setAction(event.target.value)}/>
    {decision==='WAITING_EVIDENCE'&&<><label htmlFor="assistance-date">Suggested recheck date (optional)</label><input id="assistance-date" type="date" value={date} onChange={event=>setDate(event.target.value)}/></>}
    <button type="button" className="primary-button" disabled={busy||!problem.trim()||!reason.trim()||!action.trim()} onClick={()=>void save()}>{busy?'Saving…':'Save assistance notes'}</button></fieldset>
    {error&&<p className="error-box" role="alert">{error}</p>}{notice&&<p role="status">{notice}</p>}
  </section>;
}

export function AssistanceNextAction({data,onRecheck}:{data:PlanDetail;onRecheck:()=>void}){
  const notes=data.review_assistance_notes??[];
  if(!notes.length||!data.run?.is_active||data.trip_series?.is_current===false)return null;
  const note=notes.at(-1)!;
  return <div className="plan-actions">{note.decision==='WAITING_EVIDENCE'?
    data.reassessment_available&&<button type="button" className="secondary-button" onClick={onRecheck}>View recheck option ↓</button>:
    <Link className="secondary-button" to={tripUpdatePath(data.plan.plan_id)}>Review and adjust this request ↗</Link>}</div>;
}
