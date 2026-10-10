'use strict';

const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const root = path.join(__dirname, '..', 'frontend', 'dist');
const source = fs.readFileSync(path.join(root, 'assets', 'motion-lab-recording.js'), 'utf8');
const html = fs.readFileSync(path.join(root, 'index.html'), 'utf8');
const animation = fs.readFileSync(path.join(root, 'assets', 'animation.js'), 'utf8');
const css = fs.readFileSync(path.join(root, 'assets', 'animation.css'), 'utf8');

function harness(sampleInput = () => ({values:{}, sources:[]})) {
  let now = 0;
  let callback = null;
  const completions = [];
  const frames = [];
  const context = {
    window: {},
    performance: {now: () => now},
    requestAnimationFrame: cb => { callback = cb; return 7; },
    cancelAnimationFrame: () => { callback = null; },
  };
  vm.runInNewContext(source, context);
  const recorder = new context.window.MorphorumMotionLabFrameRecorder({
    now: () => now,
    requestFrame: cb => { callback = cb; return 7; },
    cancelFrame: () => { callback = null; },
  });
  const start = overrides => recorder.start({
    fps: 12,
    startFrame: 4,
    maxFrames: 20,
    armedAxes: ['translation_x'],
    translationScale: .02,
    rotationScale: .5,
    deadzone: 0,
    response: 1,
    tailFrames: 0,
    sampleInput,
    onFrame: payload => frames.push(payload),
    onComplete: payload => completions.push(payload),
    ...overrides,
  });
  return {
    recorder, start, frames, completions,
    setNow: value => { now = value; },
    tick: stamp => { assert.ok(callback); callback(stamp); },
  };
}

test('ML2 frame clock fills dropped callbacks without duplicating frames', () => {
  const h = harness(() => ({values:{translation_x:1},sources:['keyboard']}));
  h.start();
  assert.equal(h.frames.length, 1);
  assert.equal(h.frames[0].frame, 4);
  assert.equal(h.frames[0].sample[0], .02);

  h.setNow(250);
  h.tick(250);
  assert.deepEqual(h.frames.map(item => item.frame), [4,5,6,7]);
  const count = h.frames.length;
  h.tick(250);
  assert.equal(h.frames.length, count);
  const take = h.recorder.stop('manual');
  assert.equal(take.samples.length, 4);
  assert.equal(take.startFrame, 4);
  assert.equal(take.endFrame, 8);
  assert.deepEqual(take.sources, ['keyboard']);
});

test('ML2 frame zero is forced stationary even with held input', () => {
  const h = harness(() => ({values:{translation_x:1},sources:['keyboard']}));
  h.start({startFrame:0,maxFrames:4});
  assert.deepEqual(Array.from(h.frames[0].sample), [0,0,0,0,0,0]);
  h.setNow(84);
  h.tick(84);
  assert.equal(h.frames[1].frame, 1);
  assert.equal(h.frames[1].sample[0], .02);
});

test('ML2 response smoothing and stop tail return motion to zero deterministically', () => {
  let held = true;
  const h = harness(() => ({
    values:{translation_x:held ? 1 : 0},
    sources:['touch'],
  }));
  h.start({response:.5,tailFrames:3});
  assert.equal(h.frames[0].sample[0], .01);
  h.setNow(84);
  h.tick(84);
  assert.equal(h.frames[1].sample[0], .015);
  held = false;
  const take = h.recorder.stop('manual');
  assert.equal(take.samples.length, 5);
  assert.equal(take.samples.at(-1)[0], 0);
  assert.deepEqual(take.sources, ['touch']);
});

test('ML2 auto-stop respects project frame bounds exactly once', () => {
  const h = harness(() => ({values:{translation_x:.5},sources:['keyboard']}));
  h.start({startFrame:8,maxFrames:2});
  h.setNow(1000);
  h.tick(1000);
  assert.equal(h.frames.length, 2);
  assert.equal(h.completions.length, 1);
  assert.equal(h.completions[0].reason, 'project-end');
  assert.equal(h.completions[0].endFrame, 10);
});

