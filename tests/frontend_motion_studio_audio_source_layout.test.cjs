'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const root = path.join(__dirname,'..');
const js=fs.readFileSync(path.join(root,'frontend/dist/assets/animation.js'),'utf8');
const html=fs.readFileSync(path.join(root,'frontend/dist/index.html'),'utf8');
const css=fs.readFileSync(path.join(root,'frontend/dist/assets/animation.css'),'utf8');

test('audio source is the first Motion Studio card after intro',()=>{
  assert.match(js,/audioIntro\.after\(audioSourceDock\)/);
  assert.match(js,/audioSourceDock\.id = 'animation-audio-source-dock'/);
  assert.match(js,/motionStudioCreateArrangementCard\(panels\.audio\)/);
  assert.match(js,/motionStudioCreateChannelCard\(panels\.audio\)/);
  assert.doesNotMatch(js,/analysisWorkspace\.prepend\(audioSourceDock\)/);
  assert.match(css,/\.animation-audio-source-dock/);
  assert.match(css,/@media\(max-width:640px\)/);
});

test('existing WAV, saved soundtrack and analyzer controls retain their IDs and event handlers',()=>{
  for (const id of [
    'animation-motion-lab-audio-file','animation-motion-lab-use-soundtrack',
    'animation-motion-lab-analyze-audio','animation-motion-lab-add-audio',
  ]) assert.equal((html.match(new RegExp('id="'+id+'"','g'))||[]).length,1,id);
  // Controls are grouped by stable IDs, not fragile child offsets.
  for (const id of [
    'animation-motion-lab-audio-file','animation-motion-lab-audio-band',
    'animation-motion-lab-audio-detection','animation-motion-lab-audio-sensitivity',
    'animation-motion-lab-audio-threshold','animation-motion-lab-audio-axis',
    'animation-motion-lab-audio-distance','animation-motion-lab-audio-attack',
    'animation-motion-lab-audio-release',
  ]) assert.ok(js.includes("labelOf('" + id + "')"), id);
  assert.match(js,/audioSourceDock\.appendChild\(details\)/);
  assert.match(js,/audioSourceDock\.appendChild\(audioActions\)/);
  assert.match(js,/modeAreas\.pulse\.appendChild\(actions\)/);
  assert.match(js,/stages\.analysis\.insertBefore\(row, analysisStatus\)/);
  assert.match(js,/qs\('#animation-motion-lab-use-soundtrack'\)\?\.addEventListener/);
  assert.match(js,/qs\('#animation-motion-lab-analyze-audio'\)\?\.addEventListener/);
});
