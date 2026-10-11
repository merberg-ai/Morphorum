'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const js = fs.readFileSync(path.join(__dirname, '..', 'frontend', 'dist', 'assets', 'animation.js'), 'utf8');
const css = fs.readFileSync(path.join(__dirname, '..', 'frontend', 'dist', 'assets', 'animation.css'), 'utf8');

test('DA2 waveform transport follows audio clock and does not use an independent timer', () => {
  assert.match(js, /function motionLabWavePlayhead\(/);
  assert.match(js, /audio\.currentTime/);
  assert.match(js, /\['timeupdate', 'play', 'pause', 'seeked', 'ended'\]/);
  assert.match(js, /motionLabAudioElement\.addEventListener\(type, motionLabWavePlayhead\)/);
  assert.match(js, /data-wave-playhead/);
});
test('DA2 pointer and keyboard waveform seeking use visible time window', () => {
  assert.match(js, /data-wave-svg[^\n]*addEventListener\('click'/);
  assert.match(js, /data-wave-svg[^\n]*addEventListener\('keydown'/);
  assert.match(js, /section\.dataset\.waveStart/);
  assert.match(js, /section\.dataset\.waveEnd/);
  assert.match(js, /begin \+ Math\.max\(0, Math\.min\(1, ratio\)\)/);
});
test('DA2 waveform transport is scoped and responsive', () => {
  assert.match(css, /#animation-panel-audio \.animation-audio-wave-transport/);
  assert.match(css, /\[data-wave-svg\]:focus-visible/);
  assert.match(js, /data-wave-time/);
  assert.match(js, /data-wave-play/);
});
