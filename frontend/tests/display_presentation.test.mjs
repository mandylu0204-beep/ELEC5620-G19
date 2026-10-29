import test, {after} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createElement as h} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {MemoryRouter} from 'react-router-dom';
import {createServer} from 'vite';
import {changedSections,discardMessage,tentSummary,PROFILE_SAVED_NOTICE,chineseProse} from '../src/display_facts.ts';
import {evidenceState,planRowState,safetyCondition,safetyRegulations} from '../src/plan_language.ts';

// Vite only transforms modules in middleware mode: no HTTP listener, browser,
// app database, personal env file or model client is started by these tests.
const server=await createServer({configFile:false,envDir:false,appType:'custom',
  server:{middlewareMode:true,hmr:false,ws:false,watch:null},optimizeDeps:{noDiscovery:true}});
after(()=>server.close());
const panels=await server.ssrLoadModule('/src/display_panels.tsx');
const {LogisticsIssues}=await server.ssrLoadModule('/src/logistics_issues.tsx');
const {TripCoveragePanel}=await server.ssrLoadModule('/src/trip_coverage.tsx');
const {SafetyInformation}=await server.ssrLoadModule('/src/safety_information.tsx');
const {PlanView,NewPlanPrompt,TripSeriesCard}=await server.ssrLoadModule('/src/plans.tsx');
const {ChangePlanning,revealRevisionPanel}=await server.ssrLoadModule('/src/planning.tsx');
const {ProfileAdoptionPreview}=await server.ssrLoadModule('/src/replan.tsx');
const {RequirementsChangePreview,RequestHistory}=await server.ssrLoadModule('/src/requests.tsx');
const {historicalReviewNotice}=await server.ssrLoadModule('/src/reviews.tsx');
const {profileChanges}=await server.ssrLoadModule('/src/profile_changes.ts');
const {App}=await server.ssrLoadModule('/src/App.tsx');
const {GroupSizeField,EquipmentUnitField,addEquipment,changeEquipmentCategory,fixedEquipmentUnit,ProfileSummary,ProfileCorrectionStatus,TransportModeField,PublicTransportNotice}=await server.ssrLoadModule('/src/profile.tsx');
const {VehicleFields}=await server.ssrLoadModule('/src/vehicle_fields.tsx');
const {SessionProvider,LoginPage}=await server.ssrLoadModule('/src/session.tsx');
const {RegisterPage}=await server.ssrLoadModule('/src/register.tsx');
const {CookingPreparationPanel,cookingDraft}=await server.ssrLoadModule('/src/cooking_preparation.tsx');
const {TripPreparation}=await server.ssrLoadModule('/src/trip_preparation.tsx');
const {NearMatches}=await server.ssrLoadModule('/src/near_matches.tsx');
const {prepareProfileEquipment}=await server.ssrLoadModule('/src/vehicle_profile.ts');
const {profileGuidance:preparationGuidance}=await server.ssrLoadModule('/src/profile_guidance.ts');
const {profileFocusId:preparationFocus}=await server.ssrLoadModule('/src/profile_focus.ts');
const render=(component,props)=>renderToStaticMarkup(h(component,props));
const routed=(component,props)=>renderToStaticMarkup(h(MemoryRouter,null,h(component,props)));
test('system preparation removes artificial inventory prerequisites while preserving old registered facts',()=>{
  assert.deepEqual(prepareProfileEquipment([],'PUBLIC_TRANSPORT','',true),[]);
  const legacy=[{item_key:'transport_itinerary',label:'原计划',quantity:'1',unit:'plan',capacity:'',confirmed:true}];
  assert.deepEqual(prepareProfileEquipment(legacy,'PUBLIC_TRANSPORT','',true),legacy);
  assert.equal(prepareProfileEquipment([],'PUBLIC_TRANSPORT','',false)[0].item_key,'transport_itinerary');
  assert.equal(prepareProfileEquipment([],'CAR','2',true)[0].confirmed,false);
  const fields=['transport.estimated_km','transport.assumptions','equipment.transport_itinerary','equipment.fire_free_meal_plan'];
  const draft={equipment:legacy,transport:'PUBLIC_TRANSPORT',vehicles:'',km:'',children:'no',childrenCount:'0',experience:'BEGINNER',systemPreparation:true};
  const issues=fields.map(field=>({field,category:'USER_INPUT',target:'PROFILE'}));
  assert.deepEqual(preparationGuidance(draft,issues),{});
  fields.forEach(field=>assert.equal(preparationFocus(field,legacy,'PUBLIC_TRANSPORT',true),null));
});
test('transport selection omits unknown choices and yellow explanatory notices without inventing a selection',()=>{
  const props={value:'',supported:['CAR','PUBLIC_TRANSPORT'],onChange(){},error:'',systemPreparation:true};
  const html=render(TransportModeField,props);
  assert.match(html,/<option value="" disabled="" hidden="" selected="">请选择交通方式/);
  assert.doesNotMatch(html,/尚未明确|class="mode-notice"|自行核对去程|固定模拟出发地/);
  assert.doesNotMatch(html,/<option value="CAR" selected/);
});
test('saved preparation distinguishes synthetic group kilometres, transport allowance and departure checks',()=>{
  const value={system_preparation:true,transport_type:'CAR',origin_label:'悉尼市区（固定模拟出发地）',
    access_and_capacity:true,estimated_total_vehicle_km:'200',vehicle_count:2,estimated_transport_cents:7600,meal_mode:'SELF_CATERED',source_refs:[]};
  const before=structuredClone(value);const html=render(TripPreparation,{value});
  for(const text of ['200 km','2 辆','76.00','不是用户希望的行程长度','不是实测道路距离','核对炉具、燃料和炊具'])assert.ok(html.includes(text),text);
  assert.deepEqual(value,before);
  const transit=render(TripPreparation,{value:{...value,transport_type:'PUBLIC_TRANSPORT',estimated_transport_cents:null}});
  assert.match(transit,/未知，不能按零费用处理/);assert.match(transit,/去程、返程末班/);
  assert.doesNotMatch(transit,/累计里程（模拟）|本次确认车辆/);
  const ready=render(TripPreparation,{value:{...value,meal_mode:'READY_TO_EAT'}});
  assert.match(ready,/<dt>用餐方式<\/dt><dd>即食餐食<\/dd>/);
  assert.doesNotMatch(ready,/无火餐食计划|无需登记/);
});
test('no-match adjustment is an explicit user choice, disabled in read-only history',()=>{
  const value={near_matches:[],excluded_count:10,ranking:'test',metadata_note:null,scope:'SAVED'};
  const html=routed(NearMatches,{value,planId:'trip-1'});
  assert.match(html,/系统不会替你更改已确认需求/);
  assert.match(html,/href="\/profile\?plan_id=trip-1&amp;focus=transport.transport_type"/);
  assert.match(html,/href="\/plans\/trip-1\/update"/);
  assert.doesNotMatch(routed(NearMatches,{value,planId:'trip-1',readOnly:true}),/href=|<button/);
});
test('new summaries hide irrelevant mileage and keep old virtual plans explicitly historical',()=>{
  const profile={group_size:2,experience_level:'BEGINNER',has_children:false,children_count:0,accessibility_requirements:[],
    transport:{transport_type:'PUBLIC_TRANSPORT',vehicle_count:1,estimated_km:'999',assumptions:['原交通说明']},
    equipment:[{item_key:'transport_itinerary',label:'原交通计划',quantity:1,unit:'plan',capacity_persons:null,confirmed:true}]};
  const before=structuredClone(profile);
  const modern=render(ProfileSummary,{profile,systemPreparation:true});
  assert.match(modern,/旧版计划登记记录（仅供历史回看）/);
  assert.match(modern,/本次不将这些记录作为装备或可达证明/);
  assert.doesNotMatch(modern,/999|车辆数量|车辆 \/ 总路程|交通估算说明/);
  const legacy=render(ProfileSummary,{profile});
  assert.match(legacy,/999|交通估算说明/);assert.doesNotMatch(legacy,/旧版计划登记记录/);
  assert.deepEqual(profile,before);
});
const budgetIssue={issue_id:'budget',code:'OVER_BUDGET',category:'USER_INPUT',field:'budget_cents',item_key:null,
  current:34600,required:30000,target:'REQUEST',action_url:'/plans/plan/update?focus=request-budget'};
