import test from 'node:test';
import assert from 'node:assert/strict';
import {ReplanSession} from '../src/replan_session.ts';

const source={plan_id:'original-plan',expected_series_revision:1,expected_current_version_id:'v1',expected_version_revision:2,expected_active_run_id:'r1',expected_run_revision:7};

const requirements={destination:'region',start_date:'2026-11-06',end_date:'2026-11-08',duration_nights:2,duration_days:3,
  budget_cents:32000,currency:'AUD',preferences:['quiet'],mandatory_constraints:['showers']};
function fixture(){
  const calls=[];let row=null;let profile={group_size:2};let profileRevision=1;let lostConfirm=false,lostPlan=false,lostCreate=false,race=false;let number=0;
  const api=async(path,body)=>{
    calls.push({path,body:structuredClone(body)});
    if(path==='/requests/original')return {raw_text:'Original request',request_id:'original'};
    if(path==='/profile')return {revision:profileRevision};
    if(path.endsWith('/successor-requests')){if(!row)row={request_id:'new-'+(++number),raw_text:'Original request',revision:1,status:'DRAFT',summary:null,profile_snapshot:null,profile_revision:null,source_profile_revision:1,planning_available:true};if(lostCreate){lostCreate=false;throw new Error('Response lost');}return structuredClone(row);}
    if(!body)return structuredClone(row);
    if(path.endsWith('/interpret')){row={...row,revision:row.revision+2,status:'AWAITING_CONFIRMATION',summary:{extracted_requirements:structuredClone(requirements)},profile_snapshot:structuredClone(profile),profile_revision:profileRevision};return structuredClone(row);}
    if(path.endsWith('/confirm')){if(race){race=false;profileRevision++;throw Object.assign(new Error('Information has changed'),{envelope:{error:{code:'VERSION_CONFLICT'}}});}row={...row,revision:4,status:'CONFIRMED'};if(lostConfirm){lostConfirm=false;throw new Error('Response lost');}return structuredClone(row);}
    if(path.endsWith('/plan')){if(lostPlan){lostPlan=false;throw new Error('Response lost');}return {plan_id:'new-plan',run_id:'new-run'};}
    throw new Error('Unexpected call');
  };
  let key=0;const flow=new ReplanSession(api,()=>`command-${++key}`);
  return {calls,flow,setProfile(value){profile=value;profileRevision++;},loseConfirm(){lostConfirm=true;},losePlan(){lostPlan=true;},loseCreate(){lostCreate=true;},race(){race=true;}};
}
test('replanning preserves every original requirement and prepares latest profile without confirming or planning',async()=>{
  const f=fixture();const before=structuredClone(requirements);f.setProfile({group_size:4});
  const result=await f.flow.prepare(source);
  assert.equal(f.calls[0].path,'/plans/original-plan/successor-requests');
  assert.deepEqual(f.calls[0].body,{...Object.fromEntries(Object.entries(source).filter(([key])=>key!=='plan_id')),command_key:'command-1'});
  assert.equal(result.profile_snapshot.group_size,4);
  assert.deepEqual(requirements,before);
  assert.ok(!f.calls.some(call=>/\/(confirm|plan)$/i.test(call.path)));
  await assert.rejects(()=>f.flow.start(false),/Review/i);
  assert.deepEqual(await f.flow.start(true),{plan_id:'new-plan',run_id:'new-run'});
  assert.ok(f.calls.filter(call=>call.path==='/requests/original').every(call=>call.body===undefined));
});
test('lost confirmation or planning receipts reuse the exact command instead of creating duplicate requests',async()=>{
  for(const phase of ['confirm','plan']){
    const f=fixture();await f.flow.prepare(source);
    if(phase==='confirm')f.loseConfirm();else f.losePlan();
    await assert.rejects(()=>f.flow.start(true),/Response lost/i);
    await f.flow.start(true);
    const attempts=f.calls.filter(call=>call.path.endsWith('/'+phase));
    assert.equal(attempts.length,2);assert.deepEqual(attempts[0],attempts[1]);
    assert.equal(f.calls.filter(call=>call.path.endsWith('/successor-requests')).length,1);
  }
});
test('reopening preview rereads latest saved profile and does not reuse an unconfirmed snapshot',async()=>{
  const f=fixture();await f.flow.prepare(source);f.setProfile({group_size:3});
  const result=await f.flow.prepare(source);
  assert.equal(result.profile_snapshot.group_size,3);
  assert.equal(f.calls.filter(call=>call.path.endsWith('/successor-requests')).length,1);
});
test('clarifications prevent confirmation and model dispatch',async()=>{
  const f=fixture();await f.flow.prepare(source);f.flow.record.status='NEEDS_CLARIFICATION';
  await assert.rejects(()=>f.flow.start(true),/Review/i);
  assert.ok(!f.calls.some(call=>call.path.endsWith('/confirm')||call.path.endsWith('/plan')));
});
test('lost successor creation receipt retries exact context and key',async()=>{
  const f=fixture();f.loseCreate();await assert.rejects(()=>f.flow.prepare(source),/Response lost/i);
  const record=await f.flow.prepare(source);assert.equal(record.request_id,'new-1');
  assert.deepEqual(f.calls[0],f.calls[1]);
});
test('changed profile revision invalidates acknowledgement without silent interpretation or dispatch',async()=>{
  const f=fixture();await f.flow.prepare(source);f.setProfile({group_size:5});
  const count=f.calls.length;await assert.rejects(()=>f.flow.start(true),/Reload the differences/i);
  assert.equal(f.flow.previewStale,true);assert.equal(f.calls.length,count+1);assert.equal(f.calls.at(-1).path,'/profile');
  assert.equal(f.flow.record.profile_snapshot.group_size,2);await assert.rejects(()=>f.flow.start(true),/Review/i);
  await f.flow.prepare(source);assert.equal(f.flow.record.profile_snapshot.group_size,5);
  await assert.rejects(()=>f.flow.start(false),/Review/i);await f.flow.start(true);
});
test('server-side revision race requires explicit preview reload',async()=>{
  const f=fixture();await f.flow.prepare(source);f.race();
  await assert.rejects(()=>f.flow.start(true),/Information has changed/i);assert.equal(f.flow.previewStale,true);
  assert.ok(!f.calls.some(call=>call.path.endsWith('/plan')));
  await assert.rejects(()=>f.flow.start(true),/Review/i);await f.flow.prepare(source);await f.flow.start(true);
});
test('ambiguous confirmation receipt remains pinned even after latest profile changes',async()=>{
  const f=fixture();await f.flow.prepare(source);f.loseConfirm();
  await assert.rejects(()=>f.flow.start(true),/Response lost/i);f.setProfile({group_size:8});
  await f.flow.start(true);assert.equal(f.flow.record.profile_snapshot.group_size,2);
  assert.equal(f.calls.filter(call=>call.path==='/profile').length,1);
});
test('confirmed preview reopening preserves the planning key instead of creating another request',async()=>{
  const f=fixture();await f.flow.prepare(source);f.losePlan();
  await assert.rejects(()=>f.flow.start(true),/Response lost/i);await f.flow.prepare(source);await f.flow.start(true);
  const attempts=f.calls.filter(call=>call.path.endsWith('/plan'));assert.deepEqual(attempts[0],attempts[1]);
  assert.equal(f.calls.filter(call=>call.path.endsWith('/successor-requests')).length,1);
});
