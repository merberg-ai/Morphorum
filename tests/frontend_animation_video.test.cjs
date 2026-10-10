'use strict';

const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const directory = path.join(__dirname, '..', 'frontend', 'dist');
const html = fs.readFileSync(path.join(directory, 'index.html'), 'utf8');
const script = fs.readFileSync(path.join(directory, 'assets', 'animation.js'), 'utf8');

test('B5.4 video export controls are within existing Animation render section', () => {
  const card = html.indexOf('class="card glass animation-render-card"');
  const video = html.indexOf('id="animation-video-export"', card);
  const end = html.indexOf('class="card glass animation-inspector-card"', video);
  assert.ok(card > 0 && card < video && video < end);
  for (const control of [
    'animation-video-availability', 'animation-video-format',
    'animation-video-quality', 'animation-video-fps',
    'animation-export-video', 'animation-video-job-status',
    'animation-video-result', 'animation-video-playback',
    'animation-video-download',
  ]) assert.equal((html.match(new RegExp('id="' + control + '"', 'g')) || []).length, 1);
  assert.ok(html.includes('value="mp4"'));
  assert.ok(html.includes('value="webm"'));
  assert.ok(html.includes('value="high"'));
  assert.ok(html.includes('value="balanced"'));
  assert.ok(html.includes('value="compact"'));
  assert.ok(html.includes('type="number" min="1" max="120"'));
  assert.ok(script.includes("'/api/animation/video/availability'"));
  assert.ok(script.includes("'/api/animation/video/jobs/'"));
  assert.ok(script.includes("'/videos'"));
  assert.ok(script.includes("'?inline=true'"));
});

test('B5.4 video export refuses unfinished renders and uses saved PNG export API', async () => {
  const start = script.indexOf('  async function startVideoExport() {');
  const end = script.indexOf('  function resetRenderUi() {', start);
  assert.ok(start > 0 && end > start);
  const inputs = {
    '#animation-video-fps': { value: '' },
    '#animation-video-format': { value: 'mp4' },
    '#animation-video-quality': { value: 'high' },
    '#animation-export-video': { disabled: false },
  };
  const requests = [];
  const context = {
    state: {
      project: { id: 'test-project' },
      renderJob: { id: 'test-render', status: 'rendering' },
      videoAvailability: { available: true }, videoJob: null,
      videoPollTimer: null, videoRenderId: '', videoExports: [],
    },
    qs: selector => inputs[selector] || null,
    api: async (url, options) => {
      requests.push({ url, options });
      return { id: 'video-1', status: 'queued' };
    },
    renderVideoExportState() {},
    pollVideoExport() {},
    toast() {},
    window: { clearTimeout() {} },
  };
  vm.runInNewContext(script.slice(start, end) +
    '\nthis.startExport = startVideoExport;', context);
  await context.startExport();
  assert.equal(requests.length, 0);
  context.state.renderJob.status = 'completed';
  await context.startExport();
  assert.equal(requests.length, 1);
  assert.equal(requests[0].url,
    '/api/animation/renders/test-project/test-render/video');
  assert.equal(requests[0].options.method, 'POST');
  assert.deepEqual(JSON.parse(requests[0].options.body),
    { format: 'mp4', quality: 'high', fps: null });
  inputs['#animation-video-fps'].value = '121';
  await context.startExport();
  assert.equal(requests.length, 1, 'invalid FPS must never reach the server');
});


test('B5.5 displays bounded render summary and read-only JSON report link', () => {
  assert.equal((html.match(/id="animation-performance-summary"/g) || []).length, 1);
  assert.equal((html.match(/id="animation-performance-stats"/g) || []).length, 1);
  assert.equal((html.match(/id="animation-performance-report"/g) || []).length, 1);
  const begin = script.indexOf('  function renderPerformanceSummary(job) {');
  const end = script.indexOf('  function renderVideoExportState() {', begin);
  assert.ok(begin > 0 && end > begin);
  const attrs = {};
  const dom = {
    '#animation-performance-summary': { hidden: true },
    '#animation-performance-stats': { textContent: '' },
    '#animation-performance-report': {
      href: '',
      removeAttribute(attribute) { attrs[attribute] = true; },
    },
  };
  const context = { qs: key => dom[key] || null };
  vm.runInNewContext(
    script.slice(begin, end) + '\nthis.paint = renderPerformanceSummary;',
    context,
  );
  context.paint({
    id: 'run-4', project_id: 'scene-1',
    performance: {
      frames_observed: 15, diffusion_anchors: 5,
      average_anchor_diffusion_seconds: 5.2,
      maximum_allocated_gib: 14.2,
      maximum_reserved_gib: 15.1,
      maximum_peak_allocated_gib: 15.36,
      maximum_active_gib: 14.0,
      allocator_backend: 'native',
      allocation_retries: 2,
      oom_count: 0,
      maximum_resident_loras: 3,
      pipeline_device: 'cuda', optimization: 'native-gpu',
      slow_anchor_frames: [9],
    },
  });
  assert.equal(dom['#animation-performance-summary'].hidden, false);
  assert.match(dom['#animation-performance-stats'].textContent, /avg diffusion 5\.20s/);
  assert.match(dom['#animation-performance-stats'].textContent, /allocator peak 15\.36 GiB/);
  assert.match(dom['#animation-performance-stats'].textContent, /max active 14\.00 GiB/);
  assert.match(dom['#animation-performance-stats'].textContent, /allocator native/);
  assert.match(dom['#animation-performance-stats'].textContent, /alloc retries 2/);
  assert.match(dom['#animation-performance-stats'].textContent, /resident LoRAs ≤ 3/);
  assert.match(dom['#animation-performance-stats'].textContent, /slow anchors 9/);
  assert.equal(dom['#animation-performance-report'].href,
    '/api/animation/renders/scene-1/run-4/performance');
  context.paint({ id: 'run-2', project_id: 'scene-1', performance: {} });
  assert.equal(dom['#animation-performance-summary'].hidden, true);
  assert.equal(attrs.href, true);
});


