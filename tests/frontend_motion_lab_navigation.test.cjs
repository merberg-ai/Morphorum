'use strict';

const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const dist = path.join(__dirname, '..', 'frontend', 'dist');
const js = fs.readFileSync(path.join(dist, 'assets', 'animation.js'), 'utf8');
const css = fs.readFileSync(path.join(dist, 'assets', 'animation.css'), 'utf8');
const html = fs.readFileSync(path.join(dist, 'index.html'), 'utf8');

test('Motion Lab is first-class; unfinished Media is absent from visible navigation', () => {
  assert.match(js, /const VISIBLE_ANIMATION_TABS = \['editor', 'motion', 'monitor', 'outputs'\]/);
  assert.match(js, /const names = \{ editor: 'Editor', motion: 'Motion Lab', monitor: 'Monitor', outputs: 'Outputs' \}/);
  assert.doesNotMatch(js, /const names = \{[^}]*media:\s*'Media'/);
  assert.match(js, /mediaVault\.hidden = true/);
  assert.match(js, /mediaVault\.inert = true/);
  assert.match(js, /mediaVault\.setAttribute\('aria-hidden', 'true'\)/);
  assert.match(js, /if \(hybrid\) mediaVault\.appendChild\(hybrid\)/);
  assert.match(css, /#animation-media-vault\s*\{display:none!important;\}/);
  assert.match(js, /panels\.outputs\.appendChild\(video\)/);
  assert.match(js, /panels\.motion\.appendChild\(motionPreview\)/);
  assert.match(js, /panels\.motion\.appendChild\(motionIntro\)/);
});

test('Old persisted Media tab safely routes to Editor; Motion Lab selection persists', () => {
  const start = js.indexOf('  const ANIMATION_TAB_KEY = ');
  const end = js.indexOf('  function bind() {', start);
  assert.ok(start >= 0 && end > start);
  const buttons = ['editor', 'motion', 'monitor', 'outputs'].map(name => ({
    dataset: { animationTab: name }, tabIndex: -1, attrs: {},
    classList: { active: false, toggle(_, value) { this.active = value; } },
    setAttribute(k, v) { this.attrs[k] = v; },
  }));
  const panels = buttons.map(item => ({
    dataset: { animationPanel: item.dataset.animationTab }, hidden: true,
    classList: { active: false, toggle(_, value) { this.active = value; } },
  }));
  const stored = [];
  const context = {
    qsa: selector => selector.includes('[data-animation-tab]') ? buttons : panels,
    localStorage: { setItem: (k, v) => stored.push([k, v]) },
  };
  vm.runInNewContext(js.slice(start, end) +
    '\nthis.selectTab = showAnimationTab;', context);
  context.selectTab('motion');
  assert.equal(buttons[1].classList.active, true);
  assert.equal(panels[1].hidden, false);
  assert.equal(stored.at(-1)[1], 'motion');
  context.selectTab('media');
  assert.equal(buttons[0].classList.active, true);
  assert.equal(panels[0].hidden, false);
  assert.equal(buttons[1].classList.active, false);
  assert.equal(stored.at(-1)[1], 'editor');
});

test('Motion Lab preserves original CPU camera preview and gives functional navigation', () => {
  assert.match(html, /id="animation-motion-lab-intro"/);
  assert.match(html, /id="animation-motion-lab-edit-3d"/);
  assert.match(html, /id="animation-motion-lab-edit-timeline"/);
  assert.equal((html.match(/class="card glass animation-motion-preview-card"/g) || []).length, 1);
  assert.equal((html.match(/id="animation-generate-motion-preview"/g) || []).length, 1);
  assert.match(js, /showAnimationTab\('editor'\);\s*qs\('#animation-3d-camera-card'\)\?\.scrollIntoView/);
  assert.match(js, /showAnimationTab\('editor'\);\s*qs\('#animation-timeline-card'\)\?\.scrollIntoView/);
  assert.match(css, /#animation-panel-motion \{display:grid;gap:14px;/);
  assert.match(css, /@media\(max-width:640px\)\s*\{[^}]*\.animation-motion-lab-intro/);
});


test('Motion Lab preview is usable without a separately uploaded image', () => {
  assert.match(js, /if \(preview\) preview\.disabled = !state\.project \|\| Boolean\(state\.motionJobId\)/);
  assert.match(js, /if \(!state\.project \|\| state\.motionJobId\) return;/);
  assert.match(js, /animationMode\(\) !== '3d'/);
  assert.match(js, /job\.result\.source_kind === 'calibration-grid'/);
  assert.match(html, /built-in calibration grid immediately/);
  assert.match(html, /An uploaded reference is optional/);
  assert.doesNotMatch(js, /if \(preview\) preview\.disabled = [^;]*!hasSource/);
});


test('ML0 exposes draft motion layer presets with preview and explicit timeline apply', () => {
  for (const id of [
    'animation-motion-lab-composer', 'animation-motion-lab-preset',
    'animation-motion-lab-strength', 'animation-motion-lab-cycle',
    'animation-motion-lab-fade', 'animation-motion-lab-start',
    'animation-motion-lab-end', 'animation-motion-lab-blend',
    'animation-motion-lab-add', 'animation-motion-lab-clear',
    'animation-motion-lab-layer-list', 'animation-motion-lab-apply',
    'animation-motion-lab-preview-draft',
  ]) {
    assert.equal((html.match(new RegExp('id="' + id + '"', 'g')) || []).length, 1);
  }
  assert.match(js, /async function motionLabPreviewOrApply\(apply\)/);
  assert.match(js, /state\.project\.motion_lab\?\.layers/);
  assert.match(js, /body: JSON\.stringify\(\{ layers: motionLabDraftLayers \}\)/);
  assert.match(js, /await generateMotionPreview\(result\.project\)/);
  assert.match(js, /await loadTimeline\(\)/);
  assert.match(js, /const needsLayers = id !== 'animation-motion-lab-add'/);
  assert.match(css, /\.animation-motion-lab-fields \{display:grid;/);
});
