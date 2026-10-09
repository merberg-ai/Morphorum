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


test('B6.0-P high-resolution render guard is advisory and uses live memory snapshot', async () => {
  const begin = script.indexOf('  function higherResolutionRenderRisk(project) {');
  const end = script.indexOf('  async function startAnimationRender()', begin);
  assert.ok(begin > 0 && end > begin);

  const messages = [];
  let requests = 0;
  const context = {
    api: async url => {
      requests += 1;
      assert.equal(url, '/api/system/gpu-memory');
      return {
        cuda: {
          free_gib: 3.25,
          allocated_gib: 11.5,
          reserved_gib: 12.0,
          allocator_backend: 'native',
        },
        windows_wddm: {
          available: true,
          dedicated_gib: 12.25,
          shared_gib: 0.5,
        },
      };
    },
    window: {
      confirm(message) {
        messages.push(message);
        return false;
      },
    },
  };

  vm.runInNewContext(
    script.slice(begin, end) +
      '\nthis.risk = higherResolutionRenderRisk;' +
      '\nthis.confirmRisk = confirmHigherResolutionRender;',
    context,
  );

  assert.equal(context.risk({ animation: { width: 512, height: 512 } }), null);
  assert.equal(
    await context.confirmRisk({ animation: { width: 512, height: 512 } }),
    true,
  );
  assert.equal(requests, 0, 'verified baseline should not query diagnostic counters');

  const risk = context.risk({ animation: { width: 1024, height: 1024 } });
  assert.equal(risk.pixel_ratio, 4);
  assert.equal(
    await context.confirmRisk({ animation: { width: 1024, height: 1024 } }),
    false,
  );
  assert.equal(requests, 1);
  assert.match(messages[0], /4\.00× the pixel count/);
  assert.match(messages[0], /advisory warning, not a VRAM estimate/);
  assert.match(messages[0], /3\.25 GiB free/);
  assert.match(messages[0], /12\.25 GiB dedicated/);
  assert.match(messages[0], /0\.50 GiB shared/);
});
