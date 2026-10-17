'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const root=path.join(__dirname,'..','frontend','dist');
const html=fs.readFileSync(path.join(root,'index.html'),'utf8');
const app=fs.readFileSync(path.join(root,'assets','app.js'),'utf8');
const animation=fs.readFileSync(path.join(root,'assets','animation.js'),'utf8');

test('UX2.4 project destinations are in main navigation and absent from Motion Lab sidebar',()=>{
  const nav=html.match(/<nav class="main-nav glass"[\s\S]*?<\/nav>/)?.[0]||'';
  assert.ok(nav);
  for(const key of ['projects','wizard','editor']){
    assert.match(nav,new RegExp('data-project-nav="'+key+'"'));
    assert.doesNotMatch(nav,new RegExp('data-motion-nav="'+key+'"'));
    assert.match(animation,new RegExp("'"+key+"'"));
  }
});

test('UX2.4 primary nav reuses project panels and existing workspace navigation',()=>{
  assert.match(app,/\.main-nav \[data-project-nav\]/);
  assert.match(app,/switchView\('animation'\)/);
  assert.match(app,/button\.dataset\.projectNav/);
  assert.match(animation,/qs\('#animation-tab-' \+ name\)/);
  assert.match(animation,/panels\.editor\.appendChild\(layout\)/);
  assert.match(animation,/if \(!\['wizard','projects','editor'\]\.includes\(name\)\) nav\.appendChild\(button\)/);
  assert.match(animation,/if \(name === 'wizard'\) void projectWizard\?\.open\(\)/);
});

test('UX2.4 Motion Lab entry opens overview and project links preserve selection',()=>{
  assert.match(app,/button\.dataset\.view === 'animation'/);
  assert.match(app,/qs\('#animation-tab-motion'\)\?\.click\(\)/);
  assert.match(animation,/button\.dataset\.projectNav === name/);
});
