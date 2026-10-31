import test from 'node:test';
import assert from 'node:assert/strict';
import {failureGuidance} from '../src/failure_guidance.ts';
const context={plan_id:'p',plan_version_id:'v',run_id:'r',input_fingerprint:'f'};
const assessment=kind=>({kind,version_context:{...context}});
const fixture=(patch={})=>({run:{run_id:'r',status:'FAILED',stage:'ASSESSING_SAFETY',operation:'PLAN',is_active:true},
  version:{version_context:context},recommendations:{},assessments:[assessment('LOGISTICS')],retry_available:true,...patch});

test('safety interruption identifies saved results and resumes safety without describing a new plan',()=>{
  const value=failureGuidance(fixture());
  assert.equal(value.title,'Safety checks incomplete');assert.equal(value.retryLabel,'Continue safety checks');
  assert.ok(value.canRetry);assert.ok(value.saved.includes('Current equipment and cost check results'));
  assert.ok(!value.saved.includes('Current safety check results'));assert.match(value.completionNote,/incomplete/i);
  assert.match(value.retryDescription,/Unsaved steps may run again/i);
});

test('saved safety plus routing failure is completion recovery, not a repeated safety recommendation',()=>{
  const data=fixture({assessments:[assessment('LOGISTICS'),assessment('SAFETY')]});data.run.stage='ROUTING';
  const value=failureGuidance(data);
  assert.equal(value.retryLabel,'Continue unfinished steps');assert.ok(value.saved.includes('Current safety check results'));
  assert.match(value.completionNote,/not confirmed complete/i);
});

test('historical or unrelated assessment contexts never become saved current-check claims',()=>{
  for(const field of Object.keys(context)){
    const row=assessment('LOGISTICS');row.version_context[field]='other';
    assert.ok(!failureGuidance(fixture({assessments:[row]})).saved.includes('Current equipment and cost check results'));
  }
  const data=fixture();data.run.is_active=false;
  assert.equal(failureGuidance(data).canRetry,false);
  assert.equal(failureGuidance(fixture({retry_available:false})).canRetry,false);
  assert.equal(failureGuidance(fixture({retry_available:undefined})).canRetry,false);
});

test('reassessment retains the original itinerary and early failures do not invent saved artifacts',()=>{
  const data=fixture();data.run.operation='REASSESS';
  assert.match(failureGuidance(data).retryDescription,/keeps the original itinerary/i);
  const early=fixture({version:null,recommendations:null,assessments:[]});early.run.stage='GENERATING';
  assert.deepEqual(failureGuidance(early).saved,[]);
  assert.equal(failureGuidance({...early,run:{...early.run,status:'SUCCEEDED'}}),null);
});

test('no-match completion failure does not imply that downstream safety checks should have run',()=>{
  const data=fixture({version:null,assessments:[],recommendations:{result:{search_outcome:'NO_MATCH'}}});
  data.run.stage='COMPLETED';
  assert.equal(failureGuidance(data).title,'Search results are not yet confirmed complete');
  assert.match(failureGuidance(data).completionNote,/No campsite met the conditions/i);
  data.run.is_active=false;
  assert.match(failureGuidance(data).completionNote,/Historical run/i);
});

test('service failures do not send users back to refill requests or guess a provider cause',()=>{
  for(const code of ['AGENT_FAILURE','ADAPTER_FAILURE','CONTRACT_INVALID','PERSISTENCE_FAILURE']){
    const data=fixture();data.run.error={code,message:'Unexpected workflow failure; retry resumes persisted steps.'};
    const value=failureGuidance(data);
    assert.match(value.explanation,/do not need to re-enter/i);
    assert.doesNotMatch(value.explanation,/VPN|Quota|Timeout|502|Unexpected/i);
    assert.equal(value.retryLabel,'Continue safety checks');
    data.retry_available=false;
    assert.equal(failureGuidance(data).canRetry,false);
  }
});

test('input and confirmation failures ask for correction, while unknown errors remain neutral',()=>{
  for(const code of ['INPUT_INVALID','REQUEST_NOT_CONFIRMED']){
    const data=fixture();data.run.error={code};
    assert.match(failureGuidance(data).explanation,/Review and reconfirm/i);
    assert.doesNotMatch(failureGuidance(data).explanation,/Not needed/i);
  }
  const data=fixture();data.run.error={code:'FUTURE_ERROR'};
  assert.equal(failureGuidance(data).explanation,'This run is incomplete. Saved results will be retained.');
});
