'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const dist = path.join(__dirname, '..', 'frontend','dist');
const source = fs.readFileSync(path.join(dist,'assets','animation.js'),'utf8');
const html = fs.readFileSync(path.join(dist,'index.html'),'utf8');
const css = fs.readFileSync(path.join(dist,'assets','animation.css'),'utf8');

function makePlanner() {
  const begin = source.indexOf('  const MOTION_WORKFLOW_LABELS = ');
  const end = source.indexOf("  const ANIMATION_TAB_KEY = ", begin);
  assert.ok(begin >= 0 && end > begin);
  const scope = {};
  vm.runInNewContext(source.slice(begin,end) +
    '\nthis.plan=motionWorkflowPlan;\nthis.sync=syncMotionWorkflowGuide;',scope);
  return scope;
}

test('No-project workflow points to creation and selection, never a locked Editor', () => {
  const {plan} = makePlanner();
  const empty = plan('editor', false);
  assert.equal(empty.primary.tab,'projects');
  assert.equal(empty.secondary.tab,'wizard');
  assert.equal(plan('motion',false).primary.tab,'projects');
  assert.equal(plan('projects',false).primary.tab,'wizard');
  assert.equal(plan('not-a-tab',false).current,'motion');
});

test('Project workflow routes keep existing tool destinations and do not perform actions', () => {
  const {plan} = makePlanner();
  const expectations = {
    editor:'composer', composer:'curves', recording:'curves',
    curves:'preview', preview:'monitor', monitor:'outputs',
    outputs:'editor', audio:'curves', 'motion-import':'curves',
  };
  for (const [tab,target] of Object.entries(expectations)) {
    assert.equal(plan(tab,true).primary.tab,target,tab);
  }
  assert.match(source, /if \(target && VISIBLE_ANIMATION_TABS\.includes\(target\)\) showAnimationTab\(target\)/);
  const start = source.indexOf("qs('#animation-workflow-guide')?.addEventListener");
  const route = source.slice(start,start+360);
  assert.doesNotMatch(route, /saveProject|startAnimationRender|motionLabPreviewOrApply|loadProject/);
});

test('Workflow bar is present once and exposes current context, project and real buttons', () => {
  assert.equal((html.match(/id="animation-workflow-guide"/g)||[]).length,1);
  for(const id of ['animation-workflow-current','animation-workflow-project',
      'animation-workflow-hint','animation-workflow-primary','animation-workflow-secondary']) {
    assert.equal((html.match(new RegExp('id="' + id + '"','g'))||[]).length,1,id);
  }
  assert.match(html,/aria-label="Motion Lab next steps"/);
  assert.match(source,/syncMotionWorkflowGuide\(\);/);
  assert.match(source,/state\.dirty \? ' · Unsaved Editor changes' : ' · Saved project'/);
  assert.match(css, /@media\(max-width:480px\)/);
  assert.match(css, /@media\(max-width:360px\)/);
});

test('Wayfinder display derives from the selected workspace and dirtiness only', () => {
  const scope = makePlanner();
  const nodes = new Map();
  function node(id) {
    if(!nodes.has(id)) nodes.set(id,{textContent:'',dataset:{},setAttribute(name,value){this[name]=value;}});
    return nodes.get(id);
  }
  scope.qs = sel => sel === '#animation-workflow-guide' ? {} :
    sel === '#animation-name' ? {value:'Night Ride'} : node(sel);
  scope.animationTab='composer';
  scope.state={project:{id:'night-1',name:'Night Ride'},dirty:true};
  scope.sync();
  assert.equal(node('#animation-workflow-current').textContent,'Camera Composer');
  assert.match(node('#animation-workflow-project').textContent,/Night Ride · Unsaved Editor changes/);
  assert.equal(node('#animation-workflow-primary').dataset.workflowTab,'curves');
  scope.state.project=null;
  scope.sync();
  assert.equal(node('#animation-workflow-primary').dataset.workflowTab,'projects');
  assert.equal(node('#animation-workflow-secondary').dataset.workflowTab,'wizard');
});
