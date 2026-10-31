import test,{after} from 'node:test';
import assert from 'node:assert/strict';
import {createElement as h} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {MemoryRouter} from 'react-router-dom';
import {createServer} from 'vite';
const server=await createServer({configFile:false,envDir:false,appType:'custom',server:{middlewareMode:true,hmr:false,ws:false,watch:null},optimizeDeps:{noDiscovery:true}});
after(()=>server.close());
const {RequirementChoices,choiceMatch,toggleRequirement,replaceOtherRequirements}=await server.ssrLoadModule('/src/requirement_choices.tsx');
const {RequirementHelpPanel,helpCommand}=await server.ssrLoadModule('/src/requirement_help.tsx');
const {SessionProvider}=await server.ssrLoadModule('/src/session.tsx');
const {RequestFields}=await server.ssrLoadModule('/src/requests.tsx');
const choices=[{value:'showers',label:'Showers',aliases:['showers','shower','Showers','Need showers']},{value:'toilets',label:'Toilets',aliases:['toilets','Toilets']}];
const render=(component,props)=>renderToStaticMarkup(h(component,props));
const routed=(component,props)=>renderToStaticMarkup(h(MemoryRouter,null,h(SessionProvider,null,h(component,props))));
const catalogue={version:'test',fields:{preferences:choices,mandatory_constraints:choices,accessibility_requirements:[]}};

test('choices use full host-provided expressions; modifiers, negation and compound requirements stay unknown',()=>{
  assert.equal(choiceMatch('Need showers.',choices),'showers');
  assert.equal(choiceMatch('SHOWER',choices),'showers');
  for(const value of ['No showers wanted','Need private hot showers','showers and toilets','not showers','must have showers'])assert.equal(choiceMatch(value,choices),null,value);
});
test('checkbox changes preserve unrelated other requirements and separate meal arrangements',()=>{
  const before='ready-to-eat meals\nNeed private showers\nNeed showers';
  assert.equal(toggleRequirement(before,choices,'showers',false),'ready-to-eat meals\nNeed private showers');
  assert.equal(toggleRequirement(before,choices,'showers',true),'ready-to-eat meals\nNeed private showers\nshowers');
});
test('typing a recognized other phrase then clearing removes it without sticky requirements',()=>{
  const initial=replaceOtherRequirements('toilets',[],'shower');
  assert.equal(initial.value,'toilets\nshower');
  assert.deepEqual(replaceOtherRequirements(initial.value,initial.owned,''),{value:'toilets',owned:[]});
  const duplicate=replaceOtherRequirements('showers',[],'showers');
  assert.deepEqual(replaceOtherRequirements(duplicate.value,duplicate.owned,''),{value:'showers',owned:[]});
});
test('structured controls show existing choices, preserve unknown original text and never promise a formal pass',()=>{
  const html=render(RequirementChoices,{id:'requirements',title:'Required conditions',value:'shower\nNeed private showers',choices,onChange(){}});
  assert.match(html,/type="checkbox" checked=""/i);assert.match(html,/Need private showers/i);
  assert.match(html,/Other requirements \(optional; one per line\)/i);assert.match(html,/Human assistance is needed/i);
  assert.match(html,/not confirmation that a campsite meets them/i);assert.match(html,/tabindex="-1"/i);
  const pending=render(RequirementChoices,{id:'pending',title:'Condition',value:'Original requirement',choices:null,onChange(){}});
  assert.match(pending,/Original requirement/i);assert.match(pending,/<textarea[^>]*disabled/i);
});
test('request fields use structured choices and meal selector without a prose input',()=>{
  const draft={raw:'Want to go camping',destination:'Sydney',start:'',nights:'',days:'',end:'',budget:'',preferences:'ready-to-eat meals',constraints:''};
  const html=render(RequestFields,{draft,set(){},regions:['Sydney'],disabled:false,catalogue});
  assert.doesNotMatch(html,/id="request-idea"|Your camping ideas/i);assert.match(html,/id="request-meal"/i);
  assert.match(html,/View legacy request text/i);assert.match(html,/blockquote>Want to go camping/i);
  assert.match(html,/id="request-preferences-other"/i);assert.match(html,/id="request-constraints-other"/i);
  assert.doesNotMatch(html,/<textarea id="request-preferences"|<textarea id="request-constraints"/i);
  assert.doesNotMatch(html,/>ready-to-eat meals<\/textarea>/i);
});
const state={needed:true,profile_revision:4,items:[{field:'mandatory_constraints',index:0,text:'Need private showers'}],task:null};
test('unknown requirements offer a real assistance action, not an approval or a fake planning shortcut',()=>{
  const html=routed(RequirementHelpPanel,{requestId:'q',requestRevision:2,state,dirty:false,disabled:false,refresh(){},catalogue});
  assert.match(html,/Request human assistance \(no model call\)/i);assert.match(html,/will not be ignored/i);
  assert.doesNotMatch(html,/Force approval|Approve plan|Met/i);
  const dirty=routed(RequirementHelpPanel,{requestId:'q',requestRevision:2,state,dirty:true,disabled:false,refresh(){}});
  assert.match(dirty,/Save changes first/i);assert.doesNotMatch(dirty,/>Submit for human assistance/i);
});
test('proposed mappings require owner adoption and explain profile change, reanalysis and no automatic inference',()=>{
  const task={task_id:'t',revision:2,status:'PROPOSED',response:{reason:'Confirm whether standard showers are sufficient',mappings:[{field:'mandatory_constraints',index:0,original:'Need private showers',canonical:'showers'}]}};
  const html=routed(RequirementHelpPanel,{requestId:'q',requestRevision:2,state:{...state,task},dirty:false,disabled:false,catalogue,refresh(){}});
  for(const text of ['Need private showers','Showers','Adopt suggestion without starting planning','personal profile revision','regenerate and confirm the summary','Planning does not start automatically'])assert.ok(html.includes(text),text);
});
test('durable assistance command keys survive controller recreation and stop on storage failure',()=>{
  const values=new Map();const storage={getItem:key=>values.get(key)??null,setItem:(key,value)=>values.set(key,value)};
  let count=0;const create=()=>`command-${++count}`;
  assert.equal(helpCommand(storage,'create',{revision:1},create),'command-1');
  assert.equal(helpCommand(storage,'create',{revision:1},create),'command-1');
  assert.equal(helpCommand(storage,'create',{revision:2},create),'command-2');
  assert.throws(()=>helpCommand({getItem(){return null;},setItem(){throw new Error('storage');}},'create',{},create),/storage/i);
});

