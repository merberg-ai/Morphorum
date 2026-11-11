'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const dist = path.join(__dirname, '..', 'frontend', 'dist');
const read = file => fs.readFileSync(path.join(dist, file), 'utf8');
const html = read('index.html');
const app = read('assets/app.js');
const animation = read('assets/animation.js');
const civitai = read('assets/civitai.js');
const shell = read('assets/shell.css');

const SIDEBAR = '@media (min-width: 1181px) and (hover: hover) and (pointer: fine)';
const RAIL = '@media (min-width: 641px) and (max-width: 1180px), (min-width: 1181px) and (pointer: coarse)';
const TABS = '@media (max-width: 640px)';

test('shell stylesheet loads last so it layers over the device stylesheets', () => {
  const links = [...html.matchAll(/<link rel="stylesheet" href="\/assets\/([a-z-]+)\.css/g)].map(m => m[1]);
  assert.equal(links.at(-1), 'shell');
  assert.equal(links.filter(name => name === 'shell').length, 1);
  for (const name of ['mobile', 'tablet', 'desktop']) assert.ok(links.includes(name), name);
});

test('one set of nav buttons serves the sidebar, rail and tab layouts', () => {
  for (const query of [SIDEBAR, RAIL, TABS]) assert.ok(shell.includes(query), query);
  // The script switches between popup and persistent menus at the same widths.
  assert.ok(app.includes("'(max-width: 1180px), (min-width: 1181px) and (pointer: coarse)'"));
  const rail = shell.slice(shell.indexOf(RAIL), shell.indexOf('@media (min-width: 641px) and (max-height: 560px)'));
  assert.match(rail, /grid-template-columns: var\(--rail-w\) minmax\(0, 1fr\)/);
  assert.match(rail, /\.nav-button > span:not\(\.nav-icon\) \{ display: none; \}/);
  assert.match(rail, /#motion-lab-sidebar:not\(\[hidden\]\) \{\s*position: absolute;\s*left: calc\(100% \+ 10px\)/);
  const tabs = shell.slice(shell.indexOf(TABS), shell.indexOf('/* ----------------------------------------------------------- page header'));
  assert.match(tabs, /\.app-shell > \.main-nav \{\s*left: 0;\s*right: 0;/);
  assert.match(tabs, /\[data-view="loras"\],\s*\.app-shell > \.main-nav > \.nav-button\[data-view="civitai"\] \{ display: none; \}/);
});

test('navigation is grouped and every button keeps a text label and tooltip', () => {
  const nav = html.match(/<nav class="main-nav glass"[\s\S]*?<\/nav>/)[0];
  assert.deepEqual([...nav.matchAll(/class="nav-group-label"[^>]*>([^<]+)</g)].map(m => m[1]),
    ['Create', 'Library', 'System']);
  const order = [...nav.matchAll(/<button class="nav-button[^"]*"[^>]*?(?:data-view="([a-z]+)"|id="(project-nav-toggle)")/g)]
    .map(m => m[1] || m[2]);
  assert.deepEqual(order, ['image', 'project-nav-toggle', 'animation', 'models', 'loras',
    'civitai', 'settings', 'console', 'help', 'about']);
  // Icon-only rail buttons still need a name for hover and assistive tech.
  for (const button of nav.matchAll(/<button class="nav-button[^>]*>/g)) {
    assert.match(button[0], / title="[^"]+"/, button[0]);
  }
  // Icons are drawn by CSS masks; the glyph stays as plain text in the markup.
  for (const view of ['image', 'animation', 'models', 'loras', 'civitai', 'settings', 'console', 'help', 'about']) {
    assert.ok(shell.includes('.main-nav [data-view="' + view + '"] { --nav-icon: url("data:image/svg+xml,'), view);
  }
  assert.match(shell, /\.main-nav #project-nav-toggle \{ --nav-icon:/);
});

test('Render pages are grouped at the end of the Motion Lab list', () => {
  const list = html.match(/<div class="motion-lab-sidebar"[\s\S]*?<\/div>/)[0];
  const order = [...list.matchAll(/data-motion-nav="([a-z-]+)"|class="(nav-sub-label)"/g)].map(m => m[1] || m[2]);
  assert.deepEqual(order, ['motion', 'audio', 'composer', 'recording', 'curves', 'motion-import',
    'nav-sub-label', 'preview', 'monitor', 'outputs']);
});

test('sidebar keeps the active section expanded; popup layouts are left alone', () => {
  const start = app.indexOf('  function sidebarNavLayout() {');
  const end = app.indexOf('  window.MorphorumNav = ', start);
  assert.ok(start > 0 && end > start);
  const node = active => ({
    hidden: true, attributes: {},
    classList: { contains: name => name === 'active' && active },
    setAttribute(name, value) { this.attributes[name] = value; },
  });
  const run = (popup, activeToggle) => {
    const nodes = {
      '#project-nav-submenu': node(false), '#project-nav-toggle': node(activeToggle === 'project'),
      '#motion-lab-sidebar': node(false), '#motion-nav-toggle': node(activeToggle === 'motion'),
    };
    Function('window', 'qs', 'POPUP_NAV_LAYOUT', app.slice(start, end) + '; syncNavSections();')(
      { matchMedia: () => ({ matches: popup }) }, selector => nodes[selector], 'query',
    );
    return nodes;
  };
  let nodes = run(false, 'motion');
  assert.equal(nodes['#motion-lab-sidebar'].hidden, false);
  assert.equal(nodes['#project-nav-submenu'].hidden, true);
  assert.equal(nodes['#motion-nav-toggle'].attributes['aria-expanded'], 'true');
  nodes = run(false, 'project');
  assert.equal(nodes['#project-nav-submenu'].hidden, false);
  assert.equal(nodes['#motion-lab-sidebar'].hidden, true);
  nodes = run(false, 'none');
  assert.equal(nodes['#project-nav-submenu'].hidden, true);
  assert.equal(nodes['#motion-lab-sidebar'].hidden, true);
  // Rail and tab layouts open these lists as popups on demand.
  nodes = run(true, 'motion');
  assert.equal(nodes['#motion-lab-sidebar'].hidden, true);
  assert.match(animation, /globalThis\.MorphorumNav\?\.syncSections\?\.\(\);/);
});

test('top bar names the open project and tucks the meters away on small screens', () => {
  const header = html.match(/<header class="topbar glass">[\s\S]*?<\/header>/)[0];
  assert.match(header, /id="topbar-project"[^>]*hidden/);
  assert.match(header, /id="topbar-project-state" data-save-state="empty"/);
  assert.match(header, /<button class="telemetry-toggle" id="telemetry-toggle" type="button" aria-expanded="false" aria-controls="telemetry-strip"/);
  assert.match(animation, /qs\('#topbar-project-state'\),/);
  assert.match(animation, /topbarProject\.hidden = !state\.project;/);
  assert.match(app, /qs\('\.topbar'\)\?\.classList\.toggle\('telemetry-open', open\);/);
  assert.match(shell, /\.app-shell > \.topbar\.telemetry-open \.telemetry-strip \{/);
  assert.match(shell, /\.topbar-project-state\[data-save-state="dirty"\]/);
});

test('project toolbar is Save plus a More menu holding every other action', () => {
  const toolbar = html.match(/<div class="button-row animation-project-actions">[\s\S]*?<\/div>\s*<\/div>/)[0];
  const direct = toolbar.slice(0, toolbar.indexOf('<div class="animation-toolbar-menu"'));
  assert.deepEqual([...direct.matchAll(/<button[^>]* id="([a-z-]+)"/g)].map(m => m[1]),
    ['animation-save', 'animation-toolbar-more']);
  const menu = toolbar.slice(toolbar.indexOf('<div class="animation-toolbar-menu"'));
  assert.match(menu, /id="animation-toolbar-menu" role="group" aria-label="More project actions" hidden/);
  for (const id of ['animation-save-as', 'animation-new', 'animation-reload', 'animation-import-deforum',
    'animation-deforum-file', 'animation-collapse-all', 'animation-expand-all']) {
    assert.equal((menu.match(new RegExp('id="' + id + '"', 'g')) || []).length, 1, id);
    assert.equal((html.match(new RegExp('id="' + id + '"', 'g')) || []).length, 1, id);
  }
  assert.match(app, /if \(event\.key !== 'Escape' \|\| !toolbarMenu \|\| toolbarMenu\.hidden\) return;/);
  assert.match(shell, /#view-animation \.animation-workspace-nav \{ display: none; \}/);
});

test('phone keeps Save reachable and reaches every destination from five tabs', () => {
  assert.match(shell, /#view-animation \.animation-project-actions \{\s*position: fixed;/);
  assert.match(shell, /body\.mobile-keyboard-open #view-animation \.animation-project-actions \{ display: none; \}/);
  const more = html.match(/<div class="nav-more-menu"[\s\S]*?<\/div>/)[0];
  assert.deepEqual([...more.matchAll(/data-more-view="([a-z]+)"/g)].map(m => m[1]),
    ['loras', 'civitai', 'settings', 'console', 'help', 'about']);
  assert.match(more, /data-more-view="civitai" id="civitai-more" hidden/);
  assert.match(app, /const MORE_MENU_VIEWS = \['loras', 'civitai', 'settings', 'console', 'help', 'about'\];/);
  assert.match(civitai, /const moreEntry = byId\('civitai-more'\);\s*if \(moreEntry\) moreEntry\.hidden = !state\.enabled;/);
});
