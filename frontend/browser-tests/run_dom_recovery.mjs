// Manual, local-only Chromium regression. Uses an installed browser, never
// downloads one, and cannot access the user's existing browser profile.
import assert from 'node:assert/strict';
import {existsSync,mkdirSync,mkdtempSync,readFileSync,writeFileSync} from 'node:fs';
import {dirname,resolve} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {spawn} from 'node:child_process';
import {build} from 'vite';

const frontend=resolve(dirname(fileURLToPath(import.meta.url)),'..');
const candidates=[process.env.CAMPMATE_TEST_BROWSER,
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  '/usr/bin/chromium','/usr/bin/chromium-browser','/usr/bin/google-chrome'];
const browser=candidates.find(path=>path&&existsSync(path));
assert.ok(browser,'Set CAMPMATE_TEST_BROWSER to an installed Chromium/Edge executable. No browser is downloaded.');
const directory=resolve(frontend,'../var/browser-dom-regression');mkdirSync(directory,{recursive:true});
const run=mkdtempSync(resolve(directory,'run-'));
const built=await build({root:frontend,configFile:false,envDir:false,publicDir:false,logLevel:'error',
  define:{'process.env.NODE_ENV':JSON.stringify('development')},
  build:{write:false,minify:false,lib:{entry:resolve(frontend,'browser-tests/dom_recovery.fixture.tsx'),formats:['iife'],name:'OfflineDomRegression'}}});
const output=(Array.isArray(built)?built[0]:built).output;
const code=output.filter(item=>item.type==='chunk').map(item=>item.code).join('\n');
const html=resolve(run,'fixture.html');
writeFileSync(html,'<!doctype html><html lang="en"><head><meta charset="UTF-8"></head><body><script>'+code.replace(/<\/script/gi,'<\\/script')+'</script></body></html>');
// DNS and HTTP/S are blocked for this fresh profile. The fixture is an inline
// file and replaces fetch with an in-memory mock before mounting app routes.
const child=spawn(browser,['--headless=new','--disable-gpu','--disable-extensions',
  '--disable-background-networking','--disable-component-update','--disable-default-apps','--disable-sync',
  '--no-first-run','--no-default-browser-check','--host-resolver-rules=MAP * ~NOTFOUND',
  '--proxy-server=http://127.0.0.1:9','--proxy-bypass-list=<-loopback>',
  '--user-data-dir='+resolve(run,'browser-profile'),'--remote-debugging-port=0','about:blank'],
  {stdio:['ignore','pipe','pipe'],windowsHide:true});
let stderr='';child.stderr.on('data',value=>{stderr=(stderr+value.toString()).slice(-12000);});
let launchError;child.on('error',error=>{launchError=error;});
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
let socket,cases;
try{
  const portFile=resolve(run,'browser-profile/DevToolsActivePort');
  for(let i=0;i<150&&!existsSync(portFile);i++){if(launchError)throw launchError;await delay(100);}
  assert.ok(existsSync(portFile),'Isolated browser did not expose its local test endpoint');
  const [port,endpoint]=readFileSync(portFile,'utf8').trim().split(/\r?\n/);
  assert.match(port,/^\d+$/);assert.match(endpoint,/^\/devtools\/browser\/[a-zA-Z0-9-]+$/);
  socket=new WebSocket(`ws://127.0.0.1:${port}${endpoint}`);
  await new Promise((resolve,reject)=>{socket.addEventListener('open',resolve,{once:true});socket.addEventListener('error',reject,{once:true});});
  const pending=new Map();let id=0;const exceptions=[];
  socket.addEventListener('message',event=>{
    const data=JSON.parse(event.data);
    if(data.method==='Runtime.exceptionThrown')exceptions.push(String(data.params.exceptionDetails.exception?.description??data.params.exceptionDetails.text).slice(0,2000));
    if(data.id&&pending.has(data.id)){
      const {resolve,reject,timer}=pending.get(data.id);pending.delete(data.id);clearTimeout(timer);
      if(data.error)reject(new Error(data.error.message));else resolve(data.result);
    }
  });
  const call=(method,params={},sessionId)=>new Promise((resolve,reject)=>{
    const command=++id;const timer=setTimeout(()=>{pending.delete(command);reject(new Error('Local test protocol timed out: '+method));},10000);
    pending.set(command,{resolve,reject,timer});socket.send(JSON.stringify({id:command,method,params,...sessionId?{sessionId}:{}}));
  });
  const {targetId}=await call('Target.createTarget',{url:'about:blank'});
  const {sessionId}=await call('Target.attachToTarget',{targetId,flatten:true});
  await call('Runtime.enable',{},sessionId);
  await call('Page.navigate',{url:pathToFileURL(html).href},sessionId);
  let json;
  for(let i=0;i<200;i++){
    const value=await call('Runtime.evaluate',{expression:'document.getElementById("dom-test-results")?.textContent ?? null',returnByValue:true},sessionId);
    json=value.result?.value;if(json)break;await delay(100);
  }
  writeFileSync(resolve(run,'browser-exceptions.json'),JSON.stringify(exceptions,null,2));
  assert.ok(json,'Offline fixture did not finish: '+exceptions.join('\n'));
  cases=JSON.parse(json);
  await call('Browser.close');
}finally{
  if(socket&&socket.readyState===WebSocket.OPEN){socket.send(JSON.stringify({id:999999,method:'Browser.close'}));socket.close();}
  child.kill();writeFileSync(resolve(run,'browser-stderr.txt'),stderr);
}
writeFileSync(resolve(run,'result.json'),JSON.stringify(cases,null,2)+'\n');
console.log(JSON.stringify(cases,null,2));
assert.equal(cases.length,4,'Every browser scenario must finish');
assert.ok(cases.every(item=>item.passed),'An offline browser scenario failed');
console.log('4 offline browser scenarios passed; no app server, existing browser session, model calls or cloud CI.');
