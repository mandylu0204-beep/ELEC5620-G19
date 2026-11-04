import test from 'node:test';
import assert from 'node:assert/strict';
import {mergeProgress,progressPath,shouldPollPlan} from '../src/plan_progress.ts';
const detail=()=>({plan:{plan_id:'plan',active_run_id:'run'},run:{run_id:'run',status:'RUNNING',stage:'GENERATING',revision:3,is_active:true},version:{content:'saved'},finalisation_available:true,revision_available:true,reassessment_available:true,retry_available:true});
const progress=(updates={})=>({plan_id:'plan',active_run_id:'run',run:{run_id:'run',status:'RUNNING',stage:'ROUTING',revision:7,is_active:true,...updates}});

test('active polling uses progress and cannot grant an action or replace saved artifacts',()=>{
 const saved=detail();assert.equal(progressPath(saved),'/runs/run/progress');
 const next=mergeProgress(saved,progress());assert.equal(next.run.stage,'ROUTING');assert.equal(next.version,saved.version);
 for(const field of ['finalisation_available','revision_available','reassessment_available','retry_available'])assert.equal(next[field],false);
 assert.equal(saved.run.stage,'GENERATING');
});
test('terminal, superseded and mismatched progress require a full independently checked read',()=>{
 for(const status of ['SUCCEEDED','FAILED','CANCELLED'])assert.equal(mergeProgress(detail(),progress({status})),null);
 assert.equal(mergeProgress(detail(),{...progress(),active_run_id:'new-run'}),null);
 assert.equal(mergeProgress(detail(),progress({is_active:false})),null);
 assert.equal(mergeProgress(detail(),progress({run_id:'other'})),null);
 assert.equal(mergeProgress(detail(),{...progress(),plan_id:'other'}),null);
 assert.equal(progressPath({...detail(),run:{...detail().run,status:'SUCCEEDED'}}),null);
});
test('older progress cannot roll back the displayed revision',()=>{
 const saved=detail();assert.equal(mergeProgress(saved,progress({revision:2})),saved);
});

test('candidate polling updates only proposal progress while original selected artifacts remain intact',()=>{
 const value={...detail(),run:{...detail().run,status:'SUCCEEDED'},revision_comparison:{proposal_id:'proposal',decision:null,
   after:{run:{run_id:'candidate',status:'PENDING',stage:'RECOMMENDING',revision:0}}}};
 assert.equal(progressPath(value),'/runs/candidate/progress');
 const update={...progress({run_id:'candidate',is_active:false}),revision_proposal_id:'proposal'};
 const merged=mergeProgress(value,update);
 assert.equal(merged.run,value.run);assert.equal(merged.version,value.version);assert.equal(merged.plan,value.plan);
 assert.equal(merged.revision_comparison.after.run.stage,'ROUTING');
 assert.equal(merged.finalisation_available,false);
 assert.equal(mergeProgress(value,{...update,revision_proposal_id:'different-proposal'}),null);
 assert.equal(mergeProgress(value,{...update,active_run_id:'another-selected-run'}),null);
 assert.equal(mergeProgress(value,progress()),null);
 assert.equal(mergeProgress(value,{...update,run:{...update.run,status:'SUCCEEDED'}}),null);
});


test('waiting for current review polls saved detail until the exact result arrives, independently of other blockers',()=>{
 const context={plan_id:'plan',plan_version_id:'v',run_id:'run',input_fingerprint:'fp'};
 const waiting={...detail(),run:{...detail().run,status:'SUCCEEDED'},version:{status:'ESCALATED',version_context:context},reviews:[],eligibility:{blocking_reasons:[{code:'REVIEW_REQUIRED'},{code:'OTHER'}]}};
 assert.equal(shouldPollPlan(waiting),true);assert.equal(progressPath(waiting),null);
 const review={decision:'REQUEST_REVISION',version_context:context};
 assert.equal(shouldPollPlan({...waiting,reviews:[{...review,version_context:{...context,run_id:'old'}}]}),true);
 assert.equal(shouldPollPlan({...waiting,reviews:[review]}),false);
 for(const patch of [{run:{...waiting.run,is_active:false}},{trip_series:{is_current:false}},{current_inputs_error:'changed'},{version:{...waiting.version,status:'FINALISED'}},{version:{...waiting.version,status:'REVISION_REQUIRED'}}])assert.equal(shouldPollPlan({...waiting,...patch}),false);
});

test('candidate progress keeps polling even when the displayed selected run is historical',()=>{
 const data={...detail(),run:{...detail().run,status:'SUCCEEDED',is_active:false},revision_comparison:{decision:null,after:{run:{status:'RUNNING',run_id:'candidate'}}}};
 assert.equal(shouldPollPlan(data),true);assert.equal(progressPath(data),'/runs/candidate/progress');
 assert.equal(shouldPollPlan({...data,trip_series:{is_current:false}}),false);
});
