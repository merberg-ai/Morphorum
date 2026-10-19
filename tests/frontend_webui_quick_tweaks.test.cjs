'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const dist = path.join(__dirname, '..', 'frontend', 'dist');
const read = p => fs.readFileSync(path.join(dist, p), 'utf8');
const html = read('index.html');
const image = read('assets/image.js');
const animation = read('assets/animation.js');
const app = read('assets/app.js');
const css = read('assets/ux-polish.css');
const help = read('assets/help.js');

test('UX1 mobile project and motion dropdowns are bounded', () => {
  assert.match(css, /#project-nav-submenu:not\(\[hidden\]\), #motion-lab-sidebar:not\(\[hidden\]\)/);
  assert.match(css, /position:absolute; left:0; right:0; bottom:100%/);
  assert.match(css, /max-height:min\(60vh,420px\)/);
  assert.match(css, /overflow:auto/);
});

test('UX2 Image-to-Project copies selected settings, never prompt or CFG', () => {
  assert.match(html, /id="image-apply-to-project"/);
  assert.match(image, /applyImageSettingsToProject/);
  for (const field of ['image-model-select','image-width','image-height','image-steps','image-sampler','image-schedule-type','image-seed','image-seed-mode']) {
    assert.ok(image.includes("read('"+field+"')"), field);
  }
  assert.match(animation, /function applyImageSettingsToProject/);
  assert.match(animation, /const currentGuidance/);
  assert.match(animation, /const promptRowsBefore/);
  assert.match(animation, /markDirty\(\{validate:true\}\)/);
  assert.doesNotMatch(animation.match(/function applyImageSettingsToProject[\s\S]*?\n  \}/)?.[0] || '', /\.value = settings\.prompt/);
});

test('UX3 progress region is directly above image result history and preview', () => {
  const resultSection = html.split('<article class="card glass preview-card image-preview-card">')[1]?.split('</article>')[0] || '';
  assert.ok(resultSection.indexOf('id="generation-progress"') >= 0);
  assert.ok(resultSection.indexOf('id="generation-progress"') < resultSection.indexOf('id="image-empty-preview"'));
  assert.equal((html.match(/id="generation-progress"/g) || []).length, 1);
});

test('UX4 Help navigation is internal and consumes only bundled documents', () => {
  assert.match(html, /data-view="help"/);
  assert.match(html, /id="view-help"/);
  assert.match(html, /id="help-document-list"/);
  assert.match(html, /\/assets\/help\.js/);
  assert.match(app, /MorphorumHelp\?\.activate/);
  assert.match(help, /\/api\/help\/docs/);
  assert.match(help, /window\.MorphorumHelp=/);
});

test('UX4 documentation reader preserves existing contextual Help API', () => {
  const shared = read('assets/ui-services.js');
  assert.match(shared, /MorphorumHelp = \{refresh: refreshHelp, setEnabled: setHelpEnabled\}/);
  assert.match(help, /Object\.assign\(window\.MorphorumHelp \|\| \{\}, \{activate, markdownToHtml\}\)/);
  assert.doesNotMatch(help, /window\.MorphorumHelp\s*=\s*\{activate, markdownToHtml\}/);
  assert.match(app, /MorphorumHelp\?\.setEnabled/);
});

test('SDXL LoRA verification collapses by default and remembers user choice', () => {
  assert.match(html, /<details id="image-lora-verification"[^>]*hidden><\/details>/);
  assert.match(image, /LORA_VERIFICATION_OPEN_KEY = 'morphorum\.image\.loraVerificationOpen\.v1'/);
  assert.match(image, /verification\.open = loraVerificationOpen\(\)/);
  assert.match(image, /verification\.addEventListener\('toggle'/);
  assert.match(image, /localStorage\.setItem\(LORA_VERIFICATION_OPEN_KEY, String\(verification\.open\)\)/);
  assert.match(image, /document\.createElement\('summary'\)/);
  assert.match(image, /panel\.replaceChildren\(title, list\)/);
});

test('empty Image preview contains no redundant navigation shortcuts', () => {
  const preview = html.match(/<div class="preview-placeholder" id="image-empty-preview">([\s\S]*?)<\/div>\s*<div class="image-gallery"/)?.[1] || '';
  assert.match(preview, /No images yet/);
  assert.doesNotMatch(preview, /data-jump="(?:settings|models)"/);
});

test('Motion Lab narrow-menu buttons inherit Morphorum theme instead of browser defaults', () => {
  const desktop = read('assets/desktop.css');
  assert.match(html, /id="motion-lab-sidebar"[^>]*hidden/);
  assert.match(css, /@media \(max-width: 1180px\), \(min-width: 1181px\) and \(pointer: coarse\)/);
  assert.match(css, /\.main-nav #motion-lab-sidebar > button\s*\{/);
  assert.match(css, /appearance: none;/);
  assert.match(css, /background: transparent;/);
  assert.match(css, /color: var\(--muted\);/);
  assert.match(css, /#motion-lab-sidebar > button\.active,/);
  assert.match(css, /#motion-lab-sidebar > button:focus-visible/);
  assert.match(css, /#motion-lab-sidebar:not\(\[hidden\]\)\s*\{/);
  assert.match(desktop, /\.main-nav\.motion-section-active #motion-lab-sidebar/);
});

test('touch popup selection closes both menus and updates aria-expanded', () => {
  const start = app.indexOf('  function closeTouchSubmenus() {');
  const end = app.indexOf('  function switchView(name) {', start);
  assert.ok(start >= 0 && end > start);
  const helper = app.slice(start, end);
  const nodes = {
    '#project-nav-submenu': {hidden:false},
    '#motion-lab-sidebar': {hidden:false},
    '#project-nav-toggle': {attributes:{}, setAttribute(name,value){this.attributes[name]=value;}},
    '#motion-nav-toggle': {attributes:{}, setAttribute(name,value){this.attributes[name]=value;}},
  };
  const build = match => Function('window','qs',helper+'; return closeTouchSubmenus;')(
    {matchMedia: query => {
      assert.match(query,/max-width: 1180px/);
      return {matches:match};
    }},
    selector => nodes[selector]
  );
  build(true)();
  assert.equal(nodes['#project-nav-submenu'].hidden,true);
  assert.equal(nodes['#motion-lab-sidebar'].hidden,true);
  assert.equal(nodes['#project-nav-toggle'].attributes['aria-expanded'],'false');
  assert.equal(nodes['#motion-nav-toggle'].attributes['aria-expanded'],'false');
  nodes['#project-nav-submenu'].hidden=false;
  nodes['#motion-lab-sidebar'].hidden=false;
  build(false)();
  assert.equal(nodes['#project-nav-submenu'].hidden,false, 'desktop sidebar must remain open');
  assert.equal(nodes['#motion-lab-sidebar'].hidden,false, 'desktop sidebar must remain open');
});

test('Project and Motion Lab destinations dismiss popups after changing tabs', () => {
  const project = app.match(/qsa\('\.main-nav \[data-project-nav\]'\)[\s\S]*?(?=qsa\('#motion-lab-sidebar \[data-motion-nav\]'\))/)?.[0] || '';
  const motion = app.match(/qsa\('#motion-lab-sidebar \[data-motion-nav\]'\)[\s\S]*?(?=const moreToggle)/)?.[0] || '';
  assert.match(project,/switchView\('animation'\)/);
  assert.match(project,/button\.dataset\.projectNav\)\?\.click\(\);\s*closeTouchSubmenus\(\)/);
  assert.match(motion,/button\.dataset\.motionNav\)\?\.click\(\);\s*closeTouchSubmenus\(\)/);
});
