import type { SuccessorSource } from './replan_session';

export const tripUpdatePath=(planId:string,focus?:string)=>'/plans/'+encodeURIComponent(planId)+'/update'+
  (focus?'?focus='+encodeURIComponent(focus):'');
type SourcePlan={plan:{plan_id:string;current_version_id:string|null};
  trip_series?:{is_current:boolean;series_revision:number}|null;
  current_version_revision?:number|null;
  run:{run_id:string;revision:number;status:string;is_active:boolean}|null};
export function tripUpdateSource(data:SourcePlan):SuccessorSource {
  if(!data.run?.is_active||['PENDING','RUNNING'].includes(data.run.status)||data.trip_series?.is_current===false)
    throw new Error('来源方案正在检查或已被取代。请返回本次出行，核对当前方案后再更新。');
  return {plan_id:data.plan.plan_id,expected_series_revision:data.trip_series?.series_revision??0,
    expected_current_version_id:data.plan.current_version_id,expected_version_revision:data.current_version_revision??null,
    expected_active_run_id:data.run.run_id,expected_run_revision:data.run.revision};
}
type Storage=Pick<globalThis.Storage,'getItem'|'setItem'>;
type Api=<T>(path:string,body?:unknown)=>Promise<T>;
function updateSlot(userId:string,source:SuccessorSource){
  const {expected_series_revision:_,...identity}=source;
  return 'campmate.trip-update.'+userId+'.'+JSON.stringify(identity);
}
export async function forgetDeletedTripUpdate(api:Api,storage:Pick<globalThis.Storage,'removeItem'>,userId:string,planId:string){
  const source=tripUpdateSource(await api<SourcePlan>('/plans/'+encodeURIComponent(planId)));
  storage.removeItem(updateSlot(userId,source));
}

export function tripCommandKey(storage:Storage,userId:string,requestId:string,operation:string,revision:number,newKey:()=>string){
  const slot='campmate.trip-command.'+JSON.stringify([userId,requestId,operation,revision]);
  const saved=storage.getItem(slot);
  if(saved)return saved;
  const key=newKey();storage.setItem(slot,key);return key;
}

// Store only the command and its non-secret concurrency context. Persist BEFORE
// POST so refresh, duplicate mounting and a lost receipt reuse the same draft.
// Excluding series revision from the lookup allows legacy 0 -> 1 registration;
// the original exact body remains pinned and the server checks ownership/state.
export async function openTripUpdate(api:Api,storage:Storage,userId:string,planId:string,newKey:()=>string){
  const source=tripUpdateSource(await api<SourcePlan>('/plans/'+encodeURIComponent(planId)));
  const {expected_series_revision:_,...identity}=source;
  const slot=updateSlot(userId,source);
  let command:{source:SuccessorSource;key:string};
  const saved=storage.getItem(slot);
  if(saved){
    command=JSON.parse(saved);
    if(!command?.source||typeof command.key!=='string'||command.key.length<16||command.key.length>128||
      JSON.stringify({...command.source,expected_series_revision:undefined})!==JSON.stringify(identity))
      throw new Error('本次更新命令无法核对，请返回来源方案；不要另建独立出行替代重试。');
  }else{
    command={source,key:newKey()};storage.setItem(slot,JSON.stringify(command));
  }
  const {plan_id,...expected}=command.source;
  try{
    return await api<{request_id:string}>('/plans/'+encodeURIComponent(plan_id)+'/successor-requests',
      {...expected,command_key:command.key});
  }catch(reason){
    if((reason as {envelope?:{error?:{code?:string}}})?.envelope?.error?.code==='NOT_FOUND')
      Object.assign(reason as object,{deletedUpdateDraft:true});
    throw reason;
  }
}
