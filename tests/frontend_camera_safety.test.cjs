'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const root=path.join(__dirname,'..','frontend','dist');
const html=fs.readFileSync(path.join(root,'index.html'),'utf8');
const js=fs.readFileSync(path.join(root,'assets','animation.js'),'utf8');
test('3D Camera Schedules explain cumulative motion and include safety shortcut',()=>{
  assert.match(html,/3D motion safety/);
  assert.match(html,/translation and rotation are applied again at each frame/);
  assert.equal((html.match(/id="animation-camera-safety-check"/g)||[]).length,1);
});
test('Safety shortcut reuses existing non-destructive render preflight',()=>{
  const pos=js.indexOf("qs('#animation-camera-safety-check')?.addEventListener");
  assert.ok(pos>0);
  const snippet=js.slice(pos,pos+220);
  assert.match(snippet,/showAnimationTab\('monitor'\)/);
  assert.match(snippet,/checkRenderPreflight\(\)/);
  assert.doesNotMatch(snippet,/saveProject\(|startAnimationRender\(/);
});
