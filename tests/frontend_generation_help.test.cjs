'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const root=path.join(__dirname,'..','frontend','dist');
const html=fs.readFileSync(path.join(root,'index.html'),'utf8');
const service=fs.readFileSync(path.join(root,'assets','ui-services.js'),'utf8');
const css=fs.readFileSync(path.join(root,'assets','app.css'),'utf8');
test('P2.4 annotates generation and camera fields with existing help topics',()=>{
  const ids=["image-model-select","image-resolution-preset","image-width","image-height","image-steps","image-sampler","image-guidance","image-seed","image-seed-mode","image-seed-increment","image-count","animation-max-frames","animation-width","animation-height","animation-prompt-transition","animation-cadence-preset","animation-temporal-mode","animation-temporal-mix","animation-temporal-contrast","animation-start-mode","animation-source-file","animation-border-mode","animation-angle","animation-zoom","animation-translation-x","animation-translation-y","animation-noise","animation-seed-increment","animation-3d-preset","animation-3d-translation-x","animation-3d-translation-y","animation-3d-rotation-x","animation-3d-rotation-z","animation-3d-hole-fill","animation-motion-lab-preset","animation-motion-lab-fade","animation-motion-lab-start","animation-motion-lab-end"];
  for (const id of ids) {
    assert.equal((html.match(new RegExp('data-help-topic="'+id+'"','g'))||[]).length,1,id);
    assert.match(service,new RegExp('"'+id+'":\\s*\\{title:'),'Missing catalog entry '+id);
  }
});
test('Help annotations are unique and every topic has a trusted static definition',()=>{
  const tags=[...html.matchAll(/data-help-topic="([^"]+)"/g)].map(x=>x[1]);
  const defined=[...service.matchAll(/^\s+"([^"]+)": \{title:/gm)].map(x=>x[1]);
  assert.equal(tags.length,new Set(tags).size);
  for(const tag of tags) assert.ok(defined.includes(tag),'Missing help definition '+tag);
  assert.match(service,/wrapper\.append\(label, button\)/);
  assert.match(service,/for \(const layoutClass of \['animation-span-2', 'image-resolution-preset-field'\]\)/);
  assert.match(css,/\.morphorum-help-field\.image-resolution-preset-field\s*\{grid-column:1\/-1;/);
});
test('P2.4 units and schedule syntax are visible without editing project logic',()=>{
  for(const unit of ['(px)','(per image)','(per batch)','(° / frame)',
    '(scene units / frame)','(per frame)','Schedule example: <code>0:(0.65), 48:(0.5)</code>'])
    assert.ok(html.includes(unit),'Missing inline units '+unit);
  assert.equal((html.match(/class="field-help animation-schedule-syntax-help"/g)||[]).length,1);
});
