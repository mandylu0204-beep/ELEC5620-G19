import {englishSavedActivity} from '../src/legacy_activity_descriptions.ts';
import test,{after} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createElement as h} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {createServer} from 'vite';
import {addDays,dateFieldError,endDateMinimum,firstFutureDate,sydneyToday,validIsoDate} from '../src/calendar_dates.ts';
import {legacyEquipmentName} from '../src/legacy_equipment_names.ts';
const server=await createServer({configFile:false,envDir:false,server:{middlewareMode:true,hmr:false,ws:false,watch:null},optimizeDeps:{noDiscovery:true}});
after(()=>server.close());
const {TripPreparation,preparationOrigin}=await server.ssrLoadModule('/src/trip_preparation.tsx');
const {DailyItinerary}=await server.ssrLoadModule('/src/daily_itinerary.tsx');
const {RequirementChoices}=await server.ssrLoadModule('/src/requirement_choices.tsx');
const {GroupSizeField,ProfileSummary,displayEquipmentName,addEquipment}=await server.ssrLoadModule('/src/profile.tsx');
const {profileChanges}=await server.ssrLoadModule('/src/profile_changes.ts');
const {requestPayload,RequestFields,clarificationText,requestClarificationField}=await server.ssrLoadModule('/src/requests.tsx');
const render=(component,props)=>renderToStaticMarkup(h(component,props));
const minimum='2026-11-01';

test('date minimum follows Sydney midnight, leap years and month/year rollover',()=>{
 assert.equal(sydneyToday(new Date('2026-10-31T12:59:59Z')),'2026-10-31');
 assert.equal(sydneyToday(new Date('2026-10-31T13:00:00Z')),'2026-11-01');
 assert.equal(firstFutureDate(undefined,new Date('2026-10-31T00:00:00Z')),minimum);
 assert.equal(firstFutureDate('2026-11-10',new Date('2026-10-31T00:00:00Z')),'2026-11-11');
 assert.equal(addDays('2026-12-31',1),'2027-01-01');assert.equal(addDays('2028-02-28',1),'2028-02-29');
 assert.equal(validIsoDate('2026-02-29'),false);assert.equal(validIsoDate('2028-02-29'),true);
});

test('manual dates and native selections share the same lower bound; blank drafts remain allowed',()=>{
 assert.equal(dateFieldError('',minimum),'');assert.equal(dateFieldError(minimum,minimum),'');
 assert.match(dateFieldError('2026-10-31',minimum),/on or after 2026-11-01/);
 assert.match(dateFieldError('2026-10-30',minimum),/on or after/);assert.match(dateFieldError('31/10/2026',minimum),/YYYY-MM-DD/);
 assert.equal(endDateMinimum('2026-11-03',minimum),'2026-11-04');assert.equal(endDateMinimum('2026-10-20',minimum),minimum);
 const draft={raw:'',destination:'Sydney',start:'2026-10-31',end:'',nights:'1',days:'',budget:'300',preferences:'',constraints:''};
 assert.throws(()=>requestPayload(draft,minimum),/on or after/);assert.throws(()=>requestPayload({...draft,start:minimum,end:minimum},minimum),/2026-11-02/);
 assert.equal(requestPayload({...draft,start:minimum},minimum).explicit_fields.start_date,minimum);
 assert.equal(requestPayload({...draft,start:''},minimum).explicit_fields.start_date,null);
});

test('native browser date controls keep their locale and enforce start and end minimum dates',()=>{
 const form=render(RequestFields,{draft:{raw:'',destination:'',start:minimum,end:'',nights:'',days:'',budget:'',preferences:'',constraints:''},set(){},regions:[],disabled:false,minimumStart:minimum});
 assert.match(form,/id="request-start" type="date" min="2026-11-01"/);
 assert.match(form,/id="request-end" type="date" min="2026-11-02"/);
 assert.doesNotMatch(form,/date-calendar|role="dialog"|lang=/);
});

test('legacy server labels display in English without rewriting selected facts or supplied aliases',()=>{
 const choices=[{value:'quiet',label:'\u5b89\u9759\u7684\u73af\u5883',aliases:['quiet','\u5b89\u9759\u7684\u73af\u5883']},
 {value:'step-free path',label:'\u9700\u8981\u65e0\u53f0\u9636\u901a\u9053',aliases:['step-free path']}];const before=structuredClone(choices);
 const html=render(RequirementChoices,{id:'test-choices',title:'Requirements',value:'quiet',choices,onChange(){}});
 assert.match(html,/Quiet/);assert.match(html,/Step-free path/);assert.match(html,/checked=""/);assert.doesNotMatch(html,/[\u3400-\u9fff]/u);assert.deepEqual(choices,before);
});

