'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const root=path.join(__dirname,'..','frontend','dist');
const js=fs.readFileSync(path.join(root,'assets','animation.js'),'utf8');
const html=fs.readFileSync(path.join(root,'index.html'),'utf8');
const css=fs.readFileSync(path.join(root,'assets','animation.css'),'utf8');
const start=js.indexOf('  let motionCompareMetadata=null;');
const end=js.indexOf('  function motionReviewSet(start,end,enabled=true) {',start);
assert.ok(start>0 && end>start);

function harness(apiHandler) {
  const el=()=>({textContent:'',hidden:false,value:'',src:'',children:[],
    replaceChildren(){this.children=[];},
    appendChild(node){this.children.push(node);},
    get options(){return this.children;},
    getAttribute(key){return key==='src' ? this.src : null;},
    removeAttribute(key){if(key==='src')this.src='';},
  });
  const fields=Object.fromEntries(['select','render-wrap','render-image','frame-label',
    'status'].map(key=>[key,el()]));
  const state={project:{id:'project-a'}};
  const player={jobId:'preview-1',count:4,fps:24,frame:1};
  const context={
    state,motionFramePlayer:player,
    qs:selector=>fields[selector.replace('#animation-motion-compare-','')]||null,
    api:apiHandler,
    motionReviewMatch:()=>'',encodeURIComponent,
    document:{createElement:()=>({value:'',textContent:''})},
  };
  vm.runInNewContext(js.slice(start,end)+
    '\nthis.actions={refresh:motionCompareRefresh,load:motionCompareLoad,'+
    'frame:motionCompareFrame,clear:motionCompareClear};',context);
  return {fields,state,player,...context.actions};
}
const valid={project_id:'project-a',render_id:'render-1',status:'completed',
  fps:24,frames:4,recorded_frames:4,ready:true,issues:[]};

test('MS5.2 lists current project renders and follows shared frame seek with exact saved PNG',async()=>{
  const calls=[];
  const h=harness(async url=>{
    calls.push(url);
    return url.endsWith('/renders')
      ? {renders:[{id:'render-1',project_id:'project-a',status:'completed',total_frames:4},
        {id:'other',project_id:'other-project',status:'completed'}]}
      : valid;
  });
  await h.refresh();
  assert.equal(h.fields.select.children.length,2);
  assert.match(h.fields.status.textContent,/Choose a completed render/);
  h.fields.select.value='render-1';
  await h.load();
  assert.equal(h.fields['render-wrap'].hidden,false);
  assert.equal(h.fields['render-image'].src,
    '/api/animation/renders/project-a/render-1/frames/1');
  h.frame(3);
  assert.equal(h.fields['render-image'].src,
    '/api/animation/renders/project-a/render-1/frames/3');
  assert.match(h.fields['frame-label'].textContent,/Exact render frame 3/);
  assert.deepEqual(calls,[
    '/api/animation/projects/project-a/renders',
    '/api/animation/renders/project-a/render-1/review-metadata',
  ]);
  h.clear();
  assert.equal(h.fields['render-wrap'].hidden,true);
  assert.equal(h.fields['render-image'].src,'');
  h.frame(2);
  assert.equal(h.fields['render-image'].src,'');
});

test('MS5.2 refuses missing render coverage, wrong FPS and wrong project',async()=>{
  for(const failure of [
    {...valid,ready:false,issues:['One or more rendered PNG frames are missing.']},
    {...valid,fps:25},
    {...valid,frames:5},
    {...valid,project_id:'different-project'},
  ]){
    const h=harness(async()=>failure);
    h.fields.select.value='render-1';
    await h.load();
    assert.equal(h.fields['render-wrap'].hidden,true);
    assert.equal(h.fields['render-image'].src,'');
    assert.match(h.fields.status.textContent,/mismatch|not available/i);
  }
});

test('MS5.2 asynchronous render metadata from old project is ignored',async()=>{
  let complete;
  const h=harness(()=>new Promise(resolve=>{complete=resolve;}));
  h.fields.select.value='render-1';
  const loading=h.load();
  h.state.project.id='project-b';
  complete(valid);
  await loading;
  assert.equal(h.fields['render-wrap'].hidden,true);
  assert.equal(h.fields['render-image'].src,'');
});

test('MS5.2 markup is unique and side-by-side layout collapses on small screens',()=>{
  for(const id of ['animation-motion-review-split','animation-motion-compare-render-wrap',
    'animation-motion-compare-render-image','animation-motion-compare-select',
    'animation-motion-compare-load','animation-motion-compare-refresh',
    'animation-motion-compare-clear','animation-motion-compare-status']) {
    assert.equal((html.match(new RegExp('id="'+id+'"','g'))||[]).length,1,id);
  }
  assert.match(css,/\.motion-review-split\s*\{/);
  assert.match(css,/@media\(max-width:650px\)/);
  assert.match(js,/motionCompareFrame\(frame\);/);
  assert.match(js,/void motionCompareRefresh\(\);/);
  assert.match(js,/motionCompareClear\('Generate a CPU camera preview/);
});