test('over-budget task separates lower-cost preparation from changing the confirmed budget',()=>{
  const calls=[];const props={items:[structuredClone(budgetIssue)],onSafety(){},onRevisionRequested:goal=>calls.push(goal)};
  const before=structuredClone(props.items);
  const html=routed(LogisticsIssues,props);
  assert.match(html,/保持预算，寻找更低费用方案/);assert.match(html,/调整本次预算/);
  assert.match(html,/href="\/plans\/plan\/update\?focus=request-budget"/);
  assert.match(html,/确认后才执行/);assert.match(html,/不保证总费用已在预算内/);
  assert.match(html,/AUD 346\.00/);assert.match(html,/AUD 300\.00/);
  const buttons=[];
  function walk(node){
    if(Array.isArray(node)){node.forEach(walk);return;}
    if(!node||typeof node!=='object')return;
    if(node.type==='button')buttons.push(node);
    walk(node.props?.children);
  }
  walk(LogisticsIssues(props));
  buttons.find(node=>node.props.children==='保持预算，寻找更低费用方案').props.onClick();
  assert.deepEqual(calls,['cheaper campsite']); // Prepares the existing goal, no command submission.
  assert.deepEqual(props.items,before);
});
test('history and unavailable revision never offer an active lower-cost action',()=>{
  const props={items:[budgetIssue],onSafety(){},onRevisionRequested(){}};
  assert.doesNotMatch(routed(LogisticsIssues,{...props,disabled:true}),/保持预算，寻找更低费用方案|href=/);
  const unavailable=routed(LogisticsIssues,{items:[budgetIssue],onSafety(){}});
  assert.doesNotMatch(unavailable,/保持预算，寻找更低费用方案/);
  assert.match(unavailable,/当前不能启动营地修订/);assert.match(unavailable,/调整本次预算/);
});
test('budget navigation opens the real revision panel and focuses its editable goal without submitting',()=>{
  const calls=[];
  const panel={tagName:'DETAILS',open:false,scrollIntoView:options=>calls.push(options)};
  const goal={focus:()=>calls.push('focus')};
  assert.equal(revealRevisionPanel('adjust',id=>id==='adjust'?panel:id==='revision-choice'?goal:null),true);
  assert.equal(panel.open,true);assert.deepEqual(calls,[{block:'start'},'focus']);
  assert.equal(revealRevisionPanel('missing',()=>null),false);
});
test('cheaper revision confirmation preserves the displayed budget and explains the actual limited strategy',()=>{
  const data=planFixture();data.run.is_active=true;data.revision_available=true;
  data.confirmed_context.demo_context={mode:'agent'};
  const before=structuredClone(data);
  const html=renderToStaticMarkup(h(MemoryRouter,null,h(SessionProvider,null,h(ChangePlanning,{
    data,refresh(){},choice:'cheaper campsite',onChoiceChange(){},
  }))));
  assert.match(html,/<option value="cheaper campsite" selected=""/);
  for(const text of ['保留预算 AUD 300.00','尝试寻找更便宜的营地','总费用仍可能超出预算','确认保持预算并修订方案'])assert.ok(html.includes(text),text);
  assert.deepEqual(data,before);
});
test('transport choices follow backend capabilities, retain unsupported history and never promise live timetable checks',()=>{
  const props={value:'PUBLIC_TRANSPORT',supported:['CAR','PUBLIC_TRANSPORT'],onChange(){},error:''};
  const html=render(TransportModeField,props);
  assert.match(html,/<option value="CAR"/);assert.match(html,/<option value="PUBLIC_TRANSPORT"/);
  assert.doesNotMatch(html,/<option value="WALKING"|<option value="OTHER"/);
  assert.doesNotMatch(html,/class="mode-notice"|尚未明确/);
  const old=render(TransportModeField,{...props,value:'WALKING'});
  assert.match(old,/<option value="WALKING" disabled="" selected=""/);assert.match(old,/历史资料，当前暂不支持/);
  const pending=render(TransportModeField,{...props,supported:null});
  assert.match(pending,/<select[^>]*disabled=""/);
  assert.match(render(PublicTransportNotice,{}),/营地可达标记/);
});
test('connection tasks link to real profile fields while source gaps keep operator-only guidance',()=>{
  const connection=routed(LogisticsIssues,{items:[{issue_id:'connection',code:'TRANSPORT_CONNECTION',target:'PROFILE',
    category:'USER_INPUT',field:'transport.assumptions',action_url:'/profile?focus=transport.assumptions'}],onSafety(){}});
  assert.match(connection,/公共交通往返及接驳安排待核对/);assert.match(connection,/focus=transport.assumptions/);
  assert.match(connection,/不能视为已订票/);
  const data=routed(LogisticsIssues,{items:[{issue_id:'access',code:'TRANSPORT_ACCESS_DATA',target:'OPERATOR',
    category:'DATA_GAP',field:'transport.public_transport_access',action_url:null}],onSafety(){}});
  assert.match(data,/修改个人车辆数量不能解决/);assert.doesNotMatch(data,/href=|<button/);
});
test('completed correction form offers explicit next check without a stale count, dead button or formal pass',()=>{
  const props={ready:true,loading:false,failed:false,targets:[],dirty:false,returnPlan:true};
  const saved=render(ProfileCorrectionStatus,props);
  assert.match(saved,/当前表单没有待补充提示/);assert.match(saved,/不代表原方案的问题已解决/);
  assert.match(saved,/原方案仍保留上次确认的资料与检查结果/);
  assert.doesNotMatch(saved,/下方 \d+ 处|<button|检查通过|已解决<|已完成正式检查/);
  const dirty=render(ProfileCorrectionStatus,{...props,dirty:true});
  assert.match(dirty,/请先保存修改/);assert.doesNotMatch(dirty,/下方 \d+ 处|<button/);
  const active=render(ProfileCorrectionStatus,{...props,targets:['gear-quantity-0','gear-capacity-0']});
  assert.match(active,/下方 2 处/);assert.match(active,/前往首个待补充位置/);
  for(const state of [{loading:true,ready:false},{failed:true,ready:false}]){
    const pending=render(ProfileCorrectionStatus,{...props,targets:['gear-quantity-0'],...state});
    assert.doesNotMatch(pending,/<button|下方 1 处/);
  }
});
test('vehicle total guidance highlights the editable vehicle quantity rather than a read-only output',()=>{
  const html=render(VehicleFields,{equipment:[{item_key:'vehicle',quantity:'1',capacity:'5',confirmed:true}],
    issues:{},guidance:{'vehicle-count':'请核对车辆总数'},onChange(){},onRemove(){},onAdd(){}});
  assert.match(html,/<input[^>]*id="gear-quantity-0"[^>]*aria-invalid="true"/);
  assert.match(html,/请核对车辆总数/);assert.doesNotMatch(html,/id="vehicle-count"|id="gear-unit-0"|type="checkbox"|已确认可用于本次出行/);
});
test('hero captions stay level while only the mountain illustration is tilted',()=>{
  const css=readFileSync(new URL('../src/styles.css',import.meta.url),'utf8');
  const transforms=selector=>Array.from(css.matchAll(new RegExp(selector+'\\s*\\{([^}]*)\\}','g')))
    .flatMap(match=>Array.from(match[1].matchAll(/(?:^|;)\s*transform\s*:\s*([^;]+)/g),entry=>entry[1].trim()));
  assert.equal(transforms('\\.hero-art').at(-1),'none');
  assert.equal(transforms('\\.hero-art\\s*>\\s*\\.mountain').at(-1),'rotate(-3deg)');
  const html=routed(App,{});
  assert.match(html,/class="hero-art"><span>清晰规划，从容出发<\/span><svg/);
  assert.match(html,/<\/svg><div>规划 · 检查 · 审核<\/div>/);
});
const tent={records:[{quantity:2,capacity_per_tent:1,total_capacity:2,confirmed:true,unit:'item'}],
  group_size:3,registered_tent_count:2,registered_capacity:2,assessed_capacity:'2',required_person_spaces:'3',missing_person_spaces:'1'};

