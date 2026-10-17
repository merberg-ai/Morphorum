'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const root = path.join(__dirname, '..', 'frontend', 'dist');
const html = fs.readFileSync(path.join(root, 'index.html'), 'utf8');
const source = fs.readFileSync(path.join(root, 'assets', 'animation.js'), 'utf8');
const css = fs.readFileSync(path.join(root, 'assets', 'animation.css'), 'utf8');
const begin = source.indexOf('  let projectMediaGeneration = 0;');
const end = source.indexOf('  function sourceImageUrl() {', begin);
assert.ok(begin > 0 && end > begin, 'Project media implementation must be in animation.js');

function makeContext(project, api) {
  const nodes = new Map([
    ['#animation-media-status', { textContent: '' }],
    ['#animation-media-warnings', { textContent: '', hidden: true }],
  ]);
  const ctx = {
    state: { project },
    qs: selector => nodes.get(selector) || null,
    api, document: { activeElement: null },
    Audio: class {
      constructor(url) { this.src = url; this.preload = ''; }
      load() {} pause() {} removeAttribute() {}
    },
    renderSourceState() {}, motionLabReleaseAudio() {},
    motionLabAudioPreview() {}, motionLabAudioUi() {},
    motionLabAudioSyncStatus() {},
  };
  const program = `
    let motionDirectorDeleteSelection = new Set(), motionDirectorDeleteUndo = null;
    let animationTab = 'editor', motionLabSoundtrackBusy = false;
    async function motionLabUseProjectSoundtrack() {}
    let motionLabAudioAnalysis = null, motionLabAudioProjectId = null;
    let motionLabAudioElement = null, motionLabAudioUrl = null;
    async function motionStudioHydrateEdits() { return true; }
    function motionStudioRestoreChannels() {}
    let motionStudioChannelState = { projectId: '', sha: '', channels: [], dirty: false };
    function motionStudioRenderChannels() {}
    let motionStudioSpectrumToken = 0;
    let motionStudioSpectrum = {projectId:'',sha:'',points:[],maxHz:20000,loading:false,error:''};
    let motionStudioBandPreview = {projectId:'',sha:'',fps:0,frames:0,ranges:'',bands:null};
    let motionStudioSelectedChannel = '';
    function motionStudioConnectAudioTransport() {}
    function motionLabStereoWaveform() {}
    function motionDirectorPanel() {}
    ${source.slice(begin, end)}
    this.restoreProjectMedia = restoreProjectMedia;
    this.mediaState = () => projectMedia;
    this.audioState = () => ({ analysis: motionLabAudioAnalysis,
      projectId: motionLabAudioProjectId, url: motionLabAudioUrl });
  `;
  vm.runInNewContext(program, ctx);
  return { ctx, nodes };
}

const sha = 'a'.repeat(64);
const sourceImage = { kind: 'source_image', sha256: 'b'.repeat(64), url: '/image', filename: 'source.png' };
const wav = { kind: 'motion_lab_wav', sha256: sha, url: '/audio/' + sha, filename: sha + '.wav', bytes: 1048576 };
const soundtrack = { kind: 'soundtrack', sha256: 'c'.repeat(64), url: '/soundtrack', filename: 'song.mp3' };
const project = () => ({ id: 'my-project', animation: { source_image: 'assets/source.png',
  fps: 24, max_frames: 12 }, motion_lab: { layers: [{ type: 'audio', sha256: sha }] } });

test('one visible project media card owns the saved playback/offset controls', () => {
  for (const id of ['animation-project-media','animation-media-status',
    'animation-media-warnings','animation-media-soundtrack-player',
    'animation-media-offset','animation-media-offset-save',
    'animation-media-wav-select','animation-media-wav-player']) {
    assert.equal((html.match(new RegExp('id="' + id + '"', 'g')) || []).length, 1, id);
  }
  assert.match(css, /\.animation-project-media-card\s*\{\s*grid-column:\s*1 \/ -1/);
  assert.match(source, /void restoreProjectMedia\(\{ resetAudio: true \}\)/);
  assert.match(source, /projectMediaWarning\('Saved start image could not be decoded/);
});

test('project open restores image, soundtrack offset and stored WAV analysis', async () => {
  const calls = [];
  const { ctx, nodes } = makeContext(project(), async url => {
    calls.push(url);
    if (url.endsWith('/media-inventory')) return { assets: [sourceImage, soundtrack, wav], warnings: [] };
    if (url.endsWith('/motion-import/soundtrack')) return { soundtrack: { filename: 'song.mp3', offset_seconds: .35 } };
    if (url.endsWith('/analysis')) return { analysis: { source_sha256: sha,
      filename: wav.filename, fps: 24, values: Array(12).fill(0), duration_seconds: .5 } };
    throw Error('Unexpected URL: ' + url);
  });
  await ctx.restoreProjectMedia({ resetAudio: true });
  assert.deepEqual(calls, [
    '/api/animation/projects/my-project/media-inventory',
    '/api/animation/projects/my-project/motion-import/soundtrack',
    '/audio/' + sha + '/analysis',
  ]);
  assert.equal(ctx.mediaState().selectedWav, sha);
  assert.equal(ctx.mediaState().soundtrack.offset_seconds, .35);
  assert.equal(ctx.audioState().url, '/audio/' + sha);
  assert.equal(ctx.audioState().projectId, 'my-project');
  assert.equal(nodes.get('#animation-media-warnings').hidden, true);
});

test('missing media reports warnings but retains project and valid assets', async () => {
  const selected = project();
  const { ctx, nodes } = makeContext(selected, async url => {
    assert.ok(url.endsWith('/media-inventory'));
    return { assets: [], warnings: ['Saved start image is missing.', 'Audio track is missing.'] };
  });
  await ctx.restoreProjectMedia({ resetAudio: true });
  assert.equal(ctx.state.project, selected);
  assert.equal(ctx.mediaState().assets.length, 0);
  assert.equal(nodes.get('#animation-media-warnings').hidden, false);
  assert.match(nodes.get('#animation-media-warnings').textContent, /Saved start image is missing/);
  assert.equal(ctx.audioState().analysis, null);
});

test('a previous project response never overwrites a newly opened project', async () => {
  let completeFirst;
  const { ctx } = makeContext(project(), url => {
    if (url.includes('my-project')) return new Promise(resolve => { completeFirst = resolve; });
    return Promise.resolve({ assets: [wav], warnings: [] });
  });
  const first = ctx.restoreProjectMedia({ resetAudio: true });
  ctx.state.project = { id: 'second-project', animation: { fps: 24, max_frames: 12 }, motion_lab: { layers: [] } };
  const second = ctx.restoreProjectMedia({ resetAudio: true });
  completeFirst({ assets: [sourceImage], warnings: [] });
  await Promise.all([first, second]);
  assert.equal(ctx.mediaState().projectId, 'second-project');
  assert.equal(ctx.mediaState().assets[0].kind, 'motion_lab_wav');
});

test('bad reanalysis produces a visible warning instead of losing project state', async () => {
  const selected = project();
  const { ctx, nodes } = makeContext(selected, async url => {
    if (url.endsWith('/media-inventory')) return { assets: [wav], warnings: [] };
    throw Error('Stored WAV checksum mismatch');
  });
  await ctx.restoreProjectMedia({ resetAudio: true });
  assert.equal(ctx.state.project, selected);
  assert.equal(ctx.audioState().analysis, null);
  assert.match(nodes.get('#animation-media-warnings').textContent, /Could not restore saved Motion Lab WAV/);
});
