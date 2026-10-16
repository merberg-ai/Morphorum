'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const root = path.join(__dirname, '..', 'frontend', 'dist');
const read = file => fs.readFileSync(path.join(root, file), 'utf8');

test('Editor explains missing project and offers real navigation actions', () => {
  const html = read('index.html');
  const animation = read('assets/animation.js');
  const css = read('assets/animation.css');
  assert.match(html, /id="animation-editor-guidance"[^>]+aria-live="polite"/);
  assert.match(html, /id="animation-editor-open-project"/);
  assert.match(html, /id="animation-editor-create-project"/);
  assert.match(html, /id="animation-model-guidance"/);
  assert.match(animation, /function renderEditorGuidance\(\)/);
  assert.match(animation, /panel\.hidden = Boolean\(project\)/);
  assert.match(animation, /showAnimationTab\('projects'\)/);
  assert.match(animation, /showAnimationTab\('wizard'\)/);
  assert.match(animation, /still-image model selection is separate/);
  assert.match(css, /\.animation-editor-guidance\[hidden\]/);
});

test('Last project is restored only if present, and deletion clears it', () => {
  const animation = read('assets/animation.js');
  assert.match(animation, /morphorum\.animation\.lastProjectId\.v1/);
  assert.match(animation, /localStorage\.getItem\(LAST_ANIMATION_PROJECT_KEY\)/);
  assert.match(animation, /localStorage\.setItem\(LAST_ANIMATION_PROJECT_KEY/);
  assert.match(animation, /if \(savedId && !preferred\) forgetAnimationProject\(savedId\)/);
  assert.match(animation, /const ordered = \[preferred, state\.projects\[0\]\.id\]/);
  assert.match(animation, /rememberAnimationProject\(state\.project\.id\)/);
  assert.match(animation, /forgetAnimationProject\(item\.id\)/);
  assert.match(animation, /confirmDirty &&\s*state\.dirty/);
});

test('An optional depth service outage cannot block animation project loading', () => {
  const animation = read('assets/animation.js');
  assert.match(animation, /loadDepthModels\(\)\.catch\(error => \{/);
  assert.match(animation, /await loadProjectList\(\{ loadFirst: true \}\)/);
});
