import {useEffect,useRef,useState} from 'react';
import {Link,useParams} from 'react-router-dom';
import {privateApi,useSession} from './session';
import {type RequirementCatalogue} from './requirement_choices';

type Item={field:string;index:number;text:string};
type Mapping={field:string;index:number;original:string;canonical:string};
export type HelpTask={task_id:string;request_id:string;request_revision:number;profile_revision:number;status:string;revision:number;current?:boolean;created_at:string;
  snapshot:{raw_text:string;items:Item[]};response:null|{decision:string;reason:string;problem?:string|null;next_action?:string|null;mappings:Mapping[]}};
export type RequirementHelpState={needed:boolean;items:Item[];profile_revision:number;task:HelpTask|null};
const titles:Record<string,string>={preferences:'Preferences',mandatory_constraints:'Required conditions',accessibility_requirements:'Group accessibility and other needs'};
const statuses:Record<string,string>={PENDING:'Waiting for human assistance',PROPOSED:'Review the mapping suggestion',RETURNED:'Clarification needed',APPLIED:'Suggestion adopted'};
export function helpCommand(storage:Storage,key:string,body:unknown,create=()=>crypto.randomUUID()){
  const signature=JSON.stringify(body);const saved=storage.getItem(key);
  if(saved){const old=JSON.parse(saved);if(old.signature===signature&&typeof old.key==='string')return old.key;}
  const command=create();storage.setItem(key,JSON.stringify({signature,key:command}));return command;
}
const message=(reason:unknown)=>reason instanceof Error?reason.message:'Action incomplete. Retry or reload.';

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
  return <section className={'requirement-help-panel'+(returned?' requirement-help-returned':'')} aria-label="Pre-planning requirement assistance"><h3>{unsupported?'This requirement is currently unsupported':returned?'Returned by reviewer: read the feedback':task?statuses[task.status]:'Other requirements need clarification'}</h3>
    {task?.response&&<div className={'requirement-help-feedback'+(returned?' requirement-help-feedback-returned':'')} role="status" aria-live="polite" aria-atomic="true" aria-label="Reviewer feedback">
      <p className="requirement-help-feedback-label">{dirty?'Previous reviewer feedback':'Reviewer feedback'}</p>
      <h4>{unsupported?'Unsupported: adjust requirements or keep a draft':returned?'Returned: revise or clarify requirements':task.status==='PROPOSED'?'Condition mapping proposed; awaiting your confirmation':'Saved assistance feedback'}</h4>
      <blockquote>{task.response.reason}</blockquote>
      {task.response.problem&&<p><strong>Specific issue: </strong>{task.response.problem}</p>}
      {task.response.next_action&&<p><strong>Your next step: </strong>{task.response.next_action}</p>}
      {task.response.mappings.length>0&&<ul>{task.response.mappings.map(item=><li key={item.field+item.index}>{item.original} → {catalogue?.fields[item.field]?.find(choice=>choice.value===item.canonical)?.label??item.canonical}</li>)}</ul>}
      {dirty?<p>You changed the form. This feedback applies to the last saved content and has not been updated for these changes.</p>
        :unsupported?<p>Existing data and rules cannot verify this requirement. Choose an existing condition or keep a draft. Rewording the same requirement does not add system capability or remove the requirement.</p>
        :returned?<p>Read the reviewer feedback, edit or clarify the relevant requirements, save and submit assistance again. If unsupported, rewording alone cannot add support.</p>
        :task.status==='PROPOSED'&&<p>This condition mapping is proposed but not adopted. Review and confirm it. It does not mean the plan passed.</p>}
    </div>}
    <p>The following requirements do not yet map to existing conditions. They will not be ignored, and human assistance does not establish campsite compliance or safety.</p>
    <ul>{state.items.map(item=><li key={item.field+item.index}>{titles[item.field]}: {item.text}</li>)}</ul>
    {dirty?<p role="status">Save changes first, then submit assistance for the current revision.</p>:!task?<button type="button" className="secondary-button" disabled={busy||disabled} onClick={()=>act('create')}>Request human assistance (no model call)</button>:<>
      {task.status==='PENDING'&&<p role="status">A reviewer will propose an existing-condition mapping or explain what needs clarification. You may still edit requirements; edits invalidate the previous task.</p>}
      {task.status==='PROPOSED'&&<><p>Adoption replaces these requirements. Changes to group requirements also save a new personal profile revision  revision.. You must then regenerate and confirm the summary. Planning does not start automatically.</p><button type="button" className="secondary-button" disabled={busy||disabled} onClick={()=>act('adopt')}>Adopt suggestion without starting planning</button></>}
    </>}
    <button type="button" className="text-button" disabled={busy||disabled} onClick={refresh}>Refresh assistance status</button>
    {error&&<p className="error-box" role="alert">{error}</p>}
  </section>;
}

