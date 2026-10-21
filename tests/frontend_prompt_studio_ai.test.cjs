'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const ai=require('../frontend/dist/assets/prompt-studio-ai.js');
const studio=require('../frontend/dist/assets/prompt-studio.js');
const bridge=require('../frontend/dist/assets/prompt-studio-bridge.js');
function snapshot(){
  return {ok:true,projectId:'draft-01',
   context:{name:'Story',model:{family:'sdxl',model_id:'checkpoint',variant:''},
     maxFrames:96,fps:24,startMode:'prompt',sourceImageName:''},
   promptTracks:{positive:{kind:'prompt',interpolation:'blend',
     keyframes:[{frame:0,value:'<lora:Visual:1> original'},
                {frame:48,value:'second'}]},
    negative:{kind:'prompt',interpolation:'hold',
     keyframes:[{frame:0,value:'blurry'}]}}};
}
function proposal(draft){
 return {tracks:{positive:{kind:'prompt',interpolation:'blend',
   keyframes:[{frame:0,value:'AI first'},{frame:48,value:'AI next'}]},
   negative:{kind:'prompt',interpolation:'hold',
   keyframes:[{frame:0,value:'blurry'}]}},
 scenes:[{frame:0,positive:'AI first',negative:''},{frame:48,positive:'AI next',negative:''}],
 provenance:{provider:'ollama',model:'qwen3:4b',family:'sdxl',
  scene_count:2,mode:'create',created_at:'2026-10-21T00:00:00Z',profile:'ps4-generic-v1'},
 warnings:[]};
}
test('PS4 valid structured proposal is preview-only and does not mutate original',()=>{
 const d=studio.beginDraft(snapshot(),bridge),before=JSON.stringify(d.tracks);
 const result=ai.validateProposal(proposal(d),d,bridge);
 assert.equal(result.ok,true);
 assert.equal(JSON.stringify(d.tracks),before);
 const differences=ai.changes(d.tracks,result.tracks);
 assert.deepEqual(differences.map(x=>[x.lane,x.frame]),[['positive',0],['positive',48]]);
 assert.equal(differences[0].before,'<lora:Visual:1> original');
 assert.equal(differences[0].after,'AI first');
});
test('PS4 rejects mismatched provenance, malformed frames and invalid draft',()=>{
 const d=studio.beginDraft(snapshot(),bridge);
 const changed=proposal(d);changed.provenance.family='zimage';
 assert.equal(ai.validateProposal(changed,d,bridge).code,'FAMILY');
 const bad=proposal(d);bad.scenes[0].frame=200;
 assert.equal(ai.validateProposal(bad,d,bridge).code,'FRAME');
 const incomplete=proposal(d);incomplete.scenes=[];
 assert.equal(ai.validateProposal(incomplete,d,bridge).code,'SCENES');
 d.applied=true;
 assert.equal(ai.validateProposal(proposal(d),d,bridge).code,'NO_DRAFT');
});
test('PS4 existing draft serialization carries AI provenance and legacy remains readable',()=>{
 const d=studio.beginDraft(snapshot(),bridge);
 d.aiProvenance=proposal(d).provenance;
 const serialized=studio.serializeDraft(d,'AI Story',bridge);
 assert.equal(serialized.ok,true);
 assert.equal(serialized.record.ai_provenance.model,'qwen3:4b');
 const restored=studio.restoreDraft(serialized.record,snapshot(),bridge);
 assert.equal(restored.ok,true);
 assert.equal(restored.aiProvenance.mode,'create');
 const old={...serialized.record};delete old.ai_provenance;
 assert.equal(studio.restoreDraft(old,snapshot(),bridge).aiProvenance,null);
});
test('PS4 UI isolates proposals from native render and enforces review, cancellation and stale checks',()=>{
 const ui=fs.readFileSync(path.join(__dirname,'..','frontend','dist','assets','prompt-studio-ai.js'),'utf8');
 const host=fs.readFileSync(path.join(__dirname,'..','frontend','dist','assets','prompt-studio.js'),'utf8');
 const html=fs.readFileSync(path.join(__dirname,'..','frontend','dist','index.html'),'utf8');
 assert.match(html,/prompt-studio-ai\.js[^"]*" defer/);
 assert.ok(html.indexOf('prompt-studio-ai.js')<html.indexOf('prompt-studio.js'));
 assert.match(ui,/AbortController/);
 assert.match(ui,/\/api\/prompt-studio\/ollama\/models/);
 assert.match(ui,/\/api\/prompt-studio\/ollama\/generate/);
 assert.match(ui,/data-p4="review"/);
 assert.match(ui,/d\.revision!==rev/);
 assert.match(ui,/d\.revision!==review\.revision/);
 assert.match(ui,/MorphorumDialog\.confirm/);
 assert.match(ui,/onCommit\?\.\(review\.result\.tracks,review\.result\.provenance\)/);
 assert.match(host,/ai_provenance:draft\.aiProvenance\|\|null/);
 assert.match(host,/onCommit:\(tracks,provenance\)=>/);
 assert.match(host,/draft\.aiProvenance=provenance/);
 assert.doesNotMatch(ui,/\/api\/animation\/projects\/.*(?:save|render)/);
});
