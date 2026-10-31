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
const draft=(patch={})=>({raw:'Planning a trip with my boyfriend and looking for somewhere quiet',destination:'Sydney and Surrounds',
  start:'2026-11-09',nights:'2',days:'',end:'',budget:'320.05',preferences:'',constraints:'',...patch});
const requirements=(patch={})=>({destination:'Sydney and Surrounds',start_date:'2026-11-09',duration_nights:2,
  duration_days:3,end_date:'2026-11-11',budget_cents:32005,currency:'AUD',preferences:[],mandatory_constraints:[],...patch});

test('request payload preserves original prose and soft/hard text for server interpretation',()=>{
  const value=draft({preferences:'Quiet\nNot too noisy\nPrefer showers',constraints:'Need showers\nNo campfires\nToilets or showers'});
  const result=requestPayload(value);
  assert.equal(result.raw_text,value.raw);
  assert.deepEqual(result.explicit_fields.preferences,['Quiet','Not too noisy','Prefer showers']);
  assert.deepEqual(result.explicit_fields.mandatory_constraints,['Need showers','No campfires','Toilets or showers']);
  assert.equal(result.explicit_fields.budget_cents,32005);
  assert.equal(result.explicit_fields.start_date,'2026-11-09');
});

test('empty dedicated boxes stay empty and do not copy or replace requirements in the idea',()=>{
  const result=requestPayload(draft({raw:'Must have showers, prefer quiet, and choose ready-to-eat meals',preferences:'  \n',constraints:''}));
  assert.deepEqual(result.explicit_fields.preferences,[]);
  assert.deepEqual(result.explicit_fields.mandatory_constraints,[]);
  assert.equal(result.raw_text,'Must have showers, prefer quiet, and choose ready-to-eat meals');
});

test('changing meal choice preserves every unrelated phrase and negation',()=>{
  const original=['Quiet','Prefer quiet but no ready-to-eat meals','quiet hours are insufficient','Self-catered meals'].join('\n');
  const next=requestMealPreferences(original,'ready-to-eat meals');
  assert.equal(next,['Quiet','Prefer quiet but no ready-to-eat meals','quiet hours are insufficient','Ready-to-eat meals'].join('\n'));
  assert.deepEqual(requestPayload(draft({preferences:next})).explicit_fields.preferences,
    ['Quiet','Prefer quiet but no ready-to-eat meals','quiet hours are insufficient','Ready-to-eat meals']);
});

test('clearing meal choice removes only recognized meal lines, without guessing compound prose',()=>{
  assert.equal(requestMealPreferences('self_catered\nQuiet\nready-to-eat meals\nNo self-catering',''),
    'Quiet\nNo self-catering');
});

test('saved explicit input round-trips without translating, canonicalizing or losing wording',()=>{
  const saved={raw_text:'Showers required, no campfire wanted',explicit_fields:{...requirements(),preferences:['Quiet','Prefer showers'],
    mandatory_constraints:['Need showers','no_fires']}};
  const restored=requestDraftFromRecord(saved);
  assert.equal(restored.preferences,'Quiet\nPrefer showers');
  assert.equal(restored.constraints,'Need showers\nno_fires');
  assert.deepEqual(requestPayload(restored).explicit_fields.preferences,saved.explicit_fields.preferences);
  assert.deepEqual(requestPayload(restored).explicit_fields.mandatory_constraints,saved.explicit_fields.mandatory_constraints);
});

test('summary shows interpreted meanings separately from facts and keeps unknown preferences visible',()=>{
  const html=renderToStaticMarkup(h(RequestMeaningSummary,{requirements:requirements({
    preferences:['quiet','ready-to-eat meals','Near a shaded walking trail'],mandatory_constraints:['showers','no_fires']})}));
  for(const phrase of ['Interpreted requirements','Preferences','Required conditions','Quiet','Ready-to-eat meals','Showers','No campfire','Near a shaded walking trail'])
    assert.ok(html.includes(phrase),phrase);
  assert.doesNotMatch(html,/Check for omissions|Legacy original text|Checks passed|Campsite confirmed|<input|<button/i);
});

test('unresolved hard requirement is not presented as no requirement',()=>{
  const html=renderToStaticMarkup(h(RequestMeaningSummary,{requirements:requirements(),pendingConstraints:true}));
  assert.match(html,/Some required conditions need review/i);
  assert.doesNotMatch(html,/No additional required conditions/i);
  const empty=renderToStaticMarkup(h(RequestMeaningSummary,{requirements:requirements()}));
  assert.match(empty,/No additional required conditions/i);
});

test('legacy unsupported errors give an actionable correction rather than an implementation error',()=>{
  const message=clarificationText('mandatory_constraints','Unsupported hard constraint: Need showers.',undefined);
  assert.equal(message,'Cannot verify required condition: Need showers. Specify the facilities you need, or move nonessential requirements to preferences, then generate the summary.');
  assert.doesNotMatch(message,/Unsupported|hard constraint/i);
});

test('semantic clarification field paths locate the original input without crossing profile fields',()=>{
  assert.equal(requestFieldRoot('mandatory_constraints[1]'),'mandatory_constraints');
  assert.equal(requestFieldRoot('preferences.0'),'preferences');
  assert.equal(requestFieldRoot('raw_text'),'raw_text');
  assert.equal(requestFieldRoot('profile.group_size'),'profile.group_size');
  assert.equal(requestFieldRoot('preferences_extra'),'preferences_extra');
});

test('missing meal clarification locates the meal selector without redirecting ordinary preference questions',()=>{
  assert.equal(requestClarificationField('preferences','Choose a meal arrangement: ready-to-eat or self-catered meals.'),'meal_mode');
  assert.equal(requestClarificationField('preferences','Describe your meal-environment preference.'),'preferences');
});

test('conflicting meal clarification locates the selector while unknown indexed preferences retain their textarea',()=>{
  assert.equal(requestClarificationField('preferences','Both ready-to-eat and self-catered meals were selected. Choose one arrangement for this trip.'),'meal_mode');
  assert.equal(requestClarificationField('preferences[0]','Clarify whether you want a nearby restaurant.'),'preferences');
});

test('new structured requests omit prose rather than sending filler text',()=>{
  const payload=requestPayload(draft({raw:''}));
  assert.equal(Object.hasOwn(payload,'raw_text'),false);
  assert.equal(payload.explicit_fields.destination,'Sydney and Surrounds');
  assert.equal(payload.explicit_fields.budget_cents,32005);
});

test('structured history names come from real destination and dates without rewriting saved raw text',()=>{
  const row={raw_text:'',explicit_fields:{destination:'Sydney',start_date:'2026-11-10',duration_nights:2}};
  assert.equal(requestHistoryTitle(row),'Sydney · 2026-11-10 · 2 nights');assert.equal(row.raw_text,'');
  assert.equal(requestHistoryTitle({raw_text:'Historical original text',explicit_fields:row.explicit_fields}),'Historical original text');
});
