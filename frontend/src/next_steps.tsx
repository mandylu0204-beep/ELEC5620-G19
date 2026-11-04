import {boundReview} from './review_revision';
import {planCheckState} from './plan_check_state';
import { needsMealChoice } from './logistics_guidance';
import { Link } from 'react-router-dom';
import type { PlanDetail } from './plans';
import { tripUpdatePath } from './trip_update';

// Navigation guidance only; all operations remain controlled by server flags.
export function NextSteps({data,onRecheck,onReviewRevision}:{data:PlanDetail;onRecheck?:()=>void;onReviewRevision?:()=>void}) {
  const run=data.run;
  if(!run?.is_active||data.trip_series?.is_current===false||['PENDING','RUNNING','FAILED'].includes(run.status))return null;
  // A pending candidate must be selected or kept before opening a successor.
  if(data.revision_comparison&&!data.revision_comparison.decision)return null;
  const reasons=new Set(data.eligibility?.blocking_reasons.map(item=>item.code));
  const review=boundReview(data);
  const safety=data.assessments.find(item=>item.kind==='SAFETY')?.result;
  const roadClosed=!!safety&&'evidence' in safety&&safety.evidence.some(item=>item.kind==='ROAD'&&item.road_state==='CLOSED');
  const quality=safety&&'data_quality' in safety?Object.values(safety.data_quality):[];
  const logistics=data.assessments.find(item=>item.kind==='LOGISTICS')?.result;
  const mealUnknown=!!logistics&&'clarifications' in logistics&&needsMealChoice(logistics.clarifications);
  let title='Adjust the plan before confirming';
  let description='Address the listed issues. Changes to dates, group size, budget, preferences or profile require request reconfirmation.';
  if(data.current_inputs_error){
    title=data.current_inputs_state==='CHANGED'?'Previous check results need updating':'Checking service temporarily unavailable';
    description=data.current_inputs_state==='CHANGED'
      ? 'Source information or service settings changed. Previous cost and safety results are reference only. You can recheck the existing itinerary. Date, group-size or budget changes require request reconfirmation.'
      : 'Existing check results cannot currently be verified, so saving is unavailable. The itinerary and results are retained. Check again when service resumes.';
  }else if(data.recommendations?.result.search_outcome==='NO_MATCH'){
    title='Consider the closest campsites';description='The closest campsites and unmet conditions appear below. Adjust budget, dates or required conditions based on the differences, then reconfirm the request.';
  }else if(data.version?.status==='FINALISED'){
    title='Final plan saved; this trip can still be updated';
    description='Review this update and reconfirm changes to dates, group size, budget or profile. Saved final plans are retained. New plans require new checks and confirmation before saving.';
  }else if(data.finalisation_available&&data.eligibility?.eligible){
    title=review?.decision==='APPROVE'?'Review approved; awaiting your save confirmation':'Plan generated; awaiting your save confirmation';
    description='Review itinerary, costs, equipment and safety, then select the confirmation below to save the final plan.';
  }else if(roadClosed||reasons.has('ROAD_CLOSED')||reasons.has('CAMPSITE_CLOSED')||reasons.has('FIRE_PROHIBITED')){
    title=roadClosed||reasons.has('ROAD_CLOSED')?'Choose a campsite with an open route':reasons.has('CAMPSITE_CLOSED')?'Choose an open campsite':'Adjust campfire arrangements';
    description='Adjust arrangements according to trip restrictions, then check the new plan. Reviewers cannot override road or campsite closures or fire bans.';
  }else if(quality.some(value=>['MISSING','STALE','CONFLICTING'].includes(value))){
    const upcomingWeather=data.trip_evidence_coverage?.next_weather_check_on;
    title=upcomingWeather?'Itinerary generated; check weather close to departure':'Current information does not support a complete safety assessment';
    description=upcomingWeather?`Review the itinerary, equipment and costs now; the plan is retained. Suggested recheck: ${upcomingWeather} or later. Weather and other safety conditions depend on the results then.`:'View missing sources, coverage dates and conflicts on the Safety page. Adjust dates or campsite, or keep a draft and recheck after information updates. Repeating checks on the same day does not extend forecast coverage.';
  }else if((data.logistics_issues??[]).length){
    title='Continue this trip update';description='Save changes from the tasks above, then open Review this update to compare profiles and requirements. Confirmation starts new checks. The original check remains in the same trip history.';
  }else if(mealUnknown){
    title='Confirm meal arrangement first';description='The itinerary is retained. Adjust requirements below, choose ready-to-eat meals or self-catering and reconfirm. This determines food costs and equipment. Confirmed transport does not need re-entry.';
  }else if(review?.decision==='REQUEST_REVISION'||review?.decision==='REJECT'){
    title=review.decision==='REJECT'?'Review not approved; adjust the plan':'Reviewer requested plan changes';
    description='Adjust arrangements based on the review reason. Revise the plan to change campsite. Reconfirm requirements for changes to dates, budget, group size or preferences.';
  }else if(reasons.size===1&&reasons.has('REVIEW_REQUIRED')){
    title='Awaiting reviewer action';description='This plan needs human risk review. Continue after review is complete.';
  }
  const state=planCheckState(data);
  if(state.kind==='cancelled')return null;
  const heading=review&&['REQUEST_REVISION','REJECT'].includes(review.decision)?state.title:state.kind==='adjustment'?'Next':state.kind==='review'?'Awaiting human review':title;
  return <section className="panel next-steps" aria-label="What to do next"><h2>{heading}</h2><p>{description}</p>
    {data.current_inputs_error&&<>{data.current_inputs_state==='CHANGED'&&<p className="muted">Rechecking retains the current itinerary. Missing or inapplicable information will remain unresolved.</p>}
      {data.reassessment_available&&onRecheck?<button className="secondary-button" onClick={onRecheck}>Open recheck ↓</button>:<p className="muted">Checks cannot start now. The original itinerary is retained.</p>}
      <details className="source-details"><summary>View system details</summary><p>{data.current_inputs_error}</p></details></>}
    {review&&<div className="clarifications" role="status" aria-label="Reviewer feedback"><strong>Reviewer feedback</strong><blockquote>{review.reason}</blockquote>{['REQUEST_REVISION','REJECT'].includes(review.decision)&&<p>{review.decision==='REJECT'?'This plan was not approved.':'The reviewer requested changes.'} Review the reason before adjusting the plan; final saving remains unavailable until the required checks and approval are valid.</p>}</div>}
    {onReviewRevision&&<button type="button" className="primary-button" onClick={onReviewRevision}>Prepare revision using reviewer feedback ↓</button>}
    <div className="plan-actions"><Link className="text-link" to={tripUpdatePath(data.plan.plan_id)}>Review and adjust this trip requirements ↗</Link><Link className="text-link" to={'/profile?plan_id='+encodeURIComponent(data.plan.plan_id)+'&request_id='+encodeURIComponent(data.plan.request_id)}>Edit camping profile ↗</Link></div>
  </section>;
}
