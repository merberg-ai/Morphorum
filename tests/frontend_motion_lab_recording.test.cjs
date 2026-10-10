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
