'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const root = path.join(__dirname, '..', 'frontend', 'dist');
const read = p => fs.readFileSync(path.join(root, p), 'utf8');
test('shared UI service loads before consumers and sanitizes dialog messages', () => {
  const html = read('index.html');
  assert.ok(html.indexOf('/assets/ui-services.js') < html.indexOf('/assets/app.js'));
  const service = read('assets/ui-services.js');
  assert.match(service, /message\.textContent = entry\.message/);
  assert.match(service, /title\.textContent = entry\.title/);
  assert.match(service, /if \(event\.target === dialog\) onCancel\(event\)/);
  assert.match(service, /document\.execCommand\?\.\('copy'\)/);
});
test('native confirm/prompt calls replaced with promise-based shared dialogs', () => {
  const source = read('assets/animation.js');
  assert.doesNotMatch(source, /window\.(confirm|prompt)\(/);
  assert.match(source, /await window\.MorphorumDialog\.confirm/);
  assert.match(source, /await window\.MorphorumDialog\.prompt/);
});
test('model-index errors are displayed as text instead of interpolated HTML', () => {
  const models = read('assets/models.js');
  assert.doesNotMatch(models, /innerHTML = `<div class="model-empty">/);
  assert.match(models, /detail\.textContent = String\(error\.message\)/);
  assert.match(models, /window\.MorphorumClipboard\.writeText/);
});
test('server-buffer deletion requires confirmation', () => {
  assert.match(read('assets/app.js'), /Clear server console buffer\?/);
});
