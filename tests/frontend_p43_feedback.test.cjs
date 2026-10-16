'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const frontend = path.join(__dirname, '..', 'frontend', 'dist');
const file = name => fs.readFileSync(path.join(frontend, name), 'utf8');
const services = file('assets/ui-services.js');
const app = file('assets/app.js');
const models = file('assets/models.js');
const image = file('assets/image.js');
const animation = file('assets/animation.js');
const html = file('index.html');
function servicesUnderTest() {
  const start = services.indexOf('  function createOperationTracker(publish) {');
  const end = services.indexOf('  function renderOperationFeedback(entry) {', start);
  assert.ok(start >= 0 && end > start);
  const ctx = {Map, Set, console: {warn(){}},
    window: {MorphorumClientDiagnostics: {record(){}}}};
  vm.runInNewContext(services.slice(start, end) +
    '\nthis.createTracker=createOperationTracker;this.createHealth=createPollHealth;', ctx);
  const published = [];
  const operations = ctx.createTracker(value => published.push(value));
  return {operations, health:ctx.createHealth(operations),published};
}

test('P4.3 prioritizes terminal errors over progress and success, while retries and dismiss work',()=>{
  const {operations:ops, published} = servicesUnderTest();
  const render = ops.begin('render','Rendering','Working', 'animation');
  const model = ops.begin('model','Scanning','Working','models');
  const error = ops.begin('settings','Saving','Waiting','settings');
  ops.finish('settings',error,{tone:'error',title:'Settings save failed'});
  assert.equal(published.at(-1).tone,'error');
  ops.update('render',render,{progress:33,message:'Frame 2'});
  ops.finish('model',model,{title:'Scan complete'});
  assert.equal(published.at(-1).title,'Settings save failed');
  const retry = ops.begin('settings','Retrying settings');
  assert.equal(published.at(-1).title,'Retrying settings');
  ops.dismiss();
  assert.equal(published.at(-1).title,'Rendering');
  assert.equal(ops.snapshot().active.length,2);
  assert.equal(ops.finish('settings',error,{title:'Stale success'}),false);
  ops.finish('settings',retry,{title:'Settings saved'});
  assert.equal(published.at(-1).tone,'busy');
  ops.finish('render',render,{title:'Render complete'});
  assert.equal(published.at(-1).title,'Render complete');
  assert.equal(ops.snapshot().results.length,3);
});

test('P4.3 keeps simultaneous errors independently dismissible, capped and ordered',()=>{
  const {operations:ops,published} = servicesUnderTest();
  const first = ops.begin('first','First request');
  ops.finish('first',first,{tone:'warning',title:'First warning'});
  const second = ops.begin('second','Second request');
  ops.finish('second',second,{tone:'error',title:'Second error'});
  assert.equal(published.at(-1).title,'Second error');
  ops.dismiss();
  assert.equal(published.at(-1).title,'First warning');
  ops.dismiss();
  assert.equal(published.at(-1),null);
  for(let i=0;i<16;i++){
    const token = ops.begin('op-'+i,'Request');
    ops.finish('op-'+i,token,{title:'Finished'});
  }
  assert.ok(ops.snapshot().results.length <= 12);
  ops.retire('op-15');
  assert.notEqual(ops.snapshot().settled?.key,'op-15');
});

test('P4.3 polling health warns once after repeated misses and distinguishes recovery from job success',()=>{
  const {health,operations:ops,published} = servicesUnderTest();
  health.failed('render:a','Animation render','animation');
  health.failed('render:a','Animation render','animation');
  assert.equal(published.length,0);
  for(let i=0;i<8;i++)health.failed('render:a','Animation render','animation');
  const warnings=published.filter(x=>x?.tone==='warning');
  assert.equal(warnings.length,1);
  assert.match(warnings[0].message,/may still be running/);
  assert.equal(health.snapshot('render:a').count,10);
  assert.equal(ops.snapshot().active.length,0);
  health.recovered('render:a');
  assert.equal(health.snapshot('render:a'),null);
  assert.equal(published.at(-1).title,'Live status restored');
  health.failed('render:a','Animation render','animation');
  health.reset('render:a');
  assert.equal(health.snapshot('render:a'),null);
  assert.equal(ops.snapshot().results.some(x=>x.key==='poll:render:a'),false);
});

test('P4.3 accessibility announces transitions, not rapidly changing percentages',()=>{
  const start = services.indexOf('  function renderOperationFeedback(entry) {');
  const end = services.indexOf('  const operations = createOperationTracker(',start);
  assert.ok(start >= 0 && end > start);
  const elements=new Map();
  for(const id of [
    'operation-feedback','operation-feedback-announcement',
    'operation-feedback-title','operation-feedback-message',
    'operation-feedback-progress','operation-feedback-fill',
    'operation-feedback-open'
  ])elements.set(id,{
    id,dataset:{},hidden:false,style:{},
    textContent:'',attributes:{},classList:{toggle(){}},
    setAttribute(k,v){this.attributes[k]=v;},
    removeAttribute(k){delete this.attributes[k];}
  });
  const ctx={document:{getElementById:id=>elements.get(id)},Number,String,Math};
  vm.runInNewContext(services.slice(start,end)+
    '\nthis.render=renderOperationFeedback;',ctx);
  ctx.render({key:'render',token:123,tone:'busy',title:'Rendering',
    message:'Frame 1',progress:5,view:'animation'});
  const announcement=elements.get('operation-feedback-announcement');
  assert.match(announcement.textContent,/Frame 1/);
  ctx.render({key:'render',token:123,tone:'busy',title:'Rendering',
    message:'Frame 100',progress:60,view:'animation'});
  assert.match(announcement.textContent,/Frame 1/);
  assert.equal(elements.get('operation-feedback-fill').style.width,'60%');
  ctx.render({key:'render',token:123,tone:'error',title:'Render failed',
    message:'Check the Console',view:'animation'});
  assert.match(announcement.textContent,/Check the Console/);
  assert.equal(announcement.attributes.role,'alert');
  assert.equal(announcement.attributes['aria-live'],'assertive');
  assert.equal(elements.get('operation-feedback').attributes['aria-busy'],'false');
});

test('P4.3 preserves queued jobs during lost polls, manages recovered status and UI retries',()=>{
  assert.match(image,/MorphorumPollHealth\?\.failed\(healthKey, 'Image generation'/);
  assert.match(image,/MorphorumPollHealth\?\.recovered\(healthKey\)/);
  assert.doesNotMatch(image,/toast\('Could not read generation progress'/);
  for(const name of ['motion:','video:','render:']){
    assert.ok(animation.includes('MorphorumPollHealth?.failed(\''+name));
    assert.ok(animation.includes('MorphorumPollHealth?.recovered(\''+name));
  }
  assert.match(models,/Preserve accepted download IDs/);
  assert.match(models,/MorphorumPollHealth\?\.recovered\('managed-models'\)/);
  assert.match(app,/MorphorumClientDiagnostics =/);
  assert.match(app,/const browserEvents = state\.events\.filter/);
});

test('P4.3 gives toasts bounded space, warning priority, and accessible error roles',()=>{
  assert.match(app,/if \(displayed\.length >= 4\)/);
  assert.match(app,/recentToasts\.set\(signature, now\)/);
  assert.match(app,/type === 'error' \? 'alert' : 'status'/);
  assert.match(html,/id="operation-feedback-announcement"/);
});
