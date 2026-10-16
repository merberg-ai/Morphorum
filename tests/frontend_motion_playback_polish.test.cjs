'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const base=path.join(__dirname,'..','frontend','dist');
const js=fs.readFileSync(path.join(base,'assets','animation.js'),'utf8');
const css=fs.readFileSync(path.join(base,'assets','animation.css'),'utf8');
const html=fs.readFileSync(path.join(base,'index.html'),'utf8');
const extract=(a,b)=>{
  const start=js.indexOf(a),end=js.indexOf(b,start+a.length);
  assert.ok(start>=0&&end>start,a+' missing');
  return js.slice(start,end);
};
function deferred(){
  let resolve,reject;
  const promise=new Promise((a,b)=>{resolve=a;reject=b;});
  return {promise,resolve,reject};
}

test('MS5.4 stale preview poll never updates a different project or restarts timer',async()=>{
  const pending=deferred(),actions=[];
  const state={project:{id:'new'},motionJobId:'old',motionPollTimer:null};
  const ctx={
    state,
    api:()=>pending.promise,
    updateMotionProgress:()=>actions.push('progress'),
    finishMotionPreview:()=>actions.push('finish'),
    pollMotionPreview:()=>actions.push('again'),
    window:{setTimeout:()=>{actions.push('timer');return 1;}},
    encodeURIComponent,
  };
  vm.runInNewContext(extract('  async function pollMotionPreview(jobId) {',
    '  async function generateMotionPreview(',),ctx);
  const polling=ctx.pollMotionPreview('old');
  // A project reload/switch clears the expected job ID while the request is in flight.
  state.motionJobId=null;
  pending.resolve({id:'old',status:'completed',result:{frame_player_samples:4}});
  await polling;
  assert.deepEqual(actions,[],'stale HTTP completion must have no side effects');
});

test('MS5.4 stale preview poll errors never retry after project switch',async()=>{
  const pending=deferred(),actions=[];
  const state={project:{id:'new'},motionJobId:'old',motionPollTimer:null};
  const ctx={state,api:()=>pending.promise,
    updateMotionProgress:()=>actions.push('progress'),
    finishMotionPreview:()=>actions.push('finish'),
    window:{setTimeout:()=>{actions.push('retry');return 2;}},
    encodeURIComponent};
  vm.runInNewContext(extract('  async function pollMotionPreview(jobId) {',
    '  async function generateMotionPreview(',),ctx);
  const polling=ctx.pollMotionPreview('old');
  state.motionJobId=null;
  pending.reject(Error('Disconnected'));
  await polling;
  assert.deepEqual(actions,[]);
});

test('MS5.4 late render-history responses cannot show old-project renders',async()=>{
  const pending=deferred(),actions=[];
  const state={project:{id:'old'},renderJobId:null};
  const ctx={state,renderHistoryGeneration:0,
    api:()=>pending.promise,
    populateRenderHistory:r=>actions.push('populate:'+r.length),
    renderAnimationJob:()=>actions.push('render'),
    loadVideoExportHistory:async()=>actions.push('videos'),
    resetRenderUi:()=>actions.push('reset'),
    toast:()=>actions.push('toast'),
    encodeURIComponent};
  vm.runInNewContext(extract('  async function loadRenderHistory() {',
    '  async function showRender(',),ctx);
  const result=ctx.loadRenderHistory();
  state.project.id='new';
  pending.resolve({renders:[{id:'old-render',project_id:'old',status:'interrupted'}]});
  await result;
  assert.deepEqual(actions,[]);
});

test('MS5.4 incompatible completed preview falls back to GIF instead of poll retry',()=>{
  assert.match(js,/catch \(error\) \{\s*motionFramePlayer\.clear\(\);/);
  assert.match(js,/Frame player unavailable: /);
  assert.match(js,/if \(image\) \{\s*image\.hidden = loadedFrames;/);
  assert.match(js,/if \(state\.motionJobId !== jobId\) return;/);
  assert.match(js,/if \(state\.project\?\.id !== requestedProjectId\) return;/);
  assert.match(js,/renderHistoryGeneration/);
  assert.match(js,/job\.project_id && job\.project_id !== state\.project\?\.id/);
  assert.match(js,/const issue = motionReviewMatch\(\)/);
  assert.match(js,/canPlay: \(\) =>/);
});

test('MS5.4 mobile preview and editor controls fit small screens without giant checkboxes',()=>{
  assert.match(css,/#view-animation #animation-motion-frame-player input\[type="checkbox"\]/);
  assert.match(css,/width:16px !important/);
  assert.match(css,/@media\(max-width:390px\)/);
  assert.match(css,/\.motion-review-render-chooser select \{width:100%;min-width:0;\}/);
  assert.match(css,/\.motion-review-refine-actions button \{width:100%;min-width:0;white-space:normal;\}/);
  for(const id of ['animation-motion-frame-player','animation-motion-review-enabled',
    'animation-motion-refine-continuous','animation-motion-compare-render-image']){
    assert.equal((html.match(new RegExp('id="'+id+'"','g'))||[]).length,1);
  }
  assert.match(js,/motionLabAudioProjectId === state\.project\?\.id \? motionLabAudioElement : null/);
});
