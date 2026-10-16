'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.join(__dirname, '..', 'frontend', 'dist');
const read = f => fs.readFileSync(path.join(root,f),'utf8');
const src = read('assets/animation.js');
const html = read('index.html');
const css = read('assets/animation.css');

const start = src.indexOf('  function describeAnimationModelCompatibility(');
const end = src.indexOf('  function renderAnimationModelCompatibility()',start);
assert.ok(start>=0 && end>start);
const context={};
vm.runInNewContext(src.slice(start,end)+'\nthis.describe=describeAnimationModelCompatibility;',context);
const describe = input=>context.describe(input);
const base={hasProject:true,modelId:'checkpoint-1',model:{id:'checkpoint-1',kind:'checkpoints',name:'Test model',family:'sdxl',variant:'standard'},
  capability:{supported:true,label:'SDXL',samplers:{default:'euler',options:[{id:'euler',label:'Euler'},{id:'ddim',label:'DDIM'}]}},
  sampler:'euler',width:'1024',height:'1024'};

test('compatible SDXL shows known family, variant, selected sampler and noncommittal index readiness',()=>{
  const result=describe({...base});
  assert.equal(result.tone,'ok');
  assert.equal(result.issues.length,0);
  assert.deepEqual(Array.from(result.facts, v=>Array.from(v)),[
    ['Family','SDXL'],['Variant','standard'],['Sampler','Euler'],['Resolution','1024 × 1024']
  ]);
  assert.match(result.note,/File integrity and GPU readiness/);
});

test('missing or absent model keeps project untouched and suggests Models',()=>{
  const missing=describe({...base,model:null});
  assert.equal(missing.action,'models');
  assert.match(missing.status,/unavailable/);
  assert.match(missing.issues[0],/saved checkpoint/);
  const none=describe({...base,modelId:'',model:null});
  assert.equal(none.action,'models');
  assert.equal(none.tone,'attention');
  assert.equal(describe({...base,hasProject:false}).status,'No project');
});

test('unsupported and unknown capabilities are warnings instead of invented support',()=>{
  assert.equal(describe({...base,capability:{supported:false,reason:'Unsupported family'}}).status,'Unsupported model family');
  assert.equal(describe({...base,capability:{}}).status,'Compatibility unknown');
});

test('sampler and aligned dimensions are checked using actual model rules',()=>{
  const badSampler=describe({...base,sampler:'flowmatch_euler'});
  assert.equal(badSampler.action,'sampler');
  assert.match(badSampler.issues[0],/not supported/);
  const badSdxl=describe({...base,width:'1025'});
  assert.equal(badSdxl.action,'resolution');
  assert.match(badSdxl.issues[0],/divisible by 8/);
  const flux={...base,model:{...base.model,family:'flux',variant:'schnell'},
    capability:{supported:true,label:'Flux Schnell',samplers:{options:[{id:'flowmatch_euler',label:'FlowMatch Euler'}]}},
    sampler:'flowmatch_euler',width:'1032',height:'1024'};
  assert.match(describe(flux).issues[0],/divisible by 16/);
  assert.equal(describe({...flux,width:'1024'}).issues.length,0);
  assert.match(describe({...base,width:'4097'}).issues[0],/between 64 and 4096/);
  assert.match(describe({...base,width:'1920',height:'1080'}).note,/substantial VRAM/);
});

test('model compatibility UI is scoped to project editor and never mutates settings',()=>{
  for(const id of ['animation-model-compatibility','animation-compatibility-status',
    'animation-compatibility-facts','animation-compatibility-issues',
    'animation-compatibility-note','animation-compatibility-action']) {
    assert.equal((html.match(new RegExp('id="'+id+'"','g'))||[]).length,1);
  }
  assert.match(src,/function renderAnimationModelCompatibility\(\)/);
  assert.match(src,/renderAnimationModelCompatibility\(\);\s*\}\s*function setEditorEnabled/);
  assert.match(src,/renderAnimationModelCompatibility\(\);\s*\}\s*function syncAnimationResolutionPreset/);
  assert.match(src,/action === 'models'/);
  assert.match(src,/action === 'sampler'/);
  assert.match(src,/action === 'resolution'/);
  assert.match(css,/\.animation-compatibility-facts/);
  assert.match(css,/@media\(max-width:480px\)/);
});

test('older saved unsupported sampler remains in the dropdown until explicitly repaired',()=>{
  assert.match(src,/preserveUnsupported && preferredSampler && !valid\.has\(preferredSampler\)/);
  assert.match(src,/missing\.textContent = 'Unsupported sampler · '/);
  assert.match(src,/populateSamplerSelect\(project\.generation\?\.sampler \|\| '', \{ preserveUnsupported: true \}\)/);
  assert.match(src,/populateSamplerSelect\(''\)/);
});