const gear=(patch={})=>({item_key:'tent',label:'帐篷',quantity:'2',unit:'item',capacity:'3',confirmed:true,...patch});
const preparation={scope:'PREPARATION_ONLY',official_assessment:false,fuel_price_status:'MISSING_REFERENCE',
  items:['camping_stove','fuel_canister'].map(item_key=>({item_key,recorded:false,entered_quantity:null,confirmed_quantity:null,unit_valid:true}))};
test('first cooking preparation names both items without declaring an inactive fuel rule unnecessary or passed',()=>{
  const html=render(CookingPreparationPanel,{value:preparation});
  for(const phrase of ['烹饪装备准备','露营炉具','燃料罐','尚未填写数量'])assert.ok(html.includes(phrase),phrase);
  assert.doesNotMatch(html,/检查通过|确认已解决|href=|<button|规则预检查|系统报价资料|虚填|不调用模型|燃料费用待确认/);
  const issue=routed(LogisticsIssues,{items:[{issue_id:'cooking_method',code:'COOKING_ARRANGEMENT',category:'USER_INPUT',target:'REQUEST',
    cooking_preparation:preparation,alternate_action_url:'/profile?plan_id=p&focus=equipment.camping_stove'}],onSafety(){}});
  assert.match(issue,/一起核对炉具与燃料资料/);assert.match(issue,/燃料罐/);
});
test('draft check is explicit and expires on edit; zero estimated gap cannot grant a formal pass',()=>{
  const value={...preparation,required_fuel_quantity:'2',fuel_gap:'0',calculation_status:'DRAFT_ESTIMATE'};
  const html=render(CookingPreparationPanel,{value:preparation,preview:value,onCheck(){}});
  assert.match(html,/预计需要燃料罐 2 个/);assert.match(html,/还缺 0 个/);
  assert.match(html,/更新准备情况/);assert.doesNotMatch(html,/检查通过|已解决|燃料费用待确认/);
  const stale=render(CookingPreparationPanel,{value:preparation,preview:value,stale:true,onCheck(){}});
  assert.match(stale,/资料已修改，请更新准备情况/);assert.doesNotMatch(stale,/预计需要燃料罐 2 个/);
  const unknown=render(CookingPreparationPanel,{value:preparation,preview:{...preparation,calculation_status:'WAITING_FOR_STOVE',example:{stove_quantity:1,fuel_quantity:'2'}}});
  assert.match(unknown,/请先填写可用炉具数量/);assert.doesNotMatch(unknown,/规则示例|预计需要燃料罐|检查通过/);
  const shortage=render(CookingPreparationPanel,{value:preparation,preview:{...value,fuel_gap:'1'}});
  assert.match(shortage,/燃料费用待确认/);assert.match(shortage,/还缺 1 个/);
  const invalid=render(CookingPreparationPanel,{value:{...preparation,items:[{...preparation.items[0],recorded:true,unit_valid:false}]}});
  assert.match(invalid,/请核对数量单位/);
});
test('cooking preparation survives final/history rendering without offering an active profile update',()=>{
  const data={...planFixture(),cooking_preparation:preparation};
  const history=routed(PlanView,{data,error:'',refresh(){},snapshot:true});
  assert.match(history,/烹饪装备准备/);assert.doesNotMatch(history,/一起核对炉具与燃料资料 ↗/);
  const reviewer=routed(PlanView,{data,error:'',refresh(){},review:true});
  assert.match(reviewer,/烹饪装备准备/);assert.doesNotMatch(reviewer,/一起核对炉具与燃料资料 ↗/);
});
test('cooking candidate preserves unknowns, units, duplicates and confirmation; names never decide item type',()=>{
  const rows=[gear({item_key:'camping_stove',label:'燃料罐',quantity:'',confirmed:false}),gear({item_key:'fuel_canister',quantity:'2',unit:'set'}),gear()];
  const before=structuredClone(rows);const draft=cookingDraft(rows);
  assert.equal(draft.length,2);assert.equal(draft[0].item_key,'camping_stove');assert.equal(draft[0].quantity,null);assert.equal(draft[0].confirmed,false);
  assert.equal(draft[1].unit,'set');assert.deepEqual(rows,before);
  for(const quantity of ['-1','1.5','1e2','9007199254740992'])assert.throws(()=>cookingDraft([gear({item_key:'camping_stove',quantity})]),/非负整数/);
});
test('fuel task explains its own missing quote and offers real correction paths, not a price editor',()=>{
  const item={issue_id:'equipment.fuel_canister',code:'EQUIPMENT_SHORTAGE',category:'EQUIPMENT_GAP',field:'equipment.fuel_canister.quantity',item_key:'fuel_canister',
    current:{records:[],available_quantity:'0'},required:{quantity:'3',missing_quantity:'3'},target:'PROFILE',action_url:'/profile?plan_id=owned-plan&focus=equipment.fuel_canister.quantity',
    arrangement_action_url:'/plans/owned-plan/update?focus=request-meal',cost_impacts:[{code:'PRICE_DATA',item_key:'fuel_canister',category:'ADDITIONAL_GEAR',unit_price_cents:null}]};
  const html=routed(LogisticsIssues,{items:[item],onSafety(){}});
  assert.match(html,/燃料罐还缺 3 罐/);assert.match(html,/燃料罐费用待确认，完整总费用暂无法估算/);
  assert.match(html,/补充燃料罐/);assert.match(html,/调整用餐方式/);
  assert.doesNotMatch(html,/必要装备数量不足|问题：|影响：|处理：|不是另一项无关任务|<h3>系统缺少适用报价/);
  const history=routed(LogisticsIssues,{items:[item],disabled:true,onSafety(){}});
  assert.doesNotMatch(history,/href=/);assert.match(history,/只展示当时的缺项/);
});
test('dependent checks remain visible before quantities are known and source-only problems have no fake link',()=>{
  const html=routed(LogisticsIssues,{items:[{issue_id:'stove',code:'EQUIPMENT_DETAILS',category:'USER_INPUT',item_key:'camping_stove',target:'PROFILE',action_url:'/profile?focus=equipment.camping_stove',pending_checks:[{item_key:'fuel_canister',status:'WAITING_FOR_INPUT'}]}],onSafety(){}});
  assert.match(html,/补充后再核对：燃料罐/);assert.match(html,/所需数量待确认/);
  const price=routed(LogisticsIssues,{items:[{issue_id:'price.fuel',code:'PRICE_DATA',category:'DATA_GAP',item_key:'fuel_canister',target:'OPERATOR',action_url:null}],onSafety(){}});
  assert.match(price,/燃料罐 · 系统缺少适用报价/);assert.doesNotMatch(price,/href=|<button/);
});

