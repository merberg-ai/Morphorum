'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const js=fs.readFileSync(path.join(__dirname,'..','frontend','dist','assets','animation.js'),'utf8');
const start=js.indexOf('  function motionDirectorFindCandidates() {');
const end=js.indexOf('  function motionDirectorAssignBeats() {',start);
assert.ok(start>=0&&end>start);
const source=js.slice(start,end);

function fixture({events,overrides=null,band='kick',strength='.35',startTime='0',
  endTime='2',gap='.1',every='1',analysis=true}={}) {
  const fields={
    '[data-beat-kind]':{value:band},
    '[data-beat-strength]':{value:strength},
    '[data-beat-gap]':{value:gap},
    '[data-beat-start]':{value:startTime},
    '[data-beat-end]':{value:endTime},
    '[data-beat-every]':{value:every},
    '[data-beat-summary]':{textContent:''},
    '[data-beat-undo]':{disabled:true},
  };
  const panel={querySelector:key=>fields[key]||null};
  const ctx={
    qs:()=>panel,
    motionLabAudioAnalysis:analysis?{
      duration_seconds:2,events:{events:events || []}
    }:null,
    motionLabEditedEvents:overrides,
    motionDirectorBulkUndo:null,
  };
  vm.runInNewContext(source,ctx);
  return {ctx,fields};
}

test('Preview Matches reads analyzed spectral events when no marker file is saved',()=>{
  const f=fixture({events:[
    {id:'k1',kind:'kick',time_seconds:.2,strength:.8},
    {id:'s1',kind:'snare',time_seconds:.7,strength:.9},
    {id:'k2',kind:'kick',time_seconds:1.1,strength:.56},
  ]});
  const matches=f.ctx.motionDirectorFindCandidates();
  assert.equal(matches.length,2);
  f.ctx.motionDirectorFindStatus();
  assert.match(f.fields['[data-beat-summary]'].textContent,/2 matching kick hit/);
});

test('Preview Matches honors an intentionally cleared set of marker edits',()=>{
  const f=fixture({events:[{id:'k1',kind:'kick',time_seconds:.2,strength:.8}],
    overrides:[]});
  assert.equal(f.ctx.motionDirectorFindCandidates().length,0);
  f.ctx.motionDirectorFindStatus();
  assert.match(f.fields['[data-beat-summary]'].textContent,/No enabled markers/);
});

test('Preview Matches tells users to lower strength instead of unexplained zero',()=>{
  const f=fixture({events:[{id:'k1',kind:'kick',time_seconds:.2,strength:.4}],
    strength:'.8'});
  f.ctx.motionDirectorFindStatus();
  assert.match(f.fields['[data-beat-summary]'].textContent,/Lower that filter/);
});

test('Preview Matches explains a selected band without matching hit types',()=>{
  const f=fixture({events:[{id:'s1',kind:'snare',time_seconds:.2,strength:.9}]});
  f.ctx.motionDirectorFindStatus();
  assert.match(f.fields['[data-beat-summary]'].textContent,/No kick markers/);
});

test('Preview Matches explains stale range from a previous longer WAV',()=>{
  const f=fixture({events:[{id:'k1',kind:'kick',time_seconds:.2,strength:.9}],
    endTime:'12'});
  assert.equal(f.ctx.motionDirectorFindCandidates().length,0);
  f.ctx.motionDirectorFindStatus();
  assert.match(f.fields['[data-beat-summary]'].textContent,/Invalid beat range/);
  assert.match(js,/panel\.dataset\.beatSourceSha !== currentWav/);
  assert.match(js,/end\.value=motionLabAudioAnalysis\.duration_seconds\.toFixed\(3\)/);
});

test('Preview Matches honors minimum spacing and Nth hit safely',()=>{
  const f=fixture({events:[
    {id:'k1',kind:'kick',time_seconds:.2,strength:.9},
    {id:'k2',kind:'kick',time_seconds:.24,strength:.9},
    {id:'k3',kind:'kick',time_seconds:.8,strength:.9},
    {id:'k4',kind:'kick',time_seconds:1.5,strength:.9},
  ],every:'2',gap:'.1'});
  assert.equal(f.ctx.motionDirectorFindCandidates().length,2);
});

test('Preview Matches reports missing analysis rather than counting zero hits',()=>{
  const f=fixture({analysis:false});
  f.ctx.motionDirectorFindStatus();
  assert.match(f.fields['[data-beat-summary]'].textContent,/Analyze or restore a WAV/);
});

test('Preview Matches refreshes on filter edits without writing project state',()=>{
  assert.match(js,/field\.addEventListener\('input',update\)/);
  assert.match(js,/if \(motionDirectorPreviewMatches\) motionLabStereoWaveform\(\)/);
  assert.match(js,/motionDirectorPreviewMatches=false;/);
});
