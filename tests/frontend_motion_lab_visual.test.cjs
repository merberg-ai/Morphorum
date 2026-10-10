'use strict';

const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(
  path.join(__dirname, '..', 'frontend', 'dist', 'assets', 'motion-lab-visual.js'), 'utf8',
);

function createVisualizer() {
  const context = {
    document: {getElementById: () => null},
    window: {},
    requestAnimationFrame: () => 1,
    cancelAnimationFrame: () => {},
  };
  vm.runInNewContext(source, context);
  return new context.window.MorphorumMotionLabVisualizer();
}

function sampleData() {
  return {
    frames: 4, fps: 2,
    series: {
      translation_x: [0, 1, 0, -1],
      translation_y: [0, 0, 1, 0],
      translation_z: [0, 1, 1, 1],
      rotation_x: [0, .1, .2, .3],
      rotation_y: [0, 0, 0, 0],
      rotation_z: [0, .1, 0, -.1],
    },
  };
}

test('ML1 client visualizer integrates native per-frame motion and scrubs deterministically', () => {
  const visual = createVisualizer();
  visual.setData(sampleData());
  assert.equal(visual.count, 4);
  assert.equal(visual.fps, 2);
  assert.equal(visual.series.translation_x[1], 1);
  assert.equal(visual.points.length, 4);
  assert.equal(visual.frame, 0);
  visual.setFrame(2);
  assert.equal(visual.frame, 2);
  visual.setFrame(100);
  assert.equal(visual.frame, 3);
  visual.setFrame(-20);
  assert.equal(visual.frame, 0);
  assert.equal(visual.stale, false);
  visual.invalidate();
  assert.equal(visual.stale, true);
  visual.clear();
  assert.equal(visual.series, null);
  assert.equal(visual.count, 0);
});

test('ML1 playback respects project FPS and pauses when a draft becomes stale', () => {
  const visual = createVisualizer();
  visual.setData(sampleData());
  visual.play();
  assert.equal(visual.playing, true);
  visual.tick(1000); // initial requestAnimationFrame time origin
  visual.tick(1500); // two frames / second => frame 1
  assert.equal(visual.frame, 1);
  visual.invalidate();
  assert.equal(visual.playing, false);
  visual.play();
  assert.equal(visual.playing, false);
});

test('ML1 rejects missing or malformed preview motion data', () => {
  const visual = createVisualizer();
  assert.throws(() => visual.setData({frames: 2, fps: 12}), /No resolved motion/);
  const wrong = sampleData();
  wrong.series.rotation_y = [0, 0, 0];
  assert.throws(() => visual.setData(wrong), /Incomplete rotation_y/);
  const invalid = sampleData();
  invalid.series.rotation_x = [0, NaN, 0, 0];
  assert.throws(() => visual.setData(invalid), /Non-finite/);
});
