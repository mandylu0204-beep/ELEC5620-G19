import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {createRequire} from 'node:module';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {transpileModule,ModuleKind,JsxEmit} from 'typescript';
import {createElement} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {groupSafetyAdvice,safetyAdvice} from '../src/safety_advisory.ts';

const require=createRequire(import.meta.url);
const componentUrl=new URL('../src/safety_advisory_panel.tsx',import.meta.url);
const source=await readFile(componentUrl,'utf8');
const compiled=transpileModule(source,{fileName:fileURLToPath(componentUrl),
  compilerOptions:{module:ModuleKind.ESNext,jsx:JsxEmit.ReactJSX}}).outputText
  .replaceAll('"react/jsx-runtime"',JSON.stringify(pathToFileURL(require.resolve('react/jsx-runtime')).href))
  .replaceAll("'./safety_advisory'",JSON.stringify(new URL('../src/safety_advisory.ts',import.meta.url).href))
  .replaceAll("'./visitor_text.ts'",JSON.stringify(new URL('../src/visitor_text.ts',import.meta.url).href))
  .replaceAll("'./display_facts'",JSON.stringify(new URL('../src/display_facts.ts',import.meta.url).href));
const {SafetyAdvisoryPanel}=await import('data:text/javascript;base64,'+Buffer.from(compiled).toString('base64'));

const binding={runId:'private-run',versionId:'private-version',assessmentId:'private-safety',
  logisticsId:'private-logistics',inputFingerprint:'private-input-hash'};
function fixture(){return {kind:'SAFETY',run_id:binding.runId,plan_version_id:binding.versionId,
  assessment_id:binding.assessmentId,depends_on_assessment_id:binding.logisticsId,input_fingerprint:binding.inputFingerprint,
  audit_id:'private-audit',attempt_id:'private-attempt',trace:{requested_model:'private-model',usage:{total_tokens:123}},
  plan:{decision_summary_unverified:'Check the registered conditions before departure.',
    findings:[{finding_key:'road',fact_refs:['/baseline/evidence/0'],action_code:'CHANGE_TRIP',
      interpretation_unverified:'The recorded access restriction needs attention.',action_unverified:'Choose another accessible campsite.'},
      {finding_key:'weather',fact_refs:['/baseline/evidence/1'],action_code:'CHECK_NEAR_DEPARTURE',
        interpretation_unverified:'The forecast window needs a later check.',action_unverified:'Check again near departure.'}],
    action_priority:['weather','road']}};}
const render=(value=fixture(),options={})=>renderToStaticMarkup(createElement(SafetyAdvisoryPanel,{value,binding,...options}));

test('compact advice is displayed once and does not invent a second explanation',()=>{
  const value=fixture();value.advice_format='single-advice-v1';
  for(const item of value.plan.findings)item.interpretation_unverified=item.action_unverified;
  const html=render(value);
  for(const item of value.plan.findings)assert.equal(html.split(item.action_unverified).length-1,1);
  assert.equal(safetyAdvice(value,binding).items.length,2);
});

test('compact advice with a localized original is not repeated inside details',()=>{
  const value=fixture();value.advice_format='single-advice-v1';
  for(const item of value.plan.findings)item.interpretation_unverified=item.action_unverified='Check this arrangement before departure.';
  assert.equal(render(value).split('Check this arrangement before departure.').length-1,2);
});

test('unknown advice formats and mismatched compact compatibility fields fail closed',()=>{
  const unknown=fixture();unknown.advice_format='future-format';
  assert.equal(safetyAdvice(unknown,binding),null);
  const mismatch=fixture();mismatch.advice_format='single-advice-v1';
  assert.equal(safetyAdvice(mismatch,binding),null);
});

test('no model audit means no model label or fabricated advice',()=>{
  assert.equal(safetyAdvice(undefined,binding),null);
  assert.equal(render(undefined,{value:null}), '');
  assert.equal(render(fixture(),{binding:null}), '');
});

test('old run, version, assessment, dependency or fingerprint cannot be displayed as current advice',()=>{
  for(const field of ['run_id','plan_version_id','assessment_id','depends_on_assessment_id','input_fingerprint','kind']){
    const value={...fixture(),[field]:'other'};
    assert.equal(safetyAdvice(value,binding),null,field);
    assert.equal(render(value),'',field);
  }
});

test('advice follows the complete saved priority instead of array order',()=>{
  const view=safetyAdvice(fixture(),binding);
  assert.deepEqual(view.items.map(item=>item.title),['Recheck near departure','Change campsite, dates or activities']);
  const html=render();
  assert.ok(html.indexOf('Check again near departure.')<html.indexOf('Choose another accessible campsite.'));
});

test('missing, duplicated or unknown priorities and actions fail closed',()=>{
  for(const mutate of [
    value=>value.plan.action_priority=['weather','weather'],
    value=>value.plan.action_priority=['weather','unknown'],
    value=>value.plan.action_priority=['weather'],
    value=>value.plan.findings[0].action_code='AUTO_APPROVE',
    value=>value.plan.findings[0]=null,
  ]){
    const value=fixture();mutate(value);assert.equal(safetyAdvice(value,binding),null);
  }
});

