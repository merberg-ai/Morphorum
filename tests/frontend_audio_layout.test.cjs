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
  assert.match(js, /preview\.after\(section\)/);
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
