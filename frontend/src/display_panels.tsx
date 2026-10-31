import {englishSavedReason} from './legacy_filter_reasons';
import { useState } from 'react';
import { displayProse, discardMessage, tentSummary, type TentCapacity } from './display_facts';
import { ModelTracePanel, type ModelTrace } from './model_trace';
import { selectionPresentation,selectedRequirementsPresentation,type SelectedRequirements } from './campsite_selection';
import { cataloguePlace, additionalFacilities, CampsiteArrivalDetails } from './campsite_details';

export function TentCapacityPanel({value}:{value:TentCapacity|null|undefined}){
  if(!value)return null;
  return <section className="tent-capacity" aria-label="Tent sleeping capacity"><h3>Check tents by total sleeping capacity</h3><p>{tentSummary(value)}</p>
    <div className="table-scroll"><table><caption>Tent records for this confirmation (different capacities shown separately)</caption><thead><tr><th>Number of tents</th><th>Capacity per tent</th><th>Total capacity of this row</th><th>Availability</th></tr></thead><tbody>
      {value.records.map((row,index)=><tr key={index}><td>{row.unit==='item'?`${row.quantity??'Unknown'} tents`:'Quantity unit needs review'}</td><td>{row.capacity_per_tent??'Unknown'} people</td><td>{row.total_capacity??'Unknown'} people</td><td>{row.confirmed?'Ownership verified':'Ownership unverified'}</td></tr>)}
    </tbody></table></div>{!value.records.length&&<p>No tents registered yet.</p>}
    <p>Group size:  {value.group_size??'Unknown'} people · Recorded tents:  {value.registered_tent_count??'Unknown'} · Recorded capacity:  {value.registered_capacity??'Unknown'} people · Accepted capacity: {value.assessed_capacity??'Unknown'} people · Shortage:  {value.missing_person_spaces??'Unknown'} places</p>
    <p className="muted">Recorded capacity is not necessarily confirmed available capacity. Unverified equipment does not become available through this display. Group size is not the number of tents to purchase.</p>
  </section>;
}

export function DiscardChanges({sections,busy=false,onDiscard}:{sections:string[];busy?:boolean;onDiscard:()=>void}){
  const [confirm,setConfirm]=useState(false);
  return <><button type="button" className="secondary-button" disabled={busy||!sections.length} onClick={()=>setConfirm(true)}>Discard unsaved changes</button>
    {confirm&&sections.length>0&&<div className="mode-notice" role="alertdialog" aria-label="Confirm discard of unsaved changes"><p>{discardMessage(sections)}</p>
      <button type="button" className="secondary-button" disabled={busy} onClick={()=>{setConfirm(false);onDiscard();}}>Discard and reload</button>
      <button type="button" className="secondary-button" disabled={busy} onClick={()=>setConfirm(false)}>Continue editing</button></div>}</>;
}

