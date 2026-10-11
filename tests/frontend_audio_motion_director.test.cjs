'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const js = fs.readFileSync(path.join(__dirname,'..','frontend/dist/assets/animation.js'),'utf8');
const css = fs.readFileSync(path.join(__dirname,'..','frontend/dist/assets/animation.css'),'utf8');

test('DA4.2 can add a manual cue without detecting a beat', () => {
  assert.match(js,/function motionDirectorPanel\(/);
  assert.match(js,/data-cue-add/);
  assert.match(js,/motionLabAudioElement\?\.currentTime/);
  assert.match(js,/source_event_id:null/);
  assert.match(js,/push_zoom_in/);
  assert.match(js,/roll_right_left/);
});
test('DA4.2 saves and loads source-bound cue documents', () => {
  assert.match(js,/\/motion-lab\/audio-cues\//);
  assert.match(js,/source_sha256:motionLabAudioAnalysis\.source_sha256/);
  assert.match(js,/storedCues\.cues\.cues\.map/);
  assert.match(js,/duration_seconds:motionLabAudioAnalysis\.duration_seconds/);
});
test('DA4.2 separate cue lane and inspector is responsive', () => {
  assert.match(js,/data-timeline-cue/);
  assert.match(js,/data-cue-preset/);
  assert.match(css,/\.animation-audio-motion-director/);
  assert.match(css,/@media\(max-width:620px\)/);
});
