'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const root = path.join(__dirname, '..', 'frontend', 'dist');
const read = file => fs.readFileSync(path.join(root,file),'utf8');

test('context help uses accessible real button triggers outside labels', () => {
  const js = read('assets/ui-services.js');
  const html = read('index.html');
  const css = read('assets/app.css');
  for (const key of ['animation-model','animation-cadence','animation-strength',
    'animation-guidance','animation-3d-translation-z','animation-3d-rotation-y',
    'animation-3d-fov','animation-motion-lab-strength']) {
    assert.match(html, new RegExp('data-help-topic="' + key + '"'));
    assert.match(js, new RegExp('"' + key + '":'));
  }
  assert.match(js, /function addHelpButton\(label\)/);
  assert.match(js, /wrapper\.append\(label, button\)/);
  assert.match(js, /label\.classList\.remove\('animation-span-2'\)/);
  assert.match(js, /'role', 'tooltip'/);
  assert.match(js, /'aria-label', 'Help: '/);
  assert.match(js, /'aria-describedby', HELP_PANEL_ID/);
  assert.match(js, /event\.key === 'Escape'/);
  assert.match(js, /event\.pointerType === 'mouse'/);
  assert.match(js, /window\.MorphorumHelp =/);
  assert.match(css, /html\[data-help-hints="off"\]/);
  assert.match(css, /@media \(pointer:coarse\)/);
});

test('help toggle is surfaced in Appearance and included in settings persistence', () => {
  const app = read('assets/app.js');
  assert.match(app, /function createHelpPreferencesCard\(\)/);
  assert.match(app, /input\.id = 'ui-show-help-hints'/);
  assert.match(app, /state\.settings\.ui\.show_help_hints = input\.checked/);
  assert.match(app, /show_help_hints: state\.settings\.ui\.show_help_hints !== false/);
  assert.equal((app.match(/window\.MorphorumHelp\?\.setEnabled\(state\.settings\.ui\.show_help_hints\)/g)||[]).length, 2);
  assert.match(app, /panes\.appearance\.appendChild\(createHelpPreferencesCard\(\)\)/);
});
