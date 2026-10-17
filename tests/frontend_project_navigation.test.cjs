'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const root=path.join(__dirname,'..','frontend','dist');
const html=fs.readFileSync(path.join(root,'index.html'),'utf8');
const app=fs.readFileSync(path.join(root,'assets','app.js'),'utf8');
const animation=fs.readFileSync(path.join(root,'assets','animation.js'),'utf8');

test('UX2.4 project destinations are in main navigation and absent from Motion Lab sidebar',()=>{
  const nav=html.match(/<nav class="main-nav glass"[\s\S]*?<\/nav>/)?.[0]||'';
  assert.ok(nav);
  for(const key of ['projects','wizard','editor']){
    assert.match(nav,new RegExp('data-project-nav="'+key+'"'));
    assert.doesNotMatch(nav,new RegExp('data-motion-nav="'+key+'"'));
    assert.match(animation,new RegExp("'"+key+"'"));
  }
});

test('UX2.4 primary nav reuses project panels and existing workspace navigation',()=>{
  assert.match(app,/\.main-nav \[data-project-nav\]/);
  assert.match(app,/switchView\('animation'\)/);
  assert.match(app,/button\.dataset\.projectNav/);
  assert.match(animation,/qs\('#animation-tab-' \+ name\)/);
  assert.match(animation,/panels\.editor\.appendChild\(layout\)/);
  assert.match(animation,/button\.hidden = true/);
  assert.match(animation,/button\.style\.display = 'none'/);
  assert.match(animation,/nav\.appendChild\(button\)/);
  assert.match(animation,/if \(name === 'wizard'\) void projectWizard\?\.open\(\)/);
});

test('UX2.4 Motion Lab entry opens overview and project links preserve selection',()=>{
  assert.match(app,/button\.dataset\.view === 'animation'/);
  assert.match(app,/qs\('#animation-tab-motion'\)\?\.click\(\)/);
  assert.match(animation,/button\.dataset\.projectNav === name/);
});

test('UX2.4 main-menu project targets have DOM-backed click destinations',()=>{
  for (const name of ['wizard','projects','editor']) {
    assert.match(app,/qs\('#animation-tab-' \+ button\.dataset\.projectNav\)\?\.click\(\)/);
    assert.match(animation,/button\.id = 'animation-tab-' \+ name/);
  }
  assert.match(animation,/button\.hidden = true/);
  assert.match(animation,/nav\.appendChild\(button\)/);
});

test('UX2.4 global page heading follows project destination',()=>{
  for(const id of ['animation-page-eyebrow','animation-page-title','animation-page-description'])
    assert.match(html,new RegExp('id="'+id+'"'));
  for(const title of ['Project Manager','New Project Wizard','Project Editor'])
    assert.ok(animation.includes("'"+title+"'"));
  assert.match(animation,/if \(title\) title\.textContent = pageHeading\[1\]/);
  assert.match(animation,/if \(description\) description\.textContent = pageHeading\[2\]/);
});

test('UX2.5 Motion Studio appears directly after Overview',()=>{
  const nav=html.match(/<div class="motion-lab-sidebar"[\s\S]*?<\/div>/)?.[0]||'';
  const overview=nav.indexOf('data-motion-nav="motion"');
  const audio=nav.indexOf('data-motion-nav="audio"');
  const composer=nav.indexOf('data-motion-nav="composer"');
  assert.ok(overview>=0 && audio>overview && composer>audio);
});
test('UX2.5 bulk trash uses confirmation and existing managed trash route',()=>{
  assert.match(animation,/animation-project-manager-select-visible/);
  assert.match(animation,/animation-project-manager-clear-selection/);
  assert.doesNotMatch(animation,/animation-project-manager-bulk-trash/);
  assert.match(animation,/projectManagerState\.bulkIds\.add\(item\.id\)/);
  assert.match(animation,/window\.MorphorumDialog\.confirm\(/);
  assert.match(animation,/async function projectManagerBulkTrash\(/);
  assert.match(animation,/encodeURIComponent\(item\.id\), \{method: 'DELETE'\}/);
  assert.match(animation,/failed\.push\(item\.name/);
});

test('UX2.5 bulk selection count and action state update in Project Manager only',()=>{
  const pm=animation.slice(animation.indexOf('  function renderProjectManager() {'),
    animation.indexOf('  async function projectManagerOpen() {'));
  const prompt=animation.slice(animation.indexOf('  function renderPromptRows() {'),
    animation.indexOf('  function renderProjectManager() {'));
  assert.match(pm,/bulkCount\.textContent = projectManagerState\.bulkIds\.size/);
  assert.match(pm,/trashButton\.textContent = projectManagerState\.bulkIds\.size > 1/);
  assert.doesNotMatch(prompt,/const bulkCount = qs\('#animation-project-manager-bulk-count'\)/);
  assert.match(pm,/checkbox\.addEventListener\('change'/);
});
test('Motion Studio analyzed WAV prompts before replacing export soundtrack',()=>{
  const analysis=animation.slice(animation.indexOf('  async function motionLabAnalyzeAudio() {'),
    animation.indexOf('  function motionLabAddAudio() {'));
  assert.match(analysis,/Replace project export soundtrack\?/);
  assert.match(analysis,/motion-import\/soundtrack/);
  assert.match(analysis,/Existing export soundtrack preserved/);
  assert.match(analysis,/audio motion was analyzed but export soundtrack attachment failed/);
});
test('Motion Studio can restore a saved soundtrack automatically without replacing an edited WAV',()=>{
  assert.match(animation,/!chosen && soundtrackAsset && animationTab === 'audio'/);
  assert.match(animation,/!projectMediaAssets\('motion_lab_wav'\)\.length/);
  assert.match(animation,/await motionLabUseProjectSoundtrack\(\)/);
});

test('UX2.5 one trash button routes multi-checkbox to batch and retains single confirmation',()=>{
  const single=animation.slice(animation.indexOf('  async function projectManagerTrash() {'),
    animation.indexOf('  async function projectManagerBulkTrash() {'));
  assert.match(single,/projectManagerState\.bulkIds\.size > 1/);
  assert.match(single,/await projectManagerBulkTrash\(\)/);
  assert.match(single,/projectManagerState\.bulkIds\.size === 1/);
  assert.match(single,/window\.MorphorumDialog\.prompt\(/);
  assert.match(single,/projectManagerState\.bulkIds\.delete\(item\.id\)/);
  assert.doesNotMatch(animation,/id="animation-project-manager-bulk-trash"/);
});
