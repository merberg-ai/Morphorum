'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.join(__dirname,'..','frontend','dist');
const read = name => fs.readFileSync(path.join(root,name),'utf8');

function makeNode(tag='option') {
  return {
    tag,children:[],value:'',label:'',textContent:'',disabled:false,
    appendChild(child){this.children.push(child);},
    replaceChildren(...children){this.children=children;},
    querySelectorAll(selector) {
      const walk = node => [
        ...(node.tag===selector?[node]:[]),
        ...node.children.flatMap(walk),
      ];
      return this.children.flatMap(walk);
    },
  };
}
function createResolution() {
  const context={window:{},document:{createElement:makeNode}};
  vm.runInNewContext(read('assets/resolution.js'),context);
  return context.window.MorphorumResolution;
}
const r=createResolution();
const model={supported:true,default_resolution:{width:1024,height:1024},resolutions:[
  {label:'Portrait 2:3',width:832,height:1216},
  {label:'Landscape 3:2',width:1216,height:832},
]};

test('preset catalog includes model recommendations, square previews and landscape/portrait 480p through 1440p',()=>{
  const sizes=r.optionsFor(model,'sdxl');
  const lookup=label=>sizes.find(item=>item.label.startsWith(label));
  assert.equal(lookup('480p landscape').value,'848x480');
  assert.equal(lookup('480p portrait').value,'480x848');
  assert.equal(lookup('720p landscape').value,'1280x720');
  assert.equal(lookup('720p portrait').value,'720x1280');
  assert.equal(lookup('1080p landscape').value,'1920x1080');
  assert.equal(lookup('1080p portrait').value,'1080x1920');
  assert.equal(lookup('1440p landscape').value,'2560x1440');
  assert.equal(lookup('1440p portrait').value,'1440x2560');
  assert.equal(lookup('Portrait 2:3').value,'832x1216');
  assert.equal(lookup('512px square').value,'512x512');
  assert.equal(new Set(sizes.map(item=>item.value)).size,sizes.length);
  assert.equal(sizes.at(0).value,'1024x1024');
});
test('model-aware 1080p presets use divisible-by-16 dimensions on Flux and Z-Image',()=>{
  for(const family of ['flux','zimage']){
    const sizes=r.optionsFor(model,family);
    const horizontal=sizes.find(p=>p.label.startsWith('1080p landscape'));
    const vertical=sizes.find(p=>p.label.startsWith('1080p portrait'));
    assert.equal(horizontal.value,'1920x1088');
    assert.equal(vertical.value,'1088x1920');
    assert.match(horizontal.label,/model-aligned/);
    assert.match(horizontal.label,/high VRAM/);
    for(const {width,height} of sizes){
      assert.equal(width%16,0);
      assert.equal(height%16,0);
    }
  }
});
test('select, manual custom, and chosen preset update dimensions without rewriting arbitrary values',()=>{
  const select=makeNode('select');
  r.populate(select,model,'sdxl','1024','1024');
  assert.equal(select.disabled,false);
  assert.equal(select.value,'1024x1024');
  assert.equal(select.querySelectorAll('option').at(-1).value,'custom');
  r.sync(select,944,688);
  assert.equal(select.value,'custom');
  const w={value:'944'},h={value:'688'};
  assert.equal(r.apply(select,w,h),false);
  assert.equal(w.value,'944');
  select.value='1920x1080';
  assert.equal(r.apply(select,w,h),true);
  assert.equal(w.value,'1920');
  assert.equal(h.value,'1080');
  r.sync(select,w.value,h.value);
  assert.equal(select.value,'1920x1080');
  r.populate(select,{},'','944','688');
  assert.equal(select.disabled,true);
  assert.equal(select.querySelectorAll('option')[0].value,'');
});
test('guidance explains compatibility and memory pressure rather than inventing model limits',()=>{
  const node={textContent:''};
  r.guidance(node,'flux',1920,1080);
  assert.match(node.textContent,/multiples of 16/);
  r.guidance(node,'flux',1920,1088);
  assert.match(node.textContent,/more GPU memory/);
  r.guidance(node,'sdxl',848,480);
  assert.match(node.textContent,/848 × 480/);
  r.guidance(node,'',848,480);
  assert.match(node.textContent,/Choose a model/);
});
test('both workspaces invoke the same picker and preserve editable width and height',()=>{
  const html=read('index.html');
  const image=read('assets/image.js');
  const anim=read('assets/animation.js');
  assert.ok(html.indexOf('assets/resolution.js')<html.indexOf('assets/image.js'));
  assert.ok(html.indexOf('assets/resolution.js')<html.indexOf('assets/animation.js'));
  for(const key of ['image-resolution-preset','animation-resolution-preset','image-width','image-height','animation-width','animation-height'])
    assert.ok(html.includes('id="'+key+'"'));
  assert.match(image,/MorphorumResolution\.populate/);
  assert.match(image,/MorphorumResolution\.apply/);
  assert.match(image,/syncResolutionPreset\(\)/);
  assert.match(image,/saveImageDraft\(\)/);
  assert.match(anim,/populateResolutionPresets\(\)/);
  assert.match(anim,/MorphorumResolution\.apply/);
  assert.match(anim,/markDirty\(\{validate:true\}\)/);
});
