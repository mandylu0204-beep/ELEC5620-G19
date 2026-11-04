import {readFileSync} from 'node:fs';
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

test('other recommended campsite reasons use English in user, review and final snapshot pages without changing saved facts',()=>{
 const data=fixture();data.recommendations.result.candidates=[{campsite_id:'little-beach',rank:1,reasons:[
 '\u76ee\u7684\u5730\u533a\u57df\uff1aSydney & Surrounds\uff0c\u4e0e\u672c\u6b21\u9009\u62e9\u4e00\u81f4\u3002',
 '\u540c\u884c\u4eba\u6570\uff1a\u672c\u6b21 2 \u4eba\uff0c\u767b\u8bb0\u4eba\u6570\u4e0a\u9650 6 \u4eba\u3002',
 '\u4ea4\u901a\uff1a\u53ef\u9a7e\u8f66\u62b5\u8fbe\u505c\u8f66\u5904\uff0c\u4e4b\u540e\u9700\u642c\u8fd0\u88c5\u5907\u6b65\u884c\u8fdb\u5165\u8425\u4f4d\uff1b\u8f66\u8f86\u4e0d\u80fd\u76f4\u63a5\u8fdb\u5165\u8425\u4f4d\u3002',
 '\u5fc5\u987b\u6761\u4ef6\uff1a\u5395\u6240\uff0c\u767b\u8bb0\u4fe1\u606f\u4e3a\u652f\u6301\u3002',
 '\u8425\u5730\u914d\u5957\uff1a\u5395\u6240\u5df2\u767b\u8bb0\u63d0\u4f9b\u3002',
 '\u8425\u5730\u914d\u5957\uff1a\u6dcb\u6d74\u672a\u63d0\u4f9b\uff0c\u9700\u53e6\u4f5c\u5b89\u6392\u3002',
 '\u8425\u5730\u914d\u5957\uff1a\u996e\u7528\u6c34\u672a\u63d0\u4f9b\uff0c\u9700\u53e6\u4f5c\u5b89\u6392\u3002',
 '\u4f4f\u5bbf\u8d39\u7528\uff1a\u6bcf\u665a AUD 35.00\uff0c2 \u665a\u5408\u8ba1 AUD 70.00\uff1b\u4ec5\u4e3a\u8425\u5730\u8d39\uff0c\u5b8c\u6574\u8d39\u7528\u4ecd\u9700\u68c0\u67e5\u3002',
 ],material_uncertainties:['A recommendation does not confirm availability. Verify safety information before departure.']}];
 const before=structuredClone(data);
 for(const mode of [{},{review:true},{snapshot:true}]){
  const html=render(PlanView,{data,error:'',refresh(){},...mode});
  const comparison=html.match(/<ol class="candidate-list">([\s\S]*?)<\/ol>/)?.[1];assert.ok(comparison);
  for(const text of ['Destination region: Sydney &amp; Surrounds','this trip has 2 people; recorded capacity is 6 people','drive to the parking area','Vehicles cannot enter the campsite directly','Required condition: Toilets; registered information: supported','Campsite facilities: Toilets; Listed as provided.','Campsite facilities: Showers; Not provided; make alternative arrangements.','Campsite facilities: Drinking water; Not provided; make alternative arrangements.','per night AUD 35.00, 2 nights total AUD 70.00','does not confirm availability'])assert.ok(comparison.includes(text),text);
  assert.doesNotMatch(comparison,/[\u3400-\u9fff]/u);
 }
 assert.deepEqual(data,before);
});

