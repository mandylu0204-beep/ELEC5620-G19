import { DiscardChanges } from './display_panels';
import { changedSections } from './display_facts';
import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Link, useLocation, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { ApiFailure, type PreviewResult, type Requirements } from './api';
import { integer, lines, ProfileSummary, type Profile } from './profile';
import { CookingPreparationPanel, type CookingPreparation } from './cooking_preparation';
import { privateApi, useSession } from './session';
import { TripFlow, FieldHint } from './trip_flow';
import { canonicalTerms, termLabel } from './user_terms';
import { ProfileAdoptionPreview } from './replan';
import { ReplanSession } from './replan_session';
import { tripCommandKey,tripUpdatePath } from './trip_update';

type RequestContext = { supported_destinations: string[]; execution_mode: string; demo_today: string; planning_available: boolean };
type Record = { request_id: string; raw_text: string; explicit_fields: Partial<Requirements>; status: string; revision: number; created_at: string; summary: PreviewResult | null; profile_snapshot: Profile | null; profile_revision: number | null; error: { message:string } | null; confirmed_context: { requirements: Requirements; profile_snapshot: Profile; confirmed_at: string; demo_context: { mode:string } } | null; planning_available:boolean; planning_plan_id?:string|null };
type UpdateRecord = Record & {trip_series_id?:string;predecessor_plan_id?:string|null;source_profile_revision?:number|null;source_profile_snapshot?:Profile;source_requirements?:Requirements;is_trip_update?:boolean;cooking_preparation?:CookingPreparation|null};
type Draft = { raw: string; destination: string; start: string; nights: string; days: string; end: string; budget: string; preferences: string; constraints: string };
const EMPTY: Draft = {raw:'',destination:'',start:'',nights:'',days:'',end:'',budget:'',preferences:'',constraints:''};
const STATUS: {[key:string]:string} = {DRAFT:'草稿',ANALYSING:'正在生成摘要',NEEDS_CLARIFICATION:'需要澄清',UNSUPPORTED:'暂不支持该地区',AWAITING_CONFIRMATION:'等待你的确认',CONFIRMED:'需求已确认'};

function fromRecord(record: Record): Draft {
  const value = record.explicit_fields;
  return { raw:record.raw_text, destination:value.destination ?? '', start:value.start_date ?? '', nights:String(value.duration_nights ?? ''), days:String(record.explicit_fields.duration_days ?? ''), end:record.explicit_fields.end_date ?? '', budget:value.budget_cents === null || value.budget_cents === undefined ? '' : (value.budget_cents / 100).toFixed(2), preferences:(value.preferences ?? []).map(item=>termLabel(item,'preference')).join('\n'), constraints:(value.mandatory_constraints ?? []).map(item=>termLabel(item,'constraint')).join('\n') };
}

function payload(draft: Draft) {
  let budget_cents: number | null = null;
  if (draft.budget !== '') {
    if (!/^\d+([.]\d{1,2})?$/.test(draft.budget)) throw new Error('预算请填写最多两位小数的 AUD 金额。');
    const [whole,fraction=''] = draft.budget.split('.');
    budget_cents = Number(whole) * 100 + Number(fraction.padEnd(2,'0'));
    if (!Number.isSafeInteger(budget_cents)) throw new Error('预算金额过大，请修改。');
  }
  return { raw_text:draft.raw, explicit_fields:{destination:draft.destination.trim() || null, start_date:draft.start || null, duration_nights:integer(draft.nights), duration_days:integer(draft.days), end_date:draft.end || null, budget_cents, ...(draft.preferences.trim()?{preferences:canonicalTerms(lines(draft.preferences),'preference')} : {}), mandatory_constraints:canonicalTerms(lines(draft.constraints),'constraint')} };
}

