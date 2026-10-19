'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const root = path.join(__dirname, '..', 'frontend', 'dist');
const animation = fs.readFileSync(path.join(root, 'assets', 'animation.js'), 'utf8');
const html = fs.readFileSync(path.join(root, 'index.html'), 'utf8');
const css = fs.readFileSync(path.join(root, 'assets', 'animation.css'), 'utf8');

test('project manager has archive import available and export/save-as only with selected project', () => {
  for (const id of ['animation-project-manager-import', 'animation-project-manager-import-file',
                    'animation-project-manager-save-as', 'animation-project-manager-export']) {
    assert.ok(animation.includes(id), id + ' is missing');
  }
  assert.match(animation, /for \(const id of \['open', 'rename', 'save-as', 'export', 'trash'\]\)/);
  assert.match(animation, /const importButton = qs\('#animation-project-manager-import'\)/);
  assert.match(animation, /accept=".zip,application\/zip"/);
  assert.match(css, /\.animation-project-manager-archive-tools/);
});

test('manager export avoids unsaved draft and excludes rendering outputs', () => {
  const start = animation.indexOf('  async function projectManagerExport()');
  const end = animation.indexOf('  async function projectManagerSaveAs(', start);
  const code = animation.slice(start, end);
  assert.ok(start >= 0 && end > start);
  assert.match(code, /state\.dirty/);
  assert.match(code, /method|response\.blob\(\)/);
  assert.match(code, /\/archive/);
  assert.match(code, /Generated|Rendered/);
});

test('manager import inspects ZIP, asks for overwrite confirmation and then offers to load', () => {
  const start = animation.indexOf('  async function projectManagerImport(file)');
  const end = animation.indexOf('  async function projectManagerOpen()', start);
  const code = animation.slice(start, end);
  assert.ok(start >= 0 && end > start);
  assert.match(code, /\/archive\/inspect/);
  assert.match(code, /\/archive\/import/);
  assert.match(code, /MorphorumDialog\.prompt/);
  assert.match(code, /Enter the exact project name/);
  assert.match(code, /X-Morphorum-Overwrite/);
  assert.match(code, /Load imported project/);
  assert.match(code, /loadProject\(result\.project\.id\)/);
  assert.match(code, /resetRenderUi\(\)/);
});

test('Save Project As keeps separate identity and includes current editor draft', () => {
  assert.match(html, /id="animation-save-as"/);
  assert.match(animation, /'animation-save-as',/);
  assert.match(animation, /animation-save-as'\)\?\.addEventListener\('click'/);
  const start = animation.indexOf('  async function projectManagerSaveAs(');
  const end = animation.indexOf('  async function projectManagerImport(', start);
  const code = animation.slice(start, end);
  assert.ok(start >= 0 && end > start);
  assert.match(code, /MorphorumDialog\.prompt/);
  assert.match(code, /collectProject\(\)/);
  assert.match(code, /\/save-as/);
  assert.match(code, /loadProject\(result\.project\.id\)/);
});
