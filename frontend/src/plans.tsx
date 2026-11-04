import {visitorText,sourceDisplayName} from './visitor_text.ts';
import {englishSavedReason} from './legacy_filter_reasons';
import {planCheckState,pendingRevision} from './plan_check_state';
import {ConfirmedRequirementsList} from './confirmed_requirements';
import {AssistanceNotes,AssistanceNextAction,type AssistanceNote} from './review_assistance';
import {boundReview,revisionReview} from './review_revision';
import { failureGuidance } from './failure_guidance';
import { RevisionComparison, type RevisionComparisonData } from './revision_comparison';
import type { SafetyAudit } from './safety_advisory';
import { LogisticsIssues, type LogisticsIssue } from './logistics_issues';
import { CookingPreparationPanel, canHideCookingPreparation, type CookingPreparation } from './cooking_preparation';
import { logisticsQuestions, needsMealChoice } from './logistics_guidance';
import { useEffect, useId, useRef, useState, type KeyboardEvent, type ReactNode } from 'react';
import { Link, useLocation, useParams, useSearchParams } from 'react-router-dom';
import { FinalisePanel } from './finalise';
import { RetryPlanning, ChangePlanning, revealRevisionPanel } from './planning';
import { NextSteps } from './next_steps';
import { ReplanFromProfile } from './replan';
import { CheckFeedback } from './check_feedback';
import { NearMatches, type RecommendationGuidance } from './near_matches';
import { ModelRunDiagnostics, PlanningExplanationPanel, TentCapacityPanel, type PlanningExplanation, type ModelDiagnostics } from './display_panels';
import { PROFILE_SAVED_NOTICE, displayProse, type TentCapacity } from './display_facts';
import { LogisticsPlanPanel, type LogisticsAudit } from './logistics_plan';
import { blockerText, checkNames, safetyCondition, planRowState } from './plan_language';
import { SafetyInformation } from './safety_information';
import { DailyItinerary } from './daily_itinerary';
import { campName } from './campsite_names';
import { TripPreparation, type PreparationSummary } from './trip_preparation';
export { campName } from './campsite_names';
import type { TripCoverage } from './trip_coverage';
import { ApiFailure, type ApiError, type Requirements } from './api';
import { ProfileSummary, equipmentLabel, type Profile } from './profile';
import { privateApi, useSession } from './session';
import { mergeProgress, progressPath, shouldPollPlan, type RunProgress } from './plan_progress';
import { startSavedPolling, subscribePageRefresh } from './saved_polling';

export type Source = { dataset_file:string; record_id:string; provenance:{source_name:string; source_type:string; source_date:string; demo_only:boolean}; valid_from:string|null; valid_to:string|null };
type Artifact = { execution_mode:string; source_refs:Source[]; assumptions:string[]; uncertainties:string[] };
type Blocker = { code:string; message:string; source_refs:Source[] };
type ErrorInfo = ApiError['error'];
type Run = {run_id:string;status:string;stage:string;revision:number;error:ErrorInfo|null;execution_mode:string;operation:string;is_active:boolean;created_at:string};
type Version = {version_number:number;status:string;revision:number;version_context:{plan_id:string;plan_version_id:string;run_id:string;input_fingerprint:string};content:Artifact & {selected_campsite_ids:string[];revision_reason:string;itinerary_entries:{entry_kind:string;start_at:string;end_at:string;campsite_id:string|null;description:string}[]}};
type Logistics = Artifact & {outcome:string;transport_feasible:boolean|null;gear_checklist:{item_key:string;required_quantity:string|null;available_quantity:string|null;missing_quantity:string|null;unit:string;capacity_requirement:number|null;arrangement_status:string;essential:boolean}[];cost_breakdown:{category:string;item_key:string;quantity:string|null;unit:string;unit_price_cents:number|null;subtotal_cents:number|null;source_ref:Source|null;assumption:string|null}[];total_cents:number|null;known_subtotal_cents:number;budget_difference_cents:number|null;mandatory_blockers:Blocker[];clarifications:{field:string;question:string;reason:string}[]};
export type Safety = Artifact & {outcome:string;risk_level:string;confidence:string;requires_human_review:boolean;data_quality:{[key:string]:string};evidence:{kind:string;summary:string|null;source_date:string|null;status:string;valid_from:string|null;valid_to:string|null;road_state:string|null;source_refs:Source[]}[];hazards:string[];recommended_actions:string[];unresolved_conflicts:string[];mandatory_blockers:Blocker[]};
type Assessment = {assessment_id:string;kind:string;depends_on_assessment_id?:string|null;version_context:Version['version_context'];result:Logistics|Safety};
type Eligibility = {eligible:boolean;blocking_reasons:Blocker[];review_required:boolean;valid_review_id:string|null};
export type FinalIndex = {plan_id:string;final_id:string;plan_version_id:string;run_id:string;version_number:number;finalised_at:string;is_current:boolean};
export type PlanDetail = {review_assistance_notes?:AssistanceNote[];revision_comparison?:RevisionComparisonData|null;preparation_summary?:PreparationSummary|null;campsite_catalogue_id?:string;series_last_final?:FinalIndex|null;trip_series?:{trip_series_id:string;series_revision:number;current_plan_id:string|null;predecessor_plan_id:string|null;is_current:boolean}|null;display_status?:string|null;tent_capacity?:TentCapacity;planning_explanation?:PlanningExplanation|null;can_view_model_diagnostics?:boolean;model_diagnostics?:ModelDiagnostics;logistics_issues?:LogisticsIssue[];trip_evidence_coverage?:TripCoverage|null;current_inputs_state?:'CHANGED'|'UNAVAILABLE'|null;check_feedback?:{status:'IN_PROGRESS'|'COMPLETED'|'FAILED'|'INCOMPLETE';started_at:string;completed_at:string|null;comparison:'NOT_COMPARABLE'|'UNCHANGED'|'CHANGED';compared_run_id:string|null;changed_sections:string[]}|null;model_assessment_audits?:{LOGISTICS?:LogisticsAudit;SAFETY?:SafetyAudit};recommendation_guidance?:RecommendationGuidance|null;revision_available?:boolean;reassessment_available?:boolean;current_version_revision?:number|null;current_inputs_error?:string|null;planning_available?:boolean;retry_available?:boolean;retry_unavailable_reason?:string|null;finalisation_available:boolean;last_final:FinalIndex|null;selected_final:FinalIndex|null;final_history:FinalIndex[];reviews:{review_id:string;decision:string;reason:string;reviewer_user_id:string;version_context?:Version['version_context']}[];review_available?:boolean;plan:{plan_id:string;request_id:string;active_run_id:string|null;current_version_id:string|null;final_version_id:string|null;created_at:string};run:Run|null;run_history:{run_id:string;status:string;stage:string;created_at:string;plan_version_id:string|null;version_number:number|null}[];confirmed_context:{request_id:string;requirements:Requirements;profile_snapshot:Profile;demo_context:{demo_today:string;mode:string};dataset_context:{dataset_version:string}}|null;events:{id:number;stage:string;status:string;error:ErrorInfo|null;created_at:string}[];version:Version|null;assessments:Assessment[];recommendations:{recommendation_id:string;result:Artifact & {search_outcome:string;candidates:{campsite_id:string;rank:number;reasons:string[];material_uncertainties:string[]}[];excluded_candidates:{campsite_id:string;reasons:string[]}[]}}|null;route:{status:string;eligibility:Eligibility}|null;eligibility:Eligibility|null};
type PlanRow = {display_status?:string|null;search_outcome?:string|null;start_date?:string|null;end_date?:string|null;last_final:FinalIndex|null;plan_id:string;request_id:string;destination:string|null;created_at:string;execution_mode:string|null;run_status:string|null;stage:string|null;version_status:string|null;version_number:number|null};
const LABEL:{[key:string]:string} = {PENDING:'Queued',RUNNING:'Running',SUCCEEDED:'Checks completed',FAILED:'Run failed',CANCELLED:'Cancelled',SUPERSEDED:'Superseded by a new run',RECOMMENDING:'Recommend campsites',GENERATING:'Generate itinerary',SAVING_VERSION:'Save version',ASSESSING_LOGISTICS:'Equipment and logistics',ASSESSING_SAFETY:'Safety assessment',ROUTING:'Determine next step',COMPLETED:'Complete checks',DRAFT:'Draft',ASSESSING:'Assessing',REVISION_REQUIRED:'Revision required',ESCALATED:'Awaiting reviewer action',BLOCKED:'Plan needs attention',ELIGIBLE_FOR_FINALISATION:'Ready to save',REJECTED:'Review rejected',FINALISED:'Saved',PASSED:'Assessment passed',REVISION:'Revision required',REVIEW:'Review required',WEATHER:'Weather',FIRE:'Campfire restrictions',ROAD:'Road',RESTRICTION:'Campsite restrictions',AVAILABLE:'Available',MISSING:'Missing',STALE:'Outdated',CONFLICTING:'Conflict',LOW:'Low',MEDIUM:'Medium',HIGH:'High',UNKNOWN:'Unknown',OPEN:'Open',CLOSED:'Closed',OWNED:'Owned',CONFIRMED_RENTAL:'Confirmed rental',UNCONFIRMED:'Unconfirmed',CAMPSITE:'Campsite',TRANSPORT:'Transport',FOOD:'Food',WATER:'Drinking water',ADDITIONAL_GEAR:'Additional equipment',PLAN:'Initial planning',REASSESS:'Reassessment',REVISE:'Plan revision',TRAVEL:'Transport',CAMP:'Camping',ACTIVITY:'Activity'};
const STAGES=['RECOMMENDING','GENERATING','SAVING_VERSION','ASSESSING_LOGISTICS','ASSESSING_SAFETY','ROUTING','COMPLETED'];
function label(value:string|null|undefined){return value?LABEL[value]??value:'Unknown';}
export function aud(cents:number|null|undefined){
  if(cents===null||cents===undefined)return 'Unknown';
  if(!Number.isSafeInteger(cents))return 'Amount exceeds the display range';
  const digits=(cents<0?-BigInt(cents):BigInt(cents)).toString().padStart(3,'0');
  return `AUD ${cents<0?'-':''}${digits.slice(0,-2)}.${digits.slice(-2)}`;
}
function time(value:string){const parsed=new Date(value);return Number.isNaN(parsed.getTime())?value:new Intl.DateTimeFormat('en-AU',{timeZone:'Australia/Sydney',dateStyle:'short',timeStyle:'short'}).format(parsed);}
const plansActive=(value:{plans:PlanRow[]})=>value.plans.some(row=>['PENDING','RUNNING'].includes(row.run_status??''));

