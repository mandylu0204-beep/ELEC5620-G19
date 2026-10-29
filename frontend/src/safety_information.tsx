import type { ReactNode } from 'react';
import type { Safety, Source } from './plans';
import type { Requirements } from './api';
import { checkNames,safetyCondition,safetySummary,safetyRegulations } from './plan_language';
import { TripCoveragePanel, type TripCoverage } from './trip_coverage';

export function SafetyInformation({value,requirements,summary,approved,review,outdated,blockers,notes,rawWarnings,sources,label,coverage,requestId,planId,readOnly=false,advisory}:{
  value:Safety|undefined;requirements:Requirements|undefined;summary:string;approved:boolean;review:boolean;outdated:boolean;
  blockers:ReactNode;notes:ReactNode;rawWarnings:{code:string;message:string}[];sources:(refs:Source[])=>ReactNode;label:(value:string)=>string;
  coverage?:TripCoverage|null;requestId?:string;planId?:string;readOnly?:boolean;advisory?:ReactNode}){
  if(!value)return <section className="panel"><h2>出行安全信息</h2><p>规划完成后，会在这里显示安全检查。</p></section>;
  const codes=value.mandatory_blockers.map(item=>item.code);
  const states=Object.keys(checkNames).map(kind=>({kind,...safetyCondition(kind,value.data_quality[kind]??'MISSING',value.evidence,requirements,codes)}));
  return <section className="panel"><div className="section-title"><span className="eyebrow">出发前核对</span><h2>出行安全信息</h2></div>
    <div className="safety-summary"><strong>{summary}</strong>{(review||['HIGH','MEDIUM','UNKNOWN'].includes(value.risk_level))&&<span>{value.risk_level==='UNKNOWN'?'风险待确认':'风险：'+label(value.risk_level)}</span>}{review&&<span>判断依据完整度：{label(value.confidence)}</span>}</div>
    {outdated&&<p className="mode-notice">这是上次检查的结果，请更新检查。</p>}
    {!outdated&&requestId&&<TripCoveragePanel value={coverage} planId={planId} readOnly={readOnly}/>}
    <div className="safety-quality">{states.map(state=><div className={state.attention?'quality-issue':'quality-available'} key={state.kind}><span>{checkNames[state.kind]}</span><strong>{state.title}</strong><span>{state.detail}</span></div>)}</div>
    {blockers}
    {value.requires_human_review&&!approved&&!value.mandatory_blockers.length&&<p>请等待审核员核对后再确认方案。</p>}
    {advisory}
    {(value.evidence.length>0||value.hazards.length>0)&&<details className="artifact-notes"><summary>查看安全详情与营地规定</summary>
      {value.hazards.length>0&&<><h3>需要留意的风险</h3><ul>{[...new Set(value.hazards.map(text=>safetySummary(text)??safetyRegulations(text)??'存在需要核实的风险，请在出发前重新检查。'))].map(text=><li key={text}>{text}</li>)}</ul></>}
      {value.evidence.map((item,index)=>{const state=safetyCondition(item.kind,item.status,[item],requirements);const text=safetySummary(item.summary)??safetyRegulations(item.summary);return <article className="evidence-item" key={index}><h3>{checkNames[item.kind]??'安全信息'} · {state.title}</h3>
        {text&&<p>{text}</p>}
        {review&&<details className="source-details"><summary>查看资料来源与原文</summary>{item.summary&&<p>{item.summary}</p>}{sources(item.source_refs)}</details>}
      </article>;})}
    </details>}
    {review&&<details className="artifact-notes"><summary>完整检查说明</summary><p>保存的评估结果：{label(value.outcome)} · 判断依据完整度：{label(value.confidence)}</p>
      {value.hazards.length>0&&<><h3>原始风险说明</h3><ul>{value.hazards.map((item,index)=><li key={index}>{item}</li>)}</ul></>}
      {value.unresolved_conflicts.length>0&&<><h3>资料冲突</h3><ul>{value.unresolved_conflicts.map((item,index)=><li key={index}>{item}</li>)}</ul></>}
      {value.recommended_actions.length>0&&<><h3>原始检查建议</h3><ul>{value.recommended_actions.map((item,index)=><li key={index}>{item}</li>)}</ul></>}
      {rawWarnings.map((item,index)=><p key={index}><strong>{item.code}</strong> · {item.message}</p>)}{notes}
    </details>}
  </section>;
}
