'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const root = path.join(__dirname, '..', 'frontend','dist');
const read = file => fs.readFileSync(path.join(root,file),'utf8');

test('Image form is versioned, allowlisted and survives refresh', () => {
  const src = read('assets/image.js');
  assert.match(src, /morphorum\.image\.form\.v1/);
  assert.match(src, /function readImageDraft\(/);
  assert.match(src, /function restoreImageDraft\(/);
  assert.match(src, /function resetImageDraft\(/);
  assert.match(src, /await loadImageJobHistory\(\{ reconnect: true \}\)/);
  assert.match(read('index.html'), /id="image-result-lightbox"/);
});
test('Animation workspaces reuse renderer and provide actual step-count meter', () => {
  const src = read('assets/animation.js');
  assert.match(src, /function setupAnimationWorkspaceTabs\(/);
  assert.match(src, /showAnimationTab\('monitor'\)/);
  assert.match(src, /job\?\.current_step_total/);
  assert.match(read('index.html'), /id="animation-step-progress-fill"/);
  assert.match(src, /animation-video-'\)/); // Separate export controls cannot dirty project.
});
test('Global progress and compact mobile navigation are interactive', () => {
  const src = read('assets/app.js');
  const html = read('index.html');
  assert.match(src, /morphorum:job-status/);
  assert.match(src, /function openActiveJob\(/);
  assert.match(src, /function refreshNavMore\(/);
  assert.match(html, /id="global-job-status"/);
  assert.match(html, /id="nav-more-toggle"/);
});
test('Settings and Console provide guarded, grouped controls', () => {
  const src = read('assets/app.js');
  assert.match(src, /function markSettingsDirty\(/);
  assert.match(src, /Discard unsaved settings\?/);
  assert.match(src, /function selectSettingsTab\(/);
  assert.match(src, /data-console-preset/);
  assert.match(read('index.html'), /id="console-search"/);
  assert.match(read('index.html'), /id="console-jump-latest"/);
});
test('LoRA quick actions and shared clipboard use the same formatter', () => {
  const src = read('assets/loras.js');
  assert.match(src, /function copyPromptSnippet\(/);
  assert.match(src, /window\.MorphorumPromptTags\.lora\(data\)/);
  const html = read('index.html');
  assert.match(html, /id="lora-manager-copy"/);
  assert.match(html, /id="lora-manager-snippet"/);
});
