'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const root = path.join(__dirname, '..', 'frontend', 'dist');
const app = fs.readFileSync(path.join(root, 'assets', 'app.js'), 'utf8');
const css = fs.readFileSync(path.join(root, 'assets', 'app.css'), 'utf8');
const motionCss = fs.readFileSync(path.join(root, 'assets', 'animation.css'), 'utf8');
const otherCss = ['models.css','image.css','mobile.css','tablet.css','desktop.css']
  .map(n => fs.readFileSync(path.join(root,'assets',n),'utf8'));
const choices = ['midnight-glass','deep-ocean','amethyst-night','slate-graphite'];

test('Appearance settings advertise four themed palettes and working font choices', () => {
  for (const id of choices) {
    assert.match(app, new RegExp("'"+id+"'"));
    if (id !== 'midnight-glass') {
      assert.match(css, new RegExp('html\\[data-theme="'+id+'"\\]\\s*\\{'));
      const block = css.split('html[data-theme="'+id+'"] {')[1].split('}')[0];
      for (const key of ['bg','panel','panel-strong','border','text','muted',
        'accent','accent-2','ok','warn','danger','button-primary-text'])
        assert.ok(block.includes('--'+key+':'), id+' missing '+key);
    }
  }
  for (const kind of ['modern','humanist','geometric','technical'])
    assert.match(css, new RegExp('html\\[data-font-style="'+kind+'"\\]'));
  for (const kind of ['modern-mono','cascadia','classic-mono','compact-mono'])
    assert.match(css, new RegExp('html\\[data-mono-style="'+kind+'"\\]'));
  assert.match(app, /root\.dataset\.theme = theme/);
  assert.match(app, /root\.dataset\.fontStyle = fontStyle/);
  assert.match(app, /root\.dataset\.monoStyle = monoStyle/);
  assert.match(app, /root\.dataset\.uiScale = uiScale/);
});

test('Selecting a theme and fonts updates live document and remembered state', () => {
  const start = app.indexOf('  function applyAppearance(ui = {}) {');
  const end = app.indexOf('  function ensurePreferences() {', start);
  assert.ok(start > 0 && end > start);
  const storage = new Map();
  const documentRoot = {dataset:{}};
  const meta = {setAttribute(key, value) { this[key] = value; }};
  const context = {
    THEME_OPTIONS: choices.map(x => [x,x]),
    UI_FONT_FACES: {modern:'Inter',humanist:'Source Sans 3',
      geometric:'Space Grotesk',technical:'IBM Plex Sans Condensed'},
    MONO_FONT_FACES: {'modern-mono':'JetBrains Mono',cascadia:'Cascadia Code',
      'classic-mono':'IBM Plex Mono','compact-mono':'Roboto Mono'},
    UI_SCALE_OPTIONS: [['compact','Compact'],['standard','Standard'],
      ['comfortable','Comfortable']],
    document: {documentElement:documentRoot},
    localStorage: {setItem:(key, val)=>storage.set(key,val)},
    requestAnimationFrame:fn=>fn(),
    getComputedStyle:()=>({getPropertyValue:()=> ' #121824 '}),
    qs:selector=>selector==='meta[name="theme-color"]'?meta:null,
    updateAppearanceDiagnostic:()=>{},
  };
  vm.runInNewContext(app.slice(start,end)+'\nthis.applyAppearance=applyAppearance;', context);
  for (const theme of choices) {
    context.applyAppearance({theme,font_style:'geometric',mono_font_style:'classic-mono',
      ui_scale:'comfortable'});
    assert.equal(documentRoot.dataset.theme,theme);
    assert.equal(documentRoot.dataset.fontStyle,'geometric');
    assert.equal(documentRoot.dataset.monoStyle,'classic-mono');
    assert.equal(documentRoot.dataset.uiScale,'comfortable');
    assert.equal(storage.get('morphorum.ui.theme'),theme);
    assert.equal(storage.get('morphorum.ui.fontStyle'),'geometric');
    assert.equal(storage.get('morphorum.ui.monoStyle'),'classic-mono');
    assert.equal(meta.content,'#121824');
  }
  context.applyAppearance({theme:'unknown',font_style:'unknown',
    mono_font_style:'unknown',ui_scale:'tiny'});
  assert.equal(documentRoot.dataset.theme,'midnight-glass');
  assert.equal(documentRoot.dataset.fontStyle,'modern');
  assert.equal(documentRoot.dataset.monoStyle,'modern-mono');
  assert.equal(documentRoot.dataset.uiScale,'compact');
});

test('Fonts cover native controls, code, graphics and dialogs', () => {
  assert.match(css, /body\s*\{[^}]*font-family: var\(--font-ui\);/);
  assert.match(css, /button, input, select, textarea, dialog, option, optgroup,/);
  assert.match(css, /\[role="dialog"\], \[contenteditable="true"\]\s*\{\s*font-family: var\(--font-ui\);/);
  assert.match(css, /pre, code, kbd, samp \{ font-family: var\(--font-mono\); \}/);
  assert.match(css, /svg text \{ font-family: var\(--font-ui\); \}/);
  for (const control of ['checkbox','radio','range'])
    assert.match(css, new RegExp('input\\[type="'+control+'"\\]'));
  assert.match(css, /input::file-selector-button/);
  assert.match(css, /font-family: var\(--font-ui\)/);
  assert.match(css, /font-family: var\(--font-mono\)/);
  assert.match(app, /document\.fonts\.load/);
});

test('No stale original cyan accent tint remains in major CSS bundles', () => {
  for (const sheet of [css,motionCss,...otherCss]) {
    assert.doesNotMatch(sheet,/rgba\(\s*65\s*,\s*217\s*,\s*255\s*,/i);
    assert.doesNotMatch(sheet,/rgba\(\s*164\s*,\s*108\s*,\s*255\s*,/i);
  }
  assert.match(css, /--button-primary-bg:\s*linear-gradient\(135deg,var\(--accent\)/);
  assert.match(css, /--button-secondary-hover:\s*color-mix\(in srgb,var\(--accent\)/);
  assert.match(motionCss, /var\(--accent\)/);
});
