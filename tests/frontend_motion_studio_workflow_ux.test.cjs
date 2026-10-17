'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const root = path.join(__dirname, '..', 'frontend', 'dist');
const source = fs.readFileSync(path.join(root, 'assets', 'animation.js'), 'utf8');
const styles = fs.readFileSync(path.join(root, 'assets', 'animation.css'), 'utf8');
const html = fs.readFileSync(path.join(root, 'index.html'), 'utf8');

const codeStart = source.indexOf('  // UX1/UX2: stage navigation');
const codeEnd = source.indexOf('  function setupAnimationWorkspaceTabs()', codeStart);
assert.ok(codeStart > 0 && codeEnd > codeStart, 'UX1/2 stage code must be present');

function fakeElement() {
  return {
    hidden: false, attrs: {}, tabIndex: -1, classList: {toggle() {}},
    setAttribute(key, value) {this.attrs[key] = value;},
    focus() {this.focused = true;},
    scrollIntoView() {this.scrolled = true;},
  };
}

function fixture() {
  const keys = ['source','analysis','detect','compose','review'];
  const modes = ['cues','channels','continuous','pulse'];
  const objects = new Map();
  const panel = {querySelector(selector) {
    if (selector.startsWith('[data-motion-studio-stage-status=')) return fakeElement();
    return null;
  }};
  for (const key of keys) {
    objects.set('#motion-studio-tab-' + key, fakeElement());
    objects.set('#motion-studio-stage-' + key, fakeElement());
  }
  for (const key of modes) {
    objects.set('#motion-studio-mode-' + key, fakeElement());
    objects.set('#motion-studio-composer-' + key, fakeElement());
  }
  objects.set('#motion-studio-author-hint', fakeElement());
  objects.set('#motion-studio-review-summary', fakeElement());
  objects.set('#animation-panel-audio', panel);
  const storage = new Map();
  const state = {project:{id:'demo'}, dirty:true};
  const draft = [{id:'one'}];
  const ctx = {
    state, motionLabAudioProjectId:null, motionLabAudioAnalysis:null,
    motionLabEditedEvents:null, motionLabDraftLayers:draft, qs:selector=>objects.get(selector)||null,
    localStorage:{
      setItem:(k,v)=>storage.set(k,v),
      getItem:k=>storage.get(k)||null,
    },
    window:{},
  };
  vm.runInNewContext(source.slice(codeStart, codeEnd), ctx);
  return {ctx,objects,storage,state,draft,keys,modes};
}

