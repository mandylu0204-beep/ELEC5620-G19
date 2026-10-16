import type { PreviewResult, Requirements } from './api';
import type { Profile } from './profile';

export type ReplanRequest={request_id:string;raw_text:string;revision:number;status:string;
  summary:PreviewResult|null;profile_snapshot:Profile|null;planning_available:boolean;
  confirmed_context?:{requirements:Requirements;profile_snapshot:Profile}|null};
type Api=<T>(path:string,body?:unknown)=>Promise<T>;

// A new request pins the latest saved profile without changing the old plan.
// Keep request/revision and command keys across failed-response retries.
export class ReplanSession {
  record:ReplanRequest|null=null;
  private confirmCommand:{revision:number;key:string}|null=null;
  private planCommand:{revision:number;key:string}|null=null;
  private api:Api;
  private newKey:()=>string;
  constructor(api:Api,newKey:()=>string){this.api=api;this.newKey=newKey;}
  async prepare(sourceId:string,requirements:Requirements) {
    if(this.record)this.record=await this.api<ReplanRequest>('/requests/'+encodeURIComponent(this.record.request_id));
    if(!this.record||this.record.status==='CONFIRMED'){
      const source=await this.api<ReplanRequest>('/requests/'+encodeURIComponent(sourceId));
      this.record=await this.api<ReplanRequest>('/requests',{raw_text:source.raw_text,explicit_fields:requirements});
    }
    this.confirmCommand=null;this.planCommand=null;
    this.record=await this.api<ReplanRequest>('/requests/'+encodeURIComponent(this.record.request_id)+'/interpret',
      {expected_revision:this.record.revision});
    return this.record;
  }
  async start(acknowledged:boolean) {
    if(!acknowledged||!this.record||!['AWAITING_CONFIRMATION','CONFIRMED'].includes(this.record.status))
      throw new Error('请先核对并确认本次需求和最新露营资料。');
    if(this.record.status!=='CONFIRMED'){
      if(this.confirmCommand?.revision!==this.record.revision)
        this.confirmCommand={revision:this.record.revision,key:this.newKey()};
      this.record=await this.api<ReplanRequest>('/requests/'+encodeURIComponent(this.record.request_id)+'/confirm',
        {expected_revision:this.record.revision,command_key:this.confirmCommand.key,acknowledged:true});
    }
    if(!this.record.planning_available)throw new Error('规划服务暂不可用，已保存确认的需求，请稍后重试。');
    if(this.planCommand?.revision!==this.record.revision)
      this.planCommand={revision:this.record.revision,key:this.newKey()};
    return this.api<{plan_id:string;run_id:string}>('/requests/'+encodeURIComponent(this.record.request_id)+'/plan',
      {expected_request_revision:this.record.revision,command_key:this.planCommand.key});
  }
}
