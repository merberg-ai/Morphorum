'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const js = fs.readFileSync(path.join(__dirname,'..','frontend/dist/assets/animation.js'),'utf8');
const css = fs.readFileSync(path.join(__dirname,'..','frontend/dist/assets/animation.css'),'utf8');
test('DA3 analysis graphs are reparented into independent full-width workspace', () => {
  assert.match(js, /legacyDetails\.appendChild\(audioPreview\)/);
  assert.match(js, /panels\.audio\.appendChild\(analysisWorkspace\)/);
  assert.match(js, /diagnostics\.before\(section\)/);
  assert.match(js, /section\.after\(editor\)/);
  assert.match(css, /#animation-panel-audio\s*\{\s*display:flex;flex-direction:column/);
  assert.match(css, /\.animation-audio-analysis-workspace/);
});
test('DA3 existing audio graph identifiers and interactions remain mounted', () => {
  assert.match(js, /#animation-motion-lab-audio-preview/);
  assert.match(js, /#animation-audio-stereo-timeline/);
  assert.match(js, /#animation-audio-event-editor/);
  assert.match(css, /#animation-motion-lab-audio-plot \{\s*height:260px/);
});

test('DA3.3 timeline view and editing history stay integrated', () => {
  assert.match(js, /data-wave-mode/);
  assert.match(js, /Envelope \+ markers/);
  assert.match(js, /mode !== 'stereo'/);
  assert.match(js, /motionLabMarkerUndo/);
  assert.match(js, /motionLabMarkerRedo/);
  assert.match(js, /pointerdown/);
  assert.match(js, /pointermove/);
  assert.match(js, /motionLabMarkerSnapshot\(\)/);
  assert.match(js, /animation-audio-config-group/);
  assert.match(css, /\.animation-audio-config-grid/);
  assert.match(js, /diagnostics\.before\(section\)/);
});

test('Parseq-inspired layout places source and actions before waveform, controls after', () => {
  assert.match(js, /audioIntro\.after\(audioSourceDock\)/);
  assert.match(js, /audioSourceDock\.appendChild\(audioActions\)/);
  assert.match(js, /panels\.audio\.appendChild\(audioCard\)/);
  assert.match(js, /data-wave-left-time/);
  assert.match(js, /data-wave-right-time/);
  assert.match(js, /addEventListener\('dblclick'/);
  assert.match(js, /event\.shiftKey/);
  assert.match(css, /\.animation-audio-source-dock/);
  assert.match(css, /\.animation-audio-ruler/);
});