async function readPlanProgress(value:PlanDetail,signal:AbortSignal):Promise<PlanDetail|null>{
  const path=progressPath(value);
  return path ? mergeProgress(value,await privateApi<RunProgress>(path,{signal})) : null;
}

export function useSavedRead<T>(path:string,poll:(value:T)=>boolean,progress?:(value:T,signal:AbortSignal)=>Promise<T|null>,liveRefresh=false){
  const {reload}=useSession();const [data,setData]=useState<T|null>(null);const [error,setError]=useState('');const [retry,setRetry]=useState(0);
  useEffect(()=>{setData(null);setError('');
    return startSavedPolling<T>({read:signal=>privateApi<T>(path,{signal}),progress,poll,
      subscribeRefresh:liveRefresh?subscribePageRefresh:undefined,
      retryOnError:liveRefresh?reason=>reason instanceof ApiFailure?reason.envelope.error.recoverable&&!['UNAUTHENTICATED','FORBIDDEN','NOT_FOUND'].includes(reason.envelope.error.code):reason instanceof TypeError||reason instanceof SyntaxError:undefined,
      onValue:value=>{setData(value);setError('');},
      onError:reason=>{setError(reason instanceof ApiFailure?`${reason.message}(Trace ID ${reason.envelope.trace_id})`:'Connection failed; displayed content is from the most recent successful read.');if(reason instanceof ApiFailure&&reason.envelope.error.code==='UNAUTHENTICATED')reload();}});
  },[path,retry,poll,progress,reload,liveRefresh]);
  return {data,error,refresh:()=>setRetry(value=>value+1)};
}

function Sources({refs}:{refs:Source[]}){return refs.length?<details className="source-details"><summary>Source records ({refs.length})</summary><ul>{refs.map((ref,index)=><li key={index}><strong>{sourceDisplayName(ref.dataset_file)} · {ref.record_id}</strong><span>Source registration date {ref.provenance.source_date}</span>{(ref.valid_from||ref.valid_to)&&<span>Coverage: {ref.valid_from??'Unknown'} to {ref.valid_to??'Unknown'}</span>}</li>)}</ul></details>:<p className="muted">No source records were provided.</p>;}
function Blockers({items,review=false}:{items:Blocker[];review?:boolean}){return items.length?<div className="clarifications"><h3>Items to address</h3><ul>{[...new Set(items.map(item=>blockerText(item.code)))].map(text=><li key={text}>{text}</li>)}</ul>{review&&<details><summary>View check details</summary>{items.map((item,index)=><div key={index}><p><strong>{item.code}</strong> · {item.message}</p>{item.source_refs.length>0&&<Sources refs={item.source_refs}/>}</div>)}</details>}</div>:null;}

export function NewPlanPrompt(){
  return <section className="panel"><h2>No camping plans yet</h2><p>Complete your group, transport and equipment details, then enter and confirm your camping requirements.</p><Link className="text-link" to="/profile">Start planning ↗</Link></section>;
}