test('known legacy defaults and ordinals are translated without guessing custom names or capacity',()=>{
 assert.equal(legacyEquipmentName('tent','\u5e10\u7bf7\u4e00','Tent'),'Tent 1');assert.equal(displayEquipmentName('tent','\u5e10\u7bf7\u5341\u4e8c'),'Tent 12');
 assert.equal(displayEquipmentName('groundsheet','\u5730\u5e03'),'Groundsheet');assert.equal(displayEquipmentName('tent','\u7ea2\u8272\u5e10\u7bf7'),'\u7ea2\u8272\u5e10\u7bf7');
 assert.equal(displayEquipmentName('other','\u5e10\u7bf7\u4e00'),'\u5e10\u7bf7\u4e00');
 const items=[{item_key:'tent',label:'\u5e10\u7bf7\u4e00',quantity:'1',unit:'item',capacity:'2',confirmed:true}],before=structuredClone(items);
 assert.equal(addEquipment(items,'tent')[1].label,'Tent 2');assert.deepEqual(items,before);
});

test('saved summaries and update comparisons show English defaults while keeping original snapshots immutable',()=>{
 const before={group_size:2,experience_level:'BEGINNER',has_children:false,children_count:0,equipment:[
 {item_key:'tent',label:'\u5e10\u7bf7\u4e00',quantity:1,unit:'item',capacity_persons:2,confirmed:true},
 {item_key:'transport_itinerary',label:'\u4ea4\u901a\u8fde\u63a5\u8ba1\u5212',quantity:1,unit:'plan',capacity_persons:null,confirmed:true}],transport:{transport_type:'CAR',vehicle_count:1,estimated_km:'100',assumptions:[]},accessibility_requirements:['\u9700\u8981\u65e0\u53f0\u9636\u901a\u9053']};
 const original=structuredClone(before),after=structuredClone(before);after.equipment[0].quantity=2;const html=render(ProfileSummary,{profile:before});
 for(const text of ['Tent 1','Transport connection plan','Step-free path'])assert.ok(html.includes(text),text);assert.doesNotMatch(html,/[\u3400-\u9fff]/u);
 const changes=profileChanges(before,after);assert.equal(changes.length,1);assert.match(changes[0].before[0],/Tent 1/);assert.match(changes[0].after[0],/Tent 1/);
 assert.deepEqual(before,original);assert.deepEqual(profileChanges(before,structuredClone(before)),[]);
});

