'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const root=path.join(__dirname,'..','frontend','dist');
const source=fs.readFileSync(path.join(root,'assets','animation.js'),'utf8');
const html=fs.readFileSync(path.join(root,'index.html'),'utf8');
const start=source.indexOf('  function evenlySpacedPromptFrames(');
const end=source.indexOf('  function redistributePromptKeyframes(',start);
assert.ok(start>=0 && end>start);
const spacing=Function(source.slice(start,end)+'; return evenlySpacedPromptFrames;')();

test('543 frames evenly distributes four and five prompts including both endpoints',()=>{
  assert.deepEqual(spacing(4,543),[0,181,361,542]);
  assert.deepEqual(spacing(5,543),[0,136,271,407,542]);
});
test('short animations refuse collisions and handle frame zero',()=>{
  assert.deepEqual(spacing(1,1),[0]);
  assert.deepEqual(spacing(2,2),[0,1]);
  assert.equal(spacing(3,2),null);
});
test('spacing stays increasing and on timeline for supported prompt counts',()=>{
  for(const frames of [2,3,5,120,543]){
    for(let count=1;count<=frames;count++){
      const result=spacing(count,frames);
      assert.equal(result.length,count);
      assert.equal(result[0],0);
      if(count>1) assert.equal(result[result.length-1],frames-1);
      assert.ok(result.every((v,i)=>v>=0&&v<frames&&(i===0||v>result[i-1])));
    }
  }
});
test('toolbar actions update draft without replacing prompt text',()=>{
  assert.match(html,/id="animation-evenly-space-prompts"/);
  assert.match(source,/animation-evenly-space-prompts'\)\?\.addEventListener\('click', evenlySpacePromptKeyframes\)/);
  const logic=source.slice(end,source.indexOf('  function inspectorFrameMax()',end));
  assert.match(logic,/markDirty\(\{validate:true\}\)/);
  assert.match(logic,/rows\.push\(createPromptRow\(0, '', ''\)\)/);
  assert.doesNotMatch(logic,/\.replaceChildren\(/);
});
