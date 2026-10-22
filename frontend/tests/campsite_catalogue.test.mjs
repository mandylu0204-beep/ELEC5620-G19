import test from 'node:test';
import assert from 'node:assert/strict';
import {campName} from '../src/campsite_names.ts';
import {checkState,safetySummary} from '../src/plan_language.ts';

test('Sydney catalogue names resolve without reidentifying historical campsite records',()=>{
  const expected={
    'the-basin':'The Basin campground','bonnie-vale':'Bonnie Vale campground',
    'bents-basin':'Bents Basin campground',cattai:'Cattai campground',euroka:'Euroka campground',
    'lane-cove':'Lane Cove caravan park','putty-beach':'Putty Beach campground',
    'little-beach':'Little Beach campground','tallow-beach':'Tallow Beach campground',
    'cockatoo-island':'Cockatoo Island waterfront campground',
  };
  for(const [id,name] of Object.entries(expected))assert.equal(campName(id),name);
  assert.equal(campName('demo-wattle-rest'),'Demo Wattle Rest');
  assert.equal(campName('unregistered-campsite'),'unregistered-campsite');
});

test('estimated weather stays an estimate and unknown source prose is not reinterpreted',()=>{
  assert.equal(safetySummary('Estimated mild conditions.'),'天气预估：天气温和。');
  assert.equal(safetySummary('Mild synthetic conditions.'),'天气预估：天气温和。');
  assert.equal(safetySummary('No additional fire restriction recorded.'),'现有资料未注明额外营火限制。');
  assert.equal(safetySummary('Unverified unfamiliar weather text.'),null);
});

test('presentation changes preserve missing, conflicting and closed-road check states',()=>{
  assert.equal(checkState('WEATHER','MISSING',[]).title,'暂无适用资料');
  const record={kind:'ROAD',summary:null,source_date:'2026-10-23',status:'AVAILABLE',
    valid_from:'2026-10-23',valid_to:'2026-10-25',road_state:'CLOSED',source_refs:[]};
  assert.equal(checkState('ROAD','AVAILABLE',[record]).title,'道路关闭');
  assert.equal(checkState('ROAD','CONFLICTING',[{...record,status:'CONFLICTING'}]).title,'资料有冲突');
});
