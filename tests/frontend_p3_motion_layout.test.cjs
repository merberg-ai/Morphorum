'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const root=path.join(__dirname,'..','frontend','dist');
const html=fs.readFileSync(path.join(root,'index.html'),'utf8');
const css=fs.readFileSync(path.join(root,'assets','animation.css'),'utf8');
const js=fs.readFileSync(path.join(root,'assets','animation.js'),'utf8');
const own = css.slice(css.indexOf('/* P3.3:'));
test('Timeline width uses measured card width on narrow phone and preserves desktop scaling',()=>{
  assert.match(js,/const availableWidth = Math\.max\(160, Math\.floor\(measuredWidth - 4\)\)/);
  assert.match(js,/const contentWidth = mobile\s*\?\s*availableWidth\s*:\s*Math\.max\(640, Math\.round\(maxFrames \* state\.timelineScale\)\)/);
  assert.doesNotMatch(js,/Math\.max\(300, Number\(scroll\?\.clientWidth/);
  assert.match(html,/id="animation-timeline-scroll" role="region" tabindex="0" aria-label="/);
  assert.match(own,/\.animation-timeline-scroll:focus-visible/);
  assert.match(own,/\.animation-timeline-keyframe-chip,/);
});
test('Motion curve/inspector/camera controls and dialog remain shrinkable',()=>{
  assert.ok(own.startsWith('/* P3.3:'), 'P3.3 styles missing');
  for(const item of ['.animation-motion-lab-visual-grid','.animation-motion-lab-curve-fields',
    '.animation-inspector-controls','.animation-camera-preset-bar',
    '.animation-motion-lab-svg-wrap','.animation-timeline-editor']) {
    assert.ok(own.includes(item),'Missing responsive control: '+item);
  }
  assert.match(own,/dialog#animation-deforum-dialog\s*\{[\s\S]*?max-height:calc\(100dvh - 16px\)/);
  assert.match(own,/#animation-deforum-dialog \.animation-import-actions button\s*\{[\s\S]*?min-height:44px/);
  assert.match(own,/@media\(max-width:720px\)/);
  assert.match(own,/@media\(max-width:420px\)/);
  assert.match(own,/\.animation-timeline-editor-actions\s*\{[\s\S]*?grid-template-columns:minmax\(0,1fr\)/);
});
test('Responsive styles do not add project-mutating JavaScript actions',()=>{
  const buttonIds=['animation-timeline-apply','animation-timeline-delete',
    'animation-motion-lab-key-save','animation-motion-lab-key-delete',
    'animation-deforum-close','animation-deforum-create','animation-3d-apply-preset'];
  for(const id of buttonIds)assert.equal((html.match(new RegExp('id="'+id+'"','g'))||[]).length,1,id);
  assert.match(html,/id="animation-motion-lab-curves"[^>]*role="img"/);
  assert.match(html,/id="animation-motion-lab-key-axis"/);
  assert.match(own,/@media\(prefers-reduced-motion:reduce\)/);
});
