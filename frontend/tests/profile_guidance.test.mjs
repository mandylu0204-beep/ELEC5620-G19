import test from 'node:test';
import assert from 'node:assert/strict';
import {prepareMissingEquipment,profileGuidance} from '../src/profile_guidance.ts';
import {logisticsDestinations} from '../src/logistics_navigation.ts';

const catalog=[['tent','帐篷','item'],['vehicle','车辆','vehicle'],['sleeping_bag','睡袋','item'],['camping_stove','炉具','item']];
const issue=(field,code='EQUIPMENT_DETAILS',extra={})=>({issue_id:field,code,category:'USER_INPUT',field,
  item_key:field.startsWith('equipment.')?field.split('.')[1]:null,target:'PROFILE',current:null,required:null,
  action_url:'/profile?focus='+encodeURIComponent(field)+'&request_id=r&plan_id=p',...extra});
const draft=(equipment=[],extra={})=>({equipment,transport:'CAR',vehicles:'1',km:'100',children:'no',childrenCount:'0',experience:'BEGINNER',...extra});
const tent={item_key:'tent',label:'帐篷',quantity:'1',unit:'item',capacity:'',confirmed:true};

test('conditional cooking preparation creates two blank rows together without confirmation, duplication or fake blockers',()=>{
  const cookingCatalog=[...catalog,['fuel_canister','燃料罐','item']];
  const root=issue('cooking_method','COOKING_ARRANGEMENT',{target:'REQUEST',related_equipment:['camping_stove','fuel_canister']});
  const prepared=prepareMissingEquipment([], [root], '',cookingCatalog);
  assert.deepEqual(prepared.map(row=>row.item_key),['camping_stove','fuel_canister']);
  for(const row of prepared)assert.deepEqual([row.quantity,row.capacity,row.confirmed],['','',false]);
  assert.deepEqual(profileGuidance(draft(prepared),[root]),{});
  assert.equal(prepareMissingEquipment(prepared,[root],'',cookingCatalog),prepared);
  assert.equal(prepareMissingEquipment([],[],'',cookingCatalog,['camping_stove','fuel_canister']).length,2);
  assert.deepEqual(prepareMissingEquipment([],[{...root,code:'PRICE_DATA',category:'DATA_GAP'}],'',cookingCatalog),[]);
});

test('one visit prepares every known missing item without filling inventory facts or altering existing input',()=>{
  const original=[{...tent}];
  const result=prepareMissingEquipment(original,[issue('equipment.tent.capacity'),issue('equipment.vehicle.capacity'),
    issue('equipment.sleeping_bag.quantity'),issue('equipment.vehicle.capacity')],'equipment.tent.capacity',catalog);
  assert.deepEqual(result.map(item=>item.item_key),['tent','vehicle','sleeping_bag']);
  assert.deepEqual(original,[tent]);
  for(const item of result.slice(1))assert.deepEqual([item.quantity,item.capacity,item.confirmed],['','',false]);
  assert.equal(prepareMissingEquipment(result,[issue('equipment.vehicle.capacity')],'',catalog),result);
});

test('cooking alternate entry prepares the stove, while data problems and unsupported keys create no inventory',()=>{
  assert.equal(prepareMissingEquipment([],[],'equipment.camping_stove',catalog)[0].item_key,'camping_stove');
  const result=prepareMissingEquipment([],[issue('equipment.vehicle','EQUIPMENT_DETAILS',{category:'DATA_GAP'}),
    issue('equipment.unregistered'),issue('equipment.tent.capacity.extra')],'#password',catalog);
  assert.deepEqual(result,[]);
});

test('tent capacity is highlighted without asking again for already confirmed quantity',()=>{
  const hints=profileGuidance(draft([tent]),[issue('equipment.tent.capacity')]);
  assert.deepEqual(Object.keys(hints),['gear-capacity-0']);
  assert.match(hints['gear-capacity-0'],/双人帐填写 2/);
});

test('vehicle draft highlights all actual missing fields and explains seats including driver',()=>{
  const equipment=prepareMissingEquipment([],[issue('equipment.vehicle.capacity','VEHICLE_DETAILS')],'',catalog);
  const hints=profileGuidance(draft(equipment,{vehicles:''}),[issue('equipment.vehicle.capacity','VEHICLE_DETAILS')]);
  for(const id of ['gear-quantity-0','gear-capacity-0','gear-confirmed-0','vehicle-count'])assert.ok(hints[id],id);
  assert.match(hints['gear-capacity-0'],/包含驾驶员/);
  const updated=equipment.map(item=>({...item,quantity:'1',capacity:'5',confirmed:true}));
  assert.deepEqual(profileGuidance(draft(updated),[issue('equipment.vehicle.capacity','VEHICLE_DETAILS')]),{});
});

