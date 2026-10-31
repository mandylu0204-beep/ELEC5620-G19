import {FinalPdfDownload} from './final_pdf';
import { tripUpdatePath } from './trip_update';
import { Link, useParams } from 'react-router-dom';
import { PlanView, useSavedRead, type PlanDetail } from './plans';

const noPoll=()=>false;
type FinalRecord={preparation_summary?:PlanDetail['preparation_summary'];model_assessment_audits?:PlanDetail['model_assessment_audits'];tent_capacity?:PlanDetail['tent_capacity'];logistics_issues?:PlanDetail['logistics_issues'];planning_explanation?:PlanDetail['planning_explanation'];can_view_model_diagnostics?:boolean;model_diagnostics?:PlanDetail['model_diagnostics'];final_id:string;status:string;finalised_at:string;finalised_by:string;version_context:NonNullable<PlanDetail['version']>['version_context'];version_number:number;version_revision:number;content:NonNullable<PlanDetail['version']>['content'];confirmed_context:PlanDetail['confirmed_context'];assessments:PlanDetail['assessments'];review:PlanDetail['reviews'][number]|null;recommendations:PlanDetail['recommendations'];route:PlanDetail['route'];events:PlanDetail['events'];run:Omit<NonNullable<PlanDetail['run']>,'is_active'>};

// Navigation creates no changes to the saved snapshot. The update route reads
// current state again, then applies the existing ownership/concurrency guards.
export function FinalPlanNavigation({planId,isCurrent}:{planId:string;isCurrent:boolean}){
  return <><Link className="text-link" to={'/plans/'+encodeURIComponent(planId)}>View current plan ↗</Link>
    {isCurrent&&<Link className="text-link" to={tripUpdatePath(planId)}>Update this trip ↗</Link>}</>;
}

export function FinalPage(){
  const {planId,finalId}=useParams();const {data,error,refresh}=useSavedRead<{is_current:boolean;final_record:FinalRecord}>('/plans/'+planId+'/finals/'+finalId,noPoll);
  if(!data)return <section className="panel"><h1>Read final plan</h1>{error&&<p className="error-box" role="alert">{error}</p>}<button className="secondary-button" onClick={refresh}>Reload</button><Link className="text-link" to={'/plans/'+planId}>Back to current plan ↗</Link></section>;
  const saved=data.final_record;
  const view:PlanDetail={preparation_summary:saved.preparation_summary,model_assessment_audits:saved.model_assessment_audits,tent_capacity:saved.tent_capacity,logistics_issues:saved.logistics_issues,planning_explanation:saved.planning_explanation,can_view_model_diagnostics:saved.can_view_model_diagnostics,model_diagnostics:saved.model_diagnostics,plan:{plan_id:planId!,request_id:saved.confirmed_context?.request_id??'',active_run_id:saved.run.run_id,current_version_id:saved.version_context.plan_version_id,final_version_id:saved.version_context.plan_version_id,created_at:saved.run.created_at},run:{...saved.run,is_active:data.is_current},run_history:[],confirmed_context:saved.confirmed_context,events:saved.events,version:{version_number:saved.version_number,status:'FINALISED',revision:saved.version_revision,version_context:saved.version_context,content:saved.content},assessments:saved.assessments,recommendations:saved.recommendations,route:saved.route,eligibility:null,reviews:saved.review?[saved.review]:[],last_final:null,selected_final:null,final_history:[],finalisation_available:false};
  return <><section className="panel final-record-heading"><div className="saved-record-status"><span className="tag">{data.is_current?'Current final plan':'Historical final plan'}</span><strong className="saved-record-title">Saved final plan</strong></div><p>Saved: {new Intl.DateTimeFormat('en-AU',{timeZone:'Australia/Sydney',dateStyle:'medium',timeStyle:'short'}).format(new Date(saved.finalised_at))}(Sydney time) · Saved by: {saved.finalised_by}</p><div className="saved-record-tools">{saved.status==='FINALISED'&&<FinalPdfDownload planId={planId!} finalId={saved.final_id}/>}<details className="source-details"><summary>Save record ID</summary><p className="identifier">{saved.final_id}</p></details><FinalPlanNavigation planId={planId!} isCurrent={data.is_current}/></div>{!data.is_current&&<p className="saved-record-history">A revision or reassessment occurred later. This is the plan saved at that time.</p>}</section><PlanView data={view} error={error} refresh={refresh} snapshot/></>;
}
