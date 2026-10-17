import test from 'node:test';
import assert from 'node:assert/strict';
import {failureGuidance} from '../src/failure_guidance.ts';
const context={plan_id:'p',plan_version_id:'v',run_id:'r',input_fingerprint:'f'};
const assessment=kind=>({kind,version_context:{...context}});
const fixture=(patch={})=>({run:{run_id:'r',status:'FAILED',stage:'ASSESSING_SAFETY',operation:'PLAN',is_active:true},
  version:{version_context:context},recommendations:{},assessments:[assessment('LOGISTICS')],retry_available:true,...patch});

test('safety interruption identifies saved results and resumes safety without describing a new plan',()=>{
  const value=failureGuidance(fixture());
  assert.equal(value.title,'安全检查暂未完成');assert.equal(value.retryLabel,'继续安全检查');
  assert.ok(value.canRetry);assert.ok(value.saved.includes('本次装备与费用检查结果'));
  assert.ok(!value.saved.includes('本次安全检查结果'));assert.match(value.completionNote,/尚未完成/);
  assert.match(value.retryDescription,/尚未保存的步骤可能重新执行/);
});

test('saved safety plus routing failure is completion recovery, not a repeated safety recommendation',()=>{
  const data=fixture({assessments:[assessment('LOGISTICS'),assessment('SAFETY')]});data.run.stage='ROUTING';
  const value=failureGuidance(data);
  assert.equal(value.retryLabel,'继续未完成的步骤');assert.ok(value.saved.includes('本次安全检查结果'));
  assert.match(value.completionNote,/尚未确认完成/);
});

test('historical or unrelated assessment contexts never become saved current-check claims',()=>{
  for(const field of Object.keys(context)){
    const row=assessment('LOGISTICS');row.version_context[field]='other';
    assert.ok(!failureGuidance(fixture({assessments:[row]})).saved.includes('本次装备与费用检查结果'));
  }
  const data=fixture();data.run.is_active=false;
  assert.equal(failureGuidance(data).canRetry,false);
  assert.equal(failureGuidance(fixture({retry_available:false})).canRetry,false);
  assert.equal(failureGuidance(fixture({retry_available:undefined})).canRetry,false);
});

test('reassessment retains the original itinerary and early failures do not invent saved artifacts',()=>{
  const data=fixture();data.run.operation='REASSESS';
  assert.match(failureGuidance(data).retryDescription,/保留原行程/);
  const early=fixture({version:null,recommendations:null,assessments:[]});early.run.stage='GENERATING';
  assert.deepEqual(failureGuidance(early).saved,[]);
  assert.equal(failureGuidance({...early,run:{...early.run,status:'SUCCEEDED'}}),null);
});

test('no-match completion failure does not imply that downstream safety checks should have run',()=>{
  const data=fixture({version:null,assessments:[],recommendations:{result:{search_outcome:'NO_MATCH'}}});
  data.run.stage='COMPLETED';
  assert.equal(failureGuidance(data).title,'搜索结果尚未确认完成');
  assert.match(failureGuidance(data).completionNote,/未找到满足条件/);
  data.run.is_active=false;
  assert.match(failureGuidance(data).completionNote,/历史执行/);
});
