// Self-contained offline browser regression. No app server, credentials or API.
import React,{useEffect,useState} from 'react';
import {createRoot} from 'react-dom/client';
import {MemoryRouter,Route,Routes,useLocation} from 'react-router-dom';
import {ProfilePage} from '../src/profile';
import {TripUpdateEntry} from '../src/replan';
import {RequestDetail} from '../src/requests';
import {Protected,SessionProvider} from '../src/session';
import {showRenderRecovery} from '../src/render_recovery';

const results:{name:string;passed:boolean;detail?:unknown}[]=[];
function check(value:unknown,message:string):asserts value {if(!value)throw new Error(message);}
const tick=()=>new Promise(resolve=>setTimeout(resolve,20));
async function waitFor(test:()=>boolean){for(let i=0;i<150;i++){if(test())return;await tick();}throw new Error('Offline UI condition timed out');}

function replaceTextNodes(root:HTMLElement,respectTranslationFlag=true){
  const walker=document.createTreeWalker(root,NodeFilter.SHOW_TEXT);
  const nodes:Text[]=[];
  while(walker.nextNode()){
    const node=walker.currentNode as Text;
    if(node.textContent?.trim()&&(!respectTranslationFlag||!node.parentElement?.closest('[translate="no"],.notranslate')))
      nodes.push(node);
  }
  for(const node of nodes){
    const replacement=document.createElement('font');replacement.textContent='Translated: '+node.textContent;
    node.parentNode!.replaceChild(replacement,node);
  }
  return nodes.length;
}

function ConditionalText(){
  const [visible,setVisible]=useState(true);
  return <section><button onClick={()=>setVisible(false)}>Continue</button>
    <div><span>Keep this element</span>{visible&&'Conditional translated text'}</div></section>;
}

async function mutationCase(name:string,protectedRoot:boolean,force:boolean,recover:boolean){
  const container=document.createElement('div');document.body.append(container);
  if(protectedRoot){container.setAttribute('translate','no');container.className='notranslate';}
  const errors:string[]=[];
  createRoot(container,{onUncaughtError(error){
    errors.push((error as Error).name);
    if(recover)showRenderRecovery(container,error);
  }}).render(<ConditionalText/>);
  await waitFor(()=>!!container.querySelector('button'));
  const mutations=replaceTextNodes(container,!force);
  container.querySelector('button')!.click();
  if(!protectedRoot||force)await waitFor(()=>errors.length>0);else await tick();
  if(!protectedRoot){
    check(mutations>0&&errors.includes('NotFoundError'),'Unprotected control must reproduce removeChild failure');
    check(container.childElementCount===0,'Unprotected control must reproduce the blank root');
  }else if(force){
    check(errors.includes('NotFoundError'),'Forced mutation must reach React root error handler');
    await waitFor(()=>!!container.querySelector('[role="alert"]'));
    check(container.textContent?.includes('Reload page'),'Failure must provide explicit recovery');
    check(container.textContent?.includes('Turn off automatic page translation'),'DOM failure must provide actionable guidance');
    check(!container.textContent?.includes('Failed to execute'),'Raw exception must not be displayed');
    check(container.querySelector('a')?.getAttribute('href')==='/plans','Recovery must use a local read-only navigation');
  }else{
    check(mutations===0&&errors.length===0,'Translation-aware mutation must leave protected app alone');
    check(!!container.querySelector('button'),'Protected UI must stay mounted');
  }
  results.push({name,passed:true,detail:{mutations,errors}});
}

