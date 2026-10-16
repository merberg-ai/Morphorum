'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const js = fs.readFileSync(path.join(__dirname,'..','frontend/dist/assets/animation.js'),'utf8');
const css = fs.readFileSync(path.join(__dirname,'..','frontend/dist/assets/animation.css'),'utf8');

test('DA4.4 Find Beats is optional and preserves manual cue workflow',()=>{
  assert.match(js,/function motionDirectorFindCandidates\(/);
  assert.match(js,/data-beat-preview/);
  assert.match(js,/data-beat-assign/);
  assert.match(js,/data-cue-add/);
});
test('DA4.4 filters by audio event, strength, gap, range and nth hit',()=>{
  assert.match(js,/event\.enabled === false/);
  assert.match(js,/event\.kind !== kind/);
  assert.match(js,/event\.time_seconds-last<minGap/);
  assert.match(js,/candidates\.filter\(\(_,i\)=>i%every===0\)/);
});
test('DA4.4 bulk assignment is source-linked, bounded and undoable',()=>{
  assert.match(js,/source_event_id:event\.id/);
  assert.match(js,/existing\.has\(event\.id\+'\|'\+chosen\)/);
  assert.match(js,/motionDirectorCues\.length\+additions\.length>3000/);
  assert.match(js,/motionDirectorBulkUndo=motionDirectorCues\.map/);
  assert.match(js,/data-beat-undo/);
  assert.match(css,/\.animation-audio-beat-grid/);
});
