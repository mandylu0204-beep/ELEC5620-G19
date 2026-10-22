import test, {after} from 'node:test';
import assert from 'node:assert/strict';
import {createElement as h} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {MemoryRouter} from 'react-router-dom';
import {createServer} from 'vite';
import {changedSections,discardMessage,tentSummary,PROFILE_SAVED_NOTICE,chineseProse} from '../src/display_facts.ts';
import {evidenceState,planRowState} from '../src/plan_language.ts';

// Vite only transforms modules in middleware mode: no HTTP listener, browser,
// app database, personal env file or model client is started by these tests.
const server=await createServer({configFile:false,envDir:false,appType:'custom',
  server:{middlewareMode:true,hmr:false,watch:null},optimizeDeps:{noDiscovery:true}});
after(()=>server.close());
const panels=await server.ssrLoadModule('/src/display_panels.tsx');
const {LogisticsIssues}=await server.ssrLoadModule('/src/logistics_issues.tsx');
const {TripCoveragePanel}=await server.ssrLoadModule('/src/trip_coverage.tsx');
const {PlanView,NewPlanPrompt,TripSeriesCard}=await server.ssrLoadModule('/src/plans.tsx');
const {ProfileAdoptionPreview}=await server.ssrLoadModule('/src/replan.tsx');
const {historicalReviewNotice}=await server.ssrLoadModule('/src/reviews.tsx');
const {profileChanges}=await server.ssrLoadModule('/src/profile_changes.ts');
const {App}=await server.ssrLoadModule('/src/App.tsx');
const {GroupSizeField,EquipmentUnitField,addEquipment,changeEquipmentCategory,fixedEquipmentUnit,ProfileSummary}=await server.ssrLoadModule('/src/profile.tsx');
const {SessionProvider}=await server.ssrLoadModule('/src/session.tsx');
const render=(component,props)=>renderToStaticMarkup(h(component,props));
const routed=(component,props)=>renderToStaticMarkup(h(MemoryRouter,null,h(component,props)));
const tent={records:[{quantity:2,capacity_per_tent:1,total_capacity:2,confirmed:true,unit:'item'}],
  group_size:3,registered_tent_count:2,registered_capacity:2,assessed_capacity:'2',required_person_spaces:'3',missing_person_spaces:'1'};

const gear=(patch={})=>({item_key:'tent',label:'帐篷',quantity:'2',unit:'item',capacity:'3',confirmed:true,...patch});
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
  assert.match(text,/已知必须条件/);assert.match(text,/不代表安全放行/);
  assert.equal(chineseProse('unknown English explanation'),null); // No invented translation.
});
test('safety reuses structured equipment issue and routes back to equipment without duplicate raw quantities',()=>{
  const item={issue_id:'equipment.tent',code:'EQUIPMENT_SHORTAGE',category:'EQUIPMENT_GAP',item_key:'tent',
    field:'equipment.tent.quantity',target:'PROFILE',action_url:'/profile',current:{records:[]},required:{quantity:'3'},tent_capacity:tent};
  const text=routed(LogisticsIssues,{items:[item],summary:true,onSafety(){},onGear(){}});
  assert.match(text,/缺少 1 人住宿容量/);assert.match(text,/暂不能保存最终方案/);assert.match(text,/查看装备问题与补充入口/);
  assert.doesNotMatch(text,/所需数量：3|3 顶帐篷/);
});
test('weather shows missing dates, actions, next recheck and never claims overall safety',()=>{
  const value={checked_on:'2026-10-21',next_weather_check_on:'2026-10-25',issues:[{campsite_id:'demo-river-flat',kind:'WEATHER',code:'NOT_YET_OBSERVED',requested_range:{start:'2026-11-01',end:'2026-11-02'},uncovered_ranges:[{start:'2026-11-01',end:'2026-11-02'}],available_ranges:[]}],alternative_dates:[],alternative_campsites:[]};
  const text=routed(TripCoveragePanel,{value,requestId:'request'});
  for(const expected of ['2026-11-01 至 2026-11-02','2026-10-25','影响：','处理：','不能据此确认整段行程安全'])assert.ok(text.includes(expected),expected);
  assert.equal(evidenceState({status:'AVAILABLE',valid_from:'2026-10-01',valid_to:'2026-11-01',source_refs:[]},{start_date:'2026-10-21',end_date:'2026-10-22'}).title,'资料覆盖本次日期');
});
test('new pending checks override old successful display and completed issues have distinct labels',()=>{
  const row={run_status:'RUNNING',stage:'ASSESSING_SAFETY',version_status:'FINALISED',display_status:'FINALISED'};
  assert.equal(planRowState(row),'正在准备方案');
  for(const [key,label] of Object.entries({NEEDS_USER_INPUT:'需要用户补充',NEEDS_REVISION:'需要修改方案',AWAITING_REVIEW:'等待人工审核',CANNOT_RELEASE:'不能放行'}))
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
