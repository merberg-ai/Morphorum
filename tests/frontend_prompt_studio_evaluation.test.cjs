'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const ev=require('../frontend/dist/assets/prompt-studio-evaluation.js');
test('PS5.3 has four fixed scenarios across every supported model family',()=>{
 assert.deepEqual(ev.CASES.map(x=>x.id),['horror','character','landscape','mixed-lora']);
 for(const family of ['sdxl','flux','zimage'])for(const c of ev.CASES){
   const request=ev.makeRequest(c.id,family,'qwen3:4b','http://localhost:11434',false);
   assert.equal(request.profile,'ps5-'+family+'-v1');
   assert.equal(request.max_frames,96);
   assert.equal(request.fps,24);
   assert.equal(request.include_negative,false);
   assert.deepEqual(request.tracks.positive.keyframes.map(x=>x.frame),
     c.id==='mixed-lora'?[0,48]:[0]);
   assert.equal(request.scene_count,c.id==='mixed-lora'?2:3);
 }
 assert.throws(()=>ev.makeRequest('bad','sdxl','qwen3:4b'),/Select/);
});
test('PS5.3 mixed-LoRA case is synthetic and independently cloned',()=>{
 const a=ev.makeRequest('mixed-lora','sdxl','qwen3:4b');
 const b=ev.makeRequest('mixed-lora','sdxl','qwen3:9b');
 assert.match(a.tracks.positive.keyframes[0].value,/<lora:EvalInkStyle:0.65>/);
 assert.match(a.tracks.positive.keyframes[1].value,/<lora:EvalAtmosphere:0.35>/);
 b.tracks.positive.keyframes[0].value='modified';
 assert.notEqual(a.tracks.positive.keyframes[0].value,b.tracks.positive.keyframes[0].value);
 assert.doesNotMatch(JSON.stringify(a),/safetensors|source_image/);
});
test('PS5.3 rejects wrong candidate identity or frame mapping',()=>{
 const request=ev.makeRequest('horror','zimage','qwen3:4b');
 const value={provenance:{provider:'ollama',model:'qwen3:4b',
   family:'zimage',mode:'create'},
   scenes:[0,32,64].map(frame=>({frame,title:'Scene',positive:'a detailed prompt'})),
   tracks:{positive:{keyframes:[0,32,64].map(frame=>({frame,value:'a detailed prompt'}))}},
   metrics:{eval_seconds:1.5,eval_count:100}};
 assert.equal(ev.validateResult(value,request).scenes.length,3);
 value.provenance.model='wrong';
 assert.throws(()=>ev.validateResult(value,request),/mismatched/);
 value.provenance.model='qwen3:4b';value.scenes[1].frame=33;
 assert.throws(()=>ev.validateResult(value,request),/mismatched/);
});
test('PS5.3 compares serially with cancellation and records physical checks only manually',()=>{
 const ui=fs.readFileSync(path.join(__dirname,'..','frontend','dist','assets',
   'prompt-studio-evaluation.js'),'utf8');
 assert.match(ui,/for\(let i=0;i<requests.length;i\+\+\)/);
 assert.match(ui,/readStream\(response,event=>/);
 assert.match(ui,/abort\?\.abort\(\)/);
 assert.match(ui,/draft.revision!==revision/);
 assert.match(ui,/Physical render spot-check/);
 assert.match(ui,/Export JSON Report/);
 assert.match(ui,/onBusy\?\.\(true\)/);
 assert.match(ui,/onBusy\?\.\(false\)/);
 assert.doesNotMatch(ui,/onCommit|applyPromptStudioTransfer|save_animation_project/);
});
