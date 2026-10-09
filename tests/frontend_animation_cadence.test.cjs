'use strict';

const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const root = path.join(__dirname, '..', 'frontend', 'dist');
const html = fs.readFileSync(path.join(root, 'index.html'), 'utf8');
const source = fs.readFileSync(path.join(root, 'assets', 'animation.js'), 'utf8');
const begin = source.indexOf('  function syncCadencePreset() {');
const end = source.indexOf('  function fillForm() {', begin);
assert.ok(begin >= 0 && end > begin, 'animation.js has cadence preset behavior');

function setup(schedule = '0:(1)') {
  const field = { value: schedule, focused: false, focus() { this.focused = true; } };
  const preset = {
    value: '1',
    options: ['1', '2', '3', '4', '6', '8', 'custom'].map(value => ({ value })),
  };
  const help = { textContent: '' };
  const nodes = {
    '#animation-cadence': field,
    '#animation-cadence-preset': preset,
    '#animation-cadence-help': help,
  };
  const dirty = [];
  const context = {
    qs(selector) { return nodes[selector] || null; },
    state: { project: { id: 'project' } },
    markDirty(args) { dirty.push(args); },
  };
  vm.runInNewContext(
    source.slice(begin, end) +
    '\nthis.sync = syncCadencePreset; this.apply = applyCadencePreset;',
    context,
  );
  return { field, preset, help, dirty, sync: context.sync, apply: context.apply };
}

test('cadence control is top-level, early in Animation, with one schedule input', () => {
  const start = html.indexOf('id="view-animation"');
  const project = html.indexOf('animation-project-card', start);
  const cadence = html.indexOf('id="animation-cadence-card"', project);
  const startFrame = html.indexOf('animation-start-card', project);
  const generation = html.indexOf('Generation State', startFrame);
  assert.ok(start < project && project < cadence && cadence < startFrame && startFrame < generation);
  assert.equal((html.match(/id="animation-cadence"/g) || []).length, 1);
  assert.equal((html.match(/id="animation-cadence-preset"/g) || []).length, 1);
  assert.ok(source.includes("'diffusion-cadence',"), 'cadence section is open by default on mobile');
  assert.ok(source.includes("input.id === 'animation-cadence-preset'"),
    'preset does not get registered as a generic duplicate editor');
});

test('choosing cadence 2 writes the existing canonical Deforum schedule', () => {
  const a = setup('0:(1)');
  a.preset.value = '2';
  a.apply();
  assert.equal(a.field.value, '0:(2)');
  assert.equal(a.preset.value, '2');
  assert.match(a.help.textContent, /every 2 frames/);
  assert.equal(a.dirty.length, 1);
  assert.equal(a.dirty[0].validate, true);
});

test('cadence 3 and manual keyframed schedule survive synchronization', () => {
  const a = setup('0:(3)');
  a.sync();
  assert.equal(a.preset.value, '3');
  a.field.value = '0:(1), 24:(3)';
  a.sync();
  assert.equal(a.preset.value, 'custom');
  assert.equal(a.field.value, '0:(1), 24:(3)');
  assert.match(a.help.textContent, /Custom keyframe schedule/);
});

test('selecting Custom preserves the raw schedule and focuses its editor', () => {
  const a = setup('0:(2)');
  a.preset.value = 'custom';
  a.apply();
  assert.equal(a.field.value, '0:(2)');
  assert.equal(a.field.focused, true);
  assert.equal(a.dirty.length, 0);
});

test('B5.1 projection quality and hole fill are editable and round-trip through Animation', () => {
  assert.equal((html.match(/id="animation-3d-projection-mode"/g) || []).length, 1);
  assert.equal((html.match(/id="animation-3d-hole-fill"/g) || []).length, 1);
  assert.match(html, /value="legacy".*Legacy: nearest-pixel Z-buffer/);
  assert.match(html, /value="splat".*subpixel depth-tested splat/);
  assert.match(html, /value="background".*Prefer background layer/);
  assert.match(source, /project\.camera_3d\?\.projection_mode \|\| 'legacy'/);
  assert.match(source, /project\.camera_3d\?\.hole_fill \|\| 'nearest'/);
  assert.match(source, /projection_mode: qs\('#animation-3d-projection-mode'\)/);
  assert.match(source, /hole_fill: qs\('#animation-3d-hole-fill'\)/);
});

test('B5.2 future-anchor settings are opt-in and survive project editor round-trip', () => {
  assert.equal((html.match(/id="animation-temporal-mode"/g) || []).length, 1);
  assert.equal((html.match(/id="animation-temporal-mix"/g) || []).length, 1);
  assert.equal((html.match(/id="animation-temporal-contrast"/g) || []).length, 1);
  assert.match(html, /value="forward">Forward-only/);
  assert.match(html, /value="future-anchor">Future-anchor depth-aligned tween/);
  assert.match(source, /project\.temporal\?\.mode \|\| 'forward'/);
  assert.match(source, /project\.temporal\?\.mix \?\? 0\.65/);
  assert.match(source, /project\.temporal\?\.contrast_threshold \?\? 96/);
  assert.match(source, /mode: qs\('#animation-temporal-mode'\)\?\.value \|\| 'forward'/);
  assert.match(source, /mix: Number\(qs\('#animation-temporal-mix'\)/);
  assert.match(source, /contrast_threshold: Number\(qs\('#animation-temporal-contrast'\)/);
});
