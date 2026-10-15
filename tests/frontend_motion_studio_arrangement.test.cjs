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
    ['preset','wave'],['blend','add'],['strength','.65'],['cycle','2'],
    ['fade','.1'],['start','12'],['end','36'],
  ].map(([k,value])=>[k,{value}]));
  const selectedAxes = [{value:'translation_x'},{value:'translation_y'}];
  inputs.axes = {querySelectorAll:()=>selectedAxes};
  inputs.name = {value:'Cinematic Orbit'};
  inputs.library = {
    value:'',children:[],
    replaceChildren(){this.children=[];},
    appendChild(child){this.children.push(child);},
  };
  inputs.status = {textContent:''};
  const panel={querySelector:selector=>{
    const key=selector.match(/^\[data-ms(?:4|43)-(\w+)\]$/)?.[1];
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
    document:{activeElement:null,createElement(){return {value:'',textContent:''};}},
    window:{MorphorumDialog:{confirm:async()=>true}},
    async api(){throw Error('Mock API not configured');},
  };
  vm.runInNewContext(js.slice(start,end)+`
    motionStudioArrangementSyncRange = () => {};
    motionStudioArrangementResetFields = () => {};
    motionStudioRenderArrangement = () => {};
    motionStudioArrangementRebuildAxes = axes => {
      selectedAxes.splice(0, selectedAxes.length, ...axes.map(value=>({value})));
    };
    this.savePreset = ms43Save;
    this.loadPreset = ms43Load;
    this.deletePreset = ms43Delete;
    this.setPresets = value => {ms43Presets=value;};
    this.stage = motionStudioArrange;
    this.remove = motionStudioArrangementRemove;
    this.choose = motionStudioArrangementSelect;
    this.selection = () => motionStudioArrangementSelection;
    this.setSelection = (value) => {motionStudioArrangementSelection=value;};
  `,ctx);
  return {ctx,layers,inputs,selectedAxes,actions,commitCount:()=>commits};
}