test('equipment task names the saved shortage and a single correction link without repeated instructions',()=>{
  const item={issue_id:'equipment.sleeping_mat',code:'EQUIPMENT_SHORTAGE',category:'EQUIPMENT_GAP',field:'equipment.sleeping_mat.quantity',item_key:'sleeping_mat',
    current:{records:[],available_quantity:'0',unit:'item'},required:{quantity:'2',missing_quantity:'2'},target:'PROFILE',action_url:'/profile?focus=equipment.sleeping_mat.quantity'};
  const before=structuredClone(item);
  const html=routed(LogisticsIssues,{items:[item],onSafety(){}});
  assert.match(html,/<h3>睡垫还缺 2 张<\/h3>/);assert.match(html,/本次需要 2 张，目前尚未登记。/);
  const card=html.slice(html.indexOf('<article'));
  assert.equal((card.match(/<a /g)||[]).length,1);assert.match(card,/补充睡垫 ↗/);
  assert.match(card,/href="\/profile\?focus=equipment.sleeping_mat.quantity"/);
  assert.doesNotMatch(card,/需要调整安排|必要装备数量不足|问题：|影响：|处理：|本次采用|此行程需要/);
  assert.deepEqual(item,before);
  assert.doesNotMatch(routed(LogisticsIssues,{items:[item],disabled:true,onSafety(){}}),/href=|<button/);
});

test('unknown equipment quantity is never zero and unconfirmed stock is not available stock',()=>{
  const item={issue_id:'mat',code:'EQUIPMENT_DETAILS',item_key:'sleeping_mat',target:'PROFILE',action_url:'/profile',
    current:{records:[{quantity:null,unit:'item',confirmed:false}],available_quantity:null,unit:'item'},required:{quantity:'2',missing_quantity:null}};
  const unknown=routed(LogisticsIssues,{items:[item],onSafety(){}});
  assert.match(unknown,/本次需要 2 张，可用数量尚未确定/);assert.doesNotMatch(unknown,/还缺 0|可用 0|还缺 2/);
  const unconfirmed=routed(LogisticsIssues,{items:[{...item,code:'EQUIPMENT_SHORTAGE',
    current:{...item.current,records:[{quantity:2,unit:'item',confirmed:false}],available_quantity:'0'},required:{quantity:'2',missing_quantity:'2'}}],onSafety(){}});
  assert.match(unconfirmed,/已确认可用 0 张/);assert.match(unconfirmed,/请确认已登记的物品本次是否可用/);
  assert.doesNotMatch(unconfirmed,/已确认可用 2/);
});

test('compact tent and vehicle tasks preserve person capacity and the seat-filling hint',()=>{
  const base={issue_id:'tent',code:'EQUIPMENT_DETAILS',item_key:'tent',target:'PROFILE',action_url:'/profile',tent_capacity:tent};
  const html=routed(LogisticsIssues,{items:[base],onSafety(){}});
  assert.match(html,/帐篷还缺 1 人住宿容量/);assert.match(html,/每顶可住人数/);assert.doesNotMatch(html,/还缺 1 顶/);
  const vehicle=routed(LogisticsIssues,{items:[{...base,item_key:'vehicle',code:'VEHICLE_DETAILS',tent_capacity:undefined,
    current:{unit:'person_space'},required:{capacity_persons:3,missing_quantity:'1'}}],onSafety(){}});
  assert.match(vehicle,/车辆还缺 1 个座位/);assert.match(vehicle,/本次需容纳 3 人/);
  assert.match(vehicle,/每辆载客人数（含驾驶员）/);assert.match(vehicle,/补充交通安排/);
  const water=routed(LogisticsIssues,{items:[{...base,item_key:'drinking_water',code:'EQUIPMENT_SHORTAGE',tent_capacity:undefined,
    current:{records:[],unit:'litre',available_quantity:'0'},required:{quantity:'4.5',missing_quantity:'4.5'}}],onSafety(){}});
  assert.match(water,/饮用水还缺 4\.5 升/);assert.doesNotMatch(water,/4\.5 件/);
});
test('update summary shows actual requirement differences and request history stays collapsed',()=>{
  const before=planFixture().confirmed_context.requirements;
  const after={...before,budget_cents:40000,preferences:['self-catered meals']};
  const html=render(RequirementsChangePreview,{before,after});
  assert.match(html,/小组预算/);assert.match(html,/AUD 400\.00/);assert.match(html,/自行烹饪/);assert.match(html,/不代表正式检查通过/);
  const history=routed(RequestHistory,{rows:[{request_id:'update',raw_text:'本次露营',status:'DRAFT',trip_series_id:'trip'}],deleting:null,selected:null,onSelect(){},onDelete(){},onCancel(){}});
  assert.match(history,/<details class="panel request-history">/);assert.doesNotMatch(history,/<details[^>]*open/);
  assert.match(history,/本次出行更新/);assert.match(history,/已保存的需求/);
  assert.doesNotMatch(history,/不代表新增了一次独立出行|同系列的更新方案/);
});
test('historical approval copy cannot imply permission to save the current successor',()=>{
  assert.match(historicalReviewNotice('HISTORY'),/不授权当前方案/);
  assert.match(historicalReviewNotice('HISTORY'),/不能据此保存当前最终方案/);
  assert.equal(historicalReviewNotice('APPROVAL'),null);
});
test('adoption preview shows exact revision and changed inventory, people and transport without a formal pass',()=>{
  const before=planFixture().confirmed_context.profile_snapshot;
  const after=structuredClone(before);after.group_size=4;after.transport.estimated_km='150';
  after.equipment=[{item_key:'tent',label:'三人帐',quantity:1,unit:'item',capacity_persons:3,confirmed:false}];
  const changes=profileChanges(before,after);
  assert.deepEqual(changes.map(item=>item.section),['同行人数','装备与车辆','交通安排']);
  const html=render(ProfileAdoptionPreview,{before,after,revision:7,sourceRevision:2});
  for(const value of ['revision 7','revision：2','原方案采用','本次拟采用','三人帐','未核实','150 km','不代表正式检查通过'])assert.ok(html.includes(value),value);
  assert.doesNotMatch(html,/检查通过<|已核实拥有/);
  assert.deepEqual(profileChanges(before,{...structuredClone(before),profile_id:'different-metadata'}),[]);
  const named=structuredClone(after);named.equipment=[{...after.equipment[0],item_key:'sleeping_bag',unit:'item',capacity_persons:null}];
  const changed=structuredClone(named);changed.equipment[0].item_key='groundsheet';
  assert.equal(profileChanges(named,changed)[0].section,'装备与车辆');
});
test('series card uses explicit final owning plan and never presents old success as new check success',()=>{
  const value={trip_series_id:'trip',revision:2,current_plan:{plan_id:'new-plan',run_status:'RUNNING',destination:'本次出行',created_at:'2026-10-22T00:00:00Z'},
    history:[{plan_id:'old-plan',destination:'原方案',created_at:'2026-10-21T00:00:00Z'}],last_final:{plan_id:'old-plan',final_id:'saved',is_current:false}};
  const html=routed(TripSeriesCard,{value,busy:false,onDeletePlan(){},onDeleteSeries(){}});
  assert.match(html,/href="\/plans\/old-plan\/finals\/saved"/);
  assert.doesNotMatch(html,/\/plans\/new-plan\/finals\/saved/);
  assert.match(html,/本次检查尚未完成/);assert.match(html,/历史方案（1）/);
  const archived=routed(TripSeriesCard,{value:{...value,current_plan:null},busy:false,onDeletePlan(){},onDeleteSeries(){}});
  assert.match(archived,/当前方案已删除/);assert.match(archived,/不会自动恢复旧方案或旧待办/);
});
test('fixed equipment units are readonly, tent displays 顶 but retains item for calculations',()=>{
  for(const [key,unit,title] of [['tent','item','顶'],['drinking_water','litre','升'],['meal_supplies','portion','份'],['transport_itinerary','plan','份计划']]){
    const item=gear({item_key:key,unit});
    const html=render(EquipmentUnitField,{item,index:0,onChange(){throw new Error('Must not change on read');}});
    assert.match(html,/readonly=""/i);assert.match(html,new RegExp(`value="${title}"`));
    assert.doesNotMatch(html,/<select|<option/);assert.equal(item.unit,unit);
    assert.equal(fixedEquipmentUnit(key),unit);
  }
  assert.equal(fixedEquipmentUnit('warm_layers','v1'),'set');
  assert.equal(fixedEquipmentUnit('warm_layers','2.1.0'),'item');
});
test('only other equipment can select units; selection reports actual backend code',()=>{
  let selected='';const props={item:gear({item_key:'other'}),index:0,onChange(value){selected=value;}};
  const html=render(EquipmentUnitField,props);
  assert.match(html,/<select/);assert.doesNotMatch(html,/readonly/i);
  for(const unit of ['item','litre','portion','vehicle','plan','set'])assert.ok(html.includes(`value="${unit}"`));
  const select=EquipmentUnitField(props).props.children.find(child=>child?.type==='select');
  select.props.onChange({target:{value:'litre'}});assert.equal(selected,'litre');
});
test('legacy mismatched unit stays visible until explicit correction; rendering never changes saved facts',()=>{
  const item=gear({unit:'litre'});let corrected='';
  const props={item,index:0,onChange(value){corrected=value;}};
  const html=render(EquipmentUnitField,props);
  assert.match(html,/value="升"/);assert.match(html,/已保存的单位与类别不符/);
  assert.equal(item.unit,'litre');assert.equal(corrected,'');
  const button=EquipmentUnitField(props).props.children.find(child=>child?.type==='button');
  button.props.onClick();assert.equal(corrected,'item');assert.equal(item.unit,'litre');
});
test('adding same-category equipment numbers generic names without changing quantity, capacity or confirmation',()=>{
  const original=[gear()];const copy=JSON.stringify(original);
  const items=addEquipment(original,'tent');
  assert.deepEqual(items.map(item=>item.label),['帐篷一','帐篷二']);
  assert.equal(JSON.stringify(original),copy);
  assert.deepEqual(items[0],{...original[0],label:'帐篷一'});
  assert.deepEqual(items[1],gear({label:'帐篷二',quantity:'',capacity:'',confirmed:false}));
  assert.deepEqual(addEquipment([],'tent').map(item=>item.label),['帐篷一']);
  assert.equal(addEquipment(items,'tent')[2].label,'帐篷三');
});
test('custom names and existing numbered names survive additions and removals without collisions',()=>{
  const items=[gear({label:'三人帐'}),gear({label:'帐篷一'}),gear({label:'帐篷三'})];
  assert.deepEqual(addEquipment(items,'tent').map(item=>item.label),['三人帐','帐篷一','帐篷三','帐篷二']);
  let many=[];for(let i=0;i<12;i++)many=addEquipment(many,'tent');
  assert.equal(many[9].label,'帐篷十');assert.equal(many[11].label,'帐篷十二');
  assert.equal(new Set(many.map(item=>item.label)).size,12);
});
test('category changes assign target units and distinct auto names while preserving user-defined names',()=>{
  let items=addEquipment(addEquipment([],'tent'),'tent');
  items=changeEquipmentCategory(items,1,'drinking_water');
  assert.equal(items[1].label,'饮用水一');assert.equal(items[1].unit,'litre');
  items=changeEquipmentCategory(items,1,'tent');
  assert.deepEqual(items.map(item=>item.label),['帐篷一','帐篷二']);assert.equal(items[1].unit,'item');
  const custom=changeEquipmentCategory([gear({label:'备用物品'})],0,'meal_supplies');
  assert.equal(custom[0].label,'备用物品');assert.equal(custom[0].unit,'portion');
  assert.equal(changeEquipmentCategory([gear({unit:'litre'})],0,'other')[0].unit,'litre');
  assert.equal(addEquipment([],'warm_layers','v1')[0].unit,'set');
});
test('profile snapshots preserve distinguishing tent names and individual capacities',()=>{
  const profile=planFixture().confirmed_context.profile_snapshot;
  profile.equipment=[{...gear({label:'三人帐'}),quantity:1,capacity_persons:3},{...gear({label:'单人帐'}),quantity:1,capacity_persons:1}];
  const html=render(ProfileSummary,{profile});
  assert.match(html,/三人帐：1 顶/);assert.match(html,/单人帐：1 顶/);
  assert.match(html,/该行总住宿容量 3 人/);assert.match(html,/该行总住宿容量 1 人/);
});

