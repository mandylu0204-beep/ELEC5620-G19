import test from 'node:test';
import assert from 'node:assert/strict';
import {setImmediate} from 'node:timers/promises';
import {startSavedPolling,subscribePageRefresh} from '../src/saved_polling.ts';
import {mergeProgress} from '../src/plan_progress.ts';
const settle=()=>setImmediate();
const deferred=()=>{let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b;});return {promise,resolve,reject};};
function scheduler(){let id=0;const jobs=new Map();return {jobs,schedule:cb=>{jobs.set(++id,cb);return id;},cancel:key=>jobs.delete(key),next:async()=>{const [key,cb]=jobs.entries().next().value;jobs.delete(key);cb();await settle();}};}
const value=(status='RUNNING')=>({plan:{plan_id:'p',active_run_id:'r'},run:{run_id:'r',is_active:true,status,stage:'GENERATING',revision:1},finalisation_available:false});
const poll=v=>v.run.is_active&&['PENDING','RUNNING'].includes(v.run.status);

test('terminal progress reloads complete detail before publishing a terminal plan',async()=>{
 const clock=scheduler(),seen=[],requests=[];const initial=value(),final={...value('SUCCEEDED'),assessment:'validated full result'};
 const stop=startSavedPolling({...clock,read:async()=>{requests.push('detail');return requests.length===1?initial:final;},
  progress:async old=>{requests.push('progress');return mergeProgress(old,{plan_id:'p',active_run_id:'r',run:{...old.run,status:'SUCCEEDED'}});},poll,onValue:v=>seen.push(v),onError:e=>assert.fail(e)});
 await settle();await clock.next();assert.deepEqual(requests,['detail','progress','detail']);assert.equal(seen.at(-1),final);assert.equal(clock.jobs.size,0);stop();
});
test('session failure stops polling, reaches the error handler once and never falls back to detail',async()=>{
 const clock=scheduler(),error=Object.assign(new Error('Session expired'),{envelope:{error:{code:'UNAUTHENTICATED'}}});let detail=0,reauth=0;
 const stop=startSavedPolling({...clock,read:async()=>{detail++;return value();},progress:async()=>{throw error;},poll,onValue:()=>{},onError:e=>{assert.equal(e,error);if(e.envelope.error.code==='UNAUTHENTICATED')reauth++;}});
 await settle();await clock.next();assert.equal(reauth,1);assert.equal(detail,1);assert.equal(clock.jobs.size,0);stop();
});
test('page change aborts the old request and even an ignored abort cannot overwrite the new page',async()=>{
 const old=deferred(),seen=[];let signal;
 const stopOld=startSavedPolling({read:async s=>{signal=s;return old.promise;},poll:()=>false,onValue:v=>seen.push(v),onError:e=>assert.fail(e)});
 stopOld();assert.equal(signal.aborted,true);
 const stopNew=startSavedPolling({read:async()=>({page:'new'}),poll:()=>false,onValue:v=>seen.push(v),onError:e=>assert.fail(e)});
 await settle();old.resolve({page:'old'});await settle();assert.deepEqual(seen,[{page:'new'}]);stopNew();
});
test('aborting in-flight progress prevents terminal detail fetch and cancels pending timer',async()=>{
 const clock=scheduler(),pending=deferred();let reads=0,signal;
 const stop=startSavedPolling({...clock,read:async()=>{reads++;return value();},progress:async(_,s)=>{signal=s;return pending.promise;},poll,onValue:()=>{},onError:e=>assert.fail(e)});
 await settle();await clock.next();stop();assert.equal(signal.aborted,true);pending.resolve(null);await settle();assert.equal(reads,1);assert.equal(clock.jobs.size,0);
});
test('a late error from an obsolete page cannot replace the current page error state',async()=>{
 const pending=deferred(),errors=[];const stop=startSavedPolling({read:()=>pending.promise,poll:()=>false,onValue:()=>{},onError:e=>errors.push(e)});
 stop();pending.reject(new Error('late response'));await settle();assert.deepEqual(errors,[]);
});
test('no next poll starts until the current request completes and stopping clears the timer',async()=>{
 const clock=scheduler(),pending=deferred();let reads=0;
 const stop=startSavedPolling({...clock,read:async()=>{reads++;return pending.promise;},poll,onValue:()=>{},onError:e=>assert.fail(e)});
 assert.equal(clock.jobs.size,0);pending.resolve(value());await settle();assert.equal(reads,1);assert.equal(clock.jobs.size,1);stop();assert.equal(clock.jobs.size,0);
});


