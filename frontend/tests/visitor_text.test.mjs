import test,{after} from 'node:test';
import assert from 'node:assert/strict';
import {createElement as h} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {createServer} from 'vite';
import {visitorText,sourceDisplayName,diagnosticSummary} from '../src/visitor_text.ts';
const server=await createServer({configFile:false,envDir:false,server:{middlewareMode:true,hmr:false,ws:false,watch:null},optimizeDeps:{noDiscovery:true}});after(()=>server.close());
const {SafetyAdvisoryPanel}=await server.ssrLoadModule('/src/safety_advisory_panel.tsx');
const {TripPreparation}=await server.ssrLoadModule('/src/trip_preparation.tsx');
const {PlanningExplanationPanel}=await server.ssrLoadModule('/src/display_panels.tsx');
const {DailyItinerary}=await server.ssrLoadModule('/src/daily_itinerary.tsx');
const render=(component,props)=>renderToStaticMarkup(h(component,props));
const forbidden=/\b(?:synthetic|simulated|simulation|fictional|fake|demonstration)\b|demo data/i;

test('source qualifiers disappear while hazards, uncertainty and review actions stay visible',()=>{
 for(const original of ['Synthetic data only; escalate to authorised Founder before use.','Heavy rain in synthetic forecast.','Extreme heat in simulated conditions.','Synthetic comprehensive no-fire restriction.','Road closed in synthetic scenario.']){
  const text=visitorText(original);assert.doesNotMatch(text,forbidden);assert.ok(text.trim());
 }
 assert.match(visitorText('Synthetic data only; escalate to authorised Founder before use.'),/escalate to authorised Founder/);
 assert.match(visitorText('Heavy rain in synthetic forecast.'),/Heavy rain/);
 assert.match(visitorText('Road closed in synthetic scenario.'),/Road closed/);
 assert.equal(visitorText('Unknown cost; not confirmed.'),'Unknown cost; not confirmed.');
 assert.equal(sourceDisplayName('data/synthetic_campsites.csv'),'Campsite information');
});

test('saved model advice is projected without rewriting actions, priorities, refs or raw audit',()=>{
 const binding={runId:'r',versionId:'v',assessmentId:'s',logisticsId:'l',inputFingerprint:'fp'};
 const value={kind:'SAFETY',run_id:'r',plan_version_id:'v',assessment_id:'s',depends_on_assessment_id:'l',input_fingerprint:'fp',advice_format:'single-advice-v1',
 plan:{decision_summary_unverified:'Synthetic data: heavy rain requires human review.',action_priority:['status','rain'],findings:[
  {finding_key:'status',fact_refs:['/input/demo_context'],action_code:'REQUEST_HUMAN_REVIEW',interpretation_unverified:'Synthetic data only; escalate to authorised Founder before use.',action_unverified:'Synthetic data only; escalate to authorised Founder before use.'},
  {finding_key:'rain',fact_refs:['/baseline/evidence/0'],action_code:'REQUEST_HUMAN_REVIEW',interpretation_unverified:'Heavy rain hazard requires human review before departure.',action_unverified:'Heavy rain hazard requires human review before departure.'}]}};
 const before=structuredClone(value);const html=render(SafetyAdvisoryPanel,{value,binding});
 assert.doesNotMatch(html,forbidden);assert.match(html,/Heavy rain hazard requires human review/);assert.match(html,/authorised Founder/);assert.deepEqual(value,before);
 assert.equal(render(SafetyAdvisoryPanel,{value,binding:{...binding,runId:'wrong'}}),'');
});

test('preparation, saved filter reasons and itinerary cards expose no simulation notice while retaining estimates',()=>{
 const value={system_preparation:true,transport_type:'CAR',origin_label:'Central Sydney (fixed demonstration origin)',access_and_capacity:true,estimated_total_vehicle_km:'200',vehicle_count:1,estimated_transport_cents:3800,meal_mode:'READY_TO_EAT',source_refs:[]};
 const copy=structuredClone(value),html=render(TripPreparation,{value});assert.doesNotMatch(html,forbidden);assert.match(html,/estimates/);assert.match(html,/200 km/);assert.deepEqual(value,copy);
 const reasons=['Registered synthetic region, capacity and known hard constraints match.'];
 const panel=render(PlanningExplanationPanel,{siteName:'Bonnie Vale',reasons,uncertainties:['Recommendation is not booking availability or safety clearance.']});
 assert.doesNotMatch(panel,forbidden);assert.match(panel,/does not confirm availability/);
 const entry={entry_kind:'ACTIVITY',start_at:'2026-11-05T13:00:00+11:00',end_at:'2026-11-05T16:00:00+11:00',campsite_id:'bonnie-vale',description:'Rest: stay at your pitch. (Simulated activity suggestion; subject to formal safety checks and on-site conditions.)'};
 const itinerary=render(DailyItinerary,{entries:[entry],time:x=>x,label:x=>x});assert.doesNotMatch(itinerary,forbidden);assert.match(itinerary,/<h4>Rest/);assert.match(itinerary,/Subject to formal safety checks/);
});

test('readable diagnostic summaries retain accounting while original provenance and source identity stay on the server',()=>{
 const value={agent_version:'campus-logistics-agent-2',trace:{http_attempts:3,usage:{total_tokens:123},configuration_fingerprint:'unchanged-hash'},
  workflow_context:{selection_config:{a_daily_snapshot:'synthetic-daily-v1'}},file_digests:{'synthetic_campsites.csv':'source-digest'},
  provenance:{source_type:'SYNTHETIC',source_name:'CampMate Synthetic Demo Dataset v2',demo_only:true,source_date:'2026-11-04'}};
 const before=structuredClone(value),summary=diagnosticSummary(value);
 assert.doesNotMatch(JSON.stringify(summary),forbidden);assert.deepEqual(summary.trace,value.trace);assert.equal(summary.agent_version,value.agent_version);assert.deepEqual(value,before);
});
