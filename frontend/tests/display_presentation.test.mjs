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
const {PlanView}=await server.ssrLoadModule('/src/plans.tsx');
const {SessionProvider}=await server.ssrLoadModule('/src/session.tsx');
const render=(component,props)=>renderToStaticMarkup(h(component,props));
const routed=(component,props)=>renderToStaticMarkup(h(MemoryRouter,null,h(component,props)));
const tent={records:[{quantity:2,capacity_per_tent:1,total_capacity:2,confirmed:true,unit:'item'}],
  group_size:3,registered_tent_count:2,registered_capacity:2,assessed_capacity:'2',required_person_spaces:'3',missing_person_spaces:'1'};

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
  value.version.status='FINALISED';value.last_final={final_id:'old',is_current:true};
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