test('UX1 stage order follows the actual load-analyze-detect-compose-review workflow',()=>{
  const nav = source.slice(codeStart,codeEnd);
  const indices = [
    "['source', 'Load Audio'",
    "['analysis', 'Analyze WAV'",
    "['detect', 'Detect Beats'",
    "['compose', 'Create Motion'",
    "['review', 'Preview & Apply'",
  ].map(name=>nav.indexOf(name));
  assert.ok(indices.every(i=>i>=0));
  assert.deepEqual([...indices].sort((a,b)=>a-b),indices);
  assert.match(nav,/const sourceDock = qs\('#animation-audio-source-dock'\)/);
  assert.match(nav,/const analysis = qs\('#animation-audio-analysis-workspace'\)/);
  assert.match(nav,/const detection = \[\.\.\.\(audioCard\?\.querySelectorAll/);
  assert.match(nav,/summary'\)\?\.textContent === 'Beat detection'/);
  assert.match(nav,/const analyze = qs\('#animation-motion-lab-analyze-audio'\)/);
  assert.match(nav,/if \(analyze\) \{\s*const row = document\.createElement\('div'\);/);
});

test('UX2 switching stages preserves project and draft state with no API call',()=>{
  const f=fixture();
  f.ctx.motionStudioSelectStage('detect');
  assert.equal(f.objects.get('#motion-studio-stage-detect').hidden,false);
  for (const key of f.keys.filter(k=>k!=='detect')) {
    assert.equal(f.objects.get('#motion-studio-stage-'+key).hidden,true);
  }
  assert.equal(f.objects.get('#motion-studio-tab-detect').attrs['aria-selected'],'true');
  assert.equal(f.objects.get('#motion-studio-tab-detect').tabIndex,0);
  assert.equal(f.storage.get('morphorum.motionStudio.stage.v1'),'detect');
  assert.equal(f.state.project.id,'demo');
  assert.equal(f.state.dirty,true);
  assert.equal(f.draft.length,1);
  f.ctx.motionStudioSelectStage('analysis',{persist:false,navigate:false});
  assert.equal(f.objects.get('#motion-studio-stage-analysis').hidden,false);
  assert.equal(f.storage.get('morphorum.motionStudio.stage.v1'),'detect');
});

test('UX2 unsupported stage falls back to source and never discards user data',()=>{
  const f=fixture();
  f.ctx.motionStudioSelectStage('unknown');
  assert.equal(f.objects.get('#motion-studio-stage-source').hidden,false);
  assert.equal(f.storage.get('morphorum.motionStudio.stage.v1'),'source');
  assert.equal(f.draft[0].id,'one');
});

test('UX2 continuous motion remains an independent choice without a WAV',()=>{
  const f=fixture();
  f.ctx.motionStudioSelectAuthorMode('continuous');
  assert.equal(f.objects.get('#motion-studio-composer-continuous').hidden,false);
  for (const key of f.modes.filter(k=>k!=='continuous')) {
    assert.equal(f.objects.get('#motion-studio-composer-'+key).hidden,true);
  }
  assert.match(f.objects.get('#motion-studio-author-hint').textContent,/without a WAV/);
  assert.equal(f.storage.get('morphorum.motionStudio.authorMode.v1'),'continuous');
});

test('UX2 original live controls, cue editor and waveform move without cloning',()=>{
  assert.match(source,/if \(sourceDock\) stages\.source\.appendChild\(sourceDock\)/);
  assert.match(source,/if \(analysis\) stages\.analysis\.appendChild\(analysis\)/);
  assert.match(source,/if \(channels\) modeAreas\.channels\.appendChild\(channels\)/);
  assert.match(source,/if \(continuous\) modeAreas\.continuous\.appendChild\(continuous\)/);
  assert.match(source,/if \(audioCard\) modeAreas\.pulse\.appendChild\(audioCard\)/);
  assert.match(source,/if \(introActions\) stages\.review\.appendChild\(introActions\)/);
  assert.match(source,/if \(detectStage\) detectStage\.appendChild\(editor\)/);
  assert.match(source,/if \(cueStage\) cueStage\.appendChild\(panel\)/);
  assert.match(source,/motionStudioDockWaveform\(\)/);
  for (const id of ['animation-motion-lab-audio-file','animation-motion-lab-analyze-audio',
    'animation-motion-lab-add-audio']) {
    assert.equal((html.match(new RegExp('id="'+id+'"','g')) || []).length, 1, id);
  }
  // Apply shortcut is created exactly once in the Motion Studio template.
  assert.equal((source.match(/id="animation-audio-apply"/g)||[]).length, 1);
  assert.match(source,/motionStudioSelectStage\(motionStudioStage, \{persist:false, navigate:false\}\)/);
});

test('UX2 stage navigation is keyboard-accessible and works at phone widths',()=>{
  assert.match(source,/button\.setAttribute\('role', 'tab'\)/);
  assert.match(source,/stage\.setAttribute\('role', 'tabpanel'\)/);
  assert.match(source,/\['ArrowLeft', 'ArrowRight', 'Home', 'End'\]/);
  assert.match(styles,/#animation-panel-audio \.motion-studio-stage-nav \{\s*position:sticky/);
  assert.match(styles,/@media\(max-width:950px\)/);
  assert.match(styles,/@media\(max-width:640px\)/);
  assert.match(styles,/#animation-panel-audio \.motion-studio-stage\[hidden\]/);
});
