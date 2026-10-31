import test from 'node:test';
import assert from 'node:assert/strict';
import {logisticsQuestions,needsMealChoice} from '../src/logistics_guidance.ts';

test('one meal decision produces one action and never an unrelated transport warning',()=>{
  const questions=['meal_mode','gear_rule_input.meal_mode'].map(field=>({field,question:'raw',reason:'raw'}));
  assert.equal(needsMealChoice(questions),true);
  const messages=logisticsQuestions(questions);
  assert.equal(messages.length,1);
  assert.match(messages[0],/ready-to-eat meals or self-catering/i);
  assert.doesNotMatch(messages[0],/Transport/i);
});

test('meal guidance preserves independent unresolved questions',()=>{
  const questions=[{field:'meal_mode',question:'meal',reason:'unknown'},
    {field:'equipment.tent',question:'Confirm tent capacity',reason:'unknown capacity'}];
  assert.equal(logisticsQuestions(questions).length,2);
  assert.match(logisticsQuestions(questions)[1],/tent capacity/i);
  assert.equal(needsMealChoice(questions.slice(1)),false);
});
