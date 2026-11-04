import {visitorText} from './visitor_text.ts';
import { displayProse } from './display_facts';
import { groupSafetyAdvice, safetyAdvice, type SafetyAdviceItem, type SafetyAudit, type SafetyAdviceBinding } from './safety_advisory';

function AdviceItems({items}:{items:SafetyAdviceItem[]}){
  const rows=items.map(item=>({item,localized:displayProse(item.action)}));
  const originals=rows.map((row,index)=>({...row,index})).filter(({item,localized})=>
    localized!==null&&localized!==item.action||item.explanation!==item.action);
  return <>
    <ul className="safety-advice-items">{rows.map(({item,localized})=><li key={item.key}>
      <p>{localized??visitorText(item.action)}</p>
    </li>)}</ul>
    {originals.length>0&&<details><summary>View group details and saved originals</summary>
      <ul className="safety-advice-items">{originals.map(({item,localized,index})=><li key={item.key}>
        <span className="muted">Item {index+1}</span>
        {localized!==null&&localized!==item.action&&<p>{visitorText(item.action)}</p>}
        {item.explanation!==item.action&&<p>{visitorText(item.explanation)}</p>}
      </li>)}</ul>
    </details>}
  </>;
}

export function SafetyAdvisoryPanel({value,binding,outdated=false,historical=false}:{
  value:SafetyAudit|null|undefined;binding:SafetyAdviceBinding|null;outdated?:boolean;historical?:boolean}){
  const advice=safetyAdvice(value,binding);
  if(!advice)return null;
  const actions=groupSafetyAdvice(advice.items.filter(item=>!item.informational&&visitorText(item.action).trim()));
  const summary=displayProse(advice.summary);
  if(!actions.length)return null;
  const card=(group:typeof actions[number])=><li key={group.key}>
    <h4>{group.title} <small className="muted">{group.items.length} items</small></h4>
    <AdviceItems items={group.items}/>
  </li>;
  return <section className="safety-advisory" aria-label="AI Safety preparation advice">
    <div className="section-title"><span className="eyebrow">Safety preparation</span><h3>{outdated||historical?'Previously saved AI safety suggestions':'AI Safety preparation advice'}</h3></div>
    {outdated&&<p className="mode-notice">These suggestions are from a previous check. Update checks before relying on them.</p>}
    {!outdated&&historical&&<p className="muted">These suggestions correspond to the itinerary and source information saved at that time.</p>}
    {summary&&<p>{summary}</p>}
    {actions.length>0&&<><h4>Suggested actions</h4><ol className="safety-advice-list">{actions.slice(0,3).map(card)}</ol>
      {actions.length>3&&<details><summary>Other advice categories ({actions.length-3})</summary><ol className="safety-advice-list" start={4}>{actions.slice(3).map(card)}</ol></details>}</>}
  </section>;
}
