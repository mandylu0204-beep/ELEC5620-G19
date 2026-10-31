import {ReviewAssistanceForm} from './review_assistance';
import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { blockerText } from './plan_language';
import { ApiFailure } from './api';
import { aud, campName, PlanView, useSavedRead, type PlanDetail } from './plans';
import { privateApi, useSession } from './session';

const noPoll=()=>false;
export const historicalReviewNotice=(scope?:string)=>scope==='HISTORY'?'This review belongs to an old result superseded by a successor plan. It does not authorise the current plan or its final saving.':null;
const assistanceNames:Record<string,string>={WAITING_EVIDENCE:'Awaiting information',NEEDS_CAMPER_INPUT:'Awaiting user details',UNSUPPORTED:'Currently unsupported'};
const names:Record<string,string>={ESCALATED:'Human judgement needed',BLOCKED:'Blocking conditions exist',REVISION_REQUIRED:'Revision required'};
const labels:Record<string,string>={HIGH:'High',MEDIUM:'Medium',LOW:'Low',UNKNOWN:'Unknown',WEATHER:'Weather',FIRE:'Campfire restrictions',ROAD:'Road',RESTRICTION:'Campsite restrictions',MISSING:'Missing',STALE:'Outdated',CONFLICTING:'Conflict'};
const label=(value:string|null|undefined)=>value?labels[value]??value:'Unknown';
type ReviewRow={last_assistance?:{decision:string;problem:string;next_action:string;recheck_on:string|null}|null;task_kind?:'ASSISTANCE'|'RISK_APPROVAL';plan_id:string;plan_version_id:string;run_id:string;version_number:number;status:string;created_at:string;owner_display_name:string|null;summary?:{campsite_ids:string[];destination:string|null;start_date:string|null;end_date:string|null;total_cents:number|null;budget_difference_cents:number|null;risk_level:string|null;confidence:string|null;data_quality:Record<string,string>;blocking_reasons:{code:string;message:string}[]}};
type ReviewDetail=PlanDetail & {assistance_available?:boolean;owner_display_name?:string|null;review_scope?:'HISTORY'|'APPROVAL'|'CORRECTION'};
type ReviewReply={review:PlanDetail['reviews'][number];status:string};
const DECISIONS=[{value:'APPROVE',title:'Approve',description:'Complete review, then let the camper confirm final saving.'},{value:'REQUEST_REVISION',title:'Request revision',description:'Identify arrangements to change, then reassess.'},{value:'REJECT',title:'Reject',description:'Do not approve this plan. Explain the reason.'}];

function queueIssues(row:ReviewRow) {
  const summary=row.summary;
  if(!summary)return ['Open details to view assessment evidence.'];
  const reasons=summary.blocking_reasons.filter(item=>item.code!=='REVIEW_REQUIRED');
  const specific=reasons.filter(item=>!['VERSION_STATE_BLOCKED','REVISION_REQUIRED'].includes(item.code));
  const quality=Object.entries(summary.data_quality).filter(([,status])=>status!=='AVAILABLE').map(([kind,status])=>`${label(kind)}Evidence${label(status)}`);
  const cost=summary.budget_difference_cents!=null&&summary.budget_difference_cents>0?[`Trip estimate exceeds budget ${aud(summary.budget_difference_cents)}`]:[];
  return [...new Set([...(row.last_assistance?[row.last_assistance.problem]:[]),...specific.map(item=>blockerText(item.code)),...quality,...cost,...reasons.filter(item=>!specific.includes(item)).map(item=>blockerText(item.code))])];
}

