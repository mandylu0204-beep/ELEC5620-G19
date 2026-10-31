import {englishRequestMessage} from './legacy_request_messages';
import {dateFieldError,endDateMinimum,firstFutureDate} from './calendar_dates';
import {RequirementChoices,type RequirementCatalogue} from './requirement_choices';
import {RequirementHelpPanel,type RequirementHelpState} from './requirement_help';
import { DiscardChanges } from './display_panels';
import { changedSections } from './display_facts';
import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Link, useLocation, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { ApiFailure, type PreviewResult, type Requirements } from './api';
import { integer, lines, ProfileSummary, PublicTransportNotice, SystemPreparationNotice, type Profile } from './profile';
import { CookingPreparationPanel, canHideCookingPreparation, type CookingPreparation } from './cooking_preparation';
import { privateApi, useSession } from './session';
import { TripFlow, FieldHint } from './trip_flow';
import { canonicalTerms, termLabel } from './user_terms';
import { ProfileAdoptionPreview } from './replan';
import { ReplanSession } from './replan_session';
import { tripCommandKey,tripUpdatePath } from './trip_update';

type RequestContext = { requirement_choices?:RequirementCatalogue; system_preparation?:boolean; supported_destinations: string[]; execution_mode: string; demo_today: string; planning_available: boolean };
type Record = { summary_origin?:'STRUCTURED_FORM'|'MODEL_INTERPRETATION'|'LEGACY'; requirement_help?:RequirementHelpState|null; system_preparation?:boolean|null; request_id: string; raw_text: string; explicit_fields: Partial<Requirements>; status: string; revision: number; created_at: string; summary: PreviewResult | null; profile_snapshot: Profile | null; profile_revision: number | null; error: { message:string } | null; confirmed_context: { requirements: Requirements; profile_snapshot: Profile; confirmed_at: string; demo_context: { mode:string } } | null; planning_available:boolean; planning_plan_id?:string|null };
type UpdateRecord = Record & {trip_series_id?:string;predecessor_plan_id?:string|null;source_profile_revision?:number|null;source_profile_snapshot?:Profile;source_requirements?:Requirements;is_trip_update?:boolean;cooking_preparation?:CookingPreparation|null};
type Draft = { raw: string; destination: string; start: string; nights: string; days: string; end: string; budget: string; preferences: string; constraints: string };
const EMPTY: Draft = {raw:'',destination:'',start:'',nights:'',days:'',end:'',budget:'',preferences:'',constraints:''};
const STATUS: {[key:string]:string} = {DRAFT:'Draft',ANALYSING:'Generating summary',NEEDS_CLARIFICATION:'Clarification required',UNSUPPORTED:'Region not supported yet',AWAITING_CONFIRMATION:'Awaiting your confirmation',CONFIRMED:'Request confirmed'};

export function requestDraftFromRecord(record: Record): Draft {
  const value = record.explicit_fields;
  return { raw:record.raw_text, destination:value.destination ?? '', start:value.start_date ?? '', nights:String(value.duration_nights ?? ''), days:String(record.explicit_fields.duration_days ?? ''), end:record.explicit_fields.end_date ?? '', budget:value.budget_cents === null || value.budget_cents === undefined ? '' : (value.budget_cents / 100).toFixed(2), preferences:(value.preferences ?? []).join('\n'), constraints:(value.mandatory_constraints ?? []).join('\n') };
}

export function requestPayload(draft: Draft,minimumStart?:string) {
  if(minimumStart){
    const error=dateFieldError(draft.start,minimumStart);if(error)throw new Error(error);
    const endError=dateFieldError(draft.end,endDateMinimum(draft.start,minimumStart));if(endError)throw new Error(endError);
  }
  let budget_cents: number | null = null;
  if (draft.budget !== '') {
    if (!/^\d+([.]\d{1,2})?$/.test(draft.budget)) throw new Error('Enter the budget with at most two decimal places in AUD.');
    const [whole,fraction=''] = draft.budget.split('.');
    budget_cents = Number(whole) * 100 + Number(fraction.padEnd(2,'0'));
    if (!Number.isSafeInteger(budget_cents)) throw new Error('Budget amount is too large. Please revise it.');
  }
  // Free-text fields are evidence for the interpreter. Translating labels or
  // replacing phrases here loses wording, negation and the soft/hard boundary.
  return { ...(draft.raw?{raw_text:draft.raw}:{}), explicit_fields:{destination:draft.destination.trim() || null, start_date:draft.start || null, duration_nights:integer(draft.nights), duration_days:integer(draft.days), end_date:draft.end || null, budget_cents, preferences:lines(draft.preferences), mandatory_constraints:lines(draft.constraints)} };
}

export function requestMealPreferences(preferences:string,selected:string):string {
  const original=lines(preferences);
  const remaining=original.filter(item=>!['ready-to-eat meals','ready_to_eat','self-catered meals','self_catered'].includes(canonicalTerms([item],'preference')[0]));
  return [...remaining,...(selected?[termLabel(selected,'preference')]:[])].join('\n');
}