export type TripSeriesCardData={trip_series_id:string;revision:number;current_plan:PlanRow|null;history:PlanRow[];last_final:FinalIndex|null};
const seriesActive=(value:{trip_series:TripSeriesCardData[];independent_plans:PlanRow[]})=>plansActive({plans:[...value.independent_plans,...value.trip_series.flatMap(item=>item.current_plan?[item.current_plan]:[])]});
export function TripSeriesCard({value,onDeletePlan,onDeleteSeries,busy}:{value:TripSeriesCardData;onDeletePlan:(id:string)=>void;onDeleteSeries:()=>void;busy:boolean}){
  const row=value.current_plan;
  return <article className="panel plan-list-card" aria-label="Trip">
    {row?<Link className="plan-card" to={'/plans/'+row.plan_id}><h2>{row.destination??'Camping plan'}</h2>
      <p className="tag">{planRowState(row)}</p><p>{row.start_date} — {row.end_date}</p>
      <small>Current plan · {time(row.created_at)}(Sydney time)</small></Link>:<><h2>Current plan deleted</h2><p>Only undeleted history below is retained. Previous plans and tasks are not restored automatically.</p></>}
    {value.last_final&&<div className="saved-plan-notice"><p>{row&&['PENDING','RUNNING'].includes(row.run_status??'')?'Previous final plan retained; current checks are incomplete':value.last_final.is_current?'Current final plan saved':'A previous final plan is retained; this does not mean the current checks have passed'}</p>
      <Link to={'/plans/'+value.last_final.plan_id+'/finals/'+value.last_final.final_id}>View saved final plan ↗</Link></div>}
    {value.history.length>0&&<details><summary>Historical plans ({value.history.length})</summary><ul>{value.history.map(old=><li key={old.plan_id}>
      <Link to={'/plans/'+old.plan_id}>{old.destination??'Historical plan'} · {time(old.created_at)}</Link>(historical record, not the current check result)
      <button className="text-button" disabled={busy} onClick={()=>onDeletePlan(old.plan_id)}>Delete this historical plan</button>
    </li>)}</ul></details>}
    <div className="plan-card-actions">{row&&<button className="secondary-button" disabled={busy||['PENDING','RUNNING'].includes(row.run_status??'')} onClick={()=>onDeletePlan(row.plan_id)}>Delete current plan</button>}
      <button className="secondary-button" disabled={busy} onClick={onDeleteSeries}>Delete entire trip</button></div>
  </article>;
}

export function PlansPage(){
  const {session,reload}=useSession();
  const [confirmDelete,setConfirmDelete]=useState<string|null>(null);
  const [deleting,setDeleting]=useState<string|null>(null);
  const [deleteError,setDeleteError]=useState('');
  const [deleted,setDeleted]=useState<Set<string>>(new Set());
  const [seriesDelete,setSeriesDelete]=useState<TripSeriesCardData|null>(null);
  const seriesDeleteCommand=useRef<{identity:string;key:string}|null>(null);
  async function removeSeries(){
    if(!seriesDelete||!session||deleting)return;
    const identity=seriesDelete.trip_series_id+':'+seriesDelete.revision;
    if(seriesDeleteCommand.current?.identity!==identity)seriesDeleteCommand.current={identity,key:crypto.randomUUID()};
    setDeleting(seriesDelete.trip_series_id);setDeleteError('');
    try{await privateApi('/trip-series/'+encodeURIComponent(seriesDelete.trip_series_id)+'/delete',{method:'POST',headers:{'Content-Type':'application/json','X-CampMate-Client':'1','X-CSRF-Token':session.csrf_token},body:JSON.stringify({command_key:seriesDeleteCommand.current.key,expected_series_revision:seriesDelete.revision})});setSeriesDelete(null);refreshSeries();}
    catch(reason){setDeleteError(reason instanceof Error?reason.message:'Deletion failed. Please retry.');}
    finally{setDeleting(null);}
  }
  async function removePlan(planId:string){
    if(!session||deleting)return;
    setDeleting(planId);setDeleteError('');
    try{
      await privateApi<void>('/plans/'+encodeURIComponent(planId),{method:'DELETE',headers:{'X-CampMate-Client':'1','X-CSRF-Token':session.csrf_token}});
      setDeleted(value=>new Set([...value,planId]));setConfirmDelete(null);
      refreshSeries();
    }catch(reason){
      setDeleteError(reason instanceof ApiFailure?reason.message:'Deletion failed. Please retry.');
      if(reason instanceof ApiFailure&&reason.envelope.error.code==='UNAUTHENTICATED')reload();
    }finally{setDeleting(null);}
  }
  const {data:seriesData,error,refresh}=useSavedRead<{trip_series:TripSeriesCardData[];independent_plans:PlanRow[]}>('/trip-series',seriesActive);
  const refreshSeries=refresh;
  const rows=seriesData?.independent_plans.filter(row=>!deleted.has(row.plan_id))??[];
  return <><div className="page-heading"><span className="eyebrow">Plan overview</span><h1>My camping plan</h1><p>View arrangements, address pending items and save your final plan.</p></div>{error&&<p className="error-box" role="alert">{error}</p>}<div className="plan-list-actions">
      <button className="secondary-button" onClick={refresh}>Refresh plans</button>
      <Link className="secondary-button" to="/profile">Create independent trip ↗</Link>
    </div>
    {deleteError&&<p className="error-box" role="alert">{deleteError}</p>}
    {seriesDelete&&<section className="error-box" role="alert"><p>Delete the entire trip and all its plans? History and final records will no longer be accessible in the UI. Internal server audit records are retained.</p><button disabled={!!deleting} onClick={removeSeries}>Confirm deletion of entire trip</button><button disabled={!!deleting} onClick={()=>setSeriesDelete(null)}>Cancel</button></section>}
    {seriesData&&confirmDelete&&!rows.some(row=>row.plan_id===confirmDelete)&&<section className="error-box" role="alert"><p>Delete the selected plan? Deleting history does not change the current plan. Deleting the current plan does not automatically restore history.</p><button disabled={!!deleting} onClick={()=>void removePlan(confirmDelete)}>Confirm deletion of selected plan</button><button disabled={!!deleting} onClick={()=>setConfirmDelete(null)}>Cancel</button></section>}
    <div className="plan-cards">{seriesData?.trip_series.map(value=><TripSeriesCard key={value.trip_series_id} value={value} busy={!!deleting} onDeletePlan={setConfirmDelete} onDeleteSeries={()=>setSeriesDelete(value)}/>)}</div>
    {!seriesData?<section className="panel"><p>Loading…</p></section>:!rows.length&&!seriesData.trip_series.length?<NewPlanPrompt/>:<div className="plan-cards">{rows.map(row=><article className="panel plan-list-card" key={row.plan_id}><Link className="plan-card" to={'/plans/'+row.plan_id}><h2>{row.destination??'Camping plan'}</h2><p className="tag">{planRowState(row)}</p>
      {row.start_date&&row.end_date&&<p>{row.start_date} — {row.end_date}</p>}{row.version_number?<p>Version {row.version_number}</p>:row.search_outcome==='NO_MATCH'?<p>Compare the closest campsites, then adjust your conditions.</p>:<p>View the itinerary after planning is complete.</p>}
      {row.run_status==='RUNNING'&&<p>In progress:{label(row.stage)}</p>}{row.last_final&&!row.last_final.is_current&&<p className="muted">A previously saved final plan is retained</p>}<small>Created {time(row.created_at)}(Sydney time)</small><span className="text-link">{row.search_outcome==='NO_MATCH'?'View campsite comparisons':'View plan'} ↗</span></Link>
      {confirmDelete===row.plan_id?<div className="plan-delete-confirm" role="group" aria-label="Confirm plan deletion"><p>Delete this plan? It will no longer be displayed and cannot be restored through the UI.</p><div><button className="secondary-button delete-plan-button" disabled={deleting!==null} onClick={()=>void removePlan(row.plan_id)}>{deleting===row.plan_id?'Deleting…':'Confirm deletion'}</button><button className="secondary-button" disabled={deleting!==null} onClick={()=>{setConfirmDelete(null);setDeleteError('');}}>Cancel</button></div></div>
      :<div className="plan-card-actions"><button className="secondary-button delete-plan-button" disabled={deleting!==null||['PENDING','RUNNING'].includes(row.run_status??'')} title={['PENDING','RUNNING'].includes(row.run_status??'')?'Available after planning or checks finish':undefined} onClick={()=>{setConfirmDelete(row.plan_id);setDeleteError('');}}>Delete plan</button></div>}
    </article>)}</div>}
  </>;
}