test('saved selection details, old activities and departure origin stay English across user, review and final views',()=>{
 const data=fixture(),a=JSON.parse(readFileSync(new URL('../../data/planning/camp_activities_v2.json',import.meta.url),'utf8')).activities.find(item=>item.activity_id==='cattai-travel-stories');
 const description=a.title+'\uff1a'+a.description+'\uff08\u6a21\u62df\u6d3b\u52a8\u5efa\u8bae\uff1b\u987b\u4ee5\u6b63\u5f0f\u5b89\u5168\u68c0\u67e5\u548c\u73b0\u573a\u6761\u4ef6\u4e3a\u51c6。\uff09';
 data.version.content.selected_campsite_ids=['cattai'];
 data.version.content.itinerary_entries=[{entry_kind:'ACTIVITY',campsite_id:'cattai',description,start_at:'2026-11-04T13:00:00+11:00',end_at:'2026-11-04T16:00:00+11:00'}];
 data.recommendations.result.candidates=[{campsite_id:'cattai',rank:1,reasons:['\u4ea4\u901a\uff1a\u8d44\u6599\u767b\u8bb0\u652f\u6301\u8f66\u8f86\u62b5\u8fbe。','\u8425\u5730\u914d\u5957\uff1a\u996e\u7528\u6c34\u672a\u63d0\u4f9b，\u9700\u53e6\u4f5c\u5b89\u6392。'],material_uncertainties:[]}];
 data.preparation_summary={system_preparation:true,transport_type:'CAR',origin_label:'\u6089\u5c3c\u5e02\u533a\uff08\u56fa\u5b9a\u6a21\u62df\u51fa\u53d1\u5730\uff09',access_and_capacity:true,estimated_total_vehicle_km:'200',vehicle_count:1,estimated_transport_cents:3800,meal_mode:'READY_TO_EAT',source_refs:[]};
 const before=structuredClone(data);
 for(const mode of [{},{review:true},{snapshot:true}]){
  const html=render(PlanView,{data,error:'',refresh(){},...mode});assert.doesNotMatch(html,/[\u3400-\u9fff]/u);
  for(const text of ['Saved suitability reasons','Transport: registered information supports vehicle access.','Drinking water; Not provided; make alternative arrangements.','Travel stories and quiet rest','No off-site route is scheduled.','Departure point: Sydney CBD.'])assert.ok(html.includes(text),text);
  assert.doesNotMatch(html,/Original suitability reasons|View the saved original itinerary description/);
 }
 assert.deepEqual(data,before);
});

function highRainFixture(){
 const data=fixture();data.version.status='ESCALATED';
 const safe=safety(data);Object.assign(safe,{outcome:'REVIEW',requires_human_review:true,risk_level:'HIGH',
  evidence:[{kind:'WEATHER',summary:'Heavy rain in synthetic forecast.',status:'AVAILABLE',source_date:'2026-11-04',valid_from:'2026-11-04',valid_to:'2026-11-10',road_state:null,source_refs:[]}],hazards:['Heavy rain forecast.']});
 data.confirmed_context.requirements={...data.confirmed_context.requirements,start_date:'2026-11-05',end_date:'2026-11-07'};
 data.eligibility={eligible:false,blocking_reasons:[{code:'REVIEW_REQUIRED',message:'Review required.'}],review_required:true,valid_review_id:null};data.finalisation_available=false;
 data.model_assessment_audits={SAFETY:{kind:'SAFETY',run_id:'r',plan_version_id:'v',assessment_id:'s',depends_on_assessment_id:'l',input_fingerprint:'fp',advice_format:'single-advice-v1',plan:{decision_summary_unverified:'High risk synthetic demo; heavy rain and restrictions require review before departure.',action_priority:['source'],findings:[{finding_key:'source',fact_refs:['/input/demo_context'],action_code:'REQUEST_HUMAN_REVIEW',action_unverified:'Synthetic demo only; escalate to authorised Founder before use.',interpretation_unverified:'Synthetic demo only; escalate to authorised Founder before use.'}]}}};
 return data;
}
function approvedRainFixture(){
 const data=highRainFixture();data.reviews=[{review_id:'approved-current',decision:'APPROVE',reason:'Reviewed current assessments.',reviewer_user_id:'founder',version_context:{...data.version.version_context}}];
 data.eligibility={eligible:true,blocking_reasons:[],review_required:true,valid_review_id:'approved-current'};data.finalisation_available=true;data.version.status='ELIGIBLE_FOR_FINALISATION';return data;
}
function overview(html){const content=html.match(/<dl class="safety-overview"[\s\S]*?<\/dl>/)?.[0];assert.ok(content);return content;}

test('safety overview uses saved facts and removes the AI prose card while retaining HIGH risk and review requirement',()=>{
 const data=highRainFixture(),before=structuredClone(data);
 for(const mode of [{},{review:true}]){
  const html=render(PlanView,{data,error:'',refresh(){},...mode}),content=overview(html);
  for(const text of ['Risk level','HIGH','Main concern','Heavy rain forecast','Required action','Founder review is required before final saving.','Before departure','Recheck weather, road access and campsite notices.'])assert.ok(content.includes(text),text);
  assert.doesNotMatch(html,/AI Safety preparation advice|class="safety-advisory"|Suggested actions|High risk demo|only; escalate|View group details and saved originals/);
  assert.doesNotMatch(render(FinalisePanel,{data}),/Save as final plan/i);
 }
 assert.deepEqual(data,before);
});

