import { useRef,useState } from 'react';
import { Link,useNavigate } from 'react-router-dom';
import { ApiFailure } from './api';
import { ProfileSummary, type Profile } from './profile';
import { profileChanges } from './profile_changes';
import { privateApi,useSession } from './session';
import { ReplanSession,type ReplanRequest,type SuccessorSource } from './replan_session';
import { termLabel } from './user_terms';

export function ProfileAdoptionPreview({before,after,revision,sourceRevision}:{before:Profile;after:Profile;revision:number|null;sourceRevision:number|null}){
  const changes=profileChanges(before,after);
  return <section aria-label="采用资料的差异"><h3>本次采用资料 revision {revision??'未知'}</h3>
    <p>原方案资料 revision：{sourceRevision??'历史记录未登记'}。以下仅为资料对比，不代表正式检查通过。</p>
    {changes.length?changes.map(change=><details key={change.section} open><summary>{change.section}有变化</summary><div className="bottom-grid">
      <div><h4>原方案采用</h4><ul>{change.before.map((line,index)=><li key={index}>{line}</li>)}</ul></div>
      <div><h4>本次拟采用</h4><ul>{change.after.map((line,index)=><li key={index}>{line}</li>)}</ul></div>
    </div></details>):<p>资料内容与原方案一致；重新规划仍会生成后继方案并执行正式检查。</p>}
  </section>;
}

export function ReplanFromProfile({source,previousProfile,refreshSource}:{source:SuccessorSource;previousProfile:Profile;refreshSource:()=>void}) {
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
    try{setRecord(await sessionFlow().prepare(source));}catch(reason){fail(reason);}
    finally{locked.current=false;setBusy(false);}
  }
  async function start(){
    if(locked.current||!ack)return;locked.current=true;setBusy(true);setError('');
    try{const result=await sessionFlow().start(ack);navigate('/plans/'+result.plan_id+'?run_id='+encodeURIComponent(result.run_id));}
    catch(reason){setRecord(flow.current?.record??null);if(flow.current?.previewStale)setAck(false);fail(reason);}
    finally{locked.current=false;setBusy(false);}
  }
  const value=record?.confirmed_context?.requirements??record?.summary?.extracted_requirements;
  const profile=record?.confirmed_context?.profile_snapshot??record?.profile_snapshot??null;
  const stale=flow.current?.previewStale===true;
  const ready=!stale&&!!record&&['AWAITING_CONFIRMATION','CONFIRMED'].includes(record.status);
  return <section className="panel replan-panel" aria-label="使用最新资料重新规划">
    <div className="logistics-todos-heading"><div><h2>采用新资料，更新本次出行</h2><p>保留目的地、日期、预算和偏好，核对资料差异后创建同一次出行的后继方案。原确认快照、检查和最终记录保留；仅保存个人资料不会开始检查。</p></div>
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
        <ProfileAdoptionPreview before={previousProfile} after={profile} revision={record?.profile_revision??null} sourceRevision={flow.current?.sourceProfileRevision??null}/>
        <details><summary>查看同行、车辆与装备明细</summary><ProfileSummary profile={profile}/></details></>}
      {record&&!ready&&<p className="error-box" role="alert">{stale?'资料或来源已变化，请重新载入资料差异并再次确认。':'原请求仍有待核对的信息，请查看并调整已保留的需求。'}</p>}
      {ready&&<><label className="checkbox-label"><input type="checkbox" checked={ack} disabled={busy} onChange={event=>setAck(event.target.checked)}/>我已核对本次安排及最新资料，确认重新规划。</label>
        <button className="primary-button" disabled={busy||!ack} onClick={start}>确认并重新规划 ↗</button></>}
      <div className="plan-actions">{(!record||error)&&<button className="secondary-button" disabled={busy} onClick={prepare}>重新载入</button>}
        {stale&&<button className="secondary-button" disabled={busy} onClick={refreshSource}>重新读取来源方案</button>}
        {record&&<Link className="text-link" to={'/request/'+record.request_id}>需要修改日期或偏好？查看已保留的需求 ↗</Link>}
        <button className="text-button" disabled={busy} onClick={()=>{setOpen(false);setAck(false);}}>取消</button></div>
    </div>}
  </section>;
}
