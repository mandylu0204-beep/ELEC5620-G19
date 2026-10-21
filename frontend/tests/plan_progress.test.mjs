import test from 'node:test';
import assert from 'node:assert/strict';
import {mergeProgress,progressPath} from '../src/plan_progress.ts';
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
