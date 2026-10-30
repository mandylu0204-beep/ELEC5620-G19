import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Link, useParams } from 'react-router-dom';
import { blockerText } from './plan_language';
import { ApiFailure } from './api';
import { aud, campName, PlanView, useSavedRead, type PlanDetail } from './plans';
import { privateApi, useSession } from './session';

const noPoll=()=>false;
export const historicalReviewNotice=(scope?:string)=>scope==='HISTORY'?'这是旧结果的审核记录，已由后继方案取代，不授权当前方案，也不能据此保存当前最终方案。':null;
const names:Record<string,string>={ESCALATED:'需要人工判断',BLOCKED:'有阻止条件',REVISION_REQUIRED:'需要修订'};
const labels:Record<string,string>={HIGH:'高',MEDIUM:'中',LOW:'低',UNKNOWN:'未知',WEATHER:'天气',FIRE:'营火限制',ROAD:'道路',RESTRICTION:'营地限制',MISSING:'缺失',STALE:'过期',CONFLICTING:'冲突'};
const label=(value:string|null|undefined)=>value?labels[value]??value:'未知';
type ReviewRow={task_kind?:'ASSISTANCE'|'RISK_APPROVAL';plan_id:string;plan_version_id:string;run_id:string;version_number:number;status:string;created_at:string;owner_display_name:string|null;summary?:{campsite_ids:string[];destination:string|null;start_date:string|null;end_date:string|null;total_cents:number|null;budget_difference_cents:number|null;risk_level:string|null;confidence:string|null;data_quality:Record<string,string>;blocking_reasons:{code:string;message:string}[]}};
type ReviewDetail=PlanDetail & {owner_display_name?:string|null;review_scope?:'HISTORY'|'APPROVAL'|'CORRECTION'};
type ReviewReply={review:PlanDetail['reviews'][number];status:string};
const DECISIONS=[{value:'APPROVE',title:'批准',description:'完成审核，交由露营者确认保存。'},{value:'REQUEST_REVISION',title:'要求修订',description:'指出需要调整的安排，再重新评估。'},{value:'REJECT',title:'拒绝',description:'这份方案不予通过，请说明原因。'}];

function queueIssues(row:ReviewRow) {
  const summary=row.summary;
  if(!summary)return ['进入详情查看评估依据。'];
  const reasons=summary.blocking_reasons.filter(item=>item.code!=='REVIEW_REQUIRED');
  const specific=reasons.filter(item=>!['VERSION_STATE_BLOCKED','REVISION_REQUIRED'].includes(item.code));
  const quality=Object.entries(summary.data_quality).filter(([,status])=>status!=='AVAILABLE').map(([kind,status])=>`${label(kind)}证据${label(status)}`);
  const cost=summary.budget_difference_cents!=null&&summary.budget_difference_cents>0?[`行程估算超预算 ${aud(summary.budget_difference_cents)}`]:[];
  return [...new Set([...specific.map(item=>blockerText(item.code)),...quality,...cost,...reasons.filter(item=>!specific.includes(item)).map(item=>blockerText(item.code))])];
}