export function ReviewQueue(){
  const {data,error,refresh}=useSavedRead<{reviews:ReviewRow[]}>('/review-queue',noPoll);
  const {data:help,error:helpError,refresh:refreshHelp}=useSavedRead<{plans:ReviewRow[]}>('/assistance-queue',noPoll);
  const [filter,setFilter]=useState('judgement');
  const rows=[...(data?.reviews??[]),...(help?.plans??[])];
  const displayed=filter==='judgement'?(data?.reviews??[]):(help?.plans??[]);
  return <div className="review-page"><div className="onboarding-heading"><div><span className="eyebrow">Plan review</span><h1>Give every trip a sound basis.</h1><p>Review assessed plans, verify risks and evidence, then decide.</p></div><button className="secondary-button" onClick={()=>{refresh();refreshHelp();}}>Refresh review queue</button></div>
    {error&&<p className="error-box" role="alert">{error}</p>}
    {helpError&&<p className="error-box" role="alert">{helpError}</p>}
    {data&&<><div className="review-queue-stats"><div><span>Pending plans</span><strong>{rows.length}</strong></div><div><span>Human judgement needed</span><strong>{data.reviews.length}</strong></div><div><span>Issues to address first</span><strong>{help?.plans.length??0}</strong></div></div><div className="review-filters" role="group" aria-label="Filter review queue">{[['judgement','Awaiting risk approval'],['problems','Corrections / assistance (not approvable)'],['history','Processed / history']].map(([value,title])=><button className="secondary-button" key={value} aria-pressed={filter===value} onClick={()=>setFilter(value)}>{title}</button>)}</div></>}
    {filter==='history'?<ReviewHistory/>:!data?<section className="panel"><p>Loading review queue…</p></section>:displayed.length?<div className="review-card-grid">{displayed.map(row=>{const summary=row.summary;const issues=queueIssues(row);return <Link className="panel review-card" key={row.plan_id} to={'/review/'+row.plan_id}><div className="review-card-top"><span className={'review-queue-status '+(row.status==='ESCALATED'?'review-judgement':'review-problem')}>{row.last_assistance?assistanceNames[row.last_assistance.decision]:names[row.status]??row.status}</span><span className="review-version">Version {row.version_number}</span></div><h2>{summary?.campsite_ids.map(campName).join(' / ')||summary?.destination||'Camping plan'}</h2><p className="review-owner">By {row.owner_display_name??'Camper'} Submit</p><p className="review-dates">{summary?.start_date??'Dates unknown'} — {summary?.end_date??'Dates unknown'}</p><div className="review-card-facts"><span>Estimated trip cost<strong>{aud(summary?.total_cents)}</strong></span><span>Risk / Confidence<strong>{label(summary?.risk_level)} / {label(summary?.confidence)}</strong></span></div>{issues.length?<div className="review-card-issues"><strong>Issues requiring action</strong><ul>{issues.slice(0,3).map(message=><li key={message}>{message}</li>)}</ul>{issues.length>3&&<small>Another {issues.length-3}  items; open details to view.</small>}</div>:<p className="review-card-note">Review risks and assessment evidence before deciding.</p>}<span className="review-card-action">{row.task_kind==='ASSISTANCE'?'View issues (not approvable)':'View evidence and review'} <span aria-hidden="true">↗</span></span></Link>;})}</div>:<section className="panel review-queue-empty"><span aria-hidden="true">✓</span><h2>{rows.length?'No plans in this category':'No plans awaiting review'}</h2><p>{rows.length?'Switch to another category.':'Completed review decisions remain in plan records.'}</p></section>}
  </div>;
}

