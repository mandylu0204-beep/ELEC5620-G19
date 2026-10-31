import {englishSavedReason} from '../src/legacy_filter_reasons.ts';
import test, {after} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createElement as h} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {MemoryRouter} from 'react-router-dom';
import {createServer} from 'vite';
import {changedSections,discardMessage,tentSummary,PROFILE_SAVED_NOTICE,displayProse} from '../src/display_facts.ts';
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
const {FinalPlanNavigation}=await server.ssrLoadModule('/src/finals.tsx');
const {revisionReview}=await server.ssrLoadModule('/src/review_revision.ts');
const {AssistanceNotes,ReviewAssistanceForm}=await server.ssrLoadModule('/src/review_assistance.tsx');
const {FinalPdfDownload}=await server.ssrLoadModule('/src/final_pdf.tsx');
const {DailyItinerary}=await server.ssrLoadModule('/src/daily_itinerary.tsx');
const {selectionPresentation,selectedRequirementsPresentation}=await server.ssrLoadModule('/src/campsite_selection.ts');
const {cataloguePlace,CampsiteArrivalDetails}=await server.ssrLoadModule('/src/campsite_details.tsx');
const {ChangePlanning,revealRevisionPanel,preservedRevisionNotice}=await server.ssrLoadModule('/src/planning.tsx');
const {ApiFailure:PlanningApiFailure}=await server.ssrLoadModule('/src/api.ts');
const {RevisionComparison,savingsText}=await server.ssrLoadModule('/src/revision_comparison.tsx');
const {ProfileAdoptionPreview}=await server.ssrLoadModule('/src/replan.tsx');
const {RequirementsChangePreview,RequestHistory}=await server.ssrLoadModule('/src/requests.tsx');
const {historicalReviewNotice}=await server.ssrLoadModule('/src/reviews.tsx');
const {profileChanges}=await server.ssrLoadModule('/src/profile_changes.ts');
const {App}=await server.ssrLoadModule('/src/App.tsx');
const {GroupSizeField,EquipmentUnitField,addEquipment,changeEquipmentCategory,fixedEquipmentUnit,ProfileSummary,ProfileCorrectionStatus,TransportModeField,PublicTransportNotice}=await server.ssrLoadModule('/src/profile.tsx');
const {VehicleFields}=await server.ssrLoadModule('/src/vehicle_fields.tsx');
const {SessionProvider,LoginPage}=await server.ssrLoadModule('/src/session.tsx');
const {RegisterPage}=await server.ssrLoadModule('/src/register.tsx');
const {CookingPreparationPanel,cookingDraft,canHideCookingPreparation}=await server.ssrLoadModule('/src/cooking_preparation.tsx');
const {TripPreparation}=await server.ssrLoadModule('/src/trip_preparation.tsx');
const {NearMatches}=await server.ssrLoadModule('/src/near_matches.tsx');
const {prepareProfileEquipment}=await server.ssrLoadModule('/src/vehicle_profile.ts');
const {profileGuidance:preparationGuidance}=await server.ssrLoadModule('/src/profile_guidance.ts');
const {profileFocusId:preparationFocus}=await server.ssrLoadModule('/src/profile_focus.ts');
const render=(component,props)=>renderToStaticMarkup(h(component,props));
const routed=(component,props)=>renderToStaticMarkup(h(MemoryRouter,null,h(component,props)));
test('system preparation removes artificial inventory prerequisites while preserving old registered facts',()=>{
  assert.deepEqual(prepareProfileEquipment([],'PUBLIC_TRANSPORT','',true),[]);
  const legacy=[{item_key:'transport_itinerary',label:'Original plan',quantity:'1',unit:'plan',capacity:'',confirmed:true}];
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
  assert.match(html,/<option value="" disabled="" hidden="" selected="">Choose a transport mode/i);
  assert.doesNotMatch(html,/Not yet specified|class="mode-notice"|Check outbound travel yourself|Fixed demonstration origin/i);
  assert.doesNotMatch(html,/<option value="CAR" selected/i);
});
test('saved preparation keeps trip figures without technical explanatory prose',()=>{
  const value={system_preparation:true,transport_type:'CAR',origin_label:'Central Sydney (fixed demonstration origin)',
    access_and_capacity:true,estimated_total_vehicle_km:'200',vehicle_count:2,estimated_transport_cents:7600,meal_mode:'SELF_CATERED',source_refs:[{dataset_file:'transport-reference',record_id:'transport-test',provenance:{source_date:'2026-10-28'}}]};
  const before=structuredClone(value);const html=render(TripPreparation,{value});
  for(const text of ['200 km','2 vehicles','76.00','verify stove, fuel and cookware'])assert.ok(html.includes(text),text);
  assert.match(html,/Departure point: Sydney CBD./i);
  assert.doesNotMatch(html,/Fixed demonstration origin|Combined distance from versioned distance table |ready-to-eat meals or self-caterings remain subject to formal equipment checks|Simulated distance source|transport-test/i);
  assert.deepEqual(value,before);
  const transit=render(TripPreparation,{value:{...value,transport_type:'PUBLIC_TRANSPORT',estimated_transport_cents:null}});
  assert.match(transit,/Unknown; cannot be treated as zero cost/i);assert.match(transit,/Outbound, last return/i);
  assert.doesNotMatch(transit,/Combined distance (simulated)|Confirmed vehicles for this trip/i);
  const ready=render(TripPreparation,{value:{...value,meal_mode:'READY_TO_EAT'}});
  assert.match(ready,/<dt>Meal arrangement<\/dt><dd>Ready-to-eat meals<\/dd>/i);
  assert.doesNotMatch(ready,/Fire-free meal plan|No registration needed/i);
});
test('no-match adjustment is an explicit user choice, disabled in read-only history',()=>{
  const value={near_matches:[],excluded_count:10,ranking:'test',metadata_note:null,scope:'SAVED'};
  const html=routed(NearMatches,{value,planId:'trip-1'});
  assert.match(html,/The system will not change confirmed requirements for you/i);
  assert.match(html,/href="\/profile\?plan_id=trip-1&amp;focus=transport.transport_type"/i);
  assert.match(html,/href="\/plans\/trip-1\/update"/i);
  assert.doesNotMatch(routed(NearMatches,{value,planId:'trip-1',readOnly:true}),/href=|<button/i);
});
test('new summaries hide irrelevant mileage and keep old virtual plans explicitly historical',()=>{
  const profile={group_size:2,experience_level:'BEGINNER',has_children:false,children_count:0,accessibility_requirements:[],
    transport:{transport_type:'PUBLIC_TRANSPORT',vehicle_count:1,estimated_km:'999',assumptions:['Original transport notes']},
    equipment:[{item_key:'transport_itinerary',label:'Original transport plan',quantity:1,unit:'plan',capacity_persons:null,confirmed:true}]};
  const before=structuredClone(profile);
  const modern=render(ProfileSummary,{profile,systemPreparation:true});
  assert.match(modern,/Legacy plan registrations \(historical reference only\)/i);
  assert.match(modern,/These records are not used as equipment or access evidence for this run/i);
  assert.doesNotMatch(modern,/999|Number of vehicles|Vehicles \/ Total distance|Transport estimate assumptions/i);
  const legacy=render(ProfileSummary,{profile});
  assert.match(legacy,/999|Transport estimate assumptions/i);assert.doesNotMatch(legacy,/Legacy plan registration records/i);
  assert.deepEqual(profile,before);
});
const budgetIssue={issue_id:'budget',code:'OVER_BUDGET',category:'USER_INPUT',field:'budget_cents',item_key:null,
  current:34600,required:30000,target:'REQUEST',action_url:'/plans/plan/update?focus=request-budget'};
test('over-budget task separates lower-cost preparation from changing the confirmed budget',()=>{
  const calls=[];const props={items:[structuredClone(budgetIssue)],onSafety(){},onRevisionRequested:goal=>calls.push(goal)};
  const before=structuredClone(props.items);
  const html=routed(LogisticsIssues,props);
  assert.match(html,/Keep budget and look for a lower-cost plan/i);assert.match(html,/Adjust this trip budget/i);
  assert.match(html,/href="\/plans\/plan\/update\?focus=request-budget"/i);
  assert.match(html,/Execution starts only after confirmation/i);assert.match(html,/This does not guarantee the total fits the budget/i);
  assert.match(html,/AUD 346\.00/i);assert.match(html,/AUD 300\.00/i);
  const buttons=[];
  function walk(node){
    if(Array.isArray(node)){node.forEach(walk);return;}
    if(!node||typeof node!=='object')return;
    if(node.type==='button')buttons.push(node);
    walk(node.props?.children);
  }
  walk(LogisticsIssues(props));
  buttons.find(node=>node.props.children==='Keep budget and look for a lower-cost plan').props.onClick();
  assert.deepEqual(calls,['cheaper campsite']); // Prepares the existing goal, no command submission.
  assert.deepEqual(props.items,before);
});
test('history and unavailable revision never offer an active lower-cost action',()=>{
  const props={items:[budgetIssue],onSafety(){},onRevisionRequested(){}};
  assert.doesNotMatch(routed(LogisticsIssues,{...props,disabled:true}),/Keep budget and look for a lower-cost plan|href=/i);
  const unavailable=routed(LogisticsIssues,{items:[budgetIssue],onSafety(){}});
  assert.doesNotMatch(unavailable,/Keep budget and look for a lower-cost plan/i);
  assert.match(unavailable,/Campsite revision cannot start now/i);assert.match(unavailable,/Adjust this trip budget/i);
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
  assert.match(html,/<option value="cheaper campsite" selected=""/i);
  for(const text of ['Keep the budget AUD 300.00','Try to find a cheaper campsite','The total may still exceed the budget','Find a cheaper campsite','Compare and choose whether to adopt'])assert.ok(html.includes(text),text);
  assert.deepEqual(data,before);
});

test('no cheaper campsite becomes a preservation notice while auth, stale and model errors remain errors',()=>{
  const envelope={error:{code:'INPUT_INVALID',message:'No cheaper campsite meets the current conditions. The original plan is retained.',
    context:{revision_outcome:'NO_CHEAPER_CAMPSITE'}},trace_id:'test'};
  assert.equal(preservedRevisionNotice(new PlanningApiFailure(envelope)),envelope.error.message);
  assert.equal(preservedRevisionNotice(new PlanningApiFailure({...envelope,error:{...envelope.error,
    context:{revision_outcome:'CAMPSITE_FEE_UNKNOWN'}}})),envelope.error.message);
  for(const code of ['UNAUTHENTICATED','STALE_CONTEXT','VERSION_CONFLICT','CONTRACT_INVALID','AGENT_FAILURE'])
    assert.equal(preservedRevisionNotice(new PlanningApiFailure({...envelope,error:{...envelope.error,code}})),null);
  assert.equal(preservedRevisionNotice(new Error('Connection lost')),null);
  assert.equal(preservedRevisionNotice(new PlanningApiFailure({...envelope,error:{...envelope.error,context:{}}})),null);
});

const comparisonFixture=()=>({proposal_id:'proposal',revision:0,decision:null,status:'READY',can_adopt:true,can_keep:true,
  before:{run:{run_id:'old-run',status:'SUCCEEDED',stage:'COMPLETED',revision:5},version_id:'old-version',version_number:1,
    campsite_ids:['lane-cove'],duration_nights:2,nightly_fee_cents:9500,camp_fee_cents:19000,total_cents:40000},
  after:{run:{run_id:'new-run',status:'SUCCEEDED',stage:'COMPLETED',revision:5},version_id:'new-version',version_number:2,
    campsite_ids:['bonnie-vale'],duration_nights:2,nightly_fee_cents:8500,camp_fee_cents:17000,total_cents:42000},
  camp_saving_cents:2000,total_saving_cents:-2000});
const renderComparison=props=>renderToStaticMarkup(h(MemoryRouter,null,h(SessionProvider,null,h(RevisionComparison,props))));

test('revision comparison distinguishes campsite savings from higher total cost and offers explicit selection',()=>{
  const value=comparisonFixture();const before=structuredClone(value);
  const html=renderComparison({value,planId:'plan',refresh(){}});
  for(const text of ['Lane Cove','Bonnie Vale','AUD 95.00','AUD 85.00','AUD 190.00','AUD 170.00',
    'Campsite fee estimated saving AUD 20.00','Total cost estimated increase AUD 20.00','Use proposed plan','Keep original plan'])assert.ok(html.includes(text),text);
  assert.match(html,/href="\/plans\/plan\?run_id=new-run"/i);
  assert.match(html,/Estimated total cost/i);assert.deepEqual(value,before);
  assert.equal(savingsText(0,'Total cost'),'Total cost unchanged');
});

