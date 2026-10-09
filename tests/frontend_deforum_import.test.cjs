'use strict';

const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const directory = path.join(__dirname, '..', 'frontend', 'dist');
const html = fs.readFileSync(path.join(directory, 'index.html'), 'utf8');
const script = fs.readFileSync(path.join(directory, 'assets', 'animation.js'), 'utf8');

test('B6.1 Deforum importer is browser-file based and preview-first', () => {
  for (const control of [
    'animation-import-deforum',
    'animation-deforum-file',
    'animation-deforum-dialog',
    'animation-deforum-name',
    'animation-deforum-model',
    'animation-deforum-summary',
    'animation-deforum-warnings',
    'animation-deforum-mappings',
    'animation-deforum-refresh',
    'animation-deforum-create',
  ]) {
    assert.equal((html.match(new RegExp('id="' + control + '"', 'g')) || []).length, 1);
  }

  assert.match(html, /id="animation-deforum-file"[^>]+type="file"/);
  assert.match(html, /accept="\.json,\.txt,application\/json,text\/plain"/);
  assert.ok(html.includes('Imported checkpoint paths are never trusted.'));
  assert.ok(script.includes('await file.text()'));
  assert.ok(script.includes("'/api/animation/import/deforum/preview'"));
  assert.ok(script.includes("'/api/animation/import/deforum/create'"));
  assert.ok(script.includes('!report?.can_create'));
});

test('B6.1 importer requires an indexed model and creates a distinct project', () => {
  const populateStart = script.indexOf('  function populateDeforumModelSelect() {');
  const previewStart = script.indexOf('  async function previewDeforumImport(');
  const createStart = script.indexOf('  async function createDeforumProject() {');
  const projectListStart = script.indexOf('  async function loadProjectList(', createStart);
  assert.ok(populateStart > 0 && previewStart > populateStart);
  assert.ok(createStart > previewStart && projectListStart > createStart);

  const populate = script.slice(populateStart, previewStart);
  const create = script.slice(createStart, projectListStart);
  const modelFilter = script.slice(
    script.indexOf('  function deforumCheckpointModels() {'),
    populateStart
  );
  assert.ok(modelFilter.includes("model.kind === 'checkpoints'"));
  assert.ok(populate.includes("none.value = ''"));
  assert.ok(create.includes("method: 'POST'"));
  assert.ok(create.includes('state.project = payload.project'));
  assert.ok(create.includes('await loadProjectList()'));
  assert.ok(create.includes('state.dirty'));
  assert.ok(create.includes('window.confirm'));
  assert.ok(!create.includes('model_path'));
});
