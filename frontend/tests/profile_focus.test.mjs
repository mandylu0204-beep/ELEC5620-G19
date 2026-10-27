import test from 'node:test';
import assert from 'node:assert/strict';
import {profileFocusId,profileCorrectionTargets,focusProfileTargets} from '../src/profile_focus.ts';

test('equipment correction targets missing capacity instead of a generic profile page',()=>{
  const tent={item_key:'tent',quantity:'1',capacity:'',confirmed:true,unit:'item'};
  assert.equal(profileFocusId('equipment.tent.capacity',[tent]),'gear-capacity-0');
  assert.equal(profileFocusId('equipment.vehicle.capacity',[tent]),'add-vehicle');
  assert.equal(profileFocusId('transport.estimated_km',[tent]),'estimated-km');
  assert.equal(profileFocusId('transport.assumptions',[tent],'PUBLIC_TRANSPORT'),'transport-assumptions');
});
test('correction picks the incomplete duplicate record and respects unit/confirmation',()=>{
  const tent={item_key:'tent',quantity:'1',capacity:'2',confirmed:true,unit:'item'};
  assert.equal(profileFocusId('equipment.tent',[tent,{...tent,capacity:''}]),'gear-capacity-1');
  assert.equal(profileFocusId('equipment.tent',[{...tent,unit:'litre'}]),'gear-unit-0');
  assert.equal(profileFocusId('equipment.tent',[{...tent,confirmed:false}]),'gear-confirmed-0');
});
test('unknown or injected field names cannot select arbitrary elements',()=>{
  for(const field of ['#password','equipment.tent.capacity.extra','https://example.com','sessions.token'])assert.equal(profileFocusId(field,[]),null);
});

test('stale car links do not focus unrelated or hidden fields for non-car travel',()=>{
  for(const mode of ['PUBLIC_TRANSPORT','WALKING','OTHER',''])
    for(const field of ['transport.vehicle_count','transport.estimated_km','equipment.vehicle','equipment.vehicle.capacity'])
      assert.equal(profileFocusId(field,[],mode),null);
  assert.equal(profileFocusId('transport.vehicle_count',[],'CAR'),'add-vehicle');
});

test('summary deduplicates vehicle totals against editable fields and never targets an absent vehicle-unit control',()=>{
  const vehicle={item_key:'vehicle',quantity:'',capacity:'',confirmed:false,unit:'vehicle'};
  assert.deepEqual(profileCorrectionTargets({'vehicle-count':'数量未知','gear-quantity-0':'填写数量','gear-capacity-0':'填写座位'},[vehicle]),
    ['gear-quantity-0','gear-capacity-0']);
  assert.deepEqual(profileCorrectionTargets({'vehicle-count':'请添加车辆'},[]),['add-vehicle']);
  assert.equal(profileFocusId('equipment.vehicle',[{...vehicle,unit:'item'}],'CAR'),'gear-quantity-0');
  assert.deepEqual(profileCorrectionTargets({'gear-unit-0':'旧车辆单位错误'},[vehicle]),['gear-quantity-0']);
});

test('navigation focuses and scrolls an actual enabled input, skipping missing and disabled targets',()=>{
  const calls=[];
  const target={focus(){calls.push('focus');},scrollIntoView(options){calls.push(options);}};
  const nodes={disabled:{...target,disabled:true},'gear-quantity-0':target};
  assert.equal(focusProfileTargets(['vehicle-count','disabled','gear-quantity-0'],id=>nodes[id]??null),true);
  assert.deepEqual(calls,['focus',{block:'center'}]);
  assert.equal(focusProfileTargets(['missing','disabled'],id=>nodes[id]??null),false);
});