test('a transient read failure retains the prior record and retries full detail without running a command',async()=>{
 const clock=scheduler(),seen=[],errors=[],initial=value('SUCCEEDED');let reads=0,progressReads=0;
 const final={...initial,review:{decision:'REQUEST_REVISION',reason:'no'}};
 const stop=startSavedPolling({...clock,read:async()=>{reads++;if(reads===2)throw new TypeError('Network unavailable');return reads===1?initial:final;},
  progress:async()=>{progressReads++;return null;},poll:v=>!v.review,retryOnError:e=>e instanceof TypeError,onValue:v=>seen.push(v),onError:e=>errors.push(e)});
 await settle();await clock.next();assert.equal(errors.length,1);assert.equal(seen.at(-1),initial);assert.equal(clock.jobs.size,1);
 await clock.next();assert.equal(seen.at(-1),final);assert.equal(reads,3);assert.equal(progressReads,1);assert.equal(clock.jobs.size,0);stop();
});
test('returning to a plan reloads full detail even after polling stopped and unsubscribes on departure',async()=>{
 const clock=scheduler(),seen=[];let wake,unsubscribed=0,reads=0;
 const stop=startSavedPolling({...clock,read:async()=>({read:++reads}),poll:()=>false,subscribeRefresh:cb=>{wake=cb;return ()=>unsubscribed++;},onValue:v=>seen.push(v),onError:e=>assert.fail(e)});
 await settle();assert.equal(reads,1);wake();await settle();assert.equal(reads,2);stop();wake();await settle();assert.equal(reads,2);assert.equal(unsubscribed,1);
});
test('a refresh during an in-flight read queues one full read and cannot overlap requests',async()=>{
 const clock=scheduler(),pending=deferred(),seen=[];let wake,reads=0;
 const stop=startSavedPolling({...clock,read:async()=>++reads===1?pending.promise:{read:reads},poll:()=>true,subscribeRefresh:cb=>{wake=cb;return ()=>{};},onValue:v=>seen.push(v),onError:e=>assert.fail(e)});
 wake();wake();assert.equal(reads,1);pending.resolve({read:1});await settle();await settle();assert.equal(reads,2);assert.equal(clock.jobs.size,1);assert.equal(seen.at(-1).read,2);stop();
});

test('page focus and visibility only request a read when visible, with listeners removed on cleanup',()=>{
 const oldWindow=globalThis.window,oldDocument=globalThis.document;
 const page=new EventTarget(),doc=new EventTarget();doc.visibilityState='hidden';globalThis.window=page;globalThis.document=doc;
 try{
  let reads=0;const stop=subscribePageRefresh(()=>reads++);
  page.dispatchEvent(new Event('focus'));assert.equal(reads,0);
  doc.visibilityState='visible';doc.dispatchEvent(new Event('visibilitychange'));page.dispatchEvent(new Event('focus'));assert.equal(reads,2);
  stop();page.dispatchEvent(new Event('focus'));doc.dispatchEvent(new Event('visibilitychange'));assert.equal(reads,2);
 }finally{if(oldWindow===undefined)delete globalThis.window;else globalThis.window=oldWindow;if(oldDocument===undefined)delete globalThis.document;else globalThis.document=oldDocument;}
});
