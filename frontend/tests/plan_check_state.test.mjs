import test,{after} from 'node:test';
import assert from 'node:assert/strict';
import {createServer} from 'vite';
import {createElement as h} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {MemoryRouter} from 'react-router-dom';

const server=await createServer({configFile:false,envDir:false,appType:'custom',server:{middlewareMode:true,hmr:false,ws:false,watch:null},optimizeDeps:{noDiscovery:true}});
after(()=>server.close());
const {planCheckState,checkSteps}=await server.ssrLoadModule('/src/plan_check_state.ts');
const {PlanView}=await server.ssrLoadModule('/src/plans.tsx');
const {FinalisePanel}=await server.ssrLoadModule('/src/finalise.tsx');
const {SessionProvider}=await server.ssrLoadModule('/src/session.tsx');
const render=(component,props)=>renderToStaticMarkup(h(MemoryRouter,null,h(SessionProvider,null,h(component,props))));
function fixture(){
 const context={plan_id:'p',plan_version_id:'v',run_id:'r',input_fingerprint:'fp'};
 const artifact={execution_mode:'agent',source_refs:[],assumptions:[],uncertainties:[],mandatory_blockers:[]};
 return {plan:{plan_id:'p',request_id:'q',active_run_id:'r',current_version_id:'v'},run:{run_id:'r',revision:1,is_active:true,status:'SUCCEEDED',stage:'COMPLETED',operation:'PLAN',error:null},
  version:{status:'ELIGIBLE_FOR_FINALISATION',version_number:1,revision:1,version_context:context,content:{...artifact,selected_campsite_ids:['the-basin'],itinerary_entries:[{entry_kind:'CAMP',description:'Overnight',campsite_id:'the-basin',start_at:'2026-11-02T17:00:00+11:00',end_at:'2026-11-03T08:00:00+11:00'}]}},
  assessments:[{assessment_id:'l',kind:'LOGISTICS',version_context:context,result:{...artifact,outcome:'PASSED',transport_feasible:true,gear_checklist:[],cost_breakdown:[],total_cents:30000,budget_difference_cents:-10000,known_subtotal_cents:30000,clarifications:[]}},
   {assessment_id:'s',kind:'SAFETY',depends_on_assessment_id:'l',version_context:context,result:{...artifact,outcome:'PASSED',requires_human_review:false,risk_level:'LOW',confidence:'HIGH',data_quality:{WEATHER:'AVAILABLE',ROAD:'AVAILABLE',FIRE:'AVAILABLE',RESTRICTION:'AVAILABLE'},evidence:[],hazards:[],unresolved_conflicts:[],recommended_actions:[]}}],
  recommendations:{result:{...artifact,search_outcome:'MATCHES',candidates:[],excluded_candidates:[]}},
  confirmed_context:{requirements:{destination:'Sydney & Surrounds',budget_cents:40000,start_date:'2026-11-02',end_date:'2026-11-03',duration_nights:1,duration_days:2},profile_snapshot:{group_size:2,experience_level:'INTERMEDIATE',has_children:false,children_count:0,equipment:[],transport:{transport_type:'CAR',vehicle_count:1,estimated_km:'100',assumptions:[]},accessibility_requirements:[]},dataset_context:{dataset_version:'2.2.0'}},
  eligibility:{eligible:true,blocking_reasons:[],review_required:false,valid_review_id:null},finalisation_available:true,reviews:[],logistics_issues:[],run_history:[],final_history:[],last_final:null,selected_final:null,events:[],route:null};
}
const safety=data=>data.assessments[1].result;
function blocked(data,code){data.eligibility={...data.eligibility,eligible:false,blocking_reasons:[{code,message:code}]};data.finalisation_available=false;data.version.status='BLOCKED';}
test('every executing stage overrides a previous final and never changes saved source objects',()=>{
 for(const operation of ['PLAN','REVISE','REASSESS'])for(const stage of ['RECOMMENDING','GENERATING','SAVING_VERSION','ASSESSING_LOGISTICS','ASSESSING_SAFETY','ROUTING','COMPLETED']){
  const data=fixture();Object.assign(data.run,{operation,stage,status:'RUNNING'});data.version.status='FINALISED';const before=structuredClone(data);
  const state=planCheckState(data);assert.equal(state.title,'Checks incomplete');assert.equal(state.running,true);assert.deepEqual(data,before);
  assert.doesNotMatch(render(FinalisePanel,{data}),/Save as final plan/i);
 }
});
test('queue, failed execution, cancellation and unreadable current results have truthful explanations',()=>{
 const data=fixture();data.run.status='PENDING';assert.match(planCheckState(data).detail,/Waiting to start/i);
 data.run.status='FAILED';assert.equal(planCheckState(data).running,false);assert.match(planCheckState(data).detail,/stopped/i);
 data.run.status='CANCELLED';assert.equal(planCheckState(data).title,'Checks cancelled');
 data.run.status='SUCCEEDED';assert.equal(planCheckState(data,{readError:true}).title,'Checks incomplete');
 assert.doesNotMatch(render(FinalisePanel,{data,readError:true}),/Save as final plan/i);
});
test('new candidate progress and failure never borrow the selected original success',()=>{
 const data=fixture();data.version.status='FINALISED';data.revision_comparison={decision:null,status:'GENERATING',after:{run:{run_id:'candidate',status:'RUNNING',stage:'ASSESSING_SAFETY'}}};
 assert.equal(planCheckState(data).title,'Checks incomplete');
 const html=render(PlanView,{data,error:'',refresh(){}});assert.match(html,/Checks incomplete/i);assert.doesNotMatch(html,/check-step-passed|check-step-list|Resolve before confirming this plan/i);
 data.revision_comparison.after.run.status='FAILED';assert.equal(planCheckState(data).title,'Checks incomplete');
 data.revision_comparison.after.run.status='SUCCEEDED';data.revision_comparison.status='READY';assert.equal(planCheckState(data).title,'To be confirmed');assert.match(planCheckState(data).detail,/or mean safety checks passed/i);
 assert.doesNotMatch(render(FinalisePanel,{data}),/Save as final plan/i);
});
test('no campsite, budget, gear and missing evidence share one main status while reasons stay separate',()=>{
 for(const code of ['HARD_CONSTRAINT','ESSENTIAL_GEAR_MISSING','ROAD_CLOSED','EVIDENCE_COVERAGE']){
  const data=fixture();blocked(data,code);assert.equal(planCheckState(data).title,'Plan changes needed');
 }
 const data=fixture();data.recommendations.result.search_outcome='NO_MATCH';data.version=null;data.assessments=[];data.finalisation_available=false;
 assert.equal(planCheckState(data).title,'Plan changes needed');
 assert.deepEqual(checkSteps(data).map(item=>item.text),['Changes needed','Not started','Not started']);
});
test('original warning summary preserves independent causes and the exact budget amount without agent cards',()=>{
 const data=fixture();blocked(data,'ROAD_CLOSED');safety(data).mandatory_blockers=[{code:'ROAD_CLOSED',message:'closed'}];safety(data).data_quality.WEATHER='MISSING';
 data.assessments[0].result.budget_difference_cents=7200;data.logistics_issues=[{code:'OVER_BUDGET',target:'REQUEST'}];
 const html=render(PlanView,{data,error:'',refresh(){}});assert.match(html,/Resolve before confirming this plan/i);assert.match(html,/Estimated trip cost exceeds budget by AUD 72.00/i);assert.match(html,/Weather/i);assert.match(html,/Road closed/i);assert.doesNotMatch(html,/check-step-list|Itinerary Agent|Costs and equipment Agent|Safety Agent/i);
});
test('only an otherwise eligible review task waits for approval; missing evidence still needs adjustment',()=>{
 const data=fixture();blocked(data,'REVIEW_REQUIRED');data.version.status='ESCALATED';data.eligibility.review_required=true;safety(data).requires_human_review=true;safety(data).outcome='REVIEW';
 assert.equal(planCheckState(data).title,'Awaiting human review');assert.equal(checkSteps(data)[2].text,'Human judgement required');
 data.eligibility.blocking_reasons.push({code:'EVIDENCE_UNAVAILABLE',message:'missing'});safety(data).data_quality.WEATHER='MISSING';
 assert.equal(planCheckState(data).title,'Plan changes needed');assert.equal(checkSteps(data)[2].text,'Action needed');
});
test('approval is scoped to the saved context, does not clear unrelated blockers and cannot invent saving permission',()=>{
 const data=fixture();safety(data).requires_human_review=true;safety(data).outcome='REVIEW';
 data.reviews=[{review_id:'old',decision:'APPROVE',version_context:{...data.version.version_context,run_id:'old'}}];assert.notEqual(planCheckState(data).kind,'confirm');
 data.reviews=[{review_id:'current',decision:'APPROVE',version_context:{...data.version.version_context}}];assert.notEqual(planCheckState(data).kind,'confirm');data.eligibility.valid_review_id='current';assert.equal(planCheckState(data).title,'To be confirmed');
 data.finalisation_available=false;assert.notEqual(planCheckState(data).kind,'confirm');
});
test('incomplete artifact sets cannot claim passed even if stale capability flags remain',()=>{
 const data=fixture();data.assessments.pop();assert.equal(planCheckState(data).title,'Checks incomplete');assert.equal(checkSteps(data)[2].text,'Not started');
 assert.doesNotMatch(render(FinalisePanel,{data}),/Save as final plan/i);
});
test('ready to confirm offers save and modify, while history and candidate selection cannot save',()=>{
 const data=fixture();const html=render(FinalisePanel,{data,onModify(){}});
 assert.match(html,/Save as final plan/i);assert.match(html,/Modify plan and reassess/i);assert.match(html,/<button[^>]*disabled[^>]*>Save as final plan/i);
 for(const patch of [{run:{...data.run,is_active:false}},{trip_series:{is_current:false}},{finalisation_available:false}]){
  assert.doesNotMatch(render(FinalisePanel,{data:{...data,...patch},onModify(){}}),/Save as final plan/i);
 }
});
test('reassessment reuses itinerary but never reuses a passed badge for the currently running safety step',()=>{
 const data=fixture();Object.assign(data.run,{operation:'REASSESS',status:'RUNNING',stage:'ASSESSING_SAFETY'});data.assessments=[data.assessments[0]];
 assert.deepEqual(checkSteps(data).map(item=>item.text),['Reuse saved itinerary','Passed','In progress']);
});
test('outdated checks do not show an active spinner or grant finalisation; saved snapshots stay frozen',()=>{
 const data=fixture();data.current_inputs_error='changed';data.current_inputs_state='CHANGED';assert.equal(planCheckState(data).running,false);assert.match(planCheckState(data).detail,/has not started automatically/i);
 assert.ok(checkSteps(data).every(s=>s.state==='incomplete'));data.version.status='FINALISED';assert.equal(planCheckState(data,{snapshot:true}).title,'Final plan saved');
});
test('a soft preference note does not fail a complete eligible plan',()=>{
 const data=fixture();data.recommendations.result.candidates=[{campsite_id:'the-basin',material_uncertainties:['Preferred shower facilities not available'],reasons:[]}];
 assert.equal(planCheckState(data).title,'To be confirmed');
});

