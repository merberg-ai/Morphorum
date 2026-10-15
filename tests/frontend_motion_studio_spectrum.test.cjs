'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const root = path.join(__dirname, '..');
const source = fs.readFileSync(path.join(root,'frontend/dist/assets/animation.js'),'utf8');
const css = fs.readFileSync(path.join(root,'frontend/dist/assets/animation.css'),'utf8');
const backend = fs.readFileSync(path.join(root,'backend/morphorum/app.py'),'utf8');
const spectrum = fs.readFileSync(path.join(root,'backend/morphorum/audio_channel_bands.py'),'utf8');
const from = source.indexOf('  let motionStudioSpectrum = {');
const to = source.indexOf('  function motionStudioChannelDefaults(analysis) {',from);
assert.ok(from >= 0 && to > from, 'MS3b helpers must be available before the channel editor');

function fake(id, api) {
  const sha = 'b'.repeat(64);
  const channel = {id:'bass',name:'Bass',low_hz:100,high_hz:300,threshold:.3};
  const ctx = {
    state:{project:{id,animation:{fps:24,max_frames:12}}},
    motionLabAudioProjectId:id,
    motionLabAudioAnalysis:{source_sha256:sha},
    motionStudioChannelState:{projectId:id,sha,channels:[channel],dirty:false},
    motionStudioBandCache:new Map(),
    motionStudioUpdateChannelButtons(){},
    qs(){return null;}, api,
  };
  vm.runInNewContext(source.slice(from,to) + `
    this.axis = motionStudioSpectrumX;
    this.frequency = motionStudioSpectrumFrequency;
    this.band = motionStudioSelectedBand;
    this.edit = motionStudioEditBandEdge;
    this.fetchSpectrum = motionStudioFetchSpectrum;
    this.spectrumSnapshot = () => motionStudioSpectrum;
  `,ctx);
  return {ctx,sha,channel};
}

const result = {
  analysis:{
    frequency_max_hz:4000,
    spectrum:Array.from({length:96},(_,i)=>({hz:20+i*40,level:i/96})),
  },
};

test('MS3b spectrum is exposed through an authenticated project-WAV API',()=>{
  assert.match(backend, /@app\.get\("\/api\/animation\/projects\/\{project_id\}\/motion-lab\/audio\/\{sha256\}\/spectrum"\)/);
  assert.match(backend, /motion_wav_path\(project_id, sha256\)\.read_bytes\(\)/);
  assert.match(spectrum, /def analyze_frequency_spectrum\(/);
  assert.match(spectrum, /samples = min\(48,/);
});

test('MS3b editor exposes touch, keyboard, selection and spectrum preview',()=>{
  for(const term of [
    'data-ms3-spectrum-svg','data-ms3-envelope-svg','data-ms3-edge',
    'data-ms3-select','data-ms3-inspect','motionStudioShowBandPreview',
    "spectrum.addEventListener('pointerdown'","spectrum.addEventListener('pointermove'",
    "spectrum.addEventListener('keydown'","data-ms3-refresh-spectrum",
  ]) assert.ok(source.includes(term),term);
  assert.match(css,/\[data-ms3-spectrum-svg\] \{/);
  assert.match(css,/touch-action:none/);
  assert.match(css,/\[data-ms3-spectrum-svg\]:focus-visible/);
});

test('MS3b frequency mapping is log scaled and edges remain bounded',async()=>{
  const {ctx,sha,channel} = fake('one',async url=>{
    assert.equal(url,'/api/animation/projects/one/motion-lab/audio/'+sha+'/spectrum');
    return result;
  });
  await ctx.fetchSpectrum('one',sha);
  assert.equal(ctx.spectrumSnapshot().points.length,96);
  assert.equal(Math.round(ctx.axis(20,4000)),34);
  assert.equal(Math.round(ctx.axis(4000,4000)),700);
  ctx.edit(500,'low');
  assert.equal(channel.low_hz,290);
  ctx.edit(200,'high');
  assert.equal(channel.high_hz,300);
  assert.equal(ctx.motionStudioChannelState.dirty,true);
  ctx.edit(10000,'high');
  assert.equal(channel.high_hz,4000);
});

test('stale project spectrum responses cannot overwrite a newer project',async()=>{
  let release;
  const old = new Promise(resolve=>{release=resolve;});
  const {ctx,sha} = fake('one',url=>url.includes('/one/') ? old : Promise.resolve(result));
  const first = ctx.fetchSpectrum('one',sha);
  ctx.state.project.id='two';
  ctx.motionLabAudioProjectId='two';
  ctx.motionStudioChannelState.projectId='two';
  const second = ctx.fetchSpectrum('two',sha);
  release(result);
  await Promise.all([first,second]);
  assert.equal(ctx.spectrumSnapshot().projectId,'two');
  assert.equal(ctx.spectrumSnapshot().points.length,96);
});
