'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const base=path.join(__dirname,'..','frontend','dist');
const read=(p)=>fs.readFileSync(path.join(base,p),'utf8');
const services=read('assets/ui-services.js');
const app=read('assets/app.js');
const models=read('assets/models.js');
const html=read('index.html');
const css=read('assets/app.css');
function tracker() {
  const start=services.indexOf('  function createOperationTracker(publish) {');
  const end=services.indexOf('  function renderOperationFeedback(entry) {',start);
  assert.ok(start>=0&&end>start);
  const ctx={Map};
  vm.runInNewContext(services.slice(start,end)+
    '\nthis.make=createOperationTracker;',ctx);
  const published=[];
  return {ops:ctx.make(value=>published.push(value)),published};
}

test('Operation tracker supports concurrent work, stale-response guard and persistent terminal state',()=>{
  const {ops,published}=tracker();
  const saved=ops.begin('settings','Saving','Waiting','settings');
  const scanned=ops.begin('scan','Scanning','Waiting','models');
  assert.equal(ops.snapshot().active.length,2);
  assert.equal(published.at(-1).title,'Scanning');
  assert.equal(ops.update('settings',saved,{message:'Server received save'}),true);
  assert.equal(ops.finish('settings',saved,{title:'Saved'}),true);
  assert.equal(published.at(-1).title,'Scanning');
  assert.equal(ops.finish('scan',scanned,{tone:'error',title:'Scan failed'}),true);
  assert.equal(published.at(-1).tone,'error');
  const newer=ops.begin('scan','Scanning again');
  assert.equal(ops.finish('scan',scanned,{title:'Stale success'}),false);
  assert.equal(ops.update('scan',scanned,{message:'Stale progress'}),false);
  assert.equal(published.at(-1).title,'Scanning again');
  ops.dismiss();
  assert.equal(published.at(-1),null);
  assert.equal(ops.snapshot().active.length,1);
  ops.finish('scan',newer,{title:'Scan succeeded'});
  assert.equal(published.at(-1).title,'Scan succeeded');
  ops.dismiss();
  assert.equal(published.at(-1),null);
});

test('Top-level ribbon has accessible progress and non-cancelling dismiss action',()=>{
  for(const id of ['operation-feedback','operation-feedback-title','operation-feedback-message',
    'operation-feedback-progress','operation-feedback-fill','operation-feedback-open',
    'operation-feedback-dismiss']) {
    assert.equal((html.match(new RegExp('id="'+id+'"','g'))||[]).length,1,id);
  }
  assert.match(html,/aria-label="Recent operation" aria-live="polite"/);
  assert.match(html,/Dismiss operation notice; does not cancel the task/);
  assert.match(services,/document\.querySelector\('\.nav-button\[data-view=/);
  assert.match(services,/panel\.setAttribute\('aria-busy'/);
  assert.match(css,/\.operation-feedback-progress\.indeterminate/);
  assert.match(css,/@media\(prefers-reduced-motion:reduce\)/);
});

test('Settings and Models use shared lifecycles and check index refresh before success',()=>{
  assert.match(app,/state\.settingsRequestBusy = true/);
  assert.match(app,/MorphorumOperations\?\.begin\('settings'/);
  assert.match(app,/MorphorumOperations\?\.finish\('settings'/);
  assert.match(models,/MorphorumOperations\?\.begin\('model-scan'/);
  assert.match(models,/await loadModels\(\{ propagate: true \}\)/);
  assert.match(models,/if \(propagate\) throw error/);
  assert.match(models,/state\.scanning = false/);
  assert.match(models,/reportManagedDownloads\(\)/);
  assert.match(models,/state\.downloadOperations\.delete\(model\.id\)/);
  assert.match(models,/progress: model\.status === 'downloading' \? percent : null/);
});
