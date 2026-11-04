import {visitorText} from './visitor_text.ts';
export type LogisticsAudit = {audit_id:string;run_id:string;plan_version_id:string;assessment_id:string;attempt_id?:string;
  trace?:{requested_model:string;served_models:string[];turns:number;http_attempts:number;usage:Record<string,number>};
  plan:{gear_actions:{fact:{item_key:string;missing_quantity:string|null;unit:string;essential:boolean};method:string;
    procurement_quantity:string|null;procurement_unit:string;estimated_cost_cents:number|null;confirmation_required:boolean;reason_unverified:string}[];
    budget_allocations:{line_id:string;required_cents:number|null;allocated_cents:number|null;unfunded_cents:number|null}[];
    projected_cost_breakdown:{category:string;item_key:string}[];unallocated_known_budget_cents:number;
    budget_feasible:boolean|null;requires_user_confirmation:boolean;decision_summary_unverified:string}};

const methods:Record<string,string>={KEEP_CONFIRMED:'Use confirmed equipment',PROPOSE_RENTAL:'Proposed rental',PROPOSE_PURCHASE:'Proposed purchase',
  PROPOSE_BORROW:'Proposed borrowing',ASK_USER:'More information needed',DEFER_OPTIONAL:'Defer optional equipment'};
const categories:Record<string,string>={CAMPSITE:'Campsite',TRANSPORT:'Transport',FOOD:'Food',WATER:'Drinking water',ADDITIONAL_GEAR:'Equipment'};

export function LogisticsPlanPanel({value,section,money,itemName,unitName}:{value:LogisticsAudit|null|undefined;section:'gear'|'cost';
  money:(value:number|null|undefined)=>string;itemName:(value:string)=>string;unitName:(value:string)=>string}) {
  if(!value)return null;
  const plan=value.plan;
  const costItemName=(value:string)=>value==='no_priced_equipment_gaps'?'No unpriced equipment':itemName(value);
  return <section className="panel logistics-plan-panel"><div className="section-title"><span className="eyebrow">Trip preparation</span><h2>{section==='gear'?'Equipment preparation advice':'Budget allocation advice'}</h2></div>
    {section==='gear'?<><p className="muted">Verify rentals, purchases and borrowing yourself. Suggestions do not increase available inventory.</p><div className="logistics-actions">{plan.gear_actions.map(item=><article key={item.fact.item_key} className={'logistics-action '+(item.confirmation_required?'logistics-action-pending':'')}>
      <div><h3>{itemName(item.fact.item_key)}</h3><span className="tag">{methods[item.method]??item.method}</span></div>
      {item.method==='KEEP_CONFIRMED'?<p>Bring items on the confirmed checklist; no additional equipment is proposed.</p>:item.method==='DEFER_OPTIONAL'?<p>Defer acquisition and retain the current shortfall.</p>:<p>Suggested additional quantity:{item.procurement_quantity??'To be confirmed'} {unitName(item.procurement_unit)} · Shortfall resolution cost {money(item.estimated_cost_cents)}</p>}
      <small>{item.fact.missing_quantity===null?'Current shortfall unknown':`Current shortfall ${item.fact.missing_quantity} ${unitName(item.fact.unit)}`} · {item.fact.essential?'Essential equipment':'Optional equipment'}{item.confirmation_required?' · To be confirmed':''}</small>
      <details><summary>View reasoning</summary><p>{visitorText(item.reason_unverified)}</p></details>
    </article>)}</div></>:<><p className="muted">Allocate known costs in the suggested priority order. Unknown costs are not treated as zero; reserve unallocated budget.</p>
      <div className="table-scroll"><table><caption>Budget allocation and gaps (AUD)</caption><thead><tr><th>Priority / Item</th><th>Required cost</th><th>Planned allocation</th><th>Uncovered</th></tr></thead><tbody>{plan.budget_allocations.map((line,index)=>{const cost=plan.projected_cost_breakdown[index];return <tr key={line.line_id}><td>{index+1}. {cost?categories[cost.category]??cost.category:'Cost item'}{cost?.category==='ADDITIONAL_GEAR'&&<small className="cost-site">{costItemName(cost.item_key)}</small>}</td><td>{money(line.required_cents)}</td><td>{money(line.allocated_cents)}</td><td>{money(line.unfunded_cents)}</td></tr>;})}</tbody></table></div>
      <p>Unallocated known budget: <strong>{money(plan.unallocated_known_budget_cents)}</strong></p><p className={plan.budget_feasible===true?'muted':'clarifications'}>{plan.budget_feasible===null?'Some costs remain unknown; budget sufficiency cannot yet be determined.':plan.budget_feasible?'Known estimates are within budget; supply arrangements still need confirmation.':'Estimated costs exceed the budget. Adjust the arrangements.'}</p></>}
    <details className="source-details"><summary>View model suggestions</summary><p>{visitorText(plan.decision_summary_unverified)}</p><small>Model suggestions are advisory; quantities and amounts are calculated by the application.</small></details>
  </section>;
}

export function LogisticsTracePanel({value}:{value:LogisticsAudit|null|undefined}) {
  if(!value?.trace)return null;
  const trace=value.trace;
  return <section className="panel"><details className="planning-details"><summary>Equipment and budget model diagnostics</summary><h2>Model record for this logistics assessment</h2>
    {trace.served_models.includes('offline-test-only')&&<p className="mode-notice">No campus model call was made for this record.</p>}
    <p>This record belongs to the displayed logistics assessment and is stored separately from the original itinerary generation.</p><dl className="summary-list"><div><dt>Requested model</dt><dd>{trace.requested_model}</dd></div><div><dt>Response model</dt><dd>{trace.served_models.join(', ')||'Not provided'}</dd></div><div><dt>Tool turns / HTTPAttempts</dt><dd>{trace.turns} / {trace.http_attempts}</dd></div><div><dt>Token usage</dt><dd>Input {trace.usage.prompt_tokens??'Not provided'} · Generate {trace.usage.completion_tokens??'Not provided'} · Total {trace.usage.total_tokens??'Not provided'}</dd></div></dl>
    <p className="muted">usageUsage reported by this successful response; this is not a complete bill.</p><details><summary>View linked records</summary><p className="identifier">Run: {value.run_id} · Version: {value.plan_version_id}</p><p className="identifier">Assessment:{value.assessment_id} · Save attempt: {value.attempt_id}</p></details>
  </details></section>;
}
