'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const root = path.join(__dirname,'..','frontend','dist');
const js = fs.readFileSync(path.join(root,'assets','animation.js'),'utf8');
const css = fs.readFileSync(path.join(root,'assets','animation.css'),'utf8');

function grab(start,end) {
  const a=js.indexOf('  '+start);
  const b=js.indexOf('  '+end,a);
  assert.ok(a>=0 && b>a, start+'/' + end);
  return js.slice(a,b);
}
const analyzer=grab('async function motionLabAnalyzeAudio() {','function motionLabAddAudio() {');
const preview=grab('function motionLabAudioPreview() {','function motionLabAudioUi() {');

function mockAnalyzer({file={name:'drums.wav',size:8192}, project=true, http=200}={}) {
  const elements={};
  const get=id=>elements[id] ||= {textContent:'',value:'.1',disabled:false,dataset:{},checked:false};
  get('#animation-motion-lab-audio-file').files=file?[file]:[];
  get('#animation-motion-lab-audio-match-length').checked=false;
  const cues=[];
  const analysis={
    values:[.2,.4,.7,.3],duration_seconds:1,fps:4,
    filename:'drums.wav',source_sha256:'a'.repeat(64),
    events:{events:[{id:'beat-1'},{id:'beat-2'}]},
  };
  const ctx={
    state:{project:project?{id:'p1',animation:{max_frames:4,fps:4}}:null},
    motionLabAudioProjectId:null,motionLabAudioAnalysis:null,
    projectAudioRestoreGeneration:0,motionLabEditedEvents:null,motionDirectorCues:[],
    motionStudioChannelState:null,motionStudioSpectrumToken:0,
    motionStudioSpectrum:null,motionStudioBandPreview:null,
    motionStudioSelectedChannel:'',motionLabAudioUrl:null,
    motionLabAudioElement:null,
    qs:get,animationMode:()=>'3d',motionLabNotify:m=>cues.push(m),
    motionStudioRenderChannels(){},motionLabReleaseAudio(){},
    motionLabAudioPreview(){},motionLabAudioUi(){},
    motionStudioRestoreChannels(){},motionStudioConnectAudioTransport(){},
    motionLabAudioSyncStatus(){},motionLabStereoWaveform(){},
    motionDirectorPanel(){},restoreProjectMedia:async()=>{},
    motionStudioRefreshStageStatus(){},
    motionStudioHydrateEdits:async(_p,_a,current)=>current(),
    motionLabAudioSignal:()=>analysis.values,
    URL:{createObjectURL:()=>'/test-audio'},
    Audio:class {load(){}},
    fetch:async()=>({
      ok:http===200,status:http,
      json:async()=>http===200?{analysis}:{detail:'This is not PCM WAV.'},
    }),
  };
  vm.runInNewContext(analyzer,ctx);
  return {ctx,analysis,elements,get,cues};
}

test('UX2.1 valid WAV reaches backend and shows real completed analysis and beat count',async()=>{
  const f=mockAnalyzer();
  await f.ctx.motionLabAnalyzeAudio();
  assert.match(f.get('#motion-studio-analysis-status').textContent,/Analyzed drums.wav/);
  assert.match(f.get('#motion-studio-analysis-status').textContent,/2 beat candidate/);
  assert.equal(f.ctx.motionLabAudioProjectId,'p1');
  assert.ok(f.ctx.motionLabAudioAnalysis);
  assert.equal(f.get('#motion-studio-analysis-status').dataset.busy,undefined);
  assert.equal(f.cues.length,0);
});

test('UX2.1 malformed WAV reports server rejection visibly in Analyze stage',async()=>{
  const f=mockAnalyzer({http:400});
  await f.ctx.motionLabAnalyzeAudio();
  assert.match(f.get('#motion-studio-analysis-status').textContent,/This is not PCM WAV/);
  assert.equal(f.ctx.motionLabAudioAnalysis,null);
  assert.equal(f.get('#motion-studio-analysis-status').dataset.busy,undefined);
});

test('UX2.1 saved analyzed WAV without browser file does not silently reset source',async()=>{
  const f=mockAnalyzer({file:null});
  f.ctx.motionLabAudioProjectId='p1';
  f.ctx.motionLabAudioAnalysis=f.analysis;
  await f.ctx.motionLabAnalyzeAudio();
  assert.match(f.get('#motion-studio-analysis-status').textContent,/already analyzed/);
  assert.strictEqual(f.ctx.motionLabAudioAnalysis,f.analysis);
});

