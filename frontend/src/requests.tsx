import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { ApiFailure, type PreviewResult, type Requirements } from './api';
import { integer, lines, ProfileSummary, type Profile } from './profile';
import { privateApi, useSession } from './session';

type RequestContext = { supported_destinations: string[]; execution_mode: string; demo_today: string; planning_available: boolean };
type Record = { request_id: string; raw_text: string; explicit_fields: Partial<Requirements>; status: string; revision: number; created_at: string; summary: PreviewResult | null; profile_snapshot: Profile | null; profile_revision: number | null; error: { message:string } | null; confirmed_context: { requirements: Requirements; profile_snapshot: Profile; confirmed_at: string; demo_context: { mode:string } } | null; planning_available:boolean; planning_plan_id?:string|null };
type Draft = { raw: string; destination: string; start: string; nights: string; days: string; end: string; budget: string; preferences: string; constraints: string };
const EMPTY: Draft = {raw:'',destination:'',start:'',nights:'',days:'',end:'',budget:'',preferences:'',constraints:''};
const STATUS: {[key:string]:string} = {DRAFT:'草稿',ANALYSING:'正在生成摘要',NEEDS_CLARIFICATION:'需要澄清',UNSUPPORTED:'超出演示范围',AWAITING_CONFIRMATION:'等待你的确认',CONFIRMED:'需求已确认'};

function fromRecord(record: Record): Draft {
  const value = record.explicit_fields;
  return { raw:record.raw_text, destination:value.destination ?? '', start:value.start_date ?? '', nights:String(value.duration_nights ?? ''), days:String(value.duration_days ?? ''), end:value.end_date ?? '', budget:value.budget_cents === null || value.budget_cents === undefined ? '' : (value.budget_cents / 100).toFixed(2), preferences:(value.preferences ?? []).join('\n'), constraints:(value.mandatory_constraints ?? []).join('\n') };
}

function payload(draft: Draft) {
  let budget_cents: number | null = null;
  if (draft.budget !== '') {
    if (!/^\d+([.]\d{1,2})?$/.test(draft.budget)) throw new Error('预算请填写最多两位小数的 AUD 金额。');
    const [whole,fraction=''] = draft.budget.split('.');
    budget_cents = Number(whole) * 100 + Number(fraction.padEnd(2,'0'));
    if (!Number.isSafeInteger(budget_cents)) throw new Error('预算金额过大，请修改。');
  }
  return { raw_text:draft.raw, explicit_fields:{destination:draft.destination.trim() || null, start_date:draft.start || null, duration_nights:integer(draft.nights), duration_days:integer(draft.days), end_date:draft.end || null, budget_cents, preferences:lines(draft.preferences), mandatory_constraints:lines(draft.constraints)} };
}

function RequestFields({draft, set, regions, disabled}:{draft:Draft;set:(patch:Partial<Draft>)=>void;regions:string[];disabled:boolean}) {
  return <fieldset disabled={disabled}><label htmlFor="request-idea">你的露营想法</label><textarea id="request-idea" required maxLength={8000} value={draft.raw} placeholder="说明同行者、想去的地区和偏好。" onChange={event=>set({raw:event.target.value})}/><div className="form-grid"><div><label htmlFor="request-destination">目的地</label><input id="request-destination" list="supported-destinations" value={draft.destination} onChange={event=>set({destination:event.target.value})}/><datalist id="supported-destinations">{regions.map(region=><option key={region} value={region}/>)}</datalist></div><div><label htmlFor="request-start">开始日期</label><input id="request-start" type="date" value={draft.start} onChange={event=>set({start:event.target.value})}/></div><div><label htmlFor="request-nights">露营晚数</label><input id="request-nights" type="number" min="1" step="1" value={draft.nights} onChange={event=>set({nights:event.target.value})}/></div><div><label htmlFor="request-budget">整个小组预算 AUD</label><input id="request-budget" inputMode="decimal" pattern="[0-9]+([.][0-9]{1,2})?" placeholder="320.00" value={draft.budget} onChange={event=>set({budget:event.target.value})}/></div></div><p className="muted">支持地区：{regions.join('、') || '正在读取…'}。只填写已明确的字段；两晚对应三天。</p><details className="optional-fields"><summary>补充天数与结束日期（如已明确）</summary><div className="form-grid"><div><label htmlFor="request-days">已明确的天数</label><input id="request-days" type="number" min="1" step="1" value={draft.days} onChange={event=>set({days:event.target.value})}/></div><div><label htmlFor="request-end">已明确的结束日期</label><input id="request-end" type="date" value={draft.end} onChange={event=>set({end:event.target.value})}/></div></div><p className="muted">与晚数冲突时会先要求澄清，不会自动覆盖你的输入。</p></details><div className="form-grid"><div><label htmlFor="request-preferences">偏好（每行一项）</label><textarea id="request-preferences" value={draft.preferences} onChange={event=>set({preferences:event.target.value})}/></div><div><label htmlFor="request-constraints">必须满足的条件（每行一项）</label><textarea id="request-constraints" value={draft.constraints} onChange={event=>set({constraints:event.target.value})}/></div></div></fieldset>;
}

