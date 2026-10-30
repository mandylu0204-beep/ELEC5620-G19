import {useEffect,useRef,useState} from 'react';
import {Link,useParams} from 'react-router-dom';
import {privateApi,useSession} from './session';
import {type RequirementCatalogue} from './requirement_choices';

type Item={field:string;index:number;text:string};
type Mapping={field:string;index:number;original:string;canonical:string};
export type HelpTask={task_id:string;request_id:string;request_revision:number;profile_revision:number;status:string;revision:number;current?:boolean;created_at:string;
  snapshot:{raw_text:string;items:Item[]};response:null|{decision:string;reason:string;problem?:string|null;next_action?:string|null;mappings:Mapping[]}};
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
  const returned=task?.status==='RETURNED';
  const unsupported=task?.response?.decision==='UNSUPPORTED';
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
  return <section className={'requirement-help-panel'+(returned?' requirement-help-returned':'')} aria-label="规划前需求协助"><h3>{unsupported?'当前系统暂不支持此要求':returned?'审核员已退回，请查看反馈':task?statuses[task.status]:'其他要求需要先明确'}</h3>
    {task?.response&&<div className={'requirement-help-feedback'+(returned?' requirement-help-feedback-returned':'')} role="status" aria-live="polite" aria-atomic="true" aria-label="审核员反馈">
      <p className="requirement-help-feedback-label">{dirty?'此前审核员反馈':'审核员反馈'}</p>
      <h4>{unsupported?'暂不支持：请调整要求或保留草稿':returned?'已退回：需要修改或补充要求':task.status==='PROPOSED'?'已提出条件对应建议，等待你确认':'已保存的协助意见'}</h4>
      <blockquote>{task.response.reason}</blockquote>
      {task.response.problem&&<p><strong>具体问题：</strong>{task.response.problem}</p>}
      {task.response.next_action&&<p><strong>你的下一步：</strong>{task.response.next_action}</p>}
      {task.response.mappings.length>0&&<ul>{task.response.mappings.map(item=><li key={item.field+item.index}>{item.original} → {catalogue?.fields[item.field]?.find(choice=>choice.value===item.canonical)?.label??item.canonical}</li>)}</ul>}
      {dirty?<p>你已修改表单。以上反馈针对上次保存的内容，尚未针对本次修改重新处理。</p>
        :unsupported?<p>这项要求尚不能由现有数据和规则核实。可以调整为已有条件或保留草稿；重新描述同一要求不会增加系统能力，也不会自动忽略原要求。</p>
        :returned?<p>请先查看审核员的具体意见，再修改或补充相关要求、保存并重新提交协助。若意见指出系统暂不支持，仅改写文字不能补齐支持能力。</p>
        :task.status==='PROPOSED'&&<p>这是条件对应建议，尚未采用。请核对后再确认，不代表方案已经通过。</p>}
    </div>}
    <p>以下内容尚未对应已有条件，本次不会自动忽略，也不会因为人工处理就认定营地满足或安全通过。</p>
    <ul>{state.items.map(item=><li key={item.field+item.index}>{titles[item.field]}：{item.text}</li>)}</ul>
    {dirty?<p role="status">请先仅保存修改，再提交当前版本的需求协助。</p>:!task?<button type="button" className="secondary-button" disabled={busy||disabled} onClick={()=>act('create')}>提交人工协助（不调用模型）</button>:<>
      {task.status==='PENDING'&&<p role="status">审核员将提出已有条件的映射建议，或说明需要补充的内容。你仍可修改要求；修改后原任务将失效。</p>}
      {task.status==='PROPOSED'&&<><p>确认采用会替换以上要求，涉及同行需求时也会保存新的个人资料 revision。之后仍需重新生成并确认摘要，不会自动开始规划。</p><button type="button" className="secondary-button" disabled={busy||disabled} onClick={()=>act('adopt')}>确认采用建议，暂不规划</button></>}
    </>}
    <button type="button" className="text-button" disabled={busy||disabled} onClick={refresh}>刷新协助状态</button>
    {error&&<p className="error-box" role="alert">{error}</p>}
  </section>;
}