export function ReviewQueue(){
  const {data,error,refresh}=useSavedRead<{reviews:ReviewRow[]}>('/review-queue',noPoll);
  const {data:help,error:helpError,refresh:refreshHelp}=useSavedRead<{plans:ReviewRow[]}>('/assistance-queue',noPoll);
  const [filter,setFilter]=useState('judgement');
  const rows=[...(data?.reviews??[]),...(help?.plans??[])];
  const displayed=filter==='judgement'?(data?.reviews??[]):(help?.plans??[]);
  return <div className="review-page"><div className="onboarding-heading"><div><span className="eyebrow">方案审核</span><h1>让每一次出行更有依据。</h1><p>查看已完成评估的方案，核对风险与证据，再作出审核决定。</p></div><button className="secondary-button" onClick={()=>{refresh();refreshHelp();}}>刷新审核队列</button></div>
    {error&&<p className="error-box" role="alert">{error}</p>}
    {helpError&&<p className="error-box" role="alert">{helpError}</p>}
    {data&&<><div className="review-queue-stats"><div><span>待处理方案</span><strong>{rows.length}</strong></div><div><span>需要人工判断</span><strong>{data.reviews.length}</strong></div><div><span>需先处理问题</span><strong>{help?.plans.length??0}</strong></div></div><div className="review-filters" role="group" aria-label="筛选审核队列">{[['judgement','待风险审批'],['problems','修正／协助（不可审批）']].map(([value,title])=><button className="secondary-button" key={value} aria-pressed={filter===value} onClick={()=>setFilter(value)}>{title}</button>)}</div></>}
    {!data?<section className="panel"><p>正在读取审核队列…</p></section>:displayed.length?<div className="review-card-grid">{displayed.map(row=>{const summary=row.summary;const issues=queueIssues(row);return <Link className="panel review-card" key={row.plan_id} to={'/review/'+row.plan_id}><div className="review-card-top"><span className={'review-queue-status '+(row.status==='ESCALATED'?'review-judgement':'review-problem')}>{names[row.status]??row.status}</span><span className="review-version">版本 {row.version_number}</span></div><h2>{summary?.campsite_ids.map(campName).join(' / ')||summary?.destination||'露营方案'}</h2><p className="review-owner">由 {row.owner_display_name??'露营者'} 提交</p><p className="review-dates">{summary?.start_date??'日期未知'} — {summary?.end_date??'日期未知'}</p><div className="review-card-facts"><span>行程费用估算<strong>{aud(summary?.total_cents)}</strong></span><span>风险 / 置信度<strong>{label(summary?.risk_level)} / {label(summary?.confidence)}</strong></span></div>{issues.length?<div className="review-card-issues"><strong>需要处理的问题</strong><ul>{issues.slice(0,3).map(message=><li key={message}>{message}</li>)}</ul>{issues.length>3&&<small>另有 {issues.length-3} 项，进入详情查看。</small>}</div>:<p className="review-card-note">核对风险和评估证据后，作出审核决定。</p>}<span className="review-card-action">{row.task_kind==='ASSISTANCE'?'查看问题（不可审批）':'查看依据并审核'} <span aria-hidden="true">↗</span></span></Link>;})}</div>:<section className="panel review-queue-empty"><span aria-hidden="true">✓</span><h2>{rows.length?'此分类暂无方案':'暂无待审核方案'}</h2><p>{rows.length?'可以切换到其他分类。':'已处理的审核决定保留在方案记录中。'}</p></section>}
  </div>;
}

