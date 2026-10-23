import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {forgetDeletedTripUpdate,openTripUpdate,tripCommandKey,tripUpdatePath,tripUpdateSource} from '../src/trip_update.ts';
import {ReplanSession} from '../src/replan_session.ts';

const plan=()=>({plan:{plan_id:'owned-plan',current_version_id:'v1'},trip_series:{is_current:true,series_revision:1},
  current_version_revision:2,run:{run_id:'r1',revision:7,status:'SUCCEEDED',is_active:true}});
const memory=()=>{const values=new Map();return {getItem:key=>values.get(key)??null,setItem:(key,value)=>values.set(key,value),removeItem:key=>values.delete(key)};};
test('deleted draft is never silently resurrected; only explicit fresh-draft action replaces its command',async()=>{
  const storage=memory(),writes=[];let deleted=false,number=0;
  const api=async(path,body)=>{if(!body)return plan();writes.push(body);if(deleted)throw Object.assign(new Error('deleted'),{envelope:{error:{code:'NOT_FOUND'}}});return {request_id:'draft'};};
  const key=()=>`draft-command-abcdefghijkl-${++number}`;
  await openTripUpdate(api,storage,'u','owned-plan',key);deleted=true;
  await assert.rejects(()=>openTripUpdate(api,storage,'u','owned-plan',key),error=>error.deletedUpdateDraft===true);
  assert.equal(number,1);assert.deepEqual(writes[0],writes[1]);
  await forgetDeletedTripUpdate(api,storage,'u','owned-plan');deleted=false;
  await openTripUpdate(api,storage,'u','owned-plan',key);
  assert.equal(number,2);assert.notEqual(writes[0].command_key,writes[2].command_key);
});
test('every update entry prepares only one linked draft; refresh and lost receipt reuse exact body',async()=>{
  const storage=memory(),calls=[];let fail=true,sequence=0;
  const api=async(path,body)=>{calls.push({path,body});if(!body)return plan();if(fail){fail=false;throw new Error('lost receipt');}return {request_id:'same-draft'};};
  const key=()=>`update-command-${++sequence}-abcdefghijkl`;
  await assert.rejects(()=>openTripUpdate(api,storage,'u','owned-plan',key),/lost receipt/);
  assert.deepEqual(await openTripUpdate(api,storage,'u','owned-plan',key),{request_id:'same-draft'});
  await openTripUpdate(api,storage,'u','owned-plan',key);
  const writes=calls.filter(call=>call.body);
  assert.equal(sequence,1);assert.deepEqual(writes[0],writes[1]);assert.deepEqual(writes[1],writes[2]);
  assert.ok(writes.every(call=>call.path==='/plans/owned-plan/successor-requests'));
  assert.ok(!calls.some(call=>/^\/requests$|\/(interpret|confirm|plan)$/.test(call.path)));
});
test('legacy first linkage 0 to 1 does not create another preview after refresh',async()=>{
  const storage=memory(),writes=[];let linked=false;
  const api=async(path,body)=>{if(!body){const data=plan();if(!linked)data.trip_series=null;return data;}writes.push(body);linked=true;return {request_id:'legacy-draft'};};
  await openTripUpdate(api,storage,'u','owned-plan',()=> 'legacy-command-abcdefghijkl');
  await openTripUpdate(api,storage,'u','owned-plan',()=>{throw new Error('must reuse');});
  assert.equal(writes[0].expected_series_revision,0);assert.deepEqual(writes[0],writes[1]);
});
test('concurrent mounts share a command, while another owner never shares it',async()=>{
  const storage=memory(),writes=[];let sequence=0;
  const api=async(path,body)=>{if(!body)return plan();writes.push(body);return {request_id:'draft'};};
  await Promise.all([openTripUpdate(api,storage,'u','owned-plan',()=>`command-abcdefghijkl-${++sequence}`),openTripUpdate(api,storage,'u','owned-plan',()=>`command-abcdefghijkl-${++sequence}`)]);
  assert.equal(sequence,1);assert.deepEqual(writes[0],writes[1]);
  await openTripUpdate(api,storage,'other','owned-plan',()=>`command-abcdefghijkl-${++sequence}`);
  assert.equal(sequence,2);
});
test('active, historical, deleted or inaccessible source cannot create a successor',async()=>{
  for(const patch of [data=>data.run.status='RUNNING',data=>data.run.is_active=false,data=>data.trip_series.is_current=false]){
    const data=plan();patch(data);assert.throws(()=>tripUpdateSource(data),/来源/);
  }
  const calls=[];
  await assert.rejects(()=>openTripUpdate(async(path,body)=>{calls.push({path,body});throw new Error('not found');},memory(),'u','deleted',()=> 'unused-command-abcdefghijkl'),/not found/);
  assert.equal(calls.length,1);assert.equal(calls[0].body,undefined);
});
test('storage failure blocks transmission rather than losing the retry command',async()=>{
  let writes=0;
  await assert.rejects(()=>openTripUpdate(async(path,body)=>{if(body)writes++;return plan();},{getItem(){return null;},setItem(){throw new Error('storage unavailable');}},'u','owned-plan',()=> 'command-abcdefghijkl'),/storage unavailable/);
  assert.equal(writes,0);
});
test('confirmation and planning keys survive controller recreation and are distinct operations',async()=>{
  const storage=memory(),calls=[];let row={request_id:'draft',status:'AWAITING_CONFIRMATION',revision:3,profile_revision:1,planning_available:true};let lose=true;
  const api=async(path,body)=>{calls.push({path,body});if(path==='/profile')return {revision:1};if(path.endsWith('/confirm')){row={...row,status:'CONFIRMED',revision:4};return row;}if(path.endsWith('/plan')){if(lose){lose=false;throw new Error('lost plan receipt');}return {plan_id:'successor',run_id:'new-run'};}throw new Error('unexpected');};
  let number=0;const create=()=>new ReplanSession(api,()=>`unused-${++number}`,(operation,revision)=>tripCommandKey(storage,'u','draft',operation,revision,()=>`durable-command-abcdefghijkl-${++number}`));
  let flow=create();flow.record=row;await assert.rejects(()=>flow.start(true),/lost plan/);
  flow=create();flow.record=row;await flow.start(true);
  const attempts=calls.filter(call=>call.path.endsWith('/plan'));assert.deepEqual(attempts[0],attempts[1]);
  assert.notEqual(calls.find(call=>call.path.endsWith('/confirm')).body.command_key,attempts[0].body.command_key);
});
test('correction links use series update paths; copy_from remains explicit independent-template only',()=>{
  assert.equal(tripUpdatePath('owned-plan','request-meal'),'/plans/owned-plan/update?focus=request-meal');
  for(const file of ['planning.tsx','next_steps.tsx','near_matches.tsx','trip_coverage.tsx','profile.tsx']){
    const source=readFileSync(new URL('../src/'+file,import.meta.url),'utf8');assert.doesNotMatch(source,/copy_from/);
  }
  const request=readFileSync(new URL('../src/requests.tsx',import.meta.url),'utf8');
  assert.match(request,/以此为模板，新建独立出行/);assert.match(request,/确认采用并重新检查/);
});