function RequestFields({draft,set,regions,disabled}:{draft:Draft;set:(patch:Partial<Draft>)=>void;regions:string[];disabled:boolean}) {
  const nights=Number(draft.nights);
  const preferences=canonicalTerms(lines(draft.preferences),'preference');
  const ready=preferences.some(value=>['ready-to-eat meals','ready_to_eat'].includes(value));
  const cooked=preferences.some(value=>['self-catered meals','self_catered'].includes(value));
  const meal=ready!==cooked?(ready?'ready-to-eat meals':'self-catered meals'):'';
  function selectMeal(value:string) {
    const remaining=preferences.filter(item=>!['ready-to-eat meals','ready_to_eat','self-catered meals','self_catered'].includes(item));
    set({preferences:[...remaining,...(value?[value]:[])].map(item=>termLabel(item,'preference')).join('\n')});
  }
  return <fieldset disabled={disabled}>
    <section className="request-form-section"><div className="form-section-heading"><span>01</span><h3>想怎样露营？</h3></div><label htmlFor="request-idea">你的露营想法 <span className="required-mark">必填</span></label><textarea id="request-idea" required maxLength={8000} value={draft.raw} placeholder="和谁同行，想去哪里，希望怎样度过这次露营？" onChange={event=>set({raw:event.target.value})}/></section>
    <section className="request-form-section"><div className="form-section-heading"><span>02</span><h3>目的地与行程</h3></div><div className="form-grid">
      <div><label htmlFor="request-destination">目的地</label><input id="request-destination" list="supported-destinations" value={draft.destination} aria-describedby="destination-hint" onChange={event=>set({destination:event.target.value})}/><datalist id="supported-destinations">{regions.map(region=><option key={region} value={region}/>)}</datalist><FieldHint id="destination-hint">可选地区：{regions.join('、')||'正在读取…'}</FieldHint></div>
      <div><label htmlFor="request-start">开始日期</label><input id="request-start" type="date" value={draft.start} onChange={event=>set({start:event.target.value})}/></div>
      <div><label htmlFor="request-nights">露营晚数</label><input id="request-nights" type="number" min="1" step="1" value={draft.nights} aria-describedby="nights-hint" onChange={event=>set({nights:event.target.value})}/><FieldHint id="nights-hint">{draft.nights&&Number.isSafeInteger(nights)&&nights>0&&nights<Number.MAX_SAFE_INTEGER?`${nights} 晚对应 ${nights+1} 天。`:'例如：两晚对应三天。'}</FieldHint></div>
      <div><label htmlFor="request-budget">整个小组预算 AUD</label><input id="request-budget" inputMode="decimal" pattern="[0-9]+([.][0-9]{1,2})?" placeholder="例如 320.00" value={draft.budget} aria-describedby="budget-hint" onChange={event=>set({budget:event.target.value})}/><FieldHint id="budget-hint">填写整个行程的总预算。</FieldHint></div>
    </div><details className="optional-fields"><summary>已明确天数或结束日期？补充在这里</summary><div className="form-grid"><div><label htmlFor="request-days">已明确的天数</label><input id="request-days" type="number" min="1" step="1" value={draft.days} onChange={event=>set({days:event.target.value})}/></div><div><label htmlFor="request-end">已明确的结束日期</label><input id="request-end" type="date" value={draft.end} onChange={event=>set({end:event.target.value})}/></div></div><p className="field-hint">与晚数冲突时，请按摘要提示核对。</p></details></section>
    <section className="request-form-section"><div className="form-section-heading"><span>03</span><h3>偏好与必须条件</h3></div><label htmlFor="request-meal">用餐方式</label><select id="request-meal" value={meal} onChange={event=>selectMeal(event.target.value)} aria-describedby="meal-hint"><option value="">请选择用餐方式</option><option value="ready-to-eat meals">即食餐食（无需烹饪）</option><option value="self-catered meals">自行烹饪（需要核对炉具和燃料）</option></select><FieldHint id="meal-hint">用于计算餐食费用和烹饪装备；确认需求前需要明确选择。</FieldHint><div className="form-grid"><div><label htmlFor="request-preferences">偏好（每行一项）</label><textarea id="request-preferences" value={draft.preferences} placeholder="例如：安静的环境" onChange={event=>set({preferences:event.target.value})}/></div><div><label htmlFor="request-constraints">必须满足的条件（每行一项）</label><textarea id="request-constraints" value={draft.constraints} placeholder="例如：需要淋浴" onChange={event=>set({constraints:event.target.value})}/></div></div></section>
  </fieldset>;
}

