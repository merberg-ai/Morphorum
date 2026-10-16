'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const root=path.join(__dirname,'..','frontend','dist');
const script=fs.readFileSync(path.join(root,'assets','first-run-setup.js'),'utf8');
const html=fs.readFileSync(path.join(root,'index.html'),'utf8');
const css=fs.readFileSync(path.join(root,'assets','first-run-setup.css'),'utf8');

function harness(serverStatus){
  if (serverStatus.ready === undefined) serverStatus.ready = true;
  const listeners={};
  const calls=[];
  const status=()=>({...serverStatus});
  const element=id=>({
    id,hidden:true,textContent:'',disabled:false,children:[],
    listeners:{},appendChild(child){this.children.push(child);},
    replaceChildren(){this.children=[];},
    addEventListener(name,cb){this.listeners[name]=cb;},
    focus(){this.focused=true;},
  });
  const nodes=Object.fromEntries(
    ['overlay','title','progress','description','error','back','next','skip','close']
      .map(k=>['first-run-'+k,element('first-run-'+k)]));
  nodes['reopen-first-run-setup']=element('reopen-first-run-setup');
  const messages=[];
  const context={
    document:{
      activeElement:{focus(){}},
      getElementById:id=>nodes[id]||null,
      createElement:tag=>({tag,textContent:'',children:[],appendChild(c){this.children.push(c);}}),
    },
    fetch:async (url,options)=>{
      calls.push({url,options});
      if(url==='/api/setup/status')
        return {ok:true,json:async()=>status()};
      if(url==='/api/setup/progress'){
        const body=JSON.parse(options.body);
        if(body.revision!==serverStatus.revision)
          return {ok:false,json:async()=>({detail:'stale'})};
        Object.assign(serverStatus,{revision:serverStatus.revision+1,
          status:body.action==='skip'?'skipped':'in_progress',
          step:body.step||serverStatus.step,
          show_wizard:body.action!=='skip'&&serverStatus.provenance==='fresh_installer'});
        return {ok:true,json:async()=>status()};
      }
      throw Error('Unexpected fetch: '+url);
    },
    window:{
      addEventListener:(name,cb)=>{listeners[name]=cb;},
      MorphorumToast:(...args)=>messages.push(args),
      MorphorumSetupFolders:{render:(container,kind)=>{
        container.appendChild({tag:'p',textContent:kind+' folder editor'});
      },beforeNext:()=>true,reset:()=>{},welcome:()=>{}},
      MorphorumSetupZImage:{show:(container)=>container.appendChild({tag:'p',textContent:'Managed Z-Image download page'}),leave:()=>{}},
    },
  };
  vm.runInNewContext(script,context);
  const flush=async()=>{await new Promise(resolve=>setImmediate(resolve));};
  return {context,nodes,listeners,calls,messages,status:serverStatus,flush,
    overlay:nodes['first-run-overlay'],
    click:async key=>{nodes['first-run-'+key].listeners.click();await flush();},
  };
}

test('MS6.1 fresh installation automatically shows Welcome and progresses server-side',async()=>{
  const h=harness({schema_version:1,eligible:true,show_wizard:true,
    forced_for_launch:false,status:'not_started',step:'welcome',revision:1,
    provenance:'fresh_installer'});
  h.listeners.DOMContentLoaded();
  await h.flush();
  assert.equal(h.overlay.hidden,false);
  assert.match(h.nodes['first-run-title'].textContent,/Welcome/);
  assert.match(h.nodes['first-run-progress'].textContent,/Step 1 of 7/);
  assert.match(h.nodes['first-run-description'].children[0].textContent,/Morphorum/);
  assert.equal(h.nodes['first-run-back'].disabled,true);
  await h.click('next');
  assert.equal(h.status.step,'modes');
  assert.equal(h.status.status,'in_progress');
  assert.match(h.nodes['first-run-title'].textContent,/WebUI or Backend-Only/);
  assert.match(h.nodes['first-run-description'].children[2].textContent,/Backend-only/);
  assert.equal(h.calls.at(-1).options.headers['X-Morphorum-Setup'],'1');
  await h.click('next');
  assert.equal(h.status.step,'models');
  assert.equal(h.nodes['first-run-next'].disabled,false);
  assert.match(h.nodes['first-run-description'].children[0].textContent,/models folder editor/);
  await h.click('next');
  assert.equal(h.status.step,'loras');
  assert.match(h.nodes['first-run-description'].children[0].textContent,/loras folder editor/);
  await h.click('next');
  assert.equal(h.status.step,'zimage');
  assert.equal(h.nodes['first-run-next'].disabled,false);
  assert.match(h.nodes['first-run-description'].children[0].textContent,/Managed Z-Image/);
  await h.click('next');
  assert.equal(h.status.step,'examples');
  assert.equal(h.nodes['first-run-next'].disabled,true);
  assert.ok(h.calls.every(call=>!call.url.includes('/download')&&!call.url.includes('/models/scan')
    &&!call.url.includes('/animation/projects')),'Opening and progressing should have no work side effects');
});

test('MS6.1 existing install does not auto-open but Settings manually reopens',async()=>{
  const h=harness({schema_version:1,eligible:false,show_wizard:false,
    forced_for_launch:false,status:'legacy',step:'welcome',revision:0,
    provenance:'legacy'});
  h.listeners.DOMContentLoaded();
  await h.flush();
  assert.equal(h.overlay.hidden,true);
  h.nodes['reopen-first-run-setup'].listeners.click();
  await h.flush();
  assert.equal(h.overlay.hidden,false);
  await h.click('next');
  assert.equal(JSON.parse(h.calls.at(-1).options.body).manual,true);
  assert.equal(h.status.step,'modes');
});

test('MS6.1 Skip records server state; later WebUI load does not auto-open',async()=>{
  const h=harness({schema_version:1,eligible:true,show_wizard:true,
    forced_for_launch:false,status:'not_started',step:'welcome',revision:1,
    provenance:'fresh_installer'});
  h.listeners.DOMContentLoaded();
  await h.flush();
  await h.click('skip');
  assert.equal(h.status.status,'skipped');
  assert.equal(h.overlay.hidden,true);
  const next=harness(h.status);
  next.listeners.DOMContentLoaded();
  await next.flush();
  assert.equal(next.overlay.hidden,true);
});

test('MS6.1 completed or backend-only run does not open without explicit override',async()=>{
  for(const state of [
    {status:'completed',show_wizard:false,mode:'webui'},
    {status:'not_started',show_wizard:false,mode:'backend-only'},
  ]){
    const h=harness({schema_version:1,eligible:false,forced_for_launch:false,
      step:'welcome',revision:2,provenance:'fresh_installer',...state});
    h.listeners.DOMContentLoaded();
    await h.flush();
    assert.equal(h.overlay.hidden,true);
  }
});

test('MS6.1 responsive shell, Settings affordance, and no second project wizard',()=>{
  assert.equal((html.match(/id="first-run-overlay"/g)||[]).length,1);
  assert.equal((html.match(/id="reopen-first-run-setup"/g)||[]).length,1);
  assert.match(css,/\.first-run-overlay\[hidden\]/);
  assert.match(css,/@media \(max-width:550px\)/);
  assert.match(html,/first-run-setup\.js/);
  assert.match(html,/first-run-folders\.js/);
  assert.match(html,/first-run-zimage\.js/);
  assert.match(html,/project-wizard\.js/);
});
