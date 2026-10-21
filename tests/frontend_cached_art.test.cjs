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