export function RequirementHelpQueue(){
  const [tasks,setTasks]=useState<HelpTask[]|null>(null);const [error,setError]=useState('');const [revision,setRevision]=useState(0);const [filter,setFilter]=useState('pending');
  useEffect(()=>{const controller=new AbortController();privateApi<{tasks:HelpTask[]}>('/requirement-help?history=true',{signal:controller.signal})
    .then(value=>{if(!controller.signal.aborted){setTasks(value.tasks);setError('');}}).catch(reason=>{if(!controller.signal.aborted)setError(message(reason));});return()=>controller.abort();},[revision]);
  const displayed=tasks?.filter(task=>filter==='pending'?task.current&&task.status==='PENDING':filter==='processed'?task.status!=='PENDING':!task.current);
  return <div><div className="page-heading"><h1>规划前需求协助</h1><p>协助明确其他要求；这里不能批准营地条件、安全或最终保存。</p></div><button className="secondary-button" onClick={()=>setRevision(value=>value+1)}>刷新待办</button>
    <div className="review-filters" role="group" aria-label="需求协助记录筛选">{[['pending','待处理'],['processed','已处理'],['history','历史／已失效']].map(([value,title])=><button type="button" key={value} className="secondary-button" aria-pressed={filter===value} onClick={()=>setFilter(value)}>{title}</button>)}</div>
    {error&&<p className="error-box" role="alert">{error}</p>}{tasks===null?<p>正在读取…</p>:!displayed?.length?<section className="panel">此分类暂无需求协助记录。</section>:displayed.map(task=><section className="panel" key={task.task_id}><h2>{!task.current?'历史要求':task.status==='PENDING'?'待明确的要求':'已处理的要求'}</h2><p>{task.response?.decision==='UNSUPPORTED'?'当前系统暂不支持':statuses[task.status]}</p><ul>{task.snapshot.items.map(item=><li key={item.field+item.index}>{titles[item.field]}：{item.text}</li>)}</ul><Link className="text-link" to={'/requirement-help/'+task.task_id}>查看并提出建议 ↗</Link></section>)}</div>;
}