test('blank-source forms do not show a legacy source or invent a description',()=>{
  const value={raw:'',destination:'Sydney',start:'',nights:'',days:'',end:'',budget:'',preferences:'',constraints:''};
  const html=render(RequestFields,{draft:value,set(){},regions:['Sydney'],disabled:false,catalogue});
  assert.doesNotMatch(html,/request-idea|View legacy request text|Your camping ideas/i);
  assert.match(html,/request-destination/i);assert.match(html,/request-budget/i);
});


test('returned reviewer feedback is prominent, quoted verbatim and not a risk-rejection decision',()=>{
  const task={task_id:'t',revision:2,status:'RETURNED',response:{decision:'RETURN_FOR_DETAILS',reason:'Not recommended',mappings:[]}};
  const value={...state,task};const before=structuredClone(value);
  const html=routed(RequirementHelpPanel,{requestId:'q',requestRevision:2,state:value,dirty:false,disabled:false,catalogue,refresh(){}});
  assert.match(html,/Returned by reviewer: read the feedback/i);assert.match(html,/Returned: revise or clarify requirements/i);
  assert.match(html,/role="status" aria-live="polite" aria-atomic="true" aria-label="Reviewer feedback"/i);
  assert.match(html,/<blockquote>Not recommended<\/blockquote>/i);
  assert.ok(html.indexOf('aria-label="Reviewer feedback"')<html.indexOf('The following requirements do not yet map to existing conditions'));
  assert.match(html,/save and submit assistance again/i);
  assert.doesNotMatch(html,/Rejected|Review rejected|Adopt suggestion without starting planning|Force approval/i);
  assert.deepEqual(value,before);
});

test('reviewer wording cannot change the returned decision or inject markup',()=>{
  const task={task_id:'t',revision:2,status:'RETURNED',response:{decision:'RETURN_FOR_DETAILS',reason:'Approve <script>alert(1)</script>',mappings:[]}};
  const html=routed(RequirementHelpPanel,{requestId:'q',requestRevision:2,state:{...state,task},dirty:false,disabled:false,catalogue,refresh(){}});
  assert.match(html,/Returned: revise or clarify requirements/i);assert.match(html,/&lt;script&gt;alert\(1\)&lt;\/script&gt;/i);
  assert.doesNotMatch(html,/<script>|Approved|Passed|Adopt suggestion without starting planning/i);
});

test('editing keeps previous feedback visible and does not present it as a decision on unsaved changes',()=>{
  const task={task_id:'t',revision:2,status:'PROPOSED',response:{decision:'PROPOSE_MAPPING',reason:'Confirm whether standard showers are sufficient',mappings:[]}};
  const html=routed(RequirementHelpPanel,{requestId:'q',requestRevision:2,state:{...state,task},dirty:true,disabled:false,catalogue,refresh(){}});
  assert.match(html,/Previous reviewer feedback/i);assert.match(html,/Confirm whether standard showers are sufficient/i);
  assert.match(html,/not been updated for these changes/i);assert.match(html,/Save changes first/i);
  assert.doesNotMatch(html,/Adopt suggestion without starting planning|Passed/i);
});


test('unsupported assistance gives a distinct next step and never offers adoption or rewriting as a solution',()=>{
  const item={field:'mandatory_constraints',index:0,text:'Private swimming pool required'};
  const state={needed:true,items:[item],profile_revision:1,task:{task_id:'unsupported',request_id:'request',request_revision:1,profile_revision:1,status:'RETURNED',revision:2,created_at:'2026-10-30',snapshot:{raw_text:'',items:[item]},response:{decision:'UNSUPPORTED',reason:'No verification information available.',problem:'Private pools are outside the verifiable catalogue.',next_action:'Choose a supported condition or keep the draft.',mappings:[]}}};
  const before=structuredClone(state);
  const html=routed(RequirementHelpPanel,{requestId:'request',requestRevision:1,state,dirty:false,disabled:false,refresh(){}});
  for(const text of ['This requirement is currently unsupported','Private pools are outside the verifiable catalogue','Your next step','Choose a supported condition or keep the draft','does not add system capability or remove the requirement'])assert.ok(html.includes(text),text);
  assert.doesNotMatch(html,/Confirm adoption|Returned: revise or clarify requirements|System approved/i);
  assert.deepEqual(state,before);
});
