'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const root = path.join(__dirname,'..');
const read = p => fs.readFileSync(path.join(root,p),'utf8');
const app = read('frontend/dist/assets/app.js');
const animation = read('frontend/dist/assets/animation.js');
const css = read('frontend/dist/assets/app.css');
const backend = read('backend/morphorum/app.py');
const video = read('backend/morphorum/animation_video.py');
const source = read('backend/morphorum/animation_hybrid_source.py');
const extraction = read('backend/morphorum/animation_hybrid_extract.py');
const soundtrack = read('backend/morphorum/project_soundtrack_motion.py');
const config = read('config/default.yaml');
const settings = read('backend/morphorum/settings.py');
const resolver = read('backend/morphorum/ffmpeg_tools.py');

test('P4.4 normalizes persisted FFmpeg preferences and validates saves',()=>{
  assert.match(config,/tools:\s*\n\s+ffmpeg:\s*\n\s+mode: auto/);
  assert.match(settings,/normalize_ffmpeg_settings\(tools\.get\("ffmpeg"\)\)/);
  assert.match(settings,/normalize_ffmpeg_settings\(tools_update\["ffmpeg"\], strict=True\)/);
  assert.match(resolver,/MODES = \("auto", "custom", "managed"\)/);
  assert.match(resolver,/source = "environment"/);
  assert.match(resolver,/source = "system"/);
  assert.match(resolver,/MANAGED_BIN = ROOT \/ "tools" \/ "ffmpeg" \/ "current" \/ "bin"/);
});

test('P4.4 backend status and unsaved check endpoints are read-only',()=>{
  assert.match(backend,/@app\.get\("\/api\/tools\/ffmpeg\/status"\)/);
  assert.match(backend,/@app\.post\("\/api\/tools\/ffmpeg\/check"\)/);
  assert.match(backend,/normalize_ffmpeg_settings\(payload, strict=True\)/);
  assert.match(backend,/return ffmpeg_status\(\{"tools": \{"ffmpeg": config\}\}\)/);
  assert.match(resolver,/subprocess\.run\(\s*\n\s*\[path, "-version"\]/);
  assert.match(resolver,/timeout=VERSION_TIMEOUT, check=False/);
  assert.doesNotMatch(resolver,/shell=True/);
});

test('P4.4 all FFmpeg consumers resolve via the central module',()=>{
  assert.match(video,/from \.ffmpeg_tools import ffmpeg_executable/);
  assert.match(video,/from \.ffmpeg_tools import ffmpeg_status/);
  assert.match(source,/from \.ffmpeg_tools import ffmpeg_executable, ffprobe_executable/);
  assert.match(source,/executable = ffprobe_executable\(\)/);
  assert.match(extraction,/from \.ffmpeg_tools import ffmpeg_executable/);
  assert.match(soundtrack,/from \.ffmpeg_tools import ffmpeg_executable/);
  assert.match(resolver,/if not ffprobe and mode == "auto":/);
  assert.match(resolver,/ffprobe = shutil\.which\("ffprobe"\)/);
  assert.match(resolver,/elif mode == "managed":/);
});

test('P4.4 Settings includes all three source choices and explicit test action',()=>{
  for(const choice of [
    "['auto','Auto-detect from host PATH",
    "['custom','Custom installed executable']",
    "['managed','Morphorum-managed local FFmpeg']",
  ])assert.ok(app.includes(choice),choice);
  assert.match(app,/panes\.storage\.appendChild\(createFFmpegManagerCard\(\)\)/);
  assert.match(app,/id = 'ffmpeg-manager-check'/);
  assert.match(app,/api\('\/api\/tools\/ffmpeg\/check'/);
  assert.match(app,/window\.MorphorumOperations\?\.begin\(\s*\n\s*'ffmpeg-check'/);
  assert.match(app,/tools: \{ffmpeg: \{/);
  assert.match(app,/void checkFFmpegSettings\(\{quiet: true\}\)/);
  assert.match(app,/state\.ffmpegRequestId/);
  assert.match(app,/markSettingsDirty\(\)/);
});

test('P4.4 preserves responsive layout and video availability refresh',()=>{
  assert.match(css,/ffmpeg-manager-card/);
  assert.match(css,/ffmpeg-manager-details/);
  assert.match(css,/overflow-wrap:anywhere/);
  assert.match(animation,/async function refreshVideoAvailability\(\)/);
  assert.match(animation,/morphorum:settings-changed/);
  assert.match(animation,/void refreshVideoAvailability\(\)/);
  assert.match(animation,/api\('\/api\/animation\/video\/availability'\)/);
});