test('unknown totals are not zero savings; pending, failed and historical comparisons cannot adopt prematurely',()=>{
  const props={planId:'plan',refresh(){}};
  const value=comparisonFixture();value.after.total_cents=null;value.total_saving_cents=null;
  const unknown=renderComparison({...props,value});
  assert.match(unknown,/Total cost cannot yet be compared/i);assert.doesNotMatch(unknown,/Estimated total cost saving AUD 0\.00/i);
  const pending=renderComparison({...props,value:{...value,status:'GENERATING',can_adopt:false,can_keep:false}});
  assert.match(pending,/The original remains the current plan/i);assert.equal((pending.match(/disabled=""/gi)||[]).length,2);
  const failed=renderComparison({...props,value:{...value,status:'FAILED',can_adopt:false}});
  assert.match(failed,/The original is unaffected/i);assert.match(failed,/<button[^>]*disabled=""[^>]*>Use proposed plan/i);
  for(const extra of [{readOnly:true},{value:{...value,decision:'KEEP',status:'KEEP'}}])
    assert.doesNotMatch(renderComparison({...props,value,...extra}),/<button/i);
});

test('selected original stays visible while the save panel waits for a pending revision choice',()=>{
  const value=planFixture();value.run.is_active=true;
  value.revision_comparison=comparisonFixture();
  value.finalisation_available=false;value.revision_available=false;value.reassessment_available=false;
  const html=renderPlan(value);
  assert.match(html,/Demo River Flat/i);assert.match(html,/Choose the plan that suits you/i);
  assert.doesNotMatch(html,/class="panel plan-save"/i);
});

test('an unselected candidate detail is labelled a preview rather than an unrelated historical plan',()=>{
  const value=planFixture();const comparison=comparisonFixture();value.revision_comparison=comparison;
  value.run={...value.run,...comparison.after.run,is_active:false};
  value.plan.active_run_id=comparison.before.run.run_id;value.plan.current_version_id=comparison.before.version_id;
  value.version.version_context={...value.version.version_context,run_id:comparison.after.run.run_id,plan_version_id:comparison.after.version_id};
  value.assessments[0].version_context=value.version.version_context;
  const html=renderPlan(value);
  assert.match(html,/Proposed new plan/i);assert.match(html,/Previewing a new plan; the original remains the current arrangement/i);
  assert.doesNotMatch(html,/Viewing a historical plan/i);assert.match(html,/Back to current plan/i);
});
test('transport choices follow backend capabilities, retain unsupported history and never promise live timetable checks',()=>{
  const props={value:'PUBLIC_TRANSPORT',supported:['CAR','PUBLIC_TRANSPORT'],onChange(){},error:''};
  const html=render(TransportModeField,props);
  assert.match(html,/<option value="CAR"/i);assert.match(html,/<option value="PUBLIC_TRANSPORT"/i);
  assert.doesNotMatch(html,/<option value="WALKING"|<option value="OTHER"/i);
  assert.doesNotMatch(html,/class="mode-notice"|Not yet specified/i);
  const old=render(TransportModeField,{...props,value:'WALKING'});
  assert.match(old,/<option value="WALKING" disabled="" selected=""/i);assert.match(old,/Historical mode; currently unsupported/i);
  const pending=render(TransportModeField,{...props,supported:null});
  assert.match(pending,/<select[^>]*disabled=""/i);
  assert.match(render(PublicTransportNotice,{}),/registered access flags/i);
});
test('connection tasks link to real profile fields while source gaps keep operator-only guidance',()=>{
  const connection=routed(LogisticsIssues,{items:[{issue_id:'connection',code:'TRANSPORT_CONNECTION',target:'PROFILE',
    category:'USER_INPUT',field:'transport.assumptions',action_url:'/profile?focus=transport.assumptions'}],onSafety(){}});
  assert.match(connection,/Public transport return and connection arrangements need checking/i);assert.match(connection,/focus=transport.assumptions/i);
  assert.match(connection,/not booked tickets/i);
  const data=routed(LogisticsIssues,{items:[{issue_id:'access',code:'TRANSPORT_ACCESS_DATA',target:'OPERATOR',
    category:'DATA_GAP',field:'transport.public_transport_access',action_url:null}],onSafety(){}});
  assert.match(data,/Changing personal vehicle quantities cannot resolve/i);assert.doesNotMatch(data,/href=|<button/i);
});
test('completed correction form offers explicit next check without a stale count, dead button or formal pass',()=>{
  const props={ready:true,loading:false,failed:false,targets:[],dirty:false,returnPlan:true};
  const saved=render(ProfileCorrectionStatus,props);
  assert.match(saved,/No missing-field notices remain on this form/i);assert.match(saved,/This does not resolve the original plan issues/i);
  assert.match(saved,/The original plan retains its confirmed profile and check results/i);
  assert.doesNotMatch(saved,/Below \d+ locations|<button|Checks passed|Resolved<|Formal checks completed/i);
  const dirty=render(ProfileCorrectionStatus,{...props,dirty:true});
  assert.match(dirty,/Save changes, then review/i);assert.doesNotMatch(dirty,/Below \d+ locations|<button/i);
  const active=render(ProfileCorrectionStatus,{...props,targets:['gear-quantity-0','gear-capacity-0']});
  assert.match(active,/Below 2 fields/i);assert.match(active,/Go to first field requiring attention/i);
  for(const state of [{loading:true,ready:false},{failed:true,ready:false}]){
    const pending=render(ProfileCorrectionStatus,{...props,targets:['gear-quantity-0'],...state});
    assert.doesNotMatch(pending,/<button|Below 1 locations/i);
  }
});
test('vehicle total guidance highlights the editable vehicle quantity rather than a read-only output',()=>{
  const html=render(VehicleFields,{equipment:[{item_key:'vehicle',quantity:'1',capacity:'5',confirmed:true}],
    issues:{},guidance:{'vehicle-count':'Check the total vehicle count'},onChange(){},onRemove(){},onAdd(){}});
  assert.match(html,/<input[^>]*id="gear-quantity-0"[^>]*aria-invalid="true"/i);
  assert.match(html,/Check the total vehicle count/i);assert.doesNotMatch(html,/id="vehicle-count"|id="gear-unit-0"|type="checkbox"|Confirmed available for this trip/i);
});
test('hero captions stay level while only the mountain illustration is tilted',()=>{
  const css=readFileSync(new URL('../src/styles.css',import.meta.url),'utf8');
  const transforms=selector=>Array.from(css.matchAll(new RegExp(selector+'\\s*\\{([^}]*)\\}','g')))
    .flatMap(match=>Array.from(match[1].matchAll(/(?:^|;)\s*transform\s*:\s*([^;]+)/gi),entry=>entry[1].trim()));
  assert.equal(transforms('\\.hero-art').at(-1),'none');
  assert.equal(transforms('\\.hero-art\\s*>\\s*\\.mountain').at(-1),'rotate(-3deg)');
  const html=routed(App,{});
  assert.match(html,/class="hero-art"><span>Plan clearly, travel confidently<\/span><svg/i);
  assert.match(html,/<\/svg><div>Plan · Check · Review<\/div>/i);
});
const tent={records:[{quantity:2,capacity_per_tent:1,total_capacity:2,confirmed:true,unit:'item'}],
  group_size:3,registered_tent_count:2,registered_capacity:2,assessed_capacity:'2',required_person_spaces:'3',missing_person_spaces:'1'};

const gear=(patch={})=>({item_key:'tent',label:'Tent',quantity:'2',unit:'item',capacity:'3',confirmed:true,...patch});
const preparation={scope:'PREPARATION_ONLY',official_assessment:false,fuel_price_status:'MISSING_REFERENCE',
  items:['camping_stove','fuel_canister'].map(item_key=>({item_key,recorded:false,entered_quantity:null,confirmed_quantity:null,unit_valid:true}))};
test('first cooking preparation names both items without declaring an inactive fuel rule unnecessary or passed',()=>{
  const html=render(CookingPreparationPanel,{value:preparation});
  for(const phrase of ['Cooking equipment preparation','Camping stove','Fuel canister','Quantity not entered'])assert.ok(html.includes(phrase),phrase);
  assert.doesNotMatch(html,/Checks passed|Confirm resolved|href=|<button|Rules precheck|System pricing data|Fabricated entry|No model call|Fuel cost to confirm/i);
  const issue=routed(LogisticsIssues,{items:[{issue_id:'cooking_method',code:'COOKING_ARRANGEMENT',category:'USER_INPUT',target:'REQUEST',
    cooking_preparation:preparation,alternate_action_url:'/profile?plan_id=p&focus=equipment.camping_stove'}],onSafety(){}});
  assert.match(issue,/Check stove and fuel details together/i);assert.match(issue,/Fuel canister/i);
});
test('draft check is explicit and expires on edit; zero estimated gap cannot grant a formal pass',()=>{
  const value={...preparation,required_fuel_quantity:'2',fuel_gap:'0',calculation_status:'DRAFT_ESTIMATE'};
  const html=render(CookingPreparationPanel,{value:preparation,preview:value,onCheck(){}});
  assert.match(html,/Estimated fuel canisters needed 2 items/i);assert.match(html,/Still missing 0 items/i);
  assert.match(html,/Update preparation details/i);assert.doesNotMatch(html,/Checks passed|Resolved|Fuel cost to confirm/i);
  const stale=render(CookingPreparationPanel,{value:preparation,preview:value,stale:true,onCheck(){}});
  assert.match(stale,/Profile changed. Update the preparation details/i);assert.doesNotMatch(stale,/Estimated fuel canisters needed 2 items/i);
  const unknown=render(CookingPreparationPanel,{value:preparation,preview:{...preparation,calculation_status:'WAITING_FOR_STOVE',example:{stove_quantity:1,fuel_quantity:'2'}}});
  assert.match(unknown,/Enter the available stove quantity before confirming fuel requirements/i);assert.doesNotMatch(unknown,/Rule example|Estimated fuel canisters needed|Checks passed/i);
  const shortage=render(CookingPreparationPanel,{value:preparation,preview:{...value,fuel_gap:'1'}});
  assert.match(shortage,/Fuel cost to confirm/i);assert.match(shortage,/Still missing 1 items/i);
  const invalid=render(CookingPreparationPanel,{value:{...preparation,items:[{...preparation.items[0],recorded:true,unit_valid:false}]}});
  assert.match(invalid,/Check quantity units/i);
});
test('cooking preparation survives final/history rendering without offering an active profile update',()=>{
  const data={...planFixture(),cooking_preparation:preparation};
  const history=routed(PlanView,{data,error:'',refresh(){},snapshot:true});
  assert.match(history,/Cooking equipment preparation/i);assert.doesNotMatch(history,/Check stove and fuel details together ↗/i);
  const reviewer=routed(PlanView,{data,error:'',refresh(){},review:true});
  assert.match(reviewer,/Cooking equipment preparation/i);assert.doesNotMatch(reviewer,/Check stove and fuel details together ↗/i);
});
test('cooking candidate preserves unknowns, units, duplicates and confirmation; names never decide item type',()=>{
  const rows=[gear({item_key:'camping_stove',label:'Fuel canister',quantity:'',confirmed:false}),gear({item_key:'fuel_canister',quantity:'2',unit:'set'}),gear()];
  const before=structuredClone(rows);const draft=cookingDraft(rows);
  assert.equal(draft.length,2);assert.equal(draft[0].item_key,'camping_stove');assert.equal(draft[0].quantity,null);assert.equal(draft[0].confirmed,false);
  assert.equal(draft[1].unit,'set');assert.deepEqual(rows,before);
  for(const quantity of ['-1','1.5','1e2','9007199254740992'])assert.throws(()=>cookingDraft([gear({item_key:'camping_stove',quantity})]),/nonnegative whole number/i);
});
test('fuel task explains its own missing quote and offers real correction paths, not a price editor',()=>{
  const item={issue_id:'equipment.fuel_canister',code:'EQUIPMENT_SHORTAGE',category:'EQUIPMENT_GAP',field:'equipment.fuel_canister.quantity',item_key:'fuel_canister',
    current:{records:[],available_quantity:'0'},required:{quantity:'3',missing_quantity:'3'},target:'PROFILE',action_url:'/profile?plan_id=owned-plan&focus=equipment.fuel_canister.quantity',
    arrangement_action_url:'/plans/owned-plan/update?focus=request-meal',cost_impacts:[{code:'PRICE_DATA',item_key:'fuel_canister',category:'ADDITIONAL_GEAR',unit_price_cents:null}]};
  const html=routed(LogisticsIssues,{items:[item],onSafety(){}});
  assert.match(html,/Fuel canister shortage: 3 canisters/i);assert.match(html,/Fuel canister cost is unknown; the full total cannot yet be estimated/i);
  assert.match(html,/Complete Fuel canister/i);assert.match(html,/Adjust meal arrangement/i);
  assert.doesNotMatch(html,/Essential equipment quantity insufficient|Issue:|Impact:|Action:|not a separate unrelated task|<h3>No applicable price reference/i);
  const history=routed(LogisticsIssues,{items:[item],disabled:true,onSafety(){}});
  assert.doesNotMatch(history,/href=/i);assert.match(history,/Only gaps recorded at that time are shown/i);
});
test('dependent checks remain visible before quantities are known and source-only problems have no fake link',()=>{
  const html=routed(LogisticsIssues,{items:[{issue_id:'stove',code:'EQUIPMENT_DETAILS',category:'USER_INPUT',item_key:'camping_stove',target:'PROFILE',action_url:'/profile?focus=equipment.camping_stove',pending_checks:[{item_key:'fuel_canister',status:'WAITING_FOR_INPUT'}]}],onSafety(){}});
  assert.match(html,/Complete, then review: Fuel canister/i);assert.match(html,/required quantity to confirm/i);
  const price=routed(LogisticsIssues,{items:[{issue_id:'price.fuel',code:'PRICE_DATA',category:'DATA_GAP',item_key:'fuel_canister',target:'OPERATOR',action_url:null}],onSafety(){}});
  assert.match(price,/Fuel canister · No applicable price reference/i);assert.doesNotMatch(price,/href=|<button/i);
});

