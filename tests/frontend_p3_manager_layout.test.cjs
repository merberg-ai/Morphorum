'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const root=path.join(__dirname,'..','frontend','dist','assets');
const read=f=>fs.readFileSync(path.join(root,f),'utf8');
const models=read('models.css');
const image=read('image.css');
const app=read('app.css');
const phone=read('mobile.css');
const modelJS=read('models.js');
const imageJS=read('image.js');
const settingsJS=read('app.js');

test('Model Manager keeps inventory paths readable and focusable without fixed phone columns',()=>{
  const p=models.slice(models.indexOf('/* P3.2:'));
  assert.ok(p.startsWith('/* P3.2:'), 'P3.2 model layout missing');
  assert.match(p,/\.model-toolbar > input,[\s\S]*?min-width:0/);
  assert.match(p,/\.managed-model-path\s*\{[\s\S]*?overflow-wrap:anywhere/);
  assert.match(p,/\.model-path-details summary:focus-visible\s*\{/);
  assert.match(p,/@media\(max-width:520px\)[\s\S]*?\.model-toolbar\s*\{grid-template-columns:minmax\(0,1fr\)/);
  assert.match(p,/@media\(max-width:380px\)[\s\S]*?\.model-row\s*\{grid-template-columns:minmax\(0,1fr\)/);
  assert.match(modelJS,/pathDetails\.className = 'model-path-details'/);
  assert.match(modelJS,/pathSummary\.textContent = 'Show full file path'/);
});

test('Phone Settings preserves all four groups and exposes path actions at zoom',()=>{
  const p=phone.slice(phone.indexOf('/* P3.2:'));
  assert.match(p,/\.settings-internal-tabs\s*\{[\s\S]*?grid-template-columns:repeat\(2,minmax\(0,1fr\)\)/);
  assert.match(p,/\.settings-internal-tabs button\s*\{[\s\S]*?min-height:44px/);
  assert.match(p,/\.path-row \.validate-path\s*\{[\s\S]*?grid-row:2/);
  assert.match(p,/\.path-row \.icon-button\s*\{[\s\S]*?grid-row:2/);
  for(const name of ['appearance','generation','paths','storage']){
    assert.match(settingsJS,new RegExp("'"+name+"'"));
  }
  assert.match(app,/\/\* P3\.2: shared LoRA details/);
});

test('LoRA metadata and image result actions wrap and expose focus states',()=>{
  const m=app.slice(app.indexOf('/* P3.2:'));
  assert.match(m,/\.lora-manager-item:focus-visible small/);
  assert.match(m,/\.lora-manager-item\.selected small/);
  assert.match(m,/\.lora-manager-quick-actions button\s*\{[\s\S]*?min-height:42px/);
  const i=image.slice(image.indexOf('/* P3.2:'));
  assert.match(i,/\.result-seed span\s*\{white-space:normal;overflow-wrap:anywhere/);
  assert.match(i,/\.result-actions\s*\{[\s\S]*?flex-wrap:wrap/);
  assert.match(i,/@media\(max-width:640px\)[\s\S]*?\.result-actions\s*\{display:grid/);
  assert.match(i,/@media\(max-width:380px\)[\s\S]*?\.result-actions\s*\{grid-template-columns:minmax\(0,1fr\)/);
  assert.match(i,/\.image-result-lightbox-toolbar\s*\{flex-wrap:wrap/);
  assert.match(imageJS,/reuse\.textContent = 'Reuse seed'/);
  assert.match(imageJS,/save\.textContent = 'Save'/);
});
