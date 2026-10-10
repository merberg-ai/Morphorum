'use strict';

const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.join(__dirname, '..', 'frontend', 'dist');
const html = fs.readFileSync(path.join(root, 'index.html'), 'utf8');
const animation = fs.readFileSync(path.join(root, 'assets', 'animation.js'), 'utf8');
const visualSource = fs.readFileSync(path.join(root, 'assets', 'motion-lab-visual.js'), 'utf8');
const css = fs.readFileSync(path.join(root, 'assets', 'animation.css'), 'utf8');

test('ML1b numeric/drag curve keyframe editing stays inside Motion Lab', () => {
  for (const id of [
    'animation-motion-lab-curve-editor',
    'animation-motion-lab-key-axis',
    'animation-motion-lab-key-blend',
    'animation-motion-lab-key-interpolation',
    'animation-motion-lab-key-frame',
    'animation-motion-lab-key-value',
    'animation-motion-lab-key-drag',
    'animation-motion-lab-path-drag',
    'animation-motion-lab-key-save',
    'animation-motion-lab-key-delete',
    'animation-motion-lab-key-clear',
    'animation-motion-lab-key-list',
  ]) assert.equal((html.match(new RegExp('id="' + id + '"', 'g')) || []).length, 1);
  assert.match(animation, /type: 'keyframes'/);
  assert.match(animation, /function motionLabCurveModify\(\{frame, value, replaceFrame = null\}\)/);
  assert.match(animation, /commitMotionLabDraft\(\)/);
  assert.match(animation, /motionLabVisual\?\.configureEditor/);
  assert.match(animation, /motionLabPreviewOrApply\(false, \{curvesOnly:true\}\)/);
  assert.match(css, /\.animation-motion-lab-curve-fields \{display:grid;/);
  assert.match(css, /@media\(max-width:540px\)/);
});

function prepare() {
  const handlers = {};
  const svg = {
    dataset: {},
    addEventListener: (name, fn) => {handlers[name] = fn;},
    getBoundingClientRect: () => ({left: 0, top: 0, width: 800, height: 300}),
    setPointerCapture: () => {},
    querySelector: () => null,
    replaceChildren: () => {},
    innerHTML: '',
  };
  const pathHandlers = {};
  const pathSvg = {
    dataset: {},
    addEventListener: (name, fn) => {pathHandlers[name] = fn;},
    getBoundingClientRect: () => ({left: 0, top: 0, width: 440, height: 300}),
    setPointerCapture: () => {},
    querySelector: () => null,
    replaceChildren: () => {},
    innerHTML: '',
  };
  const context = {
    document: {getElementById: id =>
      id === 'animation-motion-lab-curves' ? svg :
      id === 'animation-motion-lab-path' ? pathSvg : null},
    window: {},
    requestAnimationFrame: () => 1,
    cancelAnimationFrame: () => {},
  };
  vm.runInNewContext(visualSource, context);
  const visual = new context.window.MorphorumMotionLabVisualizer();
  const series = {
    translation_x: [0, .025, .05, 0], translation_y: [0, 0, 0, 0],
    translation_z: [0, 0, 0, 0], rotation_x: [0, 0, 0, 0],
    rotation_y: [0, 0, 0, 0], rotation_z: [0, 0, 0, 0],
  };
  visual.setData({series, frames: 4, fps: 12});
  return {visual, handlers, pathHandlers};
}

test('ML1b curve pointer dragging moves an existing keyframe without saving a project', () => {
  const {visual, handlers} = prepare();
  const changes = [];
  visual.configureEditor({
    axis: 'translation_x', keys: [{frame: 0,value: 0}, {frame: 2,value: .05}],
    enabled: true, onEdit: change => changes.push(change),
  });
  const evt = (x, y) => ({
    clientX:x, clientY:y, pointerId:7, buttons:1, preventDefault() {},
  });
  handlers.pointerdown(evt(533,38));
  assert.equal(visual.dragKey.originalFrame, 2);
  handlers.pointermove(evt(778,86));
  handlers.pointerup(evt(778,86));
  assert.equal(changes.length, 1);
  assert.equal(changes[0].frame, 3);
  assert.equal(changes[0].replaceFrame, 2);
  assert.ok(Math.abs(changes[0].value) < .000001);
  assert.equal(visual.dragKey, null);
});

test('ML1b graph editing cannot set nonzero camera movement on frame 0', () => {
  const {visual, handlers} = prepare();
  const changes = [];
  visual.configureEditor({
    axis:'translation_x',keys:[{frame:0,value:0}],enabled:true,
    onEdit:change => changes.push(change),
  });
  const evt = (x, y) => ({
    clientX:x, clientY:y, pointerId:5, buttons:1, preventDefault() {},
  });
  handlers.pointerdown(evt(43,20));
  handlers.pointerup(evt(43,20));
  assert.equal(changes.length, 0);
});


test('ML1b camera path handle adjusts per-frame native X and Y velocities', () => {
  const {visual, pathHandlers} = prepare();
  const edits = [];
  visual.configureEditor({
    axis:'translation_x', keys:[], enabled:false, pathEnabled:true,
    onPathEdit: edit => edits.push(edit),
  });
  const [x,y] = visual.points[2];
  const evt = (cx,cy) => ({
    clientX: cx, clientY:cy, pointerId:3, buttons:1, preventDefault() {},
  });
  pathHandlers.pointerdown(evt(x,y));
  assert.equal(visual.pathDrag.frame, 2);
  pathHandlers.pointermove(evt(x+24,y-12));
  pathHandlers.pointerup(evt(x+24,y-12));
  assert.equal(edits.length, 1);
  assert.equal(edits[0].frame, 2);
  const expectedScale = visual.points.nativeToPixelScale;
  assert.ok(Math.abs(edits[0].deltaX - 24/expectedScale) < 1e-8);
  assert.ok(Math.abs(edits[0].deltaY - 12/expectedScale) < 1e-8);
  assert.equal(visual.pathDrag, null);
  assert.match(animation, /function motionLabCurvePathEdit\(\{frame, deltaX, deltaY\}\)/);
  assert.match(animation, /deferCommit:true/);
});