test('initial blank group field is neutral but still required and constrained to positive whole numbers',()=>{
  const html=render(GroupSizeField,{value:'',error:'请填写小组人数。',revealValidation:false,onTouch(){},onChange(){}});
  assert.match(html,/aria-invalid="false"/);
  assert.match(html,/必填/);assert.match(html,/required=""/);
  assert.match(html,/min="1"/);assert.match(html,/step="1"/);
  assert.match(html,/包括所有同行者/);
  assert.doesNotMatch(html,/field-error|请填写小组人数/);
});
test('blur and native invalid events reveal group errors without saving or calling a model',()=>{
  let touched=false,changed='';
  const props={value:'',error:'请填写小组人数。',revealValidation:false,onTouch(){touched=true;},onChange(value){changed=value;}};
  const input=GroupSizeField(props).props.children.find(child=>child?.type==='input');
  input.props.onBlur();assert.equal(touched,true);
  let html=render(GroupSizeField,{...props,revealValidation:touched});
  assert.match(html,/aria-invalid="true"/);assert.match(html,/请填写小组人数/);
  touched=false;input.props.onInvalid();assert.equal(touched,true);
  input.props.onChange({target:{value:'3'}});assert.equal(changed,'3');
  html=render(GroupSizeField,{...props,value:changed,error:undefined,revealValidation:true});
  assert.doesNotMatch(html,/field-error|请填写小组人数/);
  assert.match(html,/aria-invalid="false"/);
});
test('explicit correction guidance is retained even before interacting with the group field',()=>{
  const html=render(GroupSizeField,{value:'',guidance:'请补充本次同行人数。',revealValidation:false,onTouch(){},onChange(){}});
  assert.match(html,/aria-invalid="true"/);assert.match(html,/请补充本次同行人数/);
});

test('logged-in plan-list start action begins with profile, not request confirmation',()=>{
  const html=routed(NewPlanPrompt,{});
  assert.match(html,/<a[^>]*href="\/profile"[^>]*>开始规划/);
  assert.doesNotMatch(html,/href="\/request"/);
  assert.match(html,/先完善同行、交通和装备资料/);
});
test('home and fallback start links also follow profile-first onboarding',()=>{
  for(const route of ['/','/missing-page']){
    const html=renderToStaticMarkup(h(MemoryRouter,{initialEntries:[route]},h(App)));
    const startLinks=html.match(/<a\b[^>]*>开始规划[^<]*(?:<span>[^<]*<\/span>)?<\/a>/g)??[];
    assert.equal(startLinks.length,1,route);
    assert.match(startLinks[0],/href="\/profile"/);
  }
});

