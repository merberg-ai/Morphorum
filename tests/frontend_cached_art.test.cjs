'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const root=path.join(__dirname,'..','frontend','dist');
const html=fs.readFileSync(path.join(root,'index.html'),'utf8');
const css=fs.readFileSync(path.join(root,'assets','models.css'),'utf8');
const models=fs.readFileSync(path.join(root,'assets','models.js'),'utf8');
const loras=fs.readFileSync(path.join(root,'assets','loras.js'),'utf8');
const shared=fs.readFileSync(path.join(root,'assets','library-thumbnails.js'),'utf8');

test('cached art is shared and opt-in remote downloads stay distinct',()=>{
  assert.match(html,/library-thumbnails\.js/);
  assert.ok(html.indexOf('library-thumbnails.js') < html.indexOf('models.js'));
  assert.match(shared,/api\/civitai\/library-catalog/);
  assert.match(shared,/120/);
  assert.doesNotMatch(shared,/https:\/\//);
  assert.match(shared,/if \(response\.status === 403\)/);
  assert.match(shared,/img\.loading = 'lazy'/);
  assert.match(shared,/img\.addEventListener\('error'/);
});

test('overlapping catalog refreshes for the same models share one request',async()=>{
  const vm=require('node:vm');
  const sent=[];
  const pending=[];
  const window={};
  const fetch=(url,options)=>new Promise(resolve=>{
    sent.push(JSON.parse(options.body).model_ids);
    pending.push(()=>resolve({ok:true,status:200,json:async()=>({entries:{a:{synced:true,name:'A'}}})}));
  });
  vm.runInNewContext(shared,{window,fetch,document:{}});
  const thumbs=window.MorphorumThumbnails;
  // Models and LoRA managers ask for the same library while the page loads.
  const first=thumbs.refresh(['a','b']);
  const second=thumbs.refresh(['b','a','a']);
  const other=thumbs.refresh(['c']);
  assert.equal(first,second);
  assert.notEqual(first,other);
  assert.equal(sent.length,2);
  pending.splice(0).forEach(done=>done());
  await Promise.all([first,other]);
  assert.equal(thumbs.get('a').name,'A');
  assert.equal(thumbs.get('b'),null);
  // Once it has finished, a later refresh fetches fresh data again.
  const later=thumbs.refresh(['a','b']);
  assert.notEqual(later,first);
  assert.equal(sent.length,3);
  pending.splice(0).forEach(done=>done());
  await later;
});

test('models manager uses cards with prominent thumbnails and bulk sync',()=>{
  assert.match(html,/id="model-bulk-sync"/);
  assert.match(models,/window\.MorphorumThumbnails\?\.refresh\(ids\)/);
  assert.match(models,/window\.MorphorumThumbnails\?\.create\(model\.id/);
  assert.match(models,/window\.MorphorumThumbnails\?\.set\(model\.id, data\)/);
  assert.match(models,/model-entry-summary/);
  assert.match(models,/model-entry-actions/);
  assert.match(models,/bulkCheck\('sync'\)/);
  assert.match(css,/#view-models \.model-list \{ display:grid/);
  assert.match(css,/#view-models \.model-row/);
});

test('LoRA library and selected information both display cached thumbnails',()=>{
  assert.match(html,/id="lora-manager-preview"/);
  assert.match(loras,/lora-library-art/);
  assert.match(loras,/lora-detail-art/);
  assert.match(loras,/window\.MorphorumThumbnails\?\.refresh\(state\.records/);
  assert.match(loras,/window\.MorphorumThumbnails\?\.set\(selected\.id, result\)/);
  assert.match(css,/#view-loras \.lora-manager-preview/);
  assert.match(css,/@media\(max-width:640px\)/);
});

test('legacy core controls and model selection remain available',()=>{
  for(const id of ['scan-models','model-search','model-kind-filter',
                   'model-family-filter','model-select-visible','model-clear-selected',
                   'lora-manager-insert','lora-manager-copy','lora-sync-selected']) {
    assert.ok(html.includes('id="'+id+'"'),id);
  }
  assert.match(models,/useModel\(model\.id\)/);
  assert.match(loras,/insertIntoImage/);
});

test('thumbnail sync distinguishes metadata-only success from image success',()=>{
  assert.match(shared,/PREVIEWS OFF/);
  assert.match(shared,/PREVIEW HIDDEN/);
  assert.match(shared,/CACHE MISSING/);
  assert.match(shared,/IMAGE LOAD FAILED/);
  assert.match(models,/Civitai info saved, no thumbnail/);
  assert.match(models,/data\.preview_warning/);
  assert.match(models,/thumbnails downloaded/);
  assert.match(loras,/Metadata saved without artwork/);
  assert.match(loras,/withPreview/);
  assert.match(loras,/result\.preview_warning/);
});