export function RequirementHelpQueue(){
  const [tasks,setTasks]=useState<HelpTask[]|null>(null);const [error,setError]=useState('');const [revision,setRevision]=useState(0);const [filter,setFilter]=useState('pending');
  useEffect(()=>{const controller=new AbortController();privateApi<{tasks:HelpTask[]}>('/requirement-help?history=true',{signal:controller.signal})
    .then(value=>{if(!controller.signal.aborted){setTasks(value.tasks);setError('');}}).catch(reason=>{if(!controller.signal.aborted)setError(message(reason));});return()=>controller.abort();},[revision]);
  const displayed=tasks?.filter(task=>filter==='pending'?task.current&&task.status==='PENDING':filter==='processed'?task.status!=='PENDING':!task.current);
  return <div><div className="page-heading"><h1>Pre-planning requirement assistance</h1><p>Clarify other requirements. This cannot approve campsite conditions, safety or final saving.</p></div><button className="secondary-button" onClick={()=>setRevision(value=>value+1)}>Refresh tasks</button>
    <div className="review-filters" role="group" aria-label="Filter request assistance records">{[['pending','Pending'],['processed','Processed'],['history','History / invalidated']].map(([value,title])=><button type="button" key={value} className="secondary-button" aria-pressed={filter===value} onClick={()=>setFilter(value)}>{title}</button>)}</div>
    {error&&<p className="error-box" role="alert">{error}</p>}{tasks===null?<p>Loading…</p>:!displayed?.length?<section className="panel">No assistance records in this category.</section>:displayed.map(task=><section className="panel" key={task.task_id}><h2>{!task.current?'Historical requirements':task.status==='PENDING'?'Requirements to clarify':'Processed requirements'}</h2><p>{task.response?.decision==='UNSUPPORTED'?'Currently unsupported':statuses[task.status]}</p><ul>{task.snapshot.items.map(item=><li key={item.field+item.index}>{titles[item.field]}: {item.text}</li>)}</ul><Link className="text-link" to={'/requirement-help/'+task.task_id}>View and propose a suggestion ↗</Link></section>)}</div>;
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
  return <section className="panel"><h1>Clarify requirements</h1><p>After a mapping is proposed, the camper must adopt it and regenerate the summary. Return unverifiable conditions for clarification; they cannot be directly approved.</p>
    {error&&<p className="error-box" role="alert">{error}</p>}{!task?<p>Loading…</p>:<>{task.snapshot.raw_text&&<details className="source-details"><summary>Legacy request text</summary><blockquote>{task.snapshot.raw_text}</blockquote></details>}<ul>{task.snapshot.items.map(item=><li key={item.field+item.index}>{titles[item.field]}: {item.text}</li>)}</ul>
      {task.status==='PENDING'&&task.current?<fieldset disabled={busy}><label htmlFor="help-decision">Action</label><select id="help-decision" value={decision} onChange={event=>setDecision(event.target.value)}><option value="RETURN_FOR_DETAILS">Clarification needed</option><option value="UNSUPPORTED">Currently unsupported</option><option value="PROPOSE_MAPPING">Suggest an existing condition</option></select>
        {decision==='PROPOSE_MAPPING'&&task.snapshot.items.map(item=><div key={item.field+item.index}><label htmlFor={'help-map-'+item.field+item.index}>{item.text}</label><select id={'help-map-'+item.field+item.index} value={mappings[item.field+':'+item.index]??''} onChange={event=>setMappings(value=>({...value,[item.field+':'+item.index]:event.target.value}))}><option value="">Select an existing condition</option>{catalogue?.fields[item.field]?.map(choice=><option value={choice.value} key={choice.value}>{choice.label}</option>)}</select></div>)}
        {decision!=='PROPOSE_MAPPING'&&<><label htmlFor="help-problem">Which requirement needs attention <span className="required-mark">Required</span></label><textarea id="help-problem" maxLength={2000} value={problem} onChange={event=>setProblem(event.target.value)}/><label htmlFor="help-next-action">What the user should do <span className="required-mark">Required</span></label><textarea id="help-next-action" maxLength={2000} value={nextAction} onChange={event=>setNextAction(event.target.value)}/></>}
        <label htmlFor="help-reason">Reason for decision <span className="required-mark">Required</span></label><textarea id="help-reason" maxLength={4000} value={reason} onChange={event=>setReason(event.target.value)}/>
        <button className="primary-button" disabled={busy||!reason.trim()||decision!=='PROPOSE_MAPPING'&&(!problem.trim()||!nextAction.trim())||decision==='PROPOSE_MAPPING'&&task.snapshot.items.some(item=>!mappings[item.field+':'+item.index])} onClick={submit}>{busy?'Saving…':'Save assistance suggestion'}</button></fieldset>
        :<p role="status">{task.current?(task.response?.decision==='UNSUPPORTED'?'Currently unsupported':statuses[task.status]):'The original request or profile changed. This record is historical only.'}{task.response?.reason}{task.response?.problem&&<span> · Issue:{task.response.problem}</span>}{task.response?.next_action&&<span> · Next step: {task.response.next_action}</span>}</p>}
    </>}
    <button className="text-button" onClick={()=>setRevision(value=>value+1)}>Reload</button><Link className="text-link" to="/requirement-help">Back to request assistance ↗</Link>
  </section>;
}