export type PlanningExplanation={source_run_id:string;selected_campsite_id:string;decision_summary_unverified:string};
export function PlanningExplanationPanel({value,currentRunId,siteName,siteId,catalogueId,reasons,uncertainties,requirements,accessibility}:{value?:PlanningExplanation|null;currentRunId?:string;siteName:string;siteId?:string;catalogueId?:string;reasons:string[];uncertainties:string[];requirements?:SelectedRequirements;accessibility?:string[]}){
  const place=cataloguePlace(siteId,catalogueId);
  const hasChoices=!!requirements&&Array.isArray(requirements.preferences)&&Array.isArray(requirements.mandatory_constraints);
  const selected=hasChoices?selectedRequirementsPresentation(reasons,requirements,place,accessibility):null;
  const {rows,costs}=selected??selectionPresentation(reasons);
  const savedExtra=selected?.extra??[];
  const extra=[...savedExtra,...additionalFacilities(place,[...rows,...savedExtra]).filter(row=>!selected||!rows.some(chosen=>chosen.facility===row.facility))];
  const visibleUncertainties=[...new Set(uncertainties.map(text=>displayProse(text)).filter((text):text is string=>text!==null))];
  return <section className="panel campsite-selection" aria-label="Campsite choice and pending confirmations"><h2>Reasons for choosing {siteName}</h2>
    {rows.length>0&&<div className="table-scroll"><table className={hasChoices?'requirements-comparison':undefined}><caption>Comparison with confirmed requirements</caption><thead><tr><th>Check item</th><th>{hasChoices?'Source information bound to this plan':'Saved filtering evidence'}</th>{hasChoices&&<th>Match result</th>}</tr></thead><tbody>
      {rows.map((row,index)=><tr key={index}><th scope="row">{row.label}{row.kind?<small className="selection-required">{row.kind}</small>:row.required&&<small className="selection-required">Required for this trip</small>}</th><td>{row.detail}</td>{hasChoices&&<td>{row.result??'Basic information'}</td>}</tr>)}
    </tbody></table></div>}
    {hasChoices&&<p className="muted">Compare each confirmed requirement with the bound sources. An unmet preference is not an unmet required condition. Matching source information does not confirm booking, safety or final-save eligibility.</p>}
    {!rows.length&&<p className="muted">No specific filtering evidence is available for direct display. Expand the original selection record below if present.</p>}
    {extra.length>0&&<div className="selection-facilities"><h3>Other campsite facilities</h3><dl>{extra.map(row=><div key={row.facility}><dt>{row.label}</dt><dd>{row.detail}</dd></div>)}</dl></div>}
    {costs.length>0&&<div className="selection-cost"><h3>Campsite fees</h3>{costs.map(text=><p key={text}>{text}</p>)}<p className="muted">See Costs and budget for the full trip cost and budget checks.</p></div>}
    <CampsiteArrivalDetails place={place}/>
    <h3>Confirm before departure</h3><ul>{visibleUncertainties.map(text=><li key={text}>{text}</li>)}<li>Campsite booking, actual arrival time, transport and latest restrictions still need confirmation.</li></ul>
    {(value||reasons.length>0||uncertainties.length>0)&&<details className="source-details"><summary>Saved selection records and model comments</summary>
      {value&&<><h3>Model selection suggestions (not manually verified)</h3><p className="muted">{value.source_run_id!==currentRunId?'These model suggestions were generated for the original version. This reassessment reuses the original itinerary.':'Saved model selection suggestions; not manually verified.'}</p><p>{value.decision_summary_unverified}</p></>}
      <h3>Saved suitability reasons</h3><ul>{reasons.map((text,index)=><li key={index}>{englishSavedReason(text)}</li>)}</ul><h3>Saved pending confirmations</h3><ul>{uncertainties.map((text,index)=><li key={index}>{text}</li>)}</ul>
    </details>}
  </section>;
}

export type ModelDiagnostics={planning:ModelTrace|null;assessments:Record<string,unknown>;dataset_context?:unknown};
export function ModelRunDiagnostics({allowed,value,currentRunId}:{allowed?:boolean;value?:ModelDiagnostics;currentRunId?:string}){
  if(!allowed||!value)return null;
  return <section className="panel" aria-label="Model diagnostics"><details><summary>Model diagnostics (review permission required)</summary><p>For troubleshooting only. Not camping costs or evidence of safety or save eligibility.</p>
    <ModelTracePanel value={value.planning} currentRunId={currentRunId} logisticsModel={!!value.assessments.LOGISTICS} safetyModel={!!value.assessments.SAFETY}/>
    {Object.entries(value.assessments).map(([role,record])=><details key={role}><summary>{role==='LOGISTICS'?'Equipment and budget':role==='SAFETY'?'Safety':'Other roles'}Model diagnostics</summary><pre className="diagnostic-json">{JSON.stringify(record,null,2)}</pre></details>)}
    <details><summary>Runtime configuration and data identity</summary><pre className="diagnostic-json">{JSON.stringify(value.dataset_context,null,2)}</pre></details>
  </details></section>;
}