const FIELD_IDS: {[field:string]:string} = {destination:'request-destination',start_date:'request-start',duration_nights:'request-nights',duration_days:'request-days',end_date:'request-end',budget_cents:'request-budget',preferences:'request-meal',mandatory_constraints:'request-constraints'};
const FIELD_TITLES: {[field:string]:string} = {destination:'目的地',start_date:'开始日期',duration_nights:'露营晚数',duration_days:'行程天数',end_date:'结束日期',budget_cents:'小组预算',preferences:'偏好与用餐方式',mandatory_constraints:'必须条件','profile.group_size':'小组人数'};
export function RequirementsChangePreview({before,after}:{before:Requirements;after:Requirements}){
  const fields=['destination','start_date','duration_nights','end_date','budget_cents','preferences','mandatory_constraints'] as const;
  const changed=fields.filter(key=>JSON.stringify(before[key])!==JSON.stringify(after[key]));
  const text=(key:typeof fields[number],value:unknown)=>Array.isArray(value)?value.map(item=>termLabel(item,key==='preferences'?'preference':'constraint')).join('、')||'无'
    :key==='budget_cents'&&typeof value==='number'?`AUD ${(value/100).toFixed(2)}`:value==null?'未知':String(value);
  return <section aria-label="需求变化"><h3>需求变化</h3>{changed.length?<ul>{changed.map(key=><li key={key}>{FIELD_TITLES[key]}：{text(key,before[key])} → {text(key,after[key])}</li>)}</ul>:<p>目的地、日期、预算和偏好与原方案一致。</p>}<p>这是本次拟采用的需求，不代表正式检查通过。</p></section>;
}
function clarificationText(field:string,message:string,requirements:Requirements|undefined) {
  const pastDate=message.match(/^Start date must be on or after the checking date \((\d{4}-\d{2}-\d{2}), Australia\/Sydney\)\.$/);
  if(pastDate)return `开始日期不能早于本次检查日期（${pastDate[1]}，悉尼时间），请调整后重新生成摘要。`;
  if(message==='Start date precedes the fixed demonstration date.')return '开始日期早于此前检查采用的日期，请重新生成摘要以核对当前日期。';
  if(['What start date?','Which synthetic region?','How many nights?','What total AUD group budget?','Required request information is missing.'].includes(message))
    return `请补充${FIELD_TITLES[field]??'此项信息'}。`;
  if(message==='Choose ready-to-eat meals or self-catered meals before confirming the request.'||message==='Choose one confirmed meal mode.')return '请选择一种用餐方式：即食餐食或自行烹饪，再重新生成摘要。';
  if(message==='Only registered synthetic regions are supported.')return '当前资料暂不包含该地区，请核对目的地。';
  if(field==='duration_days'&&(message===`Please clarify ${field}.`||message==='Days must equal nights plus one.')&&requirements?.duration_nights!=null&&requirements.duration_days!=null&&requirements.duration_days!==requirements.duration_nights+1)
    return `${requirements.duration_nights} 晚对应 ${requirements.duration_nights+1} 天，当前填写了 ${requirements.duration_days} 天，请核对。`;
  return message===`Please clarify ${field}.`?`请核对${FIELD_TITLES[field]??'此项信息'}。`:message;
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
  useEffect(()=>{ const controller=new AbortController(); privateApi<RequestContext>('/request-context',{signal:controller.signal}).then(value=>{if(!controller.signal.aborted)setContext(value);}).catch(reason=>{if(!controller.signal.aborted)setError(reason instanceof ApiFailure?reason.message:'无法读取地区信息，请重新打开页面。');}); return()=>controller.abort(); },[]);
  return {context,error};
}

