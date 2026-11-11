'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const dist = path.join(__dirname, '..', 'frontend', 'dist');
const read = file => fs.readFileSync(path.join(dist, file), 'utf8');
const app = read('assets/app.js');
const animation = read('assets/animation.js');
const html = read('index.html');
const css = ['app.css', 'animation.css', 'desktop.css', 'image.css'].map(n => read('assets/' + n));

function classList() {
  const names = new Set();
  return {
    toggle(name, on) { if (on) names.add(name); else names.delete(name); },
    remove(name) { names.delete(name); },
    contains: name => names.has(name),
  };
}
function node(dataset = {}) {
  return { dataset, classList: classList(), removeAttribute() {}, setAttribute() {} };
}

function harness(openTab) {
  const start = app.indexOf('  function switchView(name) {');
  // Up to the next declaration: independent of LF or CRLF checkouts.
  const end = app.search(/\n\s*\n\s*(?:async )?function /g) < 0
    ? -1 : start + app.slice(start + 10).search(/\r?\n\r?\n\s*(?:async )?function /) + 10;
  assert.ok(start > 0 && end > start);
  const buttons = ['image', 'animation', 'models', 'settings'].map(view => node({ view }));
  const projectToggle = node();
  const activeTab = openTab ? node({ animationTab: openTab }) : null;
  const single = {
    '#project-nav-toggle': projectToggle,
    '.main-nav': node(),
    '.main-nav .nav-button[data-view="animation"]': buttons[1],
    '#animation-workspace-nav [data-animation-tab].active': activeTab,
  };
  const many = { '.nav-button': buttons, '.main-nav [data-project-nav]': [], '.view': [] };
  const switchView = Function(
    'qs', 'qsa', 'refreshNavMore', 'renderConsole', 'window', 'history', 'PROJECT_WORKSPACE_TABS',
    app.slice(start, end) + '; return switchView;',
  )(
    selector => single[selector] ?? null, selector => many[selector] || [],
    () => {}, () => {}, {}, { replaceState() {} },
    ['wizard', 'projects', 'editor', 'prompt-studio'],
  );
  const active = () => [
    ...buttons.filter(b => b.classList.contains('active')).map(b => b.dataset.view),
    ...(projectToggle.classList.contains('active') ? ['project'] : []),
  ];
  return { switchView, active };
}

test('exactly one main-menu section is highlighted for every destination', () => {
  for (const [view, tab, expected] of [
    ['image', 'audio', ['image']],
    ['image', 'editor', ['image']],
    ['animation', 'audio', ['animation']],
    ['animation', 'motion', ['animation']],
    ['animation', 'editor', ['project']],
    ['animation', 'prompt-studio', ['project']],
    ['animation', '', ['animation']],
    ['settings', 'editor', ['settings']],
  ]) {
    const h = harness(tab);
    h.switchView(view);
    assert.deepEqual(h.active(), expected, view + ' with tab ' + (tab || 'none'));
  }
});

test('workspace tab changes only highlight the menu while the view is showing', () => {
  assert.match(animation, /const viewActive = Boolean\(qs\('#view-animation'\)\?\.classList\.contains\('active'\)\);/);
  assert.match(animation, /\.classList\.toggle\('active', viewActive && !projectDestination\)/);
  assert.match(animation, /qs\('#project-nav-toggle'\)\?\.classList\.toggle\('active', viewActive && projectDestination\)/);
  assert.match(animation, /const selected = viewActive && button\.dataset\.projectNav === name;/);
});

test('unselected workspace tabs never look selected', () => {
  for (const sheet of css) {
    assert.doesNotMatch(sheet, /data-animation-tab="(?:motion|audio)"\]:not\(\.active\)/);
  }
});

test('Motion Studio shows one step navigator and counts its real stages', () => {
  assert.doesNotMatch(animation, /class="animation-audio-workflow"/);
  assert.match(animation, /' OF ' \+ MOTION_STUDIO_STAGES\.length \+ '<\/p>'/);
  assert.doesNotMatch(animation, /OF 5<\/p>/);
});

test('controls share one height scale and mixed rows use one size', () => {
  const [base, animationCss, , imageCss] = css;
  assert.match(base, /--control-h: 42px;/);
  assert.match(base, /--control-h-compact: 34px;/);
  assert.match(base, /\.primary-button, \.secondary-button, \.icon-button \{[^}]*min-height: var\(--control-h\);/);
  assert.match(base, /input, select \{ min-height: var\(--control-h\);/);
  assert.match(base, /\.compact \{ min-height: var\(--control-h-compact\);/);
  assert.match(animationCss, /\.animation-project-actions button \{ min-height: var\(--control-h-compact\);/);
  assert.match(imageCss, /\.image-history-controls button \{ min-height:var\(--control-h\); \}/);
  // Buttons that sit beside full-height fields are full height themselves.
  assert.match(html, /<button id="image-insert-lora" class="secondary-button" /);
  assert.match(html, /<button class="secondary-button" id="reopen-first-run-setup" /);
});
