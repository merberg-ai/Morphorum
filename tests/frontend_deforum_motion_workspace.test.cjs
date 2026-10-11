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

test('DMI2 exposes source soundtrack path with copy controls and browser picker limits',()=>{
  assert.match(js,/data-dmi-source-path/);
  assert.match(js,/data-dmi-copy-path/);
  assert.match(js,/data-dmi-copy-folder/);
  assert.match(js,/source\.soundtrack_path/);
  assert.match(js,/navigator\.clipboard\?\.writeText/);
  assert.match(js,/cannot set this folder as the default browse location/);
  assert.match(js,/\.mp3,\.ogg,\.flac,audio\/\*/);
  assert.match(css,/\.dmi-soundtrack-ref/);
});

test('DMI3 requires safe review before explicit import and respects project edits',()=>{
  assert.match(js,/data-dmi-prepare/);
  assert.match(js,/data-dmi-apply disabled/);
  assert.match(js,/\/motion-import\/prepare/);
  assert.match(js,/\/motion-import\/apply/);
  assert.match(js,/project_sha256:ready\.project_sha256/);
  assert.match(js,/source_sha256:ready\.source_sha256/);
  assert.match(js,/if \(state\.dirty\)/);
  assert.match(js,/Replace six camera schedules\?/);
  assert.match(js,/window\.MorphorumDialog\.confirm/);
});

test('DMI3 importer buttons use theme styles and progress through shared toast system',()=>{
  assert.match(js,/class="secondary-button compact" data-dmi-prepare/);
  assert.match(js,/class="primary-button compact" data-dmi-apply disabled/);
  assert.match(js,/progress\('Loading Deforum settings'/);
  assert.match(js,/progress\('Reviewing motion import'/);
  assert.match(js,/progress\('Applying motion'/);
  assert.match(js,/progress\('Motion import blocked'/);
});
test('DMI3 soundtrack attachment is explicit and separate from camera import',()=>{
  assert.match(js,/data-dmi-attach/);
  assert.match(js,/data-dmi-save-offset/);
  assert.match(js,/\/motion-import\/soundtrack/);
  assert.match(js,/X-Audio-Offset-Seconds/);
  assert.match(js,/Attachment does not automatically change the exported video/);
});