export function RequestHistory({rows,deleting,selected,onSelect,onDelete,onCancel}:{rows:UpdateRecord[]|null;deleting:string|null;selected:string|null;onSelect:(id:string)=>void;onDelete:(id:string)=>void;onCancel:()=>void}){
  return <details className="panel request-history"><summary>草稿与历史需求（{rows?.length??'…'}）</summary>
    <p>这些是需求及确认记录，不代表新增了一次独立出行。同系列的更新方案请在“方案与历史”查看。</p>
    {rows===null?<p>正在读取…</p>:rows.length===0?<p>暂无记录。</p>:<ul className="request-list">{rows.map(row=><li key={row.request_id}>
      <Link to={'/request/'+row.request_id}><strong>{row.raw_text.slice(0,85)}</strong><span className="tag">{row.trip_series_id?'本次出行更新 · ':''}{STATUS[row.status]??row.status}</span></Link>
      {selected===row.request_id?<div className="plan-delete-confirm" role="group" aria-label="确认删除请求"><p>删除这条需求记录？已有方案和不可变确认快照保留。</p><button disabled={deleting!==null} onClick={()=>onDelete(row.request_id)}>确认删除</button><button disabled={deleting!==null} onClick={onCancel}>取消</button></div>
        :<button className="text-button" disabled={deleting!==null||row.status==='ANALYSING'} onClick={()=>onSelect(row.request_id)}>删除需求记录</button>}
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
    }catch(reason){setDeleteError(requestFailure(reason,'删除失败，请重试。'));if(reason instanceof ApiFailure&&reason.envelope.error.code==='UNAUTHENTICATED')reload();}
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
      setDraft({...fromRecord({...record,explicit_fields:fields}),days:'',end:''});
      setCopyNotice('已载入原需求。请修改后重新确认。');
    }).catch(reason=>{if(!controller.signal.aborted){setCopyFailed(true);setError(reason instanceof ApiFailure?reason.message:'无法载入原需求，请重试或开始空白请求。');if(reason instanceof ApiFailure&&reason.envelope.error.code==='UNAUTHENTICATED')reload();}}).finally(()=>{if(!controller.signal.aborted)setCopyLoading(false);});
    return()=>controller.abort();
  },[copyFrom,reload]);
  useEffect(()=>{const controller=new AbortController(); privateApi<{requests:Record[]}>('/requests',{signal:controller.signal}).then(value=>{if(!controller.signal.aborted)setRows(value.requests);}).catch(reason=>{if(!controller.signal.aborted)setError(reason instanceof ApiFailure?reason.message:'无法读取已保存请求。');}); return()=>controller.abort();},[]);
  useEffect(()=>{
    if(!copyLoading&&!copyFailed&&['request-meal','request-budget'].includes(search.get('focus')??''))focusRequestField(search.get('focus')==='request-meal'?'preferences':'budget_cents');
  },[copyLoading,copyFailed,search]);
  async function create(event:FormEvent) {
    event.preventDefault(); if(!session||busy||copyLoading||copyFailed||!draft.raw.trim())return; setBusy(true);setError('');
    try {const record=await privateApi<Record>('/requests',{method:'POST',headers:{'Content-Type':'application/json','X-CampMate-Client':'1','X-CSRF-Token':session.csrf_token},body:JSON.stringify(payload(draft))});navigate('/request/'+record.request_id);}
    catch(reason){setError(requestFailure(reason,'保存失败。'));if(reason instanceof ApiFailure&&reason.envelope.error.code==='UNAUTHENTICATED')reload();}finally{setBusy(false);}
  }
  const createHint=copyLoading?'正在载入原需求…':copyFailed?'原需求未能载入，请开始空白请求或重新打开原记录。':busy?'正在保存草稿…':!draft.raw.trim()?'先写下你的露营想法，再保存草稿。':'先保存草稿，下一步生成摘要并核对需求。';
  return <div className="onboarding-page"><TripFlow step={2}/><div className="onboarding-heading"><div><span className="eyebrow">露营需求</span><h1>先把需求说清楚。</h1><p>写下想法，核对安排，再开始规划。</p></div><Link className="text-link" to="/profile">查看露营资料 ↗</Link></div>
    {(error||contextError)&&<p className="error-box" role="alert">{error||contextError}</p>}{copyNotice&&<p className="success-box" role="status">{copyNotice}</p>}{copyLoading&&<p role="status">正在载入原需求…</p>}{copyFrom&&<button className="secondary-button" disabled={busy} onClick={()=>setSearch({})}>开始空白请求</button>}
    <div className="request-layout"><section className="panel request-editor"><div className="section-title"><span className="eyebrow">规划下一次出行</span><h2>新建露营请求</h2></div><form onSubmit={create}><RequestFields draft={draft} set={patch=>setDraft(value=>({...value,...patch}))} regions={context?.supported_destinations??[]} disabled={busy||copyLoading||copyFailed}/><div className="request-action"><p id="create-hint" className="action-hint" role="status">{createHint}</p><button className="primary-button" disabled={busy||copyLoading||copyFailed||!draft.raw.trim()} aria-describedby="create-hint">{busy?'正在保存…':'保存草稿，下一步'} <span>↗</span></button></div></form></section>
    <aside className="request-sidebar"><section className="panel request-guide"><span className="eyebrow">开始之前</span><h2>一份清楚的计划</h2><ul><li>同行人数和装备来自已保存的露营资料。</li><li>不确定的信息先留空，摘要会提示需要补充的内容。</li><li>确认摘要后，再生成行程与评估。</li></ul><Link className="text-link" to="/profile">完善露营资料 ↗</Link></section>{deleteError&&<p className="error-box" role="alert">{deleteError}</p>}<RequestHistory rows={rows} deleting={deleting} selected={confirmDelete} onSelect={id=>{setConfirmDelete(id);setDeleteError('');}} onDelete={id=>void deleteRequest(id)} onCancel={()=>setConfirmDelete(null)}/></aside></div>
  </div>;
}