test('equipment task names the saved shortage and a single correction link without repeated instructions',()=>{
  const item={issue_id:'equipment.sleeping_mat',code:'EQUIPMENT_SHORTAGE',category:'EQUIPMENT_GAP',field:'equipment.sleeping_mat.quantity',item_key:'sleeping_mat',
    current:{records:[],available_quantity:'0',unit:'item'},required:{quantity:'2',missing_quantity:'2'},target:'PROFILE',action_url:'/profile?focus=equipment.sleeping_mat.quantity'};
  const before=structuredClone(item);
  const html=routed(LogisticsIssues,{items:[item],onSafety(){}});
  assert.match(html,/<h3>Sleeping mat shortage: 2 mats<\/h3>/i);assert.match(html,/Needed for this trip 2 mats, Not registered yet./i);
  const card=html.slice(html.indexOf('<article'));
  assert.equal((card.match(/<a /g)||[]).length,1);assert.match(card,/Complete Sleeping mat ↗/i);
  assert.match(card,/href="\/profile\?focus=equipment.sleeping_mat.quantity"/i);
  assert.doesNotMatch(card,/Arrangements need changes|Essential equipment quantity insufficient|Issue:|Impact:|Action:|Used for this check|Trip requirement/i);
  assert.deepEqual(item,before);
  assert.doesNotMatch(routed(LogisticsIssues,{items:[item],disabled:true,onSafety(){}}),/href=|<button/i);
});

test('unknown equipment quantity is never zero and unconfirmed stock is not available stock',()=>{
  const item={issue_id:'mat',code:'EQUIPMENT_DETAILS',item_key:'sleeping_mat',target:'PROFILE',action_url:'/profile',
    current:{records:[{quantity:null,unit:'item',confirmed:false}],available_quantity:null,unit:'item'},required:{quantity:'2',missing_quantity:null}};
  const unknown=routed(LogisticsIssues,{items:[item],onSafety(){}});
  assert.match(unknown,/Needed for this trip 2 mats, Available quantity is unknown/i);assert.doesNotMatch(unknown,/Still missing 0|Available 0|Still missing 2/i);
  const unconfirmed=routed(LogisticsIssues,{items:[{...item,code:'EQUIPMENT_SHORTAGE',
    current:{...item.current,records:[{quantity:2,unit:'item',confirmed:false}],available_quantity:'0'},required:{quantity:'2',missing_quantity:'2'}}],onSafety(){}});
  assert.match(unconfirmed,/Confirmed available 0 mats/i);assert.match(unconfirmed,/Confirm whether registered items are available for this trip/i);
  assert.doesNotMatch(unconfirmed,/Confirmed available 2/i);
});

test('compact tent and vehicle tasks preserve person capacity and the seat-filling hint',()=>{
  const base={issue_id:'tent',code:'EQUIPMENT_DETAILS',item_key:'tent',target:'PROFILE',action_url:'/profile',tent_capacity:tent};
  const html=routed(LogisticsIssues,{items:[base],onSafety(){}});
  assert.match(html,/Tent shortfall: 1 sleeping places/i);assert.match(html,/Capacity per tent/i);assert.doesNotMatch(html,/Still missing 1 tents/i);
  const vehicle=routed(LogisticsIssues,{items:[{...base,item_key:'vehicle',code:'VEHICLE_DETAILS',tent_capacity:undefined,
    current:{unit:'person_space'},required:{capacity_persons:3,missing_quantity:'1'}}],onSafety(){}});
  assert.match(vehicle,/Vehicle shortfall: 1 seats/i);assert.match(vehicle,/Capacity needed this trip: 3 people/i);
  assert.match(vehicle,/seats per vehicle including the driver/i);assert.match(vehicle,/Provide transport arrangements/i);
  const water=routed(LogisticsIssues,{items:[{...base,item_key:'drinking_water',code:'EQUIPMENT_SHORTAGE',tent_capacity:undefined,
    current:{records:[],unit:'litre',available_quantity:'0'},required:{quantity:'4.5',missing_quantity:'4.5'}}],onSafety(){}});
  assert.match(water,/Drinking water shortage: 4\.5 litres/i);assert.doesNotMatch(water,/4\.5 items/i);
});
test('update summary shows actual requirement differences and request history stays collapsed',()=>{
  const before=planFixture().confirmed_context.requirements;
  const after={...before,budget_cents:40000,preferences:['self-catered meals']};
  const html=render(RequirementsChangePreview,{before,after});
  assert.match(html,/Group budget/i);assert.match(html,/AUD 400\.00/i);assert.match(html,/Self-catered meals/i);assert.match(html,/not a formal check result/i);
  const history=routed(RequestHistory,{rows:[{request_id:'update',raw_text:'This camping trip',status:'DRAFT',trip_series_id:'trip'}],deleting:null,selected:null,onSelect(){},onDelete(){},onCancel(){}});
  assert.match(history,/<details class="panel request-history">/i);assert.doesNotMatch(history,/<details[^>]*open/i);
  assert.match(history,/Update this trip/i);assert.match(history,/Saved requests/i);
  assert.doesNotMatch(history,/This does not create an independent trip|Updated plan in the same series/i);
});
test('historical approval copy cannot imply permission to save the current successor',()=>{
  assert.match(historicalReviewNotice('HISTORY'),/Does not authorise the current plan/i);
  assert.match(historicalReviewNotice('HISTORY'),/or its final saving/i);
  assert.equal(historicalReviewNotice('APPROVAL'),null);
});
test('adoption preview shows exact revision and changed inventory, people and transport without a formal pass',()=>{
  const before=planFixture().confirmed_context.profile_snapshot;
  const after=structuredClone(before);after.group_size=4;after.transport.estimated_km='150';
  after.equipment=[{item_key:'tent',label:'Three-person tent',quantity:1,unit:'item',capacity_persons:3,confirmed:false}];
  const changes=profileChanges(before,after);
  assert.deepEqual(changes.map(item=>item.section),['Group size','Equipment and vehicles','Transport arrangements']);
  const html=render(ProfileAdoptionPreview,{before,after,revision:7,sourceRevision:2});
  for(const value of ['revision 7','revision: 2','Original plan used','Proposed for this update','Three-person tent','Unverified','150 km','not a formal check result'])assert.ok(html.includes(value),value);
  assert.doesNotMatch(html,/Checks passed<|Ownership verified/i);
  assert.deepEqual(profileChanges(before,{...structuredClone(before),profile_id:'different-metadata'}),[]);
  const named=structuredClone(after);named.equipment=[{...after.equipment[0],item_key:'sleeping_bag',unit:'item',capacity_persons:null}];
  const changed=structuredClone(named);changed.equipment[0].item_key='groundsheet';
  assert.equal(profileChanges(named,changed)[0].section,'Equipment and vehicles');
});
test('series card uses explicit final owning plan and never presents old success as new check success',()=>{
  const value={trip_series_id:'trip',revision:2,current_plan:{plan_id:'new-plan',run_status:'RUNNING',destination:'This trip',created_at:'2026-10-22T00:00:00Z'},
    history:[{plan_id:'old-plan',destination:'Original plan',created_at:'2026-10-21T00:00:00Z'}],last_final:{plan_id:'old-plan',final_id:'saved',is_current:false}};
  const html=routed(TripSeriesCard,{value,busy:false,onDeletePlan(){},onDeleteSeries(){}});
  assert.match(html,/href="\/plans\/old-plan\/finals\/saved"/i);
  assert.doesNotMatch(html,/\/plans\/new-plan\/finals\/saved/i);
  assert.match(html,/Checks incomplete/i);assert.match(html,/Historical plans \(1\)/i);
  const archived=routed(TripSeriesCard,{value:{...value,current_plan:null},busy:false,onDeletePlan(){},onDeleteSeries(){}});
  assert.match(archived,/Current plan deleted/i);assert.match(archived,/Previous plans and tasks are not restored automatically/i);
});
test('fixed equipment units are readonly, tent displays tents but retains item for calculations',()=>{
  for(const [key,unit,title] of [['tent','item','tents'],['drinking_water','litre','litres'],['meal_supplies','portion','portions'],['transport_itinerary','plan','plans']]){
    const item=gear({item_key:key,unit});
    const html=render(EquipmentUnitField,{item,index:0,onChange(){throw new Error('Must not change on read');}});
    assert.match(html,/readonly=""/i);assert.match(html,new RegExp(`value="${title}"`));
    assert.doesNotMatch(html,/<select|<option/i);assert.equal(item.unit,unit);
    assert.equal(fixedEquipmentUnit(key),unit);
  }
  assert.equal(fixedEquipmentUnit('warm_layers','v1'),'set');
  assert.equal(fixedEquipmentUnit('warm_layers','2.1.0'),'item');
});
test('only other equipment can select units; selection reports actual backend code',()=>{
  let selected='';const props={item:gear({item_key:'other'}),index:0,onChange(value){selected=value;}};
  const html=render(EquipmentUnitField,props);
  assert.match(html,/<select/i);assert.doesNotMatch(html,/readonly/i);
  for(const unit of ['item','litre','portion','vehicle','plan','set'])assert.ok(html.includes(`value="${unit}"`));
  const select=EquipmentUnitField(props).props.children.find(child=>child?.type==='select');
  select.props.onChange({target:{value:'litre'}});assert.equal(selected,'litre');
});
test('legacy mismatched unit stays visible until explicit correction; rendering never changes saved facts',()=>{
  const item=gear({unit:'litre'});let corrected='';
  const props={item,index:0,onChange(value){corrected=value;}};
  const html=render(EquipmentUnitField,props);
  assert.match(html,/value="litres"/i);assert.match(html,/The saved unit does not match the category/i);
  assert.equal(item.unit,'litre');assert.equal(corrected,'');
  const button=EquipmentUnitField(props).props.children.find(child=>child?.type==='button');
  button.props.onClick();assert.equal(corrected,'item');assert.equal(item.unit,'litre');
});
test('adding same-category equipment numbers generic names without changing quantity, capacity or confirmation',()=>{
  const original=[gear()];const copy=JSON.stringify(original);
  const items=addEquipment(original,'tent');
  assert.deepEqual(items.map(item=>item.label),['Tent 1','Tent 2']);
  assert.equal(JSON.stringify(original),copy);
  assert.deepEqual(items[0],{...original[0],label:'Tent 1'});
  assert.deepEqual(items[1],gear({label:'Tent 2',quantity:'',capacity:'',confirmed:false}));
  assert.deepEqual(addEquipment([],'tent').map(item=>item.label),['Tent 1']);
  assert.equal(addEquipment(items,'tent')[2].label,'Tent 3');
});
test('custom names and existing numbered names survive additions and removals without collisions',()=>{
  const items=[gear({label:'Three-person tent'}),gear({label:'Tent 1'}),gear({label:'Tent 3'})];
  assert.deepEqual(addEquipment(items,'tent').map(item=>item.label),['Three-person tent','Tent 1','Tent 3','Tent 2']);
  let many=[];for(let i=0;i<12;i++)many=addEquipment(many,'tent');
  assert.equal(many[9].label,'Tent 10');assert.equal(many[11].label,'Tent 12');
  assert.equal(new Set(many.map(item=>item.label)).size,12);
});
test('category changes assign target units and distinct auto names while preserving user-defined names',()=>{
  let items=addEquipment(addEquipment([],'tent'),'tent');
  items=changeEquipmentCategory(items,1,'drinking_water');
  assert.equal(items[1].label,'Drinking water 1');assert.equal(items[1].unit,'litre');
  items=changeEquipmentCategory(items,1,'tent');
  assert.deepEqual(items.map(item=>item.label),['Tent 1','Tent 2']);assert.equal(items[1].unit,'item');
  const custom=changeEquipmentCategory([gear({label:'Spare item'})],0,'meal_supplies');
  assert.equal(custom[0].label,'Spare item');assert.equal(custom[0].unit,'portion');
  assert.equal(changeEquipmentCategory([gear({unit:'litre'})],0,'other')[0].unit,'litre');
  assert.equal(addEquipment([],'warm_layers','v1')[0].unit,'set');
});
test('profile snapshots preserve distinguishing tent names and individual capacities',()=>{
  const profile=planFixture().confirmed_context.profile_snapshot;
  profile.equipment=[{...gear({label:'Three-person tent'}),quantity:1,capacity_persons:3},{...gear({label:'Solo tent'}),quantity:1,capacity_persons:1}];
  const html=render(ProfileSummary,{profile});
  assert.match(html,/Three-person tent: 1 tents/i);assert.match(html,/Solo tent: 1 tents/i);
  assert.match(html,/Total sleeping capacity in this row 3 people/i);assert.match(html,/Total sleeping capacity in this row 1 people/i);
});

