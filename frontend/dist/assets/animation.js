(() => {
  'use strict';

  const state = {
    project: null,
    projects: [],
    models: [],
    capabilities: {},
    path: '',
    dirty: false,
    loading: false,
    previewTimer: null,
    validationTimer: null,
    previewSequence: 0,
    motionJobId: null,
    motionPollTimer: null,
    renderJobId: null,
    renderJob: null,
    renderHistory: [],
    renderPollTimer: null,
    lastRenderFrameUrl: '',
    timeline: null,
    timelineSelection: null,
    timelineScale: 6,
    timelineBusy: false,
    timelineResizeTimer: null,
    depthModels: [],
    depthPreview: null,
    depthBusy: false,
    depthPollTimer: null,
    videoAvailability: null,
    videoExports: [],
    videoJob: null,
    videoRenderId: '',
    videoPollTimer: null,
    deforumImport: {
      content: '',
      filename: '',
      report: null,
      busy: false,
    },
  };

  const ANIMATION_CARD_STORAGE_KEY = 'morphorum.animation.cards.v1';

  function readAnimationCardState() {
    try {
      const parsed = JSON.parse(localStorage.getItem(ANIMATION_CARD_STORAGE_KEY) || '{}');
      return parsed && typeof parsed === 'object' ? parsed : {};
    } catch (_) {
      return {};
    }
  }

  function writeAnimationCardState(value) {
    try {
      localStorage.setItem(ANIMATION_CARD_STORAGE_KEY, JSON.stringify(value));
    } catch (_) {
      // Browser storage can be unavailable in private/restricted contexts.
    }
  }

  function animationCardKey(card, index) {
    if (card.dataset.animationCardKey) return card.dataset.animationCardKey;
    const heading = qs('h2', card)?.textContent || card.id || ('section-' + index);
    const slug = String(heading)
      .trim()
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-+|-+$/g, '') || ('section-' + index);
    card.dataset.animationCardKey = slug;
    return slug;
  }

  function setAnimationCardCollapsed(card, collapsed, { persist = true } = {}) {
    if (!card) return;
    const key = card.dataset.animationCardKey;
    card.classList.toggle('animation-card-collapsed', Boolean(collapsed));
    const content = qs('.animation-card-content', card);
    if (content) content.hidden = Boolean(collapsed);
    const toggle = qs('.animation-card-toggle', card);
    if (toggle) {
      toggle.textContent = collapsed ? '▸' : '▾';
      toggle.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
      toggle.title = collapsed ? 'Expand section' : 'Collapse section';
    }
    if (persist && key) {
      const stateValue = readAnimationCardState();
      stateValue[key] = Boolean(collapsed);
      writeAnimationCardState(stateValue);
    }
  }

  function setAllAnimationCards(collapsed) {
    qsa('#view-animation .animation-layout > article.card').forEach(card => {
      setAnimationCardCollapsed(card, collapsed);
    });
  }

  function setupAnimationAccordions() {
    const stored = readAnimationCardState();
    const mobile = window.matchMedia('(max-width: 720px)').matches;
    const mobileOpenByDefault = new Set([
      'project',
      'diffusion-cadence',
      'start-frame',
      '3d-depth',
      'visual-timeline',
      'animation-render',
    ]);

    qsa('#view-animation .animation-layout > article.card').forEach((card, index) => {
      if (card.dataset.animationAccordionReady === '1') return;
      card.dataset.animationAccordionReady = '1';
      const key = animationCardKey(card, index);
      const header = qs('.card-header', card);
      if (!header) return;

      const content = document.createElement('div');
      content.className = 'animation-card-content';
      const children = [...card.children].filter(child => child !== header);
      for (const child of children) content.appendChild(child);
      card.appendChild(content);

      const toggle = document.createElement('button');
      toggle.type = 'button';
      toggle.className = 'icon-button animation-card-toggle';
      toggle.setAttribute('aria-label', 'Collapse or expand section');
      header.appendChild(toggle);

      const defaultCollapsed = mobile && !mobileOpenByDefault.has(key);
      const collapsed = Object.prototype.hasOwnProperty.call(stored, key)
        ? Boolean(stored[key])
        : defaultCollapsed;
      setAnimationCardCollapsed(card, collapsed, { persist: false });

      toggle.addEventListener('click', event => {
        event.stopPropagation();
        setAnimationCardCollapsed(
          card,
          !card.classList.contains('animation-card-collapsed')
        );
      });

      header.addEventListener('click', event => {
        if (event.target.closest('button, input, select, textarea, a, label')) return;
        setAnimationCardCollapsed(
          card,
          !card.classList.contains('animation-card-collapsed')
        );
      });
    });
  }

  const SCHEDULE_INPUTS = {
    'motion.angle': '#animation-angle',
    'motion.zoom': '#animation-zoom',
    'motion.translation_x': '#animation-translation-x',
    'motion.translation_y': '#animation-translation-y',
    'camera_3d.translation_x': '#animation-3d-translation-x',
    'camera_3d.translation_y': '#animation-3d-translation-y',
    'camera_3d.translation_z': '#animation-3d-translation-z',
    'camera_3d.rotation_x': '#animation-3d-rotation-x',
    'camera_3d.rotation_y': '#animation-3d-rotation-y',
    'camera_3d.rotation_z': '#animation-3d-rotation-z',
    'camera_3d.fov': '#animation-3d-fov',
    'generation.strength': '#animation-strength',
    'generation.noise': '#animation-noise',
    'generation.steps': '#animation-steps',
    'generation.guidance': '#animation-guidance',
    'cadence.diffusion': '#animation-cadence',
  };

  // B5.3: conservative constant per-frame 3D motion schedules.
  // This does not alter existing presets, FOV, or project model state.
  const CAMERA_3D_PRESETS = Object.freeze({
    'still': { translation_x: 0, translation_y: 0, translation_z: 0, rotation_x: 0, rotation_y: 0, rotation_z: 0 },
    'dolly-in': { translation_z: 0.02 },
    'dolly-out': { translation_z: -0.02 },
    'orbit-left': { translation_x: -0.008, rotation_y: 0.18 },
    'orbit-right': { translation_x: 0.008, rotation_y: -0.18 },
    'pan-left': { rotation_y: -0.18 },
    'pan-right': { rotation_y: 0.18 },
    'tilt-up': { rotation_x: -0.18 },
    'tilt-down': { rotation_x: 0.18 },
  });
  const CAMERA_3D_MOTION_FIELDS = [
    'translation_x', 'translation_y', 'translation_z',
    'rotation_x', 'rotation_y', 'rotation_z',
  ];

  const INSPECTOR_INPUT_IDS = new Set([
    'animation-inspector-frame',
    'animation-inspector-slider',
    'animation-curve-field',
    'animation-timeline-frame',
    'animation-timeline-scrubber',
    'animation-timeline-track-select',
    'animation-timeline-scale',
    'animation-timeline-keyframe-frame',
    'animation-timeline-keyframe-value',
    'animation-timeline-interpolation',
    'animation-depth-model',
    'animation-depth-device',
    'animation-video-format',
    'animation-video-quality',
    'animation-video-fps',
    'animation-3d-preset',
    'animation-preview-highlight-holes',
  ]);

  const qs = (selector, root = document) => root.querySelector(selector);
  const qsa = (selector, root = document) => [...root.querySelectorAll(selector)];

  const toast = (title, message = '', type = 'info', timeout = 4200) => {
    if (window.MorphorumToast) {
      window.MorphorumToast(title, message, type, timeout);
    }
  };

  async function api(url, options = {}) {
    const response = await fetch(url, {
      headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
      ...options,
    });
    const type = response.headers.get('content-type') || '';
    const payload = type.includes('application/json') ? await response.json() : await response.text();
    if (!response.ok) {
      const detail = typeof payload === 'object' ? (payload.detail || JSON.stringify(payload)) : payload;
      throw new Error(detail || `${response.status} ${response.statusText}`);
    }
    return payload;
  }

  function isMobileTimeline() {
    return window.matchMedia('(max-width: 720px)').matches;
  }

  function renderDepthModels() {
    const select = qs('#animation-depth-model');
    if (!select) return;
    const current = select.value;
    select.replaceChildren();
    if (!state.depthModels.length) {
      const option = document.createElement('option');
      option.value = '';
      option.textContent = 'No depth estimators available';
      select.appendChild(option);
      return;
    }
    for (const model of state.depthModels) {
      const option = document.createElement('option');
      option.value = model.id;
      option.textContent = model.label || model.id;
      select.appendChild(option);
    }
    if (state.depthModels.some(model => model.id === current)) {
      select.value = current;
    }
  }

  function depthPreviewUrl(preview = state.depthPreview) {
    if (!state.project?.id || !preview?.cache_key) return '';
    return (
      '/api/animation/projects/' +
      encodeURIComponent(state.project.id) +
      '/depth-preview/image?v=' +
      encodeURIComponent(String(preview.cache_key).slice(0, 12))
    );
  }

  function renderDepthState() {
    const hasProject = Boolean(state.project);
    const hasSource = Boolean(state.project?.animation?.source_image);
    const renderActive = renderIsActive();
    const preview = state.depthPreview;
    const model = qs('#animation-depth-model');
    const device = qs('#animation-depth-device');
    const generate = qs('#animation-generate-depth');
    const recompute = qs('#animation-recompute-depth');
    const clear = qs('#animation-clear-depth');
    const badge = qs('#animation-depth-status');
    const image = qs('#animation-depth-preview');
    const empty = qs('#animation-depth-empty');
    const meta = qs('#animation-depth-meta');

    if (model) model.disabled = !hasProject || state.depthBusy || renderActive || !state.depthModels.length;
    if (device) device.disabled = !hasProject || state.depthBusy || renderActive;
    if (generate) generate.disabled = !hasProject || !hasSource || state.depthBusy || renderActive || !state.depthModels.length;
    if (recompute) recompute.disabled = !hasProject || !hasSource || state.depthBusy || renderActive || !state.depthModels.length;
    if (clear) clear.disabled = !hasProject || !preview || state.depthBusy || renderActive;

    if (badge) {
      badge.textContent = state.depthBusy
        ? 'Estimating…'
        : preview
          ? (preview.cache_hit ? 'Cached' : 'Ready')
          : hasSource
            ? 'Ready to estimate'
            : 'Need source image';
    }

    if (image) {
      const url = depthPreviewUrl(preview);
      image.hidden = !url;
      if (url) image.src = url;
      else image.removeAttribute('src');
    }
    if (empty) empty.hidden = Boolean(preview);

    if (meta) {
      if (state.depthBusy) {
        meta.textContent = 'Loading estimator / calculating relative depth…';
      } else if (preview) {
        const modelLabel = preview.model_label || preview.model_id || 'Depth model';
        const cache = preview.cache_hit ? 'cache hit' : 'new estimate';
        meta.textContent =
          modelLabel +
          ' · ' + String(preview.device || 'unknown device') +
          ' · ' + String(preview.width || '?') + ' × ' + String(preview.height || '?') +
          ' · raw ' + formatNumber(preview.raw_min, 4) + '…' + formatNumber(preview.raw_max, 4) +
          ' · ' + cache +
          ' · white=near / black=far';
      } else {
        meta.textContent = hasSource
          ? 'Depth preview has not been generated for this source image.'
          : 'Upload an image in Start Frame to generate a depth map.';
      }
    }
  }

  async function loadDepthModels() {
    try {
      const payload = await api('/api/animation/depth/models');
      state.depthModels = Array.isArray(payload.models) ? payload.models : [];
      renderDepthModels();
      renderDepthState();
    } catch (error) {
      state.depthModels = [];
      renderDepthModels();
      renderDepthState();
      throw error;
    }
  }

  async function loadDepthPreviewStatus() {
    state.depthPreview = null;
    if (!state.project?.id) {
      renderDepthState();
      return;
    }
    try {
      const payload = await api(
        '/api/animation/projects/' +
        encodeURIComponent(state.project.id) +
        '/depth-preview/status'
      );
      state.depthPreview = payload.available ? payload.preview : null;
    } catch (_) {
      state.depthPreview = null;
    }
    renderDepthState();
  }

  async function pollDepthManagerStatus() {
    if (!state.depthBusy) return;
    try {
      const payload = await api('/api/animation/depth/models');
      const status = payload.status || {};
      const badge = qs('#animation-depth-status');
      const meta = qs('#animation-depth-meta');
      if (badge && status.phase) {
        const labels = {
          loading: 'Loading model…',
          ready: 'Model ready',
          estimating: 'Estimating…',
          idle: 'Working…',
          error: 'Depth error',
        };
        badge.textContent = labels[status.phase] || status.phase;
      }
      if (meta && status.message) meta.textContent = status.message;
    } catch (_) {
      // The primary preview request will surface any real error.
    }
    window.clearTimeout(state.depthPollTimer);
    if (state.depthBusy) {
      state.depthPollTimer = window.setTimeout(pollDepthManagerStatus, 450);
    }
  }

  async function generateDepthPreview(force = false) {
    if (!state.project?.id || !state.project?.animation?.source_image || state.depthBusy) return;
    const button = qs(force ? '#animation-recompute-depth' : '#animation-generate-depth');
    state.depthBusy = true;
    setBusy(button, true);
    renderDepthState();
    renderSourceState();
    pollDepthManagerStatus();
    try {
      const payload = await api(
        '/api/animation/projects/' +
        encodeURIComponent(state.project.id) +
        '/depth-preview',
        {
          method: 'POST',
          body: JSON.stringify({
            model_id: qs('#animation-depth-model')?.value || undefined,
            device: qs('#animation-depth-device')?.value || 'auto',
            force: Boolean(force),
          }),
        }
      );
      state.depthPreview = payload.preview || null;
      const cacheLabel = state.depthPreview?.cache_hit ? 'Cache hit' : 'New depth estimate';
      toast(
        'Depth preview ready',
        cacheLabel + ' · depth estimator unloaded after inference.',
        'success',
        5200
      );
    } catch (error) {
      toast('Depth preview failed', error.message, 'error', 8000);
    } finally {
      state.depthBusy = false;
      window.clearTimeout(state.depthPollTimer);
      state.depthPollTimer = null;
      setBusy(button, false);
      renderDepthState();
      renderSourceState();
    }
  }

  async function clearDepthPreview() {
    if (!state.project?.id || state.depthBusy) return;
    try {
      await api(
        '/api/animation/projects/' +
        encodeURIComponent(state.project.id) +
        '/depth-preview',
        { method: 'DELETE' }
      );
      state.depthPreview = null;
      renderDepthState();
      toast('Depth preview cleared', 'Cached depth data remains available for reuse.', 'info');
    } catch (error) {
      toast('Could not clear depth preview', error.message, 'error', 6500);
    }
  }

  function animationMode() {
    const value = String(
      qs('#animation-mode')?.value ||
      state.project?.animation?.mode ||
      '2d'
    ).trim().toLowerCase();
    return value === '3d' ? '3d' : '2d';
  }

  function syncAnimationModeUi() {
    const mode = animationMode();
    qsa('[data-animation-mode]').forEach(element => {
      element.hidden = element.dataset.animationMode !== mode;
    });

    const curve = qs('#animation-curve-field');
    if (curve) {
      for (const option of curve.options) {
        const value = String(option.value || '');
        const is2d = value.startsWith('motion.');
        const is3d = value.startsWith('camera_3d.');
        option.hidden = (mode === '2d' && is3d) || (mode === '3d' && is2d);
        option.disabled = option.hidden;
      }
      const selected = curve.options[curve.selectedIndex];
      if (!selected || selected.hidden) {
        curve.value = mode === '3d' ? 'camera_3d.translation_z' : 'motion.zoom';
      }
    }

    if (
      state.timelineSelection &&
      ((mode === '2d' && state.timelineSelection.group === 'camera_3d') ||
       (mode === '3d' && state.timelineSelection.group === 'camera_2d'))
    ) {
      state.timelineSelection = null;
    }

    const renderButton = qs('#animation-start-render');
    if (renderButton) {
      renderButton.title = mode === '3d'
        ? 'Render with depth-aware 3D camera warping.'
        : 'Render with the 2D affine motion engine.';
    }

    renderTimeline();
    renderDepthState();
    renderSourceState();
    renderMotionLabDraft();
  }

  function timelineStatus(text, kind = '') {
    const badge = qs('#animation-timeline-status');
    if (!badge) return;
    badge.textContent = text;
    badge.className = 'badge animation-timeline-status';
    if (kind) badge.classList.add(kind);
  }

  function timelineMaxFrame() {
    return Math.max(
      0,
      Number(state.timeline?.max_frames || state.project?.animation?.max_frames || 1) - 1
    );
  }

  function timelinePosition(frame) {
    const max = timelineMaxFrame();
    if (max <= 0) return 0;
    return Math.max(0, Math.min(100, (Number(frame) / max) * 100));
  }

  function timelineFrameFromClientX(lane, clientX) {
    const rect = lane.getBoundingClientRect();
    if (!rect.width) return 0;
    const ratio = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width));
    return Math.round(ratio * timelineMaxFrame());
  }

  function syncTimelinePlayhead(frame) {
    const value = Math.max(0, Math.min(timelineMaxFrame(), Math.trunc(Number(frame) || 0)));
    const input = qs('#animation-timeline-frame');
    if (input) input.value = String(value);
    const scrubber = qs('#animation-timeline-scrubber');
    if (scrubber) {
      scrubber.max = String(timelineMaxFrame());
      scrubber.value = String(value);
    }
    const left = timelinePosition(value) + '%';
    qsa('.animation-timeline-playhead').forEach(playhead => {
      playhead.style.left = left;
    });
  }

  function setBusy(button, busy) {
    if (!button) return;
    button.classList.toggle('busy', busy);
    button.disabled = busy;
  }

  function setEditorEnabled(enabled) {
    qsa(
      '#view-animation input, #view-animation select, #view-animation textarea'
    ).forEach(input => {
      if (input.id.startsWith('animation-deforum-') || input.id.startsWith('animation-hybrid-') || input.id.startsWith('animation-video-')) {
        return;
      }
      if (input.id === 'animation-project-select') {
        input.disabled = state.projects.length === 0;
      } else {
        input.disabled = !enabled;
      }
    });

    for (const id of [
      'animation-add-prompt',
      'animation-save',
      'animation-reload',
      'animation-validate-schedules',
      'animation-generate-motion-preview',
      'animation-3d-apply-preset',
      'animation-clear-source',
    ]) {
      const control = qs(`#${id}`);
      if (control) control.disabled = !enabled;
    }
  }

  function setStatus(text, kind = '') {
    const badge = qs('#animation-project-status');
    if (!badge) return;
    badge.textContent = text;
    badge.className = 'badge animation-project-status';
    if (kind) badge.classList.add(kind);
  }

  function scheduleInspectorRefresh({ validate = false } = {}) {
    window.clearTimeout(state.previewTimer);
    state.previewTimer = window.setTimeout(() => refreshInspector(), 260);

    if (validate) {
      window.clearTimeout(state.validationTimer);
      state.validationTimer = window.setTimeout(() => validateSchedules(false), 520);
    }
  }

  function markDirty({ validate = false } = {}) {
    if (!state.project || state.loading) return;
    state.dirty = true;
    setStatus('Unsaved changes', 'dirty');
    scheduleInspectorRefresh({ validate });
  }

  function clearDirty() {
    state.dirty = false;
    setStatus(state.project ? 'Saved' : 'No project loaded', state.project ? 'saved' : '');
  }

  function modelById(modelId) {
    return state.models.find(model => model.id === modelId) || null;
  }

  function effectiveCapability(model) {
    const base = state.capabilities[model?.family] || {};
    const variant = String(model?.variant || '').toLowerCase();
    const override = base.variants?.[variant] || {};
    const merged = { ...base, ...override };
    for (const key of ['steps', 'guidance', 'samplers']) {
      if (base[key] || override[key]) {
        merged[key] = { ...(base[key] || {}), ...(override[key] || {}) };
      }
    }
    merged.variant = variant;
    return merged;
  }

  function populateResolutionPresets() {
    const model=modelById(qs('#animation-model')?.value||'');
    const capability=model?effectiveCapability(model):{};
    const width=qs('#animation-width'),height=qs('#animation-height');
    window.MorphorumResolution.populate(qs('#animation-resolution-preset'),
      capability,model?.family||'',width?.value,height?.value);
    const divisor=window.MorphorumResolution.divisorForFamily(model?.family);
    if(width)width.step=divisor;
    if(height)height.step=divisor;
    updateAnimationResolutionHelp();
  }
  function updateAnimationResolutionHelp() {
    const model=modelById(qs('#animation-model')?.value||'');
    window.MorphorumResolution.guidance(qs('#animation-resolution-help'),
      model?.family,qs('#animation-width')?.value,qs('#animation-height')?.value);
  }
  function syncAnimationResolutionPreset() {
    window.MorphorumResolution.sync(qs('#animation-resolution-preset'),
      qs('#animation-width')?.value,qs('#animation-height')?.value);
    updateAnimationResolutionHelp();
  }

  function populateSamplerSelect(preferredSampler = '') {
    const select = qs('#animation-sampler');
    if (!select) return;

    const modelId = qs('#animation-model')?.value || state.project?.model?.model_id || '';
    const model = modelById(modelId);
    const current = String(select.value || '');
    select.replaceChildren();

    if (!model) {
      const option = document.createElement('option');
      option.value = '';
      option.textContent = 'Select a model first';
      select.appendChild(option);
      select.disabled = true;
      return;
    }

    const capability = effectiveCapability(model);
    const samplerConfig = capability.samplers || {};
    const options = Array.isArray(samplerConfig.options) ? samplerConfig.options : [];

    if (!capability.supported || !options.length) {
      const option = document.createElement('option');
      option.value = '';
      option.textContent = 'No compatible samplers';
      select.appendChild(option);
      select.disabled = true;
      return;
    }

    for (const sampler of options) {
      const option = document.createElement('option');
      option.value = sampler.id;
      option.textContent = sampler.label || sampler.id;
      select.appendChild(option);
    }

    const fallback = samplerConfig.default || options[0]?.id || '';
    const candidates = [
      preferredSampler,
      current,
      state.project?.generation?.sampler || '',
      fallback,
    ].filter(Boolean);
    const valid = new Set(options.map(item => item.id));
    const selected = candidates.find(value => valid.has(value)) || fallback;
    select.value = selected;
    select.disabled = false;
    select.title = capability.label
      ? `${capability.label} compatible samplers`
      : 'Compatible samplers';
  }

  function repairConstantGuidanceForSelectedModel({ announce = false } = {}) {
    const input = qs('#animation-guidance');
    const modelId = qs('#animation-model')?.value || state.project?.model?.model_id || '';
    const model = modelById(modelId);
    if (!input || !model) return false;

    const capability = effectiveCapability(model);
    const guidance = capability.guidance || {};
    const minimum = Number(guidance.min ?? 0);
    const maximum = Number(guidance.max ?? 30);
    const fallback = Number(guidance.default ?? Math.max(minimum, 0));
    const compact = String(input.value || '').replace(/\s+/g, '');
    const match = /^0:\(([+-]?(?:\d+(?:\.\d*)?|\.\d+))\)$/.exec(compact);
    if (!match) return false;

    const current = Number(match[1]);
    if (Number.isFinite(current) && current >= minimum && current <= maximum) {
      return false;
    }

    const replacement = `0:(${Number.isFinite(fallback) ? fallback : minimum})`;
    input.value = replacement;
    if (state.project) {
      state.project.generation = {
        ...(state.project.generation || {}),
        guidance: replacement,
      };
    }
    if (announce) {
      toast(
        'Guidance adjusted for selected model',
        `${capability.label || model.family}: ${replacement} (allowed ${minimum}…${maximum}).`,
        'info',
        5200
      );
    }
    return true;
  }

  function populateModelSelect() {
    const select = qs('#animation-model');
    if (!select) return;
    const selected = state.project?.model?.model_id || select.value || '';
    const models = state.models.filter(model => model.kind === 'checkpoints');

    select.replaceChildren();
    const none = document.createElement('option');
    none.value = '';
    none.textContent = 'No model selected';
    select.appendChild(none);

    for (const model of models) {
      const option = document.createElement('option');
      option.value = model.id;
      const variant = model.variant ? ` · ${model.variant}` : '';
      option.textContent = `${model.name} · ${String(model.family || '').toUpperCase()}${variant}`;
      select.appendChild(option);
    }

    if (selected && !models.some(model => model.id === selected)) {
      const missing = document.createElement('option');
      missing.value = selected;
      missing.textContent = `Missing indexed model · ${selected}`;
      select.appendChild(missing);
    }
    select.value = selected;
    populateSamplerSelect(state.project?.generation?.sampler || '');
    populateResolutionPresets();
  }

  function renderProjectSelect() {
    const select = qs('#animation-project-select');
    if (!select) return;
    const selected = state.project?.id || '';

    select.replaceChildren();
    if (!state.projects.length) {
      const option = document.createElement('option');
      option.value = '';
      option.textContent = 'No projects yet';
      select.appendChild(option);
      select.disabled = true;
      return;
    }

    for (const project of state.projects) {
      const option = document.createElement('option');
      option.value = project.id;
      option.textContent = `${project.name} · ${project.max_frames}f @ ${project.fps}fps`;
      select.appendChild(option);
    }
    select.disabled = false;
    if (state.projects.some(project => project.id === selected)) {
      select.value = selected;
    }
  }

  function sortedPromptFrames(project) {
    const frames = new Set([
      ...Object.keys(project?.prompts || {}),
      ...Object.keys(project?.negative_prompts || {}),
    ]);
    if (!frames.size) frames.add('0');
    return [...frames]
      .map(value => Number(value))
      .filter(Number.isFinite)
      .sort((a, b) => a - b);
  }

  function timelineTrackDescriptors() {
    const tracks = state.timeline?.descriptors?.tracks;
    if (!Array.isArray(tracks)) return [];
    const mode = animationMode();
    return tracks.filter(item => {
      if (!item?.editable || !item?.keyframe_editable) return false;
      if (mode === '2d' && item.group === 'camera_3d') return false;
      if (mode === '3d' && item.group === 'camera_2d') return false;
      return true;
    });
  }

  function timelineDescriptor(group, name) {
    return timelineTrackDescriptors().find(
      item => item.group === group && item.name === name
    ) || null;
  }

  function timelineTrack(group, name) {
    const groupValue = state.timeline?.tracks?.[group];
    return groupValue && typeof groupValue === 'object'
      ? (groupValue[name] || null)
      : null;
  }

  function timelineGroupLabel(group) {
    const groups = state.timeline?.descriptors?.groups;
    const match = Array.isArray(groups)
      ? groups.find(item => item.id === group)
      : null;
    return match?.label || String(group || '').replaceAll('_', ' ');
  }

  function niceTimelineStep(maxFrames, width) {
    const approximateTicks = Math.max(2, Math.floor(Number(width || 720) / 90));
    const raw = Math.max(1, Number(maxFrames || 1) / approximateTicks);
    const power = 10 ** Math.floor(Math.log10(raw));
    const normalized = raw / power;
    const nice = normalized <= 1 ? 1 : normalized <= 2 ? 2 : normalized <= 5 ? 5 : 10;
    return Math.max(1, Math.round(nice * power));
  }

  function timelineKeyframeAt(track, frame) {
    const keyframes = Array.isArray(track?.keyframes) ? track.keyframes : [];
    return keyframes.find(item => Number(item.frame) === Number(frame)) || null;
  }

  function nearestTimelineValue(track, frame) {
    const keyframes = (Array.isArray(track?.keyframes) ? track.keyframes : [])
      .filter(item => Number.isFinite(Number(item.frame)))
      .sort((a, b) => Number(a.frame) - Number(b.frame));
    if (!keyframes.length) return '';
    let selected = keyframes[0];
    for (const item of keyframes) {
      if (Number(item.frame) <= Number(frame)) selected = item;
      else break;
    }
    return String(selected?.value ?? '');
  }

  function renderTimelineEditor() {
    const editor = qs('#animation-timeline-editor');
    const selection = state.timelineSelection;
    const add = qs('#animation-timeline-add');
    if (add) add.disabled = !state.project || !selection || state.timelineBusy;

    if (!editor || !selection || !state.timeline) {
      if (editor) editor.hidden = true;
      return;
    }

    const descriptor = timelineDescriptor(selection.group, selection.name);
    const track = timelineTrack(selection.group, selection.name);
    if (!descriptor || !track) {
      editor.hidden = true;
      return;
    }

    const playhead = Number(qs('#animation-timeline-frame')?.value || 0);
    const selectedFrame = selection.frame === null || selection.frame === undefined
      ? playhead
      : Number(selection.frame);
    const keyframe = timelineKeyframeAt(track, selectedFrame);

    editor.hidden = false;
    const title = qs('#animation-timeline-selected-track');
    if (title) title.textContent = descriptor.label || descriptor.id;
    const meta = qs('#animation-timeline-selected-meta');
    if (meta) {
      const unit = descriptor.unit ? ' · ' + descriptor.unit : '';
      meta.textContent =
        timelineGroupLabel(descriptor.group) +
        ' · ' + descriptor.kind +
        unit +
        (keyframe ? ' · keyframe F' + selectedFrame : ' · new keyframe at F' + selectedFrame);
    }

    const frameInput = qs('#animation-timeline-keyframe-frame');
    if (frameInput) {
      frameInput.max = String(timelineMaxFrame());
      frameInput.value = String(selectedFrame);
      frameInput.disabled = state.timelineBusy;
    }

    const valueInput = qs('#animation-timeline-keyframe-value');
    if (valueInput) {
      valueInput.value = keyframe
        ? String(keyframe.value ?? '')
        : nearestTimelineValue(track, selectedFrame);
      valueInput.rows = descriptor.kind === 'prompt' ? 3 : 2;
      valueInput.disabled = state.timelineBusy;
    }

    const interpolation = qs('#animation-timeline-interpolation');
    if (interpolation) {
      interpolation.replaceChildren();
      for (const mode of descriptor.interpolation_modes || []) {
        const option = document.createElement('option');
        option.value = mode;
        option.textContent = mode;
        interpolation.appendChild(option);
      }
      interpolation.value = track.interpolation || descriptor.interpolation_modes?.[0] || '';
      interpolation.disabled = state.timelineBusy;
    }

    const apply = qs('#animation-timeline-apply');
    if (apply) {
      apply.textContent = keyframe ? 'Apply' : 'Add keyframe';
      apply.disabled = state.timelineBusy;
    }

    const remove = qs('#animation-timeline-delete');
    if (remove) {
      const protectedFrame = Boolean(
        keyframe && descriptor.required_frame_zero && Number(selectedFrame) === 0
      );
      remove.disabled = state.timelineBusy || !keyframe || protectedFrame;
      remove.title = protectedFrame
        ? 'Frame 0 is required for this track.'
        : 'Delete selected keyframe';
    }
  }

  function renderTimeline() {
    const grid = qs('#animation-timeline-grid');
    const empty = qs('#animation-timeline-empty');
    const refresh = qs('#animation-timeline-refresh');
    const frameInput = qs('#animation-timeline-frame');
    const scrubber = qs('#animation-timeline-scrubber');
    const scaleInput = qs('#animation-timeline-scale');
    const trackSelect = qs('#animation-timeline-track-select');
    const prevButton = qs('#animation-timeline-prev-keyframe');
    const nextButton = qs('#animation-timeline-next-keyframe');
    const keyframeList = qs('#animation-timeline-keyframe-list');

    if (refresh) refresh.disabled = !state.project || state.timelineBusy;
    if (frameInput) {
      frameInput.disabled = !state.project || state.timelineBusy;
      frameInput.max = String(timelineMaxFrame());
    }
    if (scrubber) {
      scrubber.disabled = !state.project || state.timelineBusy;
      scrubber.max = String(timelineMaxFrame());
    }
    if (scaleInput) {
      scaleInput.disabled = !state.project || state.timelineBusy || isMobileTimeline();
      scaleInput.value = String(state.timelineScale);
    }

    if (!grid || !state.project || !state.timeline) {
      if (grid) {
        grid.hidden = true;
        grid.replaceChildren();
      }
      if (trackSelect) {
        trackSelect.replaceChildren();
        const option = document.createElement('option');
        option.value = '';
        option.textContent = 'No track';
        trackSelect.appendChild(option);
        trackSelect.disabled = true;
      }
      if (prevButton) prevButton.disabled = true;
      if (nextButton) nextButton.disabled = true;
      if (keyframeList) {
        keyframeList.hidden = true;
        keyframeList.replaceChildren();
      }
      if (empty) {
        empty.hidden = false;
        empty.textContent = state.project
          ? 'Loading timeline tracks…'
          : 'Create or load a project to view timeline tracks.';
      }
      timelineStatus(state.project ? 'Loading…' : 'No project', state.project ? 'busy' : '');
      renderTimelineEditor();
      return;
    }

    const descriptors = timelineTrackDescriptors();
    if (!descriptors.length) {
      grid.hidden = true;
      if (empty) {
        empty.hidden = false;
        empty.textContent = 'No editable tracks are available.';
      }
      if (trackSelect) trackSelect.disabled = true;
      if (prevButton) prevButton.disabled = true;
      if (nextButton) nextButton.disabled = true;
      if (keyframeList) {
        keyframeList.hidden = true;
        keyframeList.replaceChildren();
      }
      timelineStatus('No tracks');
      renderTimelineEditor();
      return;
    }

    if (
      !state.timelineSelection ||
      !timelineDescriptor(state.timelineSelection.group, state.timelineSelection.name)
    ) {
      state.timelineSelection = {
        group: descriptors[0].group,
        name: descriptors[0].name,
        frame: null,
      };
    }

    if (trackSelect) {
      const selectedValue =
        state.timelineSelection.group + '/' + state.timelineSelection.name;
      trackSelect.replaceChildren();
      for (const descriptor of descriptors) {
        const option = document.createElement('option');
        option.value = descriptor.group + '/' + descriptor.name;
        option.textContent =
          timelineGroupLabel(descriptor.group) + ' · ' + (descriptor.label || descriptor.name);
        trackSelect.appendChild(option);
      }
      trackSelect.value = selectedValue;
      trackSelect.disabled = state.timelineBusy;
    }

    const selectedDescriptor = timelineDescriptor(
      state.timelineSelection.group,
      state.timelineSelection.name
    );
    const selectedTrack = timelineTrack(
      state.timelineSelection.group,
      state.timelineSelection.name
    );
    const playheadFrame = Math.max(
      0,
      Math.min(
        timelineMaxFrame(),
        Math.trunc(Number(qs('#animation-timeline-frame')?.value || 0))
      )
    );
    const selectedFrames = (selectedTrack?.keyframes || [])
      .map(item => Number(item.frame))
      .filter(Number.isFinite)
      .sort((a, b) => a - b);
    if (prevButton) {
      prevButton.disabled =
        state.timelineBusy || !selectedFrames.some(frame => frame < playheadFrame);
    }
    if (nextButton) {
      nextButton.disabled =
        state.timelineBusy || !selectedFrames.some(frame => frame > playheadFrame);
    }

    const mobile = isMobileTimeline();
    if (keyframeList) {
      keyframeList.replaceChildren();
      keyframeList.hidden = !mobile || !selectedFrames.length;
      if (mobile) {
        for (const frame of selectedFrames) {
          const item = timelineKeyframeAt(selectedTrack, frame);
          const button = document.createElement('button');
          button.type = 'button';
          button.className = 'secondary-button compact animation-timeline-keyframe-chip';
          if (
            state.timelineSelection?.frame !== null &&
            state.timelineSelection?.frame !== undefined &&
            Number(state.timelineSelection.frame) === frame
          ) {
            button.classList.add('selected');
          }
          button.textContent = 'F' + frame;
          button.title = String(item?.value ?? '');
          button.addEventListener('click', () => {
            state.timelineSelection = {
              group: state.timelineSelection.group,
              name: state.timelineSelection.name,
              frame,
            };
            setInspectorFrame(frame);
            renderTimeline();
          });
          keyframeList.appendChild(button);
        }
      }
    }

    const maxFrames = Math.max(1, Number(state.timeline.max_frames || 1));
    const scroll = qs('#animation-timeline-scroll');
    const availableWidth = Math.max(300, Number(scroll?.clientWidth || 360) - 4);
    const contentWidth = mobile
      ? availableWidth
      : Math.max(640, Math.round(maxFrames * state.timelineScale));
    grid.style.setProperty('--timeline-content-width', contentWidth + 'px');
    grid.classList.toggle('mobile-focused', mobile);
    grid.replaceChildren();
    grid.hidden = false;
    if (empty) empty.hidden = true;

    const rulerRow = document.createElement('div');
    rulerRow.className = 'animation-timeline-ruler-row';
    const rulerLabel = document.createElement('div');
    rulerLabel.className = 'animation-timeline-ruler-label';
    rulerLabel.textContent =
      mobile && selectedDescriptor
        ? (selectedDescriptor.label || selectedDescriptor.name)
        : (maxFrames + 'f · ' + formatNumber(state.timeline.fps, 2) + 'fps');
    const ruler = document.createElement('div');
    ruler.className = 'animation-timeline-ruler';

    const step = niceTimelineStep(maxFrames, contentWidth);
    const lastFrame = Math.max(0, maxFrames - 1);
    for (let frame = 0; frame <= lastFrame; frame += step) {
      const tick = document.createElement('div');
      tick.className = 'animation-timeline-tick major';
      tick.style.left = timelinePosition(frame) + '%';
      const label = document.createElement('span');
      label.textContent = String(frame);
      tick.appendChild(label);
      ruler.appendChild(tick);
    }
    if (lastFrame > 0 && lastFrame % step !== 0) {
      const tick = document.createElement('div');
      tick.className = 'animation-timeline-tick major';
      tick.style.left = '100%';
      const label = document.createElement('span');
      label.textContent = String(lastFrame);
      tick.appendChild(label);
      ruler.appendChild(tick);
    }
    const rulerPlayhead = document.createElement('div');
    rulerPlayhead.className = 'animation-timeline-playhead';
    ruler.appendChild(rulerPlayhead);
    ruler.addEventListener('click', event => {
      const frame = timelineFrameFromClientX(ruler, event.clientX);
      setInspectorFrame(frame);
    });
    rulerRow.append(rulerLabel, ruler);
    grid.appendChild(rulerRow);

    const visibleDescriptors = mobile && selectedDescriptor
      ? [selectedDescriptor]
      : descriptors;

    for (const descriptor of visibleDescriptors) {
      const track = timelineTrack(descriptor.group, descriptor.name);
      if (!track) continue;
      const row = document.createElement('div');
      row.className = 'animation-timeline-track-row';
      if (
        state.timelineSelection?.group === descriptor.group &&
        state.timelineSelection?.name === descriptor.name
      ) {
        row.classList.add('selected');
      }

      const label = document.createElement('div');
      label.className = 'animation-timeline-track-label';
      const strong = document.createElement('strong');
      strong.textContent = descriptor.label || descriptor.id;
      const meta = document.createElement('span');
      meta.textContent =
        timelineGroupLabel(descriptor.group) +
        ' · ' + (track.interpolation || '') +
        (descriptor.unit ? ' · ' + descriptor.unit : '');
      label.append(strong, meta);
      label.addEventListener('click', () => {
        state.timelineSelection = {
          group: descriptor.group,
          name: descriptor.name,
          frame: null,
        };
        renderTimeline();
      });

      const lane = document.createElement('div');
      lane.className = 'animation-timeline-track-lane';
      lane.dataset.group = descriptor.group;
      lane.dataset.track = descriptor.name;
      lane.addEventListener('click', event => {
        if (event.target.closest('.animation-timeline-keyframe')) return;
        const frame = timelineFrameFromClientX(lane, event.clientX);
        state.timelineSelection = {
          group: descriptor.group,
          name: descriptor.name,
          frame: timelineKeyframeAt(track, frame) ? frame : null,
        };
        setInspectorFrame(frame);
        renderTimeline();
      });

      const playhead = document.createElement('div');
      playhead.className = 'animation-timeline-playhead';
      lane.appendChild(playhead);

      for (const item of track.keyframes || []) {
        const frame = Number(item.frame);
        if (!Number.isFinite(frame)) continue;
        const keyframe = document.createElement('button');
        keyframe.type = 'button';
        keyframe.className = 'animation-timeline-keyframe';
        if (descriptor.required_frame_zero && frame === 0) {
          keyframe.classList.add('required');
        }
        if (
          state.timelineSelection?.group === descriptor.group &&
          state.timelineSelection?.name === descriptor.name &&
          state.timelineSelection?.frame !== null &&
          state.timelineSelection?.frame !== undefined &&
          Number(state.timelineSelection.frame) === frame
        ) {
          keyframe.classList.add('selected');
        }
        keyframe.style.left = timelinePosition(frame) + '%';
        keyframe.title = descriptor.label + ' · F' + frame + ' · ' + String(item.value ?? '');
        keyframe.setAttribute('aria-label', descriptor.label + ' keyframe at frame ' + frame);
        keyframe.addEventListener('click', event => {
          event.stopPropagation();
          if (keyframe.dataset.suppressClick === '1') {
            delete keyframe.dataset.suppressClick;
            return;
          }
          state.timelineSelection = {
            group: descriptor.group,
            name: descriptor.name,
            frame,
          };
          setInspectorFrame(frame);
          renderTimeline();
        });
        keyframe.addEventListener('pointerdown', event => {
          beginTimelineDrag(event, descriptor, item, lane, keyframe);
        });
        lane.appendChild(keyframe);
      }

      row.append(label, lane);
      grid.appendChild(row);
    }

    syncTimelinePlayhead(playheadFrame);
    timelineStatus(mobile ? 'Focused track · Ready' : 'Ready', 'saved');
    renderTimelineEditor();
  }

  function navigateTimelineKeyframe(direction) {
    const selection = state.timelineSelection;
    if (!selection) return;
    const track = timelineTrack(selection.group, selection.name);
    const frames = (track?.keyframes || [])
      .map(item => Number(item.frame))
      .filter(Number.isFinite)
      .sort((a, b) => a - b);
    if (!frames.length) return;

    const current = Math.max(
      0,
      Math.min(
        timelineMaxFrame(),
        Math.trunc(Number(qs('#animation-timeline-frame')?.value || 0))
      )
    );
    const target = direction < 0
      ? [...frames].reverse().find(frame => frame < current)
      : frames.find(frame => frame > current);
    if (target === undefined) return;

    state.timelineSelection = {
      group: selection.group,
      name: selection.name,
      frame: target,
    };
    setInspectorFrame(target);
    renderTimeline();
  }

  async function persistDirtyBeforeTimelineEdit() {
    if (!state.project || !state.dirty) return;
    timelineStatus('Saving form…', 'busy');
    const payload = await api(
      '/api/animation/projects/' + encodeURIComponent(state.project.id),
      {
        method: 'PUT',
        body: JSON.stringify(collectProject()),
      }
    );
    state.project = payload.project;
    state.path = payload.path || state.path;
    clearDirty();
  }

  async function loadTimeline() {
    if (!state.project?.id) {
      state.timeline = null;
      state.timelineSelection = null;
      renderTimeline();
      return;
    }

    timelineStatus('Loading…', 'busy');
    try {
      state.timeline = await api(
        '/api/animation/projects/' + encodeURIComponent(state.project.id) + '/timeline'
      );
      if (state.timelineSelection) {
        const descriptor = timelineDescriptor(
          state.timelineSelection.group,
          state.timelineSelection.name
        );
        if (!descriptor) state.timelineSelection = null;
      }
      renderTimeline();
    } catch (error) {
      state.timeline = null;
      timelineStatus('Timeline error', 'error');
      const empty = qs('#animation-timeline-empty');
      if (empty) {
        empty.hidden = false;
        empty.textContent = error.message;
      }
      const grid = qs('#animation-timeline-grid');
      if (grid) grid.hidden = true;
    }
  }

  async function finishTimelineMutation(payload, selection) {
    if (payload?.project) {
      state.project = payload.project;
      state.timelineSelection = selection || state.timelineSelection;
      clearDirty();
      fillForm();
    }
    await loadTimeline();
    refreshInspector();
  }

  async function moveTimelineKeyframe(descriptor, sourceFrame, targetFrame) {
    if (!state.project || sourceFrame === targetFrame) return;
    state.timelineBusy = true;
    timelineStatus('Moving F' + sourceFrame + ' → F' + targetFrame + '…', 'busy');
    renderTimelineEditor();
    try {
      await persistDirtyBeforeTimelineEdit();
      const payload = await api(
        '/api/animation/projects/' + encodeURIComponent(state.project.id) +
        '/timeline/tracks/' + encodeURIComponent(descriptor.group) +
        '/' + encodeURIComponent(descriptor.name) +
        '/keyframes/' + encodeURIComponent(sourceFrame) + '/move',
        {
          method: 'POST',
          body: JSON.stringify({ frame: targetFrame, overwrite: false }),
        }
      );
      await finishTimelineMutation(payload, {
        group: descriptor.group,
        name: descriptor.name,
        frame: targetFrame,
      });
    } catch (error) {
      timelineStatus('Move failed', 'error');
      toast('Could not move keyframe', error.message, 'error', 6500);
      await loadTimeline();
    } finally {
      state.timelineBusy = false;
      renderTimeline();
    }
  }

  function beginTimelineDrag(event, descriptor, item, lane, button) {
    const sourceFrame = Number(item.frame);
    state.timelineSelection = {
      group: descriptor.group,
      name: descriptor.name,
      frame: sourceFrame,
    };
    setInspectorFrame(sourceFrame);

    if (isMobileTimeline() || window.matchMedia('(pointer: coarse)').matches) {
      renderTimeline();
      return;
    }

    if (descriptor.required_frame_zero && sourceFrame === 0) {
      renderTimeline();
      return;
    }

    event.preventDefault();
    event.stopPropagation();
    let targetFrame = sourceFrame;
    let moved = false;

    const onMove = moveEvent => {
      if (Math.abs(moveEvent.clientX - event.clientX) > 3) moved = true;
      if (!moved) return;
      button.dataset.suppressClick = '1';
      targetFrame = timelineFrameFromClientX(lane, moveEvent.clientX);
      button.style.left = timelinePosition(targetFrame) + '%';
      timelineStatus('Drop at F' + targetFrame, 'busy');
      syncTimelinePlayhead(targetFrame);
    };

    const onUp = async () => {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
      if (moved && targetFrame !== sourceFrame) {
        await moveTimelineKeyframe(descriptor, sourceFrame, targetFrame);
      } else {
        renderTimeline();
      }
    };

    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp, { once: true });
  }

  async function addTimelineKeyframeAtPlayhead() {
    if (!state.project || !state.timelineSelection || state.timelineBusy) return;
    const descriptor = timelineDescriptor(
      state.timelineSelection.group,
      state.timelineSelection.name
    );
    const track = timelineTrack(
      state.timelineSelection.group,
      state.timelineSelection.name
    );
    if (!descriptor || !track) return;

    const frame = Math.max(
      0,
      Math.min(timelineMaxFrame(), Math.trunc(Number(qs('#animation-timeline-frame')?.value || 0)))
    );
    const existing = timelineKeyframeAt(track, frame);
    if (existing) {
      state.timelineSelection.frame = frame;
      renderTimeline();
      qs('#animation-timeline-keyframe-value')?.focus();
      return;
    }

    state.timelineBusy = true;
    timelineStatus('Adding keyframe…', 'busy');
    try {
      await persistDirtyBeforeTimelineEdit();
      const payload = await api(
        '/api/animation/projects/' + encodeURIComponent(state.project.id) +
        '/timeline/tracks/' + encodeURIComponent(descriptor.group) +
        '/' + encodeURIComponent(descriptor.name) +
        '/keyframes/' + encodeURIComponent(frame),
        {
          method: 'PUT',
          body: JSON.stringify({ value: nearestTimelineValue(track, frame) }),
        }
      );
      await finishTimelineMutation(payload, {
        group: descriptor.group,
        name: descriptor.name,
        frame,
      });
    } catch (error) {
      timelineStatus('Add failed', 'error');
      toast('Could not add keyframe', error.message, 'error', 6500);
    } finally {
      state.timelineBusy = false;
      renderTimeline();
    }
  }

  async function applyTimelineEditor() {
    const selection = state.timelineSelection;
    if (!state.project || !selection || state.timelineBusy) return;
    const descriptor = timelineDescriptor(selection.group, selection.name);
    const track = timelineTrack(selection.group, selection.name);
    if (!descriptor || !track) return;

    const originalFrame = selection.frame;
    const targetFrame = Math.max(
      0,
      Math.min(
        timelineMaxFrame(),
        Math.trunc(Number(qs('#animation-timeline-keyframe-frame')?.value || 0))
      )
    );
    const value = qs('#animation-timeline-keyframe-value')?.value ?? '';
    const interpolation = qs('#animation-timeline-interpolation')?.value || track.interpolation;

    state.timelineBusy = true;
    timelineStatus('Saving keyframe…', 'busy');
    try {
      await persistDirtyBeforeTimelineEdit();
      let payload = null;
      let frame = originalFrame;

      if (frame !== null && frame !== undefined && Number(frame) !== targetFrame) {
        payload = await api(
          '/api/animation/projects/' + encodeURIComponent(state.project.id) +
          '/timeline/tracks/' + encodeURIComponent(descriptor.group) +
          '/' + encodeURIComponent(descriptor.name) +
          '/keyframes/' + encodeURIComponent(frame) + '/move',
          {
            method: 'POST',
            body: JSON.stringify({ frame: targetFrame, overwrite: false }),
          }
        );
        if (payload?.project) state.project = payload.project;
        frame = targetFrame;
      }

      payload = await api(
        '/api/animation/projects/' + encodeURIComponent(state.project.id) +
        '/timeline/tracks/' + encodeURIComponent(descriptor.group) +
        '/' + encodeURIComponent(descriptor.name) +
        '/keyframes/' + encodeURIComponent(targetFrame),
        {
          method: 'PUT',
          body: JSON.stringify({ value }),
        }
      );
      if (payload?.project) state.project = payload.project;

      if (interpolation && interpolation !== track.interpolation) {
        payload = await api(
          '/api/animation/projects/' + encodeURIComponent(state.project.id) +
          '/timeline/tracks/' + encodeURIComponent(descriptor.group) +
          '/' + encodeURIComponent(descriptor.name) +
          '/interpolation',
          {
            method: 'PUT',
            body: JSON.stringify({ interpolation }),
          }
        );
      }

      await finishTimelineMutation(payload, {
        group: descriptor.group,
        name: descriptor.name,
        frame: targetFrame,
      });
    } catch (error) {
      timelineStatus('Save failed', 'error');
      toast('Could not save timeline keyframe', error.message, 'error', 7000);
      await loadTimeline();
    } finally {
      state.timelineBusy = false;
      renderTimeline();
    }
  }

  async function deleteTimelineKeyframe() {
    const selection = state.timelineSelection;
    if (!state.project || !selection || selection.frame === null || state.timelineBusy) return;
    const descriptor = timelineDescriptor(selection.group, selection.name);
    if (!descriptor) return;

    state.timelineBusy = true;
    timelineStatus('Deleting keyframe…', 'busy');
    try {
      await persistDirtyBeforeTimelineEdit();
      const payload = await api(
        '/api/animation/projects/' + encodeURIComponent(state.project.id) +
        '/timeline/tracks/' + encodeURIComponent(descriptor.group) +
        '/' + encodeURIComponent(descriptor.name) +
        '/keyframes/' + encodeURIComponent(selection.frame),
        { method: 'DELETE' }
      );
      await finishTimelineMutation(payload, {
        group: descriptor.group,
        name: descriptor.name,
        frame: null,
      });
    } catch (error) {
      timelineStatus('Delete failed', 'error');
      toast('Could not delete keyframe', error.message, 'error', 6500);
    } finally {
      state.timelineBusy = false;
      renderTimeline();
    }
  }

  function currentAnimationLoras() {
    const modelId = qs('#animation-model')?.value || state.project?.model?.model_id || '';
    const model = modelById(modelId);
    if (!model?.family) return [];
    return state.models
      .filter(item => item.kind === 'loras' && item.family === model.family)
      .sort((a, b) => String(a.name || '').localeCompare(String(b.name || '')));
  }

  function insertAtCursor(textarea, text) {
    if (!textarea) return;
    const start = Number.isFinite(textarea.selectionStart) ? textarea.selectionStart : textarea.value.length;
    const end = Number.isFinite(textarea.selectionEnd) ? textarea.selectionEnd : start;
    const before = textarea.value.slice(0, start);
    const after = textarea.value.slice(end);
    const prefix = before && !/\s$/.test(before) ? ' ' : '';
    const suffix = after && !/^\s/.test(after) ? ' ' : '';
    const insertion = prefix + text + suffix;
    textarea.value = before + insertion + after;
    const cursor = before.length + insertion.length;
    textarea.focus();
    textarea.setSelectionRange(cursor, cursor);
    textarea.dispatchEvent(new Event('input', { bubbles: true }));
  }

  function createLoraTools(promptInput) {
    const tools = document.createElement('div');
    tools.className = 'animation-lora-tools';

    const select = document.createElement('select');
    select.className = 'animation-lora-select';
    select.setAttribute('aria-label', 'LoRA');

    const loras = currentAnimationLoras();
    if (!loras.length) {
      const option = document.createElement('option');
      option.value = '';
      option.textContent = 'No compatible indexed LoRAs';
      select.appendChild(option);
      select.disabled = true;
    } else {
      for (const lora of loras) {
        const option = document.createElement('option');
        option.value = lora.name || lora.filename || lora.id;
        option.textContent = lora.name || lora.filename || lora.id;
        select.appendChild(option);
      }
    }

    const weight = document.createElement('input');
    weight.className = 'animation-lora-weight';
    weight.type = 'number';
    weight.value = '1';
    weight.step = '0.05';
    weight.min = '-4';
    weight.max = '4';
    weight.setAttribute('aria-label', 'LoRA weight');
    weight.disabled = !loras.length;

    const insert = document.createElement('button');
    insert.type = 'button';
    insert.className = 'secondary-button compact animation-insert-lora';
    insert.textContent = 'Insert LoRA';
    insert.disabled = !loras.length;
    insert.addEventListener('click', () => {
      const name = String(select.value || '').trim();
      if (!name) return;
      const numericWeight = Number(weight.value);
      const value = Number.isFinite(numericWeight) ? numericWeight : 1;
      insertAtCursor(
        promptInput,
        `<lora:${name}:${Number(value.toFixed(4))}>`
      );
    });

    const hint = document.createElement('span');
    hint.className = 'animation-lora-hint';
    hint.textContent = loras.length
      ? 'LoRA strength can change between prompt keyframes'
      : 'Add a LoRA directory for the selected model family, then scan Models.';

    tools.append(select, weight, insert, hint);
    return tools;
  }

  function createPromptRow(frame, prompt, negativePrompt) {
    const row = document.createElement('div');
    row.className = 'animation-prompt-row';

    const frameLabel = document.createElement('label');
    const frameTitle = document.createElement('span');
    frameTitle.textContent = 'Frame';
    const frameInput = document.createElement('input');
    frameInput.className = 'animation-prompt-frame';
    frameInput.type = 'number';
    frameInput.min = '0';
    frameInput.max = String(Math.max(0, Number(qs('#animation-max-frames')?.value || 120) - 1));
    frameInput.value = String(frame);
    frameLabel.append(frameTitle, frameInput);

    const promptLabel = document.createElement('label');
    const promptTitle = document.createElement('span');
    promptTitle.textContent = 'Prompt';
    const promptInput = document.createElement('textarea');
    promptInput.className = 'animation-prompt-text';
    promptInput.rows = 2;
    promptInput.value = prompt || '';
    promptInput.placeholder = 'Describe the scene at this keyframe…';
    promptLabel.append(promptTitle, promptInput);

    const negativeLabel = document.createElement('label');
    const negativeTitle = document.createElement('span');
    negativeTitle.textContent = 'Negative';
    const negativeInput = document.createElement('textarea');
    negativeInput.className = 'animation-negative-text';
    negativeInput.rows = 2;
    negativeInput.value = negativePrompt || '';
    negativeInput.placeholder = 'Optional negative prompt';
    negativeLabel.append(negativeTitle, negativeInput);

    const remove = document.createElement('button');
    remove.type = 'button';
    remove.className = 'icon-button animation-remove-prompt';
    remove.textContent = '×';
    remove.title = 'Remove keyframe';
    remove.disabled = Number(frame) === 0;
    remove.addEventListener('click', () => {
      row.remove();
      markDirty();
    });

    qsa('input, textarea', row).forEach(input => {
      input.addEventListener('input', () => markDirty());
    });
    frameInput.addEventListener('input', () => {
      remove.disabled = Number(frameInput.value) === 0;
    });

    const loraTools = createLoraTools(promptInput);
    row.append(frameLabel, promptLabel, negativeLabel, remove, loraTools);
    return row;
  }

  function renderPromptRows() {
    const list = qs('#animation-prompt-list');
    if (!list) return;
    list.replaceChildren();

    if (!state.project) {
      const empty = document.createElement('div');
      empty.className = 'animation-empty';
      empty.textContent = 'Create or load a project to edit prompt keyframes.';
      list.appendChild(empty);
      return;
    }

    for (const frame of sortedPromptFrames(state.project)) {
      list.appendChild(
        createPromptRow(
          frame,
          state.project.prompts?.[String(frame)] || '',
          state.project.negative_prompts?.[String(frame)] || ''
        )
      );
    }
  }

  function addPromptKeyframe() {
    if (!state.project) return;
    const rows = qsa('.animation-prompt-frame');
    const frames = rows
      .map(input => Number(input.value))
      .filter(Number.isFinite);
    const maxFrames = Math.max(1, Number(qs('#animation-max-frames')?.value || 120));
    const last = frames.length ? Math.max(...frames) : 0;
    const candidate = Math.min(
      maxFrames - 1,
      Math.max(1, last + Math.max(1, Math.round(maxFrames / 4)))
    );

    const list = qs('#animation-prompt-list');
    list?.appendChild(createPromptRow(candidate, '', ''));
    markDirty();
    list?.lastElementChild?.querySelector('.animation-prompt-text')?.focus();
  }

  function inspectorFrameMax() {
    return Math.max(0, Number(qs('#animation-max-frames')?.value || 1) - 1);
  }

  function syncInspectorBounds() {
    const max = inspectorFrameMax();
    const frameInput = qs('#animation-inspector-frame');
    const slider = qs('#animation-inspector-slider');
    if (frameInput) {
      frameInput.max = String(max);
      if (Number(frameInput.value) > max) frameInput.value = String(max);
    }
    if (slider) {
      slider.max = String(max);
      if (Number(slider.value) > max) slider.value = String(max);
    }
  }

  function setInspectorFrame(value) {
    const max = inspectorFrameMax();
    const frame = Math.max(0, Math.min(max, Math.trunc(Number(value) || 0)));
    const frameInput = qs('#animation-inspector-frame');
    const slider = qs('#animation-inspector-slider');
    if (frameInput) frameInput.value = String(frame);
    if (slider) slider.value = String(frame);
    syncTimelinePlayhead(frame);
    refreshInspector();
  }

  function syncCadencePreset() {
    const raw = qs('#animation-cadence');
    const preset = qs('#animation-cadence-preset');
    const help = qs('#animation-cadence-help');
    if (!raw || !preset) return;
    const match = /^\s*0:\(\s*(\d+)\s*\)\s*$/.exec(raw.value);
    const count = match ? Number(match[1]) : NaN;
    const fixed = match && [...preset.options].some(option => option.value === String(count));
    preset.value = fixed ? String(count) : 'custom';
    if (help) {
      help.textContent = fixed
        ? (count === 1
          ? 'Cadence 1: diffusion on every eligible frame.'
          : 'Cadence ' + count + ': run diffusion on every ' + count +
            ' frames; between anchors, only camera transforms run.')
        : 'Custom cadence schedule: diffusion frequency follows the keyframes you set.';
    }
  }

  function applyCamera3DPreset() {
    if (!state.project || animationMode() !== '3d' || state.motionJobId) return;
    const key = qs('#animation-3d-preset')?.value || '';
    const values = CAMERA_3D_PRESETS[key];
    if (!values) return;
    for (const field of CAMERA_3D_MOTION_FIELDS) {
      const input = qs('#animation-3d-' + field.replaceAll('_', '-'));
      if (input) input.value = '0:(' + String(values[field] ?? 0) + ')';
    }
    clearMotionPreviewResult();
    markDirty({ validate: true });
    refreshInspector();
    toast('Camera preset applied',
      'Updated the six 3D camera motion schedules. Save the project to retain them.',
      'info', 5800);
  }

  function applyCadencePreset() {
    const preset = qs('#animation-cadence-preset');
    const raw = qs('#animation-cadence');
    if (!preset || !raw || !state.project) return;
    if (preset.value === 'custom') {
      raw.focus();
      return;
    }
    raw.value = '0:(' + preset.value + ')';
    syncCadencePreset();
    markDirty({ validate: true });
  }

  function fillForm() {
    const project = state.project;
    syncMotionLabDraft();
    state.loading = true;
    try {
      renderProjectSelect();
      setEditorEnabled(Boolean(project));
      if (!project) {
        renderPromptRows();
        renderTimeline();
        renderDepthState();
        qs('#animation-project-path').textContent = 'Create or select an animation project.';
        qs('#animation-schema-badge').textContent = 'Choose a project';
        populateResolutionPresets();
        clearInspector();
        clearDirty();
        return;
      }

      qs('#animation-name').value = project.name || 'Untitled Animation';
      qs('#animation-max-frames').value = project.animation?.max_frames ?? 120;
      qs('#animation-fps').value = project.animation?.fps ?? 24;
      qs('#animation-width').value = project.animation?.width ?? 1024;
      qs('#animation-height').value = project.animation?.height ?? 1024;
      syncAnimationResolutionPreset();
      qs('#animation-mode').value = project.animation?.mode || '2d';
      qs('#animation-prompt-transition').value = project.animation?.prompt_transition || 'blend';
      qs('#animation-start-mode').value = project.animation?.start_mode || (project.animation?.source_image ? 'source' : 'prompt');
      qs('#animation-angle').value = project.motion?.angle || '0:(0)';
      qs('#animation-zoom').value = project.motion?.zoom || '0:(1.0)';
      qs('#animation-translation-x').value = project.motion?.translation_x || '0:(0)';
      qs('#animation-translation-y').value = project.motion?.translation_y || '0:(0)';
      qs('#animation-border-mode').value = project.motion?.border_mode || 'replicate';
      qs('#animation-3d-translation-x').value = project.camera_3d?.translation_x || '0:(0)';
      qs('#animation-3d-translation-y').value = project.camera_3d?.translation_y || '0:(0)';
      qs('#animation-3d-translation-z').value = project.camera_3d?.translation_z || '0:(0)';
      qs('#animation-3d-rotation-x').value = project.camera_3d?.rotation_x || '0:(0)';
      qs('#animation-3d-rotation-y').value = project.camera_3d?.rotation_y || '0:(0)';
      qs('#animation-3d-rotation-z').value = project.camera_3d?.rotation_z || '0:(0)';
      qs('#animation-3d-fov').value = project.camera_3d?.fov || '0:(40)';
      qs('#animation-3d-depth-resolution').value = project.camera_3d?.depth_resolution || 'auto';
      qs('#animation-3d-projection-mode').value = project.camera_3d?.projection_mode || 'legacy';
      qs('#animation-3d-hole-fill').value = project.camera_3d?.hole_fill || 'nearest';
      qs('#animation-strength').value = project.generation?.strength || '0:(0.65)';
      qs('#animation-noise').value = project.generation?.noise || '0:(0.02)';
      qs('#animation-steps').value = project.generation?.steps || '0:(20)';
      qs('#animation-guidance').value = project.generation?.guidance || '0:(0)';
      qs('#animation-cadence').value = project.cadence?.diffusion || '0:(1)';
      qs('#animation-temporal-mode').value = project.temporal?.mode || 'forward';
      qs('#animation-temporal-mix').value = project.temporal?.mix ?? 0.65;
      qs('#animation-temporal-contrast').value = project.temporal?.contrast_threshold ?? 96;
      syncCadencePreset();
      qs('#animation-seed').value = project.generation?.seed ?? -1;
      qs('#animation-seed-behavior').value = project.generation?.seed_behavior || 'fixed';
      qs('#animation-seed-increment').value = project.generation?.seed_increment ?? 1;
      qs('#animation-notes').value = project.notes || '';
      qs('#animation-hybrid-render-enabled').checked = project.hybrid?.enabled === true;
      qs('#animation-hybrid-offset').value = project.hybrid?.offset_frames ?? 0;
      qs('#animation-hybrid-composite-enabled').checked = project.hybrid?.composite_enabled === true;
      qs('#animation-hybrid-composite-opacity').value = project.hybrid?.composite_opacity ?? '0:(0.35)';
      qs('#animation-schema-badge').textContent = 'Project loaded';

      const projectFile = qs('#animation-project-path');
      if (projectFile) {
        projectFile.textContent = `${project.name || 'Untitled Animation'} · project.json`;
        projectFile.title = state.path || project.id;
      }

      populateModelSelect();
      populateSamplerSelect(project.generation?.sampler || '');
      const repairedGuidance = repairConstantGuidanceForSelectedModel();
      renderPromptRows();
      syncAnimationModeUi();
      renderSourceState();
      renderDepthState();
      syncInspectorBounds();
      renderTimeline();
      clearDirty();
      if (repairedGuidance) {
        state.dirty = true;
        setStatus('Guidance adjusted · save project', 'dirty');
      }
    } finally {
      state.loading = false;
    }

    window.setTimeout(() => {
      validateSchedules(false);
      refreshInspector();
    }, 0);
  }

  function collectPromptMaps() {
    const prompts = {};
    const negativePrompts = {};
    for (const row of qsa('.animation-prompt-row')) {
      const frame = Math.max(
        0,
        Math.trunc(Number(qs('.animation-prompt-frame', row)?.value || 0))
      );
      prompts[String(frame)] = qs('.animation-prompt-text', row)?.value || '';
      negativePrompts[String(frame)] = qs('.animation-negative-text', row)?.value || '';
    }
    if (!Object.prototype.hasOwnProperty.call(prompts, '0')) prompts['0'] = '';
    if (!Object.prototype.hasOwnProperty.call(negativePrompts, '0')) negativePrompts['0'] = '';
    return { prompts, negative_prompts: negativePrompts };
  }

  function collectProject() {
    if (!state.project) return null;
    const selectedModelId = qs('#animation-model')?.value || '';
    const selectedModel = modelById(selectedModelId);
    const existingModel = state.project.model || {};
    const promptMaps = collectPromptMaps();

    return {
      ...state.project,
      name: qs('#animation-name')?.value || 'Untitled Animation',
      animation: {
        ...(state.project.animation || {}),
        max_frames: Number(qs('#animation-max-frames')?.value || 120),
        fps: Number(qs('#animation-fps')?.value || 24),
        width: Number(qs('#animation-width')?.value || 1024),
        height: Number(qs('#animation-height')?.value || 1024),
        mode: animationMode(),
        prompt_transition: qs('#animation-prompt-transition')?.value || 'blend',
        start_mode: qs('#animation-start-mode')?.value || 'prompt',
      },
      model: {
        ...existingModel,
        model_id: selectedModel?.id || selectedModelId,
        family: selectedModel?.family || existingModel.family || '',
        variant: selectedModel?.variant || existingModel.variant || '',
      },
      ...promptMaps,
      motion: {
        ...(state.project.motion || {}),
        angle: qs('#animation-angle')?.value || '0:(0)',
        zoom: qs('#animation-zoom')?.value || '0:(1.0)',
        translation_x: qs('#animation-translation-x')?.value || '0:(0)',
        translation_y: qs('#animation-translation-y')?.value || '0:(0)',
        border_mode: qs('#animation-border-mode')?.value || 'replicate',
      },
      camera_3d: {
        ...(state.project.camera_3d || {}),
        translation_x: qs('#animation-3d-translation-x')?.value || '0:(0)',
        translation_y: qs('#animation-3d-translation-y')?.value || '0:(0)',
        translation_z: qs('#animation-3d-translation-z')?.value || '0:(0)',
        rotation_x: qs('#animation-3d-rotation-x')?.value || '0:(0)',
        rotation_y: qs('#animation-3d-rotation-y')?.value || '0:(0)',
        rotation_z: qs('#animation-3d-rotation-z')?.value || '0:(0)',
        fov: qs('#animation-3d-fov')?.value || '0:(40)',
        depth_resolution: qs('#animation-3d-depth-resolution')?.value || 'auto',
        projection_mode: qs('#animation-3d-projection-mode')?.value || 'legacy',
        hole_fill: qs('#animation-3d-hole-fill')?.value || 'nearest',
      },
      generation: {
        ...(state.project.generation || {}),
        strength: qs('#animation-strength')?.value || '0:(0.65)',
        noise: qs('#animation-noise')?.value || '0:(0.02)',
        steps: qs('#animation-steps')?.value || '0:(20)',
        guidance: qs('#animation-guidance')?.value || '0:(0)',
        sampler: qs('#animation-sampler')?.value || 'flowmatch_euler',
        seed: Number(qs('#animation-seed')?.value ?? -1),
        seed_behavior: qs('#animation-seed-behavior')?.value || 'fixed',
        seed_increment: Number(qs('#animation-seed-increment')?.value || 1),
      },
      cadence: {
        ...(state.project.cadence || {}),
        diffusion: qs('#animation-cadence')?.value || '0:(1)',
      },
      temporal: {
        mode: qs('#animation-temporal-mode')?.value || 'forward',
        mix: Number(qs('#animation-temporal-mix')?.value ?? 0.65),
        contrast_threshold: Number(qs('#animation-temporal-contrast')?.value ?? 96),
      },
      hybrid: {
        enabled: Boolean(qs('#animation-hybrid-render-enabled')?.checked),
        offset_frames: Number(qs('#animation-hybrid-offset')?.value ?? 0),
        end_policy: 'hold-last',
        composite_enabled: Boolean(qs('#animation-hybrid-composite-enabled')?.checked),
        composite_opacity: qs('#animation-hybrid-composite-opacity')?.value ?? '0:(0.35)',
      },
      notes: qs('#animation-notes')?.value || '',
    };
  }

  function formatNumber(value, digits = 5) {
    const number = Number(value);
    if (!Number.isFinite(number)) return '--';
    if (Number.isInteger(number)) return String(number);
    return number.toFixed(digits).replace(/0+$/, '').replace(/\.$/, '');
  }

  function formatPromptTransition(transition) {
    if (!transition) return '--';
    const from = transition.from_text || '(empty)';
    const to = transition.to_text || '(empty)';
    if (
      transition.from_frame === transition.to_frame ||
      Number(transition.to_weight) <= 0
    ) {
      return `F${transition.from_frame} · 100% · ${from}`;
    }
    const fromPct = Math.round(Number(transition.from_weight) * 100);
    const toPct = Math.round(Number(transition.to_weight) * 100);
    return `F${transition.from_frame} ${fromPct}% · ${from}  →  F${transition.to_frame} ${toPct}% · ${to}`;
  }

  function renderResolved(resolved) {
    const set = (id, text) => {
      const element = qs(id);
      if (element) element.textContent = text;
    };

    set('#resolved-time', `${formatNumber(resolved.time_seconds, 3)}s · F${resolved.frame}`);
    set('#resolved-zoom', formatNumber(resolved.motion?.zoom));
    set('#resolved-angle', `${formatNumber(resolved.motion?.angle)}°`);
    set('#resolved-translation-x', `${formatNumber(resolved.motion?.translation_x)} px`);
    set('#resolved-translation-y', `${formatNumber(resolved.motion?.translation_y)} px`);
    set('#resolved-3d-x', formatNumber(resolved.camera_3d?.translation_x));
    set('#resolved-3d-y', formatNumber(resolved.camera_3d?.translation_y));
    set('#resolved-3d-z', formatNumber(resolved.camera_3d?.translation_z));
    set('#resolved-3d-rx', `${formatNumber(resolved.camera_3d?.rotation_x)}°`);
    set('#resolved-3d-ry', `${formatNumber(resolved.camera_3d?.rotation_y)}°`);
    set('#resolved-3d-rz', `${formatNumber(resolved.camera_3d?.rotation_z)}°`);
    set('#resolved-3d-fov', `${formatNumber(resolved.camera_3d?.fov)}°`);
    set('#resolved-strength', formatNumber(resolved.generation?.strength));
    set('#resolved-noise', formatNumber(resolved.generation?.noise));
    set('#resolved-steps', formatNumber(resolved.generation?.steps));
    set('#resolved-guidance', formatNumber(resolved.generation?.guidance));
    set('#resolved-cadence', formatNumber(resolved.cadence?.diffusion));
    const loraText = Array.isArray(resolved.loras) && resolved.loras.length
      ? resolved.loras
          .map(lora => `${lora.name || lora.requested_name || 'LoRA'} ${formatNumber(lora.weight, 3)}`)
          .join(' · ')
      : 'None';
    set('#resolved-loras', loraText);

    const seed = resolved.generation?.seed || {};
    set(
      '#resolved-seed',
      seed.random_at_render
        ? `${seed.behavior || 'random'} · resolved at render`
        : String(seed.resolved)
    );

    set('#resolved-positive-prompt', formatPromptTransition(resolved.prompts?.positive));
    set('#resolved-negative-prompt', formatPromptTransition(resolved.prompts?.negative));
  }

  function clearInspector(message = 'Load a project to inspect resolved frame state.') {
    for (const id of [
      '#resolved-time',
      '#resolved-zoom',
      '#resolved-angle',
      '#resolved-translation-x',
      '#resolved-translation-y',
      '#resolved-3d-x',
      '#resolved-3d-y',
      '#resolved-3d-z',
      '#resolved-3d-rx',
      '#resolved-3d-ry',
      '#resolved-3d-rz',
      '#resolved-3d-fov',
      '#resolved-strength',
      '#resolved-noise',
      '#resolved-steps',
      '#resolved-guidance',
      '#resolved-cadence',
      '#resolved-seed',
      '#resolved-loras',
      '#resolved-positive-prompt',
      '#resolved-negative-prompt',
    ]) {
      const element = qs(id);
      if (element) element.textContent = '--';
    }
    const summary = qs('#animation-validation-summary');
    if (summary) {
      summary.className = 'animation-validation-summary';
      summary.textContent = message;
    }
    const path = qs('#animation-curve-path');
    if (path) path.setAttribute('d', '');
    const range = qs('#animation-curve-range');
    if (range) range.textContent = 'No curve loaded';
    const keyframes = qs('#animation-curve-keyframes');
    if (keyframes) keyframes.textContent = '';
  }

  function applyValidation(result) {
    for (const selector of Object.values(SCHEDULE_INPUTS)) {
      qs(selector)?.classList.remove('schedule-valid', 'schedule-warning', 'schedule-error');
    }

    for (const [field, info] of Object.entries(result.fields || {})) {
      const input = qs(SCHEDULE_INPUTS[field]);
      if (!input) continue;
      const hasError = (info.issues || []).some(issue => issue.severity === 'error');
      const hasWarning = (info.issues || []).some(issue => issue.severity === 'warning');
      input.classList.add(
        hasError ? 'schedule-error' : hasWarning ? 'schedule-warning' : 'schedule-valid'
      );
    }

    const summary = qs('#animation-validation-summary');
    if (!summary) return;

    const errors = (result.issues || []).filter(issue => issue.severity === 'error');
    const warnings = (result.issues || []).filter(issue => issue.severity === 'warning');

    summary.className = 'animation-validation-summary';
    if (errors.length) {
      summary.classList.add('error');
      const first = errors[0];
      summary.textContent = `${errors.length} schedule error${errors.length === 1 ? '' : 's'} · ${first.field}: ${first.message}`;
    } else if (warnings.length) {
      summary.classList.add('warning');
      const first = warnings[0];
      summary.textContent = `Schedules valid with ${warnings.length} warning${warnings.length === 1 ? '' : 's'} · ${first.message}`;
    } else {
      summary.classList.add('ok');
      summary.textContent = 'All animation schedules are valid.';
    }
  }

  async function validateSchedules(announce = false) {
    if (!state.project) return;
    const button = qs('#animation-validate-schedules');
    if (announce) setBusy(button, true);
    try {
      const result = await api('/api/animation/validate-schedules', {
        method: 'POST',
        body: JSON.stringify({ project: collectProject() }),
      });
      applyValidation(result);
      if (announce) {
        if (result.valid && !(result.issues || []).length) {
          toast('Schedules valid', 'All animation schedules resolved successfully.', 'success');
        } else if (result.valid) {
          toast('Schedules valid with warnings', result.issues[0]?.message || '', 'warning', 6500);
        } else {
          toast('Schedule validation failed', result.issues[0]?.message || '', 'error', 7000);
        }
      }
    } catch (error) {
      const summary = qs('#animation-validation-summary');
      if (summary) {
        summary.className = 'animation-validation-summary error';
        summary.textContent = error.message;
      }
      if (announce) toast('Schedule validation failed', error.message, 'error', 7000);
    } finally {
      if (announce) {
        setBusy(button, false);
        if (button) button.disabled = !state.project;
      }
    }
  }

  function drawCurve(series) {
    const path = qs('#animation-curve-path');
    const range = qs('#animation-curve-range');
    const keyframeText = qs('#animation-curve-keyframes');
    const samples = Array.isArray(series?.samples) ? series.samples : [];

    if (!path || !samples.length) {
      if (path) path.setAttribute('d', '');
      if (range) range.textContent = 'No curve loaded';
      return;
    }

    const values = samples.map(sample => Number(sample.value)).filter(Number.isFinite);
    if (!values.length) {
      path.setAttribute('d', '');
      return;
    }

    let minimum = Math.min(...values);
    let maximum = Math.max(...values);
    if (Math.abs(maximum - minimum) < 1e-12) {
      minimum -= 0.5;
      maximum += 0.5;
    }

    const left = 42;
    const right = 625;
    const top = 15;
    const bottom = 162;
    const maxFrame = Math.max(1, Number(series.max_frames || 1) - 1);
    const x = frame => left + (Number(frame) / maxFrame) * (right - left);
    const y = value => bottom - ((Number(value) - minimum) / (maximum - minimum)) * (bottom - top);

    const d = samples
      .map((sample, index) => `${index === 0 ? 'M' : 'L'}${x(sample.frame).toFixed(2)},${y(sample.value).toFixed(2)}`)
      .join(' ');
    path.setAttribute('d', d);

    if (range) {
      range.textContent = `${series.field} · ${formatNumber(minimum)} → ${formatNumber(maximum)}`;
    }
    if (keyframeText) {
      const frames = (series.keyframes || []).map(item => item.frame).join(', ');
      keyframeText.textContent = frames ? `Keyframes: ${frames}` : '';
    }
  }

  async function refreshCurve(project, sequence) {
    const field = qs('#animation-curve-field')?.value || 'motion.zoom';
    try {
      const series = await api('/api/animation/schedule-series', {
        method: 'POST',
        body: JSON.stringify({
          project,
          field,
          sample_count: 140,
        }),
      });
      if (sequence !== state.previewSequence) return;
      drawCurve(series);
    } catch (error) {
      if (sequence !== state.previewSequence) return;
      const path = qs('#animation-curve-path');
      if (path) path.setAttribute('d', '');
      const range = qs('#animation-curve-range');
      if (range) range.textContent = `${field} · ${error.message}`;
      const keyframes = qs('#animation-curve-keyframes');
      if (keyframes) keyframes.textContent = '';
    }
  }

  async function refreshInspector() {
    if (!state.project) return;
    const project = collectProject();
    if (!project) return;

    syncInspectorBounds();
    const frame = Math.max(
      0,
      Math.min(
        inspectorFrameMax(),
        Math.trunc(Number(qs('#animation-inspector-frame')?.value || 0))
      )
    );

    const sequence = ++state.previewSequence;
    try {
      const payload = await api('/api/animation/resolve-frame', {
        method: 'POST',
        body: JSON.stringify({ project, frame }),
      });
      if (sequence !== state.previewSequence) return;
      renderResolved(payload.resolved);
    } catch (error) {
      if (sequence !== state.previewSequence) return;
      const summary = qs('#animation-validation-summary');
      if (summary) {
        summary.className = 'animation-validation-summary error';
        summary.textContent = `Frame ${frame} cannot resolve · ${error.message}`;
      }
    }

    await refreshCurve(project, sequence);
  }

  function sourceImageUrl() {
    if (!state.project?.id || !state.project?.animation?.source_image) return '';
    const version = encodeURIComponent(state.project.updated_at || 'source');
    return '/api/animation/projects/' + encodeURIComponent(state.project.id) + '/source-image?v=' + version;
  }

  function renderSourceState() {
    const image = qs('#animation-source-preview');
    const empty = qs('#animation-source-empty');
    const meta = qs('#animation-source-meta');
    const clear = qs('#animation-clear-source');
    const preview = qs('#animation-generate-motion-preview');
    const fileInput = qs('#animation-source-file');
    const hasSource = Boolean(state.project?.animation?.source_image);
    const startMode = qs('#animation-start-mode')?.value || state.project?.animation?.start_mode || 'prompt';
    const requiresSource = startMode === 'source';
    const renderActive = ['queued', 'loading_model', 'rendering', 'finalizing'].includes(
      state.renderJob?.status
    );
    const badge = qs('#animation-start-mode-badge');
    const note = qs('#animation-start-mode-note');
    if (badge) badge.textContent = requiresSource ? 'Starting Image' : 'Prompt';
    if (note) {
      note.textContent = requiresSource
        ? (hasSource
            ? 'Frame 0 will use the uploaded image exactly; diffusion feedback begins on frame 1.'
            : 'Frame 0 requires an uploaded image in this mode. Upload one below before rendering.')
        : 'Frame 0 will be generated with the selected model and frame-0 prompt. An uploaded image is optional and can still be used for the camera-motion preview.';
    }
    if (image) {
      image.hidden = !hasSource;
      if (hasSource) image.src = sourceImageUrl();
      else image.removeAttribute('src');
    }
    if (empty) empty.hidden = hasSource;
    if (meta) meta.textContent = hasSource
      ? ((requiresSource ? 'Starting frame · ' : 'Optional preview reference · ') + (state.project.animation.source_image_name || 'uploaded image'))
      : (requiresSource ? 'No starting image uploaded.' : 'No image uploaded. Prompt mode does not require one.');
    if (fileInput) fileInput.disabled = !state.project || Boolean(state.motionJobId) || renderActive || state.depthBusy;
    if (clear) clear.disabled = !state.project || !hasSource || Boolean(state.motionJobId) || renderActive || state.depthBusy;
    // A source photo is optional: Motion Lab falls back to a calibration grid.
    if (preview) preview.disabled = !state.project || Boolean(state.motionJobId) || renderActive || state.depthBusy;
    const overlay = qs('#animation-preview-highlight-holes');
    if (overlay) overlay.disabled = !state.project || animationMode() !== '3d' ||
      Boolean(state.motionJobId) || renderActive || state.depthBusy;
    const renderButton = qs('#animation-start-render');
    if (renderButton) {
      const hasModel = Boolean(qs('#animation-model')?.value);
      renderButton.disabled = !state.project || !hasModel || (requiresSource && !hasSource) || renderActive || state.depthBusy;
    }
  }

  let motionGifSyncRun = 0;
  let motionGifPreviewUrl = null;
  let motionGifPreviewFps = null;
  function motionGifSyncStatus(message) {
    const node = qs('#animation-motion-gif-sync-status');
    if (node) node.textContent = message;
  }
  async function replayMotionGifWithAudio() {
    const image = qs('#animation-motion-preview-image');
    if (!image || !motionGifPreviewUrl) {
      motionGifSyncStatus('Generate a Camera Motion Preview first.');
      return;
    }
    const run = ++motionGifSyncRun;
    const audio = motionLabAudioElement;
    const synced = audio && motionLabAudioProjectId === state.project?.id &&
      qs('#animation-motion-lab-audio-sync')?.checked;
    // GIF playback cannot be paused or frame-seeked. Reloading the GIF at
    // the same time as the audio is a best-effort start synchronization.
    if (audio) {
      audio.pause();
      if (audio.readyState >= 1) audio.currentTime = 0;
    }
    image.removeAttribute('src');
    // Wait for the browser to be able to start the GIF, not an elapsed timeout.
    const next = new Image();
    next.onload = async () => {
      if (run !== motionGifSyncRun || !qs('#animation-motion-result') ||
          qs('#animation-motion-result').hidden) return;
      image.src = next.src;
      if (!synced) {
        motionGifSyncStatus('Preview restarted without audio. Analyze WAV and enable audio sync.');
        return;
      }
      try {
        audio.currentTime = 0;
        await audio.play();
        if (run === motionGifSyncRun) {
          motionGifSyncStatus('GIF and WAV restarted together (approximate sync; GIF timing is browser-dependent).');
        }
      } catch (error) {
        motionGifSyncStatus('Audio could not play: ' + (error?.message || String(error)));
      }
    };
    next.onerror = () => motionGifSyncStatus('Preview GIF failed to load.');
    next.src = motionGifPreviewUrl + (motionGifPreviewUrl.includes('?') ? '&' : '?') +
      'sync=' + Date.now() + '-' + run;
  }
  function clearMotionPreviewResult() {
    motionGifSyncRun++;
    motionGifPreviewUrl = null;
    motionGifPreviewFps = null;
    motionLabAudioElement?.pause();
    window.clearTimeout(state.motionPollTimer);
    state.motionPollTimer = null;
    state.motionJobId = null;
    const panel = qs('#animation-motion-progress');
    if (panel) panel.hidden = true;
    const result = qs('#animation-motion-result');
    if (result) result.hidden = true;
    const image = qs('#animation-motion-preview-image');
    if (image) image.removeAttribute('src');
    const meta = qs('#animation-motion-result-meta');
    if (meta) meta.textContent = '';
    const coverage = qs('#animation-camera-coverage');
    if (coverage) { coverage.hidden = true; coverage.textContent = ''; }
    const button = qs('#animation-generate-motion-preview');
    if (button) {
      button.classList.remove('busy');
      const label = qs('.button-label', button);
      if (label) label.textContent = 'Preview Camera Motion';
    }
    renderSourceState();
  }

  async function uploadSourceImage(file) {
    if (!state.project || !file) return;
    const input = qs('#animation-source-file');
    if (input) input.disabled = true;
    try {
      const response = await fetch('/api/animation/projects/' + encodeURIComponent(state.project.id) + '/source-image', {
        method: 'POST',
        headers: { 'Content-Type': file.type || 'application/octet-stream', 'X-Filename': file.name || 'source-image' },
        body: file,
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || (response.status + ' ' + response.statusText));
      state.project = {
        ...state.project,
        updated_at: payload.project?.updated_at || state.project.updated_at,
        animation: {
          ...(state.project.animation || {}),
          source_image: payload.project?.animation?.source_image || 'assets/source.png',
          source_image_name: payload.project?.animation?.source_image_name || file.name,
        },
      };
      state.depthPreview = null;
      clearMotionPreviewResult();
      renderSourceState();
      renderDepthState();
      toast('Source image uploaded', payload.source.width + ' × ' + payload.source.height + ' · ' + file.name, 'success');
    } catch (error) {
      toast('Source image upload failed', error.message, 'error', 7000);
    } finally {
      if (input) { input.disabled = !state.project; input.value = ''; }
    }
  }

  async function clearSourceImage() {
    if (!state.project?.animation?.source_image) return;
    const button = qs('#animation-clear-source');
    if (button) button.disabled = true;
    try {
      const payload = await api('/api/animation/projects/' + encodeURIComponent(state.project.id) + '/source-image', { method: 'DELETE' });
      state.project = {
        ...state.project,
        updated_at: payload.project?.updated_at || state.project.updated_at,
        animation: { ...(state.project.animation || {}), source_image: '', source_image_name: '' },
      };
      state.depthPreview = null;
      clearMotionPreviewResult();
      renderSourceState();
      renderDepthState();
      toast('Source image cleared', 'The project source image was removed.', 'success');
    } catch (error) {
      toast('Could not clear source image', error.message, 'error', 6500);
    } finally {
      renderSourceState();
    }
  }

  function updateMotionProgress(job) {
    const panel = qs('#animation-motion-progress');
    if (panel) panel.hidden = false;
    const percent = Math.max(0, Math.min(100, Math.round(Number(job.progress || 0) * 100)));
    const status = qs('#animation-motion-status');
    if (status) status.textContent = job.message || job.status;
    const percentEl = qs('#animation-motion-percent');
    if (percentEl) percentEl.textContent = percent + '%';
    const fill = qs('#animation-motion-progress-fill');
    if (fill) fill.style.width = percent + '%';
  }

  function finishMotionPreview(job) {
    state.motionJobId = null;
    window.clearTimeout(state.motionPollTimer);
    state.motionPollTimer = null;
    const button = qs('#animation-generate-motion-preview');
    if (button) {
      button.classList.remove('busy');
      const label = qs('.button-label', button);
      if (label) label.textContent = 'Preview Motion';
    }
    if (job.status === 'completed') {
      const result = qs('#animation-motion-result');
      const image = qs('#animation-motion-preview-image');
      const meta = qs('#animation-motion-result-meta');
      if (result) result.hidden = false;
      motionGifPreviewUrl = job.url;
      motionGifPreviewFps = Number(job.result?.fps || state.project?.animation?.fps || 12);
      if (image) image.src = job.url + '?v=' + Date.now();
      if (motionLabAudioElement && motionLabAudioProjectId === state.project?.id &&
          qs('#animation-motion-gif-auto-audio')?.checked &&
          qs('#animation-motion-lab-audio-sync')?.checked &&
          Math.abs(motionGifPreviewFps - Number(motionLabAudioAnalysis?.fps)) < 1e-6) {
        void replayMotionGifWithAudio();
      } else {
        motionGifSyncStatus('Preview ready. Replay Preview + Audio restarts the animation and WAV together.');
      }
      if (meta && job.result) meta.textContent =
        job.result.preview_width + ' × ' + job.result.preview_height + ' · ' +
        job.result.captured_frames + ' preview frames from ' + job.result.source_frames +
        ' project frames · ' + Number(job.result.duration_seconds || 0).toFixed(2) +
        's · ' + (job.result.source_kind === 'calibration-grid' ? 'Calibration grid' : 'Uploaded image') +
        ' · ' + (job.result.mode === '3d' ? '3D depth on CPU' : job.result.border_mode);
      const coverage = qs('#animation-camera-coverage');
      if (coverage) {
        coverage.hidden = job.result?.mode !== '3d';
        if (job.result?.mode === '3d') {
          const pct = value => (100 * Number(value || 0)).toFixed(1) + '%';
          coverage.textContent = 'Projected coverage: avg ' +
            pct(job.result.average_coverage) + ' · minimum ' +
            pct(job.result.minimum_coverage) + ' at frame ' +
            job.result.worst_coverage_frame + ' · final ' +
            pct(job.result.last_coverage) + ' · avg exposed ' +
            pct(1 - Number(job.result.average_coverage || 0)) +
            (job.result.highlight_holes ? ' · red overlay on' : '');
        }
      }
      toast('Motion preview complete', 'No diffusion model was loaded.', 'success');
    } else if (job.status === 'failed') {
      toast('Motion preview failed', job.error || job.message || 'Unknown preview error.', 'error', 8000);
    }
    renderSourceState();
  }

  async function pollMotionPreview(jobId) {
    try {
      const job = await api('/api/animation/motion-preview/' + encodeURIComponent(jobId));
      updateMotionProgress(job);
      if (job.status === 'completed' || job.status === 'failed') { finishMotionPreview(job); return; }
      state.motionPollTimer = window.setTimeout(() => pollMotionPreview(jobId), 350);
    } catch (_) {
      state.motionPollTimer = window.setTimeout(() => pollMotionPreview(jobId), 1000);
    }
  }

  async function generateMotionPreview(projectOverride = null) {
    if (!state.project || state.motionJobId) return;
    const button = qs('#animation-generate-motion-preview');
    if (button) {
      button.classList.add('busy');
      button.disabled = true;
      const label = qs('.button-label', button);
      if (label) label.textContent = 'Previewing…';
    }
    const result = qs('#animation-motion-result');
    if (result) result.hidden = true;
    const panel = qs('#animation-motion-progress');
    if (panel) panel.hidden = false;
    const fill = qs('#animation-motion-progress-fill');
    if (fill) fill.style.width = '0%';
    try {
      const job = await api('/api/animation/motion-preview', {
        method: 'POST',
        body: JSON.stringify({
          project: projectOverride?.animation && projectOverride?.tracks
            ? projectOverride : collectProject(),
          options: {
            highlight_holes: animationMode() === '3d' &&
              Boolean(qs('#animation-preview-highlight-holes')?.checked),
          },
        }),
      });
      state.motionJobId = job.id;
      updateMotionProgress(job);
      renderSourceState();
      pollMotionPreview(job.id);
    } catch (error) {
      state.motionJobId = null;
      if (button) {
        button.classList.remove('busy');
        const label = qs('.button-label', button);
        if (label) label.textContent = 'Preview Camera Motion';
      }
      renderSourceState();
      toast('Could not start motion preview', error.message, 'error', 7500);
    }
  }
  function renderIsActive(job = state.renderJob) {
    return Boolean(job && ['queued', 'loading_model', 'rendering', 'finalizing'].includes(job.status));
  }

  function formatSeconds(value) {
    const seconds = Number(value);
    if (!Number.isFinite(seconds) || seconds < 0) return '--';
    if (seconds < 60) return seconds.toFixed(seconds < 10 ? 1 : 0) + 's';
    const minutes = Math.floor(seconds / 60);
    const remain = Math.round(seconds % 60);
    return minutes + 'm ' + remain + 's';
  }

  function renderPromptTelemetryTransition(transition) {
    if (!transition || typeof transition !== 'object') {
      return { weights: '--', text: '--' };
    }
    const fromFrame = Number(transition.from_frame ?? 0);
    const toFrame = Number(transition.to_frame ?? fromFrame);
    const fromWeight = Math.max(0, Math.min(1, Number(transition.from_weight ?? 1)));
    const toWeight = Math.max(0, Math.min(1, Number(transition.to_weight ?? 0)));
    const fromText = String(transition.from_text || '(empty)');
    const toText = String(transition.to_text || fromText);
    const mode = String(transition.mode || 'blend');

    if (fromFrame === toFrame || toWeight <= 0 || fromText === toText) {
      return {
        weights: 'F' + fromFrame + ' · 100% · ' + mode,
        text: fromText,
      };
    }

    return {
      weights:
        'F' + fromFrame + ' ' + Math.round(fromWeight * 100) + '% → ' +
        'F' + toFrame + ' ' + Math.round(toWeight * 100) + '% · ' + mode,
      text: 'FROM: ' + fromText + '\nTO: ' + toText,
    };
  }

  function renderAnimationPromptTelemetry(job) {
    const panel = qs('#animation-render-prompt-telemetry');
    if (!panel) return;
    const promptState = job?.current_prompt_state;
    if (!promptState || typeof promptState !== 'object' || !Object.keys(promptState).length) {
      panel.hidden = true;
      return;
    }

    panel.hidden = false;
    const positive = renderPromptTelemetryTransition(promptState.positive);
    const negative = renderPromptTelemetryTransition(promptState.negative);
    const positiveWeights = qs('#animation-render-positive-weights');
    const positiveText = qs('#animation-render-positive-prompt');
    const negativeWeights = qs('#animation-render-negative-weights');
    const negativeText = qs('#animation-render-negative-prompt');
    if (positiveWeights) positiveWeights.textContent = positive.weights;
    if (positiveText) positiveText.textContent = positive.text;
    if (negativeWeights) negativeWeights.textContent = negative.weights;
    if (negativeText) negativeText.textContent = negative.text;

    const applied = qs('#animation-render-prompt-applied');
    if (applied) {
      applied.textContent = promptState.applied ? 'Applied to diffusion' : 'Resolved only';
      applied.className =
        'badge animation-render-prompt-applied ' +
        (promptState.applied ? 'applied' : 'skipped');
    }

    const meta = qs('#animation-render-prompt-meta');
    if (meta) {
      const loras = Array.isArray(promptState.loras) && promptState.loras.length
        ? promptState.loras
            .map(item => (item.name || item.requested_name || 'LoRA') + ' ' + formatNumber(item.weight, 3))
            .join(' · ')
        : 'none';
      const reason = String(promptState.reason || '').trim();
      meta.textContent =
        'Frame ' + Number(promptState.frame ?? job?.current_frame ?? 0) +
        ' · LoRAs: ' + loras +
        (reason ? ' · ' + reason : '');
    }
  }

  function renderAnimationFrameTelemetry(job) {
    const panel = qs('#animation-render-frame-telemetry');
    if (!panel) return;
    const frameState = job?.current_frame_state;
    if (!frameState || typeof frameState !== 'object' || !Object.keys(frameState).length) {
      panel.hidden = true;
      return;
    }

    panel.hidden = false;
    const motion = frameState.motion || {};
    const cumulative = frameState.cumulative_2d || {};
    const camera3d = frameState.camera_3d || {};
    const depth3d = frameState.depth_3d || {};
    const generation = frameState.generation || {};
    const renderMode = String(frameState.animation_mode || '2d').toLowerCase() === '3d' ? '3d' : '2d';

    qsa('[data-render-motion]').forEach(element => {
      element.hidden = element.dataset.renderMotion !== renderMode;
    });
    const label = qs('#animation-render-frame-state-label');
    if (label) {
      label.textContent = renderMode === '3d'
        ? 'Resolved 3D / generation state'
        : 'Resolved 2D / generation state';
    }

    const set = (selector, value) => {
      const element = qs(selector);
      if (element) element.textContent = value;
    };

    set('#animation-render-state-angle', formatNumber(motion.angle, 4) + '°');
    set('#animation-render-state-zoom', formatNumber(motion.zoom, 6) + '×');
    set('#animation-render-state-x', formatNumber(motion.translation_x, 4) + ' px');
    set('#animation-render-state-y', formatNumber(motion.translation_y, 4) + ' px');
    set('#animation-render-state-cum-zoom', formatNumber(cumulative.zoom, 6) + '×');
    set('#animation-render-state-cum-angle', formatNumber(cumulative.rotation_degrees, 4) + '°');
    set(
      '#animation-render-state-center',
      formatNumber(cumulative.center_offset_x, 3) + ', ' +
      formatNumber(cumulative.center_offset_y, 3) + ' px'
    );
    set('#animation-render-state-border', String(motion.border_mode || '--'));
    set('#animation-render-state-3d-x', formatNumber(camera3d.translation_x, 5));
    set('#animation-render-state-3d-y', formatNumber(camera3d.translation_y, 5));
    set('#animation-render-state-3d-z', formatNumber(camera3d.translation_z, 5));
    set('#animation-render-state-3d-rx', formatNumber(camera3d.rotation_x, 4) + '°');
    set('#animation-render-state-3d-ry', formatNumber(camera3d.rotation_y, 4) + '°');
    set('#animation-render-state-3d-rz', formatNumber(camera3d.rotation_z, 4) + '°');
    set('#animation-render-state-3d-fov', formatNumber(camera3d.fov, 3) + '°');
    set(
      '#animation-render-state-depth',
      depth3d.cache_key
        ? (
            (depth3d.cache_hit ? 'cache' : 'CPU') +
            ' · ' + formatNumber(depth3d.seconds, 2) + 's' +
            (depth3d.internal_width && depth3d.internal_height
              ? ' · ' + depth3d.internal_width + '×' + depth3d.internal_height
              : '')
          )
        : '--'
    );
    set(
      '#animation-render-state-coverage',
      depth3d.projected_coverage === undefined
        ? '--'
        : Math.round(Number(depth3d.projected_coverage) * 1000) / 10 + '%'
    );
    set('#animation-render-state-strength', formatNumber(generation.strength, 4));
    set(
      '#animation-render-state-denoise',
      generation.denoise_strength === null || generation.denoise_strength === undefined
        ? 'n/a'
        : formatNumber(generation.denoise_strength, 4)
    );
    set('#animation-render-state-noise', formatNumber(generation.noise, 4));
    set('#animation-render-state-steps', String(generation.steps ?? '--'));
    set('#animation-render-state-guidance', formatNumber(generation.guidance, 4));
    set('#animation-render-state-sampler', String(generation.sampler || '--'));
    set('#animation-render-state-seed', String(generation.seed ?? '--'));
    set(
      '#animation-render-state-seed-mode',
      String(generation.seed_behavior || '--') +
      (generation.seed_behavior === 'increment'
        ? ' +' + String(generation.seed_increment ?? 0)
        : '')
    );
    set(
      '#animation-render-state-cadence',
      String(frameState.cadence?.diffusion ?? '--') +
      (frameState.cadence?.anchor === false ? ' · transform frame' : ' · anchor')
    );
    const timings = frameState.timings || {};
    const timingParts = [
      ['depth', timings.depth],
      ['warp', timings.warp],
      ['cond', timings.conditioning],
      ['diff', timings.diffusion],
      ['save', timings.save],
      ['manifest', timings.manifest],
      ['mem', timings.memory],
    ]
      .filter(([, value]) => Number.isFinite(Number(value)))
      .map(([name, value]) => name + ' ' + formatNumber(value, 2) + 's');
    set('#animation-render-state-timing', timingParts.length ? timingParts.join(' · ') : '--');

    const mode = qs('#animation-render-diffusion-mode');
    if (mode) {
      const label = String(generation.diffusion_mode || '--').replaceAll('-', ' ');
      mode.textContent = frameState.motion_applied
        ? label + ' · motion applied'
        : label + ' · frame 0';
    }
  }

  function renderPerformanceSummary(job) {
    const panel = qs('#animation-performance-summary');
    const stats = qs('#animation-performance-stats');
    const link = qs('#animation-performance-report');
    const perf = job?.performance;
    const visible = Boolean(perf && Number(perf.frames_observed || 0) > 0);
    if (panel) panel.hidden = !visible;
    if (link) {
      if (visible && job.id && job.project_id) {
        link.href = '/api/animation/renders/' +
          encodeURIComponent(job.project_id) + '/' +
          encodeURIComponent(job.id) + '/performance';
      } else {
        link.removeAttribute('href');
      }
    }
    if (!stats) return;
    if (!visible) { stats.textContent = ''; return; }
    const gb = value => Number.isFinite(Number(value))
      ? Number(value).toFixed(2) + ' GiB' : '—';
    const secs = value => Number.isFinite(Number(value))
      ? Number(value).toFixed(2) + 's' : '—';
    stats.textContent =
      'Frames ' + perf.frames_observed +
      ' · diffusion anchors ' + perf.diffusion_anchors +
      ' · avg diffusion ' + secs(perf.average_anchor_diffusion_seconds) +
      ' · max GPU allocated ' + gb(perf.maximum_allocated_gib) +
      ' · max reserved ' + gb(perf.maximum_reserved_gib) +
      (perf.maximum_peak_allocated_gib
        ? ' · allocator peak ' + gb(perf.maximum_peak_allocated_gib)
        : '') +
      (perf.maximum_active_gib
        ? ' · max active ' + gb(perf.maximum_active_gib)
        : '') +
      (perf.allocator_backend
        ? ' · allocator ' + perf.allocator_backend
        : '') +
      (Number(perf.allocation_retries || 0)
        ? ' · alloc retries ' + perf.allocation_retries
        : '') +
      (Number(perf.oom_count || 0)
        ? ' · OOM count ' + perf.oom_count
        : '') +
      ' · resident LoRAs ≤ ' + perf.maximum_resident_loras +
      ' · execution ' + (perf.pipeline_device || 'not recorded') +
      ' · ' + (perf.optimization || 'unavailable');
    if ((perf.slow_anchor_frames || []).length) {
      stats.textContent += ' · slow anchors ' +
        perf.slow_anchor_frames.join(', ');
    }
  }

  function renderVideoExportState() {
    const job = state.renderJob;
    const isCompleted = job?.status === 'completed';
    const sameRender = Boolean(job?.id && job.id === state.videoRenderId);
    const activeExport = sameRender &&
      ['queued', 'encoding'].includes(state.videoJob?.status);
    const available = Boolean(state.videoAvailability?.available);
    const button = qs('#animation-export-video');
    if (button) {
      button.disabled = !isCompleted || !available || activeExport;
      button.classList.toggle('busy', Boolean(activeExport));
      const label = qs('.button-label', button);
      if (label) label.textContent = activeExport ? 'Encoding…' : 'Export Video';
    }
    const availability = qs('#animation-video-availability');
    if (availability) availability.textContent = !state.videoAvailability
      ? 'Checking FFmpeg…'
      : (available ? 'FFmpeg ready' : 'FFmpeg missing on host');
    const matching = sameRender ? state.videoExports : [];
    const latest = matching.find(item => item.status === 'completed' && item.url);
    const status = qs('#animation-video-job-status');
    if (status) {
      status.textContent = !available && state.videoAvailability
        ? state.videoAvailability.message
        : activeExport
          ? (state.videoJob.message || 'Encoding video…') + ' · ' +
            Math.round(100 * Number(state.videoJob.progress || 0)) + '%'
          : sameRender && state.videoJob?.status === 'failed'
            ? 'Video export failed: ' + (state.videoJob.error || 'Unknown FFmpeg error')
            : !isCompleted
              ? 'Select a completed render to encode its existing PNG sequence.'
              : latest
                ? 'Video available. The original PNG frames are unchanged.'
                : 'Ready to export the selected completed render.';
    }
    const result = qs('#animation-video-result');
    if (result) result.hidden = !latest;
    const video = qs('#animation-video-playback');
    const link = qs('#animation-video-download');
    const meta = qs('#animation-video-result-meta');
    if (latest) {
      const url = latest.url;
      if (video && video.dataset.videoUrl !== url) {
        video.dataset.videoUrl = url;
        video.src = url + '?inline=true';
        video.load();
      }
      if (link) { link.href = url; link.download = ''; }
      if (meta) meta.textContent =
        latest.format.toUpperCase() + ' · ' + latest.fps + ' fps · ' +
        latest.quality + ' · ' +
        (Number(latest.bytes || 0) / 1024 / 1024).toFixed(1) + ' MiB';
    } else if (video?.dataset.videoUrl) {
      video.pause();
      video.removeAttribute('src');
      delete video.dataset.videoUrl;
      video.load();
      if (link) link.removeAttribute('href');
    }
  }

  async function loadVideoExportHistory() {
    const job = state.renderJob;
    if (!job?.id || !state.project?.id) {
      state.videoExports = [];
      state.videoRenderId = '';
      renderVideoExportState();
      return;
    }
    const requestedRender = job.id;
    try {
      const response = await api(
        '/api/animation/renders/' + encodeURIComponent(state.project.id) +
        '/' + encodeURIComponent(requestedRender) + '/videos'
      );
      if (state.renderJob?.id !== requestedRender) return;
      state.videoRenderId = requestedRender;
      state.videoExports = Array.isArray(response.exports) ? response.exports : [];
    } catch (error) {
      if (state.renderJob?.id !== requestedRender) return;
      state.videoExports = [];
      state.videoRenderId = requestedRender;
      toast('Video export history unavailable', error.message, 'warning', 5500);
    }
    renderVideoExportState();
  }

  async function pollVideoExport(jobId) {
    if (state.videoJob?.id !== jobId) return;
    try {
      const job = await api('/api/animation/video/jobs/' + encodeURIComponent(jobId));
      if (state.videoJob?.id !== jobId) return;
      state.videoJob = job;
      renderVideoExportState();
      if (['queued', 'encoding'].includes(job.status)) {
        state.videoPollTimer = window.setTimeout(() => pollVideoExport(jobId), 700);
      } else {
        await loadVideoExportHistory();
        if (job.status === 'completed') {
          toast('Video export complete', 'Download your ' + job.format.toUpperCase() + ' video.', 'success');
        } else {
          toast('Video export failed', job.error || job.message, 'error', 8500);
        }
      }
    } catch (error) {
      if (state.videoJob?.id === jobId) {
        state.videoPollTimer = window.setTimeout(() => pollVideoExport(jobId), 1200);
      }
    }
  }

  async function startVideoExport() {
    const job = state.renderJob;
    if (!job?.id || !state.project?.id || job.status !== 'completed' ||
        !state.videoAvailability?.available) return;
    const fpsRaw = String(qs('#animation-video-fps')?.value || '').trim();
    const fps = fpsRaw ? Number(fpsRaw) : null;
    if (fps !== null && (!Number.isInteger(fps) || fps < 1 || fps > 120)) {
      toast('Invalid video FPS', 'Choose a whole number between 1 and 120.', 'warning');
      return;
    }
    const requestedRender = job.id;
    const button = qs('#animation-export-video');
    if (button) button.disabled = true;
    try {
      const exportJob = await api(
        '/api/animation/renders/' + encodeURIComponent(state.project.id) +
        '/' + encodeURIComponent(requestedRender) + '/video',
        {
          method: 'POST',
          body: JSON.stringify({
            format: qs('#animation-video-format')?.value || 'mp4',
            quality: qs('#animation-video-quality')?.value || 'balanced',
            fps,
          }),
        },
      );
      state.videoJob = exportJob;
      state.videoRenderId = requestedRender;
      renderVideoExportState();
      window.clearTimeout(state.videoPollTimer);
      pollVideoExport(exportJob.id);
      toast('Video export queued', 'FFmpeg is encoding saved PNGs. No diffusion is involved.', 'info');
    } catch (error) {
      toast('Cannot export video', error.message, 'error', 7000);
      renderVideoExportState();
    }
  }

  function resetRenderUi() {
    window.clearTimeout(state.renderPollTimer);
    state.renderPollTimer = null;
    state.renderJobId = null;
    state.renderJob = null;
    state.renderHistory = [];
    state.lastRenderFrameUrl = '';
    window.clearTimeout(state.videoPollTimer);
    state.videoPollTimer = null;
    state.videoJob = null;
    state.videoExports = [];
    state.videoRenderId = '';
    const loadProgress = qs('#animation-model-load-progress');
    if (loadProgress) loadProgress.hidden = true;
    const progress = qs('#animation-render-progress');
    if (progress) progress.hidden = true;
    renderAnimationPromptTelemetry(null);
    renderAnimationFrameTelemetry(null);
    const error = qs('#animation-render-error');
    if (error) { error.hidden = true; error.textContent = ''; }
    const frame = qs('#animation-render-latest-frame');
    if (frame) { frame.hidden = true; frame.removeAttribute('src'); }
    const frameEmpty = qs('#animation-render-frame-empty');
    if (frameEmpty) frameEmpty.hidden = false;
    const preview = qs('#animation-render-preview-image');
    if (preview) { preview.hidden = true; preview.removeAttribute('src'); }
    const previewEmpty = qs('#animation-render-preview-empty');
    if (previewEmpty) previewEmpty.hidden = false;
    const badge = qs('#animation-render-state');
    if (badge) { badge.textContent = 'Idle'; badge.className = 'badge'; }
    const select = qs('#animation-render-select');
    if (select) { select.replaceChildren(); const option = document.createElement('option'); option.value = ''; option.textContent = 'No renders yet'; select.appendChild(option); select.disabled = true; }
    const resume = qs('#animation-resume-render');
    if (resume) resume.disabled = true;
    const cancel = qs('#animation-cancel-render');
    if (cancel) cancel.disabled = true;
    const start = qs('#animation-start-render');
    if (start) { start.classList.remove('busy'); const label = qs('.button-label', start); if (label) label.textContent = 'Render Animation'; }
    renderSourceState();
    renderVideoExportState();
  }

  function renderAnimationJob(job) {
    state.renderJob = job || null;
    state.renderJobId = job?.id || null;
    const active = renderIsActive(job);

    const loadPanel = qs('#animation-model-load-progress');
    const loadProgressValue = Math.max(
      0,
      Math.min(1, Number(job?.load_progress || 0))
    );
    const showLoad = Boolean(
      job &&
      (
        job.status === 'loading_model' ||
        (loadProgressValue > 0 && loadProgressValue < 1)
      )
    );
    if (loadPanel) loadPanel.hidden = !showLoad;
    const loadPercent = Math.round(loadProgressValue * 100);
    const loadStatus = qs('#animation-model-load-status');
    if (loadStatus) loadStatus.textContent = job?.load_message || 'Preparing model pipeline…';
    const loadPercentEl = qs('#animation-model-load-percent');
    if (loadPercentEl) loadPercentEl.textContent = loadPercent + '%';
    const loadFill = qs('#animation-model-load-progress-fill');
    if (loadFill) loadFill.style.width = loadPercent + '%';
    const loadPhase = qs('#animation-model-load-phase');
    if (loadPhase) loadPhase.textContent = job?.load_phase
      ? String(job.load_phase).replaceAll('_', ' ')
      : 'Preparing';
    const loadDetail = qs('#animation-model-load-detail');
    if (loadDetail) loadDetail.textContent = job?.load_detail || '';

    const progress = qs('#animation-render-progress');
    if (progress) progress.hidden = !job;
    const badge = qs('#animation-render-state');
    if (badge) {
      badge.textContent = job ? String(job.status || 'unknown').replaceAll('_', ' ') : 'Idle';
      badge.className = 'badge animation-render-state ' + (job?.status || 'idle');
    }
    const percent = Math.max(0, Math.min(100, Math.round(Number(job?.progress || 0) * 100)));
    const status = qs('#animation-render-status');
    if (status) status.textContent = job?.message || 'Waiting…';
    const percentEl = qs('#animation-render-percent');
    if (percentEl) percentEl.textContent = percent + '%';
    const fill = qs('#animation-render-progress-fill');
    if (fill) fill.style.width = percent + '%';
    const overall = qs('#animation-overall-progress-track');
    if (overall) overall.setAttribute('aria-valuenow', String(percent));
    const frameStat = qs('#animation-render-frame');
    if (frameStat) frameStat.textContent = job ? ((Number(job.current_frame || 0) + 1) + ' / ' + Number(job.total_frames || 0)) : '--';
    const stepStat = qs('#animation-render-step');
    if (stepStat) stepStat.textContent = job ? String(job.current_step ?? 0) : '--';
    const stepPanel = qs('#animation-step-progress');
    if (stepPanel) stepPanel.hidden = !job;
    const stepTotal = Number(job?.current_step_total || 0);
    const currentStep = Math.max(0, Math.min(stepTotal, Number(job?.current_step || 0)));
    const stepPercent = stepTotal ? Math.min(100, Math.round(currentStep / stepTotal * 100)) : 0;
    const stepLabel = qs('#animation-step-progress-label');
    if (stepLabel) stepLabel.textContent = job?.status === 'loading_model' ? 'Loading model…' :
      job?.status === 'queued' ? 'Waiting for worker…' :
      job?.status === 'finalizing' ? 'Finalizing frames…' :
      stepTotal ? 'Diffusion step ' + currentStep + ' / ' + stepTotal :
      job?.status === 'rendering' ? 'No diffusion this frame' : 'No active diffusion';
    const stepValue = qs('#animation-step-progress-value');
    if (stepValue) stepValue.textContent = stepTotal ? stepPercent + '%' : '';
    const stepFill = qs('#animation-step-progress-fill');
    if (stepFill) stepFill.style.width = stepPercent + '%';
    const stepMeter = qs('#animation-step-progress-track');
    if (stepMeter) {
      stepMeter.setAttribute('aria-valuenow', String(stepPercent));
      stepMeter.setAttribute('aria-valuetext', stepTotal ? currentStep + ' of ' + stepTotal + ' steps' : 'No active diffusion');
    }
    window.dispatchEvent(new CustomEvent('morphorum:job-status', {detail: {
      
      type: 'animation', id: job?.id || null, status: job?.status || 'idle', progress: Number(job?.progress || 0),
      current: job ? Number(job.current_frame || 0) + 1 : 0, total: Number(job?.total_frames || 0),
      eta_seconds: job?.eta_seconds ?? null
    }}));

    const frameTime = qs('#animation-render-frame-time');
    if (frameTime) frameTime.textContent = formatSeconds(job?.frame_seconds);
    const eta = qs('#animation-render-eta');
    if (eta) eta.textContent = formatSeconds(job?.eta_seconds);

    const latest = qs('#animation-render-latest-frame');
    const latestEmpty = qs('#animation-render-frame-empty');
    if (job?.latest_frame_url) {
      const completedFrame = job.latest_completed_frame ?? job.current_frame ?? 0;
      const url = job.latest_frame_url + '?v=' + encodeURIComponent(String(completedFrame));
      if (state.lastRenderFrameUrl !== url && latest) { latest.src = url; state.lastRenderFrameUrl = url; }
      if (latest) latest.hidden = false;
      if (latestEmpty) latestEmpty.hidden = true;
    } else {
      if (latest) latest.hidden = true;
      if (latestEmpty) latestEmpty.hidden = false;
    }

    const preview = qs('#animation-render-preview-image');
    const previewEmpty = qs('#animation-render-preview-empty');
    if (job?.preview_url) {
      if (preview) { preview.src = job.preview_url + '?v=' + Date.now(); preview.hidden = false; }
      if (previewEmpty) previewEmpty.hidden = true;
    } else {
      if (preview) preview.hidden = true;
      if (previewEmpty) previewEmpty.hidden = false;
    }

    renderAnimationPromptTelemetry(job);
    renderAnimationFrameTelemetry(job);
    renderPerformanceSummary(job);

    const error = qs('#animation-render-error');
    if (error) {
      error.hidden = !job?.error;
      error.textContent = job?.error || '';
    }
    const cancel = qs('#animation-cancel-render');
    if (cancel) cancel.disabled = !active;
    const resume = qs('#animation-resume-render');
    if (resume) resume.disabled = !job?.resumable || active;
    const start = qs('#animation-start-render');
    if (start) {
      start.classList.toggle('busy', active);
      const label = qs('.button-label', start);
      if (label) {
        label.textContent = job?.status === 'loading_model'
          ? 'Loading Model…'
          : (active ? 'Rendering…' : 'Render Animation');
      }
    }
    renderSourceState();
    renderVideoExportState();
  }

  function populateRenderHistory(renders) {
    state.renderHistory = Array.isArray(renders) ? renders : [];
    const select = qs('#animation-render-select');
    if (!select) return;
    const selected = state.renderJobId || '';
    select.replaceChildren();
    if (!state.renderHistory.length) {
      const option = document.createElement('option'); option.value = ''; option.textContent = 'No renders yet'; select.appendChild(option); select.disabled = true; return;
    }
    for (const job of state.renderHistory) {
      const option = document.createElement('option');
      option.value = job.id;
      option.textContent = job.id + ' · ' + job.status + ' · ' + (job.total_frames || 0) + 'f';
      select.appendChild(option);
    }
    select.disabled = false;
    select.value = state.renderHistory.some(item => item.id === selected) ? selected : state.renderHistory[0].id;
  }

  async function loadRenderHistory() {
    if (!state.project?.id) { resetRenderUi(); return; }
    try {
      const payload = await api('/api/animation/projects/' + encodeURIComponent(state.project.id) + '/renders');
      const renders = Array.isArray(payload.renders) ? payload.renders : [];
      populateRenderHistory(renders);
      if (!state.renderJobId && renders.length) {
        renderAnimationJob(renders[0]);
        await loadVideoExportHistory();
      } else if (!renders.length && !state.renderJobId) {
        renderAnimationJob(null);
        await loadVideoExportHistory();
      }
    } catch (error) {
      toast('Could not load animation render history', error.message, 'warning', 6000);
    }
  }

  async function showRender(renderId) {
    if (!renderId) { renderAnimationJob(null); return; }
    try {
      const job = await api('/api/animation/renders/' + encodeURIComponent(renderId));
      renderAnimationJob(job);
      await loadVideoExportHistory();
      if (renderIsActive(job)) pollAnimationRender(job.id);
    } catch (error) {
      toast('Could not load animation render', error.message, 'error', 6500);
    }
  }

  async function pollAnimationRender(renderId) {
    window.clearTimeout(state.renderPollTimer);
    if (!renderId || renderId !== state.renderJobId) return;
    try {
      const job = await api('/api/animation/renders/' + encodeURIComponent(renderId));
      if (renderId !== state.renderJobId) return;
      renderAnimationJob(job);
      if (renderIsActive(job)) {
        state.renderPollTimer = window.setTimeout(() => pollAnimationRender(renderId), 700);
      } else {
        await loadRenderHistory();
        if (job.status === 'completed') toast('Animation render complete', job.message || '', 'success');
        else if (job.status === 'failed') toast('Animation render failed', job.error || job.message || '', 'error', 8000);
      }
    } catch (_) {
      if (renderId === state.renderJobId) state.renderPollTimer = window.setTimeout(() => pollAnimationRender(renderId), 1500);
    }
  }

  async function startAnimationRender() {
    if (!state.project || renderIsActive()) return;
    const project = collectProject();
    const button = qs('#animation-start-render');
    if (button) { button.classList.add('busy'); button.disabled = true; }
    try {
      const job = await api('/api/animation/renders', { method: 'POST', body: JSON.stringify({ project }) });
      state.renderJobId = job.id;
      renderAnimationJob(job);
      showAnimationTab('monitor');
      await loadRenderHistory();
      pollAnimationRender(job.id);
      toast('Animation render queued', 'Current browser project state was frozen into the render manifest.', 'success');
    } catch (error) {
      renderAnimationJob(null);
      toast('Could not start animation render', error.message, 'error', 8000);
    }
  }

  async function cancelAnimationRender() {
    if (!state.renderJobId || !renderIsActive()) return;
    try {
      const job = await api('/api/animation/renders/' + encodeURIComponent(state.renderJobId) + '/cancel', { method: 'POST' });
      renderAnimationJob(job);
    } catch (error) {
      toast('Could not cancel animation render', error.message, 'error', 6500);
    }
  }

  async function resumeAnimationRender() {
    const job = state.renderJob;
    if (!job?.id || !state.project?.id || !job.resumable) return;
    try {
      const resumed = await api('/api/animation/renders/' + encodeURIComponent(state.project.id) + '/' + encodeURIComponent(job.id) + '/resume', { method: 'POST' });
      state.renderJobId = resumed.id;
      renderAnimationJob(resumed);
      pollAnimationRender(resumed.id);
      toast('Animation render resumed', 'Continuing from the last completed frame.', 'success');
    } catch (error) {
      toast('Could not resume animation render', error.message, 'error', 7500);
    }
  }
  async function loadCapabilities() {
    try {
      const payload = await api('/api/generation/capabilities');
      state.capabilities = payload.families || {};
      populateSamplerSelect(state.project?.generation?.sampler || '');
      populateResolutionPresets();
    } catch (error) {
      state.capabilities = {};
      toast('Animation generation capabilities unavailable', error.message, 'warning', 6500);
    }
  }

  async function loadModels() {
    try {
      const payload = await api('/api/models?limit=2000');
      state.models = Array.isArray(payload.models) ? payload.models : [];
      populateModelSelect();
      populateDeforumModelSelect();
      populateSamplerSelect(state.project?.generation?.sampler || '');
    } catch (error) {
      toast('Animation model list unavailable', error.message, 'warning', 6000);
    }
  }


  function deforumCheckpointModels() {
    return state.models.filter(model => model.kind === 'checkpoints');
  }

  function populateDeforumModelSelect() {
    const select = qs('#animation-deforum-model');
    if (!select) return;
    const selected = select.value || '';
    const models = deforumCheckpointModels();
    select.replaceChildren();

    const none = document.createElement('option');
    none.value = '';
    none.textContent = models.length
      ? 'Choose an indexed checkpoint…'
      : 'No indexed checkpoints available';
    select.appendChild(none);

    for (const model of models) {
      const option = document.createElement('option');
      option.value = model.id;
      const variant = model.variant ? ' · ' + model.variant : '';
      option.textContent =
        String(model.name || model.id) +
        ' · ' + String(model.family || '').toUpperCase() +
        variant;
      select.appendChild(option);
    }
    select.value = models.some(model => model.id === selected) ? selected : '';
  }

  function setDeforumImportBusy(busy, message = '') {
    state.deforumImport.busy = Boolean(busy);
    const refresh = qs('#animation-deforum-refresh');
    const create = qs('#animation-deforum-create');
    const status = qs('#animation-deforum-status');
    if (refresh) {
      setBusy(refresh, busy);
      refresh.disabled = busy || !state.deforumImport.content;
    }
    if (create) {
      setBusy(create, busy);
      create.disabled =
        busy ||
        !state.deforumImport.report?.can_create ||
        !state.deforumImport.content;
    }
    if (status && message) status.textContent = message;
  }

  function closeDeforumImport() {
    const dialog = qs('#animation-deforum-dialog');
    if (!dialog) return;
    if (typeof dialog.close === 'function' && dialog.open) dialog.close();
    else dialog.removeAttribute('open');
  }

  function resetDeforumImport() {
    state.deforumImport = {
      content: '',
      filename: '',
      report: null,
      busy: false,
    };
    const file = qs('#animation-deforum-file');
    const name = qs('#animation-deforum-name');
    const filename = qs('#animation-deforum-filename');
    const status = qs('#animation-deforum-status');
    const summary = qs('#animation-deforum-summary');
    const warnings = qs('#animation-deforum-warnings');
    const mappings = qs('#animation-deforum-mappings');
    const warningCount = qs('#animation-deforum-warning-count');
    const mappingCount = qs('#animation-deforum-mapping-count');
    if (file) file.value = '';
    if (name) name.value = '';
    if (filename) filename.textContent = 'No file selected';
    if (status) status.textContent = 'Waiting';
    if (summary) {
      summary.hidden = true;
      summary.textContent = '';
    }
    if (warnings) {
      warnings.replaceChildren();
      const empty = document.createElement('p');
      empty.className = 'muted';
      empty.textContent = 'Choose a file to review any settings that need attention.';
      warnings.appendChild(empty);
    }
    if (mappings) {
      mappings.replaceChildren();
      const empty = document.createElement('p');
      empty.className = 'muted';
      empty.textContent = 'Mapped, unsupported, and preserved fields will appear here.';
      mappings.appendChild(empty);
    }
    if (warningCount) warningCount.textContent = '0';
    if (mappingCount) mappingCount.textContent = '0';
    populateDeforumModelSelect();
    setDeforumImportBusy(false);
  }

  function compactImportValue(value) {
    let text;
    try {
      text = typeof value === 'string' ? value : JSON.stringify(value);
    } catch (_) {
      text = String(value ?? '');
    }
    text = String(text ?? '').replace(/\s+/g, ' ').trim();
    return text.length > 180 ? text.slice(0, 177) + '…' : text;
  }

  function renderDeforumImportReport(report) {
    state.deforumImport.report = report || null;
    const summary = qs('#animation-deforum-summary');
    const warnings = qs('#animation-deforum-warnings');
    const mappings = qs('#animation-deforum-mappings');
    const warningCount = qs('#animation-deforum-warning-count');
    const mappingCount = qs('#animation-deforum-mapping-count');
    const status = qs('#animation-deforum-status');
    const create = qs('#animation-deforum-create');
    const project = report?.project || {};
    const animation = project.animation || {};

    if (summary) {
      if (report) {
        const mapped = (report.mappings || []).filter(item =>
          String(item.status || '').startsWith('mapped')
        ).length;
        const model = report.selected_model;
        summary.textContent = [
          (animation.mode || '2d').toUpperCase(),
          String(animation.width || '?') + ' × ' + String(animation.height || '?'),
          String(animation.max_frames || '?') + ' frames',
          String(animation.fps || '?') + ' fps',
          mapped + ' mapped fields',
          model ? String(model.name || model.id) : 'model not selected',
        ].join(' · ');
        summary.hidden = false;
      } else {
        summary.hidden = true;
        summary.textContent = '';
      }
    }

    const warningItems = Array.isArray(report?.warnings) ? report.warnings : [];
    if (warningCount) warningCount.textContent = String(warningItems.length);
    if (warnings) {
      warnings.replaceChildren();
      if (!warningItems.length) {
        const clean = document.createElement('p');
        clean.className = 'animation-import-ok';
        clean.textContent = 'No compatibility issues found for the selected model.';
        warnings.appendChild(clean);
      } else {
        for (const message of warningItems) {
          const item = document.createElement('div');
          item.className = 'animation-import-warning';
          item.textContent = String(message);
          warnings.appendChild(item);
        }
      }
    }

    const mappingItems = Array.isArray(report?.mappings) ? report.mappings : [];
    if (mappingCount) mappingCount.textContent = String(mappingItems.length);
    if (mappings) {
      mappings.replaceChildren();
      for (const item of mappingItems) {
        const row = document.createElement('div');
        row.className =
          'animation-import-mapping status-' +
          String(item.status || 'unknown').replace(/[^a-z0-9_-]/gi, '-');

        const source = document.createElement('div');
        const sourceKey = document.createElement('strong');
        sourceKey.textContent = String(item.source_key || 'unknown');
        const sourceValue = document.createElement('code');
        sourceValue.textContent = compactImportValue(item.source_value);
        source.append(sourceKey, sourceValue);

        const arrow = document.createElement('span');
        arrow.className = 'animation-import-map-arrow';
        arrow.textContent = '→';

        const target = document.createElement('div');
        const targetKey = document.createElement('strong');
        targetKey.textContent = item.target ? String(item.target) : String(item.status || 'preserved');
        const mappedValue = document.createElement('code');
        mappedValue.textContent =
          item.mapped_value === undefined
            ? (item.message || 'Setting kept for reference')
            : compactImportValue(item.mapped_value);
        target.append(targetKey, mappedValue);

        row.append(source, arrow, target);
        mappings.appendChild(row);
      }
      if (!mappingItems.length) {
        const empty = document.createElement('p');
        empty.className = 'muted';
        empty.textContent = 'No recognized settings were found in this file.';
        mappings.appendChild(empty);
      }
    }

    if (status) {
      if (!report) status.textContent = 'Waiting';
      else if (report.can_create) status.textContent = 'Ready to create';
      else if (report.model_required) status.textContent = 'Choose a model';
      else if (report.validation && !report.validation.valid) status.textContent = 'Validation errors';
      else status.textContent = 'Review required';
    }
    if (create) create.disabled = state.deforumImport.busy || !report?.can_create;
  }

  async function previewDeforumImport({ preserveName = true } = {}) {
    if (!state.deforumImport.content || state.deforumImport.busy) return;
    const model = qs('#animation-deforum-model');
    const name = qs('#animation-deforum-name');
    const priorName = preserveName ? String(name?.value || '').trim() : '';
    setDeforumImportBusy(true, 'Inspecting…');
    try {
      const report = await api('/api/animation/import/deforum/preview', {
        method: 'POST',
        body: JSON.stringify({
          content: state.deforumImport.content,
          filename: state.deforumImport.filename,
          model_id: model?.value || null,
          name: priorName || null,
        }),
      });
      renderDeforumImportReport(report);
      if (name && !priorName && report?.project?.name) {
        name.value = String(report.project.name);
      }
    } catch (error) {
      state.deforumImport.report = null;
      renderDeforumImportReport(null);
      const status = qs('#animation-deforum-status');
      if (status) status.textContent = 'Import error';
      toast('Deforum import preview failed', error.message, 'error', 8000);
    } finally {
      setDeforumImportBusy(false);
    }
  }

  async function chooseDeforumFile(event) {
    const file = event?.target?.files?.[0];
    if (!file) return;
    if (file.size > 1048576) {
      toast(
        'Deforum settings file is too large',
        'Choose a settings file smaller than 1 MiB.',
        'warning',
        6500
      );
      event.target.value = '';
      return;
    }

    try {
      const content = await file.text();
      resetDeforumImport();
      state.deforumImport.content = content;
      state.deforumImport.filename = file.name || 'deforum-settings.json';
      const filename = qs('#animation-deforum-filename');
      if (filename) filename.textContent = state.deforumImport.filename;
      const dialog = qs('#animation-deforum-dialog');
      if (dialog) {
        if (typeof dialog.showModal === 'function') dialog.showModal();
        else dialog.setAttribute('open', '');
      }
      await previewDeforumImport({ preserveName: false });
    } catch (error) {
      toast('Could not read Deforum settings', error.message, 'error', 7000);
    }
  }

  async function createDeforumProject() {
    const report = state.deforumImport.report;
    if (!report?.can_create || !state.deforumImport.content || state.deforumImport.busy) {
      return;
    }
    if (
      state.dirty &&
      !(await window.MorphorumDialog.confirm({
        title: 'Discard unsaved animation edits?',
        message: 'This opens the imported project and discards unsaved changes in the current browser project.',
        variant: 'danger', confirmText: 'Discard & Import', cancelText: 'Keep Editing',
      }))
    ) {
      return;
    }

    const model = qs('#animation-deforum-model');
    const name = qs('#animation-deforum-name');
    setDeforumImportBusy(true, 'Creating…');
    try {
      const payload = await api('/api/animation/import/deforum/create', {
        method: 'POST',
        body: JSON.stringify({
          content: state.deforumImport.content,
          filename: state.deforumImport.filename,
          model_id: model?.value || null,
          name: String(name?.value || '').trim() || null,
        }),
      });

      clearMotionPreviewResult();
      resetRenderUi();
      state.project = payload.project;
      resetHybridForProject();
      state.path = payload.path || '';
      state.timeline = null;
      state.timelineSelection = null;
      state.depthPreview = null;
      state.dirty = false;
      closeDeforumImport();

      await loadProjectList();
      fillForm();
      await loadTimeline();
      await loadDepthPreviewStatus();
      await loadRenderHistory();

      const count = Array.isArray(payload.import?.warnings)
        ? payload.import.warnings.length
        : 0;
      toast(
        'Deforum project imported',
        state.project.name +
          ' created as a new Morphorum project' +
          (count ? ' · ' + count + ' warning' + (count === 1 ? '' : 's') : '') +
          '.',
        count ? 'warning' : 'success',
        6500
      );
      resetDeforumImport();
    } catch (error) {
      const status = qs('#animation-deforum-status');
      if (status) status.textContent = 'Create failed';
      toast('Deforum import failed', error.message, 'error', 8000);
    } finally {
      setDeforumImportBusy(false);
    }
  }

  async function loadProjectList({ loadFirst = false } = {}) {
    const payload = await api('/api/animation/projects');
    state.projects = Array.isArray(payload.projects) ? payload.projects : [];
    renderProjectSelect();
    if (loadFirst && !state.project && state.projects.length) {
      await loadProject(state.projects[0].id, { confirmDirty: false });
    } else if (!state.project) {
      fillForm();
    }
  }

  async function loadProject(projectId, { confirmDirty = true } = {}) {
    if (!projectId) return;
    if (
      confirmDirty &&
      state.dirty &&
      !(await window.MorphorumDialog.confirm({
        title: 'Switch animation projects?',
        message: 'The current project has unsaved edits. Switching projects will discard those edits.',
        variant: 'danger', confirmText: 'Discard & Switch', cancelText: 'Keep Editing',
      }))
    ) {
      renderProjectSelect();
      return;
    }

    const select = qs('#animation-project-select');
    if (select) select.disabled = true;
    try {
      const payload = await api(`/api/animation/projects/${encodeURIComponent(projectId)}`);
      clearMotionPreviewResult();
      resetRenderUi();
      state.project = payload.project;
      resetHybridForProject();
      state.path = payload.path || '';
      state.timeline = null;
      state.timelineSelection = null;
      state.depthPreview = null;
      fillForm();
      await loadTimeline();
      await loadDepthPreviewStatus();
      await loadRenderHistory();
    } catch (error) {
      toast('Could not load animation project', error.message, 'error', 6500);
    } finally {
      if (select) select.disabled = state.projects.length === 0;
    }
  }

  async function createProject() {
    const requestedName = await window.MorphorumDialog.prompt({
      title: 'New animation project', message: 'Give the new animation project a name.',
      initialValue: 'New Animation', inputLabel: 'Project name', maxLength: 120,
      validate: value => value ? '' : 'Enter a project name.',
      confirmText: 'Create Project',
    });
    if (requestedName === null) return;
    const name = String(requestedName).trim();
    if (!name) {
      toast('Project name required', 'Enter a name before creating the animation project.', 'warning');
      return;
    }

    const button = qs('#animation-new');
    setBusy(button, true);
    try {
      const payload = await api('/api/animation/projects', {
        method: 'POST',
        body: JSON.stringify({ name }),
      });
      clearMotionPreviewResult();
      resetRenderUi();
      state.project = payload.project;
      resetHybridForProject();
      state.path = payload.path || '';
      state.timeline = null;
      state.timelineSelection = null;
      state.depthPreview = null;
      await loadProjectList();
      fillForm();
      await loadTimeline();
      await loadDepthPreviewStatus();
      await loadRenderHistory();
      toast('Animation project created', `${state.project.name} is ready for editing.`, 'success');
    } catch (error) {
      toast('Could not create animation project', error.message, 'error', 6500);
    } finally {
      setBusy(button, false);
    }
  }

  async function saveProject() {
    if (!state.project) return;
    const button = qs('#animation-save');
    setBusy(button, true);
    try {
      const payload = await api(
        `/api/animation/projects/${encodeURIComponent(state.project.id)}`,
        {
          method: 'PUT',
          body: JSON.stringify(collectProject()),
        }
      );
      state.project = payload.project;
      state.path = payload.path || state.path;
      await loadProjectList();
      fillForm();
      await loadTimeline();
      await loadRenderHistory();
      toast('Animation project saved', `${state.project.name} was written to project.json.`, 'success');
    } catch (error) {
      toast('Animation project save failed', error.message, 'error', 7000);
      setStatus('Save failed', 'error');
    } finally {
      setBusy(button, false);
    }
  }

  async function reloadProject() {
    if (!state.project) return;
    const button = qs('#animation-reload');
    setBusy(button, true);
    try {
      await loadProject(state.project.id, { confirmDirty: true });
      if (!state.dirty) {
        toast('Animation project reloaded', 'Saved project state restored.', 'success');
      }
    } finally {
      setBusy(button, false);
    }
  }


  // B6.2: independent managed-source lab. Never modifies animation project settings.
  const hybrid = {
    filename: '', info: null, jobId: '', timer: null, frames: null,
    requestToken: 0, previewRevision: 0,
  };
  function hybridClearPreview() {
    hybrid.frames = null;
    const preview = qs('#animation-hybrid-preview');
    const image = qs('#animation-hybrid-frame');
    if (preview) preview.hidden = true;
    if (image) image.removeAttribute('src');
  }
  function hybridProjectId() { return state.project?.id || ''; }
  function hybridBase() {
    return '/api/animation/projects/' + encodeURIComponent(hybridProjectId());
  }
  function hybridMessage(message) {
    const el = qs('#animation-hybrid-meta');
    if (el) el.textContent = message;
  }
  function hybridButtons() {
    const ready = Boolean(hybridProjectId() && hybrid.info);
    const status = qs('#animation-hybrid-status');
    if (status) status.textContent = hybridProjectId()
      ? (hybrid.frames ? hybrid.frames.frames + ' frames available' : 'Ready')
      : 'Select a project';
    const active = Boolean(hybrid.jobId);
    qs('#animation-hybrid-extract').disabled = !ready || active;
    qs('#animation-hybrid-cancel').disabled = !active;
    qs('#animation-hybrid-upload').disabled = !hybridProjectId() || active || !qs('#animation-hybrid-file')?.files?.length;
  }
  async function hybridLoadFrames() {
    const projectId = hybridProjectId();
    const token = hybrid.requestToken;
    const manifest = await api(hybridBase() + '/hybrid-frames?refresh=' + (++hybrid.previewRevision));
    if (hybridProjectId() !== projectId || hybrid.requestToken !== token) return;
    hybrid.frames = manifest;
    const slider = qs('#animation-hybrid-frame-slider');
    slider.max = String(manifest.frames);
    slider.value = '1';
    qs('#animation-hybrid-preview').hidden = false;
    hybridDisplayFrame();
    hybridButtons();
  }
  async function hybridRestoreProjectFrames() {
    const projectId = hybridProjectId();
    if (!projectId) return;
    try {
      await hybridLoadFrames();
      if (hybridProjectId() === projectId && hybrid.frames) {
        hybridMessage(hybrid.frames.frames + ' extracted source frames ready. Enable anchor input to use them in rendering.');
      }
    } catch (_) {
      if (hybridProjectId() === projectId) hybridButtons();
    }
  }
  function hybridDisplayFrame() {
    if (!hybrid.frames || !hybridProjectId()) return;
    const index = Math.max(1, Math.min(hybrid.frames.frames, Number(qs('#animation-hybrid-frame-slider').value) || 1));
    const revision = encodeURIComponent(String(hybrid.frames.extraction_id || hybrid.frames.source_mtime_ns || 'legacy'));
    qs('#animation-hybrid-frame').src = hybridBase() + '/hybrid-frames/' + index +
      '?revision=' + revision + '&refresh=' + hybrid.previewRevision;
    qs('#animation-hybrid-frame-caption').textContent = 'Frame ' + index + ' of ' + hybrid.frames.frames;
  }
  async function hybridUpload() {
    const file = qs('#animation-hybrid-file')?.files?.[0];
    if (!hybridProjectId()) return hybridMessage('Save or select a project first.');
    if (!file) return hybridMessage('Select a video file.');
    if (file.size > 512 * 1024 * 1024) return hybridMessage('Video exceeds 512 MiB limit.');
    const projectId = hybridProjectId();
    const token = ++hybrid.requestToken;
    hybrid.info = null;
    hybrid.filename = '';
    hybridClearPreview();
    hybridButtons();
    hybridMessage('Uploading and inspecting ' + file.name + '…');
    try {
      const reply = await api(hybridBase() + '/hybrid-video', {
        method: 'PUT', headers: { 'Content-Type': 'application/octet-stream', 'x-filename': file.name }, body: file,
      });
      if (hybridProjectId() !== projectId || hybrid.requestToken !== token) return;
      hybrid.filename = reply.video.storage_name;
      hybrid.info = reply.video;
      // The successful upload invalidates old extraction on the server.
      hybridClearPreview();
      qs('#animation-hybrid-end').value = String(Math.min(10, hybrid.info.duration_seconds));
      hybridMessage('Accepted ' + file.name + ': ' + reply.video.width + '×' + reply.video.height +
        ', ' + reply.video.duration_seconds + 's, ' + reply.video.fps +
        ' FPS. Previous extraction cleared; extract this video to continue.');
    } catch (error) {
      if (hybridProjectId() === projectId && hybrid.requestToken === token) {
        hybridMessage('Upload failed: ' + error.message + '. Previous source was not replaced.');
      }
    }
    if (hybridProjectId() === projectId && hybrid.requestToken === token) hybridButtons();
  }
  async function hybridPoll() {
    if (!hybrid.jobId) return;
    try {
      const data = await api(hybridBase() + '/hybrid-extraction/' + hybrid.jobId);
      hybridMessage('Extraction: ' + data.status + (data.error ? ' | ' + data.error : '') +
        (data.frames ? ' | ' + data.frames + ' frames' : ''));
      if (['completed', 'failed', 'canceled'].includes(data.status)) {
        hybrid.jobId = '';
        clearInterval(hybrid.timer);
        hybrid.timer = null;
        hybridButtons();
        if (data.status === 'completed') await hybridLoadFrames();
      }
    } catch (error) {
      clearInterval(hybrid.timer);
      hybrid.timer = null;
      hybrid.jobId = '';
      hybridMessage(error.message);
      hybridButtons();
    }
  }
  async function hybridExtract() {
    if (!hybrid.info || !hybridProjectId()) return;
    hybrid.requestToken++;
    hybridClearPreview();
    hybridMessage('Extracting new frames. Previous preview hidden…');
    try {
      const job = await api(hybridBase() + '/hybrid-extraction', {
        method: 'POST',
        body: JSON.stringify({ filename: hybrid.filename,
          start: Number(qs('#animation-hybrid-start').value),
          end: Number(qs('#animation-hybrid-end').value),
          fps: Number(qs('#animation-hybrid-fps').value) }),
      });
      hybrid.jobId = job.id;
      hybridMessage('Queued ' + job.estimated_frames + ' source frames…');
      hybridButtons();
      hybrid.timer = window.setInterval(hybridPoll, 900);
      hybridPoll();
    } catch (error) { hybridMessage('Extraction failed: ' + error.message); }
  }
  async function hybridCancel() {
    if (!hybrid.jobId) return;
    try { await api(hybridBase() + '/hybrid-extraction/' + hybrid.jobId + '/cancel', {method: 'POST'}); }
    catch (error) { hybridMessage('Cancel failed: ' + error.message); }
  }
  function resetHybridForProject() {
    if (hybrid.timer) window.clearInterval(hybrid.timer);
    hybrid.filename = '';
    hybrid.info = null;
    hybrid.jobId = '';
    hybrid.timer = null;
    hybrid.requestToken++;
    hybridClearPreview();
    const fileInput = qs('#animation-hybrid-file');
    if (fileInput) fileInput.value = '';
    hybridMessage('Checking for previously extracted frames…');
    hybridButtons();
    hybridRestoreProjectFrames();
  }
  function bindHybrid() {
    qs('#animation-hybrid-upload')?.addEventListener('click', hybridUpload);
    qs('#animation-hybrid-file')?.addEventListener('change', () => {
      // A selected replacement must never display the previous extraction.
      ++hybrid.requestToken;
      hybrid.filename = '';
      hybrid.info = null;
      hybridClearPreview();
      hybridMessage('New video selected. Upload & inspect, then extract its frames.');
      hybridButtons();
    });
    qs('#animation-hybrid-extract')?.addEventListener('click', hybridExtract);
    qs('#animation-hybrid-cancel')?.addEventListener('click', hybridCancel);
    qs('#animation-hybrid-frame-slider')?.addEventListener('input', hybridDisplayFrame);
    qs('#animation-hybrid-render-enabled')?.addEventListener('change', () => {
      markDirty();
      if (qs('#animation-hybrid-render-enabled')?.checked && !hybrid.frames) {
        hybridMessage('Extract frames in Media before rendering with hybrid input.');
      }
    });
    qs('#animation-hybrid-offset')?.addEventListener('change', () => markDirty());
    qs('#animation-hybrid-composite-enabled')?.addEventListener('change', () => {
      if (qs('#animation-hybrid-composite-enabled')?.checked) {
        const hybridEnabled = qs('#animation-hybrid-render-enabled');
        if (hybridEnabled && !hybridEnabled.checked) hybridEnabled.checked = true;
      }
      markDirty();
    });
    qs('#animation-hybrid-render-enabled')?.addEventListener('change', () => {
      if (!qs('#animation-hybrid-render-enabled')?.checked) {
        const composite = qs('#animation-hybrid-composite-enabled');
        if (composite) composite.checked = false;
      }
    });
    qs('#animation-hybrid-composite-opacity')?.addEventListener('input', () => markDirty());
    hybridButtons();
  }

  // ML0: draft preset layers exist separately from the applied animation
  // timeline. Only the Apply endpoint writes camera schedules or project.json.
  let motionLabProjectId = '';
  let motionLabDraftLayers = [];
  let motionLabBusy = false;
  let motionLabEditingIndex = -1;
  let motionLabVisual = null;
  let motionLabHistory = [[]];
  let motionLabHistoryIndex = 0;
  let motionLabRecorder = null;
  const motionLabRecordKeys = new Set();
  const motionLabRecordTouch = {
    translate: {x: 0, y: 0, pointerId: null},
    rotate: {x: 0, y: 0, pointerId: null},
    hold: {},
  };
  const MOTION_RECORD_KEYMAP = {
    KeyA: ['translation_x', -1], KeyD: ['translation_x', 1],
    KeyR: ['translation_y', 1], KeyF: ['translation_y', -1],
    KeyW: ['translation_z', 1], KeyS: ['translation_z', -1],
    ArrowUp: ['rotation_x', 1], ArrowDown: ['rotation_x', -1],
    ArrowLeft: ['rotation_y', -1], ArrowRight: ['rotation_y', 1],
    KeyQ: ['rotation_z', -1], KeyE: ['rotation_z', 1],
  };
  function motionLabRecordStatus(message, gamepad = false) {
    const target = qs(gamepad ? '#animation-motion-lab-gamepad-status' : '#animation-motion-lab-record-status');
    if (target) target.textContent = message;
  }
  function motionLabRecordClamp(value) {
    return Math.max(-1, Math.min(1, Number(value) || 0));
  }
  function motionLabRecordArmedAxes() {
    return qsa('[data-motion-record-axis]:checked').map(input => input.dataset.motionRecordAxis);
  }
  function motionLabRecordInverted(axis) {
    return Boolean(qs('[data-motion-record-invert="' + axis + '"]')?.checked);
  }
  function motionLabReadGamepad(values, sources) {
    if (!qs('#animation-motion-lab-record-gamepad')?.checked) return;
    if (typeof navigator.getGamepads !== 'function') {
      motionLabRecordStatus('Gamepad API unavailable in this browser/security context. Keyboard and touch still work.', true);
      return;
    }
    let pads = [];
    try {
      pads = Array.from(navigator.getGamepads() || []).filter(Boolean);
    } catch (_) {
      motionLabRecordStatus('Gamepad access was blocked by this browser/security context. Keyboard and touch still work.', true);
      return;
    }
    const pad = pads.find(item => item.connected !== false);
    if (!pad) {
      motionLabRecordStatus('No client-browser gamepad detected. Keyboard and touch still work.', true);
      return;
    }
    const axis = index => Number.isFinite(Number(pad.axes?.[index])) ? Number(pad.axes[index]) : 0;
    const button = index => Number.isFinite(Number(pad.buttons?.[index]?.value))
      ? Number(pad.buttons[index].value) : 0;
    values.translation_x += axis(0);
    values.translation_y += -axis(1);
    values.rotation_y += axis(2);
    values.rotation_x += -axis(3);
    values.translation_z += button(7) - button(6);
    values.rotation_z += button(5) - button(4);
    if ([...pad.axes || [], button(4),button(5),button(6),button(7)]
        .some(value => Math.abs(Number(value) || 0) > .001)) sources.push('gamepad');
    motionLabRecordStatus('Gamepad visible to this browser: ' + (pad.id || 'controller') + '.', true);
  }
  function motionLabRecordSampleInput() {
    const values = Object.fromEntries(MOTION_LAB_AXES.map(axis => [axis, 0]));
    const sources = [];
    for (const code of motionLabRecordKeys) {
      const mapping = MOTION_RECORD_KEYMAP[code];
      if (!mapping) continue;
      values[mapping[0]] += mapping[1];
    }
    if (motionLabRecordKeys.size) sources.push('keyboard');
    values.translation_x += motionLabRecordTouch.translate.x;
    values.translation_y += motionLabRecordTouch.translate.y;
    values.rotation_y += motionLabRecordTouch.rotate.x;
    values.rotation_x += motionLabRecordTouch.rotate.y;
    for (const [axis, value] of Object.entries(motionLabRecordTouch.hold)) {
      if (MOTION_LAB_AXES.includes(axis)) values[axis] += value;
    }
    if (Math.abs(motionLabRecordTouch.translate.x) > .001 ||
        Math.abs(motionLabRecordTouch.translate.y) > .001 ||
        Math.abs(motionLabRecordTouch.rotate.x) > .001 ||
        Math.abs(motionLabRecordTouch.rotate.y) > .001 ||
        Object.values(motionLabRecordTouch.hold).some(value => Math.abs(value) > .001)) {
      sources.push('touch');
    }
    motionLabReadGamepad(values, sources);
    for (const axis of MOTION_LAB_AXES) {
      values[axis] = motionLabRecordClamp(values[axis]);
      if (motionLabRecordInverted(axis)) values[axis] *= -1;
    }
    return {values, sources:[...new Set(sources)]};
  }
  function motionLabNeutralizeRecordInput() {
    motionLabRecordKeys.clear();
    motionLabRecordTouch.translate.x = motionLabRecordTouch.translate.y = 0;
    motionLabRecordTouch.rotate.x = motionLabRecordTouch.rotate.y = 0;
    motionLabRecordTouch.translate.pointerId = null;
    motionLabRecordTouch.rotate.pointerId = null;
    motionLabRecordTouch.hold = {};
    for (const id of ['animation-motion-lab-stick-translate','animation-motion-lab-stick-rotate']) {
      const knob = qs('#' + id + ' .animation-motion-stick-knob');
      if (knob) knob.style.transform = 'translate(0px, 0px)';
    }
  }
  function motionLabRecordLiveFrame(frame, sample, captured, fps, maxFrame) {
    const target = qs('#animation-motion-lab-record-frame');
    if (target) target.textContent =
      '● RECORDING · frame ' + frame + '/' + maxFrame +
      ' · ' + captured + ' sample(s) · ' + fps + ' FPS';
    const indicator = qs('#animation-motion-lab-live-indicator');
    if (indicator) indicator.textContent = '● RECORDING · ' + captured + ' frames captured';
    const axes = qs('#animation-motion-lab-live-axes');
    if (axes) axes.textContent = [
      'X ' + sample[0].toFixed(4), 'Y ' + sample[1].toFixed(4),
      'Z ' + sample[2].toFixed(4), 'Pitch ' + sample[3].toFixed(3) + '°',
      'Yaw ' + sample[4].toFixed(3) + '°', 'Roll ' + sample[5].toFixed(3) + '°',
    ].join(' · ');
    const input = qs('#animation-motion-lab-live-input');
    if (input) {
      const active = MOTION_LAB_AXES.filter((axis, index) =>
        Math.abs(sample[index]) > 0.000001).map(axis => axis.replaceAll('_',' '));
      input.textContent = active.length ? 'Movement: ' + active.join(', ') :
        'Neutral controls. Hold keyboard keys or drag a joystick to record movement.';
    }
  }
  function motionLabRecordFinishedFeedback(take) {
    const indicator = qs('#animation-motion-lab-live-indicator');
    if (indicator) indicator.textContent = '■ Stopped · ' + take.samples.length + ' frames';
    const target = qs('#animation-motion-lab-record-frame');
    if (target) target.textContent = 'Take captured: frames ' + take.startFrame +
      '–' + (take.endFrame - 1) + ' · ' + take.samples.length + ' samples';
    const input = qs('#animation-motion-lab-live-input');
    if (input) input.textContent =
      'Draft recording added to layer stack. Review curves; Apply to Animation to save.';
  }
  function motionLabSyncQuickActions() {
    const active = Boolean(motionLabRecorder?.active);
    for (const button of qsa('[data-motion-quick-target]')) {
      const original = qs('#' + button.dataset.motionQuickTarget);
      button.disabled = active || !original || original.disabled;
      button.setAttribute('aria-busy', String(Boolean(motionLabBusy)));
    }
    const status = qs('#animation-motion-lab-quick-status');
    if (status) status.textContent = active ? '● Recording' :
      motionLabBusy ? 'Updating motion…' :
      motionLabDraftLayers.length + ' draft layer(s)';
  }
  function motionLabSetupQuickActions(panel) {
    const dock = document.createElement('div');
    dock.id = 'animation-motion-lab-quick-actions';
    dock.className = 'animation-motion-lab-quick-actions';
    dock.setAttribute('role', 'toolbar');
    dock.setAttribute('aria-label', 'Motion Lab quick actions');
    const specs = [
      ['animation-motion-lab-record', '● Record'],
      ['animation-motion-lab-stop-recording', '■ Stop'],
      ['animation-motion-lab-update-curves', '↻ Curves'],
      ['animation-motion-lab-preview-draft', '▶ Preview'],
      ['animation-motion-lab-apply', 'Apply'],
    ];
    for (const [id, label] of specs) {
      const button = document.createElement('button');
      button.type = 'button';
      button.textContent = label;
      button.dataset.motionQuickTarget = id;
      button.className = id.endsWith('-apply') ? 'primary-button compact' : 'secondary-button compact';
      button.disabled = true;
      button.addEventListener('click', () => {
        const original = qs('#' + id);
        if (!original || original.disabled) return;
        original.click();
      });
      dock.appendChild(button);
    }
    const status = document.createElement('span');
    status.id = 'animation-motion-lab-quick-status';
    status.className = 'muted';
    status.setAttribute('aria-live', 'polite');
    dock.appendChild(status);
    panel.appendChild(dock);
    motionLabSyncQuickActions();
  }
  let motionLabPunchContext = null;
  function motionLabPunchUi() {
    const mode = qs('#animation-motion-lab-record-mode')?.value || 'new';
    const target = qs('#animation-motion-lab-punch-target');
    const end = qs('#animation-motion-lab-punch-end');
    if (target) {
      const selected = target.value;
      target.replaceChildren();
      const blank = document.createElement('option');
      blank.value = '';
      blank.textContent = 'Select a recorded take';
      target.appendChild(blank);
      motionLabDraftLayers.forEach((layer, index) => {
        if (layer.type !== 'recording') return;
        const option = document.createElement('option');
        option.value = String(index);
        option.textContent = (index + 1) + '. ' + (layer.name || 'Recorded take') +
          ' (' + layer.start_frame + '–' + (layer.end_frame - 1) + ')';
        target.appendChild(option);
      });
      if ([...target.options].some(o => o.value === selected)) target.value = selected;
      target.disabled = mode !== 'punch' || Boolean(motionLabRecorder?.active);
    }
    if (end) {
      end.disabled = mode !== 'punch' || Boolean(motionLabRecorder?.active);
      end.max = String(Number(state.project?.animation?.max_frames || 120));
    }
  }
  let motionLabAudioAnalysis = null;
  let motionLabAudioProjectId = null;
  let motionLabAudioElement = null;
  let motionLabAudioUrl = null;
  function motionLabReleaseAudio() {
    motionLabAudioElement?.pause();
    if (motionLabAudioElement) motionLabAudioElement.removeAttribute('src');
    if (motionLabAudioUrl) URL.revokeObjectURL(motionLabAudioUrl);
    motionLabAudioElement = null;
    motionLabAudioUrl = null;
  }
  function motionLabAudioSyncStatus(message) {
    const output = qs('#animation-motion-lab-audio-sync-status');
    if (output) output.textContent = message;
  }
  function motionLabAudioTime(frame, fps) {
    return Math.max(0, frame / Math.max(1, fps));
  }
  function motionLabSyncAudioFrame(frame) {
    const audio = motionLabAudioElement;
    if (!audio || !motionLabVisual ||
        motionLabAudioProjectId !== state.project?.id ||
        !qs('#animation-motion-lab-audio-sync')?.checked) return;
    const goal = motionLabAudioTime(frame, motionLabVisual.fps);
    if (audio.readyState >= 1 && Number.isFinite(audio.duration)) {
      const position = Math.min(goal, Math.max(0, audio.duration - .001));
      if (!motionLabVisual.playing || Math.abs(audio.currentTime - position) > .18) {
        audio.currentTime = position;
      }
      if (goal >= audio.duration && !audio.paused) audio.pause();
    }
  }
  function motionLabBindAudioTransport() {
    if (!motionLabVisual) return;
    const previousFrame = motionLabVisual.onFrameChange;
    motionLabVisual.onFrameChange = frame => {
      previousFrame?.(frame);
      motionLabSyncAudioFrame(frame);
    };
    motionLabVisual.onPlay = (frame, fps) => {
      const audio = motionLabAudioElement;
      if (!audio || !qs('#animation-motion-lab-audio-sync')?.checked ||
          motionLabAudioProjectId !== state.project?.id) return;
      const seek = motionLabAudioTime(frame, fps);
      if (audio.readyState >= 1 && seek < audio.duration) {
        audio.currentTime = seek;
        const promise = audio.play();
        promise?.catch(error => motionLabAudioSyncStatus(
          'Audio playback blocked by browser: ' + (error?.message || error)));
      }
    };
    motionLabVisual.onPause = () => motionLabAudioElement?.pause();
  }

  function motionLabAudioPreview() {
    const preview = qs('#animation-motion-lab-audio-preview');
    const plot = qs('#animation-motion-lab-audio-plot');
    const analysis = motionLabAudioAnalysis;
    if (!preview || !plot) return;
    if (!analysis || motionLabAudioProjectId !== state.project?.id ||
        Number(analysis.fps) !== Number(state.project?.animation?.fps) ||
        analysis.values.length !== Number(state.project?.animation?.max_frames)) {
      preview.hidden = true;
      plot.replaceChildren();
      return;
    }
    preview.hidden = false;
    const values = analysis.values;
    const threshold = Number(qs('#animation-motion-lab-audio-threshold')?.value);
    const gate = Number.isFinite(threshold) ? Math.max(0, Math.min(1, threshold)) : .1;
    const attack = Number(qs('#animation-motion-lab-audio-attack')?.value);
    const release = Number(qs('#animation-motion-lab-audio-release')?.value);
    const pulseLength = Number.isInteger(attack) && Number.isInteger(release) &&
      attack > 0 && release > 0 ? attack + release : 4;
    const peak = Math.max(0, ...values);
    const ceiling = Math.max(.05, peak * 1.08, gate * 1.08);
    const width = 800, bottom = 196, top = 12, height = bottom - top;
    const svgNS = 'http://www.w3.org/2000/svg';
    const make = (tag, attrs) => {
      const el = document.createElementNS(svgNS, tag);
      for (const [name, value] of Object.entries(attrs)) el.setAttribute(name, String(value));
      return el;
    };
    plot.replaceChildren();
    const grid = make('path', {
      d: [0, .25, .5, .75, 1].map(f => 'M0 ' + (bottom - f * height).toFixed(2) +
        ' H' + width).join(' '),
      stroke:'currentColor','stroke-opacity':'.13',fill:'none'
    });
    plot.appendChild(grid);
    const points = [];
    let onsets = 0, valid = 0, available = 1, prior = false;
    for (let i = 0; i < values.length; i++) {
      const x = ((i + .5) * width / values.length);
      const y = bottom - values[i] / ceiling * height;
      points.push((i ? 'L' : 'M') + x.toFixed(2) + ' ' + y.toFixed(2));
      const above = values[i] >= gate && values[i] > 0;
      if (above && !prior) {
        onsets++;
        if (i >= available && i >= 1 && i + pulseLength <= values.length) {
          valid++;
          plot.appendChild(make('circle', {cx:x.toFixed(2),cy:y.toFixed(2),
            r:3.6,fill:'#ffbd69',stroke:'#fff','stroke-width':'.65'}));
          available = i + pulseLength + 3;
        }
      }
      prior = above;
    }
    plot.appendChild(make('path', {d:points.join(' '),fill:'none',
      stroke:'#73d5ed','stroke-width':'2','vector-effect':'non-scaling-stroke'}));
    const thresholdY = bottom - gate / ceiling * height;
    plot.appendChild(make('line', {x1:0,y1:thresholdY,x2:width,y2:thresholdY,
      stroke:'#ff857c','stroke-width':2,'stroke-dasharray':'7 5',
      'vector-effect':'non-scaling-stroke'}));
    const summary = qs('#animation-motion-lab-audio-summary');
    if (summary) summary.textContent = 'Peak RMS ' + peak.toFixed(3) +
      ' · threshold ' + gate.toFixed(3) + ' · ' + values.length + ' frames';
    const prediction = qs('#animation-motion-lab-audio-prediction');
    if (prediction) prediction.textContent = valid
      ? valid + ' predicted complete motion pulse(s) from ' + onsets +
        ' upward threshold crossing(s). Move the threshold to preview changes before adding.'
      : 'No complete motion pulses at this threshold. Lower it or choose a file with stronger volume changes.';
  }
  function motionLabAudioUi() {
    const ready = Boolean(state.project?.id && animationMode() === '3d' && !motionLabBusy);
    const analyze = qs('#animation-motion-lab-analyze-audio');
    const add = qs('#animation-motion-lab-add-audio');
    if (analyze) analyze.disabled = !ready;
    if (add) add.disabled = !ready || motionLabDraftLayers.length >= 24 ||
      !motionLabAudioAnalysis || motionLabAudioProjectId !== state.project?.id ||
      Number(motionLabAudioAnalysis.fps) !== Number(state.project?.animation?.fps);
  }
  async function motionLabAnalyzeAudio() {
    const file = qs('#animation-motion-lab-audio-file')?.files?.[0];
    const projectId = state.project?.id;
    const status = qs('#animation-motion-lab-audio-info');
    if (!projectId || animationMode() !== '3d' || !file) {
      motionLabNotify('Choose a 3D project and PCM WAV audio file.');
      return;
    }
    if (file.size > 20 * 1024 * 1024) {
      motionLabNotify('WAV exceeds 20 MiB.');
      return;
    }
    motionLabAudioAnalysis = null;
    motionLabAudioProjectId = null;
    motionLabReleaseAudio();
    motionLabAudioPreview();
    if (status) status.textContent = 'Analyzing WAV on host…';
    motionLabAudioUi();
    try {
      const response = await fetch('/api/animation/projects/' + encodeURIComponent(projectId) +
        '/motion-lab/audio-analyze', {
        method:'POST',headers:{'Content-Type':'audio/wav'},body:file,
      });
      const result = await response.json();
      if (!response.ok) throw new Error(typeof result.detail === 'string' ?
        result.detail : 'Audio analysis failed (HTTP ' + response.status + ')');
      if (state.project?.id !== projectId) return;
      const analysis = result.analysis;
      if (!Array.isArray(analysis?.values) ||
          analysis.values.length !== Number(state.project.animation.max_frames) ||
          Number(analysis.fps) !== Number(state.project.animation.fps)) {
        throw new Error('Audio frame alignment changed; analyze again.');
      }
      motionLabAudioAnalysis = analysis;
      motionLabAudioProjectId = projectId;
      motionLabAudioUrl = URL.createObjectURL(file);
      motionLabAudioElement = new Audio(motionLabAudioUrl);
      motionLabAudioElement.preload = 'auto';
      motionLabAudioElement.load();
      motionLabAudioSyncStatus('Ready to play with Motion Curves playback.');
      const peak = Math.max(0, ...analysis.values);
      const thresholdField = qs('#animation-motion-lab-audio-threshold');
      if (thresholdField && peak > 0) {
        // File-specific starting point. Never require the user to guess the
        // analysis scale without seeing the envelope.
        thresholdField.value = Math.min(.1, peak * .55).toFixed(3);
      }
      motionLabAudioPreview();
      if (status) status.textContent = 'Analyzed ' + file.name + ': ' +
        analysis.values.length + ' frames · ' + analysis.duration_seconds.toFixed(2) +
        ' seconds · frame-aligned full-band RMS.';
      const badge = qs('#animation-motion-lab-audio-status');
      if (badge) badge.textContent = 'WAV ready';
    } catch (error) {
      if (status) status.textContent = 'Audio import failed: ' + (error?.message || error);
      motionLabNotify('Audio import failed: ' + (error?.message || error));
    }
    motionLabAudioUi();
    motionLabAudioPreview();
  }
  function motionLabAddAudio() {
    const analysis = motionLabAudioAnalysis;
    if (!analysis || !state.project || motionLabAudioProjectId !== state.project.id ||
        animationMode() !== '3d' || motionLabDraftLayers.length >= 24) return;
    const read = (id) => Number(qs('#animation-motion-lab-audio-' + id)?.value);
    const threshold = read('threshold');
    const distance = read('distance');
    const attack = read('attack');
    const release = read('release');
    if (!Number.isFinite(threshold) || threshold < 0 || threshold > 1 ||
        !Number.isFinite(distance) || distance < 0 || distance > 1 ||
        !Number.isInteger(attack) || attack < 1 || attack > 120 ||
        !Number.isInteger(release) || release < 1 || release > 120) {
      motionLabNotify('Check audio threshold, pulse amount, attack and release.');
      return;
    }
    const layer = {
      id:'audio-' + Date.now().toString(36), type:'audio',
      name:'Audio ' + analysis.filename.slice(0, 12), enabled:true, blend:'add',
      axis:qs('#animation-motion-lab-audio-axis')?.value || 'translation_z',
      start_frame:0,end_frame:analysis.values.length,
      fps:Number(analysis.fps),sha256:analysis.source_sha256,
      envelope:analysis.values.slice(),threshold,distance,
      attack_frames:attack,release_frames:release,cooldown_frames:3,offset_frames:0,
    };
    motionLabDraftLayers.push(layer);
    motionLabEditingIndex = -1;
    commitMotionLabDraft();
    motionLabNotify('Audio motion draft layer added. Preview Curves before Apply.');
    void motionLabPreviewOrApply(false,{curvesOnly:true});
  }
  function motionLabRecordingUi() {
    const ready = Boolean(state.project && animationMode() === '3d' && !motionLabBusy);
    const active = Boolean(motionLabRecorder?.active);
    const record = qs('#animation-motion-lab-record');
    const stop = qs('#animation-motion-lab-stop-recording');
    if (record) record.disabled = !ready || active ||
      (motionLabDraftLayers.length >= 24 && qs('#animation-motion-lab-record-mode')?.value !== 'punch');
    if (stop) stop.disabled = !active;
    const start = qs('#animation-motion-lab-record-start');
    const count = Number(state.project?.animation?.max_frames || 120);
    if (start) {
      start.max = String(Math.max(0, count - 1));
      start.disabled = !ready || active;
    }
    qsa('#animation-motion-lab-recording input, #animation-motion-lab-recording select')
      .forEach(control => {
        if (control.id === 'animation-motion-lab-record-start') return;
        if (control.id === 'animation-motion-lab-record-gamepad') {
          control.disabled = !ready || active;
          return;
        }
        if (control.matches('[data-motion-record-axis], [data-motion-record-invert]') ||
            control.closest('.animation-motion-recording-controls')) {
          control.disabled = !ready || active;
        }
      });
    motionLabPunchUi();
    if (!state.project) motionLabRecordStatus('Select a project');
    else if (animationMode() !== '3d') motionLabRecordStatus('3D Motion required');
    else if (!active) motionLabRecordStatus('Ready');
    motionLabSyncQuickActions();
  }
  function motionLabFinalizeRecording(take) {
    if (!take || take.reason === 'discard' || !state.project) {
      motionLabRecordingUi();
      return;
    }
    const count = Number(state.project.animation.max_frames || 120);
    if (!take.samples?.length || take.startFrame < 0 || take.endFrame > count) {
      motionLabNotify('Recorded take was empty or outside the current project and was not added.');
      motionLabRecordingUi();
      return;
    }
    if (!motionLabPunchContext && motionLabDraftLayers.length >= 24) {
      motionLabNotify('Motion Lab supports at most 24 layers; the take was not added.');
      motionLabRecordingUi();
      return;
    }
    const source = take.sources.length === 1 ? take.sources[0] :
      take.sources.length > 1 ? 'mixed' : 'unknown';
    const layer = {
      id: 'take-' + Date.now().toString(36),
      type: 'recording',
      name: 'Recorded ' + source + ' take',
      enabled: true,
      blend: qs('#animation-motion-lab-record-blend')?.value || 'add',
      start_frame: take.startFrame,
      end_frame: take.endFrame,
      fps: Number(take.fps),
      source,
      capture_version: 1,
      axes: take.armedAxes.slice(),
      samples: take.samples.map(row => row.slice()),
    };
    if (motionLabPunchContext) {
      const context = motionLabPunchContext;
      motionLabPunchContext = null;
      if (take.endFrame !== context.endFrame) {
        motionLabRecorder = null;
        motionLabNotify('Incomplete punch-in discarded. Capture the full selected frame range.');
        motionLabRecordingUi();
        return;
      }
      try {
        const existing = motionLabDraftLayers[context.index];
        if (!existing || existing.id !== context.id ||
            JSON.stringify(existing) !== context.snapshot) {
          throw new Error('Target take changed during recording. No edits were applied.');
        }
        motionLabDraftLayers[context.index] =
          window.MorphorumMotionLabSplicePunchIn(existing, take);
      } catch (error) {
        motionLabRecorder = null;
        motionLabNotify('Punch-in canceled: ' + (error?.message || String(error)));
        motionLabRecordingUi();
        return;
      }
      motionLabRecorder = null;
      motionLabNeutralizeRecordInput();
      commitMotionLabDraft();
      motionLabRecordFinishedFeedback(take);
      motionLabNotify('Punch-in replaced frames ' + take.startFrame + '–' +
        (take.endFrame - 1) + ' on armed axes only. Undo restores the original take.');
      void motionLabPreviewOrApply(false, {curvesOnly:true});
      motionLabRecordingUi();
      return;
    }
    motionLabDraftLayers.push(layer);
    motionLabRecordFinishedFeedback(take);
    motionLabRecorder = null;
    motionLabNeutralizeRecordInput();
    motionLabNotify(
      'Recorded ' + layer.samples.length + ' frame(s) from ' + layer.start_frame +
      '–' + (layer.end_frame - 1) + '. Take added as a draft layer; Update Curves or Apply when ready.'
    );
    commitMotionLabDraft();
    const start = qs('#animation-motion-lab-record-start');
    // A second take should not unexpectedly begin on the final frame.
    // Preserve the explicit start selection for repeat takes.
    void motionLabPreviewOrApply(false, {curvesOnly:true});
    motionLabRecordingUi();
  }
  function motionLabStartRecording() {
    if (!state.project || animationMode() !== '3d' || motionLabBusy) {
      motionLabNotify('Choose a 3D project before recording camera motion.');
      return;
    }
    if (!window.MorphorumMotionLabFrameRecorder) {
      motionLabNotify('Motion recorder asset is unavailable. Hard-refresh the browser and try again.');
      return;
    }
    const isPunch = qs('#animation-motion-lab-record-mode')?.value === 'punch';
    if (!isPunch && motionLabDraftLayers.length >= 24) {
      motionLabNotify('Motion Lab supports at most 24 layers.');
      return;
    }
    const axes = motionLabRecordArmedAxes();
    if (!axes.length) {
      motionLabNotify('Arm at least one camera axis before recording.');
      return;
    }
    const count = Number(state.project.animation.max_frames || 120);
    const fps = Number(state.project.animation.fps || 12);
    const startFrame = Number(qs('#animation-motion-lab-record-start')?.value || 0);
    const translationScale = Number(qs('#animation-motion-lab-record-translation')?.value);
    const rotationScale = Number(qs('#animation-motion-lab-record-rotation')?.value);
    const deadzone = Number(qs('#animation-motion-lab-record-deadzone')?.value);
    const response = Number(qs('#animation-motion-lab-record-response')?.value);
    const tailFrames = Number(qs('#animation-motion-lab-record-tail')?.value);
    let punch = null;
    if (isPunch) {
      const raw = qs('#animation-motion-lab-punch-target')?.value;
      const index = raw === '' || raw == null ? -1 : Number(raw);
      const target = motionLabDraftLayers[index];
      const endFrame = Number(qs('#animation-motion-lab-punch-end')?.value);
      if (!target || target.type !== 'recording' ||
          !Number.isInteger(endFrame) || endFrame <= startFrame ||
          startFrame < target.start_frame || endFrame > target.end_frame ||
          Number(target.fps) !== fps || axes.some(axis => !target.axes.includes(axis))) {
        motionLabNotify('Punch-in requires a recorded target, matching FPS, an interval inside it and axes armed on that take.');
        return;
      }
      punch = {index, id:target.id, snapshot:JSON.stringify(target), endFrame};
    }

    if (!Number.isInteger(startFrame) || startFrame < 0 || startFrame >= count ||
        !Number.isFinite(translationScale) || translationScale <= 0 ||
        !Number.isFinite(rotationScale) || rotationScale <= 0 ||
        !Number.isFinite(deadzone) || deadzone < 0 || deadzone > .5 ||
        !Number.isFinite(response) || response < .05 || response > 1 ||
        !Number.isInteger(tailFrames) || tailFrames < 0 || tailFrames > 12) {
      motionLabNotify('Check recording start, sensitivity, deadzone, response and release-tail settings.');
      return;
    }
    motionLabNeutralizeRecordInput();
    motionLabVisual?.pause();
    const remainingFrames = punch ? punch.endFrame - startFrame : count - startFrame;
    const startStatus = qs('#animation-motion-lab-record-frame');
    if (startStatus) startStatus.textContent =
      '● Starting capture at frame ' + startFrame + ' · ' + remainingFrames +
      ' available frames (' + (remainingFrames / fps).toFixed(1) + ' seconds)';
    const indicator = qs('#animation-motion-lab-live-indicator');
    if (indicator) indicator.textContent = '● RECORDING';
    motionLabRecordStatus('● Recording ' + fps + ' FPS');
    motionLabNotify('Recording active: keyboard, joysticks, Z/roll buttons and optional gamepad. Stop creates a draft layer.');
    motionLabPunchContext = punch;
    motionLabRecorder = new window.MorphorumMotionLabFrameRecorder();
    try {
      motionLabRecorder.start({
      fps, startFrame, maxFrames: remainingFrames, armedAxes: axes,
      translationScale, rotationScale, deadzone, response, tailFrames,
      sampleInput: motionLabRecordSampleInput,
      onFrame: ({frame, count: captured, sample}) => {
        motionLabRecordLiveFrame(frame, sample, captured, fps, count - 1);
        // During recording the saved curves are stale; only drive their
        // playhead when actual compiled series are present.
        if (motionLabVisual?.series && !motionLabVisual.stale) motionLabVisual.setFrame(frame);
      },
      onComplete: take => motionLabFinalizeRecording(take),
      });
    } catch (error) {
      motionLabRecorder = null;
      motionLabPunchContext = null;
      motionLabRecordStatus('Recording failed');
      motionLabNotify('Unable to start recording: ' + (error?.message || String(error)));
      const failed = qs('#animation-motion-lab-live-indicator');
      if (failed) failed.textContent = 'Recording failed';
    }
    motionLabRecordingUi();
  }
  function motionLabStopRecording(reason = 'manual') {
    if (!motionLabRecorder?.active) return;
    motionLabNeutralizeRecordInput();
    motionLabRecorder.stop(reason);
  }
  function motionLabDiscardRecording() {
    if (!motionLabRecorder?.active) return;
    motionLabNeutralizeRecordInput();
    motionLabRecorder.finish('discard');
    motionLabPunchContext = null;
    motionLabRecorder = null;
    motionLabRecordingUi();
  }
  function motionLabBindStick(id, targetName) {
    const stick = qs('#' + id);
    if (!stick) return;
    const stateTarget = motionLabRecordTouch[targetName];
    const update = event => {
      const rect = stick.getBoundingClientRect();
      const radius = Math.max(1, Math.min(rect.width, rect.height) * .38);
      let x = (event.clientX - (rect.left + rect.width / 2)) / radius;
      let y = (event.clientY - (rect.top + rect.height / 2)) / radius;
      const length = Math.hypot(x, y);
      if (length > 1) { x /= length; y /= length; }
      stateTarget.x = x;
      stateTarget.y = -y;
      const knob = stick.querySelector('.animation-motion-stick-knob');
      if (knob) knob.style.transform =
        'translate(' + (x * radius * .58).toFixed(1) + 'px, ' + (y * radius * .58).toFixed(1) + 'px)';
    };
    const release = event => {
      if (stateTarget.pointerId !== null && event?.pointerId !== undefined &&
          event.pointerId !== stateTarget.pointerId) return;
      stateTarget.x = stateTarget.y = 0;
      stateTarget.pointerId = null;
      const knob = stick.querySelector('.animation-motion-stick-knob');
      if (knob) knob.style.transform = 'translate(0px, 0px)';
    };
    stick.addEventListener('pointerdown', event => {
      if (!motionLabRecorder?.active) return;
      event.preventDefault();
      stateTarget.pointerId = event.pointerId;
      stick.setPointerCapture?.(event.pointerId);
      update(event);
    });
    stick.addEventListener('pointermove', event => {
      if (!motionLabRecorder?.active || stateTarget.pointerId !== event.pointerId) return;
      event.preventDefault();
      update(event);
    });
    stick.addEventListener('pointerup', release);
    stick.addEventListener('pointercancel', release);
    stick.addEventListener('lostpointercapture', release);
  }
  function motionLabBindHoldControls() {
    qsa('[data-motion-hold-axis]').forEach(button => {
      const axis = button.dataset.motionHoldAxis;
      const value = Number(button.dataset.motionHoldValue);
      const release = () => {
        if (motionLabRecordTouch.hold[axis] === value) delete motionLabRecordTouch.hold[axis];
        button.classList.remove('active');
      };
      button.addEventListener('pointerdown', event => {
        if (!motionLabRecorder?.active || !MOTION_LAB_AXES.includes(axis)) return;
        event.preventDefault();
        motionLabRecordTouch.hold[axis] = motionLabRecordClamp(value);
        button.classList.add('active');
        button.setPointerCapture?.(event.pointerId);
      });
      button.addEventListener('pointerup', release);
      button.addEventListener('pointercancel', release);
      button.addEventListener('lostpointercapture', release);
    });
  }
  function commitMotionLabDraft() {
    const snapshot = JSON.stringify(motionLabDraftLayers);
    if (JSON.stringify(motionLabHistory[motionLabHistoryIndex]) === snapshot) {
      renderMotionLabDraft();
      return;
    }
    motionLabHistory = motionLabHistory.slice(0, motionLabHistoryIndex + 1);
    motionLabHistory.push(JSON.parse(snapshot));
    if (motionLabHistory.length > 51) motionLabHistory.shift();
    motionLabHistoryIndex = motionLabHistory.length - 1;
    motionLabVisual?.invalidate();
    renderMotionLabDraft();
  }
  function restoreMotionLabDraft(direction) {
    const next = motionLabHistoryIndex + direction;
    if (next < 0 || next >= motionLabHistory.length) return;
    motionLabHistoryIndex = next;
    motionLabDraftLayers = motionLabHistory[next].map(layer => ({ ...layer }));
    motionLabEditingIndex = -1;
    motionLabVisual?.invalidate();
    renderMotionLabDraft();
    motionLabNotify('Draft layer change ' + (direction < 0 ? 'undone' : 'redone') +
      '. Update Curves to view the new motion.');
  }
  function syncMotionLabDraft() {
    const projectId = state.project?.id || '';
    if (projectId === motionLabProjectId) return;
    if (motionLabRecorder?.active && projectId !== motionLabProjectId) motionLabDiscardRecording();
    motionLabProjectId = projectId;
    motionLabEditingIndex = -1;
    motionLabDraftLayers = Array.isArray(state.project?.motion_lab?.layers)
      ? state.project.motion_lab.layers.map(layer => ({ ...layer })) : [];
    motionLabHistory = [motionLabDraftLayers.map(layer => ({ ...layer }))];
    motionLabHistoryIndex = 0;
    motionLabVisual?.clear();
    renderMotionLabDraft();
  }
  function renderMotionLabDraft() {
    const project = state.project;
    const is3d = animationMode() === '3d';
    const ready = Boolean(project && is3d && !motionLabBusy);
    const count = Number(project?.animation?.max_frames || 120);
    motionLabRecordingUi();
    motionLabAudioUi();
    const stage = qs('#animation-motion-lab-compose-status');
    if (stage) stage.textContent = !project ? 'Select a project' :
      !is3d ? '2D project (switch to 3D here)' : motionLabDraftLayers.length +
      ' draft layer' + (motionLabDraftLayers.length === 1 ? '' : 's');
    const quick3d = qs('#animation-motion-lab-enable-3d');
    if (quick3d) {
      quick3d.hidden = !project || is3d;
      quick3d.disabled = motionLabBusy || Boolean(state.motionJobId);
    }
    for (const id of ['animation-motion-lab-add','animation-motion-lab-clear',
      'animation-motion-lab-preview-draft','animation-motion-lab-apply',
      'animation-motion-lab-update-curves']) {
      const button = qs('#' + id);
      if (!button) continue;
      const needsLayers = id !== 'animation-motion-lab-add';
      button.disabled = !ready || (needsLayers && !motionLabDraftLayers.length);
    }
    motionLabSyncQuickActions();
    const end = qs('#animation-motion-lab-end');
    if (end) end.max = String(count);
    const start = qs('#animation-motion-lab-start');
    if (start) start.max = String(Math.max(0, count - 1));
    const undo = qs('#animation-motion-lab-undo');
    const redo = qs('#animation-motion-lab-redo');
    if (undo) undo.disabled = !ready || motionLabHistoryIndex <= 0;
    if (redo) redo.disabled = !ready || motionLabHistoryIndex >= motionLabHistory.length - 1;
    const addButton = qs('#animation-motion-lab-add');
    if (addButton) addButton.textContent = motionLabEditingIndex < 0 ? '+ Add Preset Layer' : 'Update Selected Layer';
    const list = qs('#animation-motion-lab-layer-list');
    if (!list) return;
    list.replaceChildren();
    if (!motionLabDraftLayers.length) {
      list.textContent = 'No layers. Add a Wave, Spiral, Figure Eight, or another preset to begin.';
      motionLabCurveRender();
      return;
    }
    motionLabDraftLayers.forEach((layer, index) => {
      const item = document.createElement('div');
      item.className = 'animation-motion-lab-layer';
      const desc = document.createElement('span');
      desc.textContent = layer.type === 'audio'
        ? (index + 1) + '. Audio ' + layer.axis.replaceAll('_',' ') +
          ' · ' + layer.start_frame + '–' + (layer.end_frame - 1) +
          ' · threshold ' + layer.threshold
        : layer.type === 'keyframes'
        ? (index + 1) + '. Custom ' + layer.axis.replaceAll('_', ' ') +
          ' · ' + layer.blend + ' · ' + layer.interpolation +
          ' · ' + layer.keys.length + ' keyframe(s)'
        : layer.type === 'recording'
          ? (index + 1) + '. ' + (layer.name || 'Recorded take') +
            ' · ' + layer.blend + ' · ' + layer.start_frame + '–' + (layer.end_frame - 1) +
            ' · ' + layer.samples.length + ' frame(s) · ' + (layer.source || 'unknown')
          : (index + 1) + '. ' + String(layer.preset).replaceAll('-', ' ') +
            ' · ' + layer.blend + ' · ' + layer.start_frame + '–' + (layer.end_frame - 1) +
            ' · strength ' + layer.strength;
      const edit = document.createElement('button');
      edit.type = 'button';
      edit.className = 'secondary-button compact';
      edit.textContent = 'Edit';
      edit.disabled = !ready;
      edit.addEventListener('click', () => {
        if (layer.type === 'keyframes') {
          motionLabEditingIndex = -1;
          const axisField = qs('#animation-motion-lab-key-axis');
          if (axisField) axisField.value = layer.axis;
          motionLabCurveSyncAxis();
          motionLabNotify('Selected custom keyframes on ' + layer.axis.replaceAll('_', ' ') + '.');
          renderMotionLabDraft();
          return;
        }
        if (layer.type === 'recording') {
          motionLabEditingIndex = -1;
          const start = qs('#animation-motion-lab-record-start');
          if (start) start.value = String(layer.start_frame);
          motionLabVisual?.setFrame(layer.start_frame);
          motionLabNotify(
            (layer.name || 'Recorded take') + ' selected: ' + layer.samples.length +
            ' frame(s), ' + layer.axes.join(', ').replaceAll('_',' ') +
            '. Record a new take to replace or layer additional movement.'
          );
          renderMotionLabDraft();
          return;
        }
        motionLabEditingIndex = index;
        for (const [id, value] of Object.entries({
          preset: layer.preset, strength: layer.strength,
          cycle: layer.cycle_seconds, fade: layer.fade_seconds,
          start: layer.start_frame, end: layer.end_frame,
          blend: layer.blend,
        })) {
          const field = qs('#animation-motion-lab-' + id);
          if (field) field.value = String(value);
        }
        motionLabNotify('Editing layer ' + (index + 1) + '. Adjust controls and select Update Selected Layer.');
        renderMotionLabDraft();
      });
      const toggle = document.createElement('label');
      toggle.className = 'animation-motion-lab-layer-toggle';
      const enabled = document.createElement('input');
      enabled.type = 'checkbox';
      enabled.checked = layer.enabled !== false;
      enabled.disabled = !ready;
      enabled.setAttribute('aria-label', 'Enable layer ' + (index + 1));
      enabled.addEventListener('change', () => {
        motionLabDraftLayers[index].enabled = enabled.checked;
        commitMotionLabDraft();
      });
      toggle.append(enabled, document.createTextNode('On'));
      const up = document.createElement('button');
      up.type = 'button';
      up.className = 'secondary-button compact';
      up.textContent = '↑';
      up.title = 'Move layer earlier';
      up.setAttribute('aria-label', 'Move layer ' + (index + 1) + ' earlier');
      up.disabled = !ready || index === 0;
      up.addEventListener('click', () => {
        [motionLabDraftLayers[index - 1], motionLabDraftLayers[index]] =
          [motionLabDraftLayers[index], motionLabDraftLayers[index - 1]];
        motionLabEditingIndex = -1;
        commitMotionLabDraft();
      });
      const down = document.createElement('button');
      down.type = 'button';
      down.className = 'secondary-button compact';
      down.textContent = '↓';
      down.title = 'Move layer later';
      down.setAttribute('aria-label', 'Move layer ' + (index + 1) + ' later');
      down.disabled = !ready || index === motionLabDraftLayers.length - 1;
      down.addEventListener('click', () => {
        [motionLabDraftLayers[index + 1], motionLabDraftLayers[index]] =
          [motionLabDraftLayers[index], motionLabDraftLayers[index + 1]];
        motionLabEditingIndex = -1;
        commitMotionLabDraft();
      });
      const remove = document.createElement('button');
      remove.type = 'button';
      remove.className = 'secondary-button compact';
      remove.textContent = 'Remove';
      remove.disabled = !ready;
      remove.addEventListener('click', () => {
        motionLabDraftLayers.splice(index, 1);
        motionLabEditingIndex = -1;
        commitMotionLabDraft();
      });
      const actions = document.createElement('div');
      actions.className = 'animation-motion-lab-layer-actions';
      actions.append(toggle, up, down, edit);
      if (layer.type === 'recording') {
        const rename = document.createElement('button');
        rename.type = 'button';
        rename.className = 'secondary-button compact';
        rename.textContent = 'Rename';
        rename.disabled = !ready;
        rename.addEventListener('click', () => {
          if (item.querySelector('.animation-motion-take-rename')) return;
          const form = document.createElement('form');
          form.className = 'animation-motion-take-rename';
          const field = document.createElement('input');
          field.type = 'text';
          field.maxLength = 80;
          field.value = layer.name || 'Recorded take';
          field.setAttribute('aria-label', 'Recording take name');
          const save = document.createElement('button');
          save.type = 'submit';
          save.className = 'primary-button compact';
          save.textContent = 'Save name';
          const cancel = document.createElement('button');
          cancel.type = 'button';
          cancel.className = 'secondary-button compact';
          cancel.textContent = 'Cancel';
          cancel.addEventListener('click', () => form.remove());
          form.addEventListener('submit', event => {
            event.preventDefault();
            const value = field.value.trim();
            if (!value) {
              motionLabNotify('Take name cannot be empty.');
              field.focus();
              return;
            }
            motionLabDraftLayers[index].name = value;
            commitMotionLabDraft();
            motionLabNotify('Renamed recording take to ' + value + '.');
          });
          form.append(field, save, cancel);
          item.appendChild(form);
          field.focus();
          field.select();
        });
        const duplicate = document.createElement('button');
        duplicate.type = 'button';
        duplicate.className = 'secondary-button compact';
        duplicate.textContent = 'Duplicate';
        duplicate.disabled = !ready || motionLabDraftLayers.length >= 24;
        duplicate.addEventListener('click', () => {
          if (motionLabDraftLayers.length >= 24) return;
          const copy = JSON.parse(JSON.stringify(motionLabDraftLayers[index]));
          copy.id = 'take-copy-' + Date.now().toString(36) + '-' +
            Math.random().toString(36).slice(2, 8);
          copy.name = (copy.name || 'Recorded take').slice(0, 73) + ' copy';
          // A duplicate is a separately editable take, not a second motion
          // contribution until the author intentionally enables it.
          copy.enabled = false;
          motionLabDraftLayers.splice(index + 1, 0, copy);
          motionLabEditingIndex = -1;
          commitMotionLabDraft();
          motionLabNotify('Duplicated take as a disabled layer. Enable it when ready.');
          void motionLabPreviewOrApply(false, {curvesOnly:true});
        });
        actions.append(rename, duplicate);
      }
      actions.append(remove);
      item.append(desc, actions);
      list.appendChild(item);
    });
    motionLabCurveRender();
  }
  function motionLabNotify(message) {
    const target = qs('#animation-motion-lab-diagnostics');
    if (target) target.textContent = message;
  }
  function motionLabAddPreset() {
    if (!state.project || animationMode() !== '3d') {
      motionLabNotify('Choose Use 3D Motion above to enable the six-axis composer.');
      return;
    }
    const frames = Number(state.project.animation.max_frames || 120);
    const read = key => qs('#animation-motion-lab-' + key)?.value;
    const rawEnd = Number(read('end'));
    const entry = {
      id: motionLabEditingIndex >= 0
        ? motionLabDraftLayers[motionLabEditingIndex].id
        : 'layer-' + Date.now().toString(36) + '-' + motionLabDraftLayers.length,
      preset: read('preset'), blend: read('blend'),
      enabled: motionLabEditingIndex >= 0
        ? motionLabDraftLayers[motionLabEditingIndex].enabled !== false : true,
      strength: Number(read('strength')),
      cycle_seconds: Number(read('cycle')), fade_seconds: Number(read('fade')),
      start_frame: Number(read('start')),
      end_frame: rawEnd === 0 ? frames : rawEnd,
    };
    if (!Number.isInteger(entry.start_frame) || !Number.isInteger(entry.end_frame) ||
        entry.start_frame < 0 || entry.end_frame > frames ||
        entry.end_frame <= entry.start_frame || !Number.isFinite(entry.strength) ||
        entry.strength < 0 || entry.strength > 1 ||
        !Number.isFinite(entry.cycle_seconds) || entry.cycle_seconds < .2 ||
        !Number.isFinite(entry.fade_seconds) || entry.fade_seconds < 0) {
      motionLabNotify('Check the preset range, strength, cycle and fade settings.');
      return;
    }
    if (motionLabDraftLayers.length >= 24 && motionLabEditingIndex < 0) {
      motionLabNotify('Motion Lab supports up to 24 layers.');
      return;
    }
    if (motionLabEditingIndex >= 0) motionLabDraftLayers[motionLabEditingIndex] = entry;
    else motionLabDraftLayers.push(entry);
    motionLabEditingIndex = -1;
    motionLabNotify('Draft updated. Update Curves for instant feedback, then Apply to Animation to save.');
    commitMotionLabDraft();
  }
  // ML1b: manual camera-velocity keyframes live in the same ordered,
  // undoable layer stack as presets, never in an independent render pipeline.
  const MOTION_LAB_AXES = [
    'translation_x','translation_y','translation_z',
    'rotation_x','rotation_y','rotation_z',
  ];
  function motionLabCurveAxis() {
    const value = qs('#animation-motion-lab-key-axis')?.value;
    return MOTION_LAB_AXES.includes(value) ? value : 'translation_x';
  }
  function motionLabCurveLayerIndex(axis = motionLabCurveAxis()) {
    return motionLabDraftLayers.findIndex(layer =>
      layer.type === 'keyframes' && layer.axis === axis);
  }
  function motionLabCurveLayer(axis = motionLabCurveAxis()) {
    const index = motionLabCurveLayerIndex(axis);
    return index < 0 ? null : motionLabDraftLayers[index];
  }
  function motionLabCurveSyncAxis() {
    const layer = motionLabCurveLayer();
    if (layer) {
      const interp = qs('#animation-motion-lab-key-interpolation');
      const blend = qs('#animation-motion-lab-key-blend');
      if (interp) interp.value = layer.interpolation;
      if (blend) blend.value = layer.blend;
    }
    motionLabCurveRender();
  }
  function motionLabCurveFrameSync(frame) {
    const input = qs('#animation-motion-lab-key-frame');
    if (input && document.activeElement !== input) input.value = String(frame);
    // The record start frame is an explicit field, not a side effect of
    // curve playback/scrubbing. Otherwise hitting Record after a preview
    // starts at the final frame and ends before controls can be used.
    const value = qs('#animation-motion-lab-key-value');
    if (value && document.activeElement !== value) {
      const existing = motionLabCurveLayer()?.keys?.find(key => key.frame === frame);
      if (existing) value.value = String(existing.value);
    }
  }
  function motionLabCurveRender() {
    const axis = motionLabCurveAxis();
    const layer = motionLabCurveLayer(axis);
    const list = qs('#animation-motion-lab-key-list');
    if (list) {
      list.replaceChildren();
      if (!layer) {
        list.textContent = 'No custom keyframes on this axis. Add one or drag on the curve graph.';
      } else {
        for (const key of layer.keys) {
          const button = document.createElement('button');
          button.type = 'button';
          button.className = 'secondary-button compact';
          button.textContent = 'Frame ' + key.frame + ': ' + Number(key.value).toFixed(4);
          button.disabled = motionLabBusy;
          button.addEventListener('click', () => {
            const frame = qs('#animation-motion-lab-key-frame');
            const value = qs('#animation-motion-lab-key-value');
            if (frame) frame.value = String(key.frame);
            if (value) value.value = String(key.value);
            motionLabVisual?.setFrame(key.frame);
          });
          list.appendChild(button);
        }
      }
    }
    const count = Number(state.project?.animation?.max_frames || 120);
    const frame = qs('#animation-motion-lab-key-frame');
    if (frame) frame.max = String(count - 1);
    const eligible = Boolean(state.project && animationMode() === '3d' && !motionLabBusy);
    for (const id of ['animation-motion-lab-key-save','animation-motion-lab-key-delete',
      'animation-motion-lab-key-clear']) {
      const control = qs('#' + id);
      if (control) control.disabled = !eligible || (id !== 'animation-motion-lab-key-save' && !layer);
    }
    motionLabVisual?.configureEditor({
      axis,
      keys: layer?.keys || [],
      enabled: Boolean(qs('#animation-motion-lab-key-drag')?.checked) && eligible,
      pathEnabled: Boolean(qs('#animation-motion-lab-path-drag')?.checked) && eligible,
      onEdit: motionLabCurvePointerEdit,
      onPathEdit: motionLabCurvePathEdit,
      onFrameChange: motionLabCurveFrameSync,
      onPointerDraft: ({frame, value}) => {
        const f = qs('#animation-motion-lab-key-frame');
        const v = qs('#animation-motion-lab-key-value');
        if (f) f.value = String(frame);
        if (v) v.value = String(value);
      },
    });
  }
  function motionLabCurveModify({
    frame, value, replaceFrame = null,
    axis = motionLabCurveAxis(), deferCommit = false,
  }) {
    const count = Number(state.project?.animation?.max_frames || 120);
    if (!state.project || animationMode() !== '3d' || motionLabBusy ||
        !Number.isInteger(frame) || frame < 0 || frame >= count ||
        !Number.isFinite(value) || Math.abs(value) > 30 ||
        (frame === 0 && value !== 0)) {
      motionLabNotify('Invalid curve point: frame must be in range, movement finite within ±30, and frame 0 must stay at zero.');
      return false;
    }
    const index = motionLabCurveLayerIndex(axis);
    let target = index >= 0 ? structuredClone(motionLabDraftLayers[index]) : {
      id: 'manual-' + axis,
      type: 'keyframes',
      axis, enabled: true,
      blend: axis === motionLabCurveAxis()
        ? (qs('#animation-motion-lab-key-blend')?.value || 'add') : 'add',
      interpolation: axis === motionLabCurveAxis()
        ? (qs('#animation-motion-lab-key-interpolation')?.value || 'linear') : 'linear',
      start_frame: 0, end_frame: count,
      keys: [{frame: 0, value: 0}],
    };
    if (index < 0 && motionLabDraftLayers.length >= 24) {
      motionLabNotify('Motion Lab supports at most 24 layers.');
      return false;
    }
    if (axis === motionLabCurveAxis()) {
      target.blend = qs('#animation-motion-lab-key-blend')?.value || target.blend;
      target.interpolation = qs('#animation-motion-lab-key-interpolation')?.value || target.interpolation;
    }
    if (replaceFrame !== null && replaceFrame !== 0 && replaceFrame !== frame) {
      target.keys = target.keys.filter(key => key.frame !== replaceFrame);
    }
    const existing = target.keys.find(key => key.frame === frame);
    if (existing) existing.value = value;
    else target.keys.push({frame, value});
    target.keys.sort((a,b) => a.frame - b.frame);
    if (target.keys.length > 128) {
      motionLabNotify('Curve layers support at most 128 keyframes.');
      return false;
    }
    if (index < 0) motionLabDraftLayers.push(target);
    else motionLabDraftLayers[index] = target;
    motionLabEditingIndex = -1;
    if (!deferCommit) {
      commitMotionLabDraft();
      motionLabNotify('Manual ' + axis.replaceAll('_',' ') +
        ' curve changed. Update Curves to inspect the new camera movement.');
    }
    return true;
  }
  function motionLabCurvePathEdit({frame, deltaX, deltaY}) {
    if (!Number.isInteger(frame) || frame <= 0 ||
        !Number.isFinite(deltaX) || !Number.isFinite(deltaY) || motionLabBusy) return;
    const axes = [['translation_x', deltaX], ['translation_y', deltaY]];
    const needed = axes.filter(([axis]) => motionLabCurveLayerIndex(axis) < 0).length;
    if (motionLabDraftLayers.length + needed > 24) {
      motionLabNotify('Not enough free Motion Lab layers to adjust both X and Y path values.');
      return;
    }
    const snapshot = structuredClone(motionLabDraftLayers);
    for (const [axis, delta] of axes) {
      if (Math.abs(delta) < 1e-8) continue;
      const current = motionLabCurveLayer(axis)?.keys?.find(k => k.frame === frame)?.value || 0;
      const value = Number((current + delta).toFixed(6));
      if (!motionLabCurveModify({axis, frame, value, deferCommit:true})) {
        motionLabDraftLayers = snapshot;
        return;
      }
    }
    commitMotionLabDraft();
    motionLabNotify('Camera path frame ' + frame +
      ': X/Y velocity keyframes updated. Path is a projected, auto-fit visualization.');
    void motionLabPreviewOrApply(false, {curvesOnly:true});
  }
  function motionLabCurvePointerEdit(point) {
    if (motionLabCurveModify(point)) {
      // Compose the new visual sample series on the existing CPU-free path.
      void motionLabPreviewOrApply(false, {curvesOnly:true});
    }
  }
  function motionLabCurveSave() {
    const frame = Number(qs('#animation-motion-lab-key-frame')?.value);
    const value = Number(qs('#animation-motion-lab-key-value')?.value);
    if (motionLabCurveModify({frame, value})) {
      void motionLabPreviewOrApply(false, {curvesOnly:true});
    }
  }
  function motionLabCurveDelete() {
    const axis = motionLabCurveAxis();
    const index = motionLabCurveLayerIndex(axis);
    if (index < 0) return;
    const frame = Number(qs('#animation-motion-lab-key-frame')?.value);
    if (!Number.isInteger(frame) || frame === 0) {
      motionLabNotify('Frame 0 is the fixed motion anchor; select another keyframe to delete.');
      return;
    }
    const layer = structuredClone(motionLabDraftLayers[index]);
    const original = layer.keys.length;
    layer.keys = layer.keys.filter(key => key.frame !== frame);
    if (layer.keys.length === original) {
      motionLabNotify('No keyframe at frame ' + frame + '.');
      return;
    }
    if (!layer.keys.length) motionLabDraftLayers.splice(index, 1);
    else motionLabDraftLayers[index] = layer;
    commitMotionLabDraft();
    void motionLabPreviewOrApply(false, {curvesOnly:true});
  }
  function motionLabCurveClear() {
    const index = motionLabCurveLayerIndex();
    if (index < 0) return;
    motionLabDraftLayers.splice(index, 1);
    commitMotionLabDraft();
    motionLabNotify('Custom curve removed from draft; saved animation is unchanged.');
    if (motionLabDraftLayers.length) void motionLabPreviewOrApply(false, {curvesOnly:true});
    else motionLabVisual?.clear();
  }

  async function motionLabPreviewOrApply(apply, { curvesOnly = false } = {}) {
    if (!state.project?.id || !motionLabDraftLayers.length || motionLabBusy) return;
    const projectId = state.project.id;
    motionLabBusy = true;
    renderMotionLabDraft();
    try {
      if (apply && state.dirty) {
        const approved = await window.MorphorumDialog.confirm({
          title: 'Save Editor changes before applying Motion Lab?',
          message: 'Your Editor has unsaved settings. Motion Lab will save them first, then apply these camera layers. Nothing will be discarded.',
          variant: 'default', confirmText: 'Save & Apply', cancelText: 'Cancel',
        });
        if (!approved || state.project?.id !== projectId) return;
        const saved = await api('/api/animation/projects/' + encodeURIComponent(projectId), {
          method: 'PUT', body: JSON.stringify(collectProject()),
        });
        state.project = saved.project;
        state.path = saved.path || state.path;
        fillForm();
        await loadTimeline();
        // Confirming the save doesn't confirm overwriting hand-edited tracks.
        // A separate explicit rebase confirmation is still required if needed.
      }
      const endpoint = '/api/animation/projects/' +
        encodeURIComponent(projectId) + '/motion-lab/' + (apply ? 'apply' : 'preview');
      const payload = { layers: motionLabDraftLayers };
      if (!apply) payload.project = collectProject(); // include unsaved edits non-destructively
      let result;
      try {
        result = await api(endpoint, {
          method: 'POST', body: JSON.stringify(payload),
        });
      } catch (error) {
        if (!apply || !String(error.message || '').includes('Camera schedules changed since Motion Lab')) {
          throw error;
        }
        const approved = await window.MorphorumDialog.confirm({
          title: 'Use your edited camera schedules as the new Motion Lab base?',
          message: 'The Editor timeline has changed since Motion Lab last applied its layers. Keep those current camera values and layer this draft on top? This will replace the previous Motion Lab contribution as the baseline, but will not delete the edited schedules.',
          variant: 'default', confirmText: 'Use Current Camera & Apply',
          cancelText: 'Keep Existing Motion',
        });
        if (!approved || state.project?.id !== projectId) {
          motionLabNotify('Apply canceled. Your camera timeline remains unchanged.');
          return;
        }
        payload.rebase_current = true;
        result = await api(endpoint, {
          method: 'POST', body: JSON.stringify(payload),
        });
      }
      if (state.project?.id !== projectId) return;
      if (!apply && result.diagnostics?.series) {
        motionLabVisual?.setData(result.diagnostics);
      }
      const limited = Object.entries(result.diagnostics?.limited || {});
      const rebaseNote = result.diagnostics?.rebased
        ? (apply ? ' Camera edits accepted as the new base.' :
          ' Camera edits detected: draft uses current camera; Apply will ask before saving.') : '';
      motionLabNotify((apply ? 'Applied ' : 'Previewing ') +
        result.diagnostics.layer_count + ' motion layer(s) across ' +
        result.diagnostics.frames + ' frames.' +
        (limited.length ? ' Limited axes: ' + limited.map(([axis,n])=>axis+' ('+n+')').join(', ') : ' No clipping.') +
        rebaseNote);
      if (apply) {
        state.project = result.project;
        motionLabDraftLayers = result.project.motion_lab.layers.map(l => ({ ...l }));
        clearMotionPreviewResult();
        fillForm();
        await loadTimeline();
        await loadProjectList();
        toast('Motion Lab applied', 'Native 3D camera schedules updated without leaving Motion Lab.', 'success');
      } else if (!curvesOnly) {
        await generateMotionPreview(result.project);
      }
    } catch (error) {
      motionLabNotify('Motion Lab: ' + error.message);
      toast('Motion Lab ' + (apply ? 'apply' : 'preview') + ' failed',
        error.message, 'error', 7000);
    } finally {
      motionLabBusy = false;
      renderMotionLabDraft();
    }
  }

  // Motion Lab is first-class; unfinished hybrid Media controls remain mounted
  // in a non-navigable vault so existing project and API semantics stay intact.
  // Four visible views share the existing render controls and poller.
  const ANIMATION_TAB_KEY = 'morphorum.animation.workspaceTab.v1';
  const VISIBLE_ANIMATION_TABS = ['editor', 'motion', 'monitor', 'outputs'];
  let animationTab = 'editor';
  function showAnimationTab(name, { persist = true } = {}) {
    if (!VISIBLE_ANIMATION_TABS.includes(name)) name = 'editor';
    if (name !== 'motion') {
      motionLabVisual?.pause();
      if (motionLabRecorder?.active) motionLabStopRecording('tab-change');
    }
    animationTab = name;
    qsa('#animation-workspace-nav [data-animation-tab]').forEach(button => {
      const selected = button.dataset.animationTab === name;
      button.classList.toggle('active', selected);
      button.setAttribute('aria-selected', String(selected));
      button.tabIndex = selected ? 0 : -1;
    });
    qsa('#view-animation .animation-workspace-panel').forEach(panel => {
      const selected = panel.dataset.animationPanel === name;
      panel.hidden = !selected;
      panel.classList.toggle('active', selected);
    });
    if (persist) try { localStorage.setItem(ANIMATION_TAB_KEY, name); } catch (_) {}
  }
  function setupAnimationWorkspaceTabs() {
    const layout = qs('#view-animation .animation-layout');
    const root = qs('#view-animation');
    const card = qs('#view-animation .animation-render-card');
    if (!layout || !root || !card) return;
    const nav = document.createElement('nav');
    nav.id = 'animation-workspace-nav';
    nav.className = 'animation-workspace-nav';
    nav.setAttribute('aria-label', 'Animation workspace');
    nav.setAttribute('role', 'tablist');
    const panels = {};
    const names = { editor: 'Editor', motion: 'Motion Lab', monitor: 'Monitor', outputs: 'Outputs' };
    for (const [name, label] of Object.entries(names)) {
      const button = document.createElement('button');
      button.type = 'button';
      button.dataset.animationTab = name;
      button.id = 'animation-tab-' + name;
      button.setAttribute('role', 'tab');
      button.setAttribute('aria-controls', 'animation-panel-' + name);
      button.textContent = label;
      button.addEventListener('click', () => showAnimationTab(name));
      button.addEventListener('keydown', event => {
        if (!['ArrowLeft','ArrowRight','Home','End'].includes(event.key)) return;
        event.preventDefault();
        const keys = Object.keys(names);
        const next = event.key === 'Home' ? 0 : event.key === 'End' ? keys.length - 1 :
          (keys.indexOf(name) + (event.key === 'ArrowRight' ? 1 : keys.length - 1)) % keys.length;
        qs('#animation-tab-' + keys[next])?.focus();
        showAnimationTab(keys[next]);
      });
      nav.appendChild(button);
      const panel = document.createElement('section');
      panel.className = 'animation-workspace-panel';
      panel.id = 'animation-panel-' + name;
      panel.dataset.animationPanel = name;
      panel.setAttribute('role', 'tabpanel');
      panel.setAttribute('aria-labelledby', button.id);
      panel.hidden = name !== 'editor';
      panels[name] = panel;
    }
    layout.parentNode.insertBefore(nav, layout);
    layout.parentNode.insertBefore(panels.editor, layout);
    panels.editor.appendChild(layout);
    let last = panels.editor;
    for (const name of ['motion', 'monitor', 'outputs']) {
      last.after(panels[name]);
      last = panels[name];
    }
    // Keep the unfinished hybrid-media DOM for backward-compatible project
    // state and extraction APIs, but make it inaccessible to visible tabs.
    const mediaVault = document.createElement('section');
    mediaVault.id = 'animation-media-vault';
    mediaVault.hidden = true;
    mediaVault.inert = true;
    mediaVault.setAttribute('aria-hidden', 'true');
    panels.outputs.after(mediaVault);

    // The old accordion was initialized while Render was a direct child.
    setAnimationCardCollapsed(card, false);
    panels.monitor.appendChild(card);
    const inner = qs('.animation-card-content', card) || card;
    const hybrid = qs('#animation-hybrid-source');
    const video = qs('#animation-video-export');
    if (hybrid) mediaVault.appendChild(hybrid);
    if (video) {
      const wrapper = document.createElement('article');
      wrapper.className = 'card glass animation-output-card';
      wrapper.appendChild(video);
      panels.outputs.appendChild(wrapper);
    }
    const motionIntro = qs('#animation-motion-lab-intro');
    if (motionIntro) panels.motion.appendChild(motionIntro);
    const composer = qs('#animation-motion-lab-composer');
    if (composer) panels.motion.appendChild(composer);
    const recording = qs('#animation-motion-lab-recording');
    if (recording) panels.motion.appendChild(recording);
    const audio = qs('#animation-motion-lab-audio');
    if (audio) panels.motion.appendChild(audio);
    const visual = qs('#animation-motion-lab-visual');
    if (visual) panels.motion.appendChild(visual);
    const motionPreview = qs('.animation-motion-preview-card');
    if (motionPreview) panels.motion.appendChild(motionPreview);
    motionLabSetupQuickActions(panels.motion);
    const history = qs('.animation-render-history-row');
    if (history) panels.outputs.prepend(history);
    const completedPreview = qs('.animation-render-preview-wrap');
    if (completedPreview) panels.outputs.appendChild(completedPreview);
    const prompt = qs('#animation-render-prompt-telemetry');
    const motion = qs('#animation-render-frame-telemetry');
    const perf = qs('#animation-performance-summary');
    const expert = document.createElement('details');
    expert.className = 'animation-monitor-diagnostics';
    const expertTitle = document.createElement('summary');
    expertTitle.textContent = 'Render details: prompts, motion and performance';
    expert.appendChild(expertTitle);
    for (const item of [prompt,motion,perf]) if (item) expert.appendChild(item);
    inner.appendChild(expert);
    qs('#animation-collapse-all')?.setAttribute('title', 'Collapse Editor cards');
    qs('#animation-expand-all')?.setAttribute('title', 'Expand Editor cards');
    qs('#animation-motion-lab-edit-3d')?.addEventListener('click', () => {
      showAnimationTab('editor');
      qs('#animation-3d-camera-card')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
    qs('#animation-motion-lab-edit-timeline')?.addEventListener('click', () => {
      showAnimationTab('editor');
      qs('#animation-timeline-card')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
    let previous = 'editor';
    try { previous = localStorage.getItem(ANIMATION_TAB_KEY) || 'editor'; } catch (_) {}
    showAnimationTab(previous, { persist: false });
  }

  function bind() {
    bindHybrid();
    qs('#animation-collapse-all')?.addEventListener('click', () => setAllAnimationCards(true));
    qs('#animation-expand-all')?.addEventListener('click', () => setAllAnimationCards(false));
    qs('#animation-import-deforum')?.addEventListener('click', () => {
      const input = qs('#animation-deforum-file');
      if (input) {
        input.value = '';
        input.click();
      }
    });
    qs('#animation-deforum-file')?.addEventListener('change', chooseDeforumFile);
    qs('#animation-deforum-close')?.addEventListener('click', closeDeforumImport);
    qs('#animation-deforum-cancel')?.addEventListener('click', closeDeforumImport);
    qs('#animation-deforum-refresh')?.addEventListener('click', () => previewDeforumImport());
    qs('#animation-deforum-create')?.addEventListener('click', createDeforumProject);
    qs('#animation-deforum-model')?.addEventListener('change', () => previewDeforumImport());
    qs('#animation-new')?.addEventListener('click', createProject);
    qs('#animation-save')?.addEventListener('click', saveProject);
    qs('#animation-reload')?.addEventListener('click', reloadProject);
    qs('#animation-add-prompt')?.addEventListener('click', addPromptKeyframe);
    qs('#animation-validate-schedules')?.addEventListener('click', () => validateSchedules(true));
    qs('#animation-timeline-refresh')?.addEventListener('click', async () => {
      try {
        await persistDirtyBeforeTimelineEdit();
        await loadTimeline();
      } catch (error) {
        toast('Could not refresh timeline', error.message, 'error', 6500);
      }
    });
    qs('#animation-timeline-track-select')?.addEventListener('change', event => {
      const [group, name] = String(event.target.value || '').split('/');
      if (!group || !name) return;
      state.timelineSelection = { group, name, frame: null };
      renderTimeline();
    });
    qs('#animation-timeline-frame')?.addEventListener('input', event => {
      setInspectorFrame(event.target.value);
    });
    qs('#animation-timeline-scrubber')?.addEventListener('input', event => {
      setInspectorFrame(event.target.value);
    });
    qs('#animation-timeline-prev-keyframe')?.addEventListener('click', () => navigateTimelineKeyframe(-1));
    qs('#animation-timeline-next-keyframe')?.addEventListener('click', () => navigateTimelineKeyframe(1));
    qs('#animation-timeline-scale')?.addEventListener('input', event => {
      state.timelineScale = Math.max(2, Math.min(14, Number(event.target.value) || 6));
      renderTimeline();
    });
    qs('#animation-timeline-add')?.addEventListener('click', addTimelineKeyframeAtPlayhead);
    qs('#animation-timeline-apply')?.addEventListener('click', applyTimelineEditor);
    qs('#animation-timeline-delete')?.addEventListener('click', deleteTimelineKeyframe);

    qs('#animation-source-file')?.addEventListener('change', event => {
      const file = event.target.files?.[0];
      if (file) uploadSourceImage(file);
    });
    qs('#animation-clear-source')?.addEventListener('click', clearSourceImage);
    qs('#animation-generate-depth')?.addEventListener('click', () => generateDepthPreview(false));
    qs('#animation-recompute-depth')?.addEventListener('click', () => generateDepthPreview(true));
    qs('#animation-clear-depth')?.addEventListener('click', clearDepthPreview);
    qs('#animation-3d-apply-preset')?.addEventListener('click', applyCamera3DPreset);
    qs('#animation-cadence-preset')?.addEventListener('change', applyCadencePreset);
    qs('#animation-cadence')?.addEventListener('input', syncCadencePreset);
    qs('#animation-cadence')?.addEventListener('change', syncCadencePreset);
    qs('#animation-generate-motion-preview')?.addEventListener('click', generateMotionPreview);
    qs('#animation-motion-gif-replay')?.addEventListener('click', () => void replayMotionGifWithAudio());
    qs('#animation-motion-lab-enable-3d')?.addEventListener('click', () => {
      if (!state.project) return;
      const selector = qs('#animation-mode');
      if (selector) selector.value = '3d';
      markDirty({ validate: true });
      syncAnimationModeUi();
      renderMotionLabDraft();
      motionLabNotify('3D Motion enabled. Preview a draft now, or Apply to save the 3D setting and camera tracks.');
    });
    qs('#animation-motion-lab-add')?.addEventListener('click', motionLabAddPreset);
    qs('#animation-motion-lab-record')?.addEventListener('click', motionLabStartRecording);
    qs('#animation-motion-lab-analyze-audio')?.addEventListener('click', () => void motionLabAnalyzeAudio());
    qs('#animation-motion-lab-add-audio')?.addEventListener('click', motionLabAddAudio);
    qs('#animation-motion-lab-audio-sync')?.addEventListener('change', event => {
      if (!event.target.checked) motionLabAudioElement?.pause();
      motionLabAudioSyncStatus(event.target.checked
        ? 'Audio will follow Motion Curves playback and seeking.'
        : 'Synchronized audio playback disabled.');
    });
    for (const id of ['threshold','attack','release','distance']) {
      qs('#animation-motion-lab-audio-' + id)?.addEventListener('input', motionLabAudioPreview);
    }
    qs('#animation-motion-lab-record-mode')?.addEventListener('change', motionLabRecordingUi);
    qs('#animation-motion-lab-stop-recording')?.addEventListener('click',
      () => motionLabStopRecording('manual'));
    qs('#animation-motion-lab-record-gamepad')?.addEventListener('change', event => {
      if (!event.target.checked) {
        motionLabRecordStatus('Gamepad input off. Keyboard and touch are always available.', true);
      } else if (typeof navigator.getGamepads !== 'function') {
        motionLabRecordStatus('Gamepad API unavailable in this browser/security context. Keyboard and touch still work.', true);
      } else {
        motionLabRecordStatus('Gamepad enabled. Move a controller control while recording to verify client-browser visibility.', true);
      }
    });
    motionLabBindStick('animation-motion-lab-stick-translate', 'translate');
    motionLabBindStick('animation-motion-lab-stick-rotate', 'rotate');
    motionLabBindHoldControls();
    qs('#animation-motion-lab-clear')?.addEventListener('click', () => {
      motionLabDraftLayers = [];
      motionLabEditingIndex = -1;
      motionLabNotify('Draft cleared. The currently saved camera timeline is unchanged.');
      commitMotionLabDraft();
    });
    qs('#animation-motion-lab-undo')?.addEventListener('click', () => restoreMotionLabDraft(-1));
    qs('#animation-motion-lab-redo')?.addEventListener('click', () => restoreMotionLabDraft(1));
    qs('#animation-motion-lab-update-curves')?.addEventListener('click',
      () => motionLabPreviewOrApply(false, { curvesOnly: true }));
    qs('#animation-motion-lab-key-axis')?.addEventListener('change', motionLabCurveSyncAxis);
    qs('#animation-motion-lab-key-drag')?.addEventListener('change', motionLabCurveRender);
    qs('#animation-motion-lab-path-drag')?.addEventListener('change', motionLabCurveRender);
    for (const id of ['animation-motion-lab-key-blend','animation-motion-lab-key-interpolation']) {
      qs('#' + id)?.addEventListener('change', () => {
        const index = motionLabCurveLayerIndex();
        if (index < 0) return;
        const key = id.endsWith('blend') ? 'blend' : 'interpolation';
        const value = qs('#' + id)?.value;
        if (motionLabDraftLayers[index][key] === value) return;
        motionLabDraftLayers[index] = {...motionLabDraftLayers[index], [key]:value};
        commitMotionLabDraft();
        void motionLabPreviewOrApply(false, {curvesOnly:true});
      });
    }
    qs('#animation-motion-lab-key-save')?.addEventListener('click', motionLabCurveSave);
    qs('#animation-motion-lab-key-delete')?.addEventListener('click', motionLabCurveDelete);
    qs('#animation-motion-lab-key-clear')?.addEventListener('click', motionLabCurveClear);
    qs('#animation-motion-lab-preview-draft')?.addEventListener('click',
      () => motionLabPreviewOrApply(false));
    qs('#animation-motion-lab-apply')?.addEventListener('click',
      () => motionLabPreviewOrApply(true));
    qs('#animation-export-video')?.addEventListener('click', startVideoExport);

    qs('#animation-start-render')?.addEventListener('click', startAnimationRender);
    qs('#animation-cancel-render')?.addEventListener('click', cancelAnimationRender);
    qs('#animation-resume-render')?.addEventListener('click', resumeAnimationRender);
    qs('#animation-render-select')?.addEventListener('change', event => {
      showRender(event.target.value);
    });

    window.addEventListener('keydown', event => {
      if (!motionLabRecorder?.active || !MOTION_RECORD_KEYMAP[event.code]) return;
      if (event.repeat) return;
      event.preventDefault();
      motionLabRecordKeys.add(event.code);
    });
    window.addEventListener('keyup', event => {
      if (!MOTION_RECORD_KEYMAP[event.code]) return;
      if (motionLabRecorder?.active) event.preventDefault();
      motionLabRecordKeys.delete(event.code);
    });
    window.addEventListener('blur', () => {
      if (!motionLabRecorder?.active) {
        motionLabNeutralizeRecordInput();
        return;
      }
      motionLabStopRecording('blur');
    });
    document.addEventListener('visibilitychange', () => {
      if (document.hidden && motionLabRecorder?.active) motionLabStopRecording('hidden');
      else if (document.hidden) motionLabNeutralizeRecordInput();
    });
    window.addEventListener('gamepadconnected', event => {
      if (qs('#animation-motion-lab-record-gamepad')?.checked) {
        motionLabRecordStatus('Gamepad connected to this browser: ' + (event.gamepad?.id || 'controller') + '.', true);
      }
    });
    window.addEventListener('gamepaddisconnected', () => {
      motionLabRecordStatus('Gamepad disconnected. Keyboard and touch remain available.', true);
    });

    qs('#animation-project-select')?.addEventListener('change', event => {
      loadProject(event.target.value);
    });

    qs('#animation-mode')?.addEventListener('change', () => {
      clearMotionPreviewResult();
      markDirty({ validate: true });
      syncAnimationModeUi();
      refreshInspector();
    });

    qs('#animation-model')?.addEventListener('change', () => {
      populateSamplerSelect('');
      populateResolutionPresets();
      const repairedGuidance = repairConstantGuidanceForSelectedModel({ announce: true });
      renderPromptRows();
      markDirty({ validate: repairedGuidance });
      renderSourceState();
    });

    qs('#animation-resolution-preset')?.addEventListener('change',event => {
      if(!window.MorphorumResolution.apply(event.target,qs('#animation-width'),qs('#animation-height')))return;
      updateAnimationResolutionHelp();
      markDirty({validate:true});
    });
    for(const id of ['animation-width','animation-height'])
      qs('#'+id)?.addEventListener('input',syncAnimationResolutionPreset);

    qs('#animation-start-mode')?.addEventListener('change', () => {
      markDirty();
      renderSourceState();
    });

    qs('#animation-inspector-frame')?.addEventListener('input', event => {
      setInspectorFrame(event.target.value);
    });
    qs('#animation-inspector-slider')?.addEventListener('input', event => {
      setInspectorFrame(event.target.value);
    });
    qs('#animation-curve-field')?.addEventListener('change', refreshInspector);

    qsa(
      '#view-animation input, #view-animation select, #view-animation textarea'
    ).forEach(input => {
      if (
        input.id === 'animation-project-select' ||
        input.id.startsWith('animation-deforum-') ||
        input.id.startsWith('animation-hybrid-') ||
        input.id.startsWith('animation-motion-lab-') ||
        input.id.startsWith('animation-video-') ||
        input.id === 'animation-model' ||
        input.id === 'animation-resolution-preset' ||
        input.id === 'animation-source-file' ||
        input.id === 'animation-start-mode' ||
        input.id === 'animation-cadence-preset' ||
        input.id === 'animation-render-select' ||
        INSPECTOR_INPUT_IDS.has(input.id)
      ) {
        return;
      }
      const scheduleField = Object.entries(SCHEDULE_INPUTS).find(
        ([, selector]) => qs(selector) === input
      );
      input.addEventListener('input', () => markDirty({ validate: Boolean(scheduleField) }));
      input.addEventListener('change', () => markDirty({ validate: Boolean(scheduleField) }));
    });

    qs('#animation-max-frames')?.addEventListener('input', () => {
      const max = inspectorFrameMax();
      qsa('.animation-prompt-frame').forEach(input => {
        input.max = String(max);
      });
      syncInspectorBounds();
      syncTimelinePlayhead(qs('#animation-inspector-frame')?.value || 0);
    });
  }

  async function start() {
    setupAnimationAccordions();
    setupAnimationWorkspaceTabs();
    if (window.MorphorumMotionLabVisualizer) {
      motionLabVisual = new window.MorphorumMotionLabVisualizer();
      motionLabBindAudioTransport();
    }
    bind();
    setEditorEnabled(false);

    window.addEventListener('resize', () => {
      window.clearTimeout(state.timelineResizeTimer);
      state.timelineResizeTimer = window.setTimeout(() => renderTimeline(), 140);
    });
    try {
      await Promise.all([
        loadCapabilities(),
        loadModels(),
        loadDepthModels(),
        api('/api/animation/video/availability').then(info => {
          state.videoAvailability = info;
          renderVideoExportState();
        }).catch(() => {
          state.videoAvailability = { available: false, message: 'Cannot check host FFmpeg installation.' };
          renderVideoExportState();
        }),
      ]);
      await loadProjectList({ loadFirst: true });
      populateSamplerSelect(state.project?.generation?.sampler || '');
    } catch (error) {
      toast('Animation workspace initialization failed', error.message, 'error', 7000);
    }
  }

  window.addEventListener('DOMContentLoaded', start);
})();
