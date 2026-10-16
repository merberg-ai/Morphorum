'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const root=path.join(__dirname,'..','frontend','dist');
const js=fs.readFileSync(path.join(root,'assets','animation.js'),'utf8');
const html=fs.readFileSync(path.join(root,'index.html'),'utf8');
const css=fs.readFileSync(path.join(root,'assets','animation.css'),'utf8');
test('Preflight report and read-only action are visible with accessible status',()=>{
  for(const id of ['animation-preflight-check','animation-preflight-report',
    'animation-preflight-heading','animation-preflight-meta',
    'animation-preflight-issues','animation-preflight-fix']) {
    assert.equal((html.match(new RegExp('id="'+id+'"','g'))||[]).length,1,id);
  }
  assert.match(html,/aria-label="Pre-render validation results" aria-live="polite"/);
  assert.match(js,/async function runRenderPreflight\(project\)/);
  assert.match(js,/api\('\/api\/animation\/renders\/preflight'/);
  assert.match(js,/issue\.severity === 'warning'/);
  assert.match(css,/\.animation-preflight-report\[data-state="error"\]/);
});
test('Render preflight runs before submission, blocks errors and confirms warnings',()=>{
  const start=js.indexOf('  async function startAnimationRender() {');
  const end=js.indexOf('  async function cancelAnimationRender()',start);
  const body=js.slice(start,end);
  assert.ok(start>=0&&end>start);
  assert.ok(body.indexOf('await runRenderPreflight(project)') <
    body.indexOf("api('/api/animation/renders',"));
  assert.match(body,/if \(!preflight\.valid\)/);
  assert.match(body,/if \(preflight\.warnings\)/);
  assert.match(body,/Render Anyway/);
  assert.match(body,/JSON\.stringify\(collectProject\(\)\) !== frozen/);
  assert.match(body,/animationRenderStarting = false/);
});
test('Fix controls focus existing inputs without saving or applying changes',()=>{
  const start=js.indexOf('  function showFirstPreflightFix() {');
  const end=js.indexOf('  async function runRenderPreflight(',start);
  const body=js.slice(start,end);
  assert.match(body,/showAnimationTab\('editor'\)/);
  assert.match(body,/setAnimationCardCollapsed\(card, false, \{ persist: false \}\)/);
  assert.match(body,/issue\.action === 'models'/);
  assert.doesNotMatch(body,/saveProject\(|startAnimationRender\(|motionLabPreviewOrApply\(/);
});