test('current approval updates the next step but retains the official risk and does not add model calls',()=>{
 const data=approvedRainFixture(),before=structuredClone(data);
 for(const mode of [{},{review:true}]){
  const html=render(PlanView,{data,error:'',refresh(){},...mode}),content=overview(html);
  assert.match(content,/Review approved. The camper can confirm and save the final plan./);
  assert.match(content,/>HIGH</);assert.match(content,/Heavy rain forecast/);
  assert.doesNotMatch(content,/Founder review is required|Wait for reviewer/);
 }
 assert.deepEqual(data,before);
});

test('old approvals and matching rejection or revision decisions have distinct truthful next steps',()=>{
 const old=highRainFixture();old.reviews=[{review_id:'old',decision:'APPROVE',reason:'Old',reviewer_user_id:'founder',version_context:{...old.version.version_context,run_id:'old-run'}}];
 assert.match(overview(render(PlanView,{data:old,error:'',refresh(){}})),/Founder review is required/);
 for(const [decision,message] of [['REJECT','Review rejected. This plan cannot be saved as final.'],['REQUEST_REVISION','Changes requested. Revise the plan and complete the required checks.']]){
  const data=highRainFixture();data.reviews=[{review_id:'decision-current',decision,reason:'Current result needs attention.',reviewer_user_id:'founder',version_context:{...data.version.version_context}}];
  const content=overview(render(PlanView,{data,error:'',refresh(){}}));assert.ok(content.includes(message));assert.doesNotMatch(content,/can confirm and save/);
 }
});

test('blockers, missing evidence and stale inputs prevent an approval message from implying saving permission',()=>{
 for(const problem of ['blocker','evidence','outdated','other-check']){
  const data=approvedRainFixture();data.finalisation_available=false;data.eligibility.eligible=false;
  if(problem==='blocker')safety(data).mandatory_blockers=[{code:'ROAD_CLOSED',message:'Road closed.'}];
  if(problem==='evidence')safety(data).data_quality.WEATHER='MISSING';
  if(problem==='outdated')data.current_inputs_error='Inputs need updating.';
  const content=overview(render(PlanView,{data,error:'',refresh(){}}));assert.doesNotMatch(content,/can confirm and save/);assert.match(content,/>HIGH</);
  assert.match(content,problem==='outdated'?/Checks need updating/:problem==='other-check'?/Other checks must be resolved/:/Resolve the outstanding safety issues/);
 }
});

test('historical and final snapshots retain saved risks without inviting a new final save',()=>{
 const data=approvedRainFixture();data.version.status='FINALISED';data.finalisation_available=false;
 const before=structuredClone(data),html=render(PlanView,{data,error:'',refresh(){},snapshot:true}),content=overview(html);
 assert.match(content,/Review approval is recorded for this saved version/);assert.match(content,/>HIGH</);assert.doesNotMatch(content,/can confirm and save/);
 assert.doesNotMatch(html,/AI Safety preparation advice|class="safety-advisory"|High risk demo/);assert.deepEqual(data,before);
 const historical=highRainFixture();historical.run.is_active=false;
 assert.match(overview(render(PlanView,{data:historical,error:'',refresh(){}})),/Historical check result/);
});


test('current reviewer revision or rejection is prominent to the camper without granting saving',()=>{
 for(const decision of ['REQUEST_REVISION','REJECT']){
  const data=highRainFixture();data.version.status=decision==='REJECT'?'REJECTED':'REVISION_REQUIRED';
  data.eligibility.blocking_reasons.push({code:decision==='REJECT'?'VERSION_STATE':'REVISION_REQUIRED',message:'review prevents saving'});
  data.reviews=[{review_id:'review',decision,reason:'no',reviewer_user_id:'founder',version_context:{...data.version.version_context}}];
  const before=structuredClone(data),html=render(PlanView,{data,error:'',refresh(){}});
  assert.equal(planCheckState(data).title,decision==='REJECT'?'Review rejected':'Revision requested');
  assert.match(html,/aria-label="Reviewer feedback"/);assert.match(html,/Reviewer feedback[\s\S]*?no/);
  assert.doesNotMatch(html,/Awaiting human review|This plan needs human risk review/);
  assert.doesNotMatch(render(FinalisePanel,{data}),/Save as final plan/i);assert.deepEqual(data,before);
 }
});
test('a review for a different run or fingerprint does not replace the current waiting state or feedback',()=>{
 for(const field of ['plan_id','plan_version_id','run_id','input_fingerprint']){
  const data=highRainFixture();data.reviews=[{review_id:'old',decision:'REJECT',reason:'outdated reviewer reason',version_context:{...data.version.version_context,[field]:'old'}}];
  assert.equal(planCheckState(data).title,'Awaiting human review');
  const html=render(PlanView,{data,error:'',refresh(){}});assert.doesNotMatch(html,/aria-label="Reviewer feedback"/);
 }
});