export function PlanPage(){const location=useLocation();const {planId}=useParams();const [search,setSearch]=useSearchParams();const runId=search.get('run_id');const {data,error,refresh}=useSavedRead<PlanDetail>('/plans/'+planId+(runId?'?run_id='+encodeURIComponent(runId):''),shouldPollPlan,readPlanProgress,true);
  if(!data)return <><div className="page-heading"><h1>Read planning records</h1></div>{error&&<p className="error-box" role="alert">{error}</p>}<button className="secondary-button" onClick={refresh}>Reload</button><Link className="text-link" to="/plans">Back to plans ↗</Link></>;
  return <>{location.state?.profileSaved===true&&<p className="success-box" role="status">{PROFILE_SAVED_NOTICE}</p>}<PlanView data={data} error={error} refresh={refresh} current={()=>setSearch({})}/></>;
}
const unitName = (unit: string) => ({item:'items',person_space:'places',litre:'litres',portion:'portions',vehicle:'vehicles',plan:'plans',per_night:'nights',per_kilometre:'km',per_vehicle:'vehicles',per_person_per_day:'person-days',one_time:'trips',not_procured:'Defer purchase'} as Record<string,string>)[unit] ?? unit;
type PlanSection = 'itinerary' | 'gear' | 'cost' | 'safety' | 'history';
const PLAN_SECTIONS: {id:PlanSection; title:string}[] = [
  {id:'itinerary',title:'Itinerary'},{id:'gear',title:'Equipment'},{id:'cost',title:'Costs'},
  {id:'safety',title:'Safety'},{id:'history',title:'Records'},
];