test('tent component shows total accommodation capacity, not one tent per camper',()=>{
  const text=render(panels.TentCapacityPanel,{value:tent});
  for(const expected of ['3 人同行','2 顶帐篷','每顶可住 1 人','缺少 1 人住宿容量','帐篷数量','每顶容量','检查认可容量'])assert.ok(text.includes(expected),expected);
  assert.doesNotMatch(text,/忽略缺口|强制通过/);
  assert.match(tentSummary({...tent,missing_person_spaces:null}),/尚未确定/);
});
test('mixed tent capacities have separate rows and unconfirmed capacity is not relabelled available',()=>{
  const text=render(panels.TentCapacityPanel,{value:{...tent,records:[...tent.records,{quantity:1,capacity_per_tent:3,total_capacity:3,confirmed:false,unit:'item'}],registered_tent_count:3,registered_capacity:5}});
  assert.match(text,/未核实拥有/);assert.match(text,/登记总容量 5 人/);assert.match(text,/检查认可容量 2 人/);
  assert.equal((text.match(/<tr>/g)||[]).length,3);
});
test('discard only enables for actual changes, reversal removes change, message names changed sections',()=>{
  const saved={group:'3',gear:[{capacity:'1'}],budget:'100'};
  const names={group:'同行人数',gear:'帐篷容量',budget:'预算'};
  assert.deepEqual(changedSections(saved,{...saved},names),[]);
  const sections=changedSections(saved,{...saved,gear:[{capacity:'2'}]},names);
  assert.deepEqual(sections,['帐篷容量']);
  assert.match(discardMessage(sections),/帐篷容量/);assert.doesNotMatch(discardMessage(sections),/预算/);
  assert.match(discardMessage(sections),/不会恢复历史方案，也不会重新检查/);
  assert.match(render(panels.DiscardChanges,{sections:[],onDiscard(){}}),/disabled=""/);
  assert.doesNotMatch(render(panels.DiscardChanges,{sections,onDiscard(){}}),/disabled=""/);
});
test('saving profile explicitly distinguishes original confirmation and unfinished new checks',()=>{
  assert.match(PROFILE_SAVED_NOTICE,/资料已保存/);assert.match(PROFILE_SAVED_NOTICE,/仍采用原先确认/);
  assert.match(PROFILE_SAVED_NOTICE,/尚未采用新资料完成检查/);assert.match(PROFILE_SAVED_NOTICE,/使用最新资料重新规划/);
});
test('ordinary view cannot render diagnostic payload; reviewer has independent diagnostic section',()=>{
  const value={planning:null,assessments:{LOGISTICS:{trace:{requested_model:'private-model',http_attempts:3,usage:{total_tokens:100}}}}};
  assert.equal(render(panels.ModelRunDiagnostics,{allowed:false,value}),'');
  assert.equal(render(panels.ModelRunDiagnostics,{value}),'');
  const text=render(panels.ModelRunDiagnostics,{allowed:true,value});
  assert.match(text,/模型运行诊断/);assert.match(text,/private-model/);assert.match(text,/不属于露营费用/);
});
test('selected model explanation is visible and original provenance stays distinct on reassessment',()=>{
  const text=render(panels.PlanningExplanationPanel,{siteName:'Demo River Flat',currentRunId:'new',
    value:{source_run_id:'old',selected_campsite_id:'demo-river-flat',decision_summary_unverified:'此营地满足安静与交通需求。'},
    reasons:['Registered synthetic region, capacity and known hard constraints match.'],uncertainties:['Recommendation is not booking availability or safety clearance.']});
  assert.match(text,/此营地满足安静与交通需求/);assert.match(text,/原版本生成时/);
  assert.match(text,/已知必须条件/);assert.match(text,/出发前仍需核实安全信息/);
  assert.equal(chineseProse('unknown English explanation'),null); // No invented translation.
});
test('safety reuses structured equipment issue and routes back to equipment without duplicate raw quantities',()=>{
  const item={issue_id:'equipment.tent',code:'EQUIPMENT_SHORTAGE',category:'EQUIPMENT_GAP',item_key:'tent',
    field:'equipment.tent.quantity',target:'PROFILE',action_url:'/profile',current:{records:[]},required:{quantity:'3'},tent_capacity:tent};
  const text=routed(LogisticsIssues,{items:[item],summary:true,onSafety(){},onGear(){}});
  assert.match(text,/缺少 1 人住宿容量/);assert.match(text,/还有 1 项准备需要完善/);assert.match(text,/查看并补充装备/);
  assert.doesNotMatch(text,/所需数量：3|3 顶帐篷/);
});
test('weather shows missing dates, actions, next recheck and never claims overall safety',()=>{
  const value={checked_on:'2026-10-21',next_weather_check_on:'2026-10-25',issues:[{campsite_id:'demo-river-flat',kind:'WEATHER',code:'NOT_YET_OBSERVED',requested_range:{start:'2026-11-01',end:'2026-11-02'},uncovered_ranges:[{start:'2026-11-01',end:'2026-11-02'}],available_ranges:[]}],alternative_dates:[],alternative_campsites:[]};
  const text=routed(TripCoveragePanel,{value,requestId:'request'});
  for(const expected of ['2026-11-01 至 2026-11-02','2026-10-25','重新检查天气','待确认日期'])assert.ok(text.includes(expected),expected);
  assert.doesNotMatch(text,/资料覆盖|检查通过|天气温和/);
  assert.equal(evidenceState({status:'AVAILABLE',valid_from:'2026-10-01',valid_to:'2026-11-01',source_refs:[]},{start_date:'2026-10-21',end_date:'2026-10-22'}).title,'资料覆盖本次日期');
});

test('safety preparation summary groups repeated issues by item and keeps distinct equipment',()=>{
  const base={issue_id:'tent.quantity',code:'EQUIPMENT_SHORTAGE',item_key:'tent',field:'equipment.tent.quantity',tent_capacity:tent};
  const items=[base,{...base,issue_id:'tent.confirmed',code:'EQUIPMENT_DETAILS'},
    {...base,issue_id:'water',item_key:'drinking_water',field:'equipment.drinking_water',tent_capacity:undefined}];
  const before=structuredClone(items);
  const text=routed(LogisticsIssues,{items,summary:true,onSafety(){},onGear(){}});
  assert.match(text,/还有 2 项准备需要完善/);assert.equal((text.match(/<li>/g)||[]).length,2);
  assert.match(text,/饮用水/);assert.match(text,/缺少 1 人住宿容量/);
  assert.equal((text.match(/<button/g)||[]).length,1);
  assert.doesNotMatch(text,/→|拟购买或借用|暂不能保存最终方案/);assert.deepEqual(items,before);
});

const safetyEvidence=(kind,extra={})=>({kind,status:'AVAILABLE',summary:null,road_state:null,source_date:'2026-10-20',
  valid_from:'2026-10-20',valid_to:'2026-11-30',source_refs:[],...extra});
test('condition cards require concrete facts, inspect all evidence and preserve closures and uncertainty',()=>{
  const dates={start_date:'2026-10-22',end_date:'2026-10-24'};
  const open=safetyEvidence('ROAD',{road_state:'OPEN'});
  assert.equal(safetyCondition('ROAD','AVAILABLE',[open],dates).title,'道路可通行');
  assert.equal(safetyCondition('ROAD','AVAILABLE',[open,{...open,road_state:'CLOSED'}],dates).title,'道路关闭');
  assert.equal(safetyCondition('ROAD','AVAILABLE',[open,{...open,valid_to:'2026-10-23'}],dates).title,'待确认');
  assert.equal(safetyCondition('ROAD','AVAILABLE',[{...open,road_state:'UNKNOWN'}],dates).title,'待确认');
  assert.equal(safetyCondition('ROAD','CONFLICTING',[open],dates).attention,true);
  assert.equal(safetyCondition('WEATHER','AVAILABLE',[safetyEvidence('WEATHER',{summary:'Unrecognised forecast.'})],dates).title,'天气待确认');
  assert.equal(safetyCondition('WEATHER','MISSING',[safetyEvidence('WEATHER',{summary:'Mild synthetic conditions.'})],dates).title,'待确认');
  assert.equal(safetyCondition('WEATHER','AVAILABLE',[safetyEvidence('WEATHER',{summary:'Mild synthetic conditions.'})],dates).title,'天气温和');
  const fire=safetyCondition('FIRE','AVAILABLE',[safetyEvidence('FIRE',{summary:'No synthetic fire restriction.'})],dates);
  assert.equal(fire.title,'未注明额外限制');assert.doesNotMatch(fire.title,/允许|通过/);
  assert.equal(safetyCondition('FIRE','AVAILABLE',[],dates,['FIRE_PROHIBITED']).attention,true);
  assert.equal(safetyCondition('RESTRICTION','AVAILABLE',[],dates,['CAMPSITE_CLOSED']).title,'营地关闭');
  assert.equal(safetyRegulations('Campfires and solid fuel burners prohibited; gas/electric barbecues provided'),'禁止营火及固体燃料炉具；提供燃气或电烧烤设施');
});

