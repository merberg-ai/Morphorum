'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const base = path.join(__dirname, '..');
const read = filename => fs.readFileSync(path.join(base, filename), 'utf8');
const html = read('frontend/dist/index.html');
const animation = read('frontend/dist/assets/animation.js');
const app = read('frontend/dist/assets/app.js');

test('user-facing HTML has no internal development milestones or phase numbers', () => {
  assert.doesNotMatch(html, /\bB[0-9](?:\.[0-9]+)*(?:-[a-zA-Z0-9]+)?\b/);
  assert.doesNotMatch(html, /FIRST IMAGE MILESTONE|future frame renderer|future repair|B5\.5 Performance Diagnostics/);
  assert.match(html, /Animation Studio|ANIMATION STUDIO/);
  assert.match(html, /Source Video/);
  assert.match(html, /Performance & Memory/);
});
test('the wording-only pass preserves controls for previously implemented features', () => {
  const kept = [
    'image-prompt', 'image-negative-prompt', 'image-model-select', 'image-reset-draft',
    'animation-temporal-mode', 'animation-3d-projection-mode', 'animation-3d-preset',
    'animation-render-progress', 'animation-step-progress-fill',
    'animation-hybrid-source', 'animation-hybrid-file', 'animation-hybrid-extract',
    'animation-video-export', 'animation-export-video', 'animation-deforum-dialog',
    'animation-deforum-create', 'lora-manager-copy', 'lora-manager-insert',
    'model-list', 'console-window', 'model-path-cards',
  ];
  for (const id of kept) assert.ok(html.includes('id="' + id + '"'), id + ' must remain available');
});
test('render UI drops obsolete 512px modal while retaining informational size guidance', () => {
  const resolution = read('frontend/dist/assets/resolution.js');
  assert.doesNotMatch(animation, /confirmHigherResolutionRender|higherResolutionRenderRisk/);
  assert.match(animation, /async function startAnimationRender/);
  assert.match(animation, /api\('\/api\/animation\/renders'/);
  assert.match(resolution, /more GPU memory/);
  assert.doesNotMatch(animation, /physically verified 512|B6\.1 accepts/);
  assert.doesNotMatch(app, /text\.textContent = 'Connected'/);
  assert.match(app, /const health = await api\('\/api\/health'\)/);
  assert.match(app, /version\.textContent = displayVersion/);
  assert.match(app, /branchLabel\.textContent = branch/);
  assert.match(app, /shortBranchLabel\.textContent = compactRuntimeBranch\(branch\)/);
  assert.match(app, /commitFull\.textContent = commit/);
  assert.match(app, /version\.textContent = 'Offline'/);
});
test('import and LoRA warnings retain useful meaning without branch milestones', () => {
  const importer = read('backend/morphorum/deforum_import.py');
  const inspector = read('backend/morphorum/lora_inspector.py');
  assert.match(importer, /does not affect rendering/);
  assert.match(inspector, /Some SDXL loading modes may not apply those weights/);
  assert.doesNotMatch(importer, /no B6\.1 runtime effect/);
  assert.doesNotMatch(inspector, /B4 SDXL compatibility fallback/);
});

test('build identity shows version and branch with compact mobile disclosure', () => {
  const css = read('frontend/dist/assets/app.css');
  assert.match(html, /id="runtime-build"/);
  assert.match(html, /id="runtime-version"/);
  assert.match(html, /id="runtime-branch"/);
  assert.match(html, /id="runtime-branch-short"/);
  assert.match(html, /id="runtime-branch-full"/);
  assert.match(html, /id="runtime-commit"/);
  assert.match(css, /\.runtime-build-popover\s*\{/);
  assert.match(css, /\.runtime-branch-short\s*\{display:block !important;\}/);
  assert.match(css, /\.runtime-meta > span\s*\{/);
  assert.match(css, /text-overflow: ellipsis/);
});
