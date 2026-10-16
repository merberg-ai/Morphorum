'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const root = path.join(__dirname, '..');
const js = fs.readFileSync(path.join(root, 'frontend/dist/assets/animation.js'), 'utf8');
const css = fs.readFileSync(path.join(root, 'frontend/dist/assets/animation.css'), 'utf8');
const py = fs.readFileSync(path.join(root, 'backend/morphorum/motion_lab.py'), 'utf8');
const api = fs.readFileSync(path.join(root, 'backend/morphorum/app.py'), 'utf8');

test('MS3 offers independent Bass/Snare/Crash and custom channels in Motion Studio', () => {
  assert.match(js, /function motionStudioChannelDefaults\(/);
  for (const key of ["id:'bass'", "id:'snare'", "id:'crash'", "'custom-'"]) {
    assert.ok(js.includes(key), key);
  }
  assert.match(js, /function motionStudioCreateChannelCard\(/);
  assert.match(js, /motionStudioCreateChannelCard\(panels\.audio\)/);
  assert.match(js, /data-ms3-field="low_hz"/);
  assert.match(js, /data-ms3-field="high_hz"/);
  assert.match(js, /data-ms3-field="offset_frames"/);
  assert.match(js, /data-ms3-field="start_frame"/);
  assert.match(js, /data-ms3-field="end_frame"/);
});

test('MS3 stage, preview and apply share one native layer and never erase manual cues', () => {
  assert.match(js, /id: 'audio-channels-' \+ sha\.slice\(0, 16\)/);
  assert.match(js, /item\.type === 'audio_channels' && item\.sha256 === sha/);
  assert.match(js, /motionLabDraftLayers\[previous\] = layer/);
  assert.match(js, /motionLabDraftLayers\.push\(layer\)/);
  assert.match(js, /motionLabPreviewOrApply\(false, \{curvesOnly:true\}\)/);
  assert.match(js, /motionLabPreviewOrApply\(true\)/);
  assert.match(py, /if kind == "audio_channels"/);
  assert.match(py, /layer\["type"\] in \("audio_cues", "audio_channels"\)/);
});

test('MS3 channel analysis uses the checksum-verified project WAV', () => {
  assert.match(api, /@app\.post\("\/api\/animation\/projects\/\{project_id\}\/motion-lab\/audio\/\{sha256\}\/bands"\)/);
  assert.match(api, /data = motion_wav_path\(project_id, sha256\)\.read_bytes\(\)/);
  assert.match(js, /motionStudioBandCache/);
  assert.match(js, /analysis\.source_sha256/);
  assert.match(js, /motionStudioRestoreChannels\(id, analysis\)/);
  assert.match(js, /motionStudioRestoreChannels\(projectId, analysis\)/);
});

test('MS3 editor remains responsive without a separate browser implementation', () => {
  assert.match(css, /\.motion-studio-channel-fields/);
  assert.match(css, /@media\(max-width:640px\)/);
  assert.match(css, /@media\(max-width:390px\)/);
  assert.match(js, /motionStudioUpdateChannelButtons\(\)/);
});
