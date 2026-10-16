'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const src = fs.readFileSync(path.join(__dirname, '..', 'frontend', 'dist', 'assets', 'animation.js'),'utf8');
const html = fs.readFileSync(path.join(__dirname, '..', 'frontend', 'dist', 'index.html'),'utf8');

function extract(a,b) {
  const first=src.indexOf(a);
  const last=src.indexOf(b,first);
  assert.ok(first>=0 && last>first,'missing extraction markers '+a+' → '+b);
  return src.slice(first,last);
}

function makeSelect(value='') {
  return {
    value, disabled:false, options:[], title:'',
    replaceChildren(){this.options=[];this.value='';},
    appendChild(option){this.options.push(option);},
  };
}
function setup(project={id:'project-x',model:{model_id:'saved-model'},generation:{sampler:'saved-sampler'}}) {
  const model=makeSelect(project?.model?.model_id||'');
  const sampler=makeSelect(project?.generation?.sampler||'');
  const deforum=makeSelect('other-model');
  const status={hidden:true,textContent:''};
  const nodes=new Map([
    ['#animation-model',model],['#animation-sampler',sampler],
    ['#animation-deforum-model',deforum],['#animation-model-index-status',status]
  ]);
  const created=()=>({value:'',textContent:''});
  const state={project,models:[],dirty:true,modelIndexSignature:null,
    modelIndexStale:false,modelIndexRevision:0};
  let resolutionCalls=0,guidanceCalls=0;
  const env={
    state,document:{createElement:created},
    qs:sel=>nodes.get(sel)||null,
    populateSamplerSelect(preferred) {this.lastPreferredSampler=preferred;},
    populateResolutionPresets(){resolutionCalls++;},
    renderEditorGuidance(){guidanceCalls++;},
    toast(){throw Error('Unexpected toast')},
  };
  // Use a wrapper context: the real dropdown implementations are retained,
  // but model capabilities/rendering and unrelated DOM sections are stubbed.
  const block=extract('  function populateModelSelect(', '  function renderProjectSelect()')+
    '\n'+extract('  function modelIndexSignature(', '  function setDeforumImportBusy(');
  const code=block+
    '\nthis.applyIndex=applyAnimationModelIndex;'+
    '\nthis.updated=onAnimationModelsUpdated;'+
    '\nthis.populate=populateModelSelect;'+
    '\nthis.getState=()=>state;';
  vm.runInNewContext(code,env);
  return {env,state,model,sampler,deforum,status,created,
    get resolutionCalls(){return resolutionCalls;},
    get guidanceCalls(){return guidanceCalls;}};
}
function models(ids) {
  return ids.map((id,index)=>({id,kind:'checkpoints',name:id,family:'sdxl',variant:index?'v2':'v1'}));
}

test('Model Manager event adds checkpoints while preserving unsaved model and sampler choice',()=>{
  const t=setup();
  t.model.value='unsaved-model';
  t.sampler.value='custom-sampler';
  const settings=JSON.stringify(t.state.project);
  t.env.updated({detail:{loaded:true,models:models(['saved-model','unsaved-model'])}});
  assert.equal(t.model.value,'unsaved-model');
  assert.equal(t.env.lastPreferredSampler,'custom-sampler');
  assert.equal(t.state.dirty,true);
  assert.equal(JSON.stringify(t.state.project),settings);
  assert.equal(t.model.options.length,3);
  assert.equal(t.status.hidden,true);
  assert.equal(t.state.modelIndexRevision,1);
});

test('Cleared selection stays cleared, and unchanged scans do not rebuild DOM',()=>{
  const t=setup();
  t.model.value='';
  const payload=models(['saved-model']);
  t.env.updated({detail:{loaded:true,models:payload}});
  assert.equal(t.model.value,'');
  const first=t.model.options;
  t.env.updated({detail:{loaded:true,models:[...payload]}});
  assert.equal(t.model.options,first);
  assert.equal(t.state.dirty,true);
});

test('Missing saved checkpoint remains visible until user explicitly chooses replacement',()=>{
  const t=setup();
  t.model.value='saved-model';
  t.env.updated({detail:{loaded:true,models:models(['another-model'])}});
  assert.equal(t.model.value,'saved-model');
  assert.ok(t.model.options.some(x=>x.value==='saved-model'&&/Missing indexed model/.test(x.textContent)));
  assert.equal(t.state.project.model.model_id,'saved-model');
});

test('Failed model refresh retains last usable index and warns without altering project',()=>{
  const t=setup();
  t.env.updated({detail:{loaded:true,models:models(['saved-model'])}});
  t.env.updated({detail:{loaded:false,models:[]}});
  assert.equal(t.state.models.length,1);
  assert.equal(t.state.modelIndexStale,true);
  assert.equal(t.status.hidden,false);
  assert.match(t.status.textContent,/Keeping the last known models/);
  t.env.updated({detail:{loaded:true,models:models(['saved-model'])}});
  assert.equal(t.state.modelIndexStale,false);
  assert.equal(t.status.hidden,true);
});

test('Model selection rebuild respects project load vs live-refresh intent',()=>{
  const t=setup();
  t.state.models=models(['saved-model','unsaved-model']);
  t.model.value='unsaved-model';
  t.env.populate();
  assert.equal(t.model.value,'saved-model');
  t.model.value='unsaved-model';
  t.env.populate({preserveSelection:true});
  assert.equal(t.model.value,'unsaved-model');
});

test('Event listener is installed ahead of initial async loads and stale fetch is guarded',()=>{
  const start=src.indexOf("  async function start() {");
  const chunk=src.slice(start,start+1200);
  assert.ok(chunk.indexOf("'morphorum:models-updated', onAnimationModelsUpdated")>
    chunk.indexOf('    bind();'));
  assert.ok(chunk.indexOf("'morphorum:models-updated', onAnimationModelsUpdated")<
    chunk.indexOf('await Promise.all('));
  const loader=extract('  async function loadModels() {','  function deforumCheckpointModels()');
  assert.match(loader,/revision !== state.modelIndexRevision/);
  assert.match(html,/id="animation-model-index-status"[^>]*aria-live="polite"/);
  assert.match(loader,/state.modelIndexStale = true/);
});
