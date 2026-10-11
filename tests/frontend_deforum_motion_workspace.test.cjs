'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const root=path.join(__dirname,'..','frontend/dist');
const js=fs.readFileSync(path.join(root,'assets/animation.js'),'utf8');
const css=fs.readFileSync(path.join(root,'assets/animation.css'),'utf8');
const html=fs.readFileSync(path.join(root,'index.html'),'utf8');

test('DMI2 replaces Audio Motion navigation while retaining its hidden controls',()=>{
  assert.match(html,/data-motion-nav="motion-import"/);
  assert.doesNotMatch(html,/data-motion-nav="audio"/);
  assert.match(js,/panels\.audio = hiddenAudioPanel/);
  assert.match(js,/setupDeforumMotionImport\(panels\['motion-import'\]\)/);
  assert.match(js,/if \(name === 'audio'\) continue/);
});
test('DMI2 preview uses read-only project-scoped endpoint',()=>{
  assert.match(js,/\/motion-import\/preview/);
  assert.match(js,/data-dmi-file/);
  assert.match(js,/data-dmi-summary/);
  assert.match(js,/data-dmi-chart/);
  assert.match(js,/source\.cadence/);
});
test('DMI2 WAV locally previews offset without invoking project mutation',()=>{
  assert.match(js,/data-dmi-wav/);
  assert.match(js,/decodeAudioData/);
  assert.match(js,/data-dmi-offset/);
  assert.match(js,/data-dmi-seek/);
  assert.match(js,/URL\.createObjectURL/);
  assert.match(js,/DMI2 is preview-only/);
  assert.match(css,/\.dmi-align/);
});
