'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const root=path.join(__dirname,'..','frontend','dist');
const css=fs.readFileSync(path.join(root,'assets','animation.css'),'utf8');
const html=fs.readFileSync(path.join(root,'index.html'),'utf8');
test('All render actions remain distinct and P3.1 limits width at zoom',()=>{
  for(const id of ['animation-preflight-check','animation-resume-render',
                   'animation-cancel-render','animation-start-render']) {
    assert.equal((html.match(new RegExp('id="'+id+'"','g'))||[]).length,1,id);
  }
  assert.match(css,/\/\* P3\.1: keep new render\/check actions/);
  assert.match(css,/\.animation-render-actions > button[\s\S]*?white-space:normal/);
  assert.match(css,/min-height:42px/);
});
test('Tablet and phone breakpoints keep Check/Render primary actions on full rows',()=>{
  const start=css.indexOf('/* P3.1:');
  const responsive=css.slice(start);
  assert.match(responsive,/@media\(max-width:720px\)/);
  assert.match(responsive,/grid-template-columns:repeat\(2,minmax\(0,1fr\)\)/);
  assert.match(responsive,/#animation-preflight-check,[\s\S]*?#animation-start-render[\s\S]*?grid-column:1\/-1/);
  assert.match(responsive,/@media\(max-width:390px\)/);
  assert.match(responsive,/grid-template-columns:minmax\(0,1fr\)/);
  assert.match(responsive,/\.animation-camera-safety-note button \{width:100%;\}/);
});
