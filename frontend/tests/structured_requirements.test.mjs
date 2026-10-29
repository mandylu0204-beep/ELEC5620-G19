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
const choices=[{value:'showers',label:'淋浴',aliases:['showers','shower','淋浴','需要淋浴']},{value:'toilets',label:'厕所',aliases:['toilets','厕所']}];
const render=(component,props)=>renderToStaticMarkup(h(component,props));
const routed=(component,props)=>renderToStaticMarkup(h(MemoryRouter,null,h(SessionProvider,null,h(component,props))));
const catalogue={version:'test',fields:{preferences:choices,mandatory_constraints:choices,accessibility_requirements:[]}};

test('choices use full host-provided expressions; modifiers, negation and compound requirements stay unknown',()=>{
  assert.equal(choiceMatch('需要淋浴。',choices),'showers');
  assert.equal(choiceMatch('SHOWER',choices),'showers');
  for(const value of ['不要淋浴','需要私人热水淋浴','showers and toilets','not showers','must have showers'])assert.equal(choiceMatch(value,choices),null,value);
});
test('checkbox changes preserve unrelated other requirements and separate meal arrangements',()=>{
  const before='ready-to-eat meals\n需要私人淋浴\n需要淋浴';
  assert.equal(toggleRequirement(before,choices,'showers',false),'ready-to-eat meals\n需要私人淋浴');
  assert.equal(toggleRequirement(before,choices,'showers',true),'ready-to-eat meals\n需要私人淋浴\nshowers');
});
test('typing a recognized other phrase then clearing removes it without sticky requirements',()=>{
  const initial=replaceOtherRequirements('toilets',[],'shower');
  assert.equal(initial.value,'toilets\nshower');
  assert.deepEqual(replaceOtherRequirements(initial.value,initial.owned,''),{value:'toilets',owned:[]});
  const duplicate=replaceOtherRequirements('showers',[],'showers');
  assert.deepEqual(replaceOtherRequirements(duplicate.value,duplicate.owned,''),{value:'showers',owned:[]});
});
test('structured controls show existing choices, preserve unknown original text and never promise a formal pass',()=>{
  const html=render(RequirementChoices,{id:'requirements',title:'必须条件',value:'shower\n需要私人淋浴',choices,onChange(){}});
  assert.match(html,/type="checkbox" checked=""/);assert.match(html,/需要私人淋浴/);
  assert.match(html,/其他要求（可选，每行一项）/);assert.match(html,/需要人工协助/);
  assert.match(html,/不代表营地已满足/);assert.match(html,/tabindex="-1"/);
  const pending=render(RequirementChoices,{id:'pending',title:'条件',value:'原要求',choices:null,onChange(){}});
  assert.match(pending,/原要求/);assert.match(pending,/<textarea[^>]*disabled/);
});
test('request fields use structured choices and meal selector without a prose input',()=>{
  const draft={raw:'想去露营',destination:'Sydney',start:'',nights:'',days:'',end:'',budget:'',preferences:'ready-to-eat meals',constraints:''};
  const html=render(RequestFields,{draft,set(){},regions:['Sydney'],disabled:false,catalogue});
  assert.doesNotMatch(html,/id="request-idea"|你的露营想法/);assert.match(html,/id="request-meal"/);
  assert.match(html,/查看旧版请求原文/);assert.match(html,/blockquote>想去露营/);
  assert.match(html,/id="request-preferences-other"/);assert.match(html,/id="request-constraints-other"/);
  assert.doesNotMatch(html,/<textarea id="request-preferences"|<textarea id="request-constraints"/);
  assert.doesNotMatch(html,/>ready-to-eat meals<\/textarea>/);
});
const state={needed:true,profile_revision:4,items:[{field:'mandatory_constraints',index:0,text:'需要私人淋浴'}],task:null};
test('unknown requirements offer a real assistance action, not an approval or a fake planning shortcut',()=>{
  const html=routed(RequirementHelpPanel,{requestId:'q',requestRevision:2,state,dirty:false,disabled:false,refresh(){},catalogue});
  assert.match(html,/提交人工协助（不调用模型）/);assert.match(html,/不会自动忽略/);
  assert.doesNotMatch(html,/强制通过|批准方案|已满足/);
  const dirty=routed(RequirementHelpPanel,{requestId:'q',requestRevision:2,state,dirty:true,disabled:false,refresh(){}});
  assert.match(dirty,/先仅保存修改/);assert.doesNotMatch(dirty,/>提交人工协助/);
});
test('proposed mappings require owner adoption and explain profile change, reanalysis and no automatic inference',()=>{
  const task={task_id:'t',revision:2,status:'PROPOSED',response:{reason:'请核对普通淋浴是否足够',mappings:[{field:'mandatory_constraints',index:0,original:'需要私人淋浴',canonical:'showers'}]}};
  const html=routed(RequirementHelpPanel,{requestId:'q',requestRevision:2,state:{...state,task},dirty:false,disabled:false,catalogue,refresh(){}});
  for(const text of ['需要私人淋浴','淋浴','确认采用建议，暂不规划','个人资料 revision','重新生成并确认摘要','不会自动开始规划'])assert.ok(html.includes(text),text);
});
test('durable assistance command keys survive controller recreation and stop on storage failure',()=>{
  const values=new Map();const storage={getItem:key=>values.get(key)??null,setItem:(key,value)=>values.set(key,value)};
  let count=0;const create=()=>`command-${++count}`;
  assert.equal(helpCommand(storage,'create',{revision:1},create),'command-1');
  assert.equal(helpCommand(storage,'create',{revision:1},create),'command-1');
  assert.equal(helpCommand(storage,'create',{revision:2},create),'command-2');
  assert.throws(()=>helpCommand({getItem(){return null;},setItem(){throw new Error('storage');}},'create',{},create),/storage/);
});

