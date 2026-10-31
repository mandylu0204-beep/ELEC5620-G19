import test from 'node:test';
import assert from 'node:assert/strict';
import {equipmentForSave,equipmentPayload} from '../src/equipment_confirmation.ts';
import {profileGuidance} from '../src/profile_guidance.ts';
import {profileFocusId} from '../src/profile_focus.ts';

const gear=(patch={})=>({item_key:'tent',label:'Two-person tent',quantity:'1',unit:'item',capacity:'2',confirmed:false,...patch});
test('explicit save confirms entered stock but does not mutate loaded facts or fill unknown capacities',()=>{
  const rows=[gear(),gear({label:'Three-person tent',capacity:'3'}),gear({quantity:'1',capacity:''})];
  const original=structuredClone(rows);const payload=equipmentPayload(rows);
  assert.deepEqual(rows,original);
  assert.ok(rows.every(item=>!item.confirmed));
  assert.deepEqual(payload.map(item=>[item.quantity,item.capacity_persons,item.confirmed]),[[1,2,true],[1,3,true],[1,null,true]]);
});
test('zero means no stock; blank stays unknown even if a stale saved flag was true',()=>{
  const payload=equipmentPayload([gear({quantity:'0'}),gear({quantity:'',confirmed:true})]);
  assert.deepEqual(payload.map(item=>[item.quantity,item.confirmed]),[[0,true],[null,false]]);
});
test('invalid stock and capacity are never converted into an accepted profile payload',()=>{
  for(const quantity of ['-1','1.5','Infinity','NaN','9007199254740992',' ']){
    assert.equal(equipmentForSave([gear({quantity})])[0].confirmed,false);
    assert.throws(()=>equipmentPayload([gear({quantity})]),/valid whole numbers/i);
  }
  assert.throws(()=>equipmentPayload([gear({capacity:'0'})]),/valid whole numbers/i);
});
test('historical plan availability keeps its original explicit confirmation',()=>{
  for(const item_key of ['transport_itinerary','fire_free_meal_plan'])for(const confirmed of [false,true]){
    const row=gear({item_key,confirmed});
    assert.equal(equipmentForSave([row])[0].confirmed,confirmed);
  }
});
test('new form guidance and navigation target editable quantities instead of a removed checkbox',()=>{
  const rows=[gear({quantity:'',capacity:''})];
  const draft={equipment:equipmentForSave(rows),quantityConfirmsEquipment:true,transport:'CAR',vehicles:'1',km:'',children:'no',childrenCount:'0',experience:'BEGINNER'};
  const issue={field:'equipment.tent',target:'PROFILE',category:'USER_INPUT'};
  const hints=profileGuidance(draft,[issue]);
  assert.ok(hints['gear-quantity-0']);assert.ok(hints['gear-capacity-0']);assert.equal(hints['gear-confirmed-0'],undefined);
  assert.equal(profileFocusId('equipment.tent',[gear()],undefined,false,true),'gear-quantity-0');
  const vehicle=gear({item_key:'vehicle',unit:'vehicle'});
  assert.equal(profileFocusId('equipment.vehicle',[vehicle],'CAR',false,true),'gear-quantity-0');
});

test('vehicle save confirms entered count without inventing seat capacity or converting unknown count to available',()=>{
  const rows=[gear({item_key:'vehicle',unit:'vehicle',quantity:'2',capacity:'5'}),
    gear({item_key:'vehicle',unit:'vehicle',quantity:'1',capacity:''}),
    gear({item_key:'vehicle',unit:'vehicle',quantity:'',capacity:'7',confirmed:true}),
    gear({item_key:'vehicle',unit:'vehicle',quantity:'0',capacity:''})];
  const before=structuredClone(rows);
  const payload=equipmentPayload(rows);
  assert.deepEqual(payload.map(item=>[item.quantity,item.capacity_persons,item.confirmed]),[[2,5,true],[1,null,true],[null,7,false],[0,null,true]]);
  assert.deepEqual(rows,before);
  const draft={equipment:equipmentForSave([rows[2]]),quantityConfirmsEquipment:true,transport:'CAR',vehicles:'',km:'',children:'no',childrenCount:'0',experience:'BEGINNER'};
  const hints=profileGuidance(draft,[{field:'equipment.vehicle',target:'PROFILE',category:'USER_INPUT'}]);
  assert.ok(hints['gear-quantity-0']);assert.equal(hints['gear-confirmed-0'],undefined);
});
