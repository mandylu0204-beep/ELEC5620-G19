import test from 'node:test';
import assert from 'node:assert/strict';
import {prepareProfileEquipment,vehicleCount} from '../src/vehicle_profile.ts';
import {profileFocusId} from '../src/profile_focus.ts';

const car=(quantity,capacity='5',confirmed=false)=>({item_key:'vehicle',label:'车辆',quantity,capacity,confirmed,unit:'vehicle'});

test('transport count seeds an unconfirmed vehicle draft without inventing seats or ownership',()=>{
  const rows=prepareProfileEquipment([],'CAR','2');
  assert.deepEqual(rows,[car('2','')]);
  assert.equal(vehicleCount(rows),'2');
  assert.deepEqual(prepareProfileEquipment([],'PUBLIC_TRANSPORT',''),[{
    item_key:'transport_itinerary',label:'往返及接驳计划',quantity:'',unit:'plan',capacity:'',confirmed:false,
  }]);
});

test('different car groups retain separate seat capacity and confirmation while sharing one total',()=>{
  const original=[car('1','5',true),car('2','7')];
  const rows=prepareProfileEquipment(original,'CAR','99');
  assert.deepEqual(rows,original);
  assert.equal(vehicleCount(rows),'3');
  assert.equal(vehicleCount([car('1'),car('')]),'');
  assert.equal(vehicleCount([car('0')]),'');
  assert.equal(vehicleCount([car('9007199254740992')]),'');
});

test('phone inventory is removed from the editable draft without altering the saved source',()=>{
  const phone={item_key:'charged_phone',label:'phone',quantity:'2',capacity:'',confirmed:true,unit:'item'};
  const input=[phone,car('1','5',true)];
  assert.deepEqual(prepareProfileEquipment(input,'CAR','1'),[input[1]]);
  assert.equal(input.length,2);
});

test('vehicle count and missing seats navigate to the actual transport form fields',()=>{
  assert.equal(profileFocusId('equipment.vehicle.capacity',[car('1','')]),'gear-capacity-0');
  assert.equal(profileFocusId('transport.vehicle_count',[car('','')]),'gear-quantity-0');
  assert.equal(profileFocusId('transport.vehicle_count',[]),'add-vehicle');
});

test('public-transport preparation preserves existing plans and never confirms them or removes saved vehicles',()=>{
  const plan={item_key:'transport_itinerary',label:'My return trip',quantity:'1',unit:'plan',capacity:'',confirmed:true};
  const rows=[car('2'),plan];const original=structuredClone(rows);
  assert.deepEqual(prepareProfileEquipment(rows,'PUBLIC_TRANSPORT','2'),original);
  assert.deepEqual(rows,original);
  const unknown=prepareProfileEquipment([car('2')],'PUBLIC_TRANSPORT','2');
  assert.equal(unknown[1].confirmed,false);assert.equal(unknown[1].quantity,'');
});
