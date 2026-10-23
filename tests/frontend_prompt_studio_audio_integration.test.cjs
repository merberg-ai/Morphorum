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
test('PS6.2 stages only Studio prompts and never mutates source audio or camera motion',()=>{
 assert.match(studio,/data-ps="audio"/);
 assert.match(audio,/data-a6="review"/);
 assert.match(audio,/No soundtrack or camera/);
 assert.match(audio,/marker_mode:marked\?'saved-edits':'detected'/);
 assert.match(audio,/Math\.floor\(seconds\*fps\+0\.5\)/);
 assert.match(audio,/onStage\?\.\(p\.tracks,stamp\)/);
 assert.doesNotMatch(audio,/method:'POST'|method:'PUT'|mutation:|\/api\/animation\/render/);
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


test('PS6.2 UI uses fixed-width mobile checkbox columns and ellipsized summaries',()=>{
 assert.match(audio,/row\.append\(input,summary\)/);
 assert.match(css,/\.ps61-workspace \.ps61-lock input\[type="checkbox"\]/);
 assert.match(css,/width:18px!important;height:18px!important/);
 assert.match(css,/grid-template-columns:20px minmax\(0,1fr\)/);
 assert.match(css,/\.ps61-workspace \.ps61-lock span/);
 assert.match(css,/text-overflow:ellipsis;white-space:nowrap/);
 assert.match(css,/max-height:320px;overflow-y:auto/);
});
test('PS6.2 Studio draft Save and Apply reject a stale audio stamp',()=>{
 assert.match(studio,/audioAlignment:null/);
 assert.match(studio,/audio_alignment:draft\.audioAlignment\|\|null/);
 assert.match(studio,/audioAlignment:saved\.audio_alignment\|\|null/);
 assert.match(studio,/await audioUI\?\.verifyStaged\(draft\.audioAlignment\)/);
 assert.match(studio,/draft\.audioAlignment=clone\(provenance\)/);
 assert.match(studio,/audio-beat-alignment/);
 assert.match(studio,/onUndo:\(\)=>timeline\?\.undo\(\)/);
});
