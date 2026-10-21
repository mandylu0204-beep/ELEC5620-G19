import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {createRequire} from 'node:module';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {transpileModule,ModuleKind,JsxEmit} from 'typescript';
import {createElement} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {safetyAdvice} from '../src/safety_advisory.ts';

const require=createRequire(import.meta.url);
const componentUrl=new URL('../src/safety_advisory_panel.tsx',import.meta.url);
const source=await readFile(componentUrl,'utf8');
const compiled=transpileModule(source,{fileName:fileURLToPath(componentUrl),
  compilerOptions:{module:ModuleKind.ESNext,jsx:JsxEmit.ReactJSX}}).outputText
  .replaceAll('"react/jsx-runtime"',JSON.stringify(pathToFileURL(require.resolve('react/jsx-runtime')).href))
  .replaceAll("'./safety_advisory'",JSON.stringify(new URL('../src/safety_advisory.ts',import.meta.url).href))
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
  assert.deepEqual(view.items.map(item=>item.title),['临近出发时再检查','调整营地、日期或活动']);
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

test('user page labels unverified advice but never renders internal trace or association fields',()=>{
  const html=render();
  assert.match(html,/AI 安全准备建议/);
  assert.match(html,/未经人工核实/);
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
  assert.match(render(fixture(),{outdated:true}),/请更新检查后再参考/);
  assert.match(render(fixture(),{historical:true}),/对应当时保存的行程与检查资料/);
});

test('additional and informational advice remain available without overwhelming the initial view',()=>{
  const value=fixture();
  for(let i=0;i<3;i++)value.plan.findings.push({...value.plan.findings[0],finding_key:'extra-'+i});
  value.plan.findings.push({...value.plan.findings[0],finding_key:'information',action_code:'ACKNOWLEDGE_INFORMATION'});
  value.plan.action_priority=value.plan.findings.map(item=>item.finding_key);
  const html=render(value);
  assert.match(html,/其余建议（2）/);
  assert.match(html,/出行注意事项（1）/);
  assert.match(html,/<ol[^>]*start="4"/);
});
