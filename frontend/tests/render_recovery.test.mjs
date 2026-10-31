import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {isDomMutationError,recoveryPlanPath} from '../src/render_recovery.ts';

test('DOM mismatch detection is bounded and other errors are not labelled translation errors',()=>{
  for(const method of ['removeChild','insertBefore'])
    assert.equal(isDomMutationError({name:'NotFoundError',message:`Failed to execute '${method}' on 'Node'`}),true);
  for(const error of [null,undefined,'private error text',{},new Error('private profile'),
    {name:'NotFoundError',message:'Unknown resource'},{name:'TypeError',message:'removeChild'}])
    assert.equal(isDomMutationError(error),false);
});

test('recovery links preserve the source plan without replaying an update or trusting an external path',()=>{
  for(const path of ['/plans/owned','/plans/owned/update','/plans/owned/finals/final-1'])
    assert.equal(recoveryPlanPath(path),'/plans/owned');
  for(const path of ['/profile','/request/draft','//evil.example/plans/owned','https://evil.example',
    '/plans/../update','/plans/owned/update/extra','/plans/<script>'])
    assert.equal(recoveryPlanPath(path),'/plans');
});

test('the React-owned application root opts out of external automatic translation',()=>{
  const html=readFileSync(new URL('../index.html',import.meta.url),'utf8');
  assert.match(html,/<div\s+id="root"\s+translate="no"\s+class="notranslate"/);
  const main=readFileSync(new URL('../src/main.tsx',import.meta.url),'utf8');
  assert.match(main,/onUncaughtError\(error\)/);
  assert.match(main,/showRenderRecovery\(container,error\)/);
});