export function RequestFields({draft,set,regions,disabled,catalogue,minimumStart=firstFutureDate()}:{minimumStart?:string;catalogue?:RequirementCatalogue;draft:Draft;set:(patch:Partial<Draft>)=>void;regions:string[];disabled:boolean}) {
  const nights=Number(draft.nights);
  const preferences=canonicalTerms(lines(draft.preferences),'preference');
  const ready=preferences.some(value=>['ready-to-eat meals','ready_to_eat'].includes(value));
  const cooked=preferences.some(value=>['self-catered meals','self_catered'].includes(value));
  const meal=ready!==cooked?(ready?'ready-to-eat meals':'self-catered meals'):'';
  function selectMeal(value:string) {
    set({preferences:requestMealPreferences(draft.preferences,value)});
  }
  return <fieldset disabled={disabled}>
    {draft.raw.trim()&&<details className="source-details legacy-request-source"><summary>View legacy request text</summary><p>This legacy request still generates its summary from the original text and form. New requests use structured fields. Updates from existing plans retain confirmed conditions without reintroducing the old original text.</p><blockquote>{draft.raw}</blockquote></details>}
    <section className="request-form-section"><div className="form-section-heading"><span>01</span><h3>Destination and itinerary</h3></div><div className="form-grid">
      <div><label htmlFor="request-destination">Destination</label><input id="request-destination" list="supported-destinations" value={draft.destination} onChange={event=>set({destination:event.target.value})}/><datalist id="supported-destinations">{regions.map(region=><option key={region} value={region}/>)}</datalist></div>
      <div><label htmlFor="request-start">Start date</label><input id="request-start" type="date" min={minimumStart} value={draft.start} onChange={event=>set({start:event.target.value})}/></div>
      <div><label htmlFor="request-nights">Number of nights</label><input id="request-nights" type="number" min="1" step="1" value={draft.nights} aria-describedby="nights-hint" onChange={event=>set({nights:event.target.value})}/><FieldHint id="nights-hint">{draft.nights&&Number.isSafeInteger(nights)&&nights>0&&nights<Number.MAX_SAFE_INTEGER?`${nights} nights correspond to ${nights+1} days.`:'For example, two nights span three days.'}</FieldHint></div>
      <div><label htmlFor="request-budget">Budget for the whole group AUD</label><input id="request-budget" inputMode="decimal" pattern="[0-9]+([.][0-9]{1,2})?" placeholder="For example 320.00" value={draft.budget} aria-describedby="budget-hint" onChange={event=>set({budget:event.target.value})}/><FieldHint id="budget-hint">Enter the total budget for the entire trip.</FieldHint></div>
    </div><details className="optional-fields"><summary>Already know the duration or end date? Add it here</summary><div className="form-grid"><div><label htmlFor="request-days">Explicit number of days</label><input id="request-days" type="number" min="1" step="1" value={draft.days} onChange={event=>set({days:event.target.value})}/></div><div><label htmlFor="request-end">Explicit end date</label><input id="request-end" type="date" min={endDateMinimum(draft.start,minimumStart)} value={draft.end} onChange={event=>set({end:event.target.value})}/></div></div><p className="field-hint">If this conflicts with the number of nights, review the summary guidance.</p></details></section>
    <section className="request-form-section"><div className="form-section-heading"><span>02</span><h3>Preferences and required conditions</h3></div><label htmlFor="request-meal">Meal arrangement</label><select id="request-meal" value={meal} onChange={event=>selectMeal(event.target.value)} aria-describedby="meal-hint"><option value="">Select meal arrangement</option><option value="ready-to-eat meals">Ready-to-eat meals (no cooking)</option><option value="self-catered meals">Self-catering (verify stove and fuel)</option></select><FieldHint id="meal-hint">Used to calculate food costs and cooking equipment. Select before confirming the request.</FieldHint><div className="requirements-sections"><RequirementChoices id="request-preferences" title="Camping preferences" value={draft.preferences} choices={catalogue?.fields.preferences??null} preserved={['ready-to-eat meals','self-catered meals','ready_to_eat','self_catered','Ready-to-eat meals','Self-catered meals','Ready-to-eat food','Meals requiring no cooking','Cook own meals']} onChange={value=>set({preferences:value})} hint="Select any that apply. Preferences help compare suitability. Missing information will be identified; not all preferences are guaranteed."/><RequirementChoices id="request-constraints" title="Required conditions" value={draft.constraints} choices={catalogue?.fields.mandatory_constraints??null} onChange={value=>set({constraints:value})} hint="Select any that apply. Required conditions are strict filters. If no campsite matches, you decide whether to adjust them."/></div></section>
  </fieldset>;
}

