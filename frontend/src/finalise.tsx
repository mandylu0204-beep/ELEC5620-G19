import { useRef, useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { ApiFailure } from './api';
import type { PlanDetail } from './plans';
import { privateApi, useSession } from './session';

export function FinalisePanel({data}:{data:PlanDetail}){
  const {session,reload}=useSession();const navigate=useNavigate();
  const [acknowledged,setAcknowledged]=useState(false);const [busy,setBusy]=useState(false);const [error,setError]=useState('');
  const pending=useRef<{key:string;payload:string}|null>(null);const submitting=useRef(false);
  async function submit(event:FormEvent){
    event.preventDefault();if(!data.version||!data.run||!data.finalisation_available||!acknowledged||!session||submitting.current)return;
    const input={version_context:data.version.version_context,assessment_ids:data.assessments.map(item=>item.assessment_id).sort(),expected_review_id:data.eligibility?.valid_review_id??null,expected_version_revision:data.version.revision,expected_run_revision:data.run.revision,acknowledged:true};
    const payload=JSON.stringify(input);if(pending.current?.payload!==payload)pending.current={key:crypto.randomUUID(),payload};
    submitting.current=true;setBusy(true);setError('');
    try{const value=await privateApi<{final_id:string}>('/plans/'+data.plan.plan_id+'/finalise',{method:'POST',headers:{'Content-Type':'application/json','X-CampMate-Client':'1','X-CSRF-Token':session.csrf_token},body:JSON.stringify({...input,command_key:pending.current!.key})});navigate('/plans/'+data.plan.plan_id+'/finals/'+value.final_id);}
    catch(reason){setError(reason instanceof ApiFailure?`${reason.message}（追踪号 ${reason.envelope.trace_id}）`:'保存结果暂时无法确认；可保持内容重试，或刷新查看已保存记录。');if(reason instanceof ApiFailure&&reason.envelope.error.code==='UNAUTHENTICATED')reload();}
    finally{submitting.current=false;setBusy(false);}
  }
  if(data.run&&['PENDING','RUNNING'].includes(data.run.status))return <div className="finalise-panel" role="status"><p>{data.run.operation==='REASSESS'?'正在更新检查结果，完成后即可查看是否能够保存。':'正在生成行程并完成检查，请稍候。'}</p><button className="disabled-action" disabled>{data.run.operation==='REASSESS'?'正在重新检查…':'正在规划…'}</button></div>;
  if(data.version?.status==='FINALISED')return <p>此运行的最终方案已经保存，可通过最终方案记录查看完整快照。</p>;
  return <div className="finalise-panel">{error&&<p className="error-box" role="alert">{error}</p>}{data.finalisation_available?<form onSubmit={submit}><label className="confirmation-choice"><input type="checkbox" checked={acknowledged} disabled={busy} onChange={event=>setAcknowledged(event.target.checked)}/>我已阅读行程、费用、装备与安全依据，确认保存这份方案。</label><button className="primary-button" disabled={busy||!acknowledged}>{busy?'正在保存最终方案…':'保存为最终方案'}</button></form>:<><button className="disabled-action" disabled>当前方案暂不能保存</button><p className="muted">请先处理上方列出的问题。</p></>}</div>;
}
