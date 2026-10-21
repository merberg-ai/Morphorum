'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const studio=require('../frontend/dist/assets/prompt-studio.js');
const bridge=require('../frontend/dist/assets/prompt-studio-bridge.js');
const ai=require('../frontend/dist/assets/prompt-studio-ai.js');
const draft=()=>{
 const snapshot={ok:true,projectId:'ps51-example',
  context:{name:'Continuity demo',model:{family:'zimage',model_id:'managed',variant:''},
    maxFrames:96,fps:24,startMode:'prompt',sourceImageName:''},
  promptTracks:{positive:{kind:'prompt',interpolation:'blend',
    keyframes:[{frame:0,value:'cat'},{frame:32,value:'dog'}]},
  negative:{kind:'prompt',interpolation:'hold',keyframes:[{frame:0,value:'blur'}]}}};
 return studio.beginDraft(snapshot,bridge);
};
test('PS5.1 accepts profile-tagged proposal and exposes safe diagnostics to review',()=>{
 const d=draft(),response={
   tracks:{positive:{kind:'prompt',interpolation:'blend',
     keyframes:[{frame:0,value:'cat'},{frame:32,value:'orange cat in floral shorts'}]},
   negative:{kind:'prompt',interpolation:'hold',keyframes:[{frame:0,value:'blur'}]}},
   scenes:[{frame:32,positive:'orange cat in floral shorts',negative:''}],
   warnings:['Length is heuristic'],
   diagnostics:[{lane:'positive',frame:32,words_approx:6,long_prompt:false}],
   provenance:{provider:'ollama',profile:'ps5-zimage-v1',family:'zimage',model:'qwen3:4b',
     scene_count:1,mode:'refine',created_at:'2026-10-21T10:00:00Z'}
 };
 const result=ai.validateProposal(response,d,bridge);
 assert.equal(result.ok,true);
 assert.equal(result.provenance.profile,'ps5-zimage-v1');
 assert.equal(result.diagnostics.length,1);
 assert.equal(result.tracks.negative.keyframes[0].value,'blur');
 assert.equal(d.tracks.positive.keyframes[1].value,'dog');
});
test('PS5.1 UI carries family profile, continuity locks and targeted frame through stream request',()=>{
 const ui=fs.readFileSync(path.join(__dirname,'..','frontend','dist','assets','prompt-studio-ai.js'),'utf8');
 assert.match(ui,/data-p4="profile"/);
 assert.match(ui,/data-p4="subject"/);
 assert.match(ui,/data-p4="style"/);
 assert.match(ui,/data-p4="target"/);
 assert.match(ui,/\/api\/prompt-studio\/profiles/);
 assert.match(ui,/profile:q\('profile'\)\.value/);
 assert.match(ui,/target_frame:mode==='refine'/);
 assert.match(ui,/continuity:\{subject:q\('subject'\)\.value,style:q\('style'\)\.value\}/);
 assert.match(ui,/words_approx/);
 assert.match(ui,/not CLIP tokens/);
 assert.match(ui,/for\(const key of \['subject','style'\]\)/);
});
