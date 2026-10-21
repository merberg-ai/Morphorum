'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const bridge=require('../frontend/dist/assets/prompt-studio-bridge.js');
const root=path.join(__dirname,'..','frontend','dist');
const animation=fs.readFileSync(path.join(root,'assets','animation.js'),'utf8');
const html=fs.readFileSync(path.join(root,'index.html'),'utf8');
const project=()=>({
 id:'fixture',animation:{max_frames:60,fps:24,prompt_transition:'blend',start_mode:'prompt'},
 model:{model_id:'model',family:'sdxl'},motion:{zoom:'0:(1.3)'},generation:{strength:'0:(0.8)'},
 tracks:{schema_version:1,camera_2d:{zoom:{schedule:'0:(1.3)'}},prompts:{
  positive:{kind:'prompt',interpolation:'blend',keyframes:[{frame:0,value:'<lora:Z Horror:1> TEST'}, {frame:30,value:'last'}]},
  negative:{kind:'prompt',interpolation:'hold',keyframes:[{frame:0,value:'bad'}, {frame:20,value:'worse'}]}
 }},
 prompts:{'0':'<lora:Z Horror:1> TEST','30':'last'},negative_prompts:{'0':'bad','20':'worse'}
});
const rows=()=>[{frame:0,positive:'<lora:Z Horror:1> TEST',negative:'bad'},
 {frame:20,positive:'',negative:'worse'},{frame:30,positive:'last',negative:''}];
test('native import preserves independent sparse tracks, Hold and Blend',()=>{
 const p=project(),original=JSON.stringify(p),r=bridge.snapshotTracks(p,rows(),rows(),'blend');
 assert.equal(r.ok,true);assert.deepEqual(r.tracks,p.tracks.prompts);
 assert.deepEqual(Object.keys(r.maps.prompts),['0','30']);
 assert.deepEqual(Object.keys(r.maps.negative_prompts),['0','20']);
 assert.equal(JSON.stringify(p),original);
});
test('only the edited prompt lane changes, LoRA whitespace retained',()=>{
 const edited=rows();edited[1].positive='<lora:Z Horror:1>   New, scene!';
 const result=bridge.snapshotTracks(project(),rows(),edited,'blend');
 assert.equal(result.ok,true);
 assert.deepEqual(result.tracks.positive.keyframes.map(p=>p.frame),[0,20,30]);
 assert.deepEqual(result.tracks.negative.keyframes.map(p=>p.frame),[0,20]);
 assert.equal(result.tracks.positive.keyframes[1].value,'<lora:Z Horror:1>   New, scene!');
});
test('legacy combined-row structural changes fail closed',()=>{
 const edited=rows();edited[1].frame=21;
 assert.equal(bridge.snapshotTracks(project(),rows(),edited,'blend').code,'STRUCTURAL_EDIT');
 assert.equal(bridge.snapshotTracks(project(),rows(),rows().slice(1),'blend').code,'STRUCTURAL_EDIT');
});
test('patch changes prompt fields only and does not mutate source',()=>{
 const source=project(),original=JSON.stringify(source),target=bridge.nativeTracks(source);
 target.positive.keyframes[1].value='<lora:Z Horror:1> revised  ';
 const output=bridge.buildPromptOnlyPatch(source,target);
 assert.equal(output.ok,true);
 assert.equal(output.project.motion.zoom,'0:(1.3)');
 assert.equal(output.project.generation.strength,'0:(0.8)');
 assert.deepEqual(output.project.tracks.camera_2d,source.tracks.camera_2d);
 assert.equal(output.project.prompts['30'],'<lora:Z Horror:1> revised  ');
 assert.equal(JSON.stringify(source),original);
 assert.equal(bridge.diffTracks(bridge.nativeTracks(source),target).total,1);
});
test('invalid frames, modes, non-string values and missing frame zero reject',()=>{
 const source=project();
 for (const update of [
  x=>x.positive.keyframes[1].frame=60,
  x=>x.positive.keyframes[1].frame=0,
  x=>x.negative.interpolation='other',
  x=>x.positive.keyframes[0].value=42,
  x=>x.negative.keyframes=x.negative.keyframes.slice(1)
 ]){
   const lanes=bridge.nativeTracks(source);update(lanes);
   assert.equal(bridge.buildPromptOnlyPatch(source,lanes).ok,false);
 }
});
test('editor handshake is revision-guarded and cannot directly save a project',()=>{
 assert.match(html,/prompt-studio-bridge\.js[^"]*" defer/);
 for (const fn of ['getPromptStudioEditorSnapshot','previewPromptStudioTransfer','applyPromptStudioTransfer'])
   assert.ok(animation.includes('function '+fn+'('));
 assert.match(animation,/state\.editorRevision \+= 1/);
 assert.match(animation,/response\.headers\.get\('ETag'\)/);
 assert.match(animation,/saved\.etag!==snapshot\.savedEtag/);
 const part=animation.slice(animation.indexOf('  async function applyPromptStudioTransfer('),
  animation.indexOf('  window.MorphorumAnimation = {'));
 assert.match(part,/MorphorumDialog\.confirm/);
 assert.match(part,/state\.project=result\.project/);
 assert.match(part,/markDirty\(\{validate:true\}\)/);
 assert.doesNotMatch(part,/method:\s*'PUT'|save_animation_project/);
});
