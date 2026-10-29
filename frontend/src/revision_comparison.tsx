import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { ApiFailure } from './api';
import { privateApi, useSession } from './session';
import { campName } from './campsite_names';
import { aud } from './plans';

type ComparedPlan={run:{run_id:string;status:string;stage:string;revision:number};version_id:string|null;version_number:number|null;
  campsite_ids:string[];duration_nights:number;nightly_fee_cents:number|null;camp_fee_cents:number|null;total_cents:number|null;safety_outcome?:string|null};
export type RevisionComparisonData={proposal_id:string;revision:number;decision:'ADOPT'|'KEEP'|null;legacy?:boolean;
  status:'GENERATING'|'READY'|'FAILED'|'ADOPT'|'KEEP';before:ComparedPlan;after:ComparedPlan;
  can_adopt:boolean;can_keep:boolean;camp_saving_cents:number|null;total_saving_cents:number|null};

export function savingsText(value:number|null,subject:string){
  return value===null?`${subject}暂无法比较`:value>0?`${subject}预计节省 ${aud(value)}`
    :value<0?`${subject}预计增加 ${aud(-value)}`:`${subject}没有变化`;
}

export function RevisionComparison({value,planId,refresh,readOnly=false}:{value:RevisionComparisonData|null|undefined;planId:string;refresh:()=>void;readOnly?:boolean}){
  const {session,reload}=useSession();
  const navigate=useNavigate();
  const [busy,setBusy]=useState(false);const [error,setError]=useState('');
  const command=useRef<{payload:string;key:string}|null>(null);
  useEffect(()=>setError(''),[value?.proposal_id,value?.decision]);
  if(!value)return null;
  const pending=!value.decision;
  const safety=(outcome:string|null|undefined)=>({PASSED:'检查通过',REVIEW:'待核实',REVISION:'需要调整',BLOCKED:'条件未满足'} as Record<string,string>)[outcome??'']??'尚未完成';
  const row=(title:string,field:'nightly_fee_cents'|'camp_fee_cents'|'total_cents')=><tr><th scope="row">{title}</th>
    <td>{aud(value.before[field])}</td><td>{aud(value.after[field])}</td></tr>;
  async function choose(decision:'ADOPT'|'KEEP'){
    if(!session||busy||!value)return;
    const body={decision,expected_proposal_revision:value.revision,expected_candidate_run_revision:value.after.run.revision};
    const payload=JSON.stringify({proposal:value.proposal_id,...body});
    if(command.current?.payload!==payload)command.current={payload,key:crypto.randomUUID()};
    setBusy(true);setError('');
    try{
      await privateApi('/plans/'+encodeURIComponent(planId)+'/revision-proposals/'+encodeURIComponent(value.proposal_id)+'/decision',{
        method:'POST',headers:{'Content-Type':'application/json','X-CampMate-Client':'1','X-CSRF-Token':session.csrf_token},
        body:JSON.stringify({...body,command_key:command.current.key})});
      navigate('/plans/'+encodeURIComponent(planId));refresh();
    }catch(reason){
      setError(reason instanceof Error?reason.message:'选择结果暂未确认，请刷新查看或重试同一次选择。');
      if(reason instanceof ApiFailure&&reason.envelope.error.code==='UNAUTHENTICATED')reload();
    }finally{setBusy(false);}
  }
  return <section className="panel revision-comparison" aria-label="新旧方案对比">
    <div className="section-title"><span className="eyebrow">方案对比</span><h2>{value.legacy?'当前方案与上一版对比':value.decision==='ADOPT'?'已采用新方案':value.decision==='KEEP'?'已保留原方案':'选择适合你的方案'}</h2></div>
    {value.status==='GENERATING'?<p role="status">正在生成待选方案，原方案仍保留为当前方案。</p>
      :value.status==='FAILED'?<p role="status">新方案未完成，原方案不受影响。你可以保留原方案。</p>
      :<><p className="revision-campsites">{value.before.campsite_ids.map(campName).join(' / ')||'原营地'} → {value.after.campsite_ids.map(campName).join(' / ')||'待确认'}</p>
      <div className="table-scroll"><table><caption>费用估算对比</caption><thead><tr><th>对比项</th><th>原方案</th><th>新方案</th></tr></thead><tbody>
        <tr><th scope="row">营地</th><td>{value.before.campsite_ids.map(campName).join(' / ')}</td><td>{value.after.campsite_ids.map(campName).join(' / ')||'待确认'}</td></tr>
        {row('每晚营地费','nightly_fee_cents')}{row(`营地费合计（${value.before.duration_nights} 晚）`,'camp_fee_cents')}{row('全部费用估算','total_cents')}
        <tr><th scope="row">安全检查</th><td>{safety(value.before.safety_outcome)}</td><td>{safety(value.after.safety_outcome)}</td></tr>
      </tbody></table></div>
      <p><strong>{savingsText(value.camp_saving_cents,'营地费')}</strong></p><p>{savingsText(value.total_saving_cents,'总费用')}</p>
    </>}
    {pending&&value.status==='READY'&&<p>选择采用后，新方案才会成为当前方案。</p>}
    {value.after.version_id&&<Link className="text-link" to={'/plans/'+encodeURIComponent(planId)+'?run_id='+encodeURIComponent(value.after.run.run_id)}>查看新方案详情 ↗</Link>}
    {pending&&!readOnly&&<div className="plan-actions">
      <button className="primary-button" disabled={busy||!value.can_adopt} onClick={()=>void choose('ADOPT')}>{busy?'正在保存选择…':'采用新方案'}</button>
      <button className="secondary-button" disabled={busy||!value.can_keep} onClick={()=>void choose('KEEP')}>保留原方案</button>
    </div>}
    {error&&<p className="error-box" role="alert">{error}</p>}
  </section>;
}
