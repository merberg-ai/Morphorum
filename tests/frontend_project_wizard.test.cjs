'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const root = path.join(__dirname, '..', 'frontend', 'dist');
const html = fs.readFileSync(path.join(root, 'index.html'), 'utf8');
const app = fs.readFileSync(path.join(root, 'assets', 'app.js'), 'utf8');
const modelJs = fs.readFileSync(path.join(root, 'assets', 'models.js'), 'utf8');
const anim = fs.readFileSync(path.join(root, 'assets', 'animation.js'), 'utf8');
const wizardJs = fs.readFileSync(path.join(root, 'assets', 'project-wizard.js'), 'utf8');
const appCss = fs.readFileSync(path.join(root, 'assets', 'app.css'), 'utf8');
const animCss = fs.readFileSync(path.join(root, 'assets', 'animation.css'), 'utf8');
const desktopCss = fs.readFileSync(path.join(root, 'assets', 'desktop.css'), 'utf8');

function fakeProject() {
  return {
    name: 'New Animation',
    animation: {max_frames: 120, fps: 24, width: 1024, height: 1024,
      mode: '2d', prompt_transition:'blend'},
    model: {model_id:'',family:'',variant:''},
    prompts:{'0':''},negative_prompts:{'0':''},
    generation:{sampler:'flowmatch_euler',steps:'0:(20)',guidance:'0:(0)',
      strength:'0:(0.65)',noise:'0:(0.02)',seed:-1,seed_behavior:'fixed'},
    cadence:{diffusion:'0:(1)'},
    motion:{angle:'0:(0)',zoom:'0:(1.0)',translation_x:'0:(0)',
      translation_y:'0:(0)',border_mode:'replicate'},
    camera_3d:{translation_x:'0:(0)',translation_y:'0:(0)',translation_z:'0:(0)',
      rotation_x:'0:(0)',rotation_y:'0:(0)',rotation_z:'0:(0)',fov:'0:(40)'},
    tracks:{unwanted:'not for post'},id:'template-id',
  };
}
function setup(fetchStub = null) {
  const stored = new Map();
  const listeners = {};
  const host = {innerHTML:'',classList:{add(){}},replaceChildren() {},append(){}};
  const window = {
    addEventListener:(name, fn)=>{listeners[name] = fn;},
    MorphorumDialog:{confirm:async()=>true},
    MorphorumToast:()=>{},
  };
  const context = {
    window, document:{createElement:()=>({}),querySelector:()=>null},
    sessionStorage:{setItem:(k,v)=>stored.set(k,v),
      removeItem:k=>stored.delete(k),getItem:k=>stored.get(k)||null},
    fetch:fetchStub || (async()=>{throw Error('Unexpected network call')}),
    console,
  };
  vm.runInNewContext(wizardJs, context);
  const Wizard = window.MorphorumProjectWizard;
  const instance = new Wizard({
    panel:host,
    onSaved:async()=>{},
    onNavigate:async()=>true,
  });
  instance.ready=true;
  instance.draft=fakeProject();
  instance.models=[{id:'model1',family:'zimage',variant:'turbo',name:'Z-Image-Turbo',
    kind:'checkpoints'}];
  instance.capabilities={zimage:{
    samplers:{default:'flowmatch_euler',options:[{id:'flowmatch_euler'}]},
    steps:{default:9},guidance:{default:0},
    default_resolution:{width:1024,height:1024},
  }};
  instance.render=()=>{};
  return {instance, stored, listeners, context};
}

