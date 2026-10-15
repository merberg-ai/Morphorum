'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const root = path.join(__dirname, '..');
const source = fs.readFileSync(path.join(root, 'frontend/dist/assets/animation.js'), 'utf8');
const html = fs.readFileSync(path.join(root, 'frontend/dist/index.html'), 'utf8');
const css = fs.readFileSync(path.join(root, 'frontend/dist/assets/animation.css'), 'utf8');
const backend = fs.readFileSync(path.join(root, 'backend/morphorum/app.py'), 'utf8');
const implementation = fs.readFileSync(path.join(root, 'backend/morphorum/project_soundtrack_motion.py'), 'utf8');
const start = source.indexOf('  async function motionLabUseProjectSoundtrack() {');
const stop = source.indexOf('  async function motionLabAnalyzeAudio() {', start);
assert.ok(start > 0 && stop > start, 'Motion Studio must provide reuse handler');

const sha = 'e'.repeat(64);
function mock(onApi) {
  const events = [];
  const ctx = {
    state:{project:{id:'p-one',animation:{fps:24,max_frames:12}}},
    motionLabBusy:false,
    motionLabSoundtrackBusy:false,
    motionLabSoundtrackStatus:'',
    motionLabAudioProjectId:null,
    motionLabAudioAnalysis:null,
    projectAudioRestoreGeneration:0,
    projectMediaAssets:kind => kind === 'soundtrack' ? [{
      kind:'soundtrack',sha256:'c'.repeat(64),filename:'my-track.mp3',
    }] : [],
    animationMode:()=> '3d',
    renderProjectMedia(){events.push('render');},
    restoreProjectMedia:async({preferredWav})=>{
      events.push('restore:'+preferredWav);
      ctx.motionLabAudioProjectId = 'p-one';
      ctx.motionLabAudioAnalysis = {source_sha256:preferredWav};
    },
    api:onApi,
    qs:()=> null,
    toast:(...args)=>events.push('toast:'+args[0]),
  };
  vm.runInNewContext(source.slice(start,stop) +
    '\nthis.execute = motionLabUseProjectSoundtrack;', ctx);
  return {ctx,events};
}
const response = {
  status:'analyzed',asset:{sha256:sha},
  analysis:{source_sha256:sha},
  soundtrack:{filename:'my-track.mp3',format:'mp3',offset_seconds:.8},
  converted_to_pcm:true,
};

test('reuse button is attached to audio analyzer and responsive',()=>{
  assert.match(html,/id="animation-motion-lab-use-soundtrack"/);
  assert.match(html,/Use Saved Project Soundtrack/);
  assert.match(source,/motionLabUseProjectSoundtrack\(\)/);
  assert.match(css,/\.animation-motion-saved-soundtrack\s*\{/);
  assert.match(css,/@media\(max-width:640px\)/);
  assert.match(backend,/@app\.post\("\/api\/animation\/projects\/\{project_id\}\/motion-lab\/use-soundtrack"\)/);
  assert.match(implementation,/digest_file\(path, max_bytes=MAX_IMPORT_AUDIO_BYTES\)/);
});

test('saved soundtrack is analyzed directly by host and selected for project restore',async()=>{
  const calls=[];
  const {ctx,events}=mock(async(uri,options)=>{
    calls.push([uri,options.method]);
    return response;
  });
  await ctx.execute();
  assert.equal(calls.length,1);
  assert.deepEqual(calls[0],['/api/animation/projects/p-one/motion-lab/use-soundtrack','POST']);
  assert.ok(events.includes('restore:'+sha));
  assert.equal(ctx.motionLabAudioAnalysis.source_sha256,sha);
  assert.match(ctx.motionLabSoundtrackStatus,/my-track\.mp3/);
  assert.match(ctx.motionLabSoundtrackStatus,/converted to PCM/);
  assert.equal(ctx.motionLabSoundtrackBusy,false);
  assert.ok(events.includes('toast:Project soundtrack loaded'));
});

test('a project switch during conversion cannot restore obsolete WAV',async()=>{
  let release;
  const pending = new Promise(resolve=>{release=resolve;});
  const {ctx,events}=mock(()=>pending);
  const request=ctx.execute();
  ctx.state.project.id='p-two';
  release(response);
  await request;
  assert.ok(!events.includes('restore:'+sha));
  assert.equal(ctx.motionLabAudioProjectId,null);
});

test('failed analysis reports an actionable error and leaves existing audio alone',async()=>{
  const {ctx,events}=mock(async()=>{throw Error('Install FFmpeg on the Morphorum host');});
  ctx.motionLabAudioProjectId='p-one';
  ctx.motionLabAudioAnalysis={source_sha256:'d'.repeat(64)};
  await ctx.execute();
  assert.equal(ctx.motionLabAudioAnalysis.source_sha256,'d'.repeat(64));
  assert.match(ctx.motionLabSoundtrackStatus,/Install FFmpeg/);
  assert.ok(events.includes('toast:Project soundtrack unavailable'));
});