test('initial blank group field is neutral but still required and constrained to positive whole numbers',()=>{
  const html=render(GroupSizeField,{value:'',error:'Enter the group size.',revealValidation:false,onTouch(){},onChange(){}});
  assert.match(html,/aria-invalid="false"/i);
  assert.match(html,/Required/i);assert.match(html,/required=""/i);
  assert.match(html,/min="1"/i);assert.match(html,/step="1"/i);
  assert.match(html,/Include everyone travelling/i);
  assert.doesNotMatch(html,/field-error|Enter the group size/i);
});
test('blur and native invalid events reveal group errors without saving or calling a model',()=>{
  let touched=false,changed='';
  const props={value:'',error:'Enter the group size.',revealValidation:false,onTouch(){touched=true;},onChange(value){changed=value;}};
  const input=GroupSizeField(props).props.children.find(child=>child?.type==='input');
  input.props.onBlur();assert.equal(touched,true);
  let html=render(GroupSizeField,{...props,revealValidation:touched});
  assert.match(html,/aria-invalid="true"/i);assert.match(html,/Enter the group size/i);
  touched=false;input.props.onInvalid();assert.equal(touched,true);
  input.props.onChange({target:{value:'3'}});assert.equal(changed,'3');
  html=render(GroupSizeField,{...props,value:changed,error:undefined,revealValidation:true});
  assert.doesNotMatch(html,/field-error|Enter the group size/i);
  assert.match(html,/aria-invalid="false"/i);
});
test('explicit correction guidance is retained even before interacting with the group field',()=>{
  const html=render(GroupSizeField,{value:'',guidance:'Enter the group size for this trip.',revealValidation:false,onTouch(){},onChange(){}});
  assert.match(html,/aria-invalid="true"/i);assert.match(html,/Enter the group size for this trip/i);
});

test('logged-in plan-list start action begins with profile, not request confirmation',()=>{
  const html=routed(NewPlanPrompt,{});
  assert.match(html,/<a[^>]*href="\/profile"[^>]*>Start planning/i);
  assert.doesNotMatch(html,/href="\/request"/i);
  assert.match(html,/Complete your group, transport and equipment details/i);
});
test('home and fallback start links also follow profile-first onboarding',()=>{
  for(const route of ['/','/missing-page']){
    const html=renderToStaticMarkup(h(MemoryRouter,{initialEntries:[route]},h(App)));
    const startLinks=html.match(/<a\b[^>]*>Start planning[^<]*(?:<span>[^<]*<\/span>)?<\/a>/gi)??[];
    assert.equal(startLinks.length,1,route);
    assert.match(startLinks[0],/href="\/profile"/i);
  }
});

test('tent component shows total accommodation capacity, not one tent per camper',()=>{
  const text=render(panels.TentCapacityPanel,{value:tent});
  for(const expected of ['3 people travelling','2 tents','capacity per tent: 1','Shortage: 1 sleeping places','Number of tents','Capacity per tent','Accepted capacity'])assert.ok(text.includes(expected),expected);
  assert.doesNotMatch(text,/Ignore gap|Force approval/i);
  assert.match(tentSummary({...tent,missing_person_spaces:null}),/Available capacity is unknown/i);
});
test('mixed tent capacities have separate rows and unconfirmed capacity is not relabelled available',()=>{
  const text=render(panels.TentCapacityPanel,{value:{...tent,records:[...tent.records,{quantity:1,capacity_per_tent:3,total_capacity:3,confirmed:false,unit:'item'}],registered_tent_count:3,registered_capacity:5}});
  assert.match(text,/Ownership unverified/i);assert.match(text,/recorded sleeping capacity: 5/i);assert.match(text,/Accepted capacity: 2 people/i);
  assert.equal((text.match(/<tr>/g)||[]).length,3);
});
test('discard only enables for actual changes, reversal removes change, message names changed sections',()=>{
  const saved={group:'3',gear:[{capacity:'1'}],budget:'100'};
  const names={group:'Group size',gear:'Tent capacity',budget:'Budget'};
  assert.deepEqual(changedSections(saved,{...saved},names),[]);
  const sections=changedSections(saved,{...saved,gear:[{capacity:'2'}]},names);
  assert.deepEqual(sections,['Tent capacity']);
  assert.match(discardMessage(sections),/Tent capacity/i);assert.doesNotMatch(discardMessage(sections),/Budget/i);
  assert.match(discardMessage(sections),/does not restore a historical plan or rerun checks/i);
  assert.match(render(panels.DiscardChanges,{sections:[],onDiscard(){}}),/disabled=""/i);
  assert.doesNotMatch(render(panels.DiscardChanges,{sections,onDiscard(){}}),/disabled=""/i);
});
test('saving profile explicitly distinguishes original confirmation and unfinished new checks',()=>{
  assert.match(PROFILE_SAVED_NOTICE,/Profile saved/i);assert.match(PROFILE_SAVED_NOTICE,/still uses its original confirmed/i);
  assert.match(PROFILE_SAVED_NOTICE,/has not been checked with the new information/i);assert.match(PROFILE_SAVED_NOTICE,/Replan with latest profile/i);
});
test('ordinary view cannot render diagnostic payload; reviewer has independent diagnostic section',()=>{
  const value={planning:null,assessments:{LOGISTICS:{trace:{requested_model:'private-model',http_attempts:3,usage:{total_tokens:100}}}}};
  assert.equal(render(panels.ModelRunDiagnostics,{allowed:false,value}),'');
  assert.equal(render(panels.ModelRunDiagnostics,{value}),'');
  const text=render(panels.ModelRunDiagnostics,{allowed:true,value});
  assert.match(text,/Model diagnostics/i);assert.match(text,/private-model/i);assert.match(text,/Not camping costs/i);
});
test('selected model explanation is visible and original provenance stays distinct on reassessment',()=>{
  const text=render(panels.PlanningExplanationPanel,{siteName:'Demo River Flat',currentRunId:'new',
    value:{source_run_id:'old',selected_campsite_id:'demo-river-flat',decision_summary_unverified:'This campsite meets quietness and transport needs.'},
    reasons:['Registered synthetic region, capacity and known hard constraints match.'],uncertainties:['Recommendation is not booking availability or safety clearance.']});
  assert.match(text,/This campsite meets quietness and transport needs/i);assert.match(text,/generated for the original version/i);
  assert.match(text,/Known required conditions/i);assert.match(text,/Verify safety information before departure/i);
  assert.equal(displayProse('unknown English explanation'),'unknown English explanation'); // No invented translation.
});
test('safety reuses structured equipment issue and routes back to equipment without duplicate raw quantities',()=>{
  const item={issue_id:'equipment.tent',code:'EQUIPMENT_SHORTAGE',category:'EQUIPMENT_GAP',item_key:'tent',
    field:'equipment.tent.quantity',target:'PROFILE',action_url:'/profile',current:{records:[]},required:{quantity:'3'},tent_capacity:tent};
  const text=routed(LogisticsIssues,{items:[item],summary:true,onSafety(){},onGear(){}});
  assert.match(text,/Shortage: 1 sleeping places/i);assert.match(text,/There are also 1 preparation items need attention/i);assert.match(text,/View and update equipment/i);
  assert.doesNotMatch(text,/Required quantity: 3|3 tents/i);
});
test('weather shows missing dates, actions, next recheck and never claims overall safety',()=>{
  const value={checked_on:'2026-10-21',next_weather_check_on:'2026-10-25',issues:[{campsite_id:'demo-river-flat',kind:'WEATHER',code:'NOT_YET_OBSERVED',requested_range:{start:'2026-11-01',end:'2026-11-02'},uncovered_ranges:[{start:'2026-11-01',end:'2026-11-02'}],available_ranges:[]}],alternative_dates:[],alternative_campsites:[]};
  const text=routed(TripCoveragePanel,{value,requestId:'request'});
  for(const expected of ['2026-11-01 to 2026-11-02','2026-10-25','check the weather again','Unconfirmed dates'])assert.ok(text.includes(expected),expected);
  assert.doesNotMatch(text,/Information coverage|Checks passed|Mild weather/i);
  assert.equal(evidenceState({status:'AVAILABLE',valid_from:'2026-10-01',valid_to:'2026-11-01',source_refs:[]},{start_date:'2026-10-21',end_date:'2026-10-22'}).title,'Information covers these trip dates');
});

test('safety preparation summary groups repeated issues by item and keeps distinct equipment',()=>{
  const base={issue_id:'tent.quantity',code:'EQUIPMENT_SHORTAGE',item_key:'tent',field:'equipment.tent.quantity',tent_capacity:tent};
  const items=[base,{...base,issue_id:'tent.confirmed',code:'EQUIPMENT_DETAILS'},
    {...base,issue_id:'water',item_key:'drinking_water',field:'equipment.drinking_water',tent_capacity:undefined}];
  const before=structuredClone(items);
  const text=routed(LogisticsIssues,{items,summary:true,onSafety(){},onGear(){}});
  assert.match(text,/There are also 2 preparation items need attention/i);assert.equal((text.match(/<li>/g)||[]).length,2);
  assert.match(text,/Drinking water/i);assert.match(text,/Shortage: 1 sleeping places/i);
  assert.equal((text.match(/<button/gi)||[]).length,1);
  assert.doesNotMatch(text,/→|Planned purchases or loans|Final saving unavailable/i);assert.deepEqual(items,before);
});

const safetyEvidence=(kind,extra={})=>({kind,status:'AVAILABLE',summary:null,road_state:null,source_date:'2026-10-20',
  valid_from:'2026-10-20',valid_to:'2026-11-30',source_refs:[],...extra});
