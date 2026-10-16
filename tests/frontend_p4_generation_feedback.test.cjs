'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const root=path.join(__dirname,'..','frontend','dist');
const read=(path)=>fs.readFileSync(require('node:path').join(root,path),'utf8');
const image=read('assets/image.js');
const animation=read('assets/animation.js');
const html=read('index.html');

test('Image submit and model-unload operations have distinct in-flight locks',()=>{
  assert.match(image,/submitting: false/);
  assert.match(image,/unloading: false/);
  assert.match(image,/if \(state\.activeJobId \|\| state\.submitting \|\| state\.unloading\) return/);
  assert.match(image,/MorphorumOperations\?\.begin\('image-submit'/);
  assert.match(image,/MorphorumOperations\?\.finish\('image-submit'/);
  assert.match(image,/MorphorumOperations\?\.begin\('image-model-unload'/);
  assert.match(image,/MorphorumOperations\?\.finish\('image-model-unload'/);
  assert.match(image,/state\.submitting = false;[\s\S]*setGenerateBusy\(Boolean\(state\.activeJobId\)\)/);
});

test('Manual job history refresh uses a busy indicator; reconnect remains silent',()=>{
  assert.match(html,/id="image-history-refresh"[^>]*><span class="spinner"><\/span>/);
  assert.match(image,/loadImageJobHistory\(\{ announce: true \}\)/);
  assert.match(image,/if \(announce && state\.historyRefreshing\) return/);
  assert.match(image,/window\.MorphorumOperations\?\.finish\('image-history'/);
  assert.match(image,/if \(reconnect\) \{/);
});

test('Motion Lab CPU preview tracks real job progress and both terminal outcomes',()=>{
  assert.match(animation,/let motionPreviewOperation = null/);
  assert.match(animation,/MorphorumOperations\?\.begin\('motion-preview'/);
  assert.match(animation,/MorphorumOperations\?\.update\('motion-preview'/);
  assert.match(animation,/MorphorumOperations\?\.finish\('motion-preview'/);
  assert.match(animation,/motionPreviewOperation\.jobId === job\.id/);
  assert.match(animation,/motionPreviewOperation = null/);
  assert.match(animation,/job\.progress == null \? null : Number\(job\.progress\) \* 100/);
  assert.match(animation,/tone: job\.status === 'failed' \? 'error' : 'success'/);
});

test('Motion draft preview/apply operation respects confirmation and cancellations',()=>{
  const start=animation.indexOf('  async function motionLabPreviewOrApply(');
  const end=animation.indexOf('  // Motion Lab is first-class;',start);
  assert.ok(end>start);
  const body=animation.slice(start,end);
  assert.match(body,/MorphorumOperations\?\.begin\('motion-lab-workflow'/);
  assert.match(body,/completeOperation\(\{\s*tone: 'warning'/);
  assert.match(body,/title: 'Motion Lab action cancelled'/);
  assert.match(body,/title: 'Motion Lab applied successfully'/);
  assert.match(body,/title: 'Motion Lab draft compiled'/);
  assert.match(body,/if \(!approved \|\| state\.project\?\.id !== projectId\) return/);
  assert.match(body,/payload\.rebase_current = true/);
});

test('Preflight and queuing feedback preserves frozen browser draft and real queued job',async()=>{
  const start=animation.indexOf('  async function startAnimationRender() {');
  const end=animation.indexOf('  async function cancelAnimationRender()',start);
  assert.ok(end>start);
  const body=animation.slice(start,end);
  assert.match(body,/MorphorumOperations\?\.begin\('animation-render-submit'/);
  assert.match(body,/title: 'Animation render blocked'/);
  assert.match(body,/title: 'Animation render not submitted'/);
  assert.match(body,/title: 'Render submission cancelled: settings changed'/);
  assert.match(body,/title: 'Animation render queued'/);
  assert.match(body,/title: 'Animation render could not start'/);
  assert.match(body,/JSON\.stringify\(collectProject\(\)\) !== frozen/);
  const calls=[];
  const ops={begin(...args){calls.push(['begin',...args]);return 31;},
    update(...args){calls.push(['update',...args]);},
    finish(...args){calls.push(['finish',...args]);}};
  const context={
    state:{project:{id:'p4'},renderJobId:null,motionJobId:null},
    animationRenderStarting:false,motionPreviewStarting:false,
    qs:()=>({classList:{add(){}},disabled:false}),
    motionLabSyncQuickActions(){},renderIsActive:()=>false,
    collectProject:()=>({id:'p4',animation:{width:1024,height:1024}}),
    runRenderPreflight:async()=>({valid:true,warnings:0,errors:0,issues:[]}),
    api:async(url)=>{assert.equal(url,'/api/animation/renders');return{id:'render-1',status:'queued'};},
    renderAnimationJob(){},showAnimationTab(){},pollAnimationRender(){},
    loadRenderHistory:async()=>{throw new Error('history offline');},
    renderSourceState(){},toast(){},
    window:{MorphorumOperations:ops},
  };
  vm.runInNewContext(body+'\nthis.start=startAnimationRender;',context);
  await context.start();
  assert.equal(context.state.renderJobId,'render-1');
  assert.equal(calls.filter(x=>x[0]==='finish'&&x[3]?.title==='Animation render queued').length,1);
  assert.equal(calls.filter(x=>x[0]==='finish'&&x[3]?.tone==='error').length,0);
  assert.equal(context.animationRenderStarting,false);
});

test('Preflight blocks invalid settings and never calls the queue endpoint',async()=>{
  const start=animation.indexOf('  async function startAnimationRender() {');
  const end=animation.indexOf('  async function cancelAnimationRender()',start);
  const events=[];
  const context={
    state:{project:{id:'p4'},motionJobId:null},
    animationRenderStarting:false,motionPreviewStarting:false,
    qs:()=>({classList:{add(){}},disabled:false}),
    motionLabSyncQuickActions(){},renderIsActive:()=>false,
    collectProject:()=>({id:'p4'}),
    runRenderPreflight:async()=>({valid:false,warnings:0,errors:2,issues:[]}),
    api:async()=>{throw Error('queue must not be called');},
    showAnimationTab(){},renderSourceState(){},toast(){},
    window:{MorphorumOperations:{begin(){return 99;},finish(...x){events.push(x);},update(){}}},
  };
  vm.runInNewContext(animation.slice(start,end)+'\nthis.start=startAnimationRender;',context);
  await context.start();
  assert.equal(events.length,1);
  assert.equal(events[0][2].tone,'error');
});

test('Auto-updated motion curves avoid repeated banners and project switches retire stale previews',()=>{
  const start=animation.indexOf('  async function motionLabPreviewOrApply(');
  const end=animation.indexOf('  // Motion Lab is first-class;',start);
  const section=animation.slice(start,end);
  assert.match(section,/const operation = curvesOnly \? null : window\.MorphorumOperations\?\.begin\('motion-lab-workflow'/);
  assert.match(section,/if \(curvesOnly\) return;/);
  const clearStart=animation.indexOf('  function clearMotionPreviewResult() {');
  const clearEnd=animation.indexOf('  async function uploadSourceImage(',clearStart);
  const clear=animation.slice(clearStart,clearEnd);
  assert.match(clear,/title: 'Camera preview no longer tracked'/);
  assert.match(clear,/motionPreviewOperation = null/);
  assert.match(clear,/state\.motionJobId = null/);
});
