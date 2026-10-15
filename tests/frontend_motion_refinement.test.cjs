'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');

const root=path.join(__dirname,'..','frontend','dist');
const script=fs.readFileSync(path.join(root,'assets','animation.js'),'utf8');
const html=fs.readFileSync(path.join(root,'index.html'),'utf8');
const css=fs.readFileSync(path.join(root,'assets','animation.css'),'utf8');
const start=script.indexOf('  let motionRefineBaseline=null;');
const end=script.indexOf('  function motionReviewSet(start,end,enabled=true) {',start);
assert.ok(start>0 && end>start,'MS5.3 functions available');

const axes=['translation_x','translation_y','translation_z',
  'rotation_x','rotation_y','rotation_z'];
function harness() {
  const el=(value='')=>({value,checked:false,textContent:'',hidden:true,
    options:[],handlers:{},addEventListener(type,fn){this.handlers[type]=fn;}});
  const nodes=Object.fromEntries(['status','results','continuous','punch','before','diff',
    'a','b','enabled','take'].map(key=>[key,el()]));
  nodes.a.value='4';
  nodes.b.value='12';
  nodes.enabled.checked=true;
  const project={id:'project-one',animation:{max_frames:48,fps:24}};
  const state={project};
  const player={jobId:'cpu-1',count:48,fps:24,frame:4,paused:false,
    pause(){this.paused=true;}};
  const fields={start:el('0'),end:el('48')};
  const rec=Object.fromEntries(['mode','target','start','end'].map(key=>
    [key,el(key==='mode'?'new':'')]));
  rec.target.options=[{value:''},{value:'0'},{value:'1'}];
  const armed=axes.map(axis=>({checked:true,dataset:{motionRecordAxis:axis}}));
  const layers=[{id:'other',type:'preset'},{
    id:'recording-a',type:'recording',start_frame:2,end_frame:18,
    fps:24,axes:['translation_x','rotation_y'],
  }];
  let selection='old',loaded='old',tab='',notify='',resets=0,compiles=0;
  const frameSeries=()=>Object.fromEntries(axes.map(axis=>[axis,Array(48).fill(0)]));
  let nextCurves=frameSeries();
  const visual={series:frameSeries(),count:48,fps:24,stale:false,
    invalidate(){this.stale=true;}};
  const context={
    state,motionFramePlayer:player,motionLabRecorder:null,motionLabBusy:false,
    motionLabDraftLayers:layers,motionLabVisual:visual,Array,Object,Number,Math,
    motionStudioArrangementSelection:selection,motionStudioArrangementLoaded:loaded,
    motionReviewMatch:()=>'',animationMode:()=> '3d',
    motionReviewEl:key=>nodes[key],
    motionLabPreviewOrApply:async()=>{compiles++;visual.series=nextCurves;visual.stale=false;},
    motionStudioArrangementFields:()=>fields,
    motionStudioArrangementResetFields:()=>{resets++;fields.start.value='0';fields.end.value='48';},
    motionStudioArrangementSyncRange:()=>{},
    motionLabPunchUi:()=>{},motionLabRecordingUi:()=>{},
    motionLabNotify:message=>{notify=message;},
    showAnimationTab:name=>{tab=name;},
    qsa:selector=>selector==='[data-motion-record-axis]'?armed:[],
    qs:selector=>{
      const refineKey=selector.match(/^#animation-motion-refine-(.+)$/)?.[1];
      if(refineKey)return nodes[refineKey]||null;
      const keys={
        '#animation-motion-lab-record-mode':'mode',
        '#animation-motion-lab-punch-target':'target',
        '#animation-motion-lab-record-start':'start',
        '#animation-motion-lab-punch-end':'end',
      };
      return rec[keys[selector]]||null;
    },
  };
  vm.runInNewContext(script.slice(start,end)+
    '\nthis.ms5={continuous:motionRefineContinuous,punch:motionRefinePunch,'+
    'before:motionRefineBefore,diff:motionRefineDiff,clear:motionRefineClear,'+
    'range:motionRefineRange};',context);
  return {actions:context.ms5,ctx:context,nodes,fields,rec,armed,layers,
    visual,player,
    setCurves(value){nextCurves=value;},
    newSeries:frameSeries,
    state(){return {selection:context.motionStudioArrangementSelection,
      loaded:context.motionStudioArrangementLoaded,resets,tab,notify,compiles};},
  };
}

test('MS5.3 safely prepares new continuous correction from inclusive A/B',()=>{
  const h=harness();
  const prior=JSON.stringify(h.layers);
  h.actions.continuous();
  assert.equal(h.fields.start.value,'4');
  assert.equal(h.fields.end.value,'13');
  assert.equal(h.state().selection,'');
  assert.equal(h.state().loaded,'');
  assert.equal(h.state().resets,1);
  assert.equal(h.state().tab,'audio');
  assert.equal(JSON.stringify(h.layers),prior,'Prepare must not stage a layer');
  assert.equal(h.player.paused,true);
  assert.match(h.nodes.status.textContent,/No layer has been changed yet/);
});

test('MS5.3 prepares scoped punch-in using exact take, arming only compatible axes',()=>{
  const h=harness();
  h.nodes.take.value='recording-a';
  const prior=JSON.stringify(h.layers);
  h.actions.punch();
  assert.equal(h.rec.mode.value,'punch');
  assert.equal(h.rec.target.value,'1');
  assert.equal(h.rec.start.value,'4');
  assert.equal(h.rec.end.value,'13');
  assert.deepEqual(h.armed.filter(x=>x.checked).map(x=>x.dataset.motionRecordAxis),
    ['translation_x','rotation_y']);
  assert.equal(h.state().tab,'recording');
  assert.equal(JSON.stringify(h.layers),prior);
});

test('MS5.3 rejects invalid ranges, nonmatching FPS and take coverage',()=>{
  const h=harness();
  h.nodes.enabled.checked=false;
  h.actions.continuous();
  assert.equal(h.state().tab,'');
  h.nodes.enabled.checked=true;
  h.nodes.b.value='49';
  h.actions.continuous();
  assert.equal(h.state().tab,'');
  h.nodes.b.value='12';
  h.nodes.take.value='recording-a';
  h.layers[1].fps=30;
  h.actions.punch();
  assert.equal(h.state().tab,'');
  assert.match(h.nodes.status.textContent,/entirely inside.*same FPS/);
  h.layers[1].fps=24;
  h.nodes.a.value='0';
  h.actions.punch();
  assert.equal(h.state().tab,'');
  h.nodes.a.value='4';
  h.ctx.motionLabBusy=true;
  h.actions.continuous();
  assert.equal(h.state().tab,'');
});

test('MS5.3 before/after draft curve diff shows changed and out-of-range axes',async()=>{
  const h=harness();
  h.setCurves(h.newSeries());
  await h.actions.before();
  assert.equal(h.state().compiles,1);
  assert.match(h.nodes.status.textContent,/Before snapshot captured/);
  const modified=h.newSeries();
  modified.translation_x[4]=.05;
  modified.translation_x[12]=.09;
  modified.rotation_y[7]=.2;
  modified.translation_y[18]=.1; // deliberately outside A/B
  h.setCurves(modified);
  await h.actions.diff();
  assert.equal(h.state().compiles,2);
  assert.match(h.nodes.status.textContent,/2 axis\/axes changed within A\/B/);
  assert.match(h.nodes.status.textContent,/1 outside-frame axis changes/);
  assert.match(h.nodes.results.textContent,/translation x: 2 frame/);
  assert.match(h.nodes.results.textContent,/translation y: 0 frame/);
  assert.match(h.nodes.results.textContent,/rotation y: 1 frame/);
  assert.equal(h.nodes.results.hidden,false);
  assert.equal(h.state().selection,'old','Diff must not change Motion Lab selection');
  h.nodes.a.value='5';
  await h.actions.diff();
  assert.match(h.nodes.status.textContent,/exact A\/B interval/);
  h.actions.clear();
  assert.equal(h.nodes.results.hidden,true);
});

test('MS5.3 checkboxes keep compact fixed dimensions and controls remain unique',()=>{
  for(const id of ['animation-motion-refine-continuous','animation-motion-refine-punch',
    'animation-motion-refine-before','animation-motion-refine-diff',
    'animation-motion-refine-status','animation-motion-refine-results']){
    assert.equal((html.match(new RegExp('id="'+id+'"','g'))||[]).length,1,id);
  }
  assert.match(css,/#view-animation #animation-motion-frame-player input\[type="checkbox"\]/);
  assert.match(css,/width:16px !important/);
  assert.match(css,/height:16px !important/);
  assert.match(css,/@media\(max-width:390px\)/);
  assert.match(script,/motionRefineBind\(\);/);
});
