import { useRef,useState } from 'react';
import { Link,useNavigate } from 'react-router-dom';
import { ApiFailure,type Requirements } from './api';
import { ProfileSummary } from './profile';
import { privateApi,useSession } from './session';
import { ReplanSession,type ReplanRequest } from './replan_session';
import { termLabel } from './user_terms';

export function ReplanFromProfile({requestId,requirements}:{requestId:string;requirements:Requirements}) {
  const {session,reload}=useSession();const navigate=useNavigate();
  const flow=useRef<ReplanSession|null>(null);const locked=useRef(false);
  const [open,setOpen]=useState(false);const [busy,setBusy]=useState(false);
  const [record,setRecord]=useState<ReplanRequest|null>(null);const [error,setError]=useState('');
  const [ack,setAck]=useState(false);
  function fail(reason:unknown){setError(reason instanceof Error?reason.message:'无法完成操作，请重试。');
    if(reason instanceof ApiFailure&&reason.envelope.error.code==='UNAUTHENTICATED')reload();}
  function sessionFlow(){
    if(!flow.current)flow.current=new ReplanSession((path,body)=>privateApi(path,body===undefined?{}:{method:'POST',
      headers:{'Content-Type':'application/json','X-CampMate-Client':'1','X-CSRF-Token':session?.csrf_token??''},body:JSON.stringify(body)}),()=>crypto.randomUUID());
    return flow.current;
  }
  async function prepare(){
    if(locked.current||!session)return;locked.current=true;setBusy(true);setOpen(true);setAck(false);setError('');setRecord(null);
    try{setRecord(await sessionFlow().prepare(requestId,requirements));}catch(reason){fail(reason);}
    finally{locked.current=false;setBusy(false);}
  }
  async function start(){
    if(locked.current||!ack)return;locked.current=true;setBusy(true);setError('');
    try{const result=await sessionFlow().start(ack);navigate('/plans/'+result.plan_id+'?run_id='+encodeURIComponent(result.run_id));}
    catch(reason){setRecord(flow.current?.record??null);fail(reason);}
    finally{locked.current=false;setBusy(false);}
  }
  const value=record?.confirmed_context?.requirements??record?.summary?.extracted_requirements;
  const profile=record?.confirmed_context?.profile_snapshot??record?.profile_snapshot??null;
  const ready=!!record&&['AWAITING_CONFIRMATION','CONFIRMED'].includes(record.status);
  return <section className="panel replan-panel" aria-label="使用最新资料重新规划">
    <div className="logistics-todos-heading"><div><h2>更新资料后，重新规划</h2><p>保留本次目的地、日期、预算和偏好，使用最新保存的露营资料生成新方案。此操作不会更新原方案的确认快照或替换原检查；核对并确认后，新方案还需完成检查。</p></div>
      {!open&&<button className="primary-button" disabled={busy} onClick={prepare}>使用最新资料重新规划 ↗</button>}</div>
    {open&&<div className="replan-preview">
      {busy&&<p role="status">正在处理，请稍候…</p>}
      {error&&<p className="error-box" role="alert">{error}</p>}
      {value&&<><h3>核对本次安排</h3><dl className="summary-list"><div><dt>目的地</dt><dd>{value.destination}</dd></div>
        <div><dt>出行日期</dt><dd>{value.start_date} — {value.end_date} · {value.duration_nights} 晚</dd></div>
        <div><dt>小组预算</dt><dd>AUD {value.budget_cents==null?'未知':(value.budget_cents/100).toFixed(2)}</dd></div>
        <div><dt>偏好</dt><dd>{value.preferences.map(item=>termLabel(item,'preference')).join('、')||'无'}</dd></div>
        <div><dt>必须条件</dt><dd>{value.mandatory_constraints.map(item=>termLabel(item,'constraint')).join('、')||'无'}</dd></div></dl></>}
      {profile&&<><h3>本次采用的最新露营资料</h3><p>{profile.group_size??'未知'} 人同行 · {profile.equipment.filter(item=>!['vehicle','charged_phone'].includes(item.item_key)).length} 项装备{profile.transport.transport_type==='CAR'&&` · ${profile.transport.vehicle_count??'未知'} 辆车`}</p>
        <details><summary>查看同行、车辆与装备明细</summary><ProfileSummary profile={profile}/></details></>}
      {record&&!ready&&<p className="error-box" role="alert">原请求仍有待核对的信息，请查看并调整已保留的需求。</p>}
      {ready&&<><label className="checkbox-label"><input type="checkbox" checked={ack} disabled={busy} onChange={event=>setAck(event.target.checked)}/>我已核对本次安排及最新资料，确认重新规划。</label>
        <button className="primary-button" disabled={busy||!ack} onClick={start}>确认并重新规划 ↗</button></>}
      <div className="plan-actions">{(!record||error)&&<button className="secondary-button" disabled={busy} onClick={prepare}>重新载入</button>}
        {record&&<Link className="text-link" to={'/request/'+record.request_id}>需要修改日期或偏好？查看已保留的需求 ↗</Link>}
        <button className="text-button" disabled={busy} onClick={()=>{setOpen(false);setAck(false);}}>取消</button></div>
    </div>}
  </section>;
}