test('high-resolution animation submits immediately without a 512px confirmation', async () => {
  const begin = script.indexOf('  async function startAnimationRender() {');
  const end = script.indexOf('  async function cancelAnimationRender() {', begin);
  assert.ok(begin >= 0 && end > begin);
  assert.ok(!script.includes('confirmHigherResolutionRender('));
  assert.ok(!script.includes('High-resolution render warning'));
  const submits = [];
  let prompts = 0;
  let renderId = 0;
  const startButton = { disabled: false, classList: { add() {} } };
  const context = {
    state: { project: { id: 'test' }, renderJobId: null },
    renderIsActive: () => false,
    collectProject: () => ({ id: 'test', animation: { width: 1024, height: 1024 } }),
    qs: selector => selector === '#animation-start-render' ? startButton : null,
    api: async (url, options) => {
      if (url === '/api/system/gpu-memory') throw Error('Must not poll GPU memory');
      assert.equal(url, '/api/animation/renders');
      submits.push(JSON.parse(options.body).project.animation);
      return { id: 'job-' + ++renderId, status: 'queued' };
    },
    renderAnimationJob() {},
    showAnimationTab() {},
    loadRenderHistory: async () => {},
    pollAnimationRender() {},
    toast() {},
    window: {
      MorphorumDialog: {
        confirm: async () => { prompts++; return false; },
      },
    },
  };
  vm.runInNewContext(script.slice(begin, end) +
    '\nthis.start = startAnimationRender;', context);
  await context.start();
  assert.equal(submits.length, 1);
  assert.equal(submits[0].width, 1024);
  assert.equal(submits[0].height, 1024);
  assert.equal(prompts, 0);
  assert.equal(startButton.disabled, true);
  assert.equal(context.state.renderJobId, 'job-1');
});


test('hybrid anchor inputs are opt-in and persisted through project save', () => {
  for (const id of [
    'animation-hybrid-render-enabled', 'animation-hybrid-offset',
    'animation-hybrid-composite-enabled', 'animation-hybrid-composite-opacity',
    'animation-hybrid-source', 'animation-hybrid-frame-slider',
  ]) assert.equal((html.match(new RegExp('id="' + id + '"', 'g')) || []).length, 1);
  assert.match(html, /Use extracted video frames for animation diffusion anchors/);
  assert.match(script, /project\.hybrid\?\.enabled === true/);
  assert.match(script, /offset_frames: Number\(qs\('#animation-hybrid-offset'\)/);
  assert.match(script, /enabled: Boolean\(qs\('#animation-hybrid-render-enabled'\)\?\.checked\)/);
  assert.match(script, /function hybridRestoreProjectFrames\(/);
  assert.match(script, /markDirty\(\)/);
  assert.match(script, /await api\(hybridBase\(\) \+ '\/hybrid-frames'\)/);
});

test('source-over video compositing has independent opt-in schedule controls', () => {
  assert.match(html, /Composite source video over rendered frames/);
  assert.match(html, /Video opacity schedule/);
  assert.match(script, /project\.hybrid\?\.composite_enabled === true/);
  assert.match(script, /project\.hybrid\?\.composite_opacity \?\? '0:\(0\.35\)'/);
  assert.match(script, /composite_enabled: Boolean\(qs\('#animation-hybrid-composite-enabled'\)\?\.checked\)/);
  assert.match(script, /composite_opacity: qs\('#animation-hybrid-composite-opacity'\)\?\.value/);
});
