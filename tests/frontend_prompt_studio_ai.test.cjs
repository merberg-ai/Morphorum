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

test('PS4 visual storyboard review displays grounded frames and scene titles without injection',()=>{
 const script=fs.readFileSync(path.join(__dirname,'..','frontend','dist','assets','prompt-studio-ai.js'),'utf8');
 assert.match(script,/data-p4="scenes"/);
 assert.match(script,/result\.scenes/);
 assert.match(script,/title\.textContent=/);
 assert.match(script,/root\.localStorage\?\.setItem/);
 assert.match(script,/LAN permission is/);
 assert.match(script,/for\(const field of \['endpoint','lan','model','idea','negative','profile','subject','style'\]\)/);
});

test('PS4 visibility reveals the outer Studio container, not only the child UI',()=>{
  const parent={hidden:true},director={hidden:true},empty={hidden:true};
  ai.setVisibility(parent,director,empty,false);
  assert.equal(parent.hidden,false,'the outer workspace must be visible before importing');
  assert.equal(director.hidden,true,'form stays hidden without an editable draft');
  assert.equal(empty.hidden,false,'guidance is visible before import');
  ai.setVisibility(parent,director,empty,true);
  assert.equal(parent.hidden,false,'outer workspace must not remain hidden');
  assert.equal(director.hidden,false,'AI form must appear after import/load');
  assert.equal(empty.hidden,true,'guidance must disappear once the form opens');
});
test('PS4 always has a top-level in-Studio navigation shortcut and import guidance',()=>{
  const host=fs.readFileSync(path.join(__dirname,'..','frontend','dist','assets','prompt-studio.js'),'utf8');
  const ui=fs.readFileSync(path.join(__dirname,'..','frontend','dist','assets','prompt-studio-ai.js'),'utf8');
  assert.match(host,/data-ps="ai-shortcut"/);
  assert.match(host,/aiPanel\.scrollIntoView\?/);
  assert.match(ui,/setVisibility\(panel,node,empty,usable\)/);
  assert.match(ui,/Import Existing Prompts/);
  assert.match(ui,/panel\.append\(empty,node\)/);
});

test('PS4.1 incremental NDJSON parser handles fragmented progress and terminal storyboard',async()=>{
  const te=new TextEncoder();
  const fragments=[
    '{"type":"progress","stage":"connecting","elapsed_seconds":0,"characters":0}\n'+
      '{"type":"progress","stage":"receiv',
    'ing","elapsed_seconds":5,"characters":230}\n'+
      '{"type":"result","data":{"scenes":[{"frame":0}]}}\n'
  ];
  let index=0;
  const response={body:{getReader:()=>({
    read:async()=>index<fragments.length?{done:false,value:te.encode(fragments[index++])}:{done:true},
    releaseLock(){}
  })}};
  const events=[];
  const result=await ai.readProgressStream(response,e=>events.push(e));
  assert.deepEqual(events.map(e=>e.type),['progress','progress','result']);
  assert.equal(events[1].characters,230);
  assert.equal(result.scenes[0].frame,0);
});
test('PS4.1 stream error and disconnected early request never create a fake result',async()=>{
  function response(value){
    let done=false;
    return {body:{getReader:()=>({
      read:async()=>done?{done:true}:(done=true,{done:false,value:new TextEncoder().encode(value)}),
      releaseLock(){}
    })}};
  }
  await assert.rejects(()=>ai.readProgressStream(response(
    '{"type":"error","message":"Ollama offline"}\n')),/Ollama offline/);
  await assert.rejects(()=>ai.readProgressStream(response(
    '{"type":"progress","stage":"connecting"}\n')),/ended before/);
  await assert.rejects(()=>ai.readProgressStream(response(
    'this is not json\n')),/invalid JSON/);
});
test('PS4.1 shows elapsed real activity instead of invented progress percentage, and console source',()=>{
  const ui=fs.readFileSync(path.join(__dirname,'..','frontend','dist','assets','prompt-studio-ai.js'),'utf8');
  const html=fs.readFileSync(path.join(__dirname,'..','frontend','dist','index.html'),'utf8');
  assert.match(ui,/data-p4="activity"/);
  assert.match(ui,/data-p4="elapsed"/);
  assert.match(ui,/\/api\/prompt-studio\/ollama\/generate-stream/);
  assert.match(ui,/setInterval\(renderProgress,1000\)/);
  assert.match(ui,/stopProgress\(\)/);
  assert.match(ui,/onEvent\?\.\(evt\)/);
  assert.match(html,/value="prompt-studio" checked/);
});