function useRequestContext() {
  const [context,setContext] = useState<RequestContext|null>(null);
  const [error,setError] = useState('');
  useEffect(()=>{ const controller=new AbortController(); privateApi<RequestContext>('/request-context',{signal:controller.signal}).then(value=>{if(!controller.signal.aborted)setContext(value);}).catch(reason=>{if(!controller.signal.aborted)setError(reason instanceof ApiFailure?reason.message:'无法读取演示范围，请重新打开页面。');}); return()=>controller.abort(); },[]);
  return {context,error};
}

export function RequestsPage() {
  const {session,reload}=useSession(); const navigate=useNavigate(); const {context,error:contextError}=useRequestContext();
  const [draft,setDraft]=useState<Draft>(EMPTY); const [rows,setRows]=useState<Record[]|null>(null); const [error,setError]=useState(''); const [busy,setBusy]=useState(false);
  useEffect(()=>{const controller=new AbortController(); privateApi<{requests:Record[]}>('/requests',{signal:controller.signal}).then(value=>{if(!controller.signal.aborted)setRows(value.requests);}).catch(reason=>{if(!controller.signal.aborted)setError(reason instanceof ApiFailure?reason.message:'无法读取已保存请求。');}); return()=>controller.abort();},[]);
  async function create(event:FormEvent) {
    event.preventDefault(); if(!session)return; setBusy(true);setError('');
    try {const record=await privateApi<Record>('/requests',{method:'POST',headers:{'Content-Type':'application/json','X-CampMate-Client':'1','X-CSRF-Token':session.csrf_token},body:JSON.stringify(payload(draft))});navigate('/request/'+record.request_id);}
    catch(reason){setError(reason instanceof Error?reason.message:'保存失败。');if(reason instanceof ApiFailure&&reason.envelope.error.code==='UNAUTHENTICATED')reload();}finally{setBusy(false);}
  }
  return <><div className="page-heading"><span className="eyebrow">YOUR CAMPING REQUEST</span><h1>先把需求说清楚。</h1><p>保存想法，补齐问题，再确认你看到的摘要。</p></div>{(error||contextError)&&<p className="error-box" role="alert">{error||contextError}</p>}{context?.execution_mode==='stub'&&<p className="mode-notice">当前为 STUB：请手动填写明确字段。自然语言提取尚未接入。</p>}<div className="preview-grid"><section className="panel"><h2>新建露营请求</h2><form onSubmit={create}><RequestFields draft={draft} set={patch=>setDraft(value=>({...value,...patch}))} regions={context?.supported_destinations??[]} disabled={busy}/><button className="primary-button" disabled={busy}>{busy?'正在保存…':'保存请求草稿'} <span>↗</span></button></form><Link className="text-link" to="/profile">先完善露营资料 ↗</Link></section><section className="panel"><h2>已保存的请求</h2>{rows===null?<p className="muted">正在读取…</p>:rows.length===0?<p className="muted">还没有请求。保存后可以刷新页面继续处理。</p>:<ul className="request-list">{rows.map(row=><li key={row.request_id}><Link to={'/request/'+row.request_id}><strong>{row.raw_text.slice(0,85)}</strong><span className="tag">{STATUS[row.status]??row.status}</span></Link></li>)}</ul>}</section></div></>;
}

