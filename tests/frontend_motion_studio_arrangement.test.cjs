'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const root = path.join(__dirname, '..');
const js = fs.readFileSync(path.join(root,'frontend/dist/assets/animation.js'),'utf8');
const css = fs.readFileSync(path.join(root,'frontend/dist/assets/animation.css'),'utf8');
const backend = fs.readFileSync(path.join(root,'backend/morphorum/motion_lab.py'),'utf8');
const start = js.indexOf('  // MS4.1: continuous motion arrangement uses canonical');
const end = js.indexOf('  // MS3: Audio-frequency channels share ONE Motion Lab layer',start);
assert.ok(start > 0 && end > start,'MS4.1 block must be isolated and precede MS3');

function harness() {
  const layers=[];
  let commits=0;
  const actions=[];
  const inputs = Object.fromEntries([
    ['preset','wave'],['strength','.65'],['cycle','2'],
    ['fade','.1'],['start','12'],['end','36'],
  ].map(([k,value])=>[k,{value}]));
  const panel={querySelector:selector=>{
    const key=selector.match(/^\[data-ms4-(\w+)\]$/)?.[1];
    return inputs[key] || null;
  }};
  const state={project:{id:'project-a',animation:{mode:'3d',fps:24,max_frames:120}}};
  const ctx={
    state,motionLabDraftLayers:layers,motionLabBusy:false,motionLabAudioElement:null,
    motionLabAudioProjectId:null,
    motionLabNotify(message){actions.push('notify:'+message);},
    toast(...args){actions.push('toast:'+args[0]);},
    qs(sel){return sel==='#animation-motion-studio-arrangement'?panel:null;},
    animationMode:()=> '3d',
    commitMotionLabDraft(){commits++;},
    async motionLabPreviewOrApply(apply,opts){actions.push(apply?'apply':opts?.curvesOnly?'curves':'preview');},
    document:{activeElement:null},
  };
  vm.runInNewContext(js.slice(start,end)+`
    motionStudioArrangementSyncRange = () => {};
    this.stage = motionStudioArrange;
    this.choose = motionStudioArrangementSelect;
    this.selection = () => motionStudioArrangementSelection;
    this.setSelection = (value) => {motionStudioArrangementSelection=value;};
  `,ctx);
  return {ctx,layers,inputs,actions,commitCount:()=>commits};
}

test('arrangement mounts in existing Motion Studio, not a second camera compositor',()=>{
  assert.match(js,/motionStudioCreateArrangementCard\(panels\.audio\)/);
  assert.match(js,/motionStudioRenderArrangement\(\)/);
  assert.match(js,/motionStudioArrangementPlayhead\)/);
  for(const name of ['gentle-drift','wave','spiral','figure-eight',
    'rocking','push-in','pull-out','still']) {
    assert.match(backend,new RegExp('"'+name+'"'));
    assert.ok(js.includes("['"+name+"'"),name);
  }
  assert.match(css,/\.motion-studio-arrangement-timeline/);
  assert.match(css,/@media \(max-width:640px\)/);
  assert.match(css,/\.motion-studio-arrangement-actions/);
});

test('stage and update same preset without doubling or deleting sound layers',async()=>{
  const {ctx,layers,inputs,commitCount}=harness();
  const untouched={id:'sound',type:'audio_channels',sha256:'d'.repeat(64)};
  layers.push(untouched);
  await ctx.stage('stage');
  assert.equal(layers.length,2);
  const first=layers[1];
  assert.equal(first.type,'preset');
  assert.equal(first.preset,'wave');
  assert.equal(first.blend,'add');
  assert.equal(first.start_frame,12);
  assert.equal(first.end_frame,36);
  assert.equal(commitCount(),1);
  inputs.preset.value='spiral';
  inputs.strength.value='.3';
  await ctx.stage('stage');
  assert.equal(layers.length,2);
  assert.equal(layers[1].id,first.id);
  assert.equal(layers[1].preset,'spiral');
  assert.equal(layers[1].strength,.3);
  assert.equal(layers[0],untouched);
  assert.equal(commitCount(),2);
});

test('preview stages native preset then invokes existing curve diagnostics',async()=>{
  const {ctx,actions,layers}=harness();
  await ctx.stage('preview');
  assert.deepEqual(actions,['curves']);
  assert.equal(layers.length,1);
  await ctx.stage('apply');
  assert.deepEqual(actions,['curves','apply']);
  assert.equal(layers.length,1);
});

test('invalid movement never modifies draft or starts preview',async()=>{
  const {ctx,layers,inputs,actions}=harness();
  inputs.cycle.value='0';
  await ctx.stage('apply');
  assert.equal(layers.length,0);
  assert.equal(actions.includes('apply'),false);
  assert.ok(actions.some(x=>x.includes('Check')));
});

test('stage does not overwrite unrelated layer when 24 slots are occupied',async()=>{
  const {ctx,layers,actions}=harness();
  for(let i=0;i<24;i++)layers.push({id:'other-'+i,type:'audio_cues'});
  await ctx.stage('preview');
  assert.equal(layers.length,24);
  assert.equal(actions.includes('curves'),false);
});
