import {useRef,useState} from 'react';
import {Link} from 'react-router-dom';
import type {PlanDetail} from './plans';
import {privateApi,useSession} from './session';
import {helpCommand} from './requirement_help';
import {tripUpdatePath} from './trip_update';

export type AssistanceNote={note_id:string;plan_id:string;run_id:string;plan_version_id:string;assessment_ids:string[];
 reviewer_user_id:string;decision:'WAITING_EVIDENCE'|'NEEDS_CAMPER_INPUT'|'UNSUPPORTED';problem:string;reason:string;next_action:string;
 recheck_on:string|null;created_at:string;is_approval:false};
const titles={WAITING_EVIDENCE:'等待资料后再检查',NEEDS_CAMPER_INPUT:'需要补充或修改安排',UNSUPPORTED:'当前系统暂不支持此安排'};
export function AssistanceNotes({notes,historical=false}:{notes:AssistanceNote[];historical?:boolean}){
  if(!notes.length)return null;
  const latest=notes.at(-1)!;
  const content=(note:AssistanceNote)=><><h3>{titles[note.decision]}</h3><dl className="assistance-feedback"><dt>问题</dt><dd>{note.problem}</dd><dt>原因</dt><dd>{note.reason}</dd><dt>下一步</dt><dd>{note.next_action}</dd></dl>{note.recheck_on&&<p>建议重查日期：{note.recheck_on}</p>}</>;
  return <section className="panel human-assistance-notes" aria-label="人工处理意见"><p className="muted">{historical?'此前结果的人工处理记录':'本次结果的人工处理意见'} · 不是批准，不会解除原评估的问题。</p>{content(latest)}
    {notes.length>1&&<details><summary>此前处理意见（{notes.length-1}）</summary>{notes.slice(0,-1).map(note=><article key={note.note_id}>{content(note)}</article>)}</details>}
  </section>;
}

export function ReviewAssistanceForm({data,refresh}:{data:PlanDetail&{assistance_available?:boolean};refresh:()=>void}){
  const {session}=useSession();const [decision,setDecision]=useState<AssistanceNote['decision']>('WAITING_EVIDENCE');
  const [problem,setProblem]=useState('');const [reason,setReason]=useState('');const [action,setAction]=useState('');const [date,setDate]=useState('');
  const [busy,setBusy]=useState(false);const [error,setError]=useState('');const [notice,setNotice]=useState('');const locked=useRef(false);
  if(!data.assistance_available||!data.version||!data.run)return null;
  async function save(){
    if(!session||!data.version||!data.run||locked.current)return;
    const body={version_context:data.version.version_context,assessment_ids:data.assessments.map(item=>item.assessment_id).sort(),
      expected_version_revision:data.version.revision,expected_run_revision:data.run.revision,decision,problem:problem.trim(),reason:reason.trim(),next_action:action.trim(),
      recheck_on:decision==='WAITING_EVIDENCE'&&date?date:null};
    locked.current=true;setBusy(true);setError('');setNotice('');
    try{
      const key=helpCommand(window.sessionStorage,`review-assistance:${session.user.user_id}:${data.run.run_id}`,body);
      await privateApi('/review/'+data.plan.plan_id+'/assistance',{method:'POST',headers:{'Content-Type':'application/json','X-CampMate-Client':'1','X-CSRF-Token':session.csrf_token},body:JSON.stringify({...body,command_key:key})});
      setNotice('处理意见已保存，正式评估和保存资格未改变。');refresh();
    }catch(value){setError(value instanceof Error?value.message:'保存未完成，请重试原操作。');}finally{locked.current=false;setBusy(false);}
  }
  return <section className="review-assistance-form" aria-label="记录修正协助"><h3>记录处理意见（不可审批）</h3><p>说明缺少什么、原因及下一步。补充资料后仍需正式检查。</p>
    <fieldset disabled={busy}><label htmlFor="assistance-decision">处理类型</label><select id="assistance-decision" value={decision} onChange={event=>setDecision(event.target.value as AssistanceNote['decision'])}>{Object.entries(titles).map(([value,title])=><option key={value} value={value}>{title}</option>)}</select>
    <label htmlFor="assistance-problem">具体问题</label><textarea id="assistance-problem" maxLength={2000} value={problem} onChange={event=>setProblem(event.target.value)}/>
    <label htmlFor="assistance-reason">判断依据／原因</label><textarea id="assistance-reason" maxLength={4000} value={reason} onChange={event=>setReason(event.target.value)}/>
    <label htmlFor="assistance-action">用户下一步</label><textarea id="assistance-action" maxLength={2000} value={action} onChange={event=>setAction(event.target.value)}/>
    {decision==='WAITING_EVIDENCE'&&<><label htmlFor="assistance-date">建议重查日期（可选）</label><input id="assistance-date" type="date" value={date} onChange={event=>setDate(event.target.value)}/></>}
    <button type="button" className="primary-button" disabled={busy||!problem.trim()||!reason.trim()||!action.trim()} onClick={()=>void save()}>{busy?'正在保存…':'保存处理意见'}</button></fieldset>
    {error&&<p className="error-box" role="alert">{error}</p>}{notice&&<p role="status">{notice}</p>}
  </section>;
}

export function AssistanceNextAction({data,onRecheck}:{data:PlanDetail;onRecheck:()=>void}){
  const notes=data.review_assistance_notes??[];
  if(!notes.length||!data.run?.is_active||data.trip_series?.is_current===false)return null;
  const note=notes.at(-1)!;
  return <div className="plan-actions">{note.decision==='WAITING_EVIDENCE'?
    data.reassessment_available&&<button type="button" className="secondary-button" onClick={onRecheck}>查看重新检查入口 ↓</button>:
    <Link className="secondary-button" to={tripUpdatePath(data.plan.plan_id)}>核对并调整本次要求 ↗</Link>}</div>;
}
