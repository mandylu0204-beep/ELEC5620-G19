import { chineseProse } from './display_facts';
import { safetyAdvice, type SafetyAudit, type SafetyAdviceBinding } from './safety_advisory';

export function SafetyAdvisoryPanel({value,binding,outdated=false,historical=false}:{
  value:SafetyAudit|null|undefined;binding:SafetyAdviceBinding|null;outdated?:boolean;historical?:boolean}){
  const advice=safetyAdvice(value,binding);
  if(!advice)return null;
  const actions=advice.items.filter(item=>!item.informational);
  const information=advice.items.filter(item=>item.informational);
  const card=(item:typeof advice.items[number])=>{
    const localized=chineseProse(item.action);
    const separate=item.explanation!==item.action;
    return <li key={item.key}>
      <h4>{item.title}</h4><p>{localized??'请按此事项准备，并以上方正式检查的处理动作与限制为准。'}</p>
      {(localized!==item.action||separate)&&<details><summary>查看已保存的模型建议原文</summary>{localized!==item.action&&<p>{item.action}</p>}{separate&&<p>{item.explanation}</p>}</details>}
    </li>;
  };
  return <section className="safety-advisory" aria-label="AI 安全准备建议">
    <div className="section-title"><span className="eyebrow">安全准备</span><h3>{outdated||historical?'此前保存的 AI 安全建议':'AI 安全准备建议'}</h3></div>
    <p className="muted">以下为 AI 提供的参考建议，未经人工核实；请以上方安全检查结果及适用规定为准。</p>
    {outdated&&<p className="mode-notice">这些建议来自此前检查，请更新检查后再参考。</p>}
    {!outdated&&historical&&<p className="muted">这些建议对应当时保存的行程与检查资料。</p>}
    {chineseProse(advice.summary)&&<p>{chineseProse(advice.summary)}</p>}<details><summary>查看已保存的模型总结原文</summary><p>{advice.summary}</p></details>
    {actions.length>0&&<><h4>建议处理的事项</h4><ol className="safety-advice-list">{actions.slice(0,3).map(card)}</ol>
      {actions.length>3&&<details><summary>其余建议（{actions.length-3}）</summary><ol className="safety-advice-list" start={4}>{actions.slice(3).map(card)}</ol></details>}</>}
    {information.length>0&&<details><summary>出行注意事项（{information.length}）</summary><ul className="safety-advice-list">{information.map(card)}</ul></details>}
  </section>;
}
