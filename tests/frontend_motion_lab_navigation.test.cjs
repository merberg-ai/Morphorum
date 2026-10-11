'use strict';

const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const dist = path.join(__dirname, '..', 'frontend', 'dist');
const js = fs.readFileSync(path.join(dist, 'assets', 'animation.js'), 'utf8');
const css = fs.readFileSync(path.join(dist, 'assets', 'animation.css'), 'utf8');
const html = fs.readFileSync(path.join(dist, 'index.html'), 'utf8');

test('Motion Lab includes Project Manager and ten shared-state tool panels', () => {
  const names = ['motion','projects','editor','composer','recording','curves','preview','audio','monitor','outputs'];
  assert.match(js, /const VISIBLE_ANIMATION_TABS = \['motion', 'projects', 'editor', 'composer', 'recording', 'curves', 'preview', 'audio', 'monitor', 'outputs'\]/);
  assert.match(js, /const names = \{/);
  for (const name of names) assert.match(js, new RegExp(name + ":", 'm'));
  assert.match(js, /panels\.motion\.appendChild\(motionIntro\)/);
  assert.match(js, /panels\[name\]\.appendChild\(card\)/);
  assert.match(js, /panels\.outputs\.appendChild\(wrapper\)/);
  assert.match(js, /mediaVault\.hidden = true/);
  assert.match(js, /mediaVault\.inert = true/);
  assert.match(css, /#animation-media-vault\s*\{display:none!important;\}/);
  assert.match(html, /data-view="animation"[^>]*>[^<]*<span class="nav-icon">[^<]*<\/span><span>Motion Lab<\/span>/);
  for (const name of names) assert.match(html, new RegExp('data-motion-nav="' + name + '"'));
});

test('Tool switching highlights the desktop sidebar, preserves selections, and safely stops recording', () => {
  const start = js.indexOf('  const ANIMATION_TAB_KEY = ');
  const end = js.indexOf('  function setupAnimationWorkspaceTabs() {', start);
  assert.ok(start >= 0 && end > start);
  const keys = ['motion','projects','editor','composer','recording','curves','preview','audio','monitor','outputs'];
  const item = key => ({ dataset: { animationTab:key, animationPanel:key, motionNav:key },
    tabIndex:-1, hidden:false, attrs:{},
    classList: { active:false, toggle(_,v) {this.active=v;} },
    setAttribute(k,v) {this.attrs[k]=v;}, removeAttribute(k) {delete this.attrs[k];} });
  const tabs=keys.map(item), panels=keys.map(item), sidebar=keys.map(item);
  const stored=[]; let stopReason=null; let curvePaused=0; let previewPaused=0;
  const context={
    qsa: selector => selector.includes('[data-animation-tab]') ? tabs :
      selector.includes('[data-motion-nav]') ? sidebar : panels,
    qs: () => null,
    localStorage:{ setItem:(k,v)=>stored.push([k,v]) },
    motionLabVisual:{pause(){curvePaused++;}},
    motionFramePlayer:{pause(){previewPaused++;}},
    motionLabRecorder:{active:false},
    motionLabStopRecording:reason=>{stopReason=reason;},
  };
  vm.runInNewContext(js.slice(start,end)+'\nthis.selectTab=showAnimationTab;',context);
  context.selectTab('curves');
  assert.equal(panels[5].hidden,false);
  assert.equal(sidebar[5].attrs['aria-current'],'page');
  assert.equal(previewPaused,1);
  context.motionLabRecorder.active=true;
  context.selectTab('monitor');
  assert.equal(stopReason,'tab-change');
  assert.equal(sidebar[8].attrs['aria-current'],'page');
  assert.equal(stored.at(-1)[1],'monitor');
  context.motionLabRecorder.active=false;
  context.selectTab('media');
  assert.equal(panels[0].hidden,false);
  assert.equal(stored.at(-1)[1],'motion');
  assert.ok(curvePaused >= 1);
});

test('Motion Lab preserves its introduction and preview without redundant Editor shortcuts', () => {
  assert.match(html, /id="animation-motion-lab-intro"/);
  assert.doesNotMatch(html, /id="animation-motion-lab-edit-3d"/);
  assert.doesNotMatch(html, /id="animation-motion-lab-edit-timeline"/);
  assert.equal((html.match(/class="card glass animation-motion-preview-card"/g) || []).length, 1);
  assert.equal((html.match(/id="animation-generate-motion-preview"/g) || []).length, 1);
  assert.doesNotMatch(js, /#animation-motion-lab-edit-3d/);
  assert.doesNotMatch(js, /#animation-motion-lab-edit-timeline/);
  assert.match(css, /#animation-panel-motion \{display:grid;gap:14px;/);
  assert.match(css, /@media\(max-width:640px\)\s*\{[^}]*\.animation-motion-lab-intro/);
});


test('Motion Lab preview is usable without a separately uploaded image', () => {
  assert.match(js, /if \(preview\) preview\.disabled = !state\.project \|\| Boolean\(state\.motionJobId\)/);
  assert.match(js, /if \(!state\.project \|\| state\.motionJobId \|\| motionPreviewStarting/);
  assert.match(js, /animationMode\(\) !== '3d'/);
  assert.match(html, /built-in calibration grid immediately/);
  assert.match(html, /built-in calibration grid immediately/);
  assert.match(html, /An uploaded reference is optional/);
  assert.doesNotMatch(js, /if \(preview\) preview\.disabled = [^;]*!hasSource/);
});


test('ML0 exposes draft motion layer presets with preview and explicit timeline apply', () => {
  for (const id of [
    'animation-motion-lab-composer', 'animation-motion-lab-preset',
    'animation-motion-lab-strength', 'animation-motion-lab-cycle',
    'animation-motion-lab-fade', 'animation-motion-lab-start',
    'animation-motion-lab-end', 'animation-motion-lab-blend',
    'animation-motion-lab-add', 'animation-motion-lab-clear',
    'animation-motion-lab-layer-list', 'animation-motion-lab-apply',
    'animation-motion-lab-preview-draft',
  ]) {
    assert.equal((html.match(new RegExp('id="' + id + '"', 'g')) || []).length, 1);
  }
  assert.match(js, /async function motionLabPreviewOrApply\(apply,/);
  assert.match(js, /state\.project\.motion_lab\?\.layers/);
  assert.match(js, /body: JSON\.stringify\(payload\)/);
  assert.match(js, /await generateMotionPreview\(result\.project\)/);
  assert.match(js, /await loadTimeline\(\)/);
  assert.match(js, /const needsLayers = id !== 'animation-motion-lab-add'/);
  assert.match(css, /\.animation-motion-lab-fields \{display:grid;/);
});


test('Camera Composer and Camera Preview receive independent workspace panels', () => {
  assert.match(js, /\['composer', '#animation-motion-lab-composer'\]/);
  assert.match(js, /\['preview', '\.animation-motion-preview-card'\]/);
  assert.match(js, /\['recording', '#animation-motion-lab-recording'\]/);
  assert.match(js, /const toolGrid = document\.createElement\('div'\)/);
  assert.match(js, /button\.dataset\.motionOpen = name/);
  assert.match(js, /showAnimationTab\(name\)/);
  assert.match(html, /id="animation-motion-lab-enable-3d"/);
  assert.match(html, /id="animation-motion-lab-cycle"[^>]*value="2"/);
  assert.match(html, /id="animation-motion-lab-fade"[^>]*value="\.1"/);
});

test('Manual Editor motion edits do not block draft previews, apply needs explicit rebase', () => {
  const start = js.indexOf('  async function motionLabPreviewOrApply(apply,');
  const end = js.indexOf('  // Motion Lab is first-class;', start);
  const workflow = js.slice(start, end);
  assert.ok(start >= 0 && end > start);
  assert.match(workflow, /if \(!apply\) payload\.project = collectProject\(\)/);
  assert.match(workflow, /Camera schedules changed since Motion Lab/);
  assert.match(workflow, /payload\.rebase_current = true/);
  assert.match(workflow, /window\.MorphorumDialog\.confirm/);
  assert.match(workflow, /Save Editor changes before applying Motion Lab/);
  assert.doesNotMatch(workflow, /if \(state\.dirty\)\s*\{\s*motionLabNotify\('Save current Editor changes/);
  assert.match(js, /animation-motion-lab-enable-3d'\)\?\.addEventListener\('click'/);
});


test('Motion Lab can edit previously saved preset layers without destructive remove/readd', () => {
  assert.match(js, /let motionLabEditingIndex = -1/);
  assert.match(js, /edit\.textContent = 'Edit'/);
  assert.match(js, /motionLabEditingIndex = index/);
  assert.match(js, /cycle: layer\.cycle_seconds/);
  assert.match(js, /motionLabDraftLayers\[motionLabEditingIndex\] = entry/);
  assert.match(js, /motionLabEditingIndex < 0 \? '\+ Add Preset Layer' : 'Update Selected Layer'/);
  assert.match(css, /\.animation-motion-lab-layer-actions \{display:flex;/);
});


test('Motion Curves and path retain original controls in their own full-width panel', () => {
  for(const id of ['animation-motion-lab-visual','animation-motion-lab-curves',
    'animation-motion-lab-path','animation-motion-lab-play','animation-motion-lab-loop',
    'animation-motion-lab-frame','animation-motion-lab-axis-readout',
    'animation-motion-lab-update-curves']) {
    assert.equal((html.match(new RegExp('id="' + id + '"','g')) || []).length,1);
  }
  assert.match(js, /\['curves', '#animation-motion-lab-visual'\]/);
  assert.match(js, /new window\.MorphorumMotionLabVisualizer\(\)/);
  assert.match(js, /motionLabVisual\?\.setData\(result\.diagnostics\)/);
  assert.match(js, /motionLabVisual\?\.invalidate\(\)/);
  assert.match(js, /motionLabPreviewOrApply\(false, \{ curvesOnly: true \}\)/);
  assert.match(css, /\.animation-motion-lab-visual-grid \{display:grid;/);
});

test('ML1 draft layers support undo, redo, enable/disable and reordering', () => {
  assert.match(js, /function commitMotionLabDraft\(\)/);
  assert.match(js, /function restoreMotionLabDraft\(direction\)/);
  assert.match(js, /motionLabDraftLayers\[index\]\.enabled = enabled\.checked/);
  assert.match(js, /Move layer earlier/);
  assert.match(js, /Move layer later/);
  assert.match(js, /motionLabHistory\.slice\(0, motionLabHistoryIndex \+ 1\)/);
  assert.match(js, /motionLabHistoryIndex = motionLabHistory\.length - 1/);
  assert.match(js, /input\.id\.startsWith\('animation-motion-lab-'\)/);
});

test('Audio Motion shares the Motion Lab layer stack, with direct route to curves', () => {
  assert.match(js, /\['audio', '#animation-motion-lab-audio'\]/);
  assert.match(js, /panels\.audio\.prepend\(audioIntro\)/);
  assert.match(js, /id="animation-audio-back-motion"/);
  assert.match(js, /id="animation-audio-review-motion"/);
  assert.match(js, /showAnimationTab\('curves'\)/);
  assert.match(js, /data-motion-quick-target="animation-motion-lab-apply"/);
  assert.match(js, /if \(apply && !apply\.disabled\) apply\.click\(\)/);
  assert.match(js, /'animation-motion-lab-audio'\]\.includes\(card\.id\)/);
  assert.equal((html.match(/id="animation-motion-lab-audio"/g)||[]).length,1);
  assert.match(css, /overflow-x:auto/);
});


test('Floating Motion Lab shortcuts navigate before acting and keep Stop usable', () => {
  const first = js.indexOf('  function motionLabSyncQuickActions() {');
  const last = js.indexOf('  let motionLabPunchContext = null;', first);
  assert.ok(first >= 0 && last > first, 'quick action functions must be present');
  const calls = [];
  const navigated = [];
  const originals = new Map([
    ['animation-motion-lab-record', {disabled:false}],
    ['animation-motion-lab-stop-recording', {disabled:true}],
    ['animation-motion-lab-update-curves', {disabled:false}],
    ['animation-motion-lab-preview-draft', {disabled:false}],
    ['animation-motion-lab-apply', {disabled:false}],
    ['animation-start-render', {disabled:false}],
  ]);
  for (const [id, original] of originals) original.click = () => {
    calls.push({id, page:navigated.at(-1) || null});
  };
  const makeElement = () => ({
    dataset:{}, children:[], disabled:false, attrs:{},
    appendChild(child) {this.children.push(child);},
    addEventListener(type, handler) {if(type === 'click') this.click = handler;},
    setAttribute(k,v) {this.attrs[k] = v;},
  });
  const dockPanel = makeElement();
  const context = {
    document: {createElement:makeElement},
    motionLabRecorder: {active:false},
    motionLabBusy:false,
    motionLabBusyAction:null,
    motionPreviewStarting:false,
    animationRenderStarting:false,
    motionLabDraftLayers:[],
    state:{project:{id:'test'},motionJobId:null},
    renderIsActive: () => false,
    showAnimationTab: name => navigated.push(name),
    qsa: selector => selector === '[data-motion-quick-target]' ? dockPanel.children[0]?.children.filter(c=>c.dataset.motionQuickTarget) || [] : [],
    qs: selector => originals.get(selector.slice(1)) || null,
  };
  vm.runInNewContext(js.slice(first,last)+
    '\nthis.setupQuick = motionLabSetupQuickActions;'+
    '\nthis.syncQuick = motionLabSyncQuickActions;',context);
  context.setupQuick(dockPanel);
  const buttons = dockPanel.children[0].children.filter(c=>c.dataset.motionQuickTarget);
  const action = id => buttons.find(c=>c.dataset.motionQuickTarget === id);
  assert.equal(buttons.length,6);
  assert.equal(action('animation-start-render').textContent,'Render Animation');
  for(const [id,page] of [
    ['animation-motion-lab-record','recording'],
    ['animation-motion-lab-update-curves','curves'],
    ['animation-motion-lab-preview-draft','preview'],
    ['animation-start-render','monitor'],
  ]) {
    action(id).click();
    assert.deepEqual(calls.at(-1),{id,page});
  }
  assert.equal(navigated.length,4, 'actions navigate once each');
  assert.equal(action('animation-motion-lab-apply').disabled,false);
  originals.get('animation-start-render').disabled=true;
  context.syncQuick();
  assert.equal(action('animation-start-render').disabled,true,
    'render shortcut obeys the same guarded render button');
  context.motionLabRecorder.active=true;
  originals.get('animation-motion-lab-stop-recording').disabled=false;
  context.syncQuick();
  assert.equal(action('animation-motion-lab-stop-recording').disabled,false);
  assert.equal(action('animation-motion-lab-record').disabled,true);
  assert.equal(action('animation-start-render').disabled,true);
  action('animation-motion-lab-stop-recording').click();
  assert.equal(calls.at(-1).id,'animation-motion-lab-stop-recording');
  assert.equal(navigated.length,4,'Stop does not navigate away from live recording');
  context.motionLabRecorder.active=false;
  originals.get('animation-motion-lab-stop-recording').disabled=true;
  originals.get('animation-start-render').disabled=false;
  context.motionPreviewStarting=true;
  context.syncQuick();
  assert.equal(action('animation-motion-lab-preview-draft').disabled,true);
  assert.equal(action('animation-motion-lab-preview-draft').dataset.running,'true');
  assert.equal(action('animation-motion-lab-preview-draft').textContent,'▶ Previewing…');
  assert.equal(action('animation-motion-lab-preview-draft').attrs['aria-busy'],'true');
  assert.equal(action('animation-start-render').disabled,true);
  context.motionPreviewStarting=false;
  context.state.motionJobId='preview-job';
  context.syncQuick();
  assert.equal(action('animation-motion-lab-update-curves').disabled,true);
  assert.equal(action('animation-motion-lab-preview-draft').dataset.running,'true');
  context.state.motionJobId=null;
  context.animationRenderStarting=true;
  context.syncQuick();
  assert.equal(action('animation-start-render').disabled,true);
  assert.equal(action('animation-start-render').dataset.running,'true');
  assert.equal(action('animation-start-render').textContent,'Rendering…');
  context.animationRenderStarting=false;
  context.motionLabBusy=true;
  context.motionLabBusyAction='curves';
  context.syncQuick();
  assert.equal(action('animation-motion-lab-update-curves').dataset.running,'true');
  assert.equal(action('animation-motion-lab-update-curves').textContent,'↻ Updating…');
  assert.equal(action('animation-motion-lab-apply').disabled,true);
  context.motionLabBusy=false;
  context.motionLabBusyAction=null;
  context.syncQuick();
  assert.equal(action('animation-motion-lab-preview-draft').disabled,false);
  assert.equal(action('animation-start-render').textContent,'Render Animation');
});

test('Curve toggles keep their native 16px dimensions after moving out of Overview', () => {
  assert.match(css, /#view-animation \.animation-motion-lab-edit-toggle input\[type="checkbox"\]/);
  assert.match(css, /#view-animation \.animation-motion-lab-loop input\[type="checkbox"\]/);
  assert.match(css, /#view-animation \.animation-motion-lab-layer-toggle input\[type="checkbox"\]/);
  assert.match(css, /width:16px;\s*height:16px;\s*min-width:16px;\s*min-height:16px;/);
  assert.match(css, /padding:0;\s*margin:0;\s*flex:0 0 16px;/);
  for(const id of ['animation-motion-lab-key-drag','animation-motion-lab-path-drag','animation-motion-lab-loop']) {
    assert.equal((html.match(new RegExp('id="' + id + '"', 'g')) || []).length,1);
  }
  assert.match(js, /\['animation-start-render', 'Render Animation'\]/);
  assert.match(js, /motionLabSyncQuickActions\(\);\s*\}\s*let motionFramePlayer/);
});

test('Themes drive button colors, interaction feedback and motion accessibility', () => {
  const app = fs.readFileSync(path.join(dist,'assets','app.css'),'utf8');
  const desktop = fs.readFileSync(path.join(dist,'assets','desktop.css'),'utf8');
  const application = fs.readFileSync(path.join(dist,'assets','app.js'),'utf8');
  assert.match(application,/root\.dataset\.theme = theme/);
  assert.match(app,/--button-primary-bg:\s*linear-gradient\(135deg,var\(--accent\)/);
  assert.match(app,/--button-secondary-hover:\s*color-mix\(in srgb,var\(--accent\)/);
  assert.match(app,/\.primary-button:hover:not\(:disabled\)/);
  assert.match(app,/\.secondary-button:active:not\(:disabled\)/);
  assert.match(app,/\.icon-button:active:not\(:disabled\)/);
  assert.match(app,/button:disabled\s*\{/);
  assert.match(app,/prefers-reduced-motion:\s*reduce/);
  assert.match(css,/#view-animation \.motion-lab-tool-card:hover:not\(:disabled\)/);
  assert.match(css,/#view-animation \.animation-workspace-nav button\.active/);
  assert.match(css,/button\[data-running="true"\]/);
  assert.match(css,/@keyframes motion-button-working/);
  assert.match(desktop,/#motion-lab-sidebar button:focus-visible/);
  assert.match(desktop,/#motion-lab-sidebar button\.active/);
});

test('Preview and render locks include pending API requests and active operations', () => {
  assert.match(js,/let motionPreviewStarting = false/);
  assert.match(js,/let animationRenderStarting = false/);
  assert.match(js,/const locked = motionLabBusy \|\| motionPreviewBusy \|\| renderBusy/);
  assert.match(js,/const isStop = id === 'animation-motion-lab-stop-recording'/);
  assert.match(js,/motionPreviewStarting = true;\s*motionLabSyncQuickActions\(\)/);
  assert.match(js,/animationRenderStarting = true;\s*motionLabSyncQuickActions\(\)/);
  assert.match(js,/motionPreviewStarting = false;\s*renderSourceState\(\)/);
  assert.match(js,/animationRenderStarting = false;\s*renderSourceState\(\)/);
  assert.match(js,/motionLabBusyAction = apply \? 'apply' : curvesOnly \? 'curves' : 'preview'/);
});

test('Project Manager uses saved metadata and protects deletion', () => {
  assert.match(html, /data-motion-nav="projects">Project Manager/);
  assert.match(js, /projects: 'Project Manager'/);
  assert.match(js, /setupProjectManager\(panels\.projects\)/);
  assert.match(js, /function renderProjectManager\(\)/);
  assert.match(js, /function projectManagerSummary\(item\)/);
  assert.match(js, /selected\.prompt_keyframes/);
  assert.match(js, /selected\.motion_layers/);
  assert.match(js, /new Date\(value \|\| ''\)/);
  assert.match(js, /String\(value \|\| ''\) === item\.name/);
  assert.match(js, /method: 'DELETE'/);
  assert.match(js, /method: 'PUT'/);
  assert.match(js, /await loadProject\(id\)/);
  assert.match(js, /if \(opened\) showAnimationTab\('editor'\)/);
  assert.match(js, /state\.dirty \|\| motionLabRecorder\?\.active/);
  assert.match(css, /\.animation-project-manager-layout\s*\{/);
  assert.match(css, /\.animation-project-manager-item\.active\s*\{/);
});