export function PlanView({data,error,refresh,current,review=false,snapshot=false,reviewActions}:{data:PlanDetail;error:string;refresh:()=>void;current?:()=>void;review?:boolean;snapshot?:boolean;reviewActions?:ReactNode}) {
  const [section,setSection] = useState<PlanSection>(review?'safety':'itinerary');
  const [adjustOpen,setAdjustOpen] = useState(false);
  const [revisionChoice,setRevisionChoice] = useState('change campsite');
  const [reviewRequest,setReviewRequest]=useState(0);
  const tabRefs = useRef<(HTMLButtonElement|null)[]>([]);
  const prefix = useId().replaceAll(':','');
  const logisticsAssessment = data.assessments.find(item=>item.kind==='LOGISTICS');
  const safetyAssessment = data.assessments.find(item=>item.kind==='SAFETY');
  const logistics = logisticsAssessment?.result as Logistics|undefined;
  const safety = safetyAssessment?.result as Safety|undefined;
  const recommendation = data.recommendations?.result;
  const logisticsAudit = data.model_assessment_audits?.LOGISTICS;
  const noMatch = recommendation?.search_outcome==='NO_MATCH';
  const {version,run,confirmed_context:confirmed} = data;
  const candidatePreview=!!data.revision_comparison&&!data.revision_comparison.decision
    &&data.revision_comparison.after.run.run_id===run?.run_id&&data.trip_series?.is_current!==false;
  const savedFinal=data.last_final??data.series_last_final;
  const failure=failureGuidance(data);
  const savedApprovalScope = version?.status==='FINALISED'&&run?.status==='SUCCEEDED'
    &&data.last_final?.is_current===true
    &&data.last_final.run_id===version.version_context.run_id
    &&data.last_final.plan_version_id===version.version_context.plan_version_id;
  const validApproval = !data.current_inputs_error&&data.reviews.some(item=>item.decision==='APPROVE'&&(
    item.review_id===data.eligibility?.valid_review_id||(snapshot&&version?.status==='FINALISED')||savedApprovalScope));
  // Historical approval is a saved fact, never a current authorisation.
  const historicalApproval = !data.current_inputs_error&&run?.status==='SUCCEEDED'
    &&version?.status==='FINALISED'&&!savedApprovalScope
    &&data.final_history.some(item=>item.plan_id===version.version_context.plan_id
      &&item.run_id===version.version_context.run_id
      &&item.plan_version_id===version.version_context.plan_version_id)
    &&data.reviews.some(item=>item.decision==='APPROVE'&&item.version_context
      &&(['plan_id','plan_version_id','run_id','input_fingerprint'] as const).every(
        key=>item.version_context![key]===version.version_context[key]));
  const displayedApproval = validApproval||historicalApproval;
  const safetyReviewDecision = boundReview(data)?.decision;
  const roadClosed = safety?.evidence.some(item=>item.kind==='ROAD'&&item.road_state==='CLOSED');
  const requirements = confirmed?.requirements;
  const title = version?.content.selected_campsite_ids.map(campName).join(' / ') || requirements?.destination || 'My camping plan';
  const stepSaved = [!!recommendation,!!version,!!version,!!logistics,!!safety,!!data.route,run?.status==='SUCCEEDED'];
  const qualityIssues = safety ? Object.entries(safety.data_quality).filter(([,value])=>value!=='AVAILABLE') : [];
  const qualityGroups = new Map<string,string[]>();
  qualityIssues.forEach(([kind,status])=>{const state=safetyCondition(kind,status,safety?.evidence??[],requirements);const text=state.title+', '+state.detail;qualityGroups.set(text,[...(qualityGroups.get(text)??[]),checkNames[kind]??'Safety information']);});
  const preparationCodes=['ESSENTIAL_GEAR_MISSING','TRANSPORT_UNAVAILABLE','LOGISTICS_INCOMPLETE','COSTS_INCOMPLETE'];
  const onlyPreparationBlocked=!!safety&&safety.mandatory_blockers.length>0&&safety.mandatory_blockers.every(item=>preparationCodes.includes(item.code));
  const safetyText = !safety ? 'Not checked' : roadClosed ? 'Road closed; change the plan' : qualityIssues.length ? qualityIssues.some(([,status])=>status==='CONFLICTING')?'Conflicting safety information; verification required':qualityIssues.some(([,status])=>status==='STALE')?'Safety information needs updating':'Safety information needs confirmation' : safety.mandatory_blockers.some(item=>item.code==='CAMPSITE_CLOSED')?'Campsite closed; adjust the plan':safety.mandatory_blockers.some(item=>item.code==='FIRE_PROHIBITED')?'Adjust campfire arrangements':onlyPreparationBlocked?'Equipment and transport preparation incomplete':safety.outcome==='BLOCKED'?'Safety conditions not met':historicalApproval&&safety.outcome==='REVIEW' ? 'Approved in the earlier review' : validApproval&&safety.outcome==='REVIEW' ? 'Review approved' : safetyReviewDecision==='REQUEST_REVISION'?'Revision requested':safetyReviewDecision==='REJECT'?'Review rejected': safety.requires_human_review ? 'Human review required' : label(safety.outcome);
  const rawWarnings=data.eligibility?.blocking_reasons??[];
  const hiddenCodes = new Set(['VERSION_STATE','ASSESSMENT_BLOCKED','RUN_NOT_SUCCEEDED','REVISION_REQUIRED','REVIEW_REQUIRED',
    ...(qualityIssues.length?['EVIDENCE_COVERAGE','EVIDENCE_UNAVAILABLE','ROAD_UNAVAILABLE']:[]),
    ...(rawWarnings.some(item=>item.code==='ROAD_CLOSED')?['ROAD_UNAVAILABLE']:[])]);
  if(run?.status==='FAILED')['ASSESSMENTS_MISSING','ITINERARY_MISSING'].forEach(code=>hiddenCodes.add(code));
  const weatherFields:Record<string,string>={'gear_rule_input.forecast_rain_mm':'Rainfall','gear_rule_input.temperature_max_c':'Maximum temperature',
    'gear_rule_input.temperature_min_c':'Minimum temperature','gear_rule_input.wind_kph':'Wind speed',
    'evidence.weather.forecast_rain_mm':'Rainfall','evidence.weather.temperature_max_c':'Maximum temperature',
    'evidence.weather.temperature_min_c':'Minimum temperature','evidence.weather.wind_kph':'Wind speed'};
  const missingWeather=[...new Set((logistics?.clarifications??[]).flatMap(item=>weatherFields[item.field]?[weatherFields[item.field]]:[]))];
  const weatherOnlyLogistics = missingWeather.length>0 && logistics?.transport_feasible===true && !logistics.mandatory_blockers.length && logistics.clarifications.every(item=>!!weatherFields[item.field]);
  const mealUnknown=needsMealChoice(logistics?.clarifications??[]);
  const logisticsIssues=data.logistics_issues??[];
  const cookingPreparation=(data as PlanDetail&{cooking_preparation?:CookingPreparation|null}).cooking_preparation;
  const cookingAttention=!!data.current_inputs_error||logisticsIssues.some(item=>['camping_stove','fuel_canister'].includes(item.item_key??'')||item.code==='COOKING_ARRANGEMENT')
    ||!!logistics?.gear_checklist.some(item=>['camping_stove','fuel_canister'].includes(item.item_key)&&item.essential&&(item.missing_quantity==null||Number(item.missing_quantity)>0));
  if(logisticsIssues.length)['LOGISTICS_INCOMPLETE','COSTS_INCOMPLETE','ESSENTIAL_GEAR_MISSING','TRANSPORT_UNAVAILABLE'].forEach(code=>hiddenCodes.add(code));
  const warnings = [...new Set(rawWarnings.filter(item=>!hiddenCodes.has(item.code)).map(item=>roadClosed&&item.code==='ROAD_UNAVAILABLE'?'The access road is closed. Choose a campsite with an open route.':mealUnknown&&['LOGISTICS_INCOMPLETE','COSTS_INCOMPLETE'].includes(item.code)?'Select a meal arrangement first to determine food costs and cooking equipment.':item.code==='LOGISTICS_INCOMPLETE'&&weatherOnlyLogistics?'Applicable weather information is missing; equipment checks remain incomplete.':blockerText(item.code)))];
  const overBudget = logistics?.budget_difference_cents != null && logistics.budget_difference_cents > 0;
  const hasSafetyIssue = !!safety && (qualityIssues.length>0 || (!displayedApproval&&(safety.outcome!=='PASSED' || safety.requires_human_review)));
  const checkState=planCheckState(data,{snapshot,readError:!!error});
  const tone=checkState.tone,stateText=checkState.title;
  const choicePending=!!pendingRevision(data);
  useEffect(()=>{setSection(review?'safety':'itinerary');setAdjustOpen(false);setRevisionChoice('change campsite');setReviewRequest(0);},[run?.run_id,version?.version_context.plan_version_id,review]);
  function keyboardTabs(event:KeyboardEvent<HTMLButtonElement>,index:number) {
    let target=index;
    if(event.key==='ArrowRight')target=(index+1)%PLAN_SECTIONS.length;
    else if(event.key==='ArrowLeft')target=(index+PLAN_SECTIONS.length-1)%PLAN_SECTIONS.length;
    else if(event.key==='Home')target=0;
    else if(event.key==='End')target=PLAN_SECTIONS.length-1;
    else return;
    event.preventDefault();setSection(PLAN_SECTIONS[target].id);tabRefs.current[target]?.focus();
  }
  const pane = (id:PlanSection) => ({id:prefix+'-'+id,role:'tabpanel' as const,'aria-labelledby':prefix+'-tab-'+id,hidden:section!==id,className:'plan-tab-panel',tabIndex:0});
  return <div className="plan-result">
    <div className="plan-toolbar"><Link className="text-link" to={review?'/review':'/plans'}>← {review?'Review queue':'My plans'}</Link><div>
      {!review&&!snapshot&&<Link className="text-link" to={'/request/'+(confirmed?.request_id??data.plan.request_id)}>View request ↗</Link>}
      <button className="secondary-button" onClick={refresh}>Refresh</button>
    </div></div>
    {!review&&!snapshot&&<RevisionComparison value={data.revision_comparison} planId={data.plan.plan_id} refresh={refresh} readOnly={!!data.trip_series&&!data.trip_series.is_current}/>}
    <header className="plan-overview">
      <div className="plan-overview-title"><span className="eyebrow">{snapshot?'Saved plan':candidatePreview?'Proposed new plan':'Camping plan for this trip'}</span>
        <h1>{title}</h1><p>{requirements?.destination??'Destination to confirm'}{version&&' · Version '+version.version_number}</p>
      </div>
      <span className={'plan-status plan-status-'+tone}><i aria-hidden="true"/>{stateText}</span>
      <dl className="plan-facts">
        <div><dt>Trip dates</dt><dd>{requirements?.start_date??'To be confirmed'} <span>—</span> {requirements?.end_date??'To be confirmed'}</dd><small>{requirements?.duration_nights??'—'} nights · {requirements?.duration_days??'—'} days · {confirmed?.profile_snapshot.group_size??'—'} people</small></div>
        <div className={overBudget?'fact-attention':''}><dt>{data.current_inputs_error?'Previous cost estimate':'Estimated trip cost'}</dt><dd>{aud(logistics?.total_cents)}</dd><small>Budget {aud(requirements?.budget_cents)}{logistics?.budget_difference_cents!=null&&' · '+(overBudget?'Over by ':'Remaining ')+aud(Math.abs(logistics.budget_difference_cents))}</small></div>
        <div className={hasSafetyIssue||safety?.risk_level==='HIGH'?'fact-attention':''}><dt>{data.current_inputs_error?'Previous safety check':'Safety checks'}</dt><dd>{safetyText}</dd><small>{!safety?'View check results after planning':onlyPreparationBlocked&&safety.risk_level==='LOW'?'Review and complete preparations on the Equipment page.':safety.risk_level==='UNKNOWN'?'Insufficient information to determine risk.':'Risk '+label(safety.risk_level)+(review?' · Evidence completeness '+label(safety.confidence):'')}</small></div>
      </dl>
    </header>
    {error&&<p className="error-box" role="alert">Could not read updates: {error}</p>}
    {!review&&!snapshot&&<CheckFeedback data={data}/>}
    {!snapshot&&candidatePreview&&<div className="mode-notice">Previewing a new plan; the original remains the current arrangement.<Link className="text-link" to={'/plans/'+data.plan.plan_id}>Back to current plan ↗</Link></div>}
    {!snapshot&&!candidatePreview&&run&&(!run.is_active||data.trip_series?.is_current===false)&&<div className="mode-notice"><span>Viewing a historical plan. Assessments use the information and evidence from that time, not the latest update.</span>{data.trip_series?.is_current===false?data.trip_series.current_plan_id&&<Link className="secondary-button" to={'/plans/'+data.trip_series.current_plan_id}>View the current plan for this trip</Link>:current&&<button className="secondary-button" onClick={current}>View current plan</button>}</div>}
    {failure&&<section className="panel error-box" role="alert" aria-label="Recovery information for this run"><h2>{failure.title}</h2>
      <p>{failure.explanation}</p>
      {failure.saved.length>0?<p>Saved: {failure.saved.join(', ')}.</p>:<p>No itinerary has been saved for this run.</p>}
      <p>{failure.completionNote}</p>
      {run?.error&&<details><summary>View failure reason</summary><p>{run.error.message}</p></details>}
      {!review&&!snapshot&&<RetryPlanning data={data} refresh={refresh}/>}
    </section>}
    {!review&&!snapshot&&(!data.trip_series||data.trip_series.is_current)&&run?.is_active&&run.status==='FAILED'&&requirements&&<details className="panel"><summary>Profile or trip requirements changed? Replan</summary>
      <p>Resuming unfinished steps uses the information confirmed for this run. If your profile changed, save it and use the option below to review and generate a new plan. The original itinerary is retained.</p>
      <ReplanFromProfile key={data.plan.plan_id} source={{plan_id:data.plan.plan_id,expected_series_revision:data.trip_series?.series_revision??0,expected_current_version_id:data.plan.current_version_id,expected_version_revision:data.current_version_revision??null,expected_active_run_id:run!.run_id,expected_run_revision:run!.revision}} previousProfile={confirmed!.profile_snapshot} refreshSource={refresh}/>
    </details>}
    {!checkState.running&&!choicePending&&!['PENDING','RUNNING'].includes(run?.status??'')&&(warnings.length>0 || overBudget || hasSafetyIssue)&&<section className="plan-attention" role="alert" aria-label="Issues requiring action">
      <div><span className="attention-mark" aria-hidden="true">!</span><div><h2>{data.current_inputs_error?'Issues from the previous check':'Resolve before confirming this plan'}</h2><ul>
        {overBudget&&<li>Estimated trip cost exceeds budget by {aud(logistics?.budget_difference_cents)}.</li>}
        {[...qualityGroups.entries()].map(([text,names])=><li key={text}>{names.join(', ')}: {text}</li>)}
        {warnings.map(message=><li key={message}>{message}</li>)}
        {hasSafetyIssue&&!qualityIssues.length&&!warnings.length&&<li>{onlyPreparationBlocked?'Equipment and transport preparations are incomplete. Address missing items on the Equipment page.':`Safety assessment: ${label(safety?.outcome)}. View risks and recommendations.`}</li>}
      </ul></div></div>
      {hasSafetyIssue&&<button className="secondary-button" onClick={()=>{const gear=onlyPreparationBlocked&&!qualityIssues.length;setSection(gear?'gear':'safety');tabRefs.current[gear?1:3]?.focus();}}>{onlyPreparationBlocked&&!qualityIssues.length?'View equipment and transport':'View safety information'}</button>}
    </section>}
    {review&&data.current_inputs_error&&<div className="mode-notice"><strong>Check results need updating</strong><p>The evidence for this plan cannot currently be verified against the current information. Update checks before continuing review.</p><details><summary>View system details</summary><p>{data.current_inputs_error}</p></details></div>}
    {cookingPreparation&&(!canHideCookingPreparation(cookingPreparation)||cookingAttention)&&!logisticsIssues.some(item=>item.cooking_preparation)&&<div className="panel">
      <CookingPreparationPanel value={cookingPreparation} attention={cookingAttention}/>
      {!snapshot&&!review&&run?.is_active&&data.trip_series?.is_current!==false&&!['PENDING','RUNNING'].includes(run.status)&&
        <Link className="text-link" to={'/profile?plan_id='+encodeURIComponent(data.plan.plan_id)+'&focus=equipment.camping_stove'}>Check stove and fuel details together ↗</Link>}
    </div>}
    {logisticsIssues.length>0&&<details className="panel logistics-problem-details" id={prefix+'-logistics-problems'}><summary>Costs and equipment: view issues and actions ({logisticsIssues.length})</summary><LogisticsIssues items={logisticsIssues} disabled={!!error||choicePending||checkState.running||snapshot||review||!run?.is_active||data.trip_series?.is_current===false||['PENDING','RUNNING'].includes(run?.status??'')} onSafety={()=>{setSection('safety');tabRefs.current[3]?.focus();}}
      onRevisionRequested={!error&&!choicePending&&!checkState.running&&!review&&!snapshot&&data.revision_available?goal=>{setRevisionChoice(goal);setAdjustOpen(true);revealRevisionPanel(prefix+'-adjust');}:undefined}/></details>}
    {!snapshot&&<AssistanceNotes notes={data.review_assistance_notes??[]} historical={!run?.is_active||data.trip_series?.is_current===false}/>}
    {!review&&!snapshot&&<AssistanceNextAction data={data} onRecheck={()=>{setAdjustOpen(true);revealRevisionPanel(prefix+'-adjust');}}/>}
    {!review&&!snapshot&&checkState.kind!=='confirm'&&<NextSteps data={data} onReviewRevision={revisionReview(data)?()=>{setReviewRequest(value=>value+1);setAdjustOpen(true);revealRevisionPanel(prefix+'-adjust');}:undefined} onRecheck={()=>{setAdjustOpen(true);document.getElementById(prefix+'-adjust')?.scrollIntoView({block:'start'});}}/>}
    {!snapshot&&!review&&data.trip_series&&!data.trip_series.is_current&&<div className="mode-notice">This is a historical plan. Its tasks were superseded by a successor plan; previous approvals do not authorise new results.{data.trip_series.current_plan_id&&<Link to={'/plans/'+data.trip_series.current_plan_id}>View current plan ↗</Link>}</div>}
    {!snapshot&&!review&&savedFinal&&<div className="saved-plan-notice"><span>{['PENDING','RUNNING'].includes(run?.status??'')?'Previous final plan retained; current checks are incomplete':savedFinal.is_current?'Current final plan saved':'A historical final plan is retained; this does not mean the current checks have passed'}</span><Link className="text-link" to={'/plans/'+savedFinal.plan_id+'/finals/'+savedFinal.final_id}>View saved plan ↗</Link></div>}
    {!error&&!choicePending&&!checkState.running&&!review&&!snapshot&&(data.revision_available||data.reassessment_available)&&<details className="plan-adjust" id={prefix+'-adjust'} key={run?.run_id} open={adjustOpen} onToggle={event=>setAdjustOpen(event.currentTarget.open)}>
      <summary>Modify plan <span aria-hidden="true">↗</span></summary><ChangePlanning data={data} refresh={refresh} reviewRequest={reviewRequest} choice={revisionChoice} onChoiceChange={setRevisionChoice}/>
    </details>}
    {run&&run.operation!=='REASSESS'&&['PENDING','RUNNING'].includes(run.status)&&<div className="plan-live-progress" role="status"><span className="progress-pulse" aria-hidden="true"/><span>In progress:{label(run.stage)}, Updates automatically when complete.</span></div>}
    <div className="plan-tabs" role="tablist" aria-label="Plan contents">
      {PLAN_SECTIONS.map((tab,index)=><button key={tab.id} ref={node=>{tabRefs.current[index]=node;}} id={prefix+'-tab-'+tab.id} type="button" role="tab" aria-selected={section===tab.id} aria-controls={prefix+'-'+tab.id} tabIndex={section===tab.id?0:-1} onClick={()=>setSection(tab.id)} onKeyDown={event=>keyboardTabs(event,index)}>
        {noMatch&&tab.id==='itinerary'?'Campsite comparison':tab.title}{((tab.id==='safety'&&hasSafetyIssue)||(tab.id==='cost'&&overBudget))&&<i className="tab-alert" aria-label="Issues to address"/>}
      </button>)}
    </div>
    <div {...pane('itinerary')}>
      {version&&!noMatch&&version.content.selected_campsite_ids.map(id=><PlanningExplanationPanel key={id} siteId={id} catalogueId={data.campsite_catalogue_id} value={data.planning_explanation?.selected_campsite_id===id?data.planning_explanation:null} currentRunId={run?.run_id} siteName={campName(id)} requirements={requirements} accessibility={confirmed?.profile_snapshot.accessibility_requirements} reasons={recommendation?.candidates.find(item=>item.campsite_id===id)?.reasons??[]} uncertainties={recommendation?.candidates.find(item=>item.campsite_id===id)?.material_uncertainties??[]}/>)}
      {noMatch?data.recommendation_guidance?<NearMatches value={data.recommendation_guidance} planId={data.plan.plan_id} readOnly={snapshot||review||!run?.is_active||data.trip_series?.is_current===false}/>:<section className="panel"><h2>No campsites meet the requirements</h2><p>View excluded campsite reasons under Records, adjust conditions and reconfirm the request.</p></section>:<section className="panel itinerary-panel"><div className="section-title"><span className="eyebrow">Itinerary</span><h2>Itinerary</h2></div>
        {version?<><div className="itinerary-camps">{version.content.selected_campsite_ids.map(id=><span key={id}>{campName(id)}</span>)}</div>
          {run?.operation==='REASSESS'&&<p className="muted">The itinerary is unchanged.{!snapshot&&!review&&'Progress and results for this check appear above.'}{logisticsAudit&&'Equipment and budget suggestions are on the relevant pages.'}</p>}
          <p className="mode-notice">All times below are suggested and pending confirmation. They are not verified check-in, check-out or transport times. Confirm actual arrangements separately.</p>{version.content.itinerary_entries.length?<DailyItinerary entries={version.content.itinerary_entries} time={time} label={label}/>:<p className="muted">No itinerary entries were provided.</p>}

        </>:<div className="plan-empty"><span aria-hidden="true">⌁</span><h3>Preparing itinerary</h3><p>{run?.status==='FAILED'?'Address the execution issue above before continuing planning.':'Your camping arrangements will appear here after planning.'}</p></div>}
      </section>}
      {version&&!noMatch&&<TripPreparation value={data.preparation_summary}/>}
      {recommendation&&!noMatch&&<details className="panel recommendation-panel"><summary>Compare other recommended campsites <span>{recommendation.candidates.length} items</span></summary>
        <ol className="candidate-list">{recommendation.candidates.map(item=><li key={item.campsite_id}><h3>#{item.rank} · {campName(item.campsite_id)}</h3><ul>{item.reasons.map((reason,index)=>{const text=englishSavedReason(reason);return <li key={index}>{displayProse(text)??visitorText(text)}</li>;})}</ul>{item.material_uncertainties.map((uncertainty,index)=><p className="muted" key={index}>Uncertain: {displayProse(uncertainty)??visitorText(uncertainty)}</p>)}</li>)}</ol>
      </details>}
    </div>
    <div {...pane('gear')}><section className="panel"><div className="section-title"><span className="eyebrow">Departure preparation</span><h2>Equipment and logistics</h2></div>
      {logistics?<><p>Assessment:{label(logistics.outcome)} · Transport: {logistics.transport_feasible===null?'Needs verification':logistics.transport_feasible?'Feasible':'Not feasible'}</p>
        <TentCapacityPanel value={data.tent_capacity}/><div className="table-scroll"><table><caption>Other equipment quantities and gaps</caption><thead><tr>{['Equipment','Required','Available','Shortfall','Unit','Capacity requirement','Arrangement','Essential'].map(title=><th key={title}>{title}</th>)}</tr></thead><tbody>{logistics.gear_checklist.filter(item=>item.item_key!=='tent').map((item,index)=><tr key={index} className={item.essential&&(item.missing_quantity==null||Number(item.missing_quantity)>0)?'gear-gap':''}>
          <td>{equipmentLabel(item.item_key)}</td><td>{item.required_quantity??'Unknown'}</td><td>{item.available_quantity??'Unknown'}</td><td>{item.missing_quantity??'Unknown'}</td><td>{unitName(item.unit)}</td><td>{item.capacity_requirement===null?'Unknown':`${item.capacity_requirement} people`}</td><td>{label(item.arrangement_status)}</td><td>{item.essential?'Yes':'No'}</td>
        </tr>)}</tbody></table></div>{!logistics.gear_checklist.length&&<p className="muted">No equipment list was provided.</p>}
        <Blockers review={review} items={logistics.mandatory_blockers}/>{missingWeather.length>0&&<div className="clarifications"><p>Missing applicable {missingWeather.join(', ')} information for this trip; equipment requirements cannot yet be calculated completely.</p><button className="secondary-button" onClick={()=>{setSection('safety');tabRefs.current[3]?.focus();}}>View safety information</button></div>}{logisticsIssues.length>0?<p className="muted">Specific gaps, current records and update links appear in the task list above.</p>:logisticsQuestions(logistics.clarifications.filter(item=>!weatherFields[item.field])).map((text,index)=><p className="clarifications" key={index}>{text}</p>)}
      </>:<p className="plan-empty-text">No equipment and logistics assessment has been saved.</p>}
    </section><LogisticsPlanPanel value={logisticsAudit} section="gear" money={aud} itemName={equipmentLabel} unitName={unitName}/></div>
    <div {...pane('cost')}><section className="panel"><div className="section-title"><span className="eyebrow">Camping budget</span><h2>Costs and budget</h2></div>
      {logistics?<><div className="cost-summary"><div><span>Cost estimate</span><strong>{aud(logistics.total_cents)}</strong></div><div><span>Known cost subtotal</span><strong>{aud(logistics.known_subtotal_cents)}</strong></div><div><span>Group budget</span><strong>{aud(requirements?.budget_cents)}</strong></div><div className={overBudget?'cost-over-budget':''}><span>{logistics.budget_difference_cents===null?'Budget difference':overBudget?'Over budget':'Remaining budget'}</span><strong>{aud(logistics.budget_difference_cents===null?null:Math.abs(logistics.budget_difference_cents))}</strong></div></div>
        {logistics.total_cents===null&&<p className="clarifications">Costs are incomplete; the known subtotal is not a final total.</p>}
        <div className="table-scroll"><table><caption>Cost breakdown (AUD)</caption><thead><tr>{['Item','Quantity / Unit','Unit price','Subtotal'].map(title=><th key={title}>{title}</th>)}</tr></thead><tbody>{logistics.cost_breakdown.map((line,index)=><tr key={index}>
          <td>{label(line.category)}{line.category==='CAMPSITE'&&<small className="cost-site">{campName(line.item_key)}</small>}</td><td>{line.unit==='per_person_per_day'&&confirmed?.profile_snapshot.group_size!=null&&requirements?.duration_days!=null&&line.quantity!=null&&Number(line.quantity)===confirmed.profile_snapshot.group_size*requirements.duration_days?`${confirmed.profile_snapshot.group_size} people × ${requirements.duration_days} days`:`${line.quantity??'Unknown'} ${unitName(line.unit)}`}</td><td>{aud(line.unit_price_cents)}</td><td>{aud(line.subtotal_cents)}</td>
        </tr>)}</tbody></table></div>
        <div className="cost-notes"><p className="muted">Costs are estimates. Actual spending depends on prices when booking, purchasing and travelling.</p>{logistics.cost_breakdown.some(line=>line.unit==='per_person_per_day')&&<p className="muted">Food and drinking water are estimated by group size and trip days, using a per-person daily rate.</p>}{logistics.cost_breakdown.some(line=>line.unit==='per_kilometre')&&<p className="muted">Transport costs are estimated from the recorded total distance.</p>}{logistics.cost_breakdown.some(line=>line.unit==='not_procured')&&<p className="muted">Deferred equipment is not included in purchase costs. Confirm how it will be obtained and any costs.</p>}</div>
      </>:<p className="plan-empty-text">No costs have been saved; amounts are unknown.</p>}
    </section><LogisticsPlanPanel value={logisticsAudit} section="cost" money={aud} itemName={equipmentLabel} unitName={unitName}/></div>
    <div {...pane('safety')}><SafetyInformation coverage={data.trip_evidence_coverage} requestId={data.plan.request_id} planId={data.plan.plan_id} readOnly={snapshot||review||!run?.is_active||data.trip_series?.is_current===false} value={safety} requirements={requirements} historical={snapshot||(!run?.is_active&&!candidatePreview)||data.trip_series?.is_current===false} saved={version?.status==='FINALISED'} readyForFinalSave={!data.current_inputs_error&&!candidatePreview&&(review?data.eligibility?.eligible===true:data.finalisation_available)} decision={safetyReviewDecision} approved={displayedApproval} review={review} outdated={!!data.current_inputs_error} blockers={<><LogisticsIssues items={logisticsIssues.filter(item=>item.item_key||item.target==='PROFILE')} summary onGear={()=>{setSection('gear');tabRefs.current[1]?.focus();}} onSafety={()=>{}} disabled/><Blockers review={review} items={(safety?.mandatory_blockers??[]).filter(item=>!logisticsIssues.length||!['ESSENTIAL_GEAR_MISSING','TRANSPORT_UNAVAILABLE','LOGISTICS_INCOMPLETE','COSTS_INCOMPLETE'].includes(item.code))}/></>} notes={null} rawWarnings={rawWarnings} sources={refs=><Sources refs={refs}/>} label={label}/></div>
    <div {...pane('history')}>
      <section className="panel progress-panel"><div className="section-title"><span className="eyebrow">Versions and runs</span><h2>Planning records</h2></div>
        {run?<><p>{label(run.operation)} · {label(run.status)}</p><ol className="progress-stages">{STAGES.map((stage,index)=>{const skipped=(noMatch&&run.status==='SUCCEEDED'&&index>0&&index<6)||(run.operation==='REASSESS'&&index===0);const currentStage=run.stage===stage&&!stepSaved[index]&&!skipped;return <li key={stage} className={stepSaved[index]?'stage-saved':currentStage?'stage-current':''}><span>{index+1}</span><strong>{label(stage)}</strong><small>{skipped?'Not required':stepSaved[index]?run.operation==='REASSESS'&&(index===1||index===2)?'Reuse saved':'Saved':currentStage?run.status==='FAILED'?'Stop here':'Current stage':'No outputs yet'}</small></li>;})}</ol>
          <details><summary>View run records ({data.events.length})</summary>{data.events.length?<ol className="event-list">{data.events.map(event=><li key={event.id}>{time(event.created_at)} · {label(event.stage)} · {label(event.status)}{event.error&&<p>{visitorText(event.error.message)}</p>}</li>)}</ol>:<p className="muted">No run records yet.</p>}</details>
        </>:<p className="muted">No plan registered yet.</p>}
      </section>
      <ModelRunDiagnostics allowed={data.can_view_model_diagnostics} value={data.model_diagnostics} currentRunId={run?.run_id}/>
      <section className="panel"><h2>Review records</h2>{data.reviews.length?data.reviews.map(item=><article key={item.review_id}><h3>{item.decision==='APPROVE'?'Approved':item.decision==='REJECT'?'Rejected':'Request revision'}</h3><p>{visitorText(item.reason)}</p><small>Reviewer: {item.reviewer_user_id}</small></article>):<p className="muted">No review decision yet.</p>}</section>
      <section className="panel"><h2>Request for this trip</h2>{confirmed&&<><p>{requirements?.start_date} → {requirements?.end_date} · {requirements?.duration_nights} nights / {requirements?.duration_days} days · {aud(requirements?.budget_cents)}</p><ConfirmedRequirementsList requirements={confirmed.requirements} accessibility={confirmed.profile_snapshot.accessibility_requirements}/><details><summary>Profile used for this run</summary><ProfileSummary profile={confirmed.profile_snapshot} systemPreparation={!!data.preparation_summary}/></details></>}
        <details className="source-details"><summary>Record IDs and input fingerprints</summary><p className="identifier">{run?.run_id??'Not registered'}</p><p className="identifier">{version?.version_context.input_fingerprint??'No version fingerprint saved yet'}</p></details>
        {recommendation&&recommendation.excluded_candidates.length>0&&<details className="source-details"><summary>Original exclusion reasons</summary>{recommendation.excluded_candidates.map(item=><article key={item.campsite_id}><h3>{campName(item.campsite_id)}</h3><ul>{item.reasons.map((reason,index)=><li key={index}>{visitorText(reason)}</li>)}</ul></article>)}</details>}
        {!review&&!snapshot&&<><h3>Saved plans</h3>{data.final_history.length?<ul className="plan-history-list">{data.final_history.map(item=><li key={item.final_id}><Link to={'/plans/'+item.plan_id+'/finals/'+item.final_id}>Version {item.version_number} · {item.is_current?'Current plan':'Historical plan'}<small>{time(item.finalised_at)}</small></Link></li>)}</ul>:<p className="muted">No final plan has been saved.</p>}
          <h3>Version and assessment history</h3><ul className="plan-history-list">{data.run_history.map(item=><li key={item.run_id}><Link to={'/plans/'+data.plan.plan_id+'?run_id='+encodeURIComponent(item.run_id)}>{item.version_number?`Version ${item.version_number}`:'No versions yet'} · {label(item.status)}<small>{time(item.created_at)}</small></Link>{item.run_id===data.plan.active_run_id&&<span className="tag">Current</span>}</li>)}</ul>
        </>}
      </section>
    </div>
    {review&&reviewActions}
    {!review&&!snapshot&&(!data.revision_comparison||!!data.revision_comparison.decision)&&<section className="panel plan-save" id={prefix+'-save'}><div><span className="eyebrow">Save plan</span><h2>{['PENDING','RUNNING'].includes(run?.status??'')?'Current checks are incomplete':version?.status==='FINALISED'?'Plan saved':'Save camping plan'}</h2>{!data.finalisation_available&&version?.status!=='FINALISED'&&<p className="muted">Save after completing all required assessments and reviews.</p>}</div><FinalisePanel key={version?.version_context.input_fingerprint??run?.run_id} data={data} readError={!!error} onModify={!choicePending&&(data.revision_available||data.reassessment_available)?()=>{setAdjustOpen(true);revealRevisionPanel(prefix+'-adjust');}:undefined}/></section>}
  </div>;
}
