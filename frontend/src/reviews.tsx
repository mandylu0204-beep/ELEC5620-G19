import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Link, useParams } from 'react-router-dom';
import { ApiFailure } from './api';
import { PlanView, useSavedRead, type PlanDetail } from './plans';
import { privateApi, useSession } from './session';

const noPoll=()=>false;
const names:Record<string,string>={ESCALATED:'等待人工审核',BLOCKED:'禁止放行',REVISION_REQUIRED:'需要修订'};

export function ReviewQueue(){
  const {data,error,refresh}=useSavedRead<{reviews:{plan_id:string;plan_version_id:string;version_number:number;status:string}[]}>('/review-queue',noPoll);
  return <><div className="page-heading"><span className="eyebrow">FOUNDER REVIEW</span><h1>人工审核</h1><p>检查已经完成评估的当前方案。缺失证据和强制 blocker 必须先处理。</p></div><button className="secondary-button" onClick={refresh}>刷新审核队列</button>{error&&<p className="error-box" role="alert">{error}</p>}{!data?<p>正在读取…</p>:data.reviews.length?<div className="plan-cards">{data.reviews.map(row=><Link className="panel plan-card" key={row.plan_id} to={'/review/'+row.plan_id}><span className="tag">{names[row.status]??row.status}</span><h2>版本 {row.version_number}</h2><p className="identifier">{row.plan_version_id}</p><span className="text-link">查看依据并审核 ↗</span></Link>)}</div>:<section className="panel"><h2>暂无待审核记录</h2><p>已经处理的审核会保留在方案记录中。</p></section>}</>;
}

export function ReviewPage(){
  const {planId}=useParams(); const {session,reload}=useSession();
  const {data,error,refresh}=useSavedRead<PlanDetail>('/review/'+planId,noPoll);
  const [reason,setReason]=useState('');const [decision,setDecision]=useState('APPROVE');
  const [busy,setBusy]=useState(false);const [fault,setFault]=useState('');const [saved,setSaved]=useState(false);
  const pending=useRef<{key:string;payload:string}|null>(null);const submitting=useRef(false);
  useEffect(()=>{setReason('');setDecision('APPROVE');setFault('');setSaved(false);pending.current=null;},[planId,data?.version?.version_context.input_fingerprint]);
  async function submit(event:FormEvent){
    event.preventDefault();if(!data?.version||!data.run||!session||submitting.current)return;
    const input={version_context:data.version.version_context,assessment_ids:data.assessments.map(item=>item.assessment_id).sort(),expected_version_revision:data.version.revision,expected_run_revision:data.run.revision,decision,reason:reason.trim()};
    const payload=JSON.stringify(input);
    if(pending.current?.payload!==payload)pending.current={key:crypto.randomUUID(),payload};
    submitting.current=true;setBusy(true);setFault('');
    try{await privateApi('/review/'+planId,{method:'POST',headers:{'Content-Type':'application/json','X-CampMate-Client':'1','X-CSRF-Token':session.csrf_token},body:JSON.stringify({...input,command_key:pending.current!.key})});setSaved(true);refresh();}
    catch(value){setFault(value instanceof ApiFailure?`${value.message}（追踪号 ${value.envelope.trace_id}）`:'连接失败，可保持内容再次提交。');if(value instanceof ApiFailure&&value.envelope.error.code==='UNAUTHENTICATED')reload();}
    finally{submitting.current=false;setBusy(false);}
  }
  const approvalBlocked=!!data?.eligibility?.blocking_reasons.some(item=>item.code!=='REVIEW_REQUIRED');
  return <>{data?.version&&<section className="panel review-form"><h2>提交审核决定</h2><p>决定仅适用于下方版本和两份评估。批准后仍需 Camper 执行最终化。</p><details><summary>本次审核绑定</summary><p className="identifier">版本：{data.version.version_context.plan_version_id}</p><p className="identifier">运行：{data.version.version_context.run_id}</p><p className="identifier">输入指纹：{data.version.version_context.input_fingerprint}</p>{data.assessments.map(item=><p className="identifier" key={item.assessment_id}>{item.kind}：{item.assessment_id}</p>)}</details>{saved&&<p className="clarifications" role="status">审核已保存，正在回读记录。未生成最终方案。</p>}{fault&&<p className="error-box" role="alert">{fault}</p>}{data.review_available&&!saved?<form onSubmit={submit}><label htmlFor="review-decision">审核决定</label><select id="review-decision" value={decision} onChange={e=>setDecision(e.target.value)} disabled={busy}><option value="APPROVE" disabled={approvalBlocked}>批准</option><option value="REJECT">拒绝</option><option value="REQUEST_REVISION">要求修订</option></select>{approvalBlocked&&<p className="clarifications">存在不能由批准绕过的问题，请选择拒绝或要求修订。</p>}<label htmlFor="review-reason">审核理由（必填）</label><textarea id="review-reason" value={reason} maxLength={4000} required disabled={busy} onChange={e=>setReason(e.target.value)} placeholder="说明你的判断及需要修改的具体内容。"/><button className="primary-button" disabled={busy||!reason.trim()||(decision==='APPROVE'&&approvalBlocked)}>{busy?'正在保存审核…':'保存审核决定'}</button><p className="muted">要求修订会保存反馈。Camper 可在方案页发起修订；涉及日期、人数或预算变化，需要重新提交并确认需求。</p></form>:<p>本次审核已处理，或当前方案不接受审核。请查看下面的审核记录。</p>}</section>}{data?<PlanView data={data} error={error} refresh={refresh} review/>:<section className="panel"><h1>读取审核依据</h1>{error&&<p className="error-box" role="alert">{error}</p>}<button className="secondary-button" onClick={refresh}>重新读取</button><Link className="text-link" to="/review">返回审核队列 ↗</Link></section>}</>;
}
