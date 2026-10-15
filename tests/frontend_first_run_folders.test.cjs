'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');

const code=fs.readFileSync(path.join(__dirname,'..','frontend','dist','assets',
  'first-run-folders.js'),'utf8');

function element(tag='div') {
  return {
    tag,children:[],className:'',textContent:'',disabled:false,value:'',
    listeners:{},attributes:{},
    appendChild(child){this.children.push(child);return child;},
    replaceChildren(){this.children=[];},
    addEventListener(name,listener){this.listeners[name]=listener;},
    setAttribute(name,value){this.attributes[name]=value;},
  };
}
function descendants(node,filter){
  const found=[];
  function walk(item){
    if(filter(item)) found.push(item);
    (item.children||[]).forEach(walk);
  }
  walk(node);
  return found;
}
function testHarness(){
  const calls=[];
  const toasts=[];
  let lastSaved=null;
  let reads=0;
  const configured={
    models:{
      sdxl:{checkpoints:[],loras:[]},
      flux:{checkpoints:[],loras:[]},
      zimage:{loras:[]},
    },
  };
  const fetch=async (url,options={})=>{
    calls.push({url,options});
    if(url==='/api/settings'){
      reads++;
      return {ok:true,json:async()=>({settings:JSON.parse(JSON.stringify(configured))})};
    }
    if(url==='/api/system'){
      return {ok:true,json:async()=>({
        ok:true,version:'0.1',platform:'Windows-test',
        gpu:{devices:[{name:'GPU'}]},
        checks:[{name:'CUDA',ok:true},{name:'disk space',detail:'100 GiB free'}],
      })};
    }
    if(url==='/api/setup/folders/check'){
      const payload=JSON.parse(options.body);
      return {ok:true,json:async()=>({
        family:payload.family,kind:payload.kind,path:payload.path,
        status:'candidates',candidates:1,indexed:0,wrong_family:0,
        message:'Possible file; loadability untested.',
      })};
    }
    if(url==='/api/setup/folders/save'){
      const payload=JSON.parse(options.body);
      lastSaved=payload;
      const key=payload.kind;
      for(const [family,values] of Object.entries(payload.paths))
        configured.models[family][key]=values.slice();
      return {ok:true,json:async()=>({status:'saved',paths:payload.paths})};
    }
    if(url==='/api/models/scan')
      return {ok:true,json:async()=>({status:'complete',total:2,warnings:[]})};
    throw Error('Unexpected '+url);
  };
  const context={
    document:{createElement:element},
    fetch,
    window:{
      MorphorumToast:(...args)=>toasts.push(args),
      MorphorumDialog:{confirm:async()=>true},
      MorphorumModels:{reload:()=>{}},
      confirm:()=>true,
    },
  };
  vm.runInNewContext(code,context);
  const host=element();
  return {
    host,calls,toasts,configured,
    get lastSaved(){return lastSaved;},
    get reads(){return reads;},
    wizard:context.window.MorphorumSetupFolders,
    find:(className)=>descendants(host,node=>node.className?.split(' ').includes(className)),
    buttons:(text)=>descendants(host,node=>node.tag==='button' && node.textContent===text),
  };
}

test('MS6.2 inspecting is explicit, and empty pages never save or scan',async()=>{
  const h=testHarness();
  await h.wizard.render(h.host,'models');
  assert.equal(h.buttons('+ Add path').length,2);
  assert.equal(h.calls.length,1);
  assert.equal(h.calls[0].url,'/api/settings');
  assert.doesNotThrow(()=>h.wizard.beforeNext('models'));
  assert.equal(h.buttons('Save Folders & Scan').length,1);
  await h.wizard.render(h.host,'loras');
  assert.equal(h.buttons('+ Add path').length,3);
  assert.doesNotThrow(()=>h.wizard.beforeNext('loras'));
  assert.ok(h.calls.every(call=>!call.url.includes('/scan')&&!call.url.includes('/save')));
});

test('MS6.2 unsaved changes block Next, save is explicit and scans after saving',async()=>{
  const h=testHarness();
  await h.wizard.render(h.host,'models');
  h.buttons('+ Add path')[0].listeners.click();
  const input=h.find('first-run-folder-input')[0];
  input.value='D:\\Models\\SDXL';
  input.listeners.input();
  assert.throws(()=>h.wizard.beforeNext('models'),/unsaved folder edits/);
  await h.buttons('Check')[0].listeners.click();
  assert.equal(h.calls.at(-1).url,'/api/setup/folders/check');
  assert.equal(h.calls.at(-1).options.headers['X-Morphorum-Setup'],'1');
  assert.match(h.find('first-run-folder-report')[0].textContent,/Possible model\/LoRA files/);
  assert.equal(h.calls.filter(c=>c.url==='/api/settings').length,1);
  await h.buttons('Save Folders & Scan')[0].listeners.click();
  assert.equal(h.calls.at(-2).url,'/api/setup/folders/save');
  assert.equal(h.calls.at(-1).url,'/api/models/scan');
  assert.equal(h.lastSaved.kind,'checkpoints');
  assert.equal(h.lastSaved.paths.sdxl[0],'D:\\Models\\SDXL');
  assert.deepEqual(h.lastSaved.paths.flux,[]);
  assert.doesNotThrow(()=>h.wizard.beforeNext('models'));
  assert.ok(h.toasts.some(call=>call[0]==='Folder settings saved'));
});

test('MS6.2 LoRA page is optional and saves only family-specific LoRA arrays',async()=>{
  const h=testHarness();
  h.configured.models.sdxl.checkpoints=['C:\\Models'];
  await h.wizard.render(h.host,'loras');
  h.buttons('+ Add path')[2].listeners.click();
  const input=h.find('first-run-folder-input')[0];
  input.value='C:\\Z-Image\\loras';
  input.listeners.input();
  await h.buttons('Save Folders & Scan')[0].listeners.click();
  assert.equal(h.lastSaved.kind,'loras');
  assert.equal(h.lastSaved.paths.zimage[0],'C:\\Z-Image\\loras');
  assert.deepEqual(h.configured.models.sdxl.checkpoints,['C:\\Models']);
});

test('MS6.2 welcome reads host diagnostics without starting a job',async()=>{
  const h=testHarness();
  await h.wizard.welcome(h.host);
  assert.match(h.host.children[0].textContent,/100 GiB free/);
  assert.match(h.host.children[0].textContent,/Windows-test/);
  assert.deepEqual(h.calls.map(c=>c.url),['/api/system']);
});
