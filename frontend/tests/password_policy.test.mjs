import test from 'node:test';
import assert from 'node:assert/strict';
import {passwordChecks} from '../src/password_policy.ts';

test('password requirements report independent live completion instead of a single opaque error',()=>{
  assert.ok(passwordChecks('').every(item=>!item.met));
  assert.deepEqual(passwordChecks('abcdefgh').map(item=>item.met),[true,false,true,false,false]);
  assert.deepEqual(passwordChecks('Abcdef12').map(item=>item.met),[true,true,true,true,false]);
  assert.ok(passwordChecks('Abcdef1!').every(item=>item.met));
});
test('length boundaries, spaces and non-ASCII characters cannot bypass a required category',()=>{
  for(const value of ['Abcde1!','A'+'a'.repeat(254)+'1!', 'Abcdef1 ', 'Abcdef1💡'])
    assert.ok(passwordChecks(value).some(item=>!item.met),value);
  assert.ok(passwordChecks('A'+'a'.repeat(253)+'1!').every(item=>item.met));
  for(const symbol of ['!','@','#','-','_','[',']','\\','`','~'])
    assert.ok(passwordChecks('Abcdef1'+symbol).every(item=>item.met));
});
