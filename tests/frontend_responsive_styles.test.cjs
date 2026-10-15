'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const dist = path.join(__dirname, '..', 'frontend', 'dist');
const read = name => fs.readFileSync(path.join(dist, name), 'utf8');
const html = read('index.html');
const shared = read('assets/app.css');
const phone = read('assets/mobile.css');
const tablet = read('assets/tablet.css');
const desktop = read('assets/desktop.css');

test('browser serves one document and shared behavior with three gated presentations', () => {
  const assets = [
    ['app.css', ''],
    ['mobile.css', ' media="(max-width: 640px)"'],
    ['models.css', ''],
    ['image.css', ''],
    ['animation.css', ''],
    ['tablet.css', ' media="(min-width: 641px) and (max-width: 1180px), (min-width: 1181px) and (pointer: coarse)"'],
    ['desktop.css', ' media="(min-width: 1181px) and (hover: hover) and (pointer: fine)"'],
  ];
  let previous = -1;
  for (const [name, media] of assets) {
    const tag = `href="/assets/${name}?v=__MORPHORUM_ASSET_VERSION__"${media}`;
    const index = html.indexOf(tag);
    assert.ok(index > previous, name + ' missing or stylesheet order changed');
    assert.equal(html.indexOf(tag, index + 1), -1, name + ' loaded twice');
    previous = index;
  }
  for (const script of ['ui-services.js','app.js','models.js','image.js','animation.js']) {
    const tag = `src="/assets/${script}?v=__MORPHORUM_ASSET_VERSION__"`;
    assert.equal(html.split(tag).length - 1, 1, script + ' must remain shared');
  }
});

test('phone application chrome is owned by mobile.css, not app.css', () => {
  assert.match(phone, /\.main-nav\s*\{\s*position:\s*fixed/);
  assert.match(phone, /\.topbar-right\s*\{display:contents;\}/);
  assert.match(phone, /\.nav-more-toggle\s*\{display:flex/);
  assert.match(phone, /body\.mobile-keyboard-open \.main-nav\s*\{display:none;/);
  assert.match(phone, /@media\s*\(max-width:\s*420px\)/);
  assert.match(shared, /#motion-lab-sidebar\s*\{\s*display:\s*none/);
  assert.match(shared, /\.topbar\s*\{[^}]*display:\s*grid/s);
  const phoneQueries = [...shared.matchAll(/@media\s*\(\s*max-width:\s*(\d+)px\s*\)/g)]
    .map(match => Number(match[1]));
  assert.ok(phoneQueries.every(width => width > 640),
    'no phone-specific top-level media queries should remain in app.css');
});

test('tablets have an intentionally distinct, keyboard-accessible, wrapping layout', () => {
  assert.match(tablet, /\.main-nav\s*\{[^}]*flex-wrap:\s*wrap/s);
  assert.match(tablet, /\.main-nav > \.nav-button\s*\{[^}]*min-height:\s*44px/s);
  assert.match(tablet, /\.main-nav > \.nav-button:focus-visible\s*\{/);
  assert.match(tablet, /@media \(max-width: 900px\)/);
  assert.match(tablet, /\.telemetry-strip\s*\{[^}]*grid-template-columns:\s*repeat\(4, minmax\(0, 1fr\)\)/s);
  assert.match(desktop, /grid-template-areas:\s*"top top"\s*"nav main"/);
  assert.match(desktop, /\.main-nav\s*\{[^}]*flex-direction:\s*column/s);
});

test('device layout logic does not fork API access or HTML on the backend', () => {
  const server = fs.readFileSync(path.join(__dirname, '..', 'backend', 'morphorum', 'app.py'), 'utf8');
  assert.match(server, /FRONTEND_INDEX = FRONTEND_DIR \/ "index.html"/);
  assert.match(server, /html = FRONTEND_INDEX\.read_text\(encoding="utf-8"\)/);
  assert.doesNotMatch(server, /request\.headers\.get\(["']user-agent["']\)/i);
  assert.match(read('assets/app.js'), /window\.matchMedia\('\(max-width: 640px\)'\)/);
});
