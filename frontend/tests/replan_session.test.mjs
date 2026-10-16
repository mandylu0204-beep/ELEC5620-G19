import test from 'node:test';
import assert from 'node:assert/strict';
import {ReplanSession} from '../src/replan_session.ts';

const requirements={destination:'region',start_date:'2026-11-06',end_date:'2026-11-08',duration_nights:2,duration_days:3,
  budget_cents:32000,currency:'AUD',preferences:['quiet'],mandatory_constraints:['showers']};
function fixture(){
  const calls=[];let row=null;let profile={group_size:2};let lostConfirm=false,lostPlan=false;let number=0;
  const api=async(path,body)=>{
    calls.push({path,body:structuredClone(body)});
    if(path==='/requests/original')return {raw_text:'Original request',request_id:'original'};
    if(path==='/requests'){row={request_id:'new-'+(++number),raw_text:body.raw_text,revision:1,status:'DRAFT',summary:null,profile_snapshot:null,planning_available:true};return structuredClone(row);}
    if(!body)return structuredClone(row);
    if(path.endsWith('/interpret')){row={...row,revision:row.revision+2,status:'AWAITING_CONFIRMATION',summary:{extracted_requirements:structuredClone(requirements)},profile_snapshot:structuredClone(profile)};return structuredClone(row);}
    if(path.endsWith('/confirm')){row={...row,revision:4,status:'CONFIRMED'};if(lostConfirm){lostConfirm=false;throw new Error('Response lost');}return structuredClone(row);}
    if(path.endsWith('/plan')){if(lostPlan){lostPlan=false;throw new Error('Response lost');}return {plan_id:'new-plan',run_id:'new-run'};}
    throw new Error('Unexpected call');
  };
  let key=0;const flow=new ReplanSession(api,()=>`command-${++key}`);
  return {calls,flow,setProfile(value){profile=value;},loseConfirm(){lostConfirm=true;},losePlan(){lostPlan=true;}};
}
test('replanning preserves every original requirement and prepares latest profile without confirming or planning',async()=>{
  const f=fixture();const before=structuredClone(requirements);f.setProfile({group_size:4});
  const result=await f.flow.prepare('original',requirements);
  assert.deepEqual(f.calls[1].body,{raw_text:'Original request',explicit_fields:before});
  assert.equal(result.profile_snapshot.group_size,4);
  assert.deepEqual(requirements,before);
  assert.ok(!f.calls.some(call=>/\/(confirm|plan)$/.test(call.path)));
  await assert.rejects(()=>f.flow.start(false),/核对/);
  assert.deepEqual(await f.flow.start(true),{plan_id:'new-plan',run_id:'new-run'});
  assert.ok(f.calls.filter(call=>call.path==='/requests/original').every(call=>call.body===undefined));
});
test('lost confirmation or planning receipts reuse the exact command instead of creating duplicate requests',async()=>{
  for(const phase of ['confirm','plan']){
    const f=fixture();await f.flow.prepare('original',requirements);
    if(phase==='confirm')f.loseConfirm();else f.losePlan();
    await assert.rejects(()=>f.flow.start(true),/Response lost/);
    await f.flow.start(true);
    const attempts=f.calls.filter(call=>call.path.endsWith('/'+phase));
    assert.equal(attempts.length,2);assert.deepEqual(attempts[0],attempts[1]);
    assert.equal(f.calls.filter(call=>call.path==='/requests').length,1);
  }
});
test('reopening preview rereads latest saved profile and does not reuse an unconfirmed snapshot',async()=>{
  const f=fixture();await f.flow.prepare('original',requirements);f.setProfile({group_size:3});
  const result=await f.flow.prepare('original',requirements);
  assert.equal(result.profile_snapshot.group_size,3);
  assert.equal(f.calls.filter(call=>call.path==='/requests').length,1);
});
test('clarifications prevent confirmation and model dispatch',async()=>{
  const f=fixture();await f.flow.prepare('original',requirements);f.flow.record.status='NEEDS_CLARIFICATION';
  await assert.rejects(()=>f.flow.start(true),/核对/);
  assert.ok(!f.calls.some(call=>call.path.endsWith('/confirm')||call.path.endsWith('/plan')));
});