test('condition cards require concrete facts, inspect all evidence and preserve closures and uncertainty',()=>{
  const dates={start_date:'2026-10-22',end_date:'2026-10-24'};
  const open=safetyEvidence('ROAD',{road_state:'OPEN'});
  assert.equal(safetyCondition('ROAD','AVAILABLE',[open],dates).title,'Road open');
  assert.equal(safetyCondition('ROAD','AVAILABLE',[open,{...open,road_state:'CLOSED'}],dates).title,'Road closed');
  assert.equal(safetyCondition('ROAD','AVAILABLE',[open,{...open,valid_to:'2026-10-23'}],dates).title,'To be confirmed');
  assert.equal(safetyCondition('ROAD','AVAILABLE',[{...open,road_state:'UNKNOWN'}],dates).title,'To be confirmed');
  assert.equal(safetyCondition('ROAD','CONFLICTING',[open],dates).attention,true);
  assert.equal(safetyCondition('WEATHER','AVAILABLE',[safetyEvidence('WEATHER',{summary:'Unrecognised forecast.'})],dates).title,'Weather needs confirmation');
  assert.equal(safetyCondition('WEATHER','MISSING',[safetyEvidence('WEATHER',{summary:'Mild synthetic conditions.'})],dates).title,'To be confirmed');
  assert.equal(safetyCondition('WEATHER','AVAILABLE',[safetyEvidence('WEATHER',{summary:'Mild synthetic conditions.'})],dates).title,'Mild weather');
  const fire=safetyCondition('FIRE','AVAILABLE',[safetyEvidence('FIRE',{summary:'No synthetic fire restriction.'})],dates);
  assert.equal(fire.title,'No additional restrictions recorded');assert.doesNotMatch(fire.title,/Allowed|Pass/i);
  assert.equal(safetyCondition('FIRE','AVAILABLE',[],dates,['FIRE_PROHIBITED']).attention,true);
  assert.equal(safetyCondition('RESTRICTION','AVAILABLE',[],dates,['CAMPSITE_CLOSED']).title,'Campsite closed');
  assert.equal(safetyRegulations('Campfires and solid fuel burners prohibited; gas/electric barbecues provided'),'Campfires and solid fuel burners prohibited; gas/electric barbecues provided');
});

test('known adverse weather remains explicit without changing coverage or official assessment state',()=>{
  const dates={start_date:'2026-10-28',end_date:'2026-10-30'};
  for(const [summary,title] of [
    ['Synthetic extreme heat expected.','Extreme heat forecast'],
    ['Strong wind in synthetic forecast.','Strong winds forecast'],
    ['Strong wind in this synthetic scenario.','Strong winds forecast'],
    ['Heavy rain in synthetic forecast.','Heavy rain forecast'],
    ['Heavy rain in synthetic conditions.','Heavy rain forecast'],
    ['Cold synthetic forecast.','Cold weather forecast'],
  ]){
    const evidence=safetyEvidence('WEATHER',{summary});
    const state=safetyCondition('WEATHER','AVAILABLE',[evidence],dates);
    assert.equal(state.title,title);assert.equal(state.attention,true);
    for(const status of ['MISSING','STALE','CONFLICTING']){
      const unavailable=safetyCondition('WEATHER',status,[{...evidence,status}],dates);
      assert.equal(unavailable.attention,true);assert.notEqual(unavailable.title,title);
    }
    assert.equal(safetyCondition('WEATHER','AVAILABLE',[{...evidence,valid_to:'2026-10-29'}],dates).title,'To be confirmed');
    const mixed=safetyCondition('WEATHER','AVAILABLE',[evidence,safetyEvidence('WEATHER',{summary:'Unrecognised forecast.'})],dates);
    assert.equal(mixed.title,title+'; Other weather details need confirmation');assert.equal(mixed.attention,true);
  }
});

test('saved safety-09 heat remains visible to camper, historical, final and reviewer views without exposing diagnostics',()=>{
  const rows=JSON.parse(readFileSync(new URL('../../data/synthetic_demo_v2/data/runtime_safety_evidence.json',import.meta.url),'utf8'));
  const row=rows.find(item=>item.safety_case_id==='safety-09');
  assert.equal(row.weather.summary,'Synthetic extreme heat expected.');
  const data=planFixture();
  Object.assign(data.confirmed_context.requirements,{start_date:'2026-10-28',end_date:'2026-10-30',duration_nights:2,duration_days:3});
  const safety={outcome:'REVIEW',risk_level:'HIGH',confidence:'HIGH',requires_human_review:true,
    data_quality:{WEATHER:'AVAILABLE'},evidence:[safetyEvidence('WEATHER',{summary:row.weather.summary,valid_from:row.weather.valid_from,valid_to:row.weather.valid_until})],
    mandatory_blockers:[],hazards:[row.campsite_id+': '+row.weather.summary],unresolved_conflicts:[],recommended_actions:['private-rule-action']};
  data.assessments.push({assessment_id:'safety',kind:'SAFETY',version_context:data.version.version_context,result:safety});
  const before=structuredClone(data);
  // is_active=false is the saved historical-run path; snapshot=true is also
  // used by FinalPage after its authorised final-snapshot read.
  for(const [options,active] of [[{},true],[{},false],[{snapshot:true},false],[{review:true},true]]){
    const page={...data,run:{...data.run,is_active:active}};
    const html=renderPlan(page,options);
    assert.match(html,/Extreme heat forecast/i);assert.match(html,/View the saved original risk explanation/i);
    assert.ok(html.includes(row.campsite_id+': '+row.weather.summary));
    if(!options.review)assert.doesNotMatch(html,/Full check details|private-rule-action|Model diagnostics/i);
  }
  assert.deepEqual(data,before);
});

test('untranslated safety and hazard originals survive escaped without source or diagnostic disclosure',()=>{
  const summary='Synthetic forecast: <img src=x onerror=alert(1)> unusual weather.';
  const hazards=['demo-site-a: unknown synthetic hazard.','demo-site-b: another synthetic hazard.'];
  const value={outcome:'REVIEW',risk_level:'UNKNOWN',confidence:'UNKNOWN',requires_human_review:true,
    data_quality:{WEATHER:'MISSING'},evidence:[safetyEvidence('WEATHER',{status:'MISSING',summary})],
    mandatory_blockers:[],hazards,unresolved_conflicts:['private-conflict'],recommended_actions:['private-rule-action']};
  const props={value,summary:'Safety information needs confirmation',approved:false,review:false,outdated:true,blockers:null,notes:null,
    rawWarnings:[{code:'INTERNAL_CODE',message:'private-diagnostic'}],sources:()=>h('p',null,'private-source-record'),label:x=>x};
  const before=structuredClone(value),html=render(SafetyInformation,props);
  assert.match(html,/View the saved original safety explanation/i);assert.match(html,/&lt;img src=x onerror=alert\(1\)&gt;/i);
  assert.doesNotMatch(html,/<img|INTERNAL_CODE|private-diagnostic|private-source-record|private-conflict|private-rule-action|Full check details/i);
  for(const hazard of hazards)assert.ok(html.includes(hazard));
  assert.equal((html.match(/View the saved original risk explanation/gi)||[]).length,2);
  assert.deepEqual(value,before);
});

test('safety page folds useful rules, omits coverage explanations and restricts diagnostics to review',()=>{
  const value={outcome:'REVISION',risk_level:'LOW',confidence:'HIGH',requires_human_review:false,
    data_quality:{ROAD:'AVAILABLE',FIRE:'AVAILABLE',WEATHER:'AVAILABLE',RESTRICTION:'AVAILABLE'},
    evidence:[safetyEvidence('ROAD',{road_state:'OPEN'}),safetyEvidence('FIRE',{summary:'No synthetic fire restriction.'}),
      safetyEvidence('WEATHER',{summary:'Mild synthetic conditions.'}),safetyEvidence('RESTRICTION',{summary:'Bring all drinking water; Keep noise down after 10pm'})],
    mandatory_blockers:[],hazards:[],unresolved_conflicts:[],recommended_actions:['private-rule-action']};
  const props={value,summary:'Equipment and transport preparation incomplete',approved:false,review:false,outdated:false,blockers:null,notes:null,
    rawWarnings:[{code:'INTERNAL_CODE',message:'internal-diagnostic'}],sources:()=>h('p',null,'private-source-record'),label:x=>x,
    coverage:{issues:[]},requestId:'request'};
  const html=render(SafetyInformation,props);
  for(const text of ['Road open','Mild weather','No additional restrictions recorded','Bring all drinking water','Keep noise down after 10pm'])assert.ok(html.includes(text),text);
  assert.match(html,/<details class="artifact-notes"><summary>View safety details and campsite rules/i);
  assert.doesNotMatch(html,/Information coverage|Final eligibility|What you can do next|synthetic|Full check details|INTERNAL_CODE|private-source-record|private-rule-action|internal-diagnostic/i);
  const reviewer=render(SafetyInformation,{...props,review:true});
  assert.match(reviewer,/INTERNAL_CODE/i);assert.match(reviewer,/private-source-record/i);
  assert.equal(render(TripCoveragePanel,{value:{issues:[]}}),'');
});

