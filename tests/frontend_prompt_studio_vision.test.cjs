'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const ai=require('../frontend/dist/assets/prompt-studio-ai.js');
const script=fs.readFileSync(path.join(__dirname,'..','frontend','dist','assets',
  'prompt-studio-ai.js'),'utf8');

test('PS5.2 accepts only this project managed start image descriptor',()=>{
 const id='example-123';
 const good={kind:'source_image',id:'source-image',project_id:id,
   media_type:'image/png',sha256:'a'.repeat(64),bytes:1234,
   url:'https://attacker.invalid/never-use-me'};
 const got=ai.sourceAsset({assets:[good]},id);
 assert.deepEqual(got,{projectId:id,sha256:'a'.repeat(64),bytes:1234});
 assert.equal(JSON.stringify(got).includes('attacker'),false);
 assert.equal(ai.sourceAsset({assets:[{...good,project_id:'other'}]},id),null);
 assert.equal(ai.sourceAsset({assets:[{...good,kind:'soundtrack'}]},id),null);
 assert.equal(ai.sourceAsset({assets:[{...good,sha256:'bad'}]},id),null);
 assert.equal(ai.sourceAsset({assets:[{...good,media_type:'image/jpeg'}]},id),null);
});

test('PS5.2 description requires an explicit append and never rewrites source tracks',()=>{
 const story='A story unfolds.';
 const text='<lora:NotAnAdapter:1> icy futuristic valley';
 const result=ai.appendVisionDescription(story,text);
 assert.equal(story,'A story unfolds.');
 assert.match(result,/Visual reference from the attached start image/);
 assert.match(result,/icy futuristic valley/);
 assert.equal(ai.appendVisionDescription('x'.repeat(5998),text),null);
 assert.equal(ai.appendVisionDescription(story,' '),null);
});

test('PS5.2 UI previews managed assets and enforces consent, loopback and sha checks',()=>{
 assert.match(script,/data-p4="vision-preview"/);
 assert.match(script,/data-p4="vision-consent"/);
 assert.match(script,/data-p4="vision-analyze"/);
 assert.match(script,/data-p4="vision-description"/);
 assert.match(script,/\/media-inventory/);
 assert.match(script,/\/api\/prompt-studio\/ollama\/analyze-start-image/);
 assert.match(script,/source_sha256:sha,consent:true/);
 assert.match(script,/q\('vision-consent'\)\.checked=false/);
 assert.match(script,/isLoopbackEndpoint\(\)/);
 assert.match(script,/latest\.sha256!==sha/);
 assert.match(script,/q\('idea'\)\.value=next/);
 assert.match(script,/clearVisionResult\(\)/);
 assert.doesNotMatch(script,/vision.*(?:save_project|start_render)/i);
});
