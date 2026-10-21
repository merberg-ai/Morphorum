'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const timeline=require('../frontend/dist/assets/prompt-studio-timeline.js');
const studio=require('../frontend/dist/assets/prompt-studio.js');
const bridge=require('../frontend/dist/assets/prompt-studio-bridge.js');
const sample=()=>({
 positive:{kind:'prompt',interpolation:'blend',keyframes:[
  {frame:0,value:'<lora:Style:1> original'}, {frame:20,value:'forest'},
  {frame:40,value:'sunrise'}]},
 negative:{kind:'prompt',interpolation:'hold',keyframes:[
  {frame:0,value:'blur'}, {frame:30,value:'artifacts'}]}
});
test('PS2 snap clamps edges, works with large frames and pixel geometry roundtrips',()=>{
 assert.equal(timeline.snapFrame(0,5,120),0);
 assert.equal(timeline.snapFrame(14,5,120),15);
 assert.equal(timeline.snapFrame(119,10,120),119);
 assert.equal(timeline.snapFrame(-100,2,120),0);
 assert.equal(timeline.snapFrame(10000,24,120),119);
 for(const max of [1,5,120,4096,1000000]){
  const g=timeline.pixelGeometry(max,3);
  assert.ok(g.width>=660&&g.width<=150000);
  assert.equal(g.xToFrame(g.frameToX(0)),0);
  assert.equal(g.xToFrame(g.frameToX(max-1)),max-1);
 }
});
test('PS2 atomic multi-lane shift preserves prompt bytes, lane boundaries and independent interpolation',()=>{
 const source=sample(),original=JSON.stringify(source);
 const result=timeline.previewShift(source,[
  {lane:'positive',frame:20},{lane:'negative',frame:30}
 ],10,120);
 assert.equal(result.ok,true);
 assert.deepEqual(result.tracks.positive.keyframes.map(x=>x.frame),[0,30,40]);
 assert.deepEqual(result.tracks.negative.keyframes.map(x=>x.frame),[0,40]);
 assert.equal(result.tracks.positive.keyframes[0].value,'<lora:Style:1> original');
 assert.equal(result.tracks.negative.interpolation,'hold');
 assert.equal(JSON.stringify(source),original);
 assert.equal(bridge.validateTracks(result.tracks,120).ok,true);
});
test('PS2 rejects frame-zero drag, overlap, locked and out-of-bounds shifts atomically',()=>{
 const original=sample(),snapshot=JSON.stringify(original);
 const selected=[{lane:'positive',frame:20},{lane:'negative',frame:30}];
 assert.equal(timeline.previewShift(original,selected,20,120).code,'COLLISION');
 assert.equal(timeline.previewShift(original,selected,-30,120).code,'RANGE');
 assert.equal(timeline.previewShift(original,[{lane:'positive',frame:0}],1,120).code,'FRAME_ZERO');
 assert.equal(timeline.previewShift(original,selected,5,120,['negative']).code,'LOCKED');
 assert.equal(JSON.stringify(original),snapshot);
});
test('PS2 multiple selected neighboring keyframes can shift together without false collision',()=>{
 const tracks=sample(),selection=[{lane:'positive',frame:20},{lane:'positive',frame:40}];
 const moved=timeline.previewShift(tracks,selection,20,120);
 assert.equal(moved.ok,true);
 assert.deepEqual(moved.tracks.positive.keyframes.map(x=>x.frame),[0,40,60]);
 assert.deepEqual(moved.selection, [{lane:'positive',frame:40},{lane:'positive',frame:60}]);
});
test('PS2 duplication, collisions, exact text preservation and even spacing',()=>{
 const tracks=sample();
 const result=timeline.duplicateSelection(tracks,[{lane:'positive',frame:40}],5,120);
 assert.equal(result.ok,true);
 assert.equal(result.tracks.positive.keyframes[3].value,'sunrise');
 assert.deepEqual(result.tracks.positive.keyframes.map(x=>x.frame),[0,20,40,45]);
 assert.equal(timeline.duplicateSelection(tracks,[{lane:'positive',frame:20}],20,120).code,'COLLISION');
 assert.equal(timeline.duplicateSelection(tracks,[{lane:'positive',frame:0}],1,120).code,'FRAME_ZERO');
 const evenly=timeline.evenlySpace(tracks,'positive',120);
 assert.equal(evenly.ok,true);
 assert.deepEqual(evenly.tracks.positive.keyframes.map(x=>x.frame),[0,60,119]);
 assert.deepEqual(evenly.tracks.negative,tracks.negative);
 assert.equal(timeline.evenlySpace(tracks,'positive',120,['positive']).code,'LOCKED');
});
test('PS2 history coalesces typing, supports bounded undo redo and cancels redo on new edit',()=>{
 const history=timeline.createHistory(3);
 let value=sample();
 const save=(newValue,key)=>{history.record(value,key);value=newValue;};
 let next=structuredClone(value);next.positive.keyframes[0].value='x';
 save(next,'text:positive:0');
 next=structuredClone(value);next.positive.keyframes[0].value='xy';
 save(next,'text:positive:0');
 assert.equal(history.canUndo,true);
 assert.equal(history.undo(value).positive.keyframes[0].value,'<lora:Style:1> original');
 assert.equal(history.canUndo,false);
 assert.equal(history.redo(value).positive.keyframes[0].value,'xy');
 history.reset();
 assert.equal(history.canUndo,false);
 history.record(value,'move');assert.equal(history.canUndo,true);
 history.undo(value);history.record(value,'edit');
 assert.equal(history.canRedo,false);
});
test('PS2 integration stays isolated from project saves and follows Studio draft lifecycle',()=>{
 const js=fs.readFileSync(path.join(__dirname,'..','frontend','dist','assets','prompt-studio.js'),'utf8');
 const html=fs.readFileSync(path.join(__dirname,'..','frontend','dist','index.html'),'utf8');
 assert.match(html,/prompt-studio-timeline\.js[^"]*" defer/);
 assert.ok(html.indexOf('prompt-studio-timeline.js')<html.indexOf('prompt-studio.js'));
 assert.match(js,/MorphorumPromptStudioTimeline\?\.mount/);
 assert.match(js,/timeline\?\.reset\(\)/);
 assert.match(js,/data-ps="timeline"/);
 assert.match(js,/timeline\?\.record\(before/);
 assert.match(js,/bridge\.validateTracks\(next/);
 assert.match(js,/baselineBlocked\|\|/);
 const controller=fs.readFileSync(path.join(__dirname,'..','frontend','dist','assets','prompt-studio-timeline.js'),'utf8');
 assert.match(controller,/setPointerCapture/);
 assert.match(controller,/pointercancel/);
 assert.match(controller,/\bshiftKey\b/);
 assert.match(controller,/pointerdown/);
 assert.match(controller,/frame===0/);
 assert.doesNotMatch(controller,/\bmethod:\s*['"](?:PUT|PATCH|DELETE)['"]|saveProject\(/);
});