test('safety page folds useful rules, omits coverage explanations and restricts diagnostics to review',()=>{
  const value={outcome:'REVISION',risk_level:'LOW',confidence:'HIGH',requires_human_review:false,
    data_quality:{ROAD:'AVAILABLE',FIRE:'AVAILABLE',WEATHER:'AVAILABLE',RESTRICTION:'AVAILABLE'},
    evidence:[safetyEvidence('ROAD',{road_state:'OPEN'}),safetyEvidence('FIRE',{summary:'No synthetic fire restriction.'}),
      safetyEvidence('WEATHER',{summary:'Mild synthetic conditions.'}),safetyEvidence('RESTRICTION',{summary:'Bring all drinking water; Keep noise down after 10pm'})],
    mandatory_blockers:[],hazards:[],unresolved_conflicts:[],recommended_actions:['private-rule-action']};
  const props={value,summary:'装备与交通准备待完善',approved:false,review:false,outdated:false,blockers:null,notes:null,
    rawWarnings:[{code:'INTERNAL_CODE',message:'internal-diagnostic'}],sources:()=>h('p',null,'private-source-record'),label:x=>x,
    coverage:{issues:[]},requestId:'request'};
  const html=render(SafetyInformation,props);
  for(const text of ['道路可通行','天气温和','未注明额外限制','自备全部饮用水','晚上 10 点后保持安静'])assert.ok(html.includes(text),text);
  assert.match(html,/<details class="artifact-notes"><summary>查看安全详情与营地规定/);
  assert.doesNotMatch(html,/资料覆盖|最终资格|接下来可以怎么做|synthetic|完整检查说明|INTERNAL_CODE|private-source-record|private-rule-action|internal-diagnostic/);
  const reviewer=render(SafetyInformation,{...props,review:true});
  assert.match(reviewer,/INTERNAL_CODE/);assert.match(reviewer,/private-source-record/);
  assert.equal(render(TripCoveragePanel,{value:{issues:[]}}),'');
});

test('plan explains preparation-only blockers without disguising a road closure as a gear issue',()=>{
  const value=planFixture();
  const safety={outcome:'REVISION',risk_level:'LOW',confidence:'HIGH',requires_human_review:false,
    data_quality:{},evidence:[],mandatory_blockers:[{code:'ESSENTIAL_GEAR_MISSING',message:'internal-gear-detail',source_refs:[]}],
    hazards:[],unresolved_conflicts:[],recommended_actions:[]};
  value.assessments.push({assessment_id:'safety',kind:'SAFETY',version_context:value.version.version_context,result:safety});
  const html=renderPlan(value);
  assert.match(html,/装备与交通准备待完善/);assert.match(html,/查看装备与交通/);
  assert.doesNotMatch(html,/internal-gear-detail/);
  safety.evidence=[safetyEvidence('ROAD',{road_state:'CLOSED'})];
  safety.mandatory_blockers.push({code:'ROAD_CLOSED',message:'internal-road-detail',source_refs:[]});
  const closed=renderPlan(value);
  assert.match(closed,/道路关闭，需要调整方案/);assert.match(closed,/查看安全信息/);
  assert.doesNotMatch(closed,/装备与交通准备待完善|internal-road-detail/);
});
test('new pending checks override old successful display and completed issues have distinct labels',()=>{
  const row={run_status:'RUNNING',stage:'ASSESSING_SAFETY',version_status:'FINALISED',display_status:'FINALISED'};
  assert.equal(planRowState(row),'正在准备方案');
  for(const [key,label] of Object.entries({NEEDS_USER_INPUT:'需要用户补充',NEEDS_REVISION:'需要修改方案',AWAITING_REVIEW:'等待人工审核',CANNOT_RELEASE:'需要调整方案'}))
    assert.equal(planRowState({...row,run_status:'SUCCEEDED',display_status:key}),label);
});

function planFixture(){
  const version_context={plan_id:'plan',plan_version_id:'version',run_id:'run',input_fingerprint:'saved-fingerprint'};
  const artifact={execution_mode:'deterministic_demo',source_refs:[],assumptions:[],uncertainties:[]};
  const logistics={...artifact,outcome:'REVISION',transport_feasible:true,gear_checklist:[{item_key:'tent',required_quantity:'3',available_quantity:'2',missing_quantity:'1',unit:'person_space',capacity_requirement:3,arrangement_status:'UNCONFIRMED',essential:true}],cost_breakdown:[],total_cents:null,known_subtotal_cents:0,budget_difference_cents:null,mandatory_blockers:[],clarifications:[]};
  return {plan:{plan_id:'plan',request_id:'request',active_run_id:'run',created_at:'2026-10-21T08:00:00Z'},
    run:{run_id:'run',status:'SUCCEEDED',stage:'COMPLETED',operation:'PLAN',is_active:false,created_at:'2026-10-21T08:00:00Z'},
    version:{version_number:1,status:'REVISION_REQUIRED',revision:1,version_context,content:{...artifact,selected_campsite_ids:['demo-river-flat'],itinerary_entries:[{entry_kind:'CAMP',start_at:'2026-10-22T14:00:00+11:00',end_at:'2026-10-23T10:00:00+11:00',campsite_id:'demo-river-flat',description:'Synthetic overnight stay at Demo River Flat; no booking implied.'}]}},
    confirmed_context:{request_id:'request',requirements:{destination:'Demo Region',start_date:'2026-10-22',end_date:'2026-10-23',duration_nights:1,duration_days:2,budget_cents:30000},profile_snapshot:{group_size:3,experience_level:'BEGINNER',has_children:false,children_count:0,equipment:[],transport:{transport_type:'CAR',vehicle_count:1,estimated_km:'100',assumptions:[]},accessibility_requirements:[]},dataset_context:{dataset_version:'2.1.0',rules_version:'saved'}},
    assessments:[{assessment_id:'logistics',kind:'LOGISTICS',version_context,result:logistics}],events:[],reviews:[],run_history:[],final_history:[],route:null,eligibility:null,finalisation_available:false,last_final:null,
    tent_capacity:tent,logistics_issues:[],can_view_model_diagnostics:false};
}
const renderPlan=(data,options={})=>renderToStaticMarkup(h(MemoryRouter,null,h(SessionProvider,null,h(PlanView,{data,error:'',refresh(){},...options}))));
test('plan budget action follows revision capability and is absent from historical, final and review views',()=>{
  const value=planFixture();value.run.is_active=true;value.revision_available=true;value.reassessment_available=true;
  value.current_version_revision=1;value.logistics_issues=[budgetIssue];
  value.assessments[0].result.total_cents=34600;value.assessments[0].result.budget_difference_cents=4600;
  const html=renderPlan(value);
  assert.match(html,/保持预算，寻找更低费用方案/);assert.match(html,/修改行程或更新检查/);
  const forbidden=structuredClone(value);forbidden.revision_available=false;forbidden.display_status='NEEDS_REVISION';
  assert.doesNotMatch(renderPlan(forbidden),/保持预算，寻找更低费用方案/);
  for(const options of [{snapshot:true},{review:true}])
    assert.doesNotMatch(renderPlan(value,options),/保持预算，寻找更低费用方案/);
  for(const change of [v=>{v.run.is_active=false;},v=>{v.run.status='RUNNING';},v=>{v.trip_series={is_current:false};}]){
    const changed=structuredClone(value);change(changed);
    assert.doesNotMatch(renderPlan(changed),/保持预算，寻找更低费用方案/);
  }
});
test('historical and final plan components use saved tent facts and mark all suggested itinerary times',()=>{
  for(const snapshot of [false,true]){
    const html=renderPlan(planFixture(),{snapshot});
    assert.match(html,/缺少 1 人住宿容量/);assert.match(html,/建议时间／待确认/);
    assert.match(html,/不是已核实的入住、退房或交通时刻/);
    assert.doesNotMatch(html,/模型运行诊断|恢复已保存字段/);
    if(!snapshot)assert.match(html,/正在查看历史方案/);
  }
});
test('running new check keeps previous final but never displays its status as this check result',()=>{
  const value=planFixture();value.run={...value.run,is_active:true,status:'RUNNING',operation:'REASSESS'};
  value.version.status='FINALISED';value.last_final={plan_id:'plan',final_id:'old',is_current:true};
  const html=renderPlan(value);
  assert.match(html,/plan-status-neutral/);assert.match(html,/此前最终方案已保留，本次检查尚未完成/);
  assert.match(html,/正在重新检查/);
  assert.match(html,/<h2>本次检查尚未完成<\/h2>/);
});
test('review component alone renders authorised diagnostic payload separate from equipment/budget advice',()=>{
  const value=planFixture();value.can_view_model_diagnostics=true;
  value.model_diagnostics={planning:null,assessments:{SAFETY:{trace:{requested_model:'reviewer-private-model'}}}};
  const html=renderPlan(value,{review:true});assert.match(html,/模型运行诊断/);assert.match(html,/reviewer-private-model/);
  value.can_view_model_diagnostics=false;
  assert.doesNotMatch(renderPlan(value),/reviewer-private-model|模型运行诊断/);
});