test('required badge remains red, becomes compact and shares a stable label row height',()=>{
 const html=render(GroupSizeField,{value:'2',revealValidation:false,onTouch(){},onChange(){}});
 assert.match(html,/required-field-label/);assert.match(html,/<span class="required-mark">Required/);
 const css=readFileSync(new URL('../src/styles.css',import.meta.url),'utf8');
 assert.match(css,/\.group-information \.required-mark\{font-size:10px/);assert.match(css,/color:#9c3026;background:#fff0ed;border:1px solid #d78c82/);
 assert.match(css,/\.group-information \.form-grid>div>label\{min-height:2.8em/);
});

test('historical clarification messages display in English and meal guidance targets the meal selector',()=>{
 const meal='\u8bf7\u9009\u62e9\u7528\u9910\u65b9\u5f0f\uff1a\u5373\u98df\u9910\u98df\u6216\u81ea\u884c\u70f9\u996a\u3002';
 const start='\u8bf7\u586b\u5199\u5f00\u59cb\u65e5\u671f\u3002';
 assert.equal(clarificationText('meal_mode',meal,undefined),'Choose a meal arrangement: ready-to-eat or self-catered meals.');
 assert.equal(clarificationText('start_date',start,undefined),'Enter a start date.');
 assert.equal(requestClarificationField('preferences',meal),'meal_mode');
 assert.equal(requestClarificationField('preferences[0]','\u7528\u9910\u65b9\u5f0f\u540c\u65f6\u5305\u542b\u5373\u98df\u9910\u98df\u548c\u81ea\u884c\u70f9\u996a\uff0c\u8bf7\u660e\u786e\u672c\u6b21\u91c7\u7528\u54ea\u4e00\u79cd\u3002'),'meal_mode');
 assert.equal(clarificationText('duration_days','2 \u665a\u5e94\u4e3a 3 \u5929\uff0c\u8bf7\u4fee\u6539\u51b2\u7a81\u7684\u5929\u6570\u3002',undefined),'2 nights should span 3 days. Correct the conflicting duration.');
 assert.equal(clarificationText('end_date','\u7ed3\u675f\u65e5\u671f\u5e94\u4e3a 2026-11-04\uff0c\u8bf7\u4fee\u6539\u51b2\u7a81\u7684\u65e5\u671f\u3002',undefined),'End date should be 2026-11-04. Correct the conflicting date.');
});

test('legacy message projection preserves current English messages, unknown prose and saved facts',()=>{
 const historical={field:'start_date',message:'\u8bf7\u586b\u5199\u5f00\u59cb\u65e5\u671f\u3002'};const original=structuredClone(historical);
 clarificationText(historical.field,historical.message,undefined);assert.deepEqual(historical,original);
 assert.equal(clarificationText('start_date','Enter a start date.',undefined),'Enter a start date.');
 assert.equal(clarificationText('preferences','\u7528\u6237\u81ea\u5b9a\u4e49\u7684\u8981\u6c42',undefined),'\u7528\u6237\u81ea\u5b9a\u4e49\u7684\u8981\u6c42');
 assert.equal(requestClarificationField('preferences','\u7528\u6237\u81ea\u5b9a\u4e49\u7684\u8981\u6c42'),'preferences');
});

test('all frozen legacy activity descriptions have exact English displays without changing activity versions or unknown entries',()=>{
 for(const version of [1,2]){
  const fixture=JSON.parse(readFileSync(new URL(`../../data/planning/camp_activities_v${version}.json`,import.meta.url),'utf8'));const before=structuredClone(fixture);
  for(const item of fixture.activities){
   const saved=item.title+'\uff1a'+item.description+'\uff08\u6a21\u62df\u6d3b\u52a8\u5efa\u8bae\uff1b\u987b\u4ee5\u6b63\u5f0f\u5b89\u5168\u68c0\u67e5\u548c\u73b0\u573a\u6761\u4ef6\u4e3a\u51c6。\uff09';
   const english=englishSavedActivity(saved,item.campsite_id,'ACTIVITY');assert.ok(english,item.activity_id);assert.doesNotMatch(english,/[\u3400-\u9fff]/u);
   const html=render(DailyItinerary,{entries:[{entry_kind:'ACTIVITY',start_at:'2026-11-04T13:00:00+11:00',end_at:'2026-11-04T16:00:00+11:00',campsite_id:item.campsite_id,description:saved}],time:x=>x,label:x=>x});
   assert.doesNotMatch(html,/[\u3400-\u9fff]/u);assert.match(html,/English display of a saved activity suggestion/);assert.match(html,/Subject to formal safety checks and on-site conditions/);
   assert.equal(englishSavedActivity(saved,'unrelated-campsite','ACTIVITY'),null);assert.equal(englishSavedActivity(saved,item.campsite_id,'CAMP'),null);
   assert.equal(englishSavedActivity(saved+' Extra unknown content.',item.campsite_id,'ACTIVITY'),null);assert.equal(englishSavedActivity(english,item.campsite_id,'ACTIVITY'),null);
   if(version===1&&item.activity_id==='lane-cove-facilities')assert.doesNotMatch(english,/game|colour/i,'v1 must not acquire v2 games');
  }
  assert.deepEqual(fixture,before);
 }
});

test('known fixed Sydney origin displays in English without changing stored origin or transport figures',()=>{
 for(const origin_label of ['\u6089\u5c3c\u5e02\u533a\uff08\u56fa\u5b9a\u6a21\u62df\u51fa\u53d1\u5730\uff09','\u6089\u5c3c\u5e02\u533a \uff08\u56fa\u5b9a\u6a21\u62df\u51fa\u53d1\u5730\uff09','Central Sydney (fixed demonstration origin)']){
  const value={system_preparation:true,transport_type:'CAR',origin_label,access_and_capacity:true,estimated_total_vehicle_km:'200',vehicle_count:2,estimated_transport_cents:7600,meal_mode:'SELF_CATERED',source_refs:[]};const before=structuredClone(value);
  const html=render(TripPreparation,{value});assert.match(html,/Departure point: Sydney CBD./);assert.doesNotMatch(html,/[\u3400-\u9fff]/u);
  for(const text of ['200 km','2 vehicles','76.00'])assert.ok(html.includes(text));assert.deepEqual(value,before);
 }
 assert.equal(preparationOrigin('\u7528\u6237\u6307\u5b9a\u51fa\u53d1\u5730'),'\u7528\u6237\u6307\u5b9a\u51fa\u53d1\u5730');
});
