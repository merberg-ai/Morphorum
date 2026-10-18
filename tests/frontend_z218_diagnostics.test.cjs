'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const base = path.join(__dirname, '..', 'frontend', 'dist');
const html = fs.readFileSync(path.join(base, 'index.html'), 'utf8');
const js = fs.readFileSync(path.join(base, 'assets', 'diagnostics.js'), 'utf8');
const css = fs.readFileSync(path.join(base, 'assets', 'app.css'), 'utf8');
const mobile = fs.readFileSync(path.join(base, 'assets', 'mobile.css'), 'utf8');

test('Console preserves logs and adds a separately gated diagnostics tab', () => {
  for (const id of ['console-panel-logs', 'console-panel-diagnostics',
    'console-tab-logs', 'console-tab-diagnostics', 'console-window', 'level-filters',
    'diagnostic-model-select', 'diagnostic-section', 'diagnostic-status',
    'diagnostic-search', 'diagnostic-results', 'diagnostic-copy-json',
    'diagnostic-copy-filtered', 'diagnostic-refresh']) {
    assert.ok(html.includes('id="' + id + '"'), id);
  }
  assert.match(html, /id="console-panel-diagnostics"[^>]+hidden/);
  assert.equal(html.split('src="/assets/diagnostics.js?').length - 1, 1);
  assert.ok(html.indexOf('src="/assets/app.js?') < html.indexOf('src="/assets/diagnostics.js?'));
});

test('diagnostics fetches only same-origin indexed checkpoint endpoints', () => {
  assert.match(js, /fetch\('\/api\/models\?limit=2000'/);
  assert.match(js, /m\.family === 'zimage' && m\.source !== 'managed' && m\.kind === 'checkpoints'/);
  assert.match(js, /encodeURIComponent\(model\)/);
  assert.match(js, /zimage-diagnostics/);
  assert.doesNotMatch(js, /192\.168\.|https?:\/\/[^\s'"]+\/api\/models/);
  assert.doesNotMatch(js, /\/api\/generation|\/api\/models\/load|\/api\/convert/);
});

test('diagnostics renders server values as text, filters and limits DOM rows', () => {
  assert.match(js, /textContent = String\(value \?\? ''\)/);
  assert.doesNotMatch(js, /innerHTML/);
  assert.match(js, /const LIMIT = 350/);
  assert.match(js, /state\.filtered = state\.leaves\.filter/);
  assert.match(js, /navigator\.clipboard\.writeText/);
  assert.match(js, /row\.section === section/);
  assert.match(js, /row\.kind === status/);
});

test('diagnostic glass panel has responsive layout in phone stylesheet', () => {
  assert.match(css, /\.console-inner-tabs/);
  assert.match(css, /\.diagnostic-summary/);
  assert.match(mobile, /\.diagnostic-controls/);
  assert.match(mobile, /\.diagnostic-result-row/);
  assert.doesNotMatch(css, /@media\s*\(max-width:600px\)/);
});