test('finalised current read keeps its saved approval but never authorises a new run or version',()=>{
  const value=planFixture();value.run.is_active=true;value.version.status='FINALISED';
  value.reviews=[{review_id:'approved-review',decision:'APPROVE',reason:'saved review',reviewer_user_id:'founder'}];
  value.last_final={plan_id:'plan',final_id:'final',is_current:true,run_id:'run',plan_version_id:'version'};
  value.assessments.push({assessment_id:'safety',kind:'SAFETY',version_context:value.version.version_context,result:{outcome:'REVIEW',requires_human_review:true,risk_level:'HIGH',confidence:'LOW',data_quality:{},evidence:[],hazards:[],recommended_actions:[],mandatory_blockers:[],unresolved_conflicts:[]}});
  assert.match(renderPlan(value),/审核已批准/);
  for(const patch of [{run_id:'older-run'},{plan_version_id:'older-version'},{is_current:false}]){
    const changed=structuredClone(value);Object.assign(changed.last_final,patch);
    assert.doesNotMatch(renderPlan(changed),/审核已批准/);
  }
  const newer=structuredClone(value);newer.run.status='RUNNING';
  assert.doesNotMatch(renderPlan(newer),/审核已批准/);
});


function reviewedFixture(){
  const v=planFixture();v.run.is_active=true;
  v.assessments.push({assessment_id:'safety',kind:'SAFETY',version_context:v.version.version_context,result:{outcome:'REVIEW',requires_human_review:true,risk_level:'HIGH',confidence:'LOW',data_quality:{ROAD:'AVAILABLE'},evidence:[],hazards:[],recommended_actions:[],mandatory_blockers:[],unresolved_conflicts:[]}});
  return v;
}
test('closed-road review route displays adjustment guidance without asking for approval',()=>{
  const v=reviewedFixture();v.version.status='ESCALATED';v.display_status='CANNOT_RELEASE';
  v.assessments[1].result.evidence=[{kind:'ROAD',road_state:'CLOSED',status:'AVAILABLE',source_refs:[]}];
  v.eligibility={eligible:false,review_required:true,valid_review_id:null,blocking_reasons:[{code:'ROAD_UNAVAILABLE',message:'blocked'}]};
  const html=renderPlan(v);
  assert.match(html,/需要调整方案/);assert.match(html,/道路关闭，需要调整方案/);
  assert.match(html,/请更换可通行的营地/);assert.doesNotMatch(html,/无法确认行程期间道路/);
  assert.doesNotMatch(html,/等待审核员处理|等待人工审核|这份方案需要审核员核对风险/);
  assert.equal(v.finalisation_available,false);
});
test('historical approval is labelled as past and never becomes current eligibility',()=>{
  const v=reviewedFixture();v.version.status='FINALISED';v.trip_series={is_current:false,current_plan_id:'successor'};
  v.reviews=[{review_id:'past',decision:'APPROVE',reason:'past reason',reviewer_user_id:'founder',version_context:{...v.version.version_context}}];
  v.final_history=[{plan_id:'plan',final_id:'past-final',run_id:'run',plan_version_id:'version',is_current:false}];
  let html=renderPlan(v);assert.match(html,/当时审核已批准/);assert.match(html,/旧审核不授权新结果/);
  assert.doesNotMatch(html,/安全评估 需要审核/);assert.equal(v.eligibility,null);assert.equal(v.finalisation_available,false);
  for(const change of [{run_id:'new-run'},{plan_version_id:'new-version'},{input_fingerprint:'new-input'}]){
    const different=structuredClone(v);Object.assign(different.reviews[0].version_context,change);
    assert.doesNotMatch(renderPlan(different),/当时审核已批准/);
  }
  const newer=structuredClone(v);newer.version.status='ESCALATED';newer.run.operation='REASSESS';
  assert.doesNotMatch(renderPlan(newer),/当时审核已批准/);
});

test('login and profile no longer offer sample credentials or sample-filled personal facts',()=>{
  const html=renderToStaticMarkup(h(MemoryRouter,null,h(SessionProvider,null,h(LoginPage))));
  assert.doesNotMatch(html,/示例账户|camper\.a|camper\.b|CampMate-Founder|demo-accounts/);
  assert.match(html,/注册账户/);assert.match(html,/login-layout/);
  const profile=readFileSync(new URL('../src/profile.tsx',import.meta.url),'utf8');
  assert.doesNotMatch(profile,/想先体验|载入资料样例|demoInputs|loadDemo|demoAvailable/);
  assert.doesNotMatch(profile,/EquipmentSaveNotice|equipment-save-notice|数量请填写本次实际可用的装备/);
  assert.doesNotMatch(profile,/已核实拥有<\/label>/);
});
test('required fields have visible text badges without making optional profile facts mandatory',()=>{
  for(const [Page,ids] of [[RegisterPage,['register-username','register-password','register-confirmation']]]){
    const html=renderToStaticMarkup(h(MemoryRouter,null,h(SessionProvider,null,h(Page))));
    assert.doesNotMatch(html,/register-name|昵称/);
    for(const id of ids){
      assert.ok(html.includes(`<label for="${id}">`),id);
      assert.match(html.split(`<label for="${id}">`)[1].split('</label>')[0],/class="required-mark">必填/);
    }
  }
  const css=readFileSync(new URL('../src/styles.css',import.meta.url),'utf8');
  assert.match(css,/\.required-mark\{[^}]*font-size:12px;[^}]*font-weight:700/);
  const profile=readFileSync(new URL('../src/profile.tsx',import.meta.url),'utf8');
  assert.match(profile,/htmlFor=\{`gear-name-\$\{index\}`\}>名称<\/label>/);
  assert.match(profile,/aria-label=\{`装备 \$\{index\+1\} 名称`\} required/);
  const login=renderToStaticMarkup(h(MemoryRouter,null,h(SessionProvider,null,h(LoginPage))));
  assert.doesNotMatch(login,/required-mark/);assert.match(login,/required=""/);
  assert.match(profile,/equipment: equipmentPayload\(equipment\)/);
});
