import test from 'node:test';
import assert from 'node:assert/strict';
import {canonicalTerms,termLabel,itineraryText} from '../src/user_terms.ts';
import {loginReturnPath} from '../src/login_return.ts';

test('Chinese structured meal/quiet labels reach existing business rules',()=>{
  assert.deepEqual(canonicalTerms(['Quiet','Ready-to-eat meals'],'preference'),['quiet','ready-to-eat meals']);
  assert.deepEqual(canonicalTerms(['Quiet','ready-to-eat meals'],'preference'),['quiet','ready-to-eat meals']);
});
test('unknown, negated and compound requirements are not guessed or removed',()=>{
  const input=['Not quiet','No campfire wanted','Toilets or showers','Drone charging','Prefer quiet but no ready-to-eat meals'];
  assert.deepEqual(canonicalTerms(input,'constraint'),input);
  assert.deepEqual(canonicalTerms(input,'preference'),input);
});
test('contradictory meal and fire choices remain contradictory for server validation',()=>{
  assert.deepEqual(canonicalTerms(['Ready-to-eat meals','Self-catered meals'],'preference'),['ready-to-eat meals','self-catered meals']);
  assert.deepEqual(canonicalTerms(['Campfire','No campfire'],'constraint'),['campfire','no_fires']);
});
test('step-free requirements retain their specific meaning and field boundary',()=>{
  assert.deepEqual(canonicalTerms(['Need a step-free path'],'accessibility'),['step-free path']);
  assert.deepEqual(canonicalTerms(['Need a step-free path'],'constraint'),['Need a step-free path']);
  assert.notEqual(canonicalTerms(['Step-free path'],'accessibility')[0],'wheelchair access');
});
test('confirmation display labels do not rewrite unknown terms or source descriptions',()=>{
  assert.equal(termLabel('ready-to-eat meals','preference'),'Ready-to-eat meals');
  assert.equal(termLabel('unknown preference','preference'),'unknown preference');
  assert.equal(itineraryText('Synthetic overnight stay at Demo Wattle Rest; no booking implied.'),'Overnight campsite stay; confirm your campsite booking separately.');
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