test('blank-source forms do not show a legacy source or invent a description',()=>{
  const value={raw:'',destination:'Sydney',start:'',nights:'',days:'',end:'',budget:'',preferences:'',constraints:''};
  const html=render(RequestFields,{draft:value,set(){},regions:['Sydney'],disabled:false,catalogue});
  assert.doesNotMatch(html,/request-idea|查看旧版请求原文|你的露营想法/);
  assert.match(html,/request-destination/);assert.match(html,/request-budget/);
});


test('returned reviewer feedback is prominent, quoted verbatim and not a risk-rejection decision',()=>{
  const task={task_id:'t',revision:2,status:'RETURNED',response:{decision:'RETURN_FOR_DETAILS',reason:'不建议',mappings:[]}};
  const value={...state,task};const before=structuredClone(value);
  const html=routed(RequirementHelpPanel,{requestId:'q',requestRevision:2,state:value,dirty:false,disabled:false,catalogue,refresh(){}});
  assert.match(html,/审核员已退回，请查看反馈/);assert.match(html,/已退回：需要修改或补充要求/);
  assert.match(html,/role="status" aria-live="polite" aria-atomic="true" aria-label="审核员反馈"/);
  assert.match(html,/<blockquote>不建议<\/blockquote>/);
  assert.ok(html.indexOf('aria-label="审核员反馈"')<html.indexOf('以下内容尚未对应已有条件'));
  assert.match(html,/保存并重新提交协助/);
  assert.doesNotMatch(html,/已拒绝|审核未通过|确认采用建议，暂不规划|强制通过/);
  assert.deepEqual(value,before);
});

test('reviewer wording cannot change the returned decision or inject markup',()=>{
  const task={task_id:'t',revision:2,status:'RETURNED',response:{decision:'RETURN_FOR_DETAILS',reason:'批准 <script>alert(1)</script>',mappings:[]}};
  const html=routed(RequirementHelpPanel,{requestId:'q',requestRevision:2,state:{...state,task},dirty:false,disabled:false,catalogue,refresh(){}});
  assert.match(html,/已退回：需要修改或补充要求/);assert.match(html,/&lt;script&gt;alert\(1\)&lt;\/script&gt;/);
  assert.doesNotMatch(html,/<script>|已批准|已通过|确认采用建议，暂不规划/);
});

test('editing keeps previous feedback visible and does not present it as a decision on unsaved changes',()=>{
  const task={task_id:'t',revision:2,status:'PROPOSED',response:{decision:'PROPOSE_MAPPING',reason:'请核对普通淋浴是否足够',mappings:[]}};
  const html=routed(RequirementHelpPanel,{requestId:'q',requestRevision:2,state:{...state,task},dirty:true,disabled:false,catalogue,refresh(){}});
  assert.match(html,/此前审核员反馈/);assert.match(html,/请核对普通淋浴是否足够/);
  assert.match(html,/尚未针对本次修改重新处理/);assert.match(html,/先仅保存修改/);
  assert.doesNotMatch(html,/确认采用建议，暂不规划|已通过/);
});