test('old assessment bindings cannot provide a passed badge or a save action for the current version',()=>{
 const data=fixture();data.assessments[1].version_context={...data.version.version_context,run_id:'older'};
 assert.equal(checkSteps(data)[2].text,'Not started');assert.equal(planCheckState(data).title,'Checks incomplete');
 assert.doesNotMatch(render(FinalisePanel,{data}),/Save as final plan/i);
});

test('unclassified processing problems request operator help and never force irrelevant inventory edits',()=>{
 const data=fixture();blocked(data,'LOGISTICS_INCOMPLETE');data.logistics_issues=[{code:'UNCLASSIFIED',target:'PROFILE'}];
 assert.equal(planCheckState(data).title,'Checks incomplete');assert.match(planCheckState(data).detail,/do not repeatedly change unrelated information/i);
 assert.doesNotMatch(render(PlanView,{data,error:'Read failed',refresh(){}}),/check-step-passed|check-step-list/i);
});

test('eligible plans do not display an empty warning block or the removed three-agent cards',()=>{
 const html=render(PlanView,{data:fixture(),error:'',refresh(){}});
 assert.match(html,/To be confirmed/i);assert.doesNotMatch(html,/Resolve before confirming this plan|check-step-list|Itinerary Agent|Costs and equipment Agent|Safety Agent/i);
 assert.match(html,/Save as final plan/i);
 assert.doesNotMatch(html,/plan-state-detail|Current checks passed. Confirm and save, or modify the plan and reassess./i);
});