export function ReviewPage(){
  const {planId}=useParams(); const [search]=useSearchParams();const {session,reload}=useSession();
  const {data,error,refresh}=useSavedRead<ReviewDetail>('/review/'+planId+(search.get('run_id')?'?run_id='+encodeURIComponent(search.get('run_id')!):''),noPoll);
  const [reason,setReason]=useState('');const [decision,setDecision]=useState('');
  const [busy,setBusy]=useState(false);const [fault,setFault]=useState('');const [faultTrace,setFaultTrace]=useState('');
  const [receipt,setReceipt]=useState<{planId:string;scope:string;reply:ReviewReply}|null>(null);
  const pending=useRef<{key:string;payload:string}|null>(null);const submitting=useRef(false);const previousScope=useRef('');
  const scope=data?.version?[data.version.version_context.run_id,data.version.version_context.input_fingerprint,...data.assessments.map(item=>item.assessment_id).sort()].join('/') : '';
  useEffect(()=>{if(scope&&scope!==previousScope.current){previousScope.current=scope;setReason('');setDecision('');setFault('');setFaultTrace('');setReceipt(null);pending.current=null;}},[scope]);
  const approvalReasons=data?.eligibility?.blocking_reasons.filter(item=>item.code!=='REVIEW_REQUIRED')??[];
  const approvalBlocked=!data?.eligibility||approvalReasons.length>0||!!data.current_inputs_error;
  const savedReview=data?.reviews.at(-1)??(receipt&&receipt.planId===planId&&receipt.scope===(scope||previousScope.current)?receipt.reply.review:null);
  async function submit(event:FormEvent){
    event.preventDefault();if(!data?.version||!data.run||!session||submitting.current||scope!==previousScope.current||!data.review_available||savedReview||!decision||!reason.trim()||(decision==='APPROVE'&&approvalBlocked))return;
    const input={version_context:data.version.version_context,assessment_ids:data.assessments.map(item=>item.assessment_id).sort(),expected_version_revision:data.version.revision,expected_run_revision:data.run.revision,decision,reason:reason.trim()};
    const payload=JSON.stringify(input);
    if(pending.current?.payload!==payload)pending.current={key:crypto.randomUUID(),payload};
    submitting.current=true;setBusy(true);setFault('');setFaultTrace('');
    try{const reply=await privateApi<ReviewReply>('/review/'+planId,{method:'POST',headers:{'Content-Type':'application/json','X-CampMate-Client':'1','X-CSRF-Token':session.csrf_token},body:JSON.stringify({...input,command_key:pending.current!.key})});setReceipt({planId:planId!,scope,reply});refresh();}
    catch(value){setFault(value instanceof ApiFailure?value.message:'Connection failed. Retry with the same content.');setFaultTrace(value instanceof ApiFailure?value.envelope.trace_id:'');if(value instanceof ApiFailure&&value.envelope.error.code==='UNAUTHENTICATED')reload();}
    finally{submitting.current=false;setBusy(false);}
  }
  const submitHint=busy?'Saving review…':decision==='APPROVE'&&approvalBlocked?'Approval cannot remove the current issues. Address them first.':!decision?'Select a review decision.':!reason.trim()?'Enter a specific reason to help the camper understand your decision.':'Review the decision and reason, then save.';
  const outcomeTitle=savedReview?.decision==='APPROVE'?'Plan approved':savedReview?.decision==='REQUEST_REVISION'?'Revision requested':'Review rejected';
  const outcomeHint=historicalReviewNotice(data?.review_scope)??(savedReview?.decision==='APPROVE'?(data?.version?.status==='FINALISED'?'The camper saved the final plan.':data?.current_inputs_error||data?.eligibility?.eligible===false?'Assessments or evidence changed. Reassess before continuing.':'Review saved. The camper must still review and save the final plan.'):savedReview?.decision==='REQUEST_REVISION'?'The camper must revise based on the reason and reassess. Changes to dates, group size or budget require request reconfirmation.':'The camper can adjust arrangements based on the reason. Changed requirements need reconfirmation.' );
  const actions=<section className="panel review-decision-panel" id="review-decision-panel"><div className="section-title"><span className="eyebrow">This review</span><h2>{savedReview?'Review outcome':'Submit review decision'}</h2></div>
    {fault&&<div className="error-box" role="alert"><p>{fault}</p>{faultTrace&&<details><summary>Error details</summary><p className="identifier">Trace ID: {faultTrace}</p></details>}<button type="button" onClick={refresh}>Refresh assessment evidence</button></div>}
    {savedReview?<div className={'review-result '+(savedReview.decision==='APPROVE'?'review-result-approved':'review-result-change')} role="status"><h3>{outcomeTitle}</h3><p>{outcomeHint}</p><blockquote>{savedReview.reason}</blockquote></div>:data?.review_available?<>
      {approvalBlocked&&<div className="review-approval-warning" id="review-approval-hint"><h3>Approval unavailable</h3><p>Address the following issues first, or request revision or reject.</p><ul>{approvalReasons.length?approvalReasons.map((item,index)=><li key={index}>{blockerText(item.code)}</li>):<li>{data.current_inputs_error??'Assessment information needed for review is incomplete.'}</li>}</ul><details><summary>View original condition records</summary>{approvalReasons.map((item,index)=><p key={index}>{item.code} · {item.message}</p>)}</details></div>}
      <form onSubmit={submit}><fieldset disabled={busy}><legend>Review decision</legend><div className="review-decision-choices">{DECISIONS.map(item=><label className={'review-choice '+(decision===item.value?'review-choice-selected':'')} key={item.value}><input type="radio" name="review-decision" aria-label={item.title} value={item.value} checked={decision===item.value} disabled={item.value==='APPROVE'&&approvalBlocked} aria-describedby={item.value==='APPROVE'&&approvalBlocked?'review-approval-hint':undefined} onChange={()=>setDecision(item.value)}/><span><strong>{item.title}</strong><small>{item.description}</small></span></label>)}</div><label htmlFor="review-reason">Review reason <span className="required-mark">Required</span></label><textarea id="review-reason" value={reason} maxLength={4000} required onChange={e=>setReason(e.target.value)} placeholder="Explain which risks you checked and which arrangements should be kept or changed."/><div className="review-submit-row"><p id="review-submit-hint" className="action-hint" role="status">{submitHint}</p><button className="primary-button" disabled={busy||!decision||!reason.trim()||(decision==='APPROVE'&&approvalBlocked)} aria-describedby="review-submit-hint">{busy?'Saving…':'Save review decision'} <span>✓</span></button></div></fieldset></form>
    </>:<div className="review-unavailable"><h3>This plan cannot be reviewed yet</h3><p>{data?.current_inputs_error??(data?.review_scope==='CORRECTION'?'This is a correction / assistance task, not an approval task. The user must complete details or change arrangements and run new checks. Approval cannot remove hard gaps.':data?.review_scope==='HISTORY'?'A successor plan exists for this trip. The old review task is superseded and retained as history only.':'The current run or assessments changed. Refresh and review.')}</p></div>}
    {data&&<ReviewAssistanceForm key={data.run?.run_id} data={data} refresh={refresh}/>}
  </section>;
  return <div className="review-page">{data?<><div className="review-context-bar"><span><strong>Human review</strong> · By {data.owner_display_name??'Camper'} Submit</span>{!savedReview&&data.review_available&&<button className="secondary-button" onClick={()=>{document.getElementById('review-decision-panel')?.scrollIntoView({block:'start'});document.querySelector<HTMLInputElement>('.review-choice input:not(:disabled)')?.focus();}}>Go to review decision ↓</button>}</div><PlanView data={data} error={error} refresh={refresh} review reviewActions={actions}/></>:<section className="panel"><h1>{receipt?.planId===planId?'Review saved; updating records':'Read review evidence'}</h1>{error&&<p className="error-box" role="alert">{error}</p>}<button className="secondary-button" onClick={refresh}>Reload</button><Link className="text-link" to="/review">Back to review queue ↗</Link></section>}</div>;
}