test('version popup exposes safe links for live branch and commit', () => {
  for(const id of ['runtime-repository-link','runtime-branch-link','runtime-commit-link'])
    assert.match(html,new RegExp('id="'+id+'"'));
  assert.match(app,/branch\.split\('\/'\)\.map\(encodeURIComponent\)/);
  assert.match(app,/\^\[0-9a-f\]\{40\}\$/);
  assert.match(app,/link\.removeAttribute\('href'\)/);
  assert.match(appCss,/\.runtime-build-popover \.runtime-source-links a:hover/);
});
test('no-model warning responds only to completed scan and has actionable help', () => {
  assert.match(html,/id="model-setup-banner"[^>]+hidden/);
  assert.match(html,/id="model-setup-help"/);
  assert.match(app,/event\.detail\?\.loaded === true/);
  assert.match(app,/model\.kind === 'checkpoints'/);
  assert.match(app,/banner\.hidden = !loaded \|\| usable/);
  assert.match(modelJs,/new CustomEvent\('morphorum:models-updated'/);
  for(const id of ['model-setup-help-models','model-setup-help-settings',
    'model-setup-help-close']) assert.ok(html.includes('id="'+id+'"'));
  assert.match(desktopCss,/\.app-shell:has\(> \.model-setup-banner:not\(\[hidden\]\)\)/);
});
test('new project wizard has separate panel and all seven guided stages', () => {
  assert.match(html,/data-motion-nav="wizard">New Project Wizard/);
  assert.match(anim,/wizard: 'New Project Wizard'/);
  assert.match(anim,/new window\.MorphorumProjectWizard/);
  assert.match(html,/project-wizard\.js.*animation\.js/s);
  for(const title of ['Welcome & Name','Choose a Model','Animation Setup',
    'Prompts & Keyframes','Camera Motion','Generation Settings','Review & Save'])
    assert.ok(wizardJs.includes(title));
  assert.match(animCss,/#animation-panel-wizard/);
  assert.match(animCss,/@media\(max-width:720px\)/);
});
test('wizard validates missing name and model; preset edits native schedules', () => {
  const {instance}=setup();
  assert.equal(instance.validate(0),'');
  instance.draft.name='';
  assert.match(instance.validate(0),/Enter a project name/);
  instance.draft.name='My animation';
  assert.match(instance.validate(1),/Select a usable checkpoint/);
  instance.selectModel('model1');
  assert.equal(instance.draft.generation.steps,'0:(9)');
  assert.equal(instance.draft.generation.sampler,'flowmatch_euler');
  assert.equal(instance.validate(1),'');
  instance.configureCamera('spiral');
  assert.equal(instance.draft.animation.mode,'3d');
  assert.match(instance.draft.camera_3d.translation_z,/119/);
  assert.match(instance.draft.camera_3d.rotation_y,/119/);
  instance.configureCamera('still');
  assert.equal(instance.draft.camera_3d.translation_z,'0:(0)');
  instance.configureCamera('pan');
  assert.match(instance.draft.camera_3d.translation_x,/119/);
  assert.equal(instance.draft.motion.translation_x,'0:(0)');
  instance.configureCamera('zoom');
  assert.match(instance.draft.camera_3d.translation_z,/119/);
});
test('wizard is not persisted until final create and validates before POST', async () => {
  const posted=[];
  const fetchStub = async (url,options) => {
    posted.push({url,options});
    const result = url.endsWith('validate-schedules')
      ? {valid:true,issues:[]}
      : {project:{id:'my-animation-12345678',name:'My animation'}};
    return {ok:true,json:async()=>result};
  };
  const {instance,stored}=setup(fetchStub);
  let opened='';
  instance.onSaved=async id=>{opened=id;};
  instance.onNavigate=async()=>true;
  instance.draft.name='My animation';
  instance.selectModel('model1');
  instance.draft.prompts['0']='A haunted computer in a dark room';
  instance.nextPrompt='A haunted machine grows eyes';
  instance.nextFrame=40;
  await instance.save();
  assert.equal(posted.length,2);
  assert.match(posted[0].url,/validate-schedules/);
  assert.match(posted[1].url,/api\/animation\/projects$/);
  const payload=JSON.parse(posted[1].options.body);
  assert.equal(payload.name,'My animation');
  assert.equal(payload.id,undefined);
  assert.equal(payload.tracks,undefined);
  assert.equal(payload.prompts['40'],'A haunted machine grows eyes');
  assert.equal(opened,'my-animation-12345678');
  assert.equal(stored.size,0);
});
test('wizard never posts if validation is refused or a current Editor has unsaved changes',async()=>{
  let posts=0;
  const {instance}=setup(async()=>{
    posts++;
    return {ok:true,json:async()=>({valid:true,issues:[]})};
  });
  instance.draft.name='My animation';
  instance.selectModel('model1');
  instance.draft.prompts['0']='a cat';
  instance.onNavigate=async()=>false;
  await instance.save();
  assert.equal(posts,0);
  instance.onNavigate=async()=>true;
  instance.draft.generation.guidance='';
  await instance.save();
  assert.equal(posts,0);
});
