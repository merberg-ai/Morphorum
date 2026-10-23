'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const read=p=>fs.readFileSync(path.join(__dirname,'..',p),'utf8');
const html=read('frontend/dist/index.html');
const studio=read('frontend/dist/assets/prompt-studio.js');
const ai=read('frontend/dist/assets/prompt-studio-ai.js');
const audio=read('frontend/dist/assets/prompt-studio-audio.js');
const css=read('frontend/dist/assets/animation.css');

test('PS6.1 module is loaded before Prompt Studio workspace',()=>{
 const audioScript=html.indexOf('/assets/prompt-studio-audio.js?v=');
 const studioScript=html.indexOf('/assets/prompt-studio.js?v=');
 assert.ok(audioScript>=0);
 assert.ok(studioScript>audioScript);
 assert.match(studio,/MorphorumPromptStudioAudio\?\.mount/);
 assert.match(studio,/getLockedFrames:\(\)=>timeline\?\.locks/);
 assert.match(studio,/audioUI\?\.reset\(\)/);
 assert.match(studio,/audioUI\?\.invalidate\(\)/);
 assert.match(studio,/audioFold\?\.addEventListener\('toggle'/);
});
test('PS6.1 audio is isolated from Studio Apply, render, and source mutation',()=>{
 assert.match(studio,/data-ps="audio"/);
 assert.match(audio,/data-a6="review"/);
 assert.match(audio,/No audio, prompt, camera motion or project files are changed/);
 assert.match(audio,/marker_mode:marked\?'saved-edits':'detected'/);
 assert.match(audio,/Math\.floor\(seconds\*fps\+0\.5\)/);
 assert.doesNotMatch(audio,/applyTracks\(|onCommit\(|mutation:|method:'POST'|method:'PUT'/);
});
test('Prompt Studio advanced sections use native disclosure without hiding PS4 Director',()=>{
 assert.match(studio,/fold\('\.ps14-library'/);
 assert.match(studio,/fold\('\[data-ps="composer"\]'/);
 assert.match(studio,/fold\('\[data-ps="timeline"\]','Visual Prompt Timeline',true\)/);
 assert.match(studio,/fold\('\[data-ps="lanes"\]'/);
 assert.match(studio,/fold\('\[data-ps="audio"\]'/);
 assert.match(ai,/fold\(node\.querySelector\('\.ps5-profile'\)/);
 assert.match(ai,/fold\(node\.querySelector\('\.ps5-vision'\)/);
 assert.match(ai,/fold\(node\.querySelector\('\[data-p4="evaluation"\]'\)/);
 assert.doesNotMatch(studio,/fold\('\[data-ps="ai"\]'/);
 assert.match(css,/\.ps13-fold/);
 assert.match(css,/\.ps5-fold/);
 assert.match(css,/@media\(max-width:650px\)/);
});
