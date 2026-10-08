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
  assert.match(a.help.textContent, /every 2th frame/);
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
