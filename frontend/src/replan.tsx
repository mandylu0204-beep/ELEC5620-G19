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
  return <section aria-label="采用资料的差异"><h3>本次采用资料 revision {revision??'未知'}</h3>
    <p>原方案资料 revision：{sourceRevision??'历史记录未登记'}。以下仅为资料对比，不代表正式检查通过。</p>
    {changes.length?changes.map(change=><details key={change.section} open><summary>{change.section}有变化</summary><div className="bottom-grid">
      <div><h4>原方案采用</h4><ul>{change.before.map((line,index)=><li key={index}>{line}</li>)}</ul></div>
      <div><h4>本次拟采用</h4><ul>{change.after.map((line,index)=><li key={index}>{line}</li>)}</ul></div>
    </div></details>):<p>资料内容与原方案一致；重新规划仍会生成后继方案并执行正式检查。</p>}
  </section>;
}

export function ReplanFromProfile({source}:{source:SuccessorSource;previousProfile:Profile;refreshSource:()=>void}) {
  return <section className="panel replan-panel" aria-label="使用最新资料重新规划">
    <h2>更新本次出行</h2><p>资料与需求修改使用同一个核对入口，仍归于这次出行。仅保存不会开始检查；确认后会重新规划，营地和行程可能改变。原检查与最终记录保留。</p>
    <Link className="primary-button" to={tripUpdatePath(source.plan_id)}>核对修改并更新本次出行 ↗</Link>
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
      }catch(reason){if(!cancelled){setDeletedDraft((reason as {deletedUpdateDraft?:boolean})?.deletedUpdateDraft===true);setError(reason instanceof ApiFailure?reason.message:reason instanceof Error?reason.message:'无法准备更新，请重试。');}}
    }
    void open();
    return()=>{cancelled=true;};
  },[planId,session,navigate,focus,retry,location.state?.profileSaved]);
  async function newDraft(){
    if(!session||!planId)return;
    try{await forgetDeletedTripUpdate(<T,>(path:string)=>privateApi<T>(path),window.sessionStorage,session.user.user_id,planId);setRetry(value=>value+1);}
    catch(reason){setError(reason instanceof Error?reason.message:'来源无法核对，请返回当前方案。');}
  }
  return <section className="panel"><h1>核对本次更新</h1><p>保留原需求，准备同一次出行的更新草稿；不会自动启动模型或检查。</p>
    {error?<><p className="error-box" role="alert">{error}</p>{deletedDraft?<><p>原更新草稿可能已删除。不会自动恢复已删除记录；仅在来源仍有效时，可明确创建另一份本次更新草稿。</p><button onClick={newDraft}>明确新建本次更新草稿</button></>:<button onClick={()=>setRetry(value=>value+1)}>重试原更新命令</button>}</>:<p role="status">正在读取…</p>}
    <Link className="text-link" to={'/plans/'+encodeURIComponent(planId??'')}>取消并返回原方案 ↗</Link></section>;
}