test('user page keeps the advice heading without the removed disclaimer, original summary or diagnostic fields',()=>{
  const html=render();
  assert.match(html,/AI Safety preparation advice/i);
  assert.match(html,/Check the registered conditions before departure/i);
  assert.doesNotMatch(html,/AI Advisory suggestions|Not manually verified|View saved original model summary/i);
  for(const hidden of ['private-run','private-version','private-safety','private-logistics','private-input-hash',
    'private-audit','private-attempt','private-model','total_tokens','fact_refs','\/baseline\/'])assert.ok(!html.includes(hidden),hidden);
  assert.ok(!html.includes('<button')&&!html.includes('<a '));
});

test('model text is escaped plain text, never interpreted as markup or links',()=>{
  const value=fixture();value.plan.findings[0].action_unverified='<img src=x onerror=alert(1)>';
  const html=render(value);
  assert.ok(!html.includes('<img'));
  assert.ok(html.includes('&lt;img'));
});

test('outdated and historical suggestions retain explicit context',()=>{
  assert.match(render(fixture(),{outdated:true}),/Update checks before relying on them/i);
  assert.match(render(fixture(),{historical:true}),/correspond to the itinerary and source information saved at that time/i);
});

test('additional action groups remain available while informational advice is omitted',()=>{
  const value=fixture();
  for(const [i,action_code] of ['RESOLVE_LOGISTICS','CONFIRM_ACTIVITY_DETAILS','REQUEST_HUMAN_REVIEW'].entries())
    value.plan.findings.push({...value.plan.findings[0],finding_key:'extra-'+i,action_code});
  value.plan.findings.push({...value.plan.findings[0],finding_key:'information',action_code:'ACKNOWLEDGE_INFORMATION',action_unverified:'Informational-only text.'});
  value.plan.action_priority=value.plan.findings.map(item=>item.finding_key);
  const html=render(value);
  assert.match(html,/Other advice categories \(2\)/i);
  assert.doesNotMatch(html,/Trip notices|Informational-only text/i);
  assert.match(html,/<ol[^>]*start="4"/i);
});

test('equipment advice has one shared heading and distinct visible original bullet items',()=>{
  const value=fixture();value.advice_format='single-advice-v1';
  const texts=['Tent capacity gap must be resolved before departure.',
    'Sleeping bags are missing; resolve before departure.',
    'First aid kit is incomplete; resolve before departure.'];
  value.plan.findings=texts.map((text,index)=>({finding_key:'gear-'+index,fact_refs:[],action_code:'RESOLVE_LOGISTICS',
    interpretation_unverified:text,action_unverified:text}));
  value.plan.action_priority=value.plan.findings.map(item=>item.finding_key);
  const before=structuredClone(value);const html=render(value);
  assert.equal(html.split('Resolve equipment or transport arrangements').length-1,1);
  assert.match(html,/3 items/i);assert.match(html,/<ul class="safety-advice-items">/i);
  for(const text of texts)assert.equal(html.split(text).length-1,1,text);
  assert.doesNotMatch(html,/Prepare for this item|View saved original model suggestions|Other suggestion categories/i);
  assert.deepEqual(value,before);
});

test('informational advice stays in the saved audit but renders no section or empty card',()=>{
  const value=fixture();value.advice_format='single-advice-v1';
  const texts=['Campfires prohibited; use provided barbecues only.',
    'Road is currently open; no action needed at this time.',
    'Check local information before departure.','Keep the recorded emergency details available.'];
  value.plan.findings=texts.map((text,index)=>({finding_key:'info-'+index,fact_refs:[],action_code:'ACKNOWLEDGE_INFORMATION',
    interpretation_unverified:text,action_unverified:text}));
  value.plan.action_priority=value.plan.findings.map(item=>item.finding_key);
  const before=structuredClone(value);
  assert.equal(render(value),'');
  assert.equal(safetyAdvice(value,binding).items.length,4);
  assert.deepEqual(value,before);
});

test('groups use validated codes and retain first-priority category order and member order',()=>{
  const value=fixture();
  value.plan.findings.push({...value.plan.findings[0],finding_key:'road-later'});
  value.plan.action_priority=['road','weather','road-later'];
  const view=safetyAdvice(value,binding);const before=structuredClone(view);
  const groups=groupSafetyAdvice(view.items);
  assert.deepEqual(groups.map(group=>group.key),['CHANGE_TRIP','CHECK_NEAR_DEPARTURE']);
  assert.deepEqual(groups[0].items.map(item=>item.key),['road','road-later']);
  assert.deepEqual(view,before);
  // Equal display labels/prose do not authorise merging different action codes.
  const sameTitle=view.items.slice(0,2).map(item=>({...item,title:'Same title',action:'Same prose'}));
  assert.equal(groupSafetyAdvice(sameTitle).length,2);
});

test('legacy separate explanations share one group toggle without duplicating visible action text',()=>{
  const value=fixture();
  value.plan.findings[1].action_code=value.plan.findings[0].action_code='RESOLVE_LOGISTICS';
  const html=render(value);
  assert.equal(html.split('Resolve equipment or transport arrangements').length-1,1);
  assert.equal(html.split('View group details and saved originals').length-1,1);
  for(const item of value.plan.findings){
    assert.equal(html.split(item.action_unverified).length-1,1);
    assert.equal(html.split(item.interpretation_unverified).length-1,1);
  }
});
