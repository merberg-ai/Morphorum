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

test('Active job progress reserves a dedicated desktop header row', () => {
  const css = read('assets/app.css');
  const html = read('index.html');
  assert.match(css, /\.topbar\s*\{[^}]*display:\s*grid;[^}]*grid-template-columns:/s);
  assert.match(css, /\.global-job-status\s*\{[^}]*grid-column:\s*1\/-1;grid-row:\s*2;/s);
  assert.doesNotMatch(css, /\.global-job-status\s*\{[^}]*flex:\s*0\s+0\s+100%/s);
  assert.match(css, /@media\s*\(max-width:\s*1180px\)\s*\{[^}]*\.topbar\s*\{[^}]*grid-template-columns:/s);
  assert.match(css, /\.global-job-status\s*\{\s*grid-row:\s*3;\s*\}/);
  assert.match(css, /@media\(max-width:640px\)\s*\{[\s\S]*?\.topbar-right\s*\{display:contents;\}/);
  assert.match(css, /\.global-job-status\s*\{grid-column:1\/-1;grid-row:3;/);
  assert.ok(html.indexOf('class="brand-block"') < html.indexOf('class="topbar-right"'));
  assert.ok(html.indexOf('id="runtime-build"') < html.indexOf('id="global-job-status"'));
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

test('Desktop has an independent wide-screen layout without replacing mobile styles', () => {
  const html = read('index.html');
  const desktop = read('assets/desktop.css');
  const mobile = read('assets/app.css');
  assert.match(html, /href="\/assets\/desktop\.css\?v=__MORPHORUM_ASSET_VERSION__" media="\(min-width: 1181px\) and \(hover: hover\) and \(pointer: fine\)"/);
  assert.match(desktop, /grid-template-areas:\s*"top top"\s*"nav main"/);
  assert.match(desktop, /\.main-nav\s*\{[^}]*flex-direction:\s*column/);
  assert.match(desktop, /#view-animation \.animation-workspace-nav\s*\{[^}]*display:\s*inline-flex/);
  assert.match(desktop, /#view-animation \.animation-workspace-nav button\s*\{[^}]*flex:\s*0 0 auto/);
  assert.match(desktop, /#animation-panel-editor \.animation-layout\s*\{[^}]*grid-template-columns:\s*repeat\(12/);
  assert.match(desktop, /#animation-panel-motion\s*\{[^}]*grid-template-areas:/);
  assert.match(desktop, /"author review"/);
  assert.match(desktop, /"audio audio"/);
  assert.match(desktop, /\.animation-motion-preview-card\s*\{[^}]*order:\s*-1/);
  assert.match(read('assets/animation.css'), /\.animation-motion-authoring-column,\s*#animation-panel-motion > \.animation-motion-review-column\s*\{\s*display:\s*contents;/);
  assert.match(mobile, /@media \(max-width: 640px\)/);
  assert.match(mobile, /\.main-nav\s*\{\s*position: fixed/);
});

test('Motion Lab explains its workflow without displaying internal milestone names', () => {
  const html = read('index.html');
  assert.match(html, /New to Motion Lab\? Start here/);
  assert.match(html, /What do Strength, Cycle, Fade, and Blend mean\?/);
  assert.match(html, /Apply to Animation/);
  assert.doesNotMatch(html, /<h2>[^<]+\s+<small class="muted">ML\d/);
  assert.doesNotMatch(html, /Controller recording and audio-reactive movement are coming later/);
  assert.doesNotMatch(html, /Full-band RMS in this first release/);
});

test('Motion Lab uses existing DOM controls in mobile-transparent desktop columns', () => {
  const js = read('assets/animation.js');
  const html = read('index.html');
  const desktop = read('assets/desktop.css');
  assert.match(js, /const motionAuthoringColumn = document\.createElement\('div'\)/);
  assert.match(js, /for \(const node of \[composer, recording\]\)/);
  assert.match(js, /for \(const node of \[visual, motionPreview\]\)/);
  assert.match(js, /if \(audio\) audio\.after\(motionReviewColumn\)/);
  assert.match(desktop, /#animation-panel-motion > \.animation-motion-authoring-column\s*\{\s*display:\s*flex/);
  assert.match(desktop, /#animation-panel-motion > \.animation-motion-review-column\s*\{\s*display:\s*flex/);
  assert.match(desktop, /\.animation-layout:has\(\.animation-depth-card\[hidden\]\)/);
  assert.match(html, /class="card glass animation-generation-state-card"/);
  assert.match(html, /id="animation-timeline-card"/);
  assert.match(html, /id="animation-motion-lab-recording"/);
});
