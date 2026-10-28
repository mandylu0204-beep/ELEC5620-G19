import {useEffect,useRef,useState} from 'react';
import {Link,useParams} from 'react-router-dom';
import {privateApi,useSession} from './session';
import {type RequirementCatalogue} from './requirement_choices';

type Item={field:string;index:number;text:string};
type Mapping={field:string;index:number;original:string;canonical:string};
export type HelpTask={task_id:string;request_id:string;request_revision:number;profile_revision:number;status:string;revision:number;current?:boolean;created_at:string;
  snapshot:{raw_text:string;items:Item[]};response:null|{decision:string;reason:string;mappings:Mapping[]}};
export type RequirementHelpState={needed:boolean;items:Item[];profile_revision:number;task:HelpTask|null};
const titles:Record<string,string>={preferences:'偏好',mandatory_constraints:'必须条件',accessibility_requirements:'同行特殊需求'};
const statuses:Record<string,string>={PENDING:'等待人工协助',PROPOSED:'请核对映射建议',RETURNED:'需要补充说明',APPLIED:'建议已采用'};
export function helpCommand(storage:Storage,key:string,body:unknown,create=()=>crypto.randomUUID()){
  const signature=JSON.stringify(body);const saved=storage.getItem(key);
  if(saved){const old=JSON.parse(saved);if(old.signature===signature&&typeof old.key==='string')return old.key;}
  const command=create();storage.setItem(key,JSON.stringify({signature,key:command}));return command;
}
const message=(reason:unknown)=>reason instanceof Error?reason.message:'操作未完成，请重试或重新读取。';

export function RequirementHelpPanel({requestId,requestRevision,state,dirty,disabled,catalogue,refresh}:{
  requestId:string;requestRevision:number;state:RequirementHelpState|null;dirty:boolean;disabled:boolean;catalogue?:RequirementCatalogue;refresh:()=>void;
}){
  const {session}=useSession();const [busy,setBusy]=useState(false);const [error,setError]=useState('');
  if(!state?.needed)return null;
  const task=state.task;
  async function act(operation:'create'|'adopt'){
    if(!session||!state||busy||disabled||dirty)return;
    setBusy(true);setError('');
    try{
      const body=operation==='create'?{expected_revision:requestRevision,expected_profile_revision:state.profile_revision}
        :{expected_revision:requestRevision,expected_profile_revision:state.profile_revision,expected_task_revision:task!.revision};
      const key=helpCommand(window.sessionStorage,`requirement-help:${session.user.user_id}:${requestId}:${operation}:${task?.task_id??requestRevision}`,body);
      await privateApi(operation==='create'?'/requests/'+requestId+'/requirement-help':'/requirement-help/'+task!.task_id+'/adopt',
        {method:'POST',headers:{'Content-Type':'application/json','X-CampMate-Client':'1','X-CSRF-Token':session.csrf_token},body:JSON.stringify({...body,command_key:key})});
      refresh();
    }catch(reason){setError(message(reason));}finally{setBusy(false);}
  }
  return <section className="requirement-help-panel" aria-label="规划前需求协助"><h3>{task?statuses[task.status]:'其他要求需要先明确'}</h3>
    <p>以下内容尚未对应已有条件，本次不会自动忽略，也不会因为人工处理就认定营地满足或安全通过。</p>
    <ul>{state.items.map(item=><li key={item.field+item.index}>{titles[item.field]}：{item.text}</li>)}</ul>
    {dirty?<p role="status">请先仅保存修改，再提交当前版本的需求协助。</p>:!task?<button type="button" className="secondary-button" disabled={busy||disabled} onClick={()=>act('create')}>提交人工协助（不调用模型）</button>:<>
      {task.status==='PENDING'&&<p role="status">审核员将提出已有条件的映射建议，或说明需要补充的内容。你仍可修改要求；修改后原任务将失效。</p>}
      {task.response&&<><p>{task.response.reason}</p>{task.response.mappings.length>0&&<ul>{task.response.mappings.map(item=><li key={item.field+item.index}>{item.original} → {catalogue?.fields[item.field]?.find(choice=>choice.value===item.canonical)?.label??item.canonical}</li>)}</ul>}</>}
      {task.status==='PROPOSED'&&<><p>确认采用会替换以上要求，涉及同行需求时也会保存新的个人资料 revision。之后仍需重新生成并确认摘要，不会自动开始规划。</p><button type="button" className="secondary-button" disabled={busy||disabled} onClick={()=>act('adopt')}>确认采用建议，暂不规划</button></>}
    </>}
    <button type="button" className="text-button" disabled={busy||disabled} onClick={refresh}>刷新协助状态</button>
    {error&&<p className="error-box" role="alert">{error}</p>}
  </section>;
}