test('plan explains preparation-only blockers without disguising a road closure as a gear issue',()=>{
  const value=planFixture();
  const safety={outcome:'REVISION',risk_level:'LOW',confidence:'HIGH',requires_human_review:false,
    data_quality:{},evidence:[],mandatory_blockers:[{code:'ESSENTIAL_GEAR_MISSING',message:'internal-gear-detail',source_refs:[]}],
    hazards:[],unresolved_conflicts:[],recommended_actions:[]};
  value.assessments.push({assessment_id:'safety',kind:'SAFETY',version_context:value.version.version_context,result:safety});
  const html=renderPlan(value);
  assert.match(html,/Equipment and transport preparation incomplete/i);assert.match(html,/View equipment and transport/i);
  assert.doesNotMatch(html,/internal-gear-detail/i);
  safety.evidence=[safetyEvidence('ROAD',{road_state:'CLOSED'})];
  safety.mandatory_blockers.push({code:'ROAD_CLOSED',message:'internal-road-detail',source_refs:[]});
  const closed=renderPlan(value);
  assert.match(closed,/Road closed; change the plan/i);assert.match(closed,/View safety information/i);
  assert.doesNotMatch(closed,/Equipment and transport preparation incomplete|internal-road-detail/i);
});
test('new pending checks override old successful display and completed issues have distinct labels',()=>{
  const row={run_status:'RUNNING',stage:'ASSESSING_SAFETY',version_status:'FINALISED',display_status:'FINALISED'};
  assert.equal(planRowState(row),'Checks incomplete');
  for(const [key,label] of Object.entries({NEEDS_USER_INPUT:'Plan changes needed',NEEDS_REVISION:'Plan changes needed',AWAITING_REVIEW:'Awaiting human review',CANNOT_RELEASE:'Plan changes needed'}))
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
test('current plan omits the redundant adjustment card while retaining next steps and change controls',()=>{
  const value=planFixture();
  value.run.is_active=true;
  value.version.status='ELIGIBLE_FOR_FINALISATION';
  value.finalisation_available=true;
  value.eligibility={eligible:true,blocking_reasons:[],review_required:false,valid_review_id:null};
  value.assessments[0].result.outcome='PASSED';
  value.assessments[0].result.gear_checklist=[];
  value.assessments.push({assessment_id:'safe',kind:'SAFETY',version_context:value.version.version_context,result:{outcome:'PASSED',requires_human_review:false,risk_level:'LOW',confidence:'HIGH',data_quality:{},evidence:[],hazards:[],recommended_actions:[],mandatory_blockers:[],unresolved_conflicts:[]}});
  value.revision_available=true;value.reassessment_available=true;
  const before=structuredClone(value);
  const html=renderPlan(value);
  assert.doesNotMatch(html,/aria-label="Adjust camping plan"|<h2>Adjust camping plan<\/h2>/i);
  assert.match(html,/To be confirmed/i);
  assert.match(html,/Modify plan and reassess/i);
  assert.match(html,/href="\/plans\/plan\/update"/i);
  assert.match(html,/Edit and reconfirm requirements and profile ↗/i);
  assert.match(html,/Modify plan/i);
  assert.deepEqual(value,before);
});
test('current final snapshot offers a guarded update route while historical finals only link to current state',()=>{
  const current=routed(FinalPlanNavigation,{planId:'plan / one',isCurrent:true});
  assert.match(current,/Update this trip ↗/i);assert.match(current,/href="\/plans\/plan%20%2F%20one\/update"/i);
  const historical=routed(FinalPlanNavigation,{planId:'plan',isCurrent:false});
  assert.match(historical,/href="\/plans\/plan"/i);assert.doesNotMatch(historical,/Update this trip|\/update/i);
});

test('saved current plan retains successor navigation without reopening its immutable final',()=>{
  const value=planFixture();value.run.is_active=true;value.version.status='FINALISED';
  value.plan.current_version_id='version';value.plan.final_version_id='version';
  value.last_final={plan_id:'plan',final_id:'saved-final',is_current:true,run_id:'run',plan_version_id:'version'};
  value.finalisation_available=false;value.revision_available=false;value.reassessment_available=false;
  const before=structuredClone(value);
  const html=renderPlan(value);
  assert.match(html,/Final plan saved; this trip can still be updated/i);
  assert.match(html,/href="\/plans\/plan\/update"/i);
  assert.match(html,/Edit camping profile ↗/i);
  assert.match(html,/New plans require new checks and confirmation before saving/i);
  assert.doesNotMatch(html,/Modify plan/i);
  for(const options of [{snapshot:true},{review:true}])
    assert.doesNotMatch(renderPlan(value,options),/Final plan saved; this trip can still be updated|Review and adjust this trip requirements ↗|Edit camping profile ↗/i);
  for(const patch of [{run:{...value.run,is_active:false}},{trip_series:{is_current:false,current_plan_id:'successor'}},
      {run:{...value.run,status:'RUNNING'}},{revision_comparison:comparisonFixture()}])
    assert.doesNotMatch(renderPlan({...value,...patch}),/Final plan saved; this trip can still be updated|Review and adjust this trip requirements ↗|Edit camping profile ↗/i);
  assert.deepEqual(value,before);
});

test('plan budget action follows revision capability and is absent from historical, final and review views',()=>{
  const value=planFixture();value.run.is_active=true;value.revision_available=true;value.reassessment_available=true;
  value.current_version_revision=1;value.logistics_issues=[budgetIssue];
  value.assessments[0].result.total_cents=34600;value.assessments[0].result.budget_difference_cents=4600;
  const html=renderPlan(value);
  assert.match(html,/Keep budget and look for a lower-cost plan/i);assert.match(html,/Modify plan/i);
  const forbidden=structuredClone(value);forbidden.revision_available=false;forbidden.display_status='NEEDS_REVISION';
  assert.doesNotMatch(renderPlan(forbidden),/Keep budget and look for a lower-cost plan/i);
  for(const options of [{snapshot:true},{review:true}])
    assert.doesNotMatch(renderPlan(value,options),/Keep budget and look for a lower-cost plan/i);
  for(const change of [v=>{v.run.is_active=false;},v=>{v.run.status='RUNNING';},v=>{v.trip_series={is_current:false};}]){
    const changed=structuredClone(value);change(changed);
    assert.doesNotMatch(renderPlan(changed),/Keep budget and look for a lower-cost plan/i);
  }
});
test('historical and final plan components use saved tent facts and mark all suggested itinerary times',()=>{
  for(const snapshot of [false,true]){
    const html=renderPlan(planFixture(),{snapshot});
    assert.match(html,/Shortage: 1 sleeping places/i);assert.match(html,/Suggested time \/ to be confirmed/i);
    assert.match(html,/Not verified check-in, check-out or transport times/i);
    assert.doesNotMatch(html,/Model diagnostics|Restore saved fields/i);
    if(!snapshot)assert.match(html,/Viewing a historical plan/i);
  }
});
test('running new check keeps previous final but never displays its status as this check result',()=>{
  const value=planFixture();value.run={...value.run,is_active:true,status:'RUNNING',operation:'REASSESS'};
  value.version.status='FINALISED';value.last_final={plan_id:'plan',final_id:'old',is_current:true};
  const html=renderPlan(value);
  assert.match(html,/plan-status-neutral/i);assert.match(html,/Previous final plan retained; current checks are incomplete/i);
  assert.match(html,/Rechecking/i);
  assert.match(html,/<h2>Current checks are incomplete<\/h2>/i);
});
test('review component alone renders authorised diagnostic payload separate from equipment/budget advice',()=>{
  const value=planFixture();value.can_view_model_diagnostics=true;
  value.model_diagnostics={planning:null,assessments:{SAFETY:{trace:{requested_model:'reviewer-private-model'}}}};
  const html=renderPlan(value,{review:true});assert.match(html,/Model diagnostics/i);assert.match(html,/reviewer-private-model/i);
  value.can_view_model_diagnostics=false;
  assert.doesNotMatch(renderPlan(value),/reviewer-private-model|Model diagnostics/i);
});


test('finalised current read keeps its saved approval but never authorises a new run or version',()=>{
  const value=planFixture();value.run.is_active=true;value.version.status='FINALISED';
  value.reviews=[{review_id:'approved-review',decision:'APPROVE',reason:'saved review',reviewer_user_id:'founder'}];
  value.last_final={plan_id:'plan',final_id:'final',is_current:true,run_id:'run',plan_version_id:'version'};
  value.assessments.push({assessment_id:'safety',kind:'SAFETY',version_context:value.version.version_context,result:{outcome:'REVIEW',requires_human_review:true,risk_level:'HIGH',confidence:'LOW',data_quality:{},evidence:[],hazards:[],recommended_actions:[],mandatory_blockers:[],unresolved_conflicts:[]}});
  assert.match(renderPlan(value),/Review approved/i);
  for(const patch of [{run_id:'older-run'},{plan_version_id:'older-version'},{is_current:false}]){
    const changed=structuredClone(value);Object.assign(changed.last_final,patch);
    assert.doesNotMatch(renderPlan(changed),/Review approved/i);
  }
  const newer=structuredClone(value);newer.run.status='RUNNING';
  assert.doesNotMatch(renderPlan(newer),/Review approved/i);
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
  assert.match(html,/Plan changes needed/i);assert.match(html,/Road closed; change the plan/i);
  assert.match(html,/Choose a campsite with an open route/i);assert.doesNotMatch(html,/Cannot confirm road access during the trip/i);
  assert.doesNotMatch(html,/Awaiting reviewer action|Awaiting human review|This plan needs human risk review/i);
  assert.equal(v.finalisation_available,false);
});
test('historical approval is labelled as past and never becomes current eligibility',()=>{
  const v=reviewedFixture();v.version.status='FINALISED';v.trip_series={is_current:false,current_plan_id:'successor'};
  v.reviews=[{review_id:'past',decision:'APPROVE',reason:'past reason',reviewer_user_id:'founder',version_context:{...v.version.version_context}}];
  v.final_history=[{plan_id:'plan',final_id:'past-final',run_id:'run',plan_version_id:'version',is_current:false}];
  let html=renderPlan(v);assert.match(html,/Approved in the earlier review/i);assert.match(html,/previous approvals do not authorise new results/i);
  assert.doesNotMatch(html,/Safety assessment: review required/i);assert.equal(v.eligibility,null);assert.equal(v.finalisation_available,false);
  for(const change of [{run_id:'new-run'},{plan_version_id:'new-version'},{input_fingerprint:'new-input'}]){
    const different=structuredClone(v);Object.assign(different.reviews[0].version_context,change);
    assert.doesNotMatch(renderPlan(different),/Approved in the earlier review/i);
  }
  const newer=structuredClone(v);newer.version.status='ESCALATED';newer.run.operation='REASSESS';
  assert.doesNotMatch(renderPlan(newer),/Approved in the earlier review/i);
});

test('login and profile no longer offer sample credentials or sample-filled personal facts',()=>{
  const html=renderToStaticMarkup(h(MemoryRouter,null,h(SessionProvider,null,h(LoginPage))));
  assert.doesNotMatch(html,/Demo account|camper\.a|camper\.b|CampMate-Founder|demo-accounts/i);
  assert.match(html,/Create account/i);assert.match(html,/login-layout/i);
  const profile=readFileSync(new URL('../src/profile.tsx',import.meta.url),'utf8');
  assert.doesNotMatch(profile,/Try it first|Load sample profile|demoInputs|loadDemo|demoAvailable/i);
  assert.doesNotMatch(profile,/EquipmentSaveNotice|equipment-save-notice|Enter equipment actually available for this trip/i);
  assert.doesNotMatch(profile,/Ownership verified<\/label>/i);
});
test('required fields have visible text badges without making optional profile facts mandatory',()=>{
  for(const [Page,ids] of [[RegisterPage,['register-username','register-password','register-confirmation']]]){
    const html=renderToStaticMarkup(h(MemoryRouter,null,h(SessionProvider,null,h(Page))));
    assert.doesNotMatch(html,/register-name|Display name/i);
    for(const id of ids){
      assert.ok(html.includes(`<label for="${id}">`),id);
      assert.match(html.split(`<label for="${id}">`)[1].split('</label>')[0],/class="required-mark">Required/i);
    }
  }
  const css=readFileSync(new URL('../src/styles.css',import.meta.url),'utf8');
  assert.match(css,/\.required-mark\{[^}]*font-size:12px;[^}]*font-weight:700/i);
  const profile=readFileSync(new URL('../src/profile.tsx',import.meta.url),'utf8');
  assert.match(profile,/htmlFor=\{`gear-name-\$\{index\}`\}>Name<\/label>/i);
  assert.match(profile,/aria-label=\{`Equipment \$\{index\+1\} Name`\} required/i);
  const login=renderToStaticMarkup(h(MemoryRouter,null,h(SessionProvider,null,h(LoginPage))));
  assert.doesNotMatch(login,/required-mark/i);assert.match(login,/required=""/i);
  assert.match(profile,/equipment: equipmentPayload\(equipment\)/i);
});


test('daily itinerary groups saved Sydney dates and preserves specific content and suggested-time labels',()=>{
  const entries=[
    {entry_kind:'ACTIVITY',start_at:'2026-10-27T02:00:00Z',end_at:'2026-10-27T05:00:00Z',campsite_id:'bonnie-vale',description:'Campsite setup and meal preparation: check drinking-water and shower facilities.'},
    {entry_kind:'CAMP',start_at:'2026-10-27T17:00:00+11:00',end_at:'2026-10-28T10:00:00+11:00',campsite_id:'bonnie-vale',description:'Synthetic overnight stay at Bonnie Vale campground; no booking implied.'},
    {entry_kind:'ACTIVITY',start_at:'2026-10-28T10:00:00+11:00',end_at:'2026-10-28T11:00:00+11:00',campsite_id:'bonnie-vale',description:'Pack-up and return preparation: check equipment and take all rubbish.'}];
  const before=structuredClone(entries);
  const html=render(DailyItinerary,{entries,time:x=>x,label:x=>x});
  for(const text of ['Day 1 · 2026-10-27','Day 2 · 2026-10-28','check drinking-water and shower facilities','Pack-up and return preparation','check equipment and take all rubbish'])assert.ok(html.includes(text),text);
  assert.equal((html.match(/Suggested time \/ to be confirmed/gi)||[]).length,3);
  assert.deepEqual(entries,before);
});

test('specific matching facts remain separate from model opinion and survive historical/final display',()=>{
  const data=planFixture();
  data.recommendations={result:{search_outcome:'MATCHES',excluded_candidates:[],source_refs:[],assumptions:[],uncertainties:[],candidates:[
    {campsite_id:'demo-river-flat',rank:1,reasons:['Group size: this trip has 3 people; recorded capacity is 4 people.','Campsite facilities: Showers are listed as provided.','Accommodation cost: per night AUD 85.00; Campsite fees only; full trip costs still need checking.'],material_uncertainties:[]},
    {campsite_id:'demo-wattle-rest',rank:2,reasons:['Campsite facilities: showers unavailable; alternative arrangements needed.','Accommodation cost: per night AUD 45.00; Campsite fees only; full trip costs still need checking.'],material_uncertainties:[]}]}};
  data.planning_explanation={source_run_id:'run',selected_campsite_id:'demo-river-flat',decision_summary_unverified:'A model opinion, not a verified fact.'};
  const before=structuredClone(data);
  for(const options of [{},{snapshot:true},{review:true}]){
    const html=renderPlan(data,options);
    for(const text of ['this trip has 3 people','recorded capacity is 4 people','Listed as provided in campsite information','showers unavailable','AUD 85.00','AUD 45.00','Campsite fees only','A model opinion, not a verified fact.'])assert.ok(html.includes(text),text);
    assert.match(html,/Comparison with confirmed requirements/i);
  }
  assert.deepEqual(data,before);
});


const registeredCooking={...preparation,items:[
  {item_key:'camping_stove',recorded:true,entered_quantity:1,confirmed_quantity:1,unit_valid:true},
  {item_key:'fuel_canister',recorded:true,entered_quantity:2,confirmed_quantity:2,unit_valid:true}]};
test('complete cooking registration renders no reminder or completed-state message',()=>{
  const before=structuredClone(registeredCooking);
  assert.equal(canHideCookingPreparation(registeredCooking),true);
  const html=render(CookingPreparationPanel,{value:registeredCooking});
  assert.equal(html,'');
  assert.deepEqual(registeredCooking,before);
});

test('missing, zero, unconfirmed, invalid and duplicate cooking rows cannot be hidden',()=>{
  const badRows=[{entered_quantity:null,confirmed_quantity:null},{entered_quantity:0,confirmed_quantity:0},
    {confirmed_quantity:null},{unit_valid:false},{recorded:false}];
  for(const patch of badRows){
    const value={...registeredCooking,items:[registeredCooking.items[0],{...registeredCooking.items[1],...patch}]};
    assert.equal(canHideCookingPreparation(value),false);
    assert.match(render(CookingPreparationPanel,{value}),/<section class="clarifications"/i);
  }
  for(const value of [{...registeredCooking,items:[registeredCooking.items[0],registeredCooking.items[0]]},
    {...registeredCooking,calculation_status:'UNAVAILABLE'},
    {...registeredCooking,calculation_status:'UNKNOWN_FUTURE_STATUS'},
    {...registeredCooking,applicable:false},
    {...registeredCooking,required_fuel_quantity:'4',fuel_gap:'2'},
    {...registeredCooking,required_fuel_quantity:'2',fuel_gap:null}])assert.equal(canHideCookingPreparation(value),false);
});

test('edits, saved formal issues and errors reopen registered cooking even after a zero-gap preview',()=>{
  const preview={...registeredCooking,required_fuel_quantity:'2',fuel_gap:'0',calculation_status:'DRAFT_ESTIMATE'};
  assert.equal(render(CookingPreparationPanel,{value:registeredCooking,preview}),'');
  for(const patch of [{stale:true},{unsaved:true},{attention:true},{busy:true},{error:'Update failed'}]){
    const html=render(CookingPreparationPanel,{value:registeredCooking,preview,...patch});
    assert.match(html,/<section class="clarifications"/i);assert.doesNotMatch(html,/class="cooking-registration"/i);
  }
  const stale=render(CookingPreparationPanel,{value:registeredCooking,preview,stale:true});
  assert.match(stale,/Profile changed/i);assert.doesNotMatch(stale,/Still missing 0 items/i);
  assert.match(render(CookingPreparationPanel,{value:registeredCooking,preview,unsaved:true}),/Changes on this page are unsaved/i);
});

test('formal cooking gaps stay visible while complete records leave no empty panel or edit link',()=>{
  const value={...planFixture(),cooking_preparation:registeredCooking};
  for(const options of [{},{snapshot:true},{review:true}]){
    const html=renderPlan(value,options);
    assert.equal(html,renderPlan(planFixture(),options));
    assert.doesNotMatch(html,/Cooking equipment registered|View or edit cooking equipment|Check stove and fuel details together ↗/i);
  }
  const blocked=structuredClone(value);
  blocked.assessments[0].result.gear_checklist.push({item_key:'fuel_canister',required_quantity:'4',available_quantity:'2',missing_quantity:'2',unit:'item',capacity_requirement:null,arrangement_status:'UNCONFIRMED',essential:true});
  const html=renderPlan(blocked);
  assert.match(html,/The saved check still has cooking tasks/i);assert.doesNotMatch(html,/class="cooking-registration"/i);
  assert.equal(blocked.assessments[0].result.gear_checklist.at(-1).missing_quantity,'2');
});

test('selected campsite merges matching facts, facilities, cost and arrival without duplicating facilities',()=>{
  const reasons=['Destination region:Sydney & Surrounds, matches this selection.',
    'Group size: this trip has 1 people; recorded capacity is 4 people.',
    'Transport: public transport access is recorded; verify actual return services and final connections.',
    'Required condition: Toilets, listed as supported.','Required condition: Showers, listed as supported.',
    'Campsite facilities: Toilets are listed as provided.','Campsite facilities: Showers are listed as provided.','Campsite facilities: Drinking water is listed as provided.',
    'Accommodation cost: per night AUD 60.00, 2 nights total AUD 120.00; Campsite fees only; full trip costs still need checking.'];
  const before=[...reasons];
  const html=render(panels.PlanningExplanationPanel,{siteName:'Bonnie Vale',siteId:'bonnie-vale',catalogueId:'sydney-surrounds-2.2-2026-10-23',reasons,uncertainties:[]});
  assert.equal((html.match(/class="panel campsite-selection"/gi)||[]).length,1);
  assert.match(html,/Reasons for choosing Bonnie Vale/i);
  for(const name of ['Toilets','Showers','Drinking water']){
    assert.equal((html.match(new RegExp('<th scope="row">'+name,'g'))||[]).length,1);
    assert.ok(!html.includes('<dt>'+name+'</dt>'));
  }
  for(const text of ['Comparison with confirmed requirements','Required for this trip','this trip has 1 people','Campsite fees','AUD 120.00','Campsite fees only','Getting there and important notes','Campsite rules and sources','Official campsite overview','Official access and visitor information','verify actual return services and final connections'])assert.ok(html.includes(text),text);
  assert.doesNotMatch(html,/Campsite and arrival arrangements|Filtering record: suitability reasons|ABOUT THE CAMPGROUND/i);
  for(const reason of reasons)assert.ok(html.includes(renderToStaticMarkup(h('li',null,englishSavedReason(reason)))),'saved reason display must remain: '+reason);
  assert.deepEqual(reasons,before);
});

test('merged selection preserves conflicting, unknown and unfamiliar facts instead of declaring a match',()=>{
  const reasons=['Required condition: Toilets, listed as supported.','Campsite facilities: Toilets are unavailable; make alternative arrangements.',
    'Required condition: Drinking water, listed as unknown.','A new reason outside the standard format.','Untranslated original reason.'];
  const html=render(panels.PlanningExplanationPanel,{siteName:'Historical campsite',siteId:'bonnie-vale',catalogueId:'old-catalogue',reasons,uncertainties:[]});
  assert.equal((html.match(/<th scope="row">Toilets/gi)||[]).length,2);
  for(const text of ['Listed as provided in campsite information','Listed as unavailable in campsite information','Campsite information is unspecified','A new reason outside the standard format','Untranslated original reason.'])assert.ok(html.includes(text),text);
  assert.doesNotMatch(html,/Getting there and important notes|View official campsite information|Source records show it is provided|Best fit|Cheapest/i);
  const mixed=render(panels.PlanningExplanationPanel,{siteName:'Bents Basin',siteId:'bents-basin',catalogueId:'sydney-surrounds-2.2-2026-10-23',reasons:['Campsite facilities: Drinking water is listed as provided.'],uncertainties:[]});
  assert.match(mixed,/Listed as provided in campsite information/i);assert.match(mixed,/Listed as unavailable; bring your own drinking water/i);
});

test('arrival catalogue stays version-bound and model opinion stays folded with original run provenance',()=>{
  const props={siteName:'Bonnie Vale',siteId:'bonnie-vale',catalogueId:'sydney-surrounds-2.2-2026-10-23',currentRunId:'new',
    value:{source_run_id:'old',selected_campsite_id:'bonnie-vale',decision_summary_unverified:'Original model suggestion; not verified information.'},reasons:[],uncertainties:['Unknown historical pending-confirmation text.']};
  const html=render(panels.PlanningExplanationPanel,props);
  assert.match(html,/<details class="source-details"><summary>Saved selection records and model comments<\/summary>/i);
  assert.doesNotMatch(html,/<details[^>]*open/i);
  for(const text of ['generated for the original version','Original model suggestion; not verified information','Unknown historical pending-confirmation text'])assert.ok(html.includes(text),text);
  for(const patch of [{catalogueId:undefined},{catalogueId:'different-source'},{siteId:'demo-river-flat'},{siteId:'__proto__'}]){
    const old=render(panels.PlanningExplanationPanel,{...props,...patch});
    assert.doesNotMatch(old,/Getting there and important notes|Campsite rules and sources|Campsite records show it is provided/i);
    assert.match(old,/Original model suggestion/i);
  }
});

test('current, historical, final and reviewer plans use one merged card for each selected campsite',()=>{
  const data=planFixture();
  data.campsite_catalogue_id='sydney-surrounds-2.2-2026-10-23';
  data.version.content.selected_campsite_ids=['bonnie-vale','bents-basin'];
  data.recommendations={result:{search_outcome:'MATCHES',excluded_candidates:[],source_refs:[],assumptions:[],uncertainties:[],candidates:[
    {campsite_id:'bonnie-vale',rank:1,reasons:['Group size: this trip has 1 people; recorded capacity is 4 people.'],material_uncertainties:[]},
    {campsite_id:'bents-basin',rank:2,reasons:['Campsite facilities: Drinking water is unavailable; make alternative arrangements.'],material_uncertainties:[]}]}};
  data.planning_explanation={source_run_id:'old',selected_campsite_id:'bonnie-vale',decision_summary_unverified:'Only applies to Bonnie Vale  original model text.'};
  const before=structuredClone(data);
  for(const options of [{},{snapshot:true},{review:true}]){
    const html=renderPlan(data,options);
    assert.equal((html.match(/class="panel campsite-selection"/gi)||[]).length,2);
    assert.equal((html.match(/Getting there and important notes/gi)||[]).length,2);
    assert.equal((html.match(/Only applies to Bonnie Vale  original model text/gi)||[]).length,1);
    assert.doesNotMatch(html,/Campsite and arrival arrangements/i);
  }
  const historical=structuredClone(data);historical.run.is_active=false;
  assert.equal((renderPlan(historical).match(/class="panel campsite-selection"/gi)||[]).length,2);
  assert.deepEqual(data,before);
});


test('facility wording is consistent across mandatory and other facilities without changing known or unknown state',()=>{
  const reasons=['Required condition: Toilets, listed as supported.','Campsite facilities: Toilets are listed as provided.',
    'Required condition: Showers, listed as supported.','Campsite facilities: Drinking water is listed as provided.'];
  const before=[...reasons];
  const {rows}=selectionPresentation(reasons);
  assert.equal(rows.length,3);
  assert.deepEqual(rows.map(row=>row.detail),Array(3).fill('Listed as provided in campsite information.'));
  assert.deepEqual(rows.map(row=>!!row.required),[true,true,false]);
  assert.deepEqual(rows.map(row=>row.state),[true,true,true]);
  const unavailable=selectionPresentation(['Required condition: Showers; registered information: not supported.','Required condition: Drinking water, listed as unknown.','Campsite facilities: Drinking water is unavailable; make alternative arrangements.']).rows;
  assert.deepEqual(unavailable.map(row=>row.state),[false,null,false]);
  assert.deepEqual(unavailable.map(row=>row.detail),['Listed as unavailable in campsite information.','Campsite information is unspecified and needs confirmation.','Listed as unavailable; bring your own drinking water.']);
  assert.deepEqual(reasons,before);
});

test('official source links distinguish overview, visitor access and BYO tent pages while preserving URLs',()=>{
  const regular=cataloguePlace('the-basin','sydney-surrounds-2.2-2026-10-23');
  const island=cataloguePlace('cockatoo-island','sydney-surrounds-2.2-2026-10-23');
  for(const [place,labels] of [[regular,['Official campsite overview','Official access and visitor information']],[island,['Official campsite overview','Official bring-your-own-tent information']]]){
    const before=structuredClone(place);
    const html=render(CampsiteArrivalDetails,{place});
    const anchors=[...html.matchAll(/<a href="([^"]+)"[^>]*>([^<]+)<\/a>/gi)];
    assert.deepEqual(anchors.map(match=>match[1]),place.source_urls);
    assert.deepEqual(anchors.map(match=>match[2]),labels.map(text=>text+' ↗'));
    assert.equal(new Set(anchors.map(match=>match[2])).size,place.source_urls.length);
    assert.match(html,/target="_blank" rel="noreferrer"/i);
    assert.deepEqual(place,before);
  }
});


test('saved simulated activities show their specific titles without inventing content for old free-time entries',()=>{
  const marker='(Simulated activity suggestion; subject to formal safety checks and on-site conditions.)';
  const base={entry_kind:'ACTIVITY',start_at:'2026-10-31T13:00:00+11:00',end_at:'2026-10-31T16:00:00+11:00',campsite_id:'the-basin'};
  const entries=[{...base,description:'Campsite nature observation and photography: observe colours and shapes within the campsite, with rest breaks.'+marker}];
  const before=structuredClone(entries);
  const html=render(DailyItinerary,{entries,time:x=>x,label:x=>x});
  assert.match(html,/<h4>Campsite nature observation and photography<\/h4>/i);
  for(const text of ['The Basin','observe colours and shapes within the campsite','Suggested time / to be confirmed','Subject to formal safety checks and on-site conditions'])assert.ok(html.includes(text),text);
  assert.doesNotMatch(html,/Simulated activity suggestion/i);
  const data=planFixture();data.version.content.itinerary_entries=entries;
  for(const options of [{},{snapshot:true},{review:true}]){
    const page=renderPlan(data,options);
    assert.match(page,/Campsite nature observation and photography/i);assert.doesNotMatch(page,/Simulated activity suggestion/i);
    assert.match(page,/Subject to formal safety checks and on-site conditions/i);
  }
  assert.deepEqual(entries,before);
  const old=render(DailyItinerary,{entries:[{...base,description:'Synthetic rest and free-time block; no additional activities are assumed.'}],time:x=>x,label:x=>x});
  assert.doesNotMatch(old,/Campsite nature observation and photography|Simulated activity suggestion/i);
});


test('review revision preparation requires the active exact reviewed context and never treats approval as instructions',()=>{
  const data=planFixture();data.revision_available=true;data.run.is_active=true;data.plan.current_version_id=data.version.version_context.plan_version_id;
  const review={review_id:'review-source',decision:'REQUEST_REVISION',reason:'Change campsite and retain the confirmed budget.',reviewer_user_id:'founder',version_context:{...data.version.version_context}};
  data.reviews=[review];const before=structuredClone(data);
  assert.equal(revisionReview(data),review);
  for(const patch of [{revision_available:false},{run:{...data.run,is_active:false}},{trip_series:{is_current:false}},
      {reviews:[{...review,decision:'APPROVE'}]},{reviews:[{...review,version_context:{...review.version_context,run_id:'old'}}]},
      {reviews:[{...review,version_context:{...review.version_context,input_fingerprint:'different'}}]}])assert.equal(revisionReview({...data,...patch}),null);
  const html=renderPlan(data);
  assert.match(html,/Prepare revision using reviewer feedback/i);assert.match(html,/Use this reviewer feedback/i);assert.match(html,/Change campsite and retain the confirmed budget/i);
  assert.deepEqual(data,before);
});

test('assistance feedback is visible but cannot clear assessments or offer approval',()=>{
  const note={note_id:'n1',plan_id:'plan',run_id:'run',plan_version_id:'version',assessment_ids:['log','safe'],reviewer_user_id:'founder',decision:'WAITING_EVIDENCE',problem:'Missing weather dates.',reason:'Information does not cover all dates.',next_action:'Wait for updated sources, then recheck.',recheck_on:'2026-11-01',created_at:'2026-10-30',is_approval:false};
  const notes=[note,{...note,note_id:'n2',decision:'UNSUPPORTED',problem:'<img src=x onerror=alert(1)>',reason:'No registered data supports this qualifier.',next_action:'Choose a supported condition or keep the draft.',recheck_on:null}];
  const before=structuredClone(notes);
  const html=render(AssistanceNotes,{notes,historical:true});
  for(const text of ['Human assistance records for an earlier result','not approval','This arrangement is currently unsupported','Next','Choose a supported condition or keep the draft','Previous feedback','2026-11-01'])assert.ok(html.includes(text),text);
  assert.doesNotMatch(html,/<img|<button|Checks passed|Save final plan/i);assert.match(html,/&lt;img/i);
  assert.deepEqual(notes,before);
});

test('assistance form uses an explicit server flag and keeps mandatory restriction decisions separate',()=>{
  const data=planFixture();
  const show=value=>renderToStaticMarkup(h(MemoryRouter,null,h(SessionProvider,null,h(ReviewAssistanceForm,{data:value,refresh(){}}))));
  assert.equal(show(data),'');
  const html=show({...data,assistance_available:true});
  for(const text of ['Record assistance (not approval)','Specific issue','Evidence / reason','Your next step','Wait for information before rechecking','This arrangement is currently unsupported'])assert.ok(html.includes(text),text);
  assert.match(html,/disabled=""[^>]*>Save assistance notes/i);assert.doesNotMatch(html,/>Approve<|>Reject</i);
});

test('PDF download is an explicit action for an already saved final and does not issue a request during render',()=>{
  const html=render(FinalPdfDownload,{planId:'plan',finalId:'saved-final'});
  assert.match(html,/>Download saved plan PDF</i);assert.doesNotMatch(html,/<a |<iframe|Automatic|Model/i);
});



test('selected preference and hard requirements all receive explicit results while other facilities move below',()=>{
  const place=cataloguePlace('lane-cove','sydney-surrounds-2.2-2026-10-23');
  const requirements={preferences:['quiet','pets'],mandatory_constraints:['toilets','showers']};
  const reasons=['Destination region:Sydney & Surrounds, matches this selection.','Group size: this trip has 4 people; recorded capacity is 4 people.',
    'Required condition: Toilets, listed as supported.','Required condition: Showers, listed as supported.',
    'Campsite facilities: Toilets are listed as provided.','Campsite facilities: Showers are listed as provided.','Campsite facilities: Drinking water is listed as provided.'];
  const before=structuredClone({place,requirements,reasons});
  const projected=selectedRequirementsPresentation(reasons,requirements,place);
  assert.deepEqual(projected.rows.filter(row=>row.kind).map(row=>[row.label,row.kind,row.result]),[
    ['Toilets','Required conditions','Supported by recorded data'],['Showers','Required conditions','Supported by recorded data'],['Quiet surroundings','Preferences','Needs verification'],['Pets allowed','Preferences','Not met']]);
  assert.equal(projected.rows.some(row=>row.facility==='potable_water'),false);
  assert.equal(projected.extra[0].facility,'potable_water');
  const html=render(panels.PlanningExplanationPanel,{siteName:'Lane Cove',siteId:'lane-cove',catalogueId:'sydney-surrounds-2.2-2026-10-23',requirements,reasons,uncertainties:[]});
  const table=html.match(/<table[^>]*>.*?<\/table>/si)[0];
  for(const text of ['Toilets','Showers','Quiet surroundings','Pets allowed','Campsite records do not allow ordinary pets','Needs verification','Not met'])assert.ok(table.includes(text),text);
  assert.doesNotMatch(table,/Drinking water/i);
  assert.match(html,/<h3>Other campsite facilities<\/h3>.*?<dt>Drinking water<\/dt>/si);
  assert.deepEqual({place,requirements,reasons},before);
});

test('selected same facility merges categories while unknown, conflicting and unsupported choices never become satisfied',()=>{
  const requirements={preferences:['toilets','pets','quiet','Retain an unknown legacy preference'],mandatory_constraints:['toilets','walk_in_only','no_fires']};
  const facts=['Required condition: Toilets, listed as supported.','Campsite facilities: Toilets are unavailable; make alternative arrangements.'];
  const value=selectedRequirementsPresentation(facts,requirements,null,['step-free path']);
  const toilet=value.rows.filter(row=>row.facility==='toilets');assert.equal(toilet.length,1);
  assert.equal(toilet[0].kind,'Required conditions · Preferences');assert.equal(toilet[0].result,'Conflicting information');
  for(const name of ['Pets allowed','Quiet surroundings','Retain an unknown legacy preference','Walk-in access only','Step-free path']){
    assert.equal(value.rows.find(row=>row.label===name).result,'Needs verification',name);
  }
  assert.equal(value.rows.find(row=>row.label==='No campfire').result,'See the relevant checks');
  assert.equal(value.extra.length,0);
});

test('old catalogue versions cannot borrow new static facts and saved positive facts remain readable',()=>{
  const requirements={preferences:['pets','quiet'],mandatory_constraints:['showers']};
  const html=render(panels.PlanningExplanationPanel,{siteName:'Old site',siteId:'lane-cove',catalogueId:'old-version',requirements,reasons:['Required condition: Showers, listed as supported.'],uncertainties:[]});
  assert.match(html,/Showers.*?Supported by recorded data/si);
  assert.match(html,/Pets allowed.*?Needs verification/si);
  assert.match(html,/Quiet surroundings.*?Needs verification/si);
  assert.doesNotMatch(html,/Ordinary pets not allowed|Other campsite facilities|Getting there and important notes/i);
  const legacy=render(panels.PlanningExplanationPanel,{siteName:'Missing lists',requirements:{},reasons:['Required condition: Toilets, listed as supported.'],uncertainties:[]});
  assert.match(legacy,/Required for this trip/i);assert.doesNotMatch(legacy,/Compare each item/i);
});

test('every offered preference and mandatory condition is retained, including meals and safety-only intent',()=>{
  const requirements={preferences:['quiet','toilets','showers','potable water','public transport','wheelchair accessible','campfire','pets','self-catered meals'],
    mandatory_constraints:['toilets','showers','potable_water','wheelchair_accessible','fire_allowed','no_fires','pets_allowed','vehicle_access','public_transport_access','walk_in_only']};
  const value=selectedRequirementsPresentation([],requirements,cataloguePlace('the-basin','sydney-surrounds-2.2-2026-10-23'));
  for(const name of ['Toilets','Showers','Drinking water','Wheelchair access','Fire use allowed','No campfire','Pets allowed','Vehicle access','Public transport access','Walk-in access only','Quiet surroundings','Self-catered meals'])
    assert.ok(value.rows.some(row=>row.label===name),name);
  assert.equal(value.rows.find(row=>row.label==='Self-catered meals').result,'See the relevant checks');
  assert.equal(value.rows.find(row=>row.label==='Vehicle access').result,'Not met');
  assert.equal(value.rows.find(row=>row.label==='Wheelchair access').result,'Needs verification');
});

test('selected facilities stay in the main table even when saved and catalogue facts conflict',()=>{
  const props={siteName:'Bents Basin',siteId:'bents-basin',catalogueId:'sydney-surrounds-2.2-2026-10-23',
    requirements:{preferences:['potable water'],mandatory_constraints:[]},reasons:['Campsite facilities: Drinking water is listed as provided.'],uncertainties:[]};
  const html=render(panels.PlanningExplanationPanel,props);
  const table=html.match(/<table[^>]*>.*?<\/table>/si)[0];assert.match(table,/Conflicting information/i);
  const extra=html.match(/<h3>Other campsite facilities<\/h3>(.*?)<\/dl>/si)?.[1]??'';
  assert.doesNotMatch(extra,/Drinking water/i);
});

test('current, historical, final and reviewer views show confirmed choices without mutating or authorising outcomes',()=>{
  const data=planFixture();data.campsite_catalogue_id='sydney-surrounds-2.2-2026-10-23';
  data.confirmed_context.requirements.preferences=['quiet','pets'];data.confirmed_context.requirements.mandatory_constraints=['toilets','showers'];
  data.confirmed_context.profile_snapshot.accessibility_requirements=['step-free path'];
  data.version.content.selected_campsite_ids=['lane-cove'];
  data.recommendations={result:{search_outcome:'MATCHES',excluded_candidates:[],candidates:[{campsite_id:'lane-cove',rank:1,reasons:[],material_uncertainties:[]}]}};
  const before=structuredClone(data);
  for(const options of [{},{review:true},{snapshot:true}]){
    const html=renderPlan(data,options);
    for(const text of ['Complete confirmed requirements for this plan','Confirmed preferences and meal arrangement','Required conditions for this trip','Accessibility and other group needs for this trip','Quiet','Bring pets','Step-free path','confirmation snapshot used by this plan','Not met','Needs verification'])assert.ok(html.includes(text),text);
    const accessRow=html.match(/<tr><th scope="row">Step-free path(?:(?!<\/tr>)[\s\S])*<\/tr>/i)[0];
    assert.match(accessRow,/Needs verification/i);assert.doesNotMatch(accessRow,/Supported by recorded data/i);
  }
  assert.deepEqual(data,before);
  data.run.is_active=false;assert.match(renderPlan(data),/Complete confirmed requirements for this plan/i);
  data.confirmed_context.requirements.preferences=['<img src=x onerror=alert(1)>'];
  const escaped=renderPlan(data);assert.match(escaped,/&lt;img/i);assert.doesNotMatch(escaped,/<img/i);
  assert.deepEqual(before.eligibility,null);assert.equal(data.finalisation_available,false);
  assert.deepEqual(before.confirmed_context.requirements.preferences,['quiet','pets']);
});



test('unknown historic choice names that shadow JavaScript properties stay literal and unverified',()=>{
  const requirements={preferences:['__proto__','constructor','toString'],mandatory_constraints:[]};
  const rows=selectedRequirementsPresentation([],requirements,null).rows;
  assert.deepEqual(rows.map(row=>[row.label,row.result]),requirements.preferences.map(value=>[value,'Needs verification']));
  const data=planFixture();data.confirmed_context.requirements={...data.confirmed_context.requirements,...requirements};
  const html=renderPlan(data);for(const name of requirements.preferences)assert.ok(html.includes(name));
});
