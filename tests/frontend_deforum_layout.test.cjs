'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const base = path.join(__dirname, '..', 'frontend', 'dist');
const css = fs.readFileSync(path.join(base, 'assets', 'animation.css'), 'utf8');
const html = fs.readFileSync(path.join(base, 'index.html'), 'utf8');
test('import popup uses a single scroll container and static action footer', () => {
  const patch = css.slice(css.indexOf('/* B6.1.1:'));
  assert.ok(patch.includes('dialog#animation-deforum-dialog'));
  assert.match(patch, /\.animation-import-shell \{[\s\S]*?overflow: visible/);
  assert.match(patch, /\.animation-import-actions \{[\s\S]*?position: static/);
  assert.match(patch, /\.animation-import-mapping code \{[\s\S]*?word-break: break-word/);
  assert.ok(html.includes('aria-labelledby="animation-deforum-title"'));
});
