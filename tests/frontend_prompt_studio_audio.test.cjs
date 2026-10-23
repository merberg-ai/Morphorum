'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const sync=require('../frontend/dist/assets/prompt-studio-audio.js');
const tracks=()=>({
 positive:{kind:'prompt',interpolation:'blend',keyframes:[
 {frame:0,value:'<lora:Visual:0.8> original scene'},
 {frame:30,value:'repeat'},
 {frame:70,value:'repeat'}]},
 negative:{kind:'prompt',interpolation:'hold',keyframes:[{frame:0,value:'not this'}]}
});
test('PS6.1 nearest frame is deterministic for noninteger FPS and rejects out of range',()=>{
 assert.equal(sync.frameAt(1,23.976,120),24);
 assert.equal(sync.frameAt(1.004,23.976,120),24);
 assert.equal(sync.frameAt(2.002,23.976,120),48);
 assert.equal(sync.frameAt(4.99,23.976,120),null);
 assert.equal(sync.frameAt(5.1,23.976,120),null);
 assert.equal(sync.frameAt(-0.2,24,120),null);
 assert.equal(sync.frameAt(1,0,120),null);
 assert.equal(sync.frameAt(0,24,1),0);
});
test('PS6.1 saved enabled marker overrides take precedence and collisions are disclosed',()=>{
 const points=[
 {id:'kick-1',kind:'kick',enabled:true,time_seconds:1},
 {id:'snare-1',kind:'snare',enabled:true,time_seconds:1.004},
 {id:'high-1',kind:'highs',enabled:false,time_seconds:2},
 {id:'late-1',kind:'kick',enabled:true,time_seconds:4.99}];
 const analyzed=sync.normalizeEvents(points,5.005,23.976,120,{saved:true});
 assert.equal(analyzed.duplicateFrames,1);
 assert.equal(analyzed.outOfRange,1);
 assert.equal(analyzed.points.find(x=>x.id==='high-1').enabled,false);
 assert.equal(analyzed.points.find(x=>x.id==='kick-1').frame,24);
 assert.ok(analyzed.warnings.length>=2);
 assert.throws(()=>sync.normalizeEvents(new Array(12001).fill({}),4,24,100),/oversized/);
});
test('PS6.1 complete preview never mutates source text, negative lane or frame zero',()=>{
 const before=tracks(),serialized=JSON.stringify(before);
 const events=[
 {id:'a',frame:32,enabled:true,time_seconds:32/24,drift_seconds:0},
 {id:'b',frame:72,enabled:true,time_seconds:3,drift_seconds:0}];
 const planned=sync.planAlignment(before,events,new Set(['a','b']),new Set(),120);
 assert.equal(planned.ok,true);
 assert.deepEqual(planned.moves.map(x=>[x.from,x.to]),[[30,32],[70,72]]);
 assert.deepEqual(planned.tracks.positive.keyframes.map(x=>x.frame),[0,32,72]);
 assert.equal(planned.tracks.positive.keyframes[0].value,'<lora:Visual:0.8> original scene');
 assert.deepEqual(planned.tracks.negative,before.negative);
 assert.equal(JSON.stringify(before),serialized);
});
test('PS6.1 unavailable markers or collisions yield no partial proposal',()=>{
 const input=tracks(),e=[{id:'one',frame:32,enabled:true,time_seconds:1.33,drift_seconds:0}];
 const plan=sync.planAlignment(input,e,new Set(['one']),new Set(),120);
 assert.equal(plan.ok,false);
 assert.deepEqual(plan.tracks,input);
 assert.equal(plan.moves.length,0);
 const reserved=sync.planAlignment(input,[
  {id:'blocked',frame:30,enabled:true,time_seconds:1.25,drift_seconds:0}],
  new Set(['blocked']),new Set([30]),120);
 assert.equal(reserved.ok,false);
});
test('PS6.1 honors per-scene locks and rejects same-frame duplicate beat moves',()=>{
 const input=tracks(),events=[
 {id:'one',frame:30,enabled:true,time_seconds:1.25,drift_seconds:0},
 {id:'oneAgain',frame:30,enabled:true,time_seconds:1.252,drift_seconds:0},
 {id:'two',frame:74,enabled:true,time_seconds:74/24,drift_seconds:0}];
 const locked=sync.planAlignment(input,events,
   new Set(['one','oneAgain','two']),new Set([30]),120);
 assert.equal(locked.ok,true);
 assert.deepEqual(locked.tracks.positive.keyframes.map(p=>p.frame),[0,30,74]);
 assert.equal(locked.moves.length,1);
});
test('PS6.1 UI only uses existing verified project endpoints, never mutates media or prompts',()=>{
 const code=fs.readFileSync(path.join(__dirname,'..','frontend','dist','assets',
   'prompt-studio-audio.js'),'utf8');
 assert.match(code,/\/media-inventory/);
 assert.match(code,/\/motion-lab\/audio\/.*\/analysis/);
 assert.match(code,/\/motion-lab\/audio-markers\//);
 assert.match(code,/getLockedFrames/);
 assert.match(code,/read-only alignment preview/i);
 assert.doesNotMatch(code,/method:'POST'|method:'PUT'|method:'DELETE'/);
 assert.doesNotMatch(code,/onCommit|onTracks|saveProject|applyPromptStudioTransfer/);
});
