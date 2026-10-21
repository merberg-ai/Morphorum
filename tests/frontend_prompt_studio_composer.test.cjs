'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const composer=require('../frontend/dist/assets/prompt-studio-composer.js');
const studio=require('../frontend/dist/assets/prompt-studio.js');
const bridge=require('../frontend/dist/assets/prompt-studio-bridge.js');
const blocks=()=>composer.blank();
const promptTracks=()=>({
 positive:{kind:'prompt',interpolation:'blend',keyframes:[
  {frame:0,value:'  exact <lora:Existing:0.8>  scene  '},
  {frame:40,value:'second scene'}]},
 negative:{kind:'prompt',interpolation:'hold',keyframes:[
  {frame:0,value:'grain'}]}
});
const create=(overrides={})=>({id:'a',scope:'global',frame:null,lane:'positive',
 kind:'text',placement:'before',enabled:true,label:'Style',text:'old film',...overrides});
const sampleSnapshot=()=>({ok:true,projectId:'project1',
 context:{name:'Test',model:{family:'sdxl',model_id:'model',variant:''},
   maxFrames:100,fps:24,startMode:'prompt',sourceImageName:''},
 promptTracks:promptTracks()});
test('PS3 global blocks preserve source substring and LoRA spelling exactly',()=>{
 const source=promptTracks(),before=JSON.stringify(source);
 const state=blocks();state.blocks.push(create());
 state.blocks.push(create({id:'b',scope:'frame',frame:40,text:'night',placement:'after'}));
 const outcome=composer.compile(state,source,100,'sdxl');
 assert.equal(outcome.ok,true);
 assert.deepEqual(outcome.changed.map(x=>x.frame),[0,40]);
 assert.equal(outcome.tracks.positive.keyframes[0].value,
   'old film,   exact <lora:Existing:0.8>  scene  ');
 assert.equal(outcome.tracks.positive.keyframes[1].value,
   'old film, second scene, night');
 assert.deepEqual(outcome.tracks.negative,source.negative);
 assert.equal(JSON.stringify(source),before);
 assert.equal(bridge.validateTracks(outcome.tracks,100).ok,true);
});
test('PS3 native LoRA directive with cached trigger text, duplicate diagnostics',()=>{
 const state=blocks();state.blocks.push(create({kind:'lora',id:'lora1',name:'Existing',
  family:'sdxl',model_id:'indexed-id',weight:0.55,triggers:['h0rr0rstyl3','style words']}));
 const result=composer.compile(state,promptTracks(),100,'sdxl');
 assert.equal(result.ok,true);
 assert.equal(result.warnings.length,1);
 assert.match(result.warnings[0],/Duplicate LoRA/);
 assert.match(result.tracks.positive.keyframes[1].value,
   /^<lora:Existing:0.55>, h0rr0rstyl3, style words, second scene$/);
 assert.equal(composer.compile(state,promptTracks(),100,'flux').code,'FAMILY');
});
test('PS3 refuses negative LoRAs, invalid family/weight, overlong text and scene mismatch',()=>{
 const state=blocks();state.blocks.push(create({kind:'lora',name:'Foo',model_id:'lora',
  family:'sdxl',weight:1,triggers:[],lane:'negative'}));
 assert.equal(composer.normalize(state,100).code,'LORA_LANE');
 const bad=blocks();bad.blocks.push(create({kind:'lora',name:'Foo',model_id:'lora',
  family:'sdxl',weight:Infinity,triggers:[]}));
 assert.equal(composer.normalize(bad,100).code,'LORA');
 const missing=blocks();missing.blocks.push(create({scope:'frame',frame:30}));
 assert.equal(composer.compile(missing,promptTracks(),100,'sdxl').code,'KEYFRAME');
 const long=blocks();long.blocks.push(create({text:'X'.repeat(32769)}));
 assert.equal(composer.normalize(long,100).code,'TEXT');
});
test('PS3 block order, activation, placement and deletion are reversible pure updates',()=>{
 let state=blocks();let r=composer.change(state,'add',create(),100);assert.equal(r.ok,true);
 state=r.composer;r=composer.change(state,'add',create({id:'b',text:'ghost',placement:'after'}),100);
 assert.equal(r.ok,true);
 state=r.composer;r=composer.change(state,'reorder',{id:'b',direction:-1},100);
 assert.deepEqual(r.composer.blocks.map(x=>x.id),['b','a']);
 state=r.composer;r=composer.change(state,'update',{id:'a',patch:{enabled:false}},100);
 assert.equal(r.composer.blocks.find(x=>x.id==='a').enabled,false);
 state=r.composer;r=composer.change(state,'remove',{id:'a'},100);
 assert.deepEqual(r.composer.blocks.map(x=>x.id),['b']);
 assert.equal(composer.change(r.composer,'remove',{id:'missing'},100).code,'NOT_FOUND');
});
test('PS3 draft save/read remains compatible with precomposer PS1.4 drafts',()=>{
 const d=studio.beginDraft(sampleSnapshot(),bridge);
 const original=studio.serializeDraft(d,'Story',bridge);
 assert.equal(original.ok,true);
 assert.deepEqual(original.record.composer,blocks());
 const old={...original.record};delete old.composer;
 const loaded=studio.restoreDraft(old,sampleSnapshot(),bridge);
 assert.equal(loaded.ok,true);
 assert.deepEqual(loaded.composer,blocks());
 d.composer.blocks.push(create());
 const saved=studio.serializeDraft(d,'New storyboard',bridge);
 assert.equal(saved.ok,true);
 assert.equal(saved.record.composer.blocks.length,1);
 const restored=studio.restoreDraft(saved.record,sampleSnapshot(),bridge);
 assert.equal(restored.ok,true);
 assert.equal(restored.composer.blocks[0].text,'old film');
 assert.equal(restored.compatible,true);
});
test('PS3 UI binds cached family catalog, exact preview and explicit draft-only commit',()=>{
 const script=fs.readFileSync(path.join(__dirname,'..','frontend','dist','assets','prompt-studio-composer.js'),'utf8');
 const host=fs.readFileSync(path.join(__dirname,'..','frontend','dist','assets','prompt-studio.js'),'utf8');
 const html=fs.readFileSync(path.join(__dirname,'..','frontend','dist','index.html'),'utf8');
 assert.match(html,/prompt-studio-composer\.js[^"]*" defer/);
 assert.ok(html.indexOf('prompt-studio-composer.js')<html.indexOf('prompt-studio.js'));
 assert.match(script,/\/api\/loras\?family=/);
 assert.match(script,/\/api\/civitai\/library-catalog/);
 assert.doesNotMatch(script,/\/api\/civitai\/library\/.*sync|\/api\/models\/scan/);
 assert.match(script,/data-p3="preview"/);
 assert.match(script,/data-p3="commit"/);
 assert.match(script,/onCommit\?\.\(p\.tracks\)/);
 assert.match(host,/composer:composed\.composer/);
 assert.match(host,/onCommit:next=>applyTracks\(next,'composer'\)/);
});
