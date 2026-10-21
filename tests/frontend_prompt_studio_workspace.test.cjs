'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const studio=require('../frontend/dist/assets/prompt-studio.js');
const bridge=require('../frontend/dist/assets/prompt-studio-bridge.js');
const snapshot=()=>({ok:true,projectId:'demo',savedEtag:'"'+'a'.repeat(64)+'"',
  revision:1,dirty:true,context:{name:'Demo',model:{family:'sdxl',model_id:'test'},maxFrames:120,fps:24},
  promptTracks:{
   positive:{kind:'prompt',interpolation:'blend',keyframes:[
    {frame:0,value:'<lora:Style:1>  forest'}, {frame:60,value:'city'}]},
   negative:{kind:'prompt',interpolation:'hold',keyframes:[
    {frame:0,value:'blur'}, {frame:24,value:'bad hands'}]}
  }});
test('PS1.3 imports two independent prompt tracks without mutation',()=>{
 const source=snapshot(),raw=JSON.stringify(source);
 const d=studio.beginDraft(source,bridge);
 assert.equal(d.ok,true);
 assert.equal(JSON.stringify(source),raw);
 assert.notStrictEqual(d.tracks.positive,d.original.positive);
 assert.deepEqual(d.tracks.negative.keyframes.map(x=>x.frame),[0,24]);
});
test('PS1.3 text, exact LoRA bytes, keyframe edits and per-lane modes',()=>{
 const d=studio.beginDraft(snapshot(),bridge);
 assert.equal(studio.updateDraft(d,bridge,'positive','text',0,'<lora:Style:1>  revised').ok,true);
 assert.equal(studio.updateDraft(d,bridge,'positive','add',90).ok,true);
 assert.equal(studio.updateDraft(d,bridge,'positive','move',90,80).ok,true);
 assert.equal(studio.updateDraft(d,bridge,'negative','interpolation',0,'blend').ok,true);
 assert.equal(studio.updateDraft(d,bridge,'negative','remove',24).ok,true);
 assert.equal(d.tracks.positive.keyframes[0].value,'<lora:Style:1>  revised');
 assert.deepEqual(d.tracks.positive.keyframes.map(x=>x.frame),[0,60,80]);
 assert.deepEqual(d.tracks.negative.keyframes.map(x=>x.frame),[0]);
 assert.equal(d.tracks.negative.interpolation,'blend');
 assert.equal(bridge.buildPromptOnlyPatch({animation:{max_frames:120},tracks:{prompts:d.original}},d.tracks).ok,true);
});
test('PS1.3 refuses collisions, invalid and frame-zero edits without mutation',()=>{
 const d=studio.beginDraft(snapshot(),bridge);const before=JSON.stringify(d.tracks);
 for(const args of [['positive','add',60],['positive','move',60,0],
   ['positive','remove',0],['negative','move',0,12],
   ['negative','add',120],['positive','text',0,42],
   ['negative','interpolation',0,'ease']]){
   assert.equal(studio.updateDraft(d,bridge,...args).ok,false);
   assert.equal(JSON.stringify(d.tracks),before);
 }
});
test('PS1.3 reports changed native items and no mutation of imported source',()=>{
 const d=studio.beginDraft(snapshot(),bridge);
 assert.deepEqual(studio.changeList(d.original,d.tracks),[]);
 studio.updateDraft(d,bridge,'positive','text',60,'night');
 studio.updateDraft(d,bridge,'negative','interpolation',0,'blend');
 const changes=studio.changeList(d.original,d.tracks);
 assert.deepEqual(changes.map(x=>x.kind),['Changed','Interpolation']);
 assert.equal(d.original.positive.keyframes[1].value,'city');
 d.applied=true;
 assert.equal(studio.updateDraft(d,bridge,'positive','text',60,'not allowed').code,'NO_DRAFT');
});

test('PS1.3 frame-zero remove and move controls stay disabled on reactivation',()=>{
 const fs=require('node:fs');
 const path=require('node:path');
 const script=fs.readFileSync(path.join(__dirname,'..','frontend','dist','assets','prompt-studio.js'),'utf8');
 assert.match(script,/el\.disabled=!can\|\|el\.dataset\.psFixed==='1'/);
 assert.match(script,/frame\.dataset\.psFixed=point\.frame===0/);
 assert.match(script,/remove\.dataset\.psFixed=point\.frame===0/);
});

test('PS1.4 serializes versioned saved draft without Editor ETag and restores independently',()=>{
 const source=studio.beginDraft(snapshot(),bridge);
 studio.updateDraft(source,bridge,'positive','text',60,'<lora:Style:1>  night');
 const result=studio.serializeDraft(source,'  Horror Story  ',bridge);
 assert.equal(result.ok,true);
 assert.equal(result.record.schema_version,1);
 assert.equal(result.record.format,'morphorum.prompt-studio-draft');
 assert.equal(result.record.name,'Horror Story');
 assert.equal(result.record.project_id,'demo');
 assert.equal(result.record.project_context.max_frames,120);
 assert.equal(JSON.stringify(result.record).includes('savedEtag'),false);
 assert.equal(result.record.prompt_tracks.positive.keyframes[1].value,'<lora:Style:1>  night');
 const restored=studio.restoreDraft(result.record,snapshot(),bridge);
 assert.equal(restored.ok,true);
 assert.equal(restored.compatible,true);
 assert.equal(restored.tracks.positive.keyframes[1].value,'<lora:Style:1>  night');
 assert.equal(restored.original.positive.keyframes[1].value,'city');
 assert.deepEqual(studio.changeList(restored.original,restored.tracks).map(x=>x.kind),['Changed']);
});
test('PS1.4 refuses silent rebase after baseline/model/timing changes',()=>{
 const saved=studio.serializeDraft(studio.beginDraft(snapshot(),bridge),'saved',bridge).record;
 const edited=snapshot();edited.promptTracks.negative.keyframes[1].value='new external edit';
 assert.equal(studio.restoreDraft(saved,edited,bridge).compatible,false);
 const model=snapshot();model.context.model.family='flux';
 assert.equal(studio.restoreDraft(saved,model,bridge).compatible,false);
 const timing=snapshot();timing.context.fps=30;
 assert.equal(studio.restoreDraft(saved,timing,bridge).compatible,false);
 const other=snapshot();other.projectId='another';
 assert.equal(studio.restoreDraft(saved,other,bridge).compatible,false);
 const stale=studio.restoreDraft(saved,{ok:false,message:'stale'},bridge);
 assert.equal(stale.ok,true);
 assert.equal(stale.compatible,false);
 assert.equal(stale.snapshot.ok,false);
});
test('PS1.4 uses conditional draft overwrite and explicit deletion confirmation',()=>{
 const fs=require('node:fs'),path=require('node:path');
 const script=fs.readFileSync(path.join(__dirname,'..','frontend','dist','assets','prompt-studio.js'),'utf8');
 assert.match(script,/data-ps="load"/);
 assert.match(script,/data-ps="save-copy"/);
 assert.match(script,/data-ps="delete"/);
 assert.match(script,/async function refreshList/);
 assert.match(script,/method:overwrite\?'PUT':'POST'/);
 assert.match(script,/headers:overwrite\?\{'If-Match':savedEtag\}/);
 assert.match(script,/method:'DELETE',headers:\{'If-Match':item\.etag\}/);
 assert.match(script,/baselineBlocked\|\|/);
 assert.match(script,/async function deleteSaved/);
 assert.match(script,/MorphorumDialog\.confirm/);
});
