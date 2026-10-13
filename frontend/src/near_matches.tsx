import { Link } from 'react-router-dom';

type Issue={field:string;title:string;status:'MISMATCH'|'UNVERIFIED';expected:string|null;actual:string|null;detail:string;suggestion:string;original_reason:string};
type NearMatch={campsite_id:string;name:string;region:string|null;rank:number;mismatch_count:number;unverified_count:number;issues:Issue[];matched_preferences:string[];uncertainties:string[];nightly_fee_cents:number|null;campsite_subtotal_cents:number|null;budget_excess_cents:number|null;source_ref:{provenance:{source_date:string}}|null};
export type RecommendationGuidance={near_matches:NearMatch[];excluded_count:number;ranking:string;metadata_note:string|null;scope:string};
const amount=(cents:number|null)=>cents===null?'未知':new Intl.NumberFormat('en-AU',{style:'currency',currency:'AUD',currencyDisplay:'code'}).format(cents/100);

export function NearMatches({value,requestId}:{value:RecommendationGuidance|null|undefined;requestId:string}){
  if(!value)return null;
  return <section className="panel near-matches" aria-label="最接近的营地比较">
    <span className="eyebrow">COMPARE & ADJUST</span><h2>最接近的营地</h2>
    <p>从 {value.excluded_count} 个被排除的营地中，比较最接近的 {value.near_matches.length} 个。下面明确列出哪些条件未满足，以及哪些信息仍需核实。</p>
    <p className="clarifications">{value.scope}</p>
    {value.metadata_note&&<p className="clarifications">{value.metadata_note}</p>}
    <p className="muted">{value.ranking}</p>
    <div className="near-match-grid">{value.near_matches.map(item=><article className="near-match-card" key={item.campsite_id}>
      <span className="tag">比较 #{item.rank} · 尚未匹配</span><h3>{item.name}</h3>
      {item.region&&<p className="muted">{item.region}</p>}
      <p>{item.mismatch_count} 项不满足 · {item.unverified_count} 项待核实</p>
      <dl className="summary-list"><div><dt>每晚营地费</dt><dd>{amount(item.nightly_fee_cents)}</dd></div><div><dt>本次营地费用小计</dt><dd>{amount(item.campsite_subtotal_cents)}</dd></div></dl>
      <p className="muted">仅营地费用，未包含交通、食物、水与装备；不是完整行程报价。</p>
      <ul className="near-match-issues">{item.issues.map((issue,index)=><li key={index}>
        <h4>{issue.title} <span className="tag">{issue.status==='MISMATCH'?'不满足':'待核实'}</span></h4>
        {issue.expected&&<p>你的条件：{issue.expected}</p>}{issue.actual&&<p>营地情况：{issue.actual}</p>}
        <p>{issue.detail}</p><p><strong>可以怎么调整：</strong>{issue.suggestion}</p>
      </li>)}</ul>
      {item.matched_preferences.length>0&&<p>已知符合的偏好：{item.matched_preferences.join('、')}</p>}
      {item.uncertainties.map((text,index)=><p className="muted" key={index}>{text}</p>)}
      {item.source_ref&&<p className="muted">资料日期：{item.source_ref.provenance.source_date}</p>}
      <Link className="text-link" to={'/request?copy_from='+encodeURIComponent(requestId)}>参考差异，调整需求 ↗</Link>
    </article>)}</div>
    {!value.near_matches.length&&<p>当前保存结果没有可比较的营地记录；请核对地区与数据来源。</p>}
    <p className="muted">调整入口保留原需求供你编辑，不会自动降低条件、保存、确认或生成行程。</p>
  </section>;
}
