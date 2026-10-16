'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const script=fs.readFileSync(path.join(__dirname,'..','frontend','dist','assets','first-run-examples.js'),'utf8');

function element(tag='div'){
  return {
    tag,children:[],style:{},attributes:{},listeners:{},hidden:false,
    disabled:false,textContent:'',value:'',className:'',
    append(...children){this.children.push(...children);},
    appendChild(el){this.children.push(el);return el;},
    replaceChildren(...items){this.children=[...items];},
    setAttribute(k,v){this.attributes[k]=String(v);},
    addEventListener(k,fn){this.listeners[k]=fn;},
  };
}
function all(root,filter){
  const result=[];const visit=node=>{
    if(filter(node))result.push(node);
    for(const child of node.children||[])visit(child);
  };visit(root);return result;
}
const EXAMPLES=[
  {id:'gentle-dolly-in',name:'Gentle Dolly In',description:'Moves toward subject'},
  {id:'gentle-dolly-out',name:'Gentle Dolly Out',description:'Moves away from subject'},
];
function harness(){
  const network=[],toast=[],confirmations=[],host=element(),state={revision:7};
  let creates=0,opened=0,completions=0,allow=true,openOK=true;
  const mockFetch=async (url,opts={})=>{
    network.push({url,opts});
    if(url==='/api/setup/examples')return {ok:true,json:async()=>({examples:EXAMPLES,version:'ms6.4-1',animation:{max_frames:48,fps:12,width:512,height:512}})};
    if(url==='/api/settings')return {ok:true,json:async()=>({settings:{models:{sdxl:{checkpoints:['C:\\Models\\SDXL'],loras:[]},flux:{},zimage:{}}}})};
    if(url==='/api/managed-models/zimage-turbo')return {ok:true,json:async()=>({status:'not_installed',installed:false})};
    if(url==='/api/models?limit=2000')return {ok:true,json:async()=>({models:[]})};
    if(url==='/api/setup/example'){
      creates++;assert.equal(opts.method,'POST');
      const data=JSON.parse(opts.body);
      assert.equal(data.template_id,'gentle-dolly-out');
      assert.equal(data.model_id,'');
      return {ok:true,json:async()=>({revision:8,project:{id:'setup-gentle-dolly-out-abc'}})};
    }
    throw Error('Unexpected API '+url);
  };
  const window={
    MorphorumDialog:{confirm:async options=>{confirmations.push(options);return allow;}},
    MorphorumFirstRunSetup:{goto:()=>{}},
  };
  vm.runInNewContext(script,{document:{createElement:element},fetch:mockFetch,window});
  const app=window.MorphorumSetupExamples;
  const flush=async()=>{await new Promise(resolve=>setImmediate(resolve));};
  const findButton=text=>all(host,e=>e.tag==='button'&&e.textContent===text)[0];
  return {
    host,network,toast,app,flush,findButton,state,confirmations,
    get creates(){return creates;},get opened(){return opened;},get completions(){return completions;},
    set allow(v){allow=v;},set openOK(v){openOK=v;},
    showExamples:snap=>app.showExamples(host,snap),
    showFinish:snap=>app.showFinish(host,snap,{
      reserved:revision=>{state.revision=revision;},
      complete:async()=>{completions++;},
      openEditor:async id=>{opened++;return openOK;},
      toast:(...args)=>toast.push(args),manual:false,
    })
  };
}

test('MS6.4 selecting two reviewable cards does not create or render',async()=>{
  const h=harness();
  await h.showExamples({});
  const cards=all(h.host,n=>n.className==='first-run-example-card');
  assert.equal(cards.length,2);
  assert.equal(cards[0].attributes['aria-pressed'],'true');
  assert.equal(cards[1].attributes['aria-pressed'],'false');
  cards[1].listeners.click();
  assert.equal(cards[1].attributes['aria-pressed'],'true');
  assert.equal(h.app.selection().template_id,'gentle-dolly-out');
  assert.equal(h.creates,0);
  assert.ok(h.network.every(x=>!x.opts.method),'Catalog and model GETs are read-only');
});

test('MS6.4 review without base model warns before explicit create and editor',async()=>{
  const h=harness();
  await h.showExamples({example_template_id:'gentle-dolly-out'});
  h.host.replaceChildren();
  await h.showFinish({revision:7,example_template_id:'gentle-dolly-out',example_model_id:''});
  assert.equal(h.creates,0);
  const notices=all(h.host,n=>n.className==='first-run-example-warning');
  assert.ok(notices.some(n=>/NOT render-ready/.test(n.textContent)));
  h.allow=false;
  await h.findButton('Create Example & Open Editor').listeners.click();
  assert.equal(h.creates,0);
  assert.equal(h.completions,0);
  h.allow=true;
  await h.findButton('Create Example & Open Editor').listeners.click();
  assert.equal(h.creates,1);
  assert.equal(h.opened,1);
  assert.equal(h.completions,1);
  assert.equal(h.confirmations.length,2);
  assert.ok(h.network.every(x=>x.url!=='/api/animation/render'));
});

test('MS6.4 failed editor handoff keeps setup incomplete',async()=>{
  const h=harness();
  await h.showFinish({revision:7,example_template_id:'gentle-dolly-out',example_model_id:''});
  h.openOK=false;
  await h.findButton('Create Example & Open Editor').listeners.click();
  assert.equal(h.creates,1);
  assert.equal(h.completions,0);
  assert.ok(h.toast.some(x=>/saved but the Project Editor could not open/.test(x[1])));
});

test('MS6.4 Finish Without Example completes without creating a project',async()=>{
  const h=harness();
  await h.showFinish({revision:7,example_template_id:'gentle-dolly-out',example_model_id:''});
  await h.findButton('Finish Without Example').listeners.click();
  assert.equal(h.creates,0);
  assert.equal(h.completions,1);
});


test('MS6.5 catalog must finish loading before example choice can advance',async()=>{
  const h=harness();
  assert.throws(()=>h.app.selection(),/not ready/i);
  const progress=[];
  await h.app.showExamples(h.host,{}, {onReady:ready=>progress.push(ready)});
  assert.deepEqual(progress,[false,true]);
  assert.equal(h.app.selection().template_id,'gentle-dolly-in');
  h.app.leave();
  assert.throws(()=>h.app.selection(),/not ready/i);
});

test('MS6.5 vanished selected model blocks example creation, not falsely treated as render-ready',async()=>{
  const h=harness();
  await h.showFinish({revision:7,example_template_id:'gentle-dolly-in',
    example_model_id:'missing-checkpoint'});
  assert.equal(h.findButton('Create Example & Open Editor').disabled,true);
  assert.ok(all(h.host,e=>/no longer indexed/i.test(e.textContent||'')).length>0);
  assert.equal(h.creates,0);
  await h.findButton('Finish Without Example').listeners.click();
  assert.equal(h.completions,1);
  assert.equal(h.creates,0);
});