export function RequirementHelpQueue(){
  const [tasks,setTasks]=useState<HelpTask[]|null>(null);const [error,setError]=useState('');const [revision,setRevision]=useState(0);
  useEffect(()=>{const controller=new AbortController();privateApi<{tasks:HelpTask[]}>('/requirement-help',{signal:controller.signal})
    .then(value=>{if(!controller.signal.aborted){setTasks(value.tasks);setError('');}}).catch(reason=>{if(!controller.signal.aborted)setError(message(reason));});return()=>controller.abort();},[revision]);
  return <div><div className="page-heading"><h1>规划前需求协助</h1><p>协助明确其他要求；这里不能批准营地条件、安全或最终保存。</p></div><button className="secondary-button" onClick={()=>setRevision(value=>value+1)}>刷新待办</button>
    {error&&<p className="error-box" role="alert">{error}</p>}{tasks===null?<p>正在读取…</p>:tasks.length===0?<section className="panel">暂无待协助的需求。</section>:tasks.map(task=><section className="panel" key={task.task_id}><h2>待明确的要求</h2><ul>{task.snapshot.items.map(item=><li key={item.field+item.index}>{titles[item.field]}：{item.text}</li>)}</ul><Link className="text-link" to={'/requirement-help/'+task.task_id}>查看并提出建议 ↗</Link></section>)}</div>;
}

export function RequirementHelpReview(){
  const {taskId}=useParams();const {session}=useSession();
  const [task,setTask]=useState<HelpTask|null>(null);const [catalogue,setCatalogue]=useState<RequirementCatalogue|null>(null);
  const [decision,setDecision]=useState('RETURN_FOR_DETAILS');const [reason,setReason]=useState('');const [mappings,setMappings]=useState<Record<string,string>>({});
  const [busy,setBusy]=useState(false);const [error,setError]=useState('');const [revision,setRevision]=useState(0);const locked=useRef(false);const activeTask=useRef(taskId);activeTask.current=taskId;
  useEffect(()=>{const controller=new AbortController();setTask(null);setError('');setMappings({});setReason('');setDecision('RETURN_FOR_DETAILS');
    Promise.all([privateApi<HelpTask>('/requirement-help/'+taskId,{signal:controller.signal}),privateApi<RequirementCatalogue>('/requirement-choices',{signal:controller.signal})])
      .then(([value,choices])=>{if(!controller.signal.aborted){setTask(value);setCatalogue(choices);}}).catch(fault=>{if(!controller.signal.aborted)setError(message(fault));});return()=>controller.abort();},[taskId,revision]);
  async function submit(){
    if(!task||!session||locked.current)return;const scope=taskId;locked.current=true;setBusy(true);setError('');
    try{
      const payload={expected_revision:task.revision,decision,reason,mappings:decision==='PROPOSE_MAPPING'?task.snapshot.items.map(item=>({field:item.field,index:item.index,original:item.text,canonical:mappings[item.field+':'+item.index]??''})):[]};
      const key=helpCommand(window.sessionStorage,`requirement-help:${session.user.user_id}:decide:${task.task_id}`,payload);
      const result=await privateApi<HelpTask>('/requirement-help/'+task.task_id+'/decision',{method:'POST',headers:{'Content-Type':'application/json','X-CampMate-Client':'1','X-CSRF-Token':session.csrf_token},body:JSON.stringify({...payload,command_key:key})});
      if(activeTask.current===scope)setTask({...result,current:true});
    }catch(fault){if(activeTask.current===scope)setError(message(fault));}finally{locked.current=false;setBusy(false);}
  }
  return <section className="panel"><h1>明确要求含义</h1><p>提出映射建议后，必须由露营者确认采用并重新生成摘要。无法验证的条件应退回补充，不能直接批准。</p>
    {error&&<p className="error-box" role="alert">{error}</p>}{!task?<p>正在读取…</p>:<>{task.snapshot.raw_text&&<details className="source-details"><summary>旧版请求原文</summary><blockquote>{task.snapshot.raw_text}</blockquote></details>}<ul>{task.snapshot.items.map(item=><li key={item.field+item.index}>{titles[item.field]}：{item.text}</li>)}</ul>
      {task.status==='PENDING'&&task.current?<fieldset disabled={busy}><label htmlFor="help-decision">处理方式</label><select id="help-decision" value={decision} onChange={event=>setDecision(event.target.value)}><option value="RETURN_FOR_DETAILS">退回补充说明</option><option value="PROPOSE_MAPPING">建议对应已有条件</option></select>
        {decision==='PROPOSE_MAPPING'&&task.snapshot.items.map(item=><div key={item.field+item.index}><label htmlFor={'help-map-'+item.field+item.index}>{item.text}</label><select id={'help-map-'+item.field+item.index} value={mappings[item.field+':'+item.index]??''} onChange={event=>setMappings(value=>({...value,[item.field+':'+item.index]:event.target.value}))}><option value="">请选择已有条件</option>{catalogue?.fields[item.field]?.map(choice=><option value={choice.value} key={choice.value}>{choice.label}</option>)}</select></div>)}
        <label htmlFor="help-reason">判断理由 <span className="required-mark">必填</span></label><textarea id="help-reason" maxLength={4000} value={reason} onChange={event=>setReason(event.target.value)}/>
        <button className="primary-button" disabled={busy||!reason.trim()||decision==='PROPOSE_MAPPING'&&task.snapshot.items.some(item=>!mappings[item.field+':'+item.index])} onClick={submit}>{busy?'正在保存…':'保存协助建议'}</button></fieldset>
        :<p role="status">{task.current?statuses[task.status]:'原需求或资料已变化，此记录仅供回看。'}{task.response?.reason}</p>}
    </>}
    <button className="text-button" onClick={()=>setRevision(value=>value+1)}>重新读取</button><Link className="text-link" to="/requirement-help">返回需求协助列表 ↗</Link>
  </section>;
}