type HistoryRow={review_id:string;plan_id:string;run_id:string;version_number:number;decision:string;reason:string;is_current_result:boolean;owner_display_name:string;destination:string|null;start_date:string|null;created_at:string};
export function ReviewHistory(){
  const [decision,setDecision]=useState('');const [offset,setOffset]=useState(0);
  const path='/review-history?limit=30&offset='+offset+(decision?'&decision='+decision:'');
  const {data,error,refresh}=useSavedRead<{reviews:HistoryRow[];total:number;offset:number;limit:number}>(path,noPoll);
  const names:Record<string,string>={APPROVE:'Approved',REJECT:'Rejected',REQUEST_REVISION:'Request revision'};
  return <section className="panel" aria-label="Completed review history"><h2>Processed / historical reviews</h2><p>Retains the decision and reason at that time. Historical approval does not authorise current or successor plans.</p>
    <label htmlFor="review-history-decision">Filter by decision</label><select id="review-history-decision" value={decision} onChange={event=>{setDecision(event.target.value);setOffset(0);}}><option value="">All decisions</option>{Object.entries(names).map(([value,title])=><option key={value} value={value}>{title}</option>)}</select>
    {error&&<p className="error-box" role="alert">{error}</p>}{!data?<p>Loading…</p>:<>{data.reviews.map(row=><article className="review-history-row" key={row.review_id}><h3>{names[row.decision]} · Version {row.version_number}</h3><p>{row.owner_display_name} · {row.destination} · {row.start_date}</p><p>{row.is_current_result?'Record for current result':'Previous result, superseded'}</p><blockquote>{row.reason}</blockquote><Link className="text-link" to={'/review/'+row.plan_id+'?run_id='+encodeURIComponent(row.run_id)}>View original review evidence ↗</Link></article>)}{!data.reviews.length&&<p>No review records of this type.</p>}
    <div className="plan-actions"><button type="button" className="secondary-button" disabled={!offset} onClick={()=>setOffset(value=>Math.max(0,value-30))}>Previous page</button><span>Total {data.total} entries</span><button type="button" className="secondary-button" disabled={offset+data.reviews.length>=data.total} onClick={()=>setOffset(value=>value+30)}>Next page</button><button type="button" className="text-button" onClick={refresh}>Refresh history</button></div></>}
  </section>;
}