test('UX2.1 no selected WAV gives a visible next action, not a silent noop',async()=>{
  const f=mockAnalyzer({file:null});
  await f.ctx.motionLabAnalyzeAudio();
  assert.match(f.get('#motion-studio-analysis-status').textContent,/No local WAV selected/);
  assert.equal(f.cues.length,0);
});

test('UX2.1 no open project tells the user why Analyze cannot run',async()=>{
  const f=mockAnalyzer({project:false});
  await f.ctx.motionLabAnalyzeAudio();
  assert.match(f.get('#motion-studio-analysis-status').textContent,/Open a 3D project/);
});

test('UX2.1 envelope diagnostics give a reason before analysis and on misalignment',()=>{
  const status={textContent:''};
  const graph={replaceChildren(){},appendChild(){}};
  const pane={hidden:false};
  const ctx={
    qs:s=>s==='#animation-motion-lab-audio-preview'?pane:
      s==='#animation-motion-lab-audio-plot'?graph:
      s==='#motion-studio-envelope-message'?status:null,
    state:{project:{id:'p1',animation:{fps:4,max_frames:4}}},
    motionLabAudioProjectId:null,motionLabAudioAnalysis:null,
  };
  vm.runInNewContext(preview,ctx);
  ctx.motionLabAudioPreview();
  assert.equal(pane.hidden,true);
  assert.match(status.textContent,/No envelope available yet/);
  ctx.motionLabAudioProjectId='p1';
  ctx.motionLabAudioAnalysis={fps:4,values:[1]};
  ctx.motionLabAudioPreview();
  assert.match(status.textContent,/frame alignment changed/);
});

test('UX2.1 aligned audio renders the envelope graph and reports readiness',()=>{
  const diagnostics={textContent:''};
  const graph={
    children:[],
    replaceChildren(){this.children=[];},
    appendChild(node){this.children.push(node);},
  };
  const pane={hidden:true};
  const summary={textContent:''};
  const prediction={textContent:''};
  const aligned={values:[.1,.4,.6,.3],fps:4};
  const nodes={
    '#animation-motion-lab-audio-preview':pane,
    '#animation-motion-lab-audio-plot':graph,
    '#motion-studio-envelope-message':diagnostics,
    '#animation-motion-lab-audio-threshold':{value:'0.12'},
    '#animation-motion-lab-audio-attack':{value:'1'},
    '#animation-motion-lab-audio-release':{value:'3'},
    '#animation-motion-lab-audio-summary':summary,
    '#animation-motion-lab-audio-prediction':prediction,
    '#animation-motion-lab-audio-band':{value:'fullband'},
    '#animation-motion-lab-audio-detection':{value:'transient'},
  };
  const ctx={
    qs:s=>nodes[s]||null,
    state:{project:{id:'p1',animation:{fps:4,max_frames:4}}},
    motionLabAudioProjectId:'p1',motionLabAudioAnalysis:aligned,
    motionLabAudioSignal:()=>aligned.values,
    document:{createElementNS:(_ns,tag)=>({
      tag,setAttribute(){},appendChild(){},
    })},
  };
  vm.runInNewContext(preview,ctx);
  ctx.motionLabAudioPreview();
  assert.equal(pane.hidden,false);
  assert.ok(graph.children.length>1,'envelope path and guide should render');
  assert.match(diagnostics.textContent,/Analyzed envelope ready/);
  assert.match(summary.textContent,/4 frames/);
});

test('UX2.1 original Analyze button and status are both in visible Stage 2',()=>{
  assert.match(js,/stages\.analysis\.appendChild\(liveStatus\)/);
  assert.match(js,/stages\.analysis\.insertBefore\(row, analysis\)/);
  assert.match(js,/stages\.analysis\.appendChild\(analysisStatus\)/);
  assert.match(js,/legacyDetails\.appendChild\(diagnosticMessage\)/);
  assert.match(js,/showMarkers\.textContent = 'Show Detected Beats'/);
  assert.match(js,/beatsLink\.textContent = 'View Detected Beats/);
  assert.match(js,/stages\.source\.appendChild\(proceedRow\)/);
  assert.match(css,/#animation-panel-audio \.animation-audio-preview-placeholder\[hidden\]/);
});
