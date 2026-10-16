import test from 'node:test';
import assert from 'node:assert/strict';
import {profileFocusId} from '../src/profile_focus.ts';

test('equipment correction targets missing capacity instead of a generic profile page',()=>{
  const tent={item_key:'tent',quantity:'1',capacity:'',confirmed:true,unit:'item'};
  assert.equal(profileFocusId('equipment.tent.capacity',[tent]),'gear-capacity-0');
  assert.equal(profileFocusId('equipment.vehicle.capacity',[tent]),'add-vehicle');
  assert.equal(profileFocusId('transport.estimated_km',[tent]),'estimated-km');
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