test('ML2 recording card is wired into Motion Lab with mobile-safe controls', () => {
  for (const id of [
    'animation-motion-lab-recording',
    'animation-motion-lab-record',
    'animation-motion-lab-stop-recording',
    'animation-motion-lab-record-start',
    'animation-motion-lab-record-status',
    'animation-motion-lab-stick-translate',
    'animation-motion-lab-stick-rotate',
    'animation-motion-lab-record-gamepad',
  ]) assert.equal((html.match(new RegExp('id="' + id + '"', 'g')) || []).length, 1);
  assert.match(animation, /const recording = qs\('#animation-motion-lab-recording'\)/);
  assert.match(animation, /panels\.motion\.appendChild\(recording\)/);
  assert.match(animation, /new window\.MorphorumMotionLabFrameRecorder/);
  assert.match(animation, /visibilitychange/);
  assert.match(animation, /pointercancel/);
  assert.match(animation, /navigator\.getGamepads/);
  assert.match(css, /\.animation-motion-stick \{[^}]*touch-action:none/s);
  assert.match(css, /@media\(max-width:640px\)[\s\S]*animation-motion-recording-controls/);
});

test('ML2 recording exposes live axis/frame feedback and does not seek the start with playback', () => {
  for (const id of [
    'animation-motion-lab-live-monitor',
    'animation-motion-lab-live-indicator',
    'animation-motion-lab-live-axes',
    'animation-motion-lab-live-input',
  ]) assert.equal((html.match(new RegExp('id="' + id + '"', 'g')) || []).length, 1);
  assert.match(animation, /function motionLabRecordLiveFrame\(frame, sample, captured, fps, maxFrame\)/);
  assert.match(animation, /motionLabRecordLiveFrame\(frame, sample, captured, fps, count - 1\)/);
  assert.match(animation, /motionLabRecordFinishedFeedback\(take\)/);
  assert.match(animation, /The record start frame is an explicit field/);
  assert.doesNotMatch(animation, /recordStart\.value = String\(frame\)/);
  assert.doesNotMatch(animation, /start\.value = String\(Math\.min\(count - 1, layer\.end_frame\)\)/);
  assert.match(css, /\.animation-motion-live-monitor \{/);
});

test('ML2 quick actions stay available during scrolling and use the canonical controls', () => {
  assert.match(animation, /function motionLabSetupQuickActions\(panel\)/);
  assert.match(animation, /motionLabSetupQuickActions\(panels\.motion\)/);
  for (const id of ['animation-motion-lab-record', 'animation-motion-lab-stop-recording',
    'animation-motion-lab-update-curves', 'animation-motion-lab-preview-draft',
    'animation-motion-lab-apply']) {
    assert.ok(animation.includes("['" + id + "',"), 'dock missing ' + id);
  }
  assert.match(animation, /button\.disabled = active \|\| !original \|\| original\.disabled/);
  assert.match(animation, /original\.click\(\)/);
  assert.match(css, /\.animation-motion-lab-quick-actions\s*\{[^}]*position:sticky;bottom:8px/s);
  assert.match(css, /@media\(max-width:640px\)[\s\S]*animation-motion-lab-quick-actions/s);
});

test('sticky Motion Lab toolbar is desktop-only and cannot overlay mobile navigation', () => {
  assert.match(css, /@media \(max-width: 767px\), \(hover: none\) and \(pointer: coarse\)\s*\{\s*\.animation-motion-lab-quick-actions\s*\{\s*display: none !important;/);
});

test('ML2.3 take rename and duplication are safe and undoable', () => {
  assert.match(animation, /if \(layer\.type === 'recording'\) \{\s*const rename = document\.createElement\('button'\)/);
  assert.match(animation, /field\.maxLength = 80/);
  assert.match(animation, /motionLabDraftLayers\[index\]\.name = value;/);
  assert.match(animation, /copy\.enabled = false;/);
  assert.match(animation, /motionLabDraftLayers\.splice\(index \+ 1, 0, copy\)/);
  assert.match(animation, /motionLabDraftLayers\.length >= 24/);
  assert.match(css, /\.animation-motion-take-rename \{/);
});

test('ML2.3 punch-in splices only armed axes and selected frames, without mutating source', () => {
  const context = {window:{},performance:{now:()=>0},requestAnimationFrame:()=>1,cancelAnimationFrame:()=>{}};
  vm.runInNewContext(source,context);
  const splice = context.window.MorphorumMotionLabSplicePunchIn;
  const original = {id:'one',type:'recording',enabled:true,source:'keyboard',fps:12,
    start_frame:0,end_frame:6,axes:['translation_x','rotation_y'],
    samples:Array.from({length:6},(_,i)=>[i,0,0,0,i*2,0])};
  const take={fps:12,startFrame:2,endFrame:4,armedAxes:['translation_x'],
    sources:['keyboard'],samples:[[77,0,0,0,0,0],[88,0,0,0,0,0]]};
  const edited=splice(original,take);
  assert.deepEqual(JSON.parse(JSON.stringify(edited.samples)),[
    [0,0,0,0,0,0],[1,0,0,0,2,0],[77,0,0,0,4,0],
    [88,0,0,0,6,0],[4,0,0,0,8,0],[5,0,0,0,10,0]]);
  assert.equal(original.samples[2][0],2);
  assert.throws(()=>splice(original,{...take,fps:24}),/FPS/);
  assert.throws(()=>splice(original,{...take,endFrame:7}),/range/);
  assert.throws(()=>splice(original,{...take,armedAxes:['rotation_z']}),/axes/);
  assert.throws(()=>splice(original,{...take,samples:[[1,2,3,4,5,6]]}),/range/);
});

test('ML2.3 punch-in requires explicit mode target end boundary and guards incomplete takes', () => {
  for(const id of ['animation-motion-lab-record-mode','animation-motion-lab-punch-target','animation-motion-lab-punch-end'])
    assert.ok(html.includes('id="'+id+'"'));
  assert.match(animation,/function motionLabPunchUi\(\)/);
  assert.match(animation,/take\.endFrame !== context\.endFrame/);
  assert.match(animation,/window\.MorphorumMotionLabSplicePunchIn\(existing, take\)/);
  assert.match(animation,/snapshot:JSON\.stringify\(target\)/);
  assert.match(animation,/maxFrames: remainingFrames/);
});

test('ML3.1 WAV analysis has a live pre-layer envelope and threshold preview', () => {
  for (const id of ['animation-motion-lab-audio-preview','animation-motion-lab-audio-plot',
    'animation-motion-lab-audio-summary','animation-motion-lab-audio-prediction']) {
    assert.ok(html.includes('id="' + id + '"'), 'missing ' + id);
  }
  assert.match(animation, /function motionLabAudioPreview\(\)/);
  assert.match(animation, /motionLabAudioPreview\(\);/);
  assert.match(animation, /thresholdField\.value = Math\.min\(\.1, peak \* \.55\)\.toFixed\(3\)/);
  assert.match(animation, /i \+ pulseLength <= values\.length/);
  assert.match(animation, /for \(const id of \['threshold','attack','release','distance'\]\)/);
  assert.match(css, /#animation-motion-lab-audio-plot \{/);
  assert.match(css, /@media\(max-width:540px\) \{#animation-motion-lab-audio-plot/);
});

test('ML3 WAV audio transport follows visual play pause frame seek and source lifecycle', () => {
  assert.match(html, /id="animation-motion-lab-audio-sync"/);
  assert.match(html, /id="animation-motion-lab-audio-sync-status"/);
  assert.match(animation, /function motionLabBindAudioTransport\(\)/);
  assert.match(animation, /motionLabVisual\.onPlay = \(frame, fps\)/);
  assert.match(animation, /motionLabVisual\.onPause = \(\) => motionLabAudioElement\?\.pause\(\)/);
  assert.match(animation, /motionLabVisual\.onFrameChange = frame =>/);
  assert.match(animation, /Math\.abs\(audio\.currentTime - position\) > \.18/);
  assert.match(animation, /URL\.revokeObjectURL\(motionLabAudioUrl\)/);
  assert.match(animation, /motionLabBindAudioTransport\(\);/);
  assert.match(css, /\.animation-motion-audio-playback/);
});