async function profileUpdateCase(){
  const calls:{path:string;method:string;body:unknown}[]=[];
  const original={group_size:2,experience_level:'INTERMEDIATE',has_children:false,children_count:0,
    accessibility_requirements:[],transport:{transport_type:'CAR',vehicle_count:1,estimated_km:null,assumptions:[]},
    equipment:[{item_key:'tent',label:'Tent',quantity:1,unit:'item',capacity_persons:2,confirmed:true},
      {item_key:'vehicle',label:'Vehicle',quantity:1,unit:'vehicle',capacity_persons:2,confirmed:true}]};
  let profile=structuredClone(original),revision=1;
  const source={plan:{plan_id:'source-plan',request_id:'source-request',current_version_id:'v1'},
    trip_series:{is_current:true,series_revision:1},current_version_revision:1,
    run:{run_id:'source-run',revision:5,status:'SUCCEEDED',is_active:true},logistics_issues:[],cooking_preparation:null};
  const request={request_id:'update-request',raw_text:'',explicit_fields:{destination:'Sydney & Surrounds',
    start_date:'2026-11-05',duration_nights:2,end_date:'2026-11-07',duration_days:3,budget_cents:100000,
    preferences:['quiet','ready-to-eat meals'],mandatory_constraints:['toilets','showers','potable_water','vehicle_access']},
    status:'DRAFT',revision:1,summary:null,profile_snapshot:null,profile_revision:null,error:null,
    confirmed_context:null,planning_available:true,trip_series_id:'series-1',predecessor_plan_id:'source-plan',
    source_profile_snapshot:original,source_profile_revision:1};
  const originalFetch=window.fetch;
  window.fetch=(async(input,options={})=>{
    const path=String(input);const method=options.method??'GET';
    const body=typeof options.body==='string'?JSON.parse(options.body):null;
    calls.push({path,method,body});let value:unknown;
    if(path==='/api/v1/auth/me')value={user:{user_id:'offline-user',username:'offline',display_name:'Offline test',role:'CAMPER'},csrf_token:'offline-only'};
    else if(path==='/api/v1/profile'){
      if(method==='PUT'){profile=body.profile;revision++;}
      value={profile,revision};
    }else if(path==='/api/v1/request-context')value={supported_transport_modes:['CAR','PUBLIC_TRANSPORT'],
      supported_destinations:['Sydney & Surrounds'],execution_mode:'agent',demo_today:'2026-11-04',
      planning_available:true,system_preparation:true,
      requirement_choices:{version:'offline',fields:{preferences:[],mandatory_constraints:[],accessibility_requirements:[]}}};
    else if(path==='/api/v1/plans/source-plan')value=source;
    else if(path==='/api/v1/plans/source-plan/successor-requests'&&method==='POST')value={request_id:'update-request'};
    else if(path==='/api/v1/requests/update-request')value=request;
    else throw new Error('Unexpected/offline-forbidden request: '+method+' '+path);
    return new Response(JSON.stringify(value),{status:200,headers:{'Content-Type':'application/json'}});
  }) as typeof fetch;
  const container=document.createElement('div');container.setAttribute('translate','no');container.className='notranslate';document.body.append(container);
  const errors:string[]=[];
  function Probe(){const {pathname}=useLocation();useEffect(()=>{container.dataset.route=pathname;},[pathname]);return null;}
  const root=createRoot(container,{onUncaughtError(error){errors.push((error as Error).name);showRenderRecovery(container,error);}});
  let stage='load-profile';
  try{
    root.render(<React.StrictMode><MemoryRouter initialEntries={['/profile?plan_id=source-plan']}><SessionProvider><Probe/><Routes>
      <Route path="/profile" element={<Protected role="CAMPER"><ProfilePage datasetVersion="2.2.0"/></Protected>}/>
      <Route path="/plans/:planId/update" element={<Protected role="CAMPER"><TripUpdateEntry/></Protected>}/>
      <Route path="/request/:requestId" element={<Protected role="CAMPER"><RequestDetail/></Protected>}/>
    </Routes></SessionProvider></MemoryRouter></React.StrictMode>);
    await waitFor(()=>!!container.querySelector<HTMLInputElement>('#gear-quantity-0'));
    stage='edit-equipment';
    const input=container.querySelector<HTMLInputElement>('#gear-quantity-0')!;
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value')!.set!.call(input,'2');
    input.dispatchEvent(new Event('input',{bubbles:true}));input.dispatchEvent(new Event('change',{bubbles:true}));
    await waitFor(()=>container.querySelector<HTMLButtonElement>('[name="save-and-return"]')?.disabled===false);
    check(replaceTextNodes(container)===0,'Actual profile must retain the translation protection');
    stage='save-and-navigate';
    container.querySelector<HTMLButtonElement>('[name="save-and-return"]')!.click();
    await waitFor(()=>container.dataset.route==='/request/update-request'&&container.textContent?.includes('Review this update')===true);
    check(profile.equipment[0].quantity===2,'Save must retain the changed equipment quantity');
    check(calls.filter(c=>c.path==='/api/v1/profile'&&c.method==='PUT').length===1,'Exactly one profile save is allowed');
    const drafts=calls.filter(c=>c.path.endsWith('/successor-requests'));
    check(drafts.length>0,'The real route must prepare its linked draft');
    check(new Set(drafts.map(c=>JSON.stringify(c.body))).size===1,'StrictMode mounts must reuse the exact command');
    check(!calls.some(c=>/\/(interpret|confirm|plan)$/.test(c.path)),'Saving/navigation must never dispatch a model or confirm');
    check(errors.length===0,'Actual save/update/request route must not crash');
    results.push({name:'actual-profile-save-update-draft-route',passed:true,detail:{profile_saves:1,model_calls:0}});
  }catch(error){throw new Error(stage+': '+(error as Error).message+'; route='+container.dataset.route+
    '; mock requests='+calls.map(c=>c.method+' '+c.path).join(', ')+'; synthetic page='+container.textContent?.slice(0,900));
  }finally{root.unmount();window.fetch=originalFetch;}
}

async function main(){
  try{
    await mutationCase('unprotected-removeChild-control',false,false,false);
    await mutationCase('protected-translation-aware-update',true,false,false);
    await mutationCase('forced-mutation-recovers-without-blank-screen',true,true,true);
    await profileUpdateCase();
  }catch(error){results.push({name:'browser-regression',passed:false,detail:(error as Error).message});}
  const output=document.createElement('pre');output.id='dom-test-results';output.textContent=JSON.stringify(results);document.body.append(output);
}
void main();
