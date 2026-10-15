'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const js = fs.readFileSync(path.join(__dirname, '..', 'frontend/dist/assets/animation.js'), 'utf8');
const css = fs.readFileSync(path.join(__dirname, '..', 'frontend/dist/assets/animation.css'), 'utf8');

test('DA3.1 edits a separate copy of detector events rather than analysis output', () => {
  assert.match(js, /const original = \(analysis\.events\?\.events \|\| \[\]\)\.map\(e => \(\{ \.\.\.e, enabled: true \}\)\)/);
  assert.match(js, /function motionLabEventChange\(action\)/);
  assert.match(js, /action === 'reset'/);
  assert.match(js, /action === 'remove'/);
  assert.match(js, /selected\.time_seconds =/);
  assert.match(js, /selected\.enabled =/);
});
test('DA3.1 selection uses waveform time and a bounded click tolerance', () => {
  assert.match(js, /const tolerance = \(end - begin\) \* 12 \/ bounds\.width/);
  assert.match(js, /motionLabSelectedEvent = closest\.id/);
  assert.match(js, /motionLabStereoWaveform\(\)/);
});
test('DA3.2 marker panel exposes explicit persistence without changing camera motion', () => {
  assert.match(js, /Marker edits are stored with this WAV in the project/);
  assert.match(js, /data-event-persist/);
  assert.match(js, /motionLabSaveMarkers/);
  assert.match(css, /\.animation-audio-event-fields/);
  assert.match(css, /@media\(max-width:620px\)/);
});
test('DA4.3 clear detected markers preserves manual markers and camera cues', () => {
  assert.match(js, /data-event-clear-detected/);
  assert.match(js, /action === 'clear-detected'/);
  assert.match(js, /e\.source === 'manual'/);
  assert.match(js, /String\(e\.id\)\.startsWith\('manual-'\)/);
  assert.match(js, /motionLabMarkerSnapshot\(\)/);
});
