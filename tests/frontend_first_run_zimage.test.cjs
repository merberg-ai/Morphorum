'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const script=fs.readFileSync(path.join(__dirname,'..','frontend','dist','assets','first-run-zimage.js'),'utf8');

function dom(tag='div') {
  return {
    tag,children:[],textContent:'',className:'',hidden:false,disabled:false,
    attributes:{},style:{},listeners:{},
    append(...children){this.children.push(...children);},
    appendChild(child){this.children.push(child);return child;},
    setAttribute(k,v){this.attributes[k]=String(v);},
    addEventListener(k,cb){this.listeners[k]=cb;},
  };
}
function visit(node,filter){
  const result=[];
  const walk=e=>{
    if(filter(e)) result.push(e);
    for(const child of e.children||[])walk(child);
  };walk(node);return result;
}
const baseline={
  id:'zimage-turbo',index_id:'managed:zimage-turbo',name:'Z-Image-Turbo',
  description:'Official Diffusers package.',license:'Apache-2.0',
  destination:'D:\\Models\\Z-Image-Turbo',advertised_size_bytes:32900000000,
  expected_bytes:32900000000,downloaded_bytes:0,progress_percent:0,
  available_bytes:60000000000,estimated_remaining_bytes:32900000000,
  required_free_bytes:35047483648,space_sufficient:true,
  installed:false,resumable:false,status:'not_installed',error:null,
};
function harness(start={}){
  const state={...baseline,...start};
  const urls=[],notifications=[],pending=[],confirms=[];
  let allow=true,posted=0,selected=null,advanced=0,confirmed=0;
  const w={
    MorphorumToast:(...args)=>notifications.push(args),
    MorphorumDialog:{confirm:async arg=>{confirms.push(arg);return allow;}},
    MorphorumModels:{reload:()=>{},reloadManaged:()=>{},selectExisting:async id=>{selected=id;return true;}},
    setTimeout:cb=>{const id=pending.length;pending.push(cb);return id;},
    clearTimeout:()=>{},
  };
  const fetch=async (url,options={})=>{
    urls.push({url,options});
    if(url==='/api/managed-models/zimage-turbo' && !options.method)
      return {ok:true,json:async()=>({...state})};
    if(url==='/api/managed-models/zimage-turbo/download' && options.method==='POST'){
      posted++;
      Object.assign(state,{status:'checking'});
      return {ok:true,json:async()=>({...state})};
    }
    throw Error('Unexpected '+url);
  };
  const context={document:{createElement:dom},window:w,fetch};
  vm.runInNewContext(script,context);
  const host=dom();
  const wizard=context.window.MorphorumSetupZImage;
  const render=()=>wizard.show(host,()=>{advanced++;});
  const buttons=()=>visit(host,n=>n.tag==='button');
  const find=text=>buttons().find(b=>b.textContent===text);
  const flush=async()=>{await new Promise(resolve=>setImmediate(resolve));};
  return {
    wizard,render,find,buttons,state,urls,notifications,confirms,flush,
    set allow(v){allow=v;},get posted(){return posted;},get selected(){return selected;},
    get advanced(){return advanced;},get timers(){return pending;},
  };
}

test('MS6.3 opening and refreshing are GET-only; declining confirmation does not download',async()=>{
  const h=harness();
  h.render();
  await h.flush();
  assert.equal(h.posted,0);
  assert.equal(h.find('Download Now').disabled,false);
  assert.ok(h.urls.every(req=>req.url==='/api/managed-models/zimage-turbo' && !req.options.method));
  h.allow=false;
  await h.find('Download Now').listeners.click();
  assert.equal(h.posted,0);
  assert.equal(h.confirms.length,1);
  assert.match(h.confirms[0].message,/Apache-2\.0/);
  h.find('Not Now · Continue').listeners.click();
  assert.equal(h.advanced,1);
  assert.equal(h.posted,0);
});

test('MS6.3 accepted confirmation launches only one explicit POST and resumes polling',async()=>{
  const h=harness({status:'interrupted',resumable:true,downloaded_bytes:1000});
  h.render();
  await h.flush();
  const button=h.find('Resume / Repair Download');
  assert.ok(button);
  await button.listeners.click();
  assert.equal(h.posted,1);
  assert.equal(h.confirms[0].confirmText,'Resume Download');
  assert.ok(h.urls.some(x=>x.url.endsWith('/download') && x.options.method==='POST'));
  assert.ok(h.timers.length>=1);
  assert.equal(h.find('Download In Progress').disabled,true);
  h.state.status='installed';
  h.state.installed=true;
  h.state.progress_percent=100;
  const refresh=h.find('Refresh Status');
  await refresh.listeners.click();
  assert.ok(h.find('Use Existing Model'));
  assert.equal(h.posted,1);
  await h.find('Use Existing Model').listeners.click();
  assert.equal(h.selected,'managed:zimage-turbo');
  assert.equal(h.posted,1);
});

test('MS6.3 insufficient space prevents download and still permits continuing',async()=>{
  const h=harness({space_sufficient:false,available_bytes:2048});
  h.render();
  await h.flush();
  assert.equal(h.find('Download Now').disabled,true);
  assert.equal(h.posted,0);
  assert.match(visit(h.renderHost || h.buttons()[0],()=>true)[0]?.textContent||'','');
  h.find('Not Now · Continue').listeners.click();
  assert.equal(h.advanced,1);
});

test('MS6.3 later installation state does not imply ready when only partial',async()=>{
  const h=harness({status:'partial',progress_percent:100,downloaded_bytes:33000000000,resumable:true});
  const mount=h.render();
  await h.flush();
  assert.equal(h.find('Resume / Repair Download').disabled,false);
  assert.equal(mount.progressTrack.attributes['aria-valuenow'],'99.9');
  assert.equal(h.posted,0);
  h.wizard.leave();
  // Calling stale refresh handler must not schedule or launch anything.
  const count=h.urls.length;
  await h.find('Refresh Status').listeners.click();
  assert.equal(h.urls.length,count);
});

test('MS6.3 existing verified package offers explicit selection, never a download',async()=>{
  const h=harness({status:'installed',installed:true,progress_percent:100});
  const mount=h.render();
  await h.flush();
  assert.equal(mount.progressTrack.attributes['aria-valuenow'],'100.0');
  assert.ok(h.find('Use Existing Model'));
  await h.find('Use Existing Model').listeners.click();
  assert.equal(h.selected,'managed:zimage-turbo');
  assert.equal(h.posted,0);
});
