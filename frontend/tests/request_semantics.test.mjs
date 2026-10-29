import test, {after} from 'node:test';
import assert from 'node:assert/strict';
import {createElement as h} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {createServer} from 'vite';

// Transform the real request form helpers without opening a listener or reading
// personal environment files. No model transport is started in this suite.
const server=await createServer({configFile:false,envDir:false,appType:'custom',
  server:{middlewareMode:true,hmr:false,ws:false,watch:null},optimizeDeps:{noDiscovery:true}});
after(()=>server.close());
const {requestPayload,requestDraftFromRecord,requestMealPreferences,RequestMeaningSummary,requestHistoryTitle,
  clarificationText,requestFieldRoot,requestClarificationField}=await server.ssrLoadModule('/src/requests.tsx');
const draft=(patch={})=>({raw:'准备和我男朋友一起去，想找个安静的地方',destination:'Sydney and Surrounds',
  start:'2026-11-09',nights:'2',days:'',end:'',budget:'320.05',preferences:'',constraints:'',...patch});
const requirements=(patch={})=>({destination:'Sydney and Surrounds',start_date:'2026-11-09',duration_nights:2,
  duration_days:3,end_date:'2026-11-11',budget_cents:32005,currency:'AUD',preferences:[],mandatory_constraints:[],...patch});

test('request payload preserves original prose and soft/hard text for server interpretation',()=>{
  const value=draft({preferences:'安静\nNot too noisy\n最好能洗澡',constraints:'需要洗澡\nNo campfires\n厕所或淋浴'});
  const result=requestPayload(value);
  assert.equal(result.raw_text,value.raw);
  assert.deepEqual(result.explicit_fields.preferences,['安静','Not too noisy','最好能洗澡']);
  assert.deepEqual(result.explicit_fields.mandatory_constraints,['需要洗澡','No campfires','厕所或淋浴']);
  assert.equal(result.explicit_fields.budget_cents,32005);
  assert.equal(result.explicit_fields.start_date,'2026-11-09');
});

test('empty dedicated boxes stay empty and do not copy or replace requirements in the idea',()=>{
  const result=requestPayload(draft({raw:'必须有淋浴，希望安静，选择即食餐食',preferences:'  \n',constraints:''}));
  assert.deepEqual(result.explicit_fields.preferences,[]);
  assert.deepEqual(result.explicit_fields.mandatory_constraints,[]);
  assert.equal(result.raw_text,'必须有淋浴，希望安静，选择即食餐食');
});

test('changing meal choice preserves every unrelated phrase and negation',()=>{
  const original=['Quiet','希望安静但不要即食餐食','quiet hours are insufficient','自行烹饪'].join('\n');
  const next=requestMealPreferences(original,'ready-to-eat meals');
  assert.equal(next,['Quiet','希望安静但不要即食餐食','quiet hours are insufficient','即食餐食'].join('\n'));
  assert.deepEqual(requestPayload(draft({preferences:next})).explicit_fields.preferences,
    ['Quiet','希望安静但不要即食餐食','quiet hours are insufficient','即食餐食']);
});

test('clearing meal choice removes only recognized meal lines, without guessing compound prose',()=>{
  assert.equal(requestMealPreferences('self_catered\n安静\nready-to-eat meals\n不要自己做饭',''),
    '安静\n不要自己做饭');
});

test('saved explicit input round-trips without translating, canonicalizing or losing wording',()=>{
  const saved={raw_text:'需要洗澡，不要营火',explicit_fields:{...requirements(),preferences:['Quiet','最好能洗澡'],
    mandatory_constraints:['需要洗澡','no_fires']}};
  const restored=requestDraftFromRecord(saved);
  assert.equal(restored.preferences,'Quiet\n最好能洗澡');
  assert.equal(restored.constraints,'需要洗澡\nno_fires');
  assert.deepEqual(requestPayload(restored).explicit_fields.preferences,saved.explicit_fields.preferences);
  assert.deepEqual(requestPayload(restored).explicit_fields.mandatory_constraints,saved.explicit_fields.mandatory_constraints);
});

test('summary shows interpreted meanings separately from facts and keeps unknown preferences visible',()=>{
  const html=renderToStaticMarkup(h(RequestMeaningSummary,{requirements:requirements({
    preferences:['quiet','ready-to-eat meals','Near a shaded walking trail'],mandatory_constraints:['showers','no_fires']})}));
  for(const phrase of ['需求理解结果','偏好','必须满足的条件','安静','即食餐食','淋浴','不生火','Near a shaded walking trail'])
    assert.ok(html.includes(phrase),phrase);
  assert.doesNotMatch(html,/有无遗漏|旧版原文|检查通过|营地已确认|<input|<button/);
});

test('unresolved hard requirement is not presented as no requirement',()=>{
  const html=renderToStaticMarkup(h(RequestMeaningSummary,{requirements:requirements(),pendingConstraints:true}));
  assert.match(html,/还有必须条件需要核对/);
  assert.doesNotMatch(html,/暂未提出额外必须条件/);
  const empty=renderToStaticMarkup(h(RequestMeaningSummary,{requirements:requirements()}));
  assert.match(empty,/暂未提出额外必须条件/);
});

test('legacy unsupported errors give an actionable correction rather than an implementation error',()=>{
  const message=clarificationText('mandatory_constraints','Unsupported hard constraint: 需要洗澡.',undefined);
  assert.equal(message,'无法核实必须条件“需要洗澡”。请说明具体需要的设施，或将非必要要求移到偏好中，再生成摘要。');
  assert.doesNotMatch(message,/Unsupported|hard constraint/);
});

test('semantic clarification field paths locate the original input without crossing profile fields',()=>{
  assert.equal(requestFieldRoot('mandatory_constraints[1]'),'mandatory_constraints');
  assert.equal(requestFieldRoot('preferences.0'),'preferences');
  assert.equal(requestFieldRoot('raw_text'),'raw_text');
  assert.equal(requestFieldRoot('profile.group_size'),'profile.group_size');
  assert.equal(requestFieldRoot('preferences_extra'),'preferences_extra');
});

test('missing meal clarification locates the meal selector without redirecting ordinary preference questions',()=>{
  assert.equal(requestClarificationField('preferences','请选择用餐方式：即食餐食或自行烹饪。'),'meal_mode');
  assert.equal(requestClarificationField('preferences','请说明你对用餐环境的偏好。'),'preferences');
});

test('conflicting meal clarification locates the selector while unknown indexed preferences retain their textarea',()=>{
  assert.equal(requestClarificationField('preferences','用餐方式同时包含即食餐食和自行烹饪，请明确本次采用哪一种。'),'meal_mode');
  assert.equal(requestClarificationField('preferences[0]','请明确是否希望附近有餐厅。'),'preferences');
});

test('new structured requests omit prose rather than sending filler text',()=>{
  const payload=requestPayload(draft({raw:''}));
  assert.equal(Object.hasOwn(payload,'raw_text'),false);
  assert.equal(payload.explicit_fields.destination,'Sydney and Surrounds');
  assert.equal(payload.explicit_fields.budget_cents,32005);
});

test('structured history names come from real destination and dates without rewriting saved raw text',()=>{
  const row={raw_text:'',explicit_fields:{destination:'Sydney',start_date:'2026-11-10',duration_nights:2}};
  assert.equal(requestHistoryTitle(row),'Sydney · 2026-11-10 · 2 晚');assert.equal(row.raw_text,'');
  assert.equal(requestHistoryTitle({raw_text:'历史原文',explicit_fields:row.explicit_fields}),'历史原文');
});