const FIELD_IDS: {[field:string]:string} = {destination:'request-destination',start_date:'request-start',duration_nights:'request-nights',duration_days:'request-days',end_date:'request-end',budget_cents:'request-budget',preferences:'request-preferences',meal_mode:'request-meal',mandatory_constraints:'request-constraints'};
const FIELD_TITLES: {[field:string]:string} = {raw_text:'Legacy request text',destination:'Destination',start_date:'Start date',duration_nights:'Number of nights',duration_days:'Trip duration in days',end_date:'End date',budget_cents:'Group budget',preferences:'Preferences',meal_mode:'Meal arrangement',mandatory_constraints:'Required conditions','profile.group_size':'Group size'};
export function requestFieldRoot(field:string):string {
  return field.match(/^(raw_text|preferences|mandatory_constraints)(?:\.|\[|$)/)?.[1]??field;
}
export function requestClarificationField(field:string,message:string):string {
  const base=requestFieldRoot(field);
  const mealQuestions=[
    'Choose ready-to-eat meals or self-catered meals before confirming the request.',
    'Choose one confirmed meal mode.',
    'Choose a meal arrangement: ready-to-eat or self-catered meals.',
    'Both ready-to-eat and self-catered meals were selected. Choose one arrangement for this trip.',
  ];
  return base==='preferences'&&mealQuestions.includes(englishRequestMessage(message))?'meal_mode':base;
}

export function RequestMeaningSummary({requirements,pendingConstraints=false}:{requirements:Requirements;pendingConstraints?:boolean}) {
  return <section className="request-meaning-summary" aria-label="Interpreted requirements">
    <div className="summary-preferences"><h3>Preferences</h3>{requirements.preferences?.length>0?<ul>{requirements.preferences.map((item,index)=><li key={index}>{termLabel(item,'preference')}</li>)}</ul>:<p>No additional preferences specified.</p>}</div>
    <div className="summary-preferences"><h3>Required conditions</h3>{requirements.mandatory_constraints?.length>0?<ul>{requirements.mandatory_constraints.map((item,index)=><li key={index}>{termLabel(item,'constraint')}</li>)}</ul>:<p>{pendingConstraints?'Some required conditions need review. See the notice above.':'No additional required conditions specified.'}</p>}</div>
  </section>;
}
export function RequirementsChangePreview({before,after}:{before:Requirements;after:Requirements}){
  const fields=['destination','start_date','duration_nights','end_date','budget_cents','preferences','mandatory_constraints'] as const;
  const changed=fields.filter(key=>JSON.stringify(before[key])!==JSON.stringify(after[key]));
  const text=(key:typeof fields[number],value:unknown)=>Array.isArray(value)?value.map(item=>termLabel(item,key==='preferences'?'preference':'constraint')).join(', ')||'None'
    :key==='budget_cents'&&typeof value==='number'?`AUD ${(value/100).toFixed(2)}`:value==null?'Unknown':String(value);
  return <section aria-label="Requirement changes"><h3>Requirement changes</h3>{changed.length?<ul>{changed.map(key=><li key={key}>{FIELD_TITLES[key]}: {text(key,before[key])} → {text(key,after[key])}</li>)}</ul>:<p>Destination, dates, budget and preferences match the original plan.</p>}<p>These are the proposed requirements, not a formal check result.</p></section>;
}
export function clarificationText(field:string,message:string,requirements:Requirements|undefined) {
  message=englishRequestMessage(message);
  const pastDate=message.match(/^Start date must be on or after the checking date \((\d{4}-\d{2}-\d{2}), Australia\/Sydney\)\.$/);
  if(pastDate)return `The start date cannot be earlier than this check date (${pastDate[1]}, Sydney time). Adjust it and regenerate the summary.`;
  if(message==='Start date precedes the fixed demonstration date.')return 'The start date is earlier than the date used for the previous check. Regenerate the summary to verify the current date.';
  if(['What start date?','Which synthetic region?','How many nights?','What total AUD group budget?','Required request information is missing.'].includes(message))
    return `Please provide ${FIELD_TITLES[field]??'this information'}.`;
  if(message==='Choose ready-to-eat meals or self-catered meals before confirming the request.'||message==='Choose one confirmed meal mode.')return 'Select ready-to-eat meals or self-catering, then regenerate the summary.';
  if(message==='Only registered synthetic regions are supported.')return 'Current data does not cover this region. Check the destination.';
  const unsupported=message.match(/^Unsupported hard constraint:\s*(.*?)\.?$/);
  if(unsupported)return `Cannot verify required condition: ${unsupported[1]}. Specify the facilities you need, or move nonessential requirements to preferences, then generate the summary.`;
  if(field==='duration_days'&&(message===`Please clarify ${field}.`||message==='Days must equal nights plus one.')&&requirements?.duration_nights!=null&&requirements.duration_days!=null&&requirements.duration_days!==requirements.duration_nights+1)
    return `${requirements.duration_nights} nights correspond to ${requirements.duration_nights+1} days; currently entered: ${requirements.duration_days} days. Please check.`;
  return message===`Please clarify ${field}.`?`Please check ${FIELD_TITLES[field]??'this information'}.`:message;
}
function focusRequestField(field:string) {
  const node=document.getElementById(FIELD_IDS[field]);
  const details=node?.closest('details');if(details)details.open=true;
  node?.focus();node?.scrollIntoView({block:'center'});
}
function requestFailure(reason:unknown,fallback:string) {
  return reason instanceof ApiFailure?[reason.message,...reason.envelope.error.field_errors.map(item=>item.message)].filter((value,index,all)=>all.indexOf(value)===index).join(' '):reason instanceof Error?reason.message:fallback;
}

function useRequestContext() {
  const [context,setContext] = useState<RequestContext|null>(null);
  const [error,setError] = useState('');
  useEffect(()=>{ const controller=new AbortController(); privateApi<RequestContext>('/request-context',{signal:controller.signal}).then(value=>{if(!controller.signal.aborted)setContext(value);}).catch(reason=>{if(!controller.signal.aborted)setError(reason instanceof ApiFailure?reason.message:'Could not read region information. Reopen the page.');}); return()=>controller.abort(); },[]);
  return {context,error};
}

export function requestHistoryTitle(row:Pick<Record,'raw_text'> & {explicit_fields?:Partial<Requirements>}){
  if(row.raw_text.trim())return row.raw_text.slice(0,85);
  const fields=row.explicit_fields;
  return [fields?.destination,fields?.start_date,fields?.duration_nights?`${fields.duration_nights} nights`:null].filter(Boolean).join(' · ')||'Camping requests to complete';
}

export function RequestHistory({rows,deleting,selected,onSelect,onDelete,onCancel}:{rows:UpdateRecord[]|null;deleting:string|null;selected:string|null;onSelect:(id:string)=>void;onDelete:(id:string)=>void;onCancel:()=>void}){
  return <details className="panel request-history"><summary>Saved requests ({rows?.length??'…'})</summary>
    {rows===null?<p>Loading…</p>:rows.length===0?<p>No records yet.</p>:<ul className="request-list">{rows.map(row=><li key={row.request_id}>
      <Link to={'/request/'+row.request_id}><strong>{requestHistoryTitle(row)}</strong><span className="tag">{row.trip_series_id?'Update this trip · ':''}{STATUS[row.status]??row.status}</span></Link>
      {selected===row.request_id?<div className="plan-delete-confirm" role="group" aria-label="Confirm request deletion"><p>Delete this request record? Existing plans and immutable confirmation snapshots are retained.</p><button disabled={deleting!==null} onClick={()=>onDelete(row.request_id)}>Confirm deletion</button><button disabled={deleting!==null} onClick={onCancel}>Cancel</button></div>
        :<button className="text-button" disabled={deleting!==null||row.status==='ANALYSING'} onClick={()=>onSelect(row.request_id)}>Delete request record</button>}
    </li>)}</ul>}
  </details>;
}

export function RequestsPage() {
  const {session,reload}=useSession(); const navigate=useNavigate(); const {context,error:contextError}=useRequestContext();
  const [search,setSearch]=useSearchParams(); const copyFrom=search.get('copy_from');
  const [confirmDelete,setConfirmDelete]=useState<string|null>(null);
  const [deleting,setDeleting]=useState<string|null>(null);
  const [deleteError,setDeleteError]=useState('');
  async function deleteRequest(requestId:string){
    if(!session||deleting)return;
    setDeleting(requestId);setDeleteError('');
    try{
      await privateApi<void>('/requests/'+encodeURIComponent(requestId),{method:'DELETE',headers:{'X-CampMate-Client':'1','X-CSRF-Token':session.csrf_token}});
      setRows(value=>value?.filter(row=>row.request_id!==requestId)??null);setConfirmDelete(null);
    }catch(reason){setDeleteError(requestFailure(reason,'Deletion failed. Please retry.'));if(reason instanceof ApiFailure&&reason.envelope.error.code==='UNAUTHENTICATED')reload();}
    finally{setDeleting(null);}
  }

  const [copyLoading,setCopyLoading]=useState(!!copyFrom); const [copyFailed,setCopyFailed]=useState(false); const [copyNotice,setCopyNotice]=useState('');
  const [draft,setDraft]=useState<Draft>(EMPTY); const [rows,setRows]=useState<Record[]|null>(null); const [error,setError]=useState(''); const [busy,setBusy]=useState(false);
  useEffect(()=>{
    const controller=new AbortController(); setCopyNotice('');setCopyFailed(false);setCopyLoading(!!copyFrom);setError('');setDraft(EMPTY);
    if(copyFrom) privateApi<Record>('/requests/'+encodeURIComponent(copyFrom),{signal:controller.signal}).then(record=>{
      if(controller.signal.aborted)return;
      const fields=record.confirmed_context?.requirements??record.explicit_fields;
      // Derived end/day fields stay blank so changing the start or nights does
      // not accidentally retain a constraint from the old confirmed trip.
      setDraft({...requestDraftFromRecord({...record,explicit_fields:fields}),days:'',end:''});
      setCopyNotice('Original request loaded. Edit and reconfirm it.');
    }).catch(reason=>{if(!controller.signal.aborted){setCopyFailed(true);setError(reason instanceof ApiFailure?reason.message:'Could not load the original request. Retry or start a blank request.');if(reason instanceof ApiFailure&&reason.envelope.error.code==='UNAUTHENTICATED')reload();}}).finally(()=>{if(!controller.signal.aborted)setCopyLoading(false);});
    return()=>controller.abort();
  },[copyFrom,reload]);
  useEffect(()=>{const controller=new AbortController(); privateApi<{requests:Record[]}>('/requests',{signal:controller.signal}).then(value=>{if(!controller.signal.aborted)setRows(value.requests);}).catch(reason=>{if(!controller.signal.aborted)setError(reason instanceof ApiFailure?reason.message:'Could not read the saved request.');}); return()=>controller.abort();},[]);
  useEffect(()=>{
    if(!copyLoading&&!copyFailed&&['request-meal','request-budget'].includes(search.get('focus')??''))focusRequestField(search.get('focus')==='request-meal'?'meal_mode':'budget_cents');
  },[copyLoading,copyFailed,search]);
  async function create(event:FormEvent) {
    event.preventDefault(); if(!session||busy||copyLoading||copyFailed)return; setBusy(true);setError('');
    try {const record=await privateApi<Record>('/requests',{method:'POST',headers:{'Content-Type':'application/json','X-CampMate-Client':'1','X-CSRF-Token':session.csrf_token},body:JSON.stringify(requestPayload(draft,firstFutureDate(context?.demo_today)))});navigate('/request/'+record.request_id);}
    catch(reason){setError(requestFailure(reason,'Save failed.'));if(reason instanceof ApiFailure&&reason.envelope.error.code==='UNAUTHENTICATED')reload();}finally{setBusy(false);}
  }
  const createHint=copyLoading?'Loading original requirements…':copyFailed?'The original request could not be loaded. Start a blank request or reopen the original record.':busy?'Saving draft…':'Save the draft first, then generate a summary and review the requirements.';
  return <div className="onboarding-page"><TripFlow step={2}/><div className="onboarding-heading"><div><span className="eyebrow">Camping requirements</span><h1>Tell us about your ideal camping trip.</h1><p>Review your arrangements, then start planning.</p></div><Link className="text-link" to="/profile">View camping profile ↗</Link></div>
    {(error||contextError)&&<p className="error-box" role="alert">{error||contextError}</p>}{copyNotice&&<p className="success-box" role="status">{copyNotice}</p>}{copyLoading&&<p role="status">Loading original requirements…</p>}{copyFrom&&<button className="secondary-button" disabled={busy} onClick={()=>setSearch({})}>Start blank request</button>}
    <div className="request-layout"><section className="panel request-editor"><div className="section-title"><span className="eyebrow">Plan your next trip</span><h2>New camping request</h2></div><form onSubmit={create}><RequestFields minimumStart={firstFutureDate(context?.demo_today)} draft={draft} set={patch=>setDraft(value=>({...value,...patch}))} regions={context?.supported_destinations??[]} catalogue={context?.requirement_choices} disabled={busy||copyLoading||copyFailed}/><div className="request-action"><p id="create-hint" className="action-hint" role="status">{createHint}</p><button className="primary-button" disabled={busy||copyLoading||copyFailed} aria-describedby="create-hint">{busy?'Saving…':'Save draft and continue'} <span>↗</span></button></div></form></section>
    <aside className="request-sidebar"><section className="panel request-guide"><span className="eyebrow">Before you begin</span><h2>A clear plan</h2><ul><li>Group size and equipment come from your saved camping profile.</li><li>Leave uncertain information blank. The summary will identify missing details.</li><li>Confirm the summary before generating an itinerary and assessments.</li></ul><Link className="text-link" to="/profile">Complete your camping profile ↗</Link></section>{deleteError&&<p className="error-box" role="alert">{deleteError}</p>}<RequestHistory rows={rows} deleting={deleting} selected={confirmDelete} onSelect={id=>{setConfirmDelete(id);setDeleteError('');}} onDelete={id=>void deleteRequest(id)} onCancel={()=>setConfirmDelete(null)}/></aside></div>
  </div>;
}

export function RequestDetail() {
  const {requestId}=useParams(); const navigate=useNavigate(); const location=useLocation(); const [search]=useSearchParams(); const {session,reload}=useSession(); const {context,error:contextError}=useRequestContext();
  const [record,setRecord]=useState<UpdateRecord|null>(null); const [draft,setDraft]=useState<Draft>(EMPTY); const [acknowledged,setAcknowledged]=useState(false); const [busy,setBusy]=useState(false); const [error,setError]=useState(''); const [notice,setNotice]=useState(''); const [refresh,setRefresh]=useState(0);
  const updateFlow=useRef<ReplanSession|null>(null);const [updateStale,setUpdateStale]=useState(false);
  const unsavedSections=changedSections(record?requestDraftFromRecord(record):null,draft,{raw:'Legacy request text',destination:'Destination',start:'Start date',nights:'Number of nights',days:'Trip duration in days',end:'End date',budget:'Group budget',preferences:'Preferences and meals',constraints:'Required conditions'});
  const dirty=unsavedSections.length>0;
  const command=useRef<{revision:number;key:string}|null>(null);
  const planningCommand=useRef<{requestId:string;revision:number;key:string}|null>(null);
  function apply(value:UpdateRecord){setRecord(value);setDraft(requestDraftFromRecord(value));setAcknowledged(false);}
  useEffect(()=>{const controller=new AbortController();setRecord(null);setError('');setNotice('');updateFlow.current=null;setUpdateStale(false);privateApi<UpdateRecord>('/requests/'+requestId,{signal:controller.signal}).then(value=>{if(!controller.signal.aborted)apply(value);}).catch(reason=>{if(!controller.signal.aborted)setError(reason instanceof ApiFailure?reason.message:'Could not read the request.');});return()=>controller.abort();},[requestId,refresh]);
  useEffect(()=>{if(record&&['request-meal','request-budget'].includes(search.get('focus')??''))focusRequestField(search.get('focus')==='request-meal'?'meal_mode':'budget_cents');},[record?.request_id,search]);
  function change(patch:Partial<Draft>){setDraft(value=>({...value,...patch}));setAcknowledged(false);setError('');setNotice('');}
  function headers(){return {'Content-Type':'application/json','X-CampMate-Client':'1','X-CSRF-Token':session?.csrf_token??''};}
  async function saveAndAnalyse(event:FormEvent) {
    event.preventDefault();if(!record||busy)return;setBusy(true);setError('');setNotice('');
    try {
      let current=record;
      if(dirty||current.status==='ANALYSING'){current=await privateApi<Record>('/requests/'+requestId,{method:'PATCH',headers:headers(),body:JSON.stringify({...requestPayload(draft,firstFutureDate(context?.demo_today)),expected_revision:current.revision})});apply(current);}
      await privateApi<UpdateRecord>('/requests/'+requestId+'/interpret',{method:'POST',headers:headers(),body:JSON.stringify({expected_revision:current.revision})});
      // Read the role-scoped preparation projection; GET never dispatches a model.
      const updated=await privateApi<UpdateRecord>('/requests/'+requestId);apply(updated);updateFlow.current=null;setUpdateStale(false);
    } catch(reason){setError(requestFailure(reason,'Could not generate the summary.'));if(reason instanceof ApiFailure&&reason.envelope.error.code==='UNAUTHENTICATED')reload();
      // Recover the current saved revision after an interpreter failure. Preserve
      // unsaved form text on a PATCH conflict instead of overwriting it.
      try{const latest=await privateApi<Record>('/requests/'+requestId);setRecord(latest);}catch{ /* Keep the visible error and input. */ }
    } finally{setBusy(false);}
  }
  async function saveOnly(){
    if(!record||busy)return;setBusy(true);setError('');
    try{
      if(dirty){const saved=await privateApi<UpdateRecord>('/requests/'+requestId,{method:'PATCH',headers:headers(),body:JSON.stringify({...requestPayload(draft,firstFutureDate(context?.demo_today)),expected_revision:record.revision})});apply(saved);updateFlow.current=null;setUpdateStale(false);}
      setNotice(record.trip_series_id?'Changes saved. New profile information has not been adopted and formal checks have not been updated. The original plan is unchanged.':'Draft saved. No summary or planning has started.');
    }catch(reason){setError(requestFailure(reason,'Save failed.'));}finally{setBusy(false);}
  }
  async function runUpdate(){
    if(!record||!session)return;
    if(!updateFlow.current)updateFlow.current=new ReplanSession(
      <T,>(path:string,body?:unknown)=>privateApi<T>(path,body===undefined?{}:{method:'POST',headers:headers(),body:JSON.stringify(body)}),
      ()=>crypto.randomUUID(),(operation,revision)=>tripCommandKey(window.sessionStorage,session.user.user_id,record.request_id,operation,revision,()=>crypto.randomUUID()));
    const flow=updateFlow.current;flow.record=record;
    try{const ids=await flow.start(true);navigate('/plans/'+ids.plan_id+'?run_id='+encodeURIComponent(ids.run_id));}
    catch(reason){
      if(flow.record)apply(flow.record as UpdateRecord);
      if(flow.previewStale){setUpdateStale(true);setAcknowledged(false);}
      throw reason;
    }
  }
  async function confirm() {
    if(!record||busy||dirty||!acknowledged||record.status!=='AWAITING_CONFIRMATION')return;setBusy(true);setError('');
    if(command.current?.revision!==record.revision)command.current={revision:record.revision,key:crypto.randomUUID()};
    try{if(record.trip_series_id){await runUpdate();return;}const updated=await privateApi<Record>('/requests/'+requestId+'/confirm',{method:'POST',headers:headers(),body:JSON.stringify({expected_revision:record.revision,command_key:command.current.key,acknowledged:true})});apply(updated);setNotice('Request confirmed and saved.');}
    catch(reason){setError(requestFailure(reason,'Confirmation failed. Please try again.'));if(reason instanceof ApiFailure&&reason.envelope.error.code==='UNAUTHENTICATED')reload();}finally{setBusy(false);}
  }
  async function startPlanning() {
    if(!record||!requestId||busy||!record.planning_available||tripTooLong)return;
    if(planningCommand.current?.requestId!==requestId||planningCommand.current.revision!==record.revision)
      planningCommand.current={requestId,revision:record.revision,key:crypto.randomUUID()};
    setBusy(true);setError('');
    try {
      if(record.trip_series_id){await runUpdate();return;}
      const result=await privateApi<{plan_id:string;run_id:string}>('/requests/'+requestId+'/plan',{method:'POST',headers:headers(),body:JSON.stringify({expected_request_revision:record.revision,command_key:planningCommand.current.key})});
      navigate('/plans/'+result.plan_id+'?run_id='+encodeURIComponent(result.run_id));
    } catch(reason) {
      setError(reason instanceof ApiFailure?`${reason.message}(Trace ID ${reason.envelope.trace_id})`:'Submission is not yet confirmed. Submit again or refresh the request to view saved planning records.');
      if(reason instanceof ApiFailure&&reason.envelope.error.code==='UNAUTHENTICATED')reload();
      try {setRecord(await privateApi<Record>('/requests/'+requestId));} catch { /* Preserve submission error. */ }
    } finally {setBusy(false);}
  }
  const confirmed=record?.status==='CONFIRMED';const updating=!!record?.trip_series_id; const requirements=record?.confirmed_context?.requirements??record?.summary?.extracted_requirements;
  const profile=record?.confirmed_context?.profile_snapshot??record?.profile_snapshot??null;
  const systemPreparation=record?.confirmed_context?record.system_preparation===true:context?.system_preparation===true;
  const confirmationHint=busy?'Processing. Please wait…':dirty?'Changes are unsaved. Save them and regenerate the summary first.':record?.status==='DRAFT'?'Select Generate request summary first, then review the trip and group details.':record?.status==='ANALYSING'?'The summary is incomplete. You can generate it again.':record?.status==='NEEDS_CLARIFICATION'?'Address the issues listed below, then regenerate the summary.':record?.status==='UNSUPPORTED'?'Adjust unsupported conditions, then regenerate the summary.':record?.status==='AWAITING_CONFIRMATION'?!acknowledged?'Review the summary below, then select the confirmation checkbox to continue.':'Confirmation selected. You can save the request.':'Loading requirements…';
  const tripTooLong=context?.execution_mode==='agent'&&requirements?.duration_nights!=null&&requirements.duration_nights>30;
  const planningHint=busy?'Submitting planning request…':tripTooLong?'Planning currently supports up to 30 nights. Shorten the trip and reconfirm the request.':record?.planning_available?'Generate an itinerary and check equipment, costs and safety.':'Planning is temporarily unavailable. The request is saved; try again later.';
  const questions=record?.summary?.clarifications??[];
  const fieldErrors=record?.summary?.field_errors??[];
  const clarificationMap=new Map<string,string[]>();
  for(const item of [...questions.filter(item=>item.question!==`Please clarify ${item.field}.`||!fieldErrors.some(error=>error.field===item.field)).map(item=>({field:item.field,message:item.question})),...fieldErrors]) {
    const field=requestClarificationField(item.field,item.message);
    const message=clarificationText(field,item.message,requirements);
    const messages=clarificationMap.get(field)??[];
    if(!messages.includes(message))messages.push(message);
    clarificationMap.set(field,messages);
  }
  return <div className="onboarding-page"><TripFlow step={confirmed?3:2}/><div className="onboarding-heading"><div><span className="eyebrow">{updating?'Continue the same trip':'Review trip requirements'}</span><h1>{updating?'Review this update':confirmed?'Get ready for this camping trip.':'Confirm the arrangements for this camping trip.'}</h1><p>{updating?'Save changes → Review profile differences and request summary → Confirm adoption and run checks again. This will not create an independent trip.':confirmed?'Review your arrangements and generate your camping plan.':'Generate a summary, then review and confirm it.'}</p></div>{record&&<span className="onboarding-status">{STATUS[record.status]??record.status}{dirty?' · Changed':''}</span>}</div>
    {updating&&<section className="panel"><p>Regenerate the summary after changing requirements or your profile.</p>{record?.predecessor_plan_id&&<><Link className="text-link" to={'/profile?request_id='+encodeURIComponent(record.request_id)}>Edit personal profile ↗</Link><Link className="text-link" to={'/plans/'+record.predecessor_plan_id}>Cancel and return to original plan (unsaved changes will be lost) ↗</Link></>}</section>}
    {updating&&location.state?.profileSaved===true&&<p className="success-box" role="status">Profile saved. The original plan still uses the old profile. Regenerate the summary and review profile revision  revision,  before confirming the check. This does not mean the issues are resolved.</p>}
    {updateStale&&<p className="error-box" role="alert">The profile or source has changed. Regenerate the summary and review the differences. No new check has started. If the source was superseded, return to the original plan to view the current trip.</p>}
    {(error||contextError)&&<p className="error-box" role="alert">{error||contextError}</p>}{notice&&<p className="success-box" role="status">{notice}</p>}
    {!record?<section className="panel"><p>Loading request…</p><button className="secondary-button" onClick={()=>setRefresh(value=>value+1)}>Reload</button></section>:<div className={'request-layout'+(confirmed?' request-confirmed-layout':'')}>
      {!confirmed&&<section className="panel request-editor">
        <div className="section-title"><span className="eyebrow">Trip details</span><h2>Enter and complete</h2></div>
        <form onSubmit={saveAndAnalyse}><RequestFields minimumStart={firstFutureDate(context?.demo_today)} draft={draft} set={change} regions={context?.supported_destinations??[]} catalogue={context?.requirement_choices} disabled={busy}/>
          <div className="request-action"><p id="analyse-hint" className="action-hint" role="status">{busy?'Generating summary…':!context?contextError?'Could not read supported options. Reopen the page.':'Loading supported options…':!dirty&&record.requirement_help?.needed?'Other requirements need request assistance first, or must be changed to an existing option.':dirty?null:'Generate a summary to review arrangements and missing information.'}</p>
            <div className="request-action-buttons">
              <Link className="secondary-button request-back-button" to={'/profile?request_id='+encodeURIComponent(record.request_id)}><span aria-hidden="true">←</span> Back to previous page</Link>
              <button type="submit" className="primary-button" disabled={busy||!context||!dirty&&record.requirement_help?.needed===true} aria-describedby="analyse-hint">{busy?'Processing…':dirty?'Save changes and generate summary':record.status==='ANALYSING'?'Save again and generate summary':'Generate request summary'} <span>↗</span></button>
              <button type="button" className="secondary-button" disabled={busy||!dirty} onClick={saveOnly}>Save draft only</button>
              <DiscardChanges sections={unsavedSections} busy={busy} onDiscard={()=>setRefresh(value=>value+1)}/>
            </div>
          </div></form>
        <RequirementHelpPanel requestId={record.request_id} requestRevision={record.revision} state={record.requirement_help??null} dirty={dirty} disabled={busy} catalogue={context?.requirement_choices} refresh={()=>setRefresh(value=>value+1)}/>
      </section>}
      <section className={'panel confirmation-panel'+(confirmed?' confirmed-summary':'')}><div className="section-title"><span className="eyebrow">{confirmed?'Ready to start planning':'Review and confirm'}</span><h2>{confirmed?'Confirmed arrangements':'Summary to confirm'}</h2></div>
        {!confirmed&&<div className={'confirmation-status'+(record.status==='AWAITING_CONFIRMATION'&&!dirty?' confirmation-ready':'')}><span aria-hidden="true">{record.status==='AWAITING_CONFIRMATION'&&!dirty?'✓':'○'}</span><p id="confirmation-hint" role="status">{confirmationHint}</p></div>}
        {dirty?<div className="summary-placeholder"><span aria-hidden="true">↻</span><h3>Summary needs updating</h3><p>Save changes and generate a summary first.</p></div>:requirements?<>
          {!confirmed&&clarificationMap.size>0&&<section className="clarification-list" aria-label="Information to provide"><h3>Information to provide</h3>{[...clarificationMap].map(([field,messages])=><div key={field}><strong>{FIELD_TITLES[field]??'Needs review'}</strong>{messages.map(message=><p key={message}>{message}</p>)}{FIELD_IDS[field]?<button className="text-link focus-field" onClick={()=>focusRequestField(field)}>Complete details ↗</button>:field.startsWith('profile')?<Link className="text-link" to={'/profile?request_id='+encodeURIComponent(record.request_id)}>Edit camping profile ↗</Link>:null}</div>)}</section>}
          <dl className="request-summary-facts">{[['Destination',requirements.destination],['Start date',requirements.start_date],['Trip duration',`${requirements.duration_nights??'Unknown'} nights / ${requirements.duration_days??'Unknown'} days`],['End date',requirements.end_date],['Group budget',requirements.budget_cents==null?'Unknown':`AUD ${(requirements.budget_cents/100).toFixed(2)}`]].map(([title,value])=><div key={title}><dt>{title}</dt><dd>{value??'Not provided'}</dd></div>)}</dl>
          <RequestMeaningSummary requirements={requirements} pendingConstraints={clarificationMap.has('mandatory_constraints')||clarificationMap.has('raw_text')}/>
          {updating&&record.source_profile_snapshot&&profile&&<ProfileAdoptionPreview before={record.source_profile_snapshot} after={profile} revision={record.profile_revision} sourceRevision={record.source_profile_revision??null}/>}
          {updating&&record.source_requirements&&requirements&&<RequirementsChangePreview before={record.source_requirements} after={requirements}/>}
          <div className="request-profile-overview"><h3>Camping profile used for this request</h3><div><span>Group size<strong>{profile?.group_size??'Unknown'} people</strong></span><span>Registered equipment<strong>{profile?profile.equipment.filter(item=>!['vehicle','charged_phone',...(systemPreparation?['transport_itinerary','fire_free_meal_plan']:[])].includes(item.item_key)).length:'Unknown'} items</strong></span></div><details><summary>View group, transport and equipment details</summary><ProfileSummary profile={profile} systemPreparation={systemPreparation}/></details></div>
          {systemPreparation?<SystemPreparationNotice mode={profile?.transport.transport_type??''}/>:profile?.transport.transport_type==='PUBLIC_TRANSPORT'&&<PublicTransportNotice/>}
          <CookingPreparationPanel value={record.cooking_preparation} stale={dirty}/>
          {record.cooking_preparation&&!record.planning_plan_id&&(!canHideCookingPreparation(record.cooking_preparation)||dirty)&&<Link className="text-link" to={'/profile?request_id='+encodeURIComponent(record.request_id)+'&focus=equipment.camping_stove'}>Complete cooking equipment ↗</Link>}
          {record.summary?.uncertainties.filter(item=>item!=='This output is not a confirmation event.').map((item,index)=><p className="muted" key={index}>{item}</p>)}
        </>:<div className="summary-placeholder"><span aria-hidden="true">⌁</span><h3>Generate a request summary first</h3><p>The summary shows dates, budget, group details and missing information.</p></div>}
        {record.error&&<p className="error-box" role="alert">{record.error.message}</p>}
        {!confirmed&&<div className="confirmation-actions"><p className="action-hint">{confirmationHint}</p>{updating&&<p id="replan-impact" className="action-hint">The plan will be regenerated from your changes. Campsite and itinerary may change.</p>}<label className="checkbox-label acknowledgement"><input type="checkbox" checked={acknowledged} disabled={busy||dirty||updateStale||record.status!=='AWAITING_CONFIRMATION'} aria-describedby="confirmation-hint" onChange={event=>setAcknowledged(event.target.checked)}/>I have read the requirements and profile for this trip and {updating?'confirm adoption of these changes and a new check.':'confirm the information above.'}</label><button className="primary-button" disabled={busy||dirty||updateStale||!acknowledged||record.status!=='AWAITING_CONFIRMATION'||updating&&tripTooLong} aria-describedby={updating?"confirmation-hint replan-impact":"confirmation-hint"} onClick={confirm}>{busy?'Processing…':updating?'Confirm changes and recheck':'Confirm and save requirements'} <span>✓</span></button>{updating&&<button className="secondary-button" disabled={busy} onClick={saveOnly}>Save changes without checking</button>}</div>}
        {confirmed&&<div className="confirmation-actions">{record.planning_plan_id?<Link className="primary-button" to={'/plans/'+record.planning_plan_id}>View planning progress and plan ↗</Link>:<><p id="planning-hint" className="action-hint" role="status">{planningHint}</p><button className="primary-button" disabled={busy||!record.planning_available||tripTooLong||updateStale} aria-describedby="planning-hint" onClick={startPlanning}>{busy?'Submitting…':updating?'Continue submitting this check':'Start planning'} <span>↗</span></button></>}{record.planning_plan_id&&<Link className="text-link" to={tripUpdatePath(record.planning_plan_id)}>Adjust requirements for this trip ↗</Link>}</div>}
      </section>
    </div>}
    <Link className="text-link return-requests" to="/request">← Back to requests</Link>
  </div>;
}