export function RequirementHelpReview(){
  const {taskId}=useParams();const {session}=useSession();
  const [task,setTask]=useState<HelpTask|null>(null);const [catalogue,setCatalogue]=useState<RequirementCatalogue|null>(null);
  const [decision,setDecision]=useState('RETURN_FOR_DETAILS');const [reason,setReason]=useState('');
  const [problem,setProblem]=useState('');const [nextAction,setNextAction]=useState('');const [mappings,setMappings]=useState<Record<string,string>>({});
  const [busy,setBusy]=useState(false);const [error,setError]=useState('');const [revision,setRevision]=useState(0);const locked=useRef(false);const activeTask=useRef(taskId);activeTask.current=taskId;
  useEffect(()=>{const controller=new AbortController();setTask(null);setError('');setMappings({});setReason('');setProblem('');setNextAction('');setDecision('RETURN_FOR_DETAILS');
    Promise.all([privateApi<HelpTask>('/requirement-help/'+taskId,{signal:controller.signal}),privateApi<RequirementCatalogue>('/requirement-choices',{signal:controller.signal})])
      .then(([value,choices])=>{if(!controller.signal.aborted){setTask(value);setCatalogue(choices);}}).catch(fault=>{if(!controller.signal.aborted)setError(message(fault));});return()=>controller.abort();},[taskId,revision]);
  async function submit(){
    if(!task||!session||locked.current)return;const scope=taskId;locked.current=true;setBusy(true);setError('');
    try{
      const payload={expected_revision:task.revision,decision,reason,feedback_version:'structured-help-feedback-1',...(decision!=='PROPOSE_MAPPING'?{problem:problem.trim(),next_action:nextAction.trim()}:{}),mappings:decision==='PROPOSE_MAPPING'?task.snapshot.items.map(item=>({field:item.field,index:item.index,original:item.text,canonical:mappings[item.field+':'+item.index]??''})):[]};
      const key=helpCommand(window.sessionStorage,`requirement-help:${session.user.user_id}:decide:${task.task_id}`,payload);
      const result=await privateApi<HelpTask>('/requirement-help/'+task.task_id+'/decision',{method:'POST',headers:{'Content-Type':'application/json','X-CampMate-Client':'1','X-CSRF-Token':session.csrf_token},body:JSON.stringify({...payload,command_key:key})});
      if(activeTask.current===scope)setTask({...result,current:true});
    }catch(fault){if(activeTask.current===scope)setError(message(fault));}finally{locked.current=false;setBusy(false);}
  }
  return <section className="panel"><h1>明确要求含义</h1><p>提出映射建议后，必须由露营者确认采用并重新生成摘要。无法验证的条件应退回补充，不能直接批准。</p>
    {error&&<p className="error-box" role="alert">{error}</p>}{!task?<p>正在读取…</p>:<>{task.snapshot.raw_text&&<details className="source-details"><summary>旧版请求原文</summary><blockquote>{task.snapshot.raw_text}</blockquote></details>}<ul>{task.snapshot.items.map(item=><li key={item.field+item.index}>{titles[item.field]}：{item.text}</li>)}</ul>
      {task.status==='PENDING'&&task.current?<fieldset disabled={busy}><label htmlFor="help-decision">处理方式</label><select id="help-decision" value={decision} onChange={event=>setDecision(event.target.value)}><option value="RETURN_FOR_DETAILS">需要补充说明</option><option value="UNSUPPORTED">当前系统暂不支持</option><option value="PROPOSE_MAPPING">建议对应已有条件</option></select>
        {decision==='PROPOSE_MAPPING'&&task.snapshot.items.map(item=><div key={item.field+item.index}><label htmlFor={'help-map-'+item.field+item.index}>{item.text}</label><select id={'help-map-'+item.field+item.index} value={mappings[item.field+':'+item.index]??''} onChange={event=>setMappings(value=>({...value,[item.field+':'+item.index]:event.target.value}))}><option value="">请选择已有条件</option>{catalogue?.fields[item.field]?.map(choice=><option value={choice.value} key={choice.value}>{choice.label}</option>)}</select></div>)}
        {decision!=='PROPOSE_MAPPING'&&<><label htmlFor="help-problem">具体哪项要求有问题 <span className="required-mark">必填</span></label><textarea id="help-problem" maxLength={2000} value={problem} onChange={event=>setProblem(event.target.value)}/><label htmlFor="help-next-action">用户需要做什么 <span className="required-mark">必填</span></label><textarea id="help-next-action" maxLength={2000} value={nextAction} onChange={event=>setNextAction(event.target.value)}/></>}
        <label htmlFor="help-reason">判断理由 <span className="required-mark">必填</span></label><textarea id="help-reason" maxLength={4000} value={reason} onChange={event=>setReason(event.target.value)}/>
        <button className="primary-button" disabled={busy||!reason.trim()||decision!=='PROPOSE_MAPPING'&&(!problem.trim()||!nextAction.trim())||decision==='PROPOSE_MAPPING'&&task.snapshot.items.some(item=>!mappings[item.field+':'+item.index])} onClick={submit}>{busy?'正在保存…':'保存协助建议'}</button></fieldset>
        :<p role="status">{task.current?(task.response?.decision==='UNSUPPORTED'?'当前系统暂不支持':statuses[task.status]):'原需求或资料已变化，此记录仅供回看。'}{task.response?.reason}{task.response?.problem&&<span> · 问题：{task.response.problem}</span>}{task.response?.next_action&&<span> · 下一步：{task.response.next_action}</span>}</p>}
    </>}
    <button className="text-button" onClick={()=>setRevision(value=>value+1)}>重新读取</button><Link className="text-link" to="/requirement-help">返回需求协助列表 ↗</Link>
  </section>;
}
