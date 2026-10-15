import type { ReactNode } from 'react';
import type { Safety, Source } from './plans';
import type { Requirements } from './api';
import { checkNames,checkState,evidenceState,safetySummary } from './plan_language';

export function SafetyInformation({value,requirements,summary,approved,review,outdated,blockers,notes,rawWarnings,sources,label}:{
  value:Safety|undefined;requirements:Requirements|undefined;summary:string;approved:boolean;review:boolean;outdated:boolean;
  blockers:ReactNode;notes:ReactNode;rawWarnings:{code:string;message:string}[];sources:(refs:Source[])=>ReactNode;label:(value:string)=>string}){
  if(!value)return <section className="panel"><h2>出行安全信息</h2><p>规划完成后，会在这里显示安全检查。</p></section>;
  const issues=Object.values(value.data_quality).some(status=>status!=='AVAILABLE');
  return <section className="panel"><div className="section-title"><span className="eyebrow">CHECK BEFORE YOU GO</span><h2>出行安全信息</h2></div>
    <div className="safety-summary"><strong>{summary}</strong><span>{value.risk_level==='UNKNOWN'?'目前信息不足，无法判断风险。':'风险：'+label(value.risk_level)}</span>{review&&<span>判断依据完整度：{label(value.confidence)}</span>}</div>
    {outdated&&<p className="mode-notice">以下是此前保存的资料和检查结果，更新检查后才能用于当前确认。</p>}
    <div className="safety-quality">{Object.entries(value.data_quality).map(([kind,status])=>{const state=checkState(kind,status,value.evidence,requirements);return <div className={status==='AVAILABLE'&&state.title==='资料适用'?'quality-available':'quality-issue'} key={kind}><span>{checkNames[kind]??'安全信息'}</span><strong>{state.title}</strong></div>;})}</div>
    {blockers}<h3>接下来可以怎么做</h3><ul>
      {issues&&<li>核对下方资料的适用日期，可调整出行日期或营地，也可以保留草稿，待适用资料更新后再检查。</li>}
      {value.requires_human_review&&!issues&&!approved&&!value.mandatory_blockers.length&&<li>这份方案需要审核员核对风险，审核完成后再确认保存。</li>}
      {value.hazards.length>0&&<li>资料记录了天气、活动或通行风险，请查看下方的完整检查说明。</li>}
      {value.mandatory_blockers.length>0&&<li>先处理已列出的装备或安全条件；人工审核不能替代缺少的资料或解除关闭、禁火限制。</li>}
      {!issues&&!value.requires_human_review&&!value.mandatory_blockers.length&&<li>阅读行程与适用规定，按页面提示确认方案。</li>}
    </ul>
    {value.evidence.map((item,index)=>{const info=evidenceState(item,requirements);const text=safetySummary(item.summary);return <article className="evidence-item" key={index}><h3>{checkNames[item.kind]??'安全信息'} · {info.title}</h3><p>{info.detail}</p>{text&&<p>{text}</p>}<p className="muted">资料日期：{item.source_date??'未提供'} · 适用日期：{item.valid_from??'未提供'} 至 {item.valid_to??'未提供'}</p>{item.road_state&&<p>资料记录的道路状态：{label(item.road_state)}</p>}<details className="source-details"><summary>查看资料来源与原文</summary>{item.summary&&<p>{item.summary}</p>}{sources(item.source_refs)}</details></article>;})}
    {!value.evidence.length&&<p className="muted">目前没有可供核对的安全资料。</p>}
    <details className="artifact-notes"><summary>完整检查说明</summary><p>保存的评估结果：{label(value.outcome)} · 判断依据完整度：{label(value.confidence)}</p>
      {value.hazards.length>0&&<><h3>原始风险说明</h3><ul>{value.hazards.map((item,index)=><li key={index}>{item}</li>)}</ul></>}
      {value.unresolved_conflicts.length>0&&<><h3>资料冲突</h3><ul>{value.unresolved_conflicts.map((item,index)=><li key={index}>{item}</li>)}</ul></>}
      {value.recommended_actions.length>0&&<><h3>原始检查建议</h3><ul>{value.recommended_actions.map((item,index)=><li key={index}>{item}</li>)}</ul></>}
      {rawWarnings.map((item,index)=><p key={index}><strong>{item.code}</strong> · {item.message}</p>)}{notes}
    </details>
  </section>;
}