test('editing one field clears only its own missing prompt and preserves other unfinished inputs',()=>{
  const item={...tent,quantity:'',confirmed:false};
  let hints=profileGuidance(draft([item]),[issue('equipment.tent.capacity')]);
  assert.ok(hints['gear-quantity-0']&&hints['gear-capacity-0']&&hints['gear-confirmed-0']);
  item.quantity='1';
  hints=profileGuidance(draft([item]),[issue('equipment.tent.capacity')]);
  assert.ok(!hints['gear-quantity-0']&&hints['gear-capacity-0']&&hints['gear-confirmed-0']);
});

test('honest zero stock does not ask users to confirm nonexistent equipment or invent capacity',()=>{
  const item={...tent,quantity:'0',confirmed:false};
  const hints=profileGuidance(draft([item]),[issue('equipment.tent.quantity')]);
  assert.deepEqual(hints,{});
  const shortage=profileGuidance(draft([item]),[issue('equipment.tent.quantity','EQUIPMENT_SHORTAGE',{required:{quantity:'1'}})]);
  assert.ok(shortage['gear-quantity-0']);
  assert.ok(!shortage['gear-confirmed-0']&&!shortage['gear-capacity-0']);
});

test('quantity unit, seat shortage, vehicle count and trip kilometres get distinct guidance',()=>{
  const car={item_key:'vehicle',label:'车辆',quantity:'1',unit:'item',capacity:'2',confirmed:true};
  const hints=profileGuidance(draft([car],{vehicles:'2',km:''}),[
    issue('equipment.vehicle.capacity','TRANSPORT_CAPACITY',{required:3}),issue('transport.estimated_km','DISTANCE')]);
  assert.match(hints['gear-unit-0'],/辆/);
  assert.match(hints['gear-capacity-0'],/本次需 3 人/);
  assert.match(hints['vehicle-count'],/共 1 辆/);
  assert.match(hints['estimated-km'],/包含往返/);
});

test('experience and child questions highlight the correct fields without assigning answers',()=>{
  const value=draft([],{children:'unknown',childrenCount:'',experience:''});
  const questions=[issue('profile.has_children','CHILDREN'),issue('profile.experience_level','EXPERIENCE')];
  assert.deepEqual(Object.keys(profileGuidance(value,questions)),['has-children','experience']);
  assert.equal(value.children,'unknown');
  value.children='yes';
  assert.ok(profileGuidance(value,questions)['children-count']);
});

test('header navigation keeps correction context, supports stove alternative and separates source gaps',()=>{
  const profile=issue('equipment.tent.capacity');
  const cooking=issue('meal_mode','COOKING_ARRANGEMENT',{target:'REQUEST',action_url:'/request?copy_from=r&focus=request-meal',
    alternate_action_url:'/profile?focus=equipment.camping_stove&request_id=r&plan_id=p'});
  assert.equal(logisticsDestinations([profile,cooking]).profile,profile.action_url);
  assert.equal(logisticsDestinations([cooking]).profile,cooking.alternate_action_url);
  assert.equal(logisticsDestinations([cooking]).request,cooking.action_url);
  assert.deepEqual(logisticsDestinations([issue('evidence.weather','WEATHER_DATA',{target:'SAFETY',action_url:null})]),{profile:null,request:null,safety:true});
  assert.equal(logisticsDestinations([issue('equipment.tent','EQUIPMENT_DETAILS',{action_url:'https://example.com'})]).profile,null);
});

test('tent correction uses current confirmed sleeping capacity instead of stale required tent count',()=>{
  const previous=issue('equipment.tent.quantity','EQUIPMENT_SHORTAGE',{required:{quantity:'2',capacity_persons:2}});
  const small={...tent,capacity:'1'};
  assert.match(profileGuidance(draft([small]),[previous])['gear-quantity-0'],/共可住 1 人，本次需 2 人/);
  assert.deepEqual(profileGuidance(draft([{...small,capacity:'2'}]),[previous]),{});
  assert.ok(profileGuidance(draft([{...small,capacity:'2',confirmed:false}]),[previous])['gear-confirmed-0']);
  assert.match(profileGuidance(draft([{...small,capacity:'2'}],{group:'3'}),[previous])['gear-quantity-0'],/本次需 3 人/);
  assert.deepEqual(profileGuidance(draft([small,{...small}]),[previous]),{});
});
