import test,{after} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync,readdirSync} from 'node:fs';
import {createServer} from 'vite';
import {displayProse} from '../src/display_facts.ts';
import {englishSavedReason} from '../src/legacy_filter_reasons.ts';
import {canonicalTerms,termLabel} from '../src/user_terms.ts';
const server=await createServer({configFile:false,envDir:false,server:{middlewareMode:true,hmr:false,ws:false,watch:null},optimizeDeps:{noDiscovery:true}});
after(()=>server.close());
const {selectedRequirementsPresentation}=await server.ssrLoadModule('/src/campsite_selection.ts');

test('English UI sources and document language contain no untranslated labels',()=>{
 for(const file of readdirSync(new URL('../src/',import.meta.url)).filter(name=>/\.tsx?$/.test(name))){
  assert.doesNotMatch(readFileSync(new URL('../src/'+file,import.meta.url),'utf8'),/[\u3400-\u9fff]/u,file);
 }
 assert.match(readFileSync(new URL('../index.html',import.meta.url),'utf8'),/<html lang="en">/);
});

test('English model text is readable while unknown Chinese history stays original',()=>{
 const original='\u672a\u77e5\u7684\u5386\u53f2\u8bb0\u5f55';
 assert.equal(displayProse('Check equipment before departure.'),'Check equipment before departure.');
 assert.equal(displayProse(original),null);
 assert.equal(original,'\u672a\u77e5\u7684\u5386\u53f2\u8bb0\u5f55');
 assert.equal(canonicalTerms(['\u9700\u8981\u6dcb\u6d74'],'constraint')[0],'showers');
 assert.equal(termLabel('showers','constraint'),'Showers');
 assert.equal(termLabel('__proto__','constraint'),'__proto__');
});

test('exact historical filtering facts and new English facts produce the same comparison without mutation',()=>{
 const old=['\u5fc5\u987b\u6761\u4ef6\uff1a\u5395\u6240\uff0c\u767b\u8bb0\u4fe1\u606f\u4e3a\u652f\u6301\u3002',
 '\u8425\u5730\u914d\u5957\uff1a\u996e\u7528\u6c34\u5df2\u767b\u8bb0\u63d0\u4f9b\u3002'];
 const before=structuredClone(old);const english=old.map(englishSavedReason);
 assert.deepEqual(english.map(englishSavedReason),english,'normalisation must be idempotent');
 const requirements={preferences:[],mandatory_constraints:['toilets']};
 const historical=selectedRequirementsPresentation(old,requirements,null);
 assert.deepEqual(historical,selectedRequirementsPresentation(english,requirements,null));
 assert.equal(historical.rows[0].state,true);assert.equal(historical.extra[0].facility,'potable_water');
 assert.deepEqual(old,before);
});
