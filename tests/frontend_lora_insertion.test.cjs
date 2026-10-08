'use strict';

const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(
  path.join(__dirname, '..', 'frontend', 'dist', 'assets', 'image.js'), 'utf8'
);
const begin = source.indexOf('  function reportManagerInsertion(');
const end = source.indexOf('\n  window.MorphorumImage =', begin);
assert.ok(begin >= 0 && end > begin, 'image.js must expose the tested prompt insertion implementation');
const realFunctions = source.slice(begin, end);

function setup(modelFamily = 'sdxl') {
  const record = {
    id: 'creepy-529922',
    family: 'sdxl',
    name: 'DonMCr33pyD0115XL_529922',
    filename: 'DonMCr33pyD0115XL_529922.safetensors',
  };
  const prompt = { value: 'portrait, a wizard' };
  const messages = [];
  const events = [];
  const context = {
    state: {
      model: modelFamily ? { family: modelFamily } : null,
      loras: [record],
    },
    qs(selector) {
      if (selector === '#image-prompt') return prompt;
      if (selector === '.nav-button[data-view="image"]') return { click() {} };
      return null;
    },
    insertAtCursor(textarea, value) {
      textarea.value += ' ' + value;
    },
    toast(...args) { messages.push(args); },
    api(url, options) {
      events.push({ url, ...JSON.parse(options.body) });
      return Promise.resolve({});
    },
    console,
  };
  vm.runInNewContext(realFunctions + '\nthis.insertFromManager = insertFromManager;', context);
  return { insert: context.insertFromManager, record, prompt, messages, events };
}

test('valid real-world LoRA names containing r/n insert repeatedly and log success', () => {
  const { insert, record, prompt, messages, events } = setup();
  for (const weight of [1.0, 0.8]) {
    assert.equal(insert({
      id: record.id, family: record.family, name: record.name, weight,
      triggers: ['neon room', 'ranger', 'neon room'],
    }), true);
  }
  assert.match(prompt.value, /<lora:DonMCr33pyD0115XL_529922:1>/);
  assert.match(prompt.value, /<lora:DonMCr33pyD0115XL_529922:0\.8>/);
  assert.match(prompt.value, /neon room, ranger/);
  assert.equal(messages.length, 0);
  assert.equal(events.length, 2);
  assert.deepEqual(events.map(e => e.event), ['prompt_inserted', 'prompt_inserted']);
  assert.equal(events[0].trigger_count, 2);
  assert.match(events[0].url, /\/api\/loras\/creepy-529922\/activity/);
});

test('unsafe colon, angle bracket and real newline are rejected with reason', () => {
  const { insert, record, prompt, messages, events } = setup();
  for (const invalid of ['unsafe:name', 'unsafe>name', 'unsafe\nname', 'unsafe\rname']) {
    assert.equal(insert({ id: record.id, family: record.family, name: invalid, weight: 1 }), false);
  }
  assert.equal(prompt.value, 'portrait, a wizard');
  assert.equal(messages.length, 4);
  assert.deepEqual(events.map(e => e.reason),
    ['invalid_name', 'invalid_name', 'invalid_name', 'invalid_name']);
});

test('family mismatch is rejected and logged instead of inserting a wrong LoRA', () => {
  const { insert, record, prompt, events } = setup('flux');
  assert.equal(insert({ id: record.id, family: record.family, name: record.name, weight: 1 }), false);
  assert.equal(prompt.value, 'portrait, a wizard');
  assert.equal(events[0].event, 'prompt_rejected');
  assert.equal(events[0].reason, 'wrong_family');
  assert.equal(events[0].image_family, 'flux');
});

test('missing checkpoint or index entry is rejected and logged', () => {
  const none = setup(null);
  assert.equal(none.insert({ id: none.record.id, family: 'sdxl', name: none.record.name }), false);
  assert.equal(none.events[0].reason, 'no_model');
  const mismatch = setup();
  assert.equal(mismatch.insert({ id: 'not-indexed', family: 'sdxl', name: mismatch.record.name }), false);
  assert.equal(mismatch.events[0].reason, 'not_indexed');
});