export function RequestDetail() {
  const {requestId}=useParams(); const navigate=useNavigate(); const location=useLocation(); const [search]=useSearchParams(); const {session,reload}=useSession(); const {context,error:contextError}=useRequestContext();
  const [record,setRecord]=useState<UpdateRecord|null>(null); const [draft,setDraft]=useState<Draft>(EMPTY); const [acknowledged,setAcknowledged]=useState(false); const [busy,setBusy]=useState(false); const [error,setError]=useState(''); const [notice,setNotice]=useState(''); const [refresh,setRefresh]=useState(0);
  const updateFlow=useRef<ReplanSession|null>(null);const [updateStale,setUpdateStale]=useState(false);
  const unsavedSections=changedSections(record?fromRecord(record):null,draft,{raw:'露营想法',destination:'目的地',start:'开始日期',nights:'露营晚数',days:'行程天数',end:'结束日期',budget:'小组预算',preferences:'偏好与用餐方式',constraints:'必须条件'});
  const dirty=unsavedSections.length>0;
  const command=useRef<{revision:number;key:string}|null>(null);
  const planningCommand=useRef<{requestId:string;revision:number;key:string}|null>(null);
  function apply(value:UpdateRecord){setRecord(value);setDraft(fromRecord(value));setAcknowledged(false);}
  useEffect(()=>{const controller=new AbortController();setRecord(null);setError('');setNotice('');updateFlow.current=null;setUpdateStale(false);privateApi<UpdateRecord>('/requests/'+requestId,{signal:controller.signal}).then(value=>{if(!controller.signal.aborted)apply(value);}).catch(reason=>{if(!controller.signal.aborted)setError(reason instanceof ApiFailure?reason.message:'无法读取请求。');});return()=>controller.abort();},[requestId,refresh]);
  useEffect(()=>{if(record&&['request-meal','request-budget'].includes(search.get('focus')??''))focusRequestField(search.get('focus')==='request-meal'?'preferences':'budget_cents');},[record?.request_id,search]);
  function change(patch:Partial<Draft>){setDraft(value=>({...value,...patch}));setAcknowledged(false);setError('');setNotice('');}
  function headers(){return {'Content-Type':'application/json','X-CampMate-Client':'1','X-CSRF-Token':session?.csrf_token??''};}
  async function saveAndAnalyse(event:FormEvent) {
    event.preventDefault();if(!record||busy||!draft.raw.trim())return;setBusy(true);setError('');setNotice('');
    try {
      let current=record;
      if(dirty||current.status==='ANALYSING'){current=await privateApi<Record>('/requests/'+requestId,{method:'PATCH',headers:headers(),body:JSON.stringify({...payload(draft),expected_revision:current.revision})});apply(current);}
      await privateApi<UpdateRecord>('/requests/'+requestId+'/interpret',{method:'POST',headers:headers(),body:JSON.stringify({expected_revision:current.revision})});
      // Read the role-scoped preparation projection; GET never dispatches a model.
      const updated=await privateApi<UpdateRecord>('/requests/'+requestId);apply(updated);updateFlow.current=null;setUpdateStale(false);
    } catch(reason){setError(requestFailure(reason,'生成摘要失败。'));if(reason instanceof ApiFailure&&reason.envelope.error.code==='UNAUTHENTICATED')reload();
      // Recover the current saved revision after an interpreter failure. Preserve
      // unsaved form text on a PATCH conflict instead of overwriting it.
      try{const latest=await privateApi<Record>('/requests/'+requestId);setRecord(latest);}catch{ /* Keep the visible error and input. */ }
    } finally{setBusy(false);}
  }
  async function saveOnly(){
    if(!record||busy)return;setBusy(true);setError('');
    try{
      if(dirty){const saved=await privateApi<UpdateRecord>('/requests/'+requestId,{method:'PATCH',headers:headers(),body:JSON.stringify({...payload(draft),expected_revision:record.revision})});apply(saved);updateFlow.current=null;setUpdateStale(false);}
      setNotice('修改已保存，暂未采用新资料或更新正式检查。原方案保持不变。');
    }catch(reason){setError(requestFailure(reason,'保存失败。'));}finally{setBusy(false);}
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
    try{if(record.trip_series_id){await runUpdate();return;}const updated=await privateApi<Record>('/requests/'+requestId+'/confirm',{method:'POST',headers:headers(),body:JSON.stringify({expected_revision:record.revision,command_key:command.current.key,acknowledged:true})});apply(updated);setNotice('需求已确认并保存。');}
    catch(reason){setError(requestFailure(reason,'确认失败，请重试。'));if(reason instanceof ApiFailure&&reason.envelope.error.code==='UNAUTHENTICATED')reload();}finally{setBusy(false);}
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
      setError(reason instanceof ApiFailure?`${reason.message}（追踪号 ${reason.envelope.trace_id}）`:'提交结果尚未确认。可再次提交，或刷新请求查看已保存的规划记录。');
      if(reason instanceof ApiFailure&&reason.envelope.error.code==='UNAUTHENTICATED')reload();
      try {setRecord(await privateApi<Record>('/requests/'+requestId));} catch { /* Preserve submission error. */ }
    } finally {setBusy(false);}
  }
  const confirmed=record?.status==='CONFIRMED';const updating=!!record?.trip_series_id; const requirements=record?.confirmed_context?.requirements??record?.summary?.extracted_requirements;
  const profile=record?.confirmed_context?.profile_snapshot??record?.profile_snapshot??null;
  const confirmationHint=busy?'正在处理，请稍候…':dirty?'修改尚未保存，请先保存修改并重新生成摘要。':record?.status==='DRAFT'?'先点击“生成需求摘要”，核对行程与同行资料。':record?.status==='ANALYSING'?'摘要尚未完成，可以重新生成摘要。':record?.status==='NEEDS_CLARIFICATION'?'请补充下方列出的问题，再重新生成摘要。':record?.status==='UNSUPPORTED'?'请调整超出支持范围的条件，再重新生成摘要。':record?.status==='AWAITING_CONFIRMATION'?!acknowledged?'核对下方摘要后，勾选确认即可继续。':'已勾选确认，可以保存需求。':'正在读取需求…';
  const tripTooLong=context?.execution_mode==='agent'&&requirements?.duration_nights!=null&&requirements.duration_nights>30;
  const planningHint=busy?'正在提交规划…':tripTooLong?'当前规划支持最多 30 晚，请缩短行程并重新确认需求。':record?.planning_available?'开始生成行程，并检查装备、费用与安全。':'规划服务暂不可用；需求已保存，请稍后再试。';
  const questions=record?.summary?.clarifications??[];
  const fieldErrors=record?.summary?.field_errors??[];
  const clarificationMap=new Map<string,string[]>();
  for(const item of [...questions.filter(item=>item.question!==`Please clarify ${item.field}.`||!fieldErrors.some(error=>error.field===item.field)).map(item=>({field:item.field,message:item.question})),...fieldErrors]) {
    const message=clarificationText(item.field,item.message,requirements);
    const messages=clarificationMap.get(item.field)??[];
    if(!messages.includes(message))messages.push(message);
    clarificationMap.set(item.field,messages);
  }
  return <div className="onboarding-page"><TripFlow step={confirmed?3:2}/><div className="onboarding-heading"><div><span className="eyebrow">{updating?'继续处理同一次出行':'核对出行需求'}</span><h1>{updating?'核对本次更新':confirmed?'准备开始这次露营。':'确认这次露营的安排。'}</h1><p>{updating?'保存修改 → 核对资料差异与需求摘要 → 确认采用并重新检查。不会创建另一独立出行。':confirmed?'核对安排，开始生成你的露营方案。':'先生成摘要，再核对并确认。'}</p></div>{record&&<span className="onboarding-status">{STATUS[record.status]??record.status}{dirty?' · 有修改':''}</span>}</div>
    {updating&&<section className="panel"><p>原方案及最终记录保持原样。仅保存或刷新不会启动模型；确认检查后仍会重新规划，营地与行程可能变化。</p>{record?.predecessor_plan_id&&<><Link className="text-link" to={'/profile?request_id='+encodeURIComponent(record.request_id)}>修改个人资料 ↗</Link><Link className="text-link" to={'/plans/'+record.predecessor_plan_id}>取消核对，返回原方案（未保存修改不会保留） ↗</Link></>}</section>}
    {updating&&location.state?.profileSaved===true&&<p className="success-box" role="status">个人资料已保存；原方案仍采用旧资料。本页需重新生成摘要、核对资料 revision，再确认启动检查，不能视为问题已解决。</p>}
    {updateStale&&<p className="error-box" role="alert">资料或来源已变化，请重新生成摘要并核对新的差异。尚未开始新检查；若来源已被取代，请返回原方案查看当前出行。</p>}
    {(error||contextError)&&<p className="error-box" role="alert">{error||contextError}</p>}{notice&&<p className="success-box" role="status">{notice}</p>}
    {!record?<section className="panel"><p>正在读取请求…</p><button className="secondary-button" onClick={()=>setRefresh(value=>value+1)}>重新读取</button></section>:<div className={'request-layout'+(confirmed?' request-confirmed-layout':'')}>
      {!confirmed&&<section className="panel request-editor">
        <div className="section-title"><span className="eyebrow">出行详情</span><h2>填写与补充</h2></div>
        <form onSubmit={saveAndAnalyse}><RequestFields draft={draft} set={change} regions={context?.supported_destinations??[]} disabled={busy}/>
          <div className="request-action"><p id="analyse-hint" className="action-hint" role="status">{busy?'正在生成摘要…':!context?contextError?'暂时无法读取支持范围，请重新打开页面。':'正在读取支持范围…':!draft.raw.trim()?'请先填写露营想法。':dirty?'保存这次修改后，会更新确认摘要。':'生成摘要，查看安排与需要补充的信息。'}</p>
            <button className="primary-button" disabled={busy||!context||!draft.raw.trim()} aria-describedby="analyse-hint">{busy?'正在处理…':dirty?'保存修改并生成摘要':record.status==='ANALYSING'?'重新保存并生成摘要':'生成需求摘要'} <span>↗</span></button>
          </div></form>
        <div className="editor-secondary"><DiscardChanges sections={unsavedSections} busy={busy} onDiscard={()=>setRefresh(value=>value+1)}/>
          <Link className="text-link" to={'/profile?request_id='+encodeURIComponent(record.request_id)}>修改露营资料 ↗</Link>
        </div>
      </section>}
      <section className={'panel confirmation-panel'+(confirmed?' confirmed-summary':'')}><div className="section-title"><span className="eyebrow">{confirmed?'准备开始规划':'核对与确认'}</span><h2>{confirmed?'已确认的安排':'待确认摘要'}</h2></div>
        {!confirmed&&<div className={'confirmation-status'+(record.status==='AWAITING_CONFIRMATION'&&!dirty?' confirmation-ready':'')}><span aria-hidden="true">{record.status==='AWAITING_CONFIRMATION'&&!dirty?'✓':'○'}</span><p id="confirmation-hint" role="status">{confirmationHint}</p></div>}
        {dirty?<div className="summary-placeholder"><span aria-hidden="true">↻</span><h3>摘要需要更新</h3><p>请先保存修改并生成摘要。</p></div>:requirements?<>
          {!confirmed&&clarificationMap.size>0&&<section className="clarification-list" aria-label="需要补充的信息"><h3>需要补充的信息</h3>{[...clarificationMap].map(([field,messages])=><div key={field}><strong>{FIELD_TITLES[field]??'需要核对'}</strong>{messages.map(message=><p key={message}>{message}</p>)}{FIELD_IDS[field]?<button className="text-link focus-field" onClick={()=>focusRequestField(field)}>去补充 ↗</button>:field.startsWith('profile')?<Link className="text-link" to={'/profile?request_id='+encodeURIComponent(record.request_id)}>修改露营资料 ↗</Link>:null}</div>)}</section>}
          <dl className="request-summary-facts">{[['目的地',requirements.destination],['开始日期',requirements.start_date],['行程长度',`${requirements.duration_nights??'未知'} 晚 / ${requirements.duration_days??'未知'} 天`],['结束日期',requirements.end_date],['小组预算',requirements.budget_cents==null?'未知':`AUD ${(requirements.budget_cents/100).toFixed(2)}`]].map(([title,value])=><div key={title}><dt>{title}</dt><dd>{value??'未提供'}</dd></div>)}</dl>
          {requirements.preferences?.length>0&&<div className="summary-preferences"><h3>偏好</h3><ul>{requirements.preferences.map((item,index)=><li key={index}>{termLabel(item,'preference')}</li>)}</ul></div>}{requirements.mandatory_constraints?.length>0&&<div className="summary-preferences"><h3>必须满足</h3><ul>{requirements.mandatory_constraints.map((item,index)=><li key={index}>{termLabel(item,'constraint')}</li>)}</ul></div>}
          {updating&&record.source_profile_snapshot&&profile&&<ProfileAdoptionPreview before={record.source_profile_snapshot} after={profile} revision={record.profile_revision} sourceRevision={record.source_profile_revision??null}/>}
          {updating&&record.source_requirements&&requirements&&<RequirementsChangePreview before={record.source_requirements} after={requirements}/>}
          <div className="request-profile-overview"><h3>本次采用的露营资料</h3><div><span>小组人数<strong>{profile?.group_size??'未知'} 人</strong></span><span>登记装备<strong>{profile?profile.equipment.filter(item=>!['vehicle','charged_phone'].includes(item.item_key)).length:'未知'} 项</strong></span></div><details><summary>查看同行、交通与装备明细</summary><ProfileSummary profile={profile}/></details></div>
          <CookingPreparationPanel value={record.cooking_preparation}/>
          {record.cooking_preparation&&!record.planning_plan_id&&<Link className="text-link" to={'/profile?request_id='+encodeURIComponent(record.request_id)+'&focus=equipment.camping_stove'}>规划前一起核对炉具与燃料（不会启动模型） ↗</Link>}
          {record.summary?.uncertainties.filter(item=>item!=='This output is not a confirmation event.').map((item,index)=><p className="muted" key={index}>{item}</p>)}
        </>:<div className="summary-placeholder"><span aria-hidden="true">⌁</span><h3>先生成需求摘要</h3><p>摘要会展示日期、预算、同行资料和需要补充的信息。</p></div>}
        {record.error&&<p className="error-box" role="alert">{record.error.message}</p>}
        {!confirmed&&<div className="confirmation-actions"><p className="action-hint">{confirmationHint}</p><label className="checkbox-label acknowledgement"><input type="checkbox" checked={acknowledged} disabled={busy||dirty||updateStale||record.status!=='AWAITING_CONFIRMATION'} aria-describedby="confirmation-hint" onChange={event=>setAcknowledged(event.target.checked)}/>我已阅读本次需求和资料，{updating?'确认采用以上修改并重新检查。':'确认以上内容。'}</label><button className="primary-button" disabled={busy||dirty||updateStale||!acknowledged||record.status!=='AWAITING_CONFIRMATION'||updating&&tripTooLong} aria-describedby="confirmation-hint" onClick={confirm}>{busy?'正在处理…':updating?'确认采用并重新检查':'确认并保存需求'} <span>✓</span></button>{updating&&<button className="secondary-button" disabled={busy} onClick={saveOnly}>仅保存修改，暂不检查</button>}</div>}
        {confirmed&&<div className="confirmation-actions">{record.planning_plan_id?<Link className="primary-button" to={'/plans/'+record.planning_plan_id}>查看规划进度与方案 ↗</Link>:<><p id="planning-hint" className="action-hint" role="status">{planningHint}</p><button className="primary-button" disabled={busy||!record.planning_available||tripTooLong||updateStale} aria-describedby="planning-hint" onClick={startPlanning}>{busy?'正在提交…':updating?'继续提交本次检查':'开始规划'} <span>↗</span></button></>}{record.planning_plan_id&&<Link className="text-link" to={tripUpdatePath(record.planning_plan_id)}>调整本次出行需求 ↗</Link>}<Link className="text-link" to={'/request?copy_from='+encodeURIComponent(record.request_id)}>以此为模板，新建独立出行 ↗</Link></div>}
      </section>
    </div>}
    <Link className="text-link return-requests" to="/request">← 返回请求列表</Link>
  </div>;
}
