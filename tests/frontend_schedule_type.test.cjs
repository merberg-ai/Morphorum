'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.join(__dirname, '..', 'frontend', 'dist');
const src = fs.readFileSync(path.join(root, 'assets/animation.js'), 'utf8');
const html = fs.readFileSync(path.join(root, 'index.html'), 'utf8');
const start = src.indexOf('  function populateAnimationScheduleTypes(');
const end = src.indexOf('  function repairConstantGuidanceForSelectedModel(', start);
assert.ok(start >= 0 && end > start);

function render(family, indexed = true, sampler = 'euler') {
  const nodes = {
    '#animation-model': {value:'saved-model'},
    '#animation-sampler': {value:sampler},
    '#animation-schedule-type-field': {hidden:true},
    '#animation-schedule-type': {
      options:[], disabled:true, value:'',
      replaceChildren(){this.options=[];this.value='';},
      add(option){this.options.push(option);if(this.options.length===1)this.value=option.value;},
    },
  };
  const state={
    project:{model:{model_id:'saved-model',family},generation:{schedule_type:'karras'}},
    capabilities:{sdxl:{schedule_types:{default:'normal',options:[
      {id:'normal',label:'Normal'},{id:'karras',label:'Karras'}]}}},
  };
  const ctx={state,qs:key=>nodes[key],
    modelById:()=>indexed?{family}:null,
    effectiveCapability:()=>state.capabilities.sdxl,
    Option:class {constructor(text,value){this.text=text;this.value=value;}}
  };
  vm.runInNewContext(src.slice(start,end)+'\nthis.populate=populateAnimationScheduleTypes;',ctx);
  ctx.populate('karras');
  return nodes;
}

test('project editor exposes schedule dropdown for indexed SDXL checkpoint',()=>{
  const n=render('sdxl');
  assert.equal(n['#animation-schedule-type-field'].hidden,false);
  assert.equal(n['#animation-schedule-type'].value,'karras');
});
test('saved SDXL project retains control before model index refresh',()=>{
  const n=render('sdxl',false);
  assert.equal(n['#animation-schedule-type-field'].hidden,false);
  assert.equal(n['#animation-schedule-type'].value,'karras');
});
test('non-SDXL projects hide schedule type even for an indexed model',()=>{
  const n=render('flux');
  assert.equal(n['#animation-schedule-type-field'].hidden,true);
});
test('DDIM prevents Karras option from being offered',()=>{
  const n=render('sdxl',true,'ddim');
  assert.equal(n['#animation-schedule-type'].options.some(x=>x.value==='karras'),false);
});
test('schedule control exists in project editor markup',()=>{
  assert.match(html,/id="animation-schedule-type-field"/);
  assert.match(html,/id="animation-schedule-type"/);
});
