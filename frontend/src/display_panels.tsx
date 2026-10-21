import { useState } from 'react';
import { chineseProse, discardMessage, tentSummary, type TentCapacity } from './display_facts';
import { ModelTracePanel, type ModelTrace } from './model_trace';

export function TentCapacityPanel({value}:{value:TentCapacity|null|undefined}){
  if(!value)return null;
  return <section className="tent-capacity" aria-label="帐篷住宿容量"><h3>帐篷按总住宿容量核对</h3><p>{tentSummary(value)}</p>
    <div className="table-scroll"><table><caption>本次确认的帐篷登记（不同容量分行）</caption><thead><tr><th>帐篷数量</th><th>每顶容量</th><th>该行总容量</th><th>拥有情况</th></tr></thead><tbody>
      {value.records.map((row,index)=><tr key={index}><td>{row.unit==='item'?`${row.quantity??'未知'} 顶`:'数量单位待核对'}</td><td>{row.capacity_per_tent??'未知'} 人</td><td>{row.total_capacity??'未知'} 人</td><td>{row.confirmed?'已核实拥有':'未核实拥有'}</td></tr>)}
    </tbody></table></div>{!value.records.length&&<p>尚未登记帐篷。</p>}
    <p>同行 {value.group_size??'未知'} 人 · 登记共 {value.registered_tent_count??'未知'} 顶 · 登记总容量 {value.registered_capacity??'未知'} 人 · 检查认可容量 {value.assessed_capacity??'未知'} 人 · 缺少 {value.missing_person_spaces??'未知'} 人位</p>
    <p className="muted">登记容量不等于已确认可用容量；未核实的装备不会因此变为可用。人数不是需要购买的帐篷顶数。</p>
  </section>;
}

export function DiscardChanges({sections,busy=false,onDiscard}:{sections:string[];busy?:boolean;onDiscard:()=>void}){
  const [confirm,setConfirm]=useState(false);
  return <><button type="button" className="secondary-button" disabled={busy||!sections.length} onClick={()=>setConfirm(true)}>放弃未保存修改</button>
    {confirm&&sections.length>0&&<div className="mode-notice" role="alertdialog" aria-label="确认放弃未保存修改"><p>{discardMessage(sections)}</p>
      <button type="button" className="secondary-button" disabled={busy} onClick={()=>{setConfirm(false);onDiscard();}}>确认放弃并重新读取</button>
      <button type="button" className="secondary-button" disabled={busy} onClick={()=>setConfirm(false)}>继续编辑</button></div>}</>;
}

export type PlanningExplanation={source_run_id:string;selected_campsite_id:string;decision_summary_unverified:string};
export function PlanningExplanationPanel({value,currentRunId,siteName,reasons,uncertainties}:{value?:PlanningExplanation|null;currentRunId?:string;siteName:string;reasons:string[];uncertainties:string[]}){
  const summary=chineseProse(value?.decision_summary_unverified);
  const visibleReasons=reasons.map(text=>chineseProse(text)).filter((text):text is string=>text!==null);
  const visibleUncertainties=uncertainties.map(text=>chineseProse(text)).filter((text):text is string=>text!==null);
  return <section className="panel" aria-label="营地选择与待确认事项"><h2>为什么选择 {siteName}</h2>
    {value&&<p className="muted">{value.source_run_id!==currentRunId?'以下是原版本生成时的模型意见，本次重评复用原行程。':'以下为已保存的模型选择意见，未经人工核实。'}</p>}
    {summary&&<p>{summary}</p>}{visibleReasons.length>0&&<><h3>筛选记录：适合当前需求的原因</h3><ul>{visibleReasons.map((text,index)=><li key={index}>{text}</li>)}</ul></>}
    {!summary&&!visibleReasons.length&&<p>选择理由已保存在下方原始记录中；原文未提供可直接展示的中文说明，请核对日期、同行人数、预算与必须条件，不将选择意见视为已核实承诺。</p>}
    <h3>出发前待确认</h3><ul>{visibleUncertainties.map((text,index)=><li key={index}>{text}</li>)}<li>营位预订、实际入住时间、交通安排及最新限制仍需确认。</li></ul>
    {(value||reasons.length>0||uncertainties.length>0)&&<details><summary>查看已保存的选择理由与待确认事项原文</summary>{value&&<p>{value.decision_summary_unverified}</p>}<h3>适合需求的原始理由</h3><ul>{reasons.map((text,index)=><li key={index}>{text}</li>)}</ul><h3>原始待确认事项</h3><ul>{uncertainties.map((text,index)=><li key={index}>{text}</li>)}</ul></details>}
  </section>;
}

export type ModelDiagnostics={planning:ModelTrace|null;assessments:Record<string,unknown>;dataset_context?:unknown};
export function ModelRunDiagnostics({allowed,value,currentRunId}:{allowed?:boolean;value?:ModelDiagnostics;currentRunId?:string}){
  if(!allowed||!value)return null;
  return <section className="panel" aria-label="模型运行诊断"><details><summary>模型运行诊断（审核权限）</summary><p>仅用于运行排查，不属于露营费用，也不代表安全或保存资格。</p>
    <ModelTracePanel value={value.planning} currentRunId={currentRunId} logisticsModel={!!value.assessments.LOGISTICS} safetyModel={!!value.assessments.SAFETY}/>
    {Object.entries(value.assessments).map(([role,record])=><details key={role}><summary>{role==='LOGISTICS'?'装备与预算':role==='SAFETY'?'安全':'其他角色'}模型诊断</summary><pre className="diagnostic-json">{JSON.stringify(record,null,2)}</pre></details>)}
    <details><summary>运行配置与资料身份</summary><pre className="diagnostic-json">{JSON.stringify(value.dataset_context,null,2)}</pre></details>
  </details></section>;
}