test('arrangement mounts in existing Motion Studio, not a second camera compositor',()=>{
  assert.match(js,/motionStudioCreateArrangementCard\(panels\.audio\)/);
  assert.match(js,/motionStudioRenderArrangement\(\)/);
  assert.match(js,/motionStudioArrangementPlayhead\)/);
  for(const name of ['gentle-drift','wave','spiral','figure-eight',
    'rocking','push-in','pull-out']) {
    assert.match(backend,new RegExp('"'+name+'"'));
    assert.ok(js.includes("['"+name+"'"),name);
  }
  assert.ok(js.includes("['still', 'Still / Clear Selected Axes']"));
  assert.match(js,/data-ms4-blend/);
  assert.match(js,/data-ms4-axes/);
  assert.match(css,/\.motion-studio-arrangement-timeline/);
  assert.match(css,/@media \(max-width:640px\)/);
  assert.match(css,/\.motion-studio-arrangement-actions/);
  assert.match(js,/motionStudioArrangementRemove\(id\)/);
  assert.match(css,/\.motion-studio-arrangement-remove/);
  assert.match(js,/data-ms43-library/);
  assert.match(js,/data-ms43-save/);
  assert.match(js,/data-ms43-update/);
  assert.match(js,/data-ms43-delete/);
  assert.match(css,/\.motion-studio-custom-presets/);
  assert.doesNotMatch(js,/addLane\('Unstaged selection'/);
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
  assert.deepEqual(Array.from(first.axes), ['translation_x','translation_y']);
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

test('removing a staged continuous movement preserves unrelated layers',async()=>{
  const {ctx,layers,commitCount,actions}=harness();
  const sound={id:'sound-1',type:'audio_channels',sha256:'b'.repeat(64)};
  layers.push(sound);
  await ctx.stage('stage');
  const movementId=layers[1].id;
  assert.equal(ctx.selection(),movementId);
  ctx.remove(movementId);
  assert.equal(layers.length,1);
  assert.strictEqual(layers[0],sound);
  assert.equal(ctx.selection(),'');
  assert.equal(commitCount(),2);
  assert.ok(actions.some(value=>value.startsWith('toast:Movement removed')));
  ctx.remove('sound-1');
  ctx.remove('missing-layer');
  assert.equal(layers.length,1);
  assert.equal(commitCount(),2);
});

test('removing another staged movement keeps the selected layer editable',async()=>{
  const {ctx,layers,commitCount}=harness();
  await ctx.stage('stage');
  const firstId=layers[0].id;
  ctx.setSelection('');
  await ctx.stage('stage');
  const secondId=layers[1].id;
  assert.notEqual(secondId,firstId);
  ctx.remove(firstId);
  assert.equal(ctx.selection(),secondId);
  assert.equal(layers.length,1);
  assert.equal(layers[0].id,secondId);
  assert.equal(commitCount(),3);
  ctx.motionLabBusy=true;
  ctx.remove(secondId);
  assert.equal(layers.length,1);
  assert.equal(commitCount(),3);
});

test('MS4.3 presets save current editor parameters without staging or changing the project',async()=>{
  const {ctx,layers,inputs,selectedAxes,actions,commitCount}=harness();
  const endpoint='/api/animation/motion-studio/custom-presets';
  const stored=[];
  ctx.api=async (url, options={})=>{
    assert.ok(url.startsWith(endpoint));
    if (!options.method) return {presets:stored.map(item=>({...item}))};
    if (options.method==='POST') {
      const body=JSON.parse(options.body);
      const item={...body,id:'saved-1'};
      stored.push(item);
      return {preset:item};
    }
    throw Error('Unexpected request');
  };
  await ctx.savePreset(false);
  assert.equal(stored.length,1);
  assert.equal(stored[0].name,'Cinematic Orbit');
  assert.equal(stored[0].preset,'wave');
  assert.deepEqual(Array.from(stored[0].axes),['translation_x','translation_y']);
  assert.equal(stored[0].start_ratio,.1);
  assert.equal(stored[0].end_ratio,.3);
  assert.equal(layers.length,0);
  assert.equal(commitCount(),0);
  assert.equal(inputs.library.value,'saved-1');
  assert.ok(actions.some(action=>action==='toast:Custom preset saved'));
});

test('MS4.3 loads proportional frame range as a new, unstaged movement',async()=>{
  const {ctx,layers,inputs,selectedAxes,commitCount}=harness();
  await ctx.stage('stage');
  const existing=layers[0];
  assert.equal(commitCount(),1);
  inputs.library.value='saved-abc';
  ctx.setPresets([{
    id:'saved-abc',name:'Spiral Sweep',preset:'spiral',blend:'replace',
    axes:['translation_z','rotation_z'],strength:.35,cycle_seconds:5,
    fade_seconds:.4,start_ratio:.25,end_ratio:.75,
  }]);
  ctx.loadPreset();
  assert.equal(ctx.selection(),'');
  assert.equal(inputs.preset.value,'spiral');
  assert.equal(inputs.blend.value,'replace');
  assert.equal(inputs.start.value,'30');
  assert.equal(inputs.end.value,'90');
  assert.deepEqual(selectedAxes.map(x=>x.value),['translation_z','rotation_z']);
  assert.equal(layers.length,1,'Loading must not stage a project movement');
  assert.equal(layers[0],existing,'Loading must not edit existing layer');
  await ctx.stage('stage');
  assert.equal(layers.length,2);
  assert.equal(layers[1].start_frame,30);
  assert.equal(layers[1].end_frame,90);
  assert.equal(layers[1].blend,'replace');
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

test('MS4.2 allows editing native replace presets with a selected axis mask',async()=>{
  const {ctx,layers,inputs,selectedAxes}=harness();
  inputs.preset.value='spiral';
  inputs.blend.value='replace';
  selectedAxes.splice(0,selectedAxes.length,{value:'translation_z'},{value:'rotation_z'});
  await ctx.stage('stage');
  assert.equal(layers[0].blend,'replace');
  assert.deepEqual(Array.from(layers[0].axes),['translation_z','rotation_z']);
  assert.match(js,/motionStudioArrangementRebuildAxes/);
  assert.match(backend,/if "axes" in layer/);
});
test('Still without Replace or without selected axes is refused',async()=>{
  const {ctx,inputs,layers,selectedAxes,actions}=harness();
  inputs.preset.value='still';
  await ctx.stage('stage');
  assert.equal(layers.length,0);
  inputs.blend.value='replace';
  selectedAxes.splice(0);
  await ctx.stage('stage');
  assert.equal(layers.length,0);
  assert.equal(actions.includes('apply'),false);
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
