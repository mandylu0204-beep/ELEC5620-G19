import { chineseProse } from './display_facts';
import { groupSafetyAdvice, safetyAdvice, type SafetyAdviceItem, type SafetyAudit, type SafetyAdviceBinding } from './safety_advisory';

function AdviceItems({items}:{items:SafetyAdviceItem[]}){
  const rows=items.map(item=>({item,localized:chineseProse(item.action)}));
  const originals=rows.map((row,index)=>({...row,index})).filter(({item,localized})=>
    localized!==null&&localized!==item.action||item.explanation!==item.action);
  return <>
    <ul className="safety-advice-items">{rows.map(({item,localized})=><li key={item.key}>
      <p>{localized??item.action}</p>
    </li>)}</ul>
    {originals.length>0&&<details><summary>查看本组补充说明与保存原文</summary>
      <ul className="safety-advice-items">{originals.map(({item,localized,index})=><li key={item.key}>
        <span className="muted">第 {index+1} 项</span>
        {localized!==null&&localized!==item.action&&<p>{item.action}</p>}
        {item.explanation!==item.action&&<p>{item.explanation}</p>}
      </li>)}</ul>
    </details>}
  </>;
}

export function SafetyAdvisoryPanel({value,binding,outdated=false,historical=false}:{
  value:SafetyAudit|null|undefined;binding:SafetyAdviceBinding|null;outdated?:boolean;historical?:boolean}){
  const advice=safetyAdvice(value,binding);
  if(!advice)return null;
  const actions=groupSafetyAdvice(advice.items.filter(item=>!item.informational));
  const summary=chineseProse(advice.summary);
  if(!actions.length&&!summary)return null;
  const card=(group:typeof actions[number])=><li key={group.key}>
    <h4>{group.title} <small className="muted">{group.items.length} 项</small></h4>
    <AdviceItems items={group.items}/>
  </li>;
  return <section className="safety-advisory" aria-label="AI 安全准备建议">
    <div className="section-title"><span className="eyebrow">安全准备</span><h3>{outdated||historical?'此前保存的 AI 安全建议':'AI 安全准备建议'}</h3></div>
    {outdated&&<p className="mode-notice">这些建议来自此前检查，请更新检查后再参考。</p>}
    {!outdated&&historical&&<p className="muted">这些建议对应当时保存的行程与检查资料。</p>}
    {summary&&<p>{summary}</p>}
    {actions.length>0&&<><h4>建议处理的事项</h4><ol className="safety-advice-list">{actions.slice(0,3).map(card)}</ol>
      {actions.length>3&&<details><summary>其余建议类别（{actions.length-3}）</summary><ol className="safety-advice-list" start={4}>{actions.slice(3).map(card)}</ol></details>}</>}
  </section>;
}
