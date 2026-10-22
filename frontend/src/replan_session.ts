import type { PreviewResult, Requirements } from './api';
import type { Profile } from './profile';

export type ReplanRequest={request_id:string;raw_text:string;revision:number;status:string;
  summary:PreviewResult|null;profile_snapshot:Profile|null;planning_available:boolean;
  profile_revision:number|null;
  source_profile_revision?:number|null;
  confirmed_context?:{requirements:Requirements;profile_snapshot:Profile}|null};
type Api=<T>(path:string,body?:unknown)=>Promise<T>;
export type SuccessorSource={plan_id:string;expected_series_revision:number;
  expected_current_version_id:string|null;expected_version_revision:number|null;
  expected_active_run_id:string;expected_run_revision:number};

// A new request pins the latest saved profile without changing the old plan.
// Keep request/revision and command keys across failed-response retries.
export class ReplanSession {
  record:ReplanRequest|null=null;
  previewStale=false;
  sourceProfileRevision:number|null=null;
  private confirmCommand:{revision:number;key:string}|null=null;
  private planCommand:{revision:number;key:string}|null=null;
  private createCommand:{source:string;key:string}|null=null;
  private api:Api;
  private newKey:()=>string;
  constructor(api:Api,newKey:()=>string){this.api=api;this.newKey=newKey;}
  private isStale(reason:unknown){
    const code=(reason as {envelope?:{error?:{code?:string}}}|null)?.envelope?.error?.code;
    return !!code&&['VERSION_CONFLICT','STALE_CONTEXT'].includes(code);
  }
  async prepare(source:SuccessorSource) {
    this.previewStale=true;
    if(this.record)this.record=await this.api<ReplanRequest>('/requests/'+encodeURIComponent(this.record.request_id));
    if(this.record?.status==='CONFIRMED'){this.previewStale=false;return this.record;}
    if(!this.record){
      const identity=JSON.stringify(source);
      if(this.createCommand?.source!==identity)this.createCommand={source:identity,key:this.newKey()};
      const {plan_id,...expected}=source;
      this.record=await this.api<ReplanRequest>('/plans/'+encodeURIComponent(plan_id)+'/successor-requests',
        {...expected,command_key:this.createCommand.key});
      this.sourceProfileRevision=this.record.source_profile_revision??null;
    }
    this.confirmCommand=null;this.planCommand=null;
    this.record=await this.api<ReplanRequest>('/requests/'+encodeURIComponent(this.record.request_id)+'/interpret',
      {expected_revision:this.record.revision});
    this.previewStale=false;
    return this.record;
  }
  async start(acknowledged:boolean) {
    if(!acknowledged||this.previewStale||!this.record||!['AWAITING_CONFIRMATION','CONFIRMED'].includes(this.record.status))
      throw new Error('请先核对并确认本次需求和最新露营资料。');
    if(this.record.status!=='CONFIRMED'){
      // Before the first attempt, check the exact revision displayed by the
      // preview. The confirm transaction remains the authoritative race guard.
      // An ambiguous lost receipt must retry its original key before any new
      // profile check: it may already have frozen the displayed snapshot.
      if(!this.confirmCommand){
        const latest=await this.api<{revision:number}>('/profile');
        if(latest.revision!==this.record.profile_revision){
          this.previewStale=true;
          throw new Error('露营资料已变化。请重新载入资料差异，核对新的 revision 后再次确认；尚未启动规划。');
        }
      }
      if(this.confirmCommand?.revision!==this.record.revision)
        this.confirmCommand={revision:this.record.revision,key:this.newKey()};
      try{
        this.record=await this.api<ReplanRequest>('/requests/'+encodeURIComponent(this.record.request_id)+'/confirm',
          {expected_revision:this.record.revision,command_key:this.confirmCommand.key,acknowledged:true});
      }catch(reason){
        if(this.isStale(reason)){
          this.previewStale=true;this.confirmCommand=null;
        }
        throw reason;
      }
    }
    if(!this.record.planning_available)throw new Error('规划服务暂不可用，已保存确认的需求，请稍后重试。');
    if(this.planCommand?.revision!==this.record.revision)
      this.planCommand={revision:this.record.revision,key:this.newKey()};
    try{
      return await this.api<{plan_id:string;run_id:string}>('/requests/'+encodeURIComponent(this.record.request_id)+'/plan',
        {expected_request_revision:this.record.revision,command_key:this.planCommand.key});
    }catch(reason){
      if(this.isStale(reason))this.previewStale=true;
      throw reason;
    }
  }
}