export function RequestDetail() {
  const {requestId}=useParams(); const navigate=useNavigate(); const {session,reload}=useSession(); const {context,error:contextError}=useRequestContext();
  const [record,setRecord]=useState<Record|null>(null); const [draft,setDraft]=useState<Draft>(EMPTY); const [dirty,setDirty]=useState(false); const [acknowledged,setAcknowledged]=useState(false); const [busy,setBusy]=useState(false); const [error,setError]=useState(''); const [notice,setNotice]=useState(''); const [refresh,setRefresh]=useState(0);
  const command=useRef<{revision:number;key:string}|null>(null);
  const planningCommand=useRef<{requestId:string;revision:number;key:string}|null>(null);
  function apply(value:Record){setRecord(value);setDraft(fromRecord(value));setDirty(false);setAcknowledged(false);}
  useEffect(()=>{const controller=new AbortController();setRecord(null);setError('');setNotice('');privateApi<Record>('/requests/'+requestId,{signal:controller.signal}).then(value=>{if(!controller.signal.aborted)apply(value);}).catch(reason=>{if(!controller.signal.aborted)setError(reason instanceof ApiFailure?reason.message:'无法读取请求。');});return()=>controller.abort();},[requestId,refresh]);
  function change(patch:Partial<Draft>){setDraft(value=>({...value,...patch}));setDirty(true);setAcknowledged(false);setError('');setNotice('');}
  function headers(){return {'Content-Type':'application/json','X-CampMate-Client':'1','X-CSRF-Token':session?.csrf_token??''};}
  async function saveAndAnalyse(event:FormEvent) {
    event.preventDefault();if(!record)return;setBusy(true);setError('');setNotice('');
    try {
      let current=record;
      if(dirty||current.status==='ANALYSING'){current=await privateApi<Record>('/requests/'+requestId,{method:'PATCH',headers:headers(),body:JSON.stringify({...payload(draft),expected_revision:current.revision})});apply(current);}
      const updated=await privateApi<Record>('/requests/'+requestId+'/interpret',{method:'POST',headers:headers(),body:JSON.stringify({expected_revision:current.revision})});apply(updated);
    } catch(reason){setError(reason instanceof Error?reason.message:'生成摘要失败。');if(reason instanceof ApiFailure&&reason.envelope.error.code==='UNAUTHENTICATED')reload();
      // Recover the current saved revision after an interpreter failure. Preserve
      // unsaved form text on a PATCH conflict instead of overwriting it.
      try{const latest=await privateApi<Record>('/requests/'+requestId);setRecord(latest);}catch{ /* Keep the visible error and input. */ }
    } finally{setBusy(false);}
  }
  async function confirm() {
    if(!record||dirty||!acknowledged)return;setBusy(true);setError('');
    if(command.current?.revision!==record.revision)command.current={revision:record.revision,key:crypto.randomUUID()};
    try{const updated=await privateApi<Record>('/requests/'+requestId+'/confirm',{method:'POST',headers:headers(),body:JSON.stringify({expected_revision:record.revision,command_key:command.current.key,acknowledged:true})});apply(updated);setNotice('需求已确认并保存。');}
    catch(reason){setError(reason instanceof Error?reason.message:'确认失败，请重试。');if(reason instanceof ApiFailure&&reason.envelope.error.code==='UNAUTHENTICATED')reload();}finally{setBusy(false);}
  }
  async function startPlanning() {
    if(!record||!requestId||busy||!record.planning_available)return;
    if(planningCommand.current?.requestId!==requestId||planningCommand.current.revision!==record.revision)
      planningCommand.current={requestId,revision:record.revision,key:crypto.randomUUID()};
    setBusy(true);setError('');
    try {
      const result=await privateApi<{plan_id:string;run_id:string}>('/requests/'+requestId+'/plan',{method:'POST',headers:headers(),body:JSON.stringify({expected_request_revision:record.revision,command_key:planningCommand.current.key})});
      navigate('/plans/'+result.plan_id+'?run_id='+encodeURIComponent(result.run_id));
    } catch(reason) {
      setError(reason instanceof ApiFailure?`${reason.message}（追踪号 ${reason.envelope.trace_id}）`:'提交结果尚未确认。可再次提交，或刷新请求查看已保存的规划记录。');
      if(reason instanceof ApiFailure&&reason.envelope.error.code==='UNAUTHENTICATED')reload();
      try {setRecord(await privateApi<Record>('/requests/'+requestId));} catch { /* Preserve submission error. */ }
    } finally {setBusy(false);}
  }
  const confirmed=record?.status==='CONFIRMED'; const requirements=record?.confirmed_context?.requirements??record?.summary?.extracted_requirements;
  const profile=record?.confirmed_context?.profile_snapshot??record?.profile_snapshot??null;
  return <><div className="page-heading"><span className="eyebrow">REQUEST / CONFIRMATION</span><h1>{confirmed?'已保存你的需求。':'确认这次露营的安排。'}</h1><p>{record?STATUS[record.status]??record.status:'正在读取请求…'}</p></div>{(error||contextError)&&<p className="error-box" role="alert">{error||contextError}</p>}{notice&&<p className="success-box" role="status">{notice}</p>}{record&&<div className="preview-grid">{!confirmed&&<section className="panel"><h2>填写与补充</h2>{context?.execution_mode==='stub'&&<p className="muted">STUB 不解析自然语言，请明确填写字段后生成摘要。</p>}<form onSubmit={saveAndAnalyse}><RequestFields draft={draft} set={change} regions={context?.supported_destinations??[]} disabled={busy}/><button className="primary-button" disabled={busy||!context}>{busy?'正在处理…':dirty?'保存修改并生成摘要':record.status==='ANALYSING'?'重新保存并生成摘要':'生成需求摘要'} <span>↗</span></button></form>{dirty&&<p className="muted">有未保存修改，旧摘要暂时不能确认。</p>}<button className="secondary-button" disabled={busy} onClick={()=>setRefresh(value=>value+1)}>恢复已保存字段</button><Link className="text-link" to="/profile">修改露营资料 ↗</Link></section>}<section className={'panel result-panel'+(confirmed?' confirmed-summary':'')}><div className="panel-title"><h2>{confirmed?'确认快照':'待确认摘要'}</h2>{record.summary&&<span className="tag">{record.summary.execution_mode.toUpperCase()}</span>}</div>{dirty?<p className="muted">先保存修改并重新生成摘要。</p>:requirements?<><dl className="summary-list">{[['目的地',requirements.destination],['开始日期',requirements.start_date],['行程长度',`${requirements.duration_nights??'未知'} 晚 / ${requirements.duration_days??'未知'} 天`],['结束日期',requirements.end_date],['小组预算 AUD',requirements.budget_cents===null||requirements.budget_cents===undefined?'未知':(requirements.budget_cents/100).toFixed(2)]].map(([label,value])=><div key={label}><dt>{label}</dt><dd>{value??'未提供'}</dd></div>)}</dl>{requirements.preferences?.length>0&&<><h3>偏好</h3><ul>{requirements.preferences.map((item,index)=><li key={index}>{item}</li>)}</ul></>}{requirements.mandatory_constraints?.length>0&&<><h3>必须满足</h3><ul>{requirements.mandatory_constraints.map((item,index)=><li key={index}>{item}</li>)}</ul></>}{!confirmed&&(record.summary?.field_errors.length||record.summary?.clarifications.length)?<div className="clarifications"><h3>需要明确的问题</h3>{record.summary?.clarifications.map((item,index)=><p key={index}>○ {item.question}</p>)}{record.summary?.field_errors.filter(item=>!record.summary?.clarifications.some(question=>question.field===item.field)).map((item,index)=><p key={index}>{item.message}</p>)}</div>:null}<h3>本次采用的露营资料</h3><ProfileSummary profile={profile}/>{record.summary?.uncertainties.map((item,index)=><p className="muted" key={index}>{item}</p>)}</>:<p className="muted">生成摘要后，会在这里展示需求、资料与待澄清问题。</p>}{record.error&&<p className="error-box" role="alert">{record.error.message}</p>}{!confirmed&&<><label className="checkbox-label acknowledgement"><input type="checkbox" checked={acknowledged} disabled={busy||dirty||record.status!=='AWAITING_CONFIRMATION'} onChange={event=>setAcknowledged(event.target.checked)}/>我已阅读本次需求和资料，确认以上内容。</label><button className="primary-button" disabled={busy||dirty||!acknowledged||record.status!=='AWAITING_CONFIRMATION'} onClick={confirm}>确认并保存需求 <span>✓</span></button></>}{confirmed&&<><p className="success-box">此快照已保存。后续修改露营资料不会改写它。</p><>{record.planning_plan_id?<Link className="primary-button" to={'/plans/'+record.planning_plan_id}>查看规划进度与方案 ↗</Link>:<><p className="muted">{record.planning_available?'开始后可在方案页面查看保存的进度与产物。':'规划流程尚未启用，当前需求已保存。'}</p><button className="primary-button" disabled={busy||!record.planning_available} onClick={startPlanning}>{busy?'正在提交…':record.planning_available?'开始规划':'开始规划 · 待流程接入'}</button></>}</><Link className="text-link" to="/request">需求有变化？新建请求 ↗</Link></>}</section></div>}<Link className="text-link" to="/request">返回请求列表 ↗</Link></>;
}
