import test from 'node:test';
import assert from 'node:assert/strict';
import {canonicalTerms,termLabel,itineraryText} from '../src/user_terms.ts';
import {loginReturnPath} from '../src/login_return.ts';

test('Chinese structured meal/quiet labels reach existing business rules',()=>{
  assert.deepEqual(canonicalTerms(['安静','即食餐食'],'preference'),['quiet','ready-to-eat meals']);
  assert.deepEqual(canonicalTerms(['Quiet','ready-to-eat meals'],'preference'),['quiet','ready-to-eat meals']);
});
test('unknown, negated and compound requirements are not guessed or removed',()=>{
  const input=['不安静','不要营火','厕所或淋浴','无人机充电','希望安静但不要即食餐食'];
  assert.deepEqual(canonicalTerms(input,'constraint'),input);
  assert.deepEqual(canonicalTerms(input,'preference'),input);
});
test('contradictory meal and fire choices remain contradictory for server validation',()=>{
  assert.deepEqual(canonicalTerms(['即食餐食','自行烹饪'],'preference'),['ready-to-eat meals','self-catered meals']);
  assert.deepEqual(canonicalTerms(['营火','不生火'],'constraint'),['campfire','no_fires']);
});
test('step-free requirements retain their specific meaning and field boundary',()=>{
  assert.deepEqual(canonicalTerms(['需要无台阶通道'],'accessibility'),['step-free path']);
  assert.deepEqual(canonicalTerms(['需要无台阶通道'],'constraint'),['需要无台阶通道']);
  assert.notEqual(canonicalTerms(['无台阶通道'],'accessibility')[0],'wheelchair access');
});
test('confirmation display labels do not rewrite unknown terms or source descriptions',()=>{
  assert.equal(termLabel('ready-to-eat meals','preference'),'即食餐食');
  assert.equal(termLabel('unknown preference','preference'),'unknown preference');
  assert.equal(itineraryText('Synthetic overnight stay at Demo Wattle Rest; no booking implied.'),'在营地过夜，请另行确认营位预订。');
  assert.equal(itineraryText('Meet at 09:00; booking is pending.'),'Meet at 09:00; booking is pending.');
});
test('login resumes the intended role-appropriate local route and query',()=>{
  for(const path of ['/request','/request?copy_from=abc','/profile','/plans/abc/finals/def','/plans/abc?run_id=123'])
    assert.equal(loginReturnPath(path,'CAMPER'),path);
  assert.equal(loginReturnPath('/review/abc','FOUNDER'),'/review/abc');
});
test('login cannot redirect externally or enter the other role through return state',()=>{
  for(const value of [null,{},'https://example.com','//example.com','/\\example.com','/plans/../review','/review','/plans/abc#fragment','/plans/abc\n'])
    assert.equal(loginReturnPath(value,'CAMPER'),'/plans');
  assert.equal(loginReturnPath('/request','FOUNDER'),'/review');
});

test('founder login can resume a requirement assistance task without giving campers reviewer access',()=>{
  assert.equal(loginReturnPath('/requirement-help/task-1','FOUNDER'),'/requirement-help/task-1');
  assert.equal(loginReturnPath('/requirement-help/task-1','CAMPER'),'/plans');
});
