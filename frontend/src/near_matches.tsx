import {visitorText} from './visitor_text.ts';
import { Link } from 'react-router-dom';
import { tripUpdatePath } from './trip_update';

type Issue={field:string;title:string;status:'MISMATCH'|'UNVERIFIED';expected:string|null;actual:string|null;detail:string;suggestion:string;original_reason:string};
type NearMatch={campsite_id:string;name:string;region:string|null;rank:number;mismatch_count:number;unverified_count:number;issues:Issue[];matched_preferences:string[];uncertainties:string[];nightly_fee_cents:number|null;campsite_subtotal_cents:number|null;budget_excess_cents:number|null;source_ref:{provenance:{source_date:string}}|null};
export type RecommendationGuidance={near_matches:NearMatch[];excluded_count:number;ranking:string;metadata_note:string|null;scope:string};
const amount=(cents:number|null)=>cents===null?'Unknown':new Intl.NumberFormat('en-AU',{style:'currency',currency:'AUD',currencyDisplay:'code'}).format(cents/100);

export function NearMatches({value,planId,readOnly=false}:{value:RecommendationGuidance|null|undefined;requestId?:string;planId?:string;readOnly?:boolean}){
  if(!value)return null;
  return <section className="panel near-matches" aria-label="Closest campsite comparisons">
    <span className="eyebrow">Compare and adjust</span><h2>Closest campsites</h2>
    <p>These  {value.near_matches.length}  campsites are closest to your requirements. The following conditions still need adjustment or verification.</p>
    {!readOnly&&planId&&<p>Would you like to change transport, dates, budget or other conditions? The system will not change confirmed requirements for you.<Link className="text-link" to={'/profile?plan_id='+encodeURIComponent(planId)+'&focus=transport.transport_type'}>Change transport ↗</Link> <Link className="text-link" to={tripUpdatePath(planId)}>Review and adjust this request ↗</Link></p>}
    <p className="muted">The prices below include campsite fees only.</p>
    {value.metadata_note&&<p className="clarifications">{visitorText(value.metadata_note)}</p>}
    <div className="near-match-grid">{value.near_matches.map(item=><article className="near-match-card" key={item.campsite_id}>
      <span className="tag">Comparison #{item.rank} · Not yet matched</span><h3>{item.name}</h3>
      {item.region&&<p className="muted">{item.region}</p>}
      <p>{item.mismatch_count}  unmet conditions · {item.unverified_count}  unverified conditions</p>
      <dl className="summary-list"><div><dt>Nightly campsite fee</dt><dd>{amount(item.nightly_fee_cents)}</dd></div><div><dt>Campsite fee subtotal for this trip</dt><dd>{amount(item.campsite_subtotal_cents)}</dd></div></dl>
      <ul className="near-match-issues">{item.issues.map((issue,index)=><li key={index}>
        <h4>{issue.title} <span className="tag">{issue.status==='MISMATCH'?'Not met':'Needs verification'}</span></h4>
        {issue.expected&&<p>Your requirement: {issue.expected}</p>}{issue.actual&&<p>Campsite information: {issue.actual}</p>}
        <p>{issue.detail}</p><p><strong>Possible adjustment: </strong>{issue.suggestion}</p>
      </li>)}</ul>
      {item.matched_preferences.length>0&&<p>Known matching preferences: {item.matched_preferences.map(visitorText).join(', ')}</p>}
      {item.uncertainties.map((text,index)=><p className="muted" key={index}>{visitorText(text)}</p>)}
      {item.source_ref&&<p className="muted">Information date: {item.source_ref.provenance.source_date}</p>}
      {planId&&!readOnly&&<Link className="text-link" to={tripUpdatePath(planId)}>Review the differences and adjust this request ↗</Link>}
    </article>)}</div>
    {!value.near_matches.length&&<p>No comparable campsite records were saved. Check the region and data source.</p>}
  </section>;
}