export function ReviewPage(){
  const {planId}=useParams(); const {session,reload}=useSession();
  const {data,error,refresh}=useSavedRead<ReviewDetail>('/review/'+planId,noPoll);
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
    catch(value){setFault(value instanceof ApiFailure?value.message:'连接失败，可保持内容再次提交。');setFaultTrace(value instanceof ApiFailure?value.envelope.trace_id:'');if(value instanceof ApiFailure&&value.envelope.error.code==='UNAUTHENTICATED')reload();}
    finally{submitting.current=false;setBusy(false);}
  }
  const submitHint=busy?'正在保存审核…':decision==='APPROVE'&&approvalBlocked?'当前问题不能由批准解除，请先处理。':!decision?'请选择一个审核决定。':!reason.trim()?'请填写具体理由，帮助露营者理解你的决定。':'核对决定和理由后，保存本次审核。';
  const outcomeTitle=savedReview?.decision==='APPROVE'?'已批准这份方案':savedReview?.decision==='REQUEST_REVISION'?'已要求修订':'审核未通过';
  const outcomeHint=historicalReviewNotice(data?.review_scope)??(savedReview?.decision==='APPROVE'?(data?.version?.status==='FINALISED'?'露营者已保存最终方案。':data?.current_inputs_error||data?.eligibility?.eligible===false?'当前评估或证据已变化，需要重新评估后再继续。':'审核已保存，露营者还需要核对并最终保存方案。'):savedReview?.decision==='REQUEST_REVISION'?'露营者需要按理由修订方案，再重新评估；日期、人数或预算变化时需重新确认需求。':'露营者可根据理由调整方案；需求变更后需重新确认。' );
  const actions=<section className="panel review-decision-panel" id="review-decision-panel"><div className="section-title"><span className="eyebrow">本次审核</span><h2>{savedReview?'本次审核结果':'提交审核决定'}</h2></div>
    {fault&&<div className="error-box" role="alert"><p>{fault}</p>{faultTrace&&<details><summary>错误详情</summary><p className="identifier">追踪号：{faultTrace}</p></details>}<button type="button" onClick={refresh}>刷新评估依据</button></div>}
    {savedReview?<div className={'review-result '+(savedReview.decision==='APPROVE'?'review-result-approved':'review-result-change')} role="status"><h3>{outcomeTitle}</h3><p>{outcomeHint}</p><blockquote>{savedReview.reason}</blockquote></div>:data?.review_available?<>
      {approvalBlocked&&<div className="review-approval-warning" id="review-approval-hint"><h3>当前不能批准</h3><p>请先处理以下问题，或选择要求修订、拒绝。</p><ul>{approvalReasons.length?approvalReasons.map((item,index)=><li key={index}>{blockerText(item.code)}</li>):<li>{data.current_inputs_error??'审核所需评估信息尚不完整。'}</li>}</ul><details><summary>查看原始条件记录</summary>{approvalReasons.map((item,index)=><p key={index}>{item.code} · {item.message}</p>)}</details></div>}
      <form onSubmit={submit}><fieldset disabled={busy}><legend>审核决定</legend><div className="review-decision-choices">{DECISIONS.map(item=><label className={'review-choice '+(decision===item.value?'review-choice-selected':'')} key={item.value}><input type="radio" name="review-decision" aria-label={item.title} value={item.value} checked={decision===item.value} disabled={item.value==='APPROVE'&&approvalBlocked} aria-describedby={item.value==='APPROVE'&&approvalBlocked?'review-approval-hint':undefined} onChange={()=>setDecision(item.value)}/><span><strong>{item.title}</strong><small>{item.description}</small></span></label>)}</div><label htmlFor="review-reason">审核理由 <span className="required-mark">必填</span></label><textarea id="review-reason" value={reason} maxLength={4000} required onChange={e=>setReason(e.target.value)} placeholder="说明你核对了哪些风险，以及需要保留或修改的安排。"/><div className="review-submit-row"><p id="review-submit-hint" className="action-hint" role="status">{submitHint}</p><button className="primary-button" disabled={busy||!decision||!reason.trim()||(decision==='APPROVE'&&approvalBlocked)} aria-describedby="review-submit-hint">{busy?'正在保存…':'保存审核决定'} <span>✓</span></button></div></fieldset></form>
    </>:<div className="review-unavailable"><h3>当前方案暂不能审核</h3><p>{data?.current_inputs_error??(data?.review_scope==='CORRECTION'?'这是修正／协助事项，不是待审批任务。用户需补充资料或修改安排并完成新检查，审批不能解除硬性缺口。':data?.review_scope==='HISTORY'?'本次出行已有后继方案，旧审核任务已被取代；此处仅保留历史。':'当前运行或评估已变化，请刷新后核对。')}</p></div>}
  </section>;
  return <div className="review-page">{data?<><div className="review-context-bar"><span><strong>人工审核</strong> · 由 {data.owner_display_name??'露营者'} 提交</span>{!savedReview&&data.review_available&&<button className="secondary-button" onClick={()=>{document.getElementById('review-decision-panel')?.scrollIntoView({block:'start'});document.querySelector<HTMLInputElement>('.review-choice input:not(:disabled)')?.focus();}}>前往审核决定 ↓</button>}</div><PlanView data={data} error={error} refresh={refresh} review reviewActions={actions}/></>:<section className="panel"><h1>{receipt?.planId===planId?'审核已保存，正在更新记录':'读取审核依据'}</h1>{error&&<p className="error-box" role="alert">{error}</p>}<button className="secondary-button" onClick={refresh}>重新读取</button><Link className="text-link" to="/review">返回审核队列 ↗</Link></section>}</div>;
}
