(() => {
  'use strict';

  let motionPreviewStarting = false;
  let animationRenderStarting = false;
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
  const LAST_ANIMATION_PROJECT_KEY = 'morphorum.animation.lastProjectId.v1';

  function readLastAnimationProject() {
    try { return localStorage.getItem(LAST_ANIMATION_PROJECT_KEY) || ''; }
    catch (_) { return ''; }
  }

  function rememberAnimationProject(projectId) {
    if (!projectId) return;
    try { localStorage.setItem(LAST_ANIMATION_PROJECT_KEY, String(projectId)); }
    catch (_) { /* Storage may be unavailable in a restricted browser. */ }
  }

  function forgetAnimationProject(projectId) {
    if (!projectId) return;
    try {
      if (localStorage.getItem(LAST_ANIMATION_PROJECT_KEY) === projectId) {
        localStorage.removeItem(LAST_ANIMATION_PROJECT_KEY);
      }
    } catch (_) { /* Browser storage is optional. */ }
  }

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
      // Standalone Motion Lab tool pages must always open with their
      // controls visible. The Editor alone retains its accordion workflow.
      if (['animation-motion-lab-composer', 'animation-motion-lab-recording',
           'animation-motion-lab-visual', 'animation-motion-lab-audio'].includes(card.id) ||
          card.classList.contains('animation-motion-preview-card')) return;
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

  // P1: explain why the editor is locked without changing saved settings.
  function renderEditorGuidance() {
    const project = state.project;
    const panel = qs('#animation-editor-guidance');
    const open = qs('#animation-editor-open-project');
    const context = qs('#animation-project-context');
    if (panel) panel.hidden = Boolean(project);
    if (open) open.hidden = state.projects.length === 0;
    if (context) {
      if (!project) {
        context.textContent = state.projects.length
          ? 'No project open · choose an existing project or create a new one.'
          : 'No project open · create a project to begin editing.';
      } else {
        const selectedModelId = qs('#animation-model')?.value || project.model?.model_id || '';
        const model = state.models.find(item => item.id === selectedModelId && item.kind === 'checkpoints');
        const modelLabel = model?.name || (selectedModelId ? 'Model unavailable' : 'Model not selected');
        context.textContent = (qs('#animation-name')?.value?.trim() || project.name || 'Untitled Animation') +
          ' · ' + modelLabel + ' · ' + (state.dirty ? 'Unsaved changes' : 'Saved');
      }
    }
    const modelHelp = qs('#animation-model-guidance');
    const modelSelect = qs('#animation-model');
    if (modelHelp) {
      const selectedModelId = modelSelect?.value || project?.model?.model_id || '';
      if (!project) {
        modelHelp.hidden = true;
      } else if (!selectedModelId) {
        modelHelp.hidden = false;
        modelHelp.textContent = state.models.some(item => item.kind === 'checkpoints')
          ? 'Choose a checkpoint for this animation project. The still-image model selection is separate.'
          : 'No checkpoints indexed. Open Models, configure or download a checkpoint, then scan models.';
      } else if (!state.models.some(item => item.id === selectedModelId && item.kind === 'checkpoints')) {
        modelHelp.hidden = false;
        modelHelp.textContent = 'This project references a model not currently indexed on this computer. Scan Models or choose another compatible checkpoint.';
      } else {
        modelHelp.hidden = true;
      }
    }
    if (modelSelect) {
      modelSelect.title = project
        ? 'Choose a checkpoint for the current animation project.'
        : 'Open or create an animation project before selecting a model.';
    }
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
    renderEditorGuidance();
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
    renderEditorGuidance();
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
    // Reload limits even when the user refreshes the same project ID.
    motionLabSyncRecordingLimits();
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

  // The project is the source of truth, not a browser file input. Every project
  // open starts with a verified inventory and rehydrates its media players.
  let projectMediaGeneration = 0;
  let projectAudioRestoreGeneration = 0;
  let motionLabSoundtrackBusy = false;
  let motionLabSoundtrackStatus = '';
  let projectMedia = {
    projectId: '', loading: false, assets: [], warnings: [],
    soundtrack: null, selectedWav: '',
  };

  function projectMediaAssets(kind) {
    return projectMedia.projectId === state.project?.id
      ? projectMedia.assets.filter(asset => asset.kind === kind) : [];
  }

  function projectMediaWarning(message) {
    if (projectMedia.projectId !== state.project?.id) return;
    if (!projectMedia.warnings.includes(message)) projectMedia.warnings.push(message);
  }

  function renderProjectMedia() {
    const project = state.project;
    const status = qs('#animation-media-status');
    const warningNode = qs('#animation-media-warnings');
    const soundtrackRow = qs('#animation-media-soundtrack');
    const soundtrackPlayer = qs('#animation-media-soundtrack-player');
    const soundtrackName = qs('#animation-media-soundtrack-name');
    const offset = qs('#animation-media-offset');
    const offsetSave = qs('#animation-media-offset-save');
    const wavRow = qs('#animation-media-motion-audio');
    const wavSelect = qs('#animation-media-wav-select');
    const wavPlayer = qs('#animation-media-wav-player');
    const wavNote = qs('#animation-media-wav-note');
    const current = Boolean(project && projectMedia.projectId === project.id);
    const loading = current && projectMedia.loading;
    const image = projectMediaAssets('source_image')[0];
    const soundtrack = projectMediaAssets('soundtrack')[0];
    const wavs = projectMediaAssets('motion_lab_wav');
    const warnings = current ? projectMedia.warnings : [];

    if (status) status.textContent = !project ? 'Open a project to inspect saved media.' :
      !current || loading ? 'Checking saved project media…' :
      (image ? 'Start image verified · ' : '') +
      (soundtrack ? 'Soundtrack attached · ' : '') +
      wavs.length + ' saved Motion Lab WAV' + (wavs.length === 1 ? '' : 's') +
      (warnings.length ? ' · Some assets need attention.' : '.');
    if (warningNode) {
      warningNode.hidden = !warnings.length;
      warningNode.textContent = warnings.join('\n');
    }
    if (soundtrackRow) soundtrackRow.hidden = !soundtrack;
    if (soundtrackPlayer) {
      const url = soundtrack?.url || '';
      if (soundtrackPlayer.getAttribute('src') !== url) {
        if (url) soundtrackPlayer.src = url;
        else soundtrackPlayer.removeAttribute('src');
      }
    }
    if (soundtrackName) soundtrackName.textContent = soundtrack
      ? (projectMedia.soundtrack?.filename || soundtrack.filename) +
        (Number.isFinite(soundtrackPlayer?.duration) ?
          ' · ' + soundtrackPlayer.duration.toFixed(2) + 's' : '') +
        ' · offset ' + Number(projectMedia.soundtrack?.offset_seconds || 0).toFixed(2) + 's'
      : '';
    if (offset) {
      offset.disabled = !soundtrack;
      if (current && projectMedia.soundtrack && document.activeElement !== offset) {
        offset.value = String(projectMedia.soundtrack.offset_seconds || 0);
      }
    }
    if (offsetSave) offsetSave.disabled = !soundtrack || !projectMedia.soundtrack;
    const savedUse = qs('#animation-motion-lab-use-soundtrack');
    const savedStatus = qs('#animation-motion-lab-soundtrack-info');
    if (savedUse) savedUse.disabled = !soundtrack || !current || loading ||
      motionLabSoundtrackBusy || Boolean(motionLabBusy) || animationMode() !== '3d';
    if (savedStatus) savedStatus.textContent = motionLabSoundtrackBusy
      ? 'Preparing the saved soundtrack on the Morphorum host…'
      : motionLabSoundtrackStatus && current
        ? motionLabSoundtrackStatus
        : soundtrack ? 'Available: ' + (projectMedia.soundtrack?.filename || soundtrack.filename) +
          ' · ' + (projectMedia.soundtrack?.format || 'audio').toUpperCase() +
          '. Use without uploading again. Compressed formats need host FFmpeg.'
        : 'No project soundtrack attached. Choose a WAV or attach audio in Import Motion Settings.';

    if (wavRow) wavRow.hidden = wavs.length === 0;
    if (wavSelect) {
      const previouslySelected = wavSelect.value;
      wavSelect.replaceChildren();
      for (const wav of wavs) {
        const option = document.createElement('option');
        option.value = wav.sha256;
        option.textContent = wav.filename.slice(0, 12) + '… · ' +
          (wav.bytes / (1024 * 1024)).toFixed(1) + ' MiB';
        wavSelect.appendChild(option);
      }
      const selected = wavs.some(w => w.sha256 === projectMedia.selectedWav)
        ? projectMedia.selectedWav
        : (wavs.some(w => w.sha256 === previouslySelected) ? previouslySelected : '');
      if (selected) wavSelect.value = selected;
      wavSelect.disabled = loading;
    }
    const selectedWav = wavs.find(w => w.sha256 === projectMedia.selectedWav);
    if (wavPlayer) {
      const url = selectedWav?.url || '';
      if (wavPlayer.getAttribute('src') !== url) {
        if (url) wavPlayer.src = url;
        else wavPlayer.removeAttribute('src');
      }
    }
    if (wavNote) wavNote.textContent = !selectedWav
      ? 'No WAV selected.'
      : motionLabAudioProjectId === project?.id &&
        motionLabAudioAnalysis?.source_sha256 === selectedWav.sha256
        ? 'Saved WAV restored for synchronized Motion Curves playback and analysis.'
        : warnings.some(message => message.startsWith('Could not restore saved Motion Lab WAV'))
          ? 'Saved WAV could not be analyzed. See the media warning above.'
          : 'Restoring saved WAV analysis for this project…';
    renderSourceState();
  }

  async function restoreSavedMotionWav(sha256) {
    const id = state.project?.id;
    const asset = projectMediaAssets('motion_lab_wav').find(item => item.sha256 === sha256);
    const token = ++projectAudioRestoreGeneration;
    motionLabReleaseAudio();
    motionLabAudioAnalysis = null;
    motionLabAudioProjectId = null;
    motionLabAudioPreview();
    motionLabAudioUi();
    if (!id || !asset) return;
    const info = qs('#animation-motion-lab-audio-info');
    if (info) info.textContent = 'Restoring saved WAV analysis…';
    try {
      const response = await api(asset.url + '/analysis');
      if (token !== projectAudioRestoreGeneration || state.project?.id !== id ||
          projectMedia.selectedWav !== sha256) return;
      const analysis = response.analysis;
      if (!Array.isArray(analysis?.values) ||
          analysis.values.length !== Number(state.project.animation.max_frames) ||
          Number(analysis.fps) !== Number(state.project.animation.fps)) {
        throw new Error('Saved WAV analysis does not match the current project frames/FPS.');
      }
      motionLabAudioAnalysis = analysis;
      motionLabAudioProjectId = id;
      motionStudioRestoreChannels(id, analysis);
      motionLabAudioUrl = asset.url;
      motionLabAudioElement = new Audio(asset.url);
      motionLabAudioElement.preload = 'auto';
      motionLabAudioElement.load();
      if (!(await motionStudioHydrateEdits(id, analysis, () =>
        token === projectAudioRestoreGeneration && state.project?.id === id &&
        projectMedia.selectedWav === sha256))) return;
      motionStudioConnectAudioTransport();
      // Reload the most recently saved layer's editing choices alongside its
      // analysis. Keep the currently saved camera tracks untouched.
      const savedLayer = (state.project.motion_lab?.layers || []).slice().reverse()
        .find(layer => layer.type === 'audio' && layer.sha256 === sha256);
      if (savedLayer) {
        for (const [name, value] of Object.entries({
          band: savedLayer.band, detection: savedLayer.detection,
          sensitivity: savedLayer.sensitivity, axis: savedLayer.axis,
          threshold: savedLayer.threshold, distance: savedLayer.distance,
          attack: savedLayer.attack_frames, release: savedLayer.release_frames,
        })) {
          const control = qs('#animation-motion-lab-audio-' + name);
          if (control && value != null) control.value = String(value);
        }
      }
      motionLabAudioSyncStatus('Saved WAV ready for synchronized playback.');
      if (info) info.textContent = 'Restored saved WAV (' + analysis.values.length +
        ' frames, ' + Number(analysis.duration_seconds).toFixed(2) + ' seconds).';
      const badge = qs('#animation-motion-lab-audio-status');
      if (badge) badge.textContent = 'Saved WAV ready';
      motionLabStereoWaveform();
      motionDirectorPanel();
      motionLabAudioPreview();
      motionLabAudioUi();
    } catch (error) {
      if (token !== projectAudioRestoreGeneration || state.project?.id !== id) return;
      projectMediaWarning('Could not restore saved Motion Lab WAV: ' + error.message);
      if (info) info.textContent = 'Saved WAV could not be restored: ' + error.message;
      renderProjectMedia();
      motionLabAudioUi();
    }
    if (token === projectAudioRestoreGeneration) renderProjectMedia();
  }

  async function restoreProjectMedia({ resetAudio = false, preferredWav = '' } = {}) {
    const id = state.project?.id;
    const token = ++projectMediaGeneration;
    if (resetAudio) {
      motionLabSoundtrackStatus = '';
      ++projectAudioRestoreGeneration;
      motionLabReleaseAudio();
      motionLabAudioAnalysis = null;
      motionLabAudioProjectId = null;
      motionLabEditedEvents = null;
      motionLabSelectedEvent = null;
      motionDirectorCues = [];
      motionDirectorSelected = null;
      motionStudioChannelState = {projectId: '', sha: '', channels: [], dirty: false};
      ++motionStudioSpectrumToken;
      motionStudioSpectrum = {projectId:'',sha:'',points:[],maxHz:20000,loading:false,error:''};
      motionStudioBandPreview = {projectId:'',sha:'',fps:0,frames:0,ranges:'',bands:null};
      motionStudioSelectedChannel = '';
      motionStudioRenderChannels();
      motionLabStereoWaveform();
      motionLabAudioPreview();
      motionLabAudioUi();
    }
    if (!id) {
      projectMedia = { projectId: '', loading: false, assets: [], warnings: [],
        soundtrack: null, selectedWav: '' };
      renderProjectMedia();
      return;
    }
    const previous = projectMedia.projectId === id ? projectMedia.selectedWav : '';
    projectMedia = { projectId: id, loading: true, assets: [], warnings: [],
      soundtrack: null, selectedWav: previous };
    renderProjectMedia();
    try {
      const inventory = await api('/api/animation/projects/' + encodeURIComponent(id) + '/media-inventory');
      if (token !== projectMediaGeneration || state.project?.id !== id) return;
      const assets = Array.isArray(inventory.assets) ? inventory.assets : [];
      const warnings = Array.isArray(inventory.warnings) ? inventory.warnings.slice() : [];
      const soundtrackAsset = assets.find(asset => asset.kind === 'soundtrack');
      let soundtrack = null;
      if (soundtrackAsset) {
        try {
          const response = await api('/api/animation/projects/' + encodeURIComponent(id) +
            '/motion-import/soundtrack');
          soundtrack = response.soundtrack;
          if (!soundtrack) warnings.push('Soundtrack is stored but its metadata is unavailable.');
        } catch (error) {
          warnings.push('Could not read attached soundtrack settings: ' + error.message);
        }
      }
      if (token !== projectMediaGeneration || state.project?.id !== id) return;
      const wavs = assets.filter(asset => asset.kind === 'motion_lab_wav');
      const layers = Array.isArray(state.project.motion_lab?.layers)
        ? state.project.motion_lab.layers : [];
      const lastAudioLayer = layers.slice().reverse().find(layer =>
        layer.type === 'audio' && wavs.some(wav => wav.sha256 === layer.sha256));
      const currentAnalysisSha = motionLabAudioProjectId === id
        ? motionLabAudioAnalysis?.source_sha256 : '';
      const chosen = [preferredWav, currentAnalysisSha, previous, lastAudioLayer?.sha256, wavs[0]?.sha256]
        .find(sha => sha && wavs.some(wav => wav.sha256 === sha)) || '';
      projectMedia = { projectId: id, loading: false, assets, warnings,
        soundtrack, selectedWav: chosen };
      renderProjectMedia();
      if (chosen && (resetAudio || motionLabAudioProjectId !== id ||
          motionLabAudioAnalysis?.source_sha256 !== chosen)) {
        await restoreSavedMotionWav(chosen);
      }
    } catch (error) {
      if (token !== projectMediaGeneration || state.project?.id !== id) return;
      projectMedia.loading = false;
      projectMediaWarning('Could not check saved project assets: ' + error.message);
      renderProjectMedia();
    }
  }

  function sourceImageUrl() {
    if (!state.project?.id || !state.project?.animation?.source_image) return '';
    if (projectMedia.projectId === state.project.id && !projectMedia.loading &&
        !projectMediaAssets('source_image').length) return '';
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
    const hasSource = Boolean(state.project?.animation?.source_image) &&
      (projectMedia.projectId !== state.project?.id || projectMedia.loading ||
       projectMediaAssets('source_image').length > 0);
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
            : 'Frame 0 requires a valid uploaded image. If its saved file is missing, upload it again.')
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
      : (state.project?.animation?.source_image ? 'Saved start image missing or unreadable. Re-upload to repair.' :
        requiresSource ? 'No starting image uploaded.' : 'No image uploaded. Prompt mode does not require one.');
    if (fileInput) fileInput.disabled = !state.project || Boolean(state.motionJobId) || renderActive || state.depthBusy;
    if (clear) clear.disabled = !state.project || !state.project?.animation?.source_image || Boolean(state.motionJobId) || renderActive || state.depthBusy;
    // A source photo is optional: Motion Lab falls back to a calibration grid.
    if (preview) preview.disabled = !state.project || Boolean(state.motionJobId) || renderActive || state.depthBusy;
    const overlay = qs('#animation-preview-highlight-holes');
    if (overlay) overlay.disabled = !state.project || animationMode() !== '3d' ||
      Boolean(state.motionJobId) || renderActive || state.depthBusy;
    const renderButton = qs('#animation-start-render');
    if (renderButton) {
      const hasModel = Boolean(qs('#animation-model')?.value);
      renderButton.disabled = !state.project || !hasModel || (requiresSource && !hasSource) ||
        renderActive || Boolean(state.motionJobId) || motionPreviewStarting ||
        animationRenderStarting || state.depthBusy;
    }
    // Keep the floating Render Animation shortcut synchronized with the
    // existing guarded render button as models, sources, and jobs change.
    motionLabSyncQuickActions();
  }

  let motionFramePlayer = null;

  // MS5.1: project-frame review metadata is kept outside saved motion layers.
  let motionReviewRange={start:0,end:0};
  const motionReviewEl=key=>qs('#animation-motion-review-'+key);
  function motionReviewStatus(message) {
    const node=motionReviewEl('status');
    if(node)node.textContent=message;
  }
  function motionReviewMatch() {
    const player=motionFramePlayer;
    if(!player?.jobId)return 'Generate a camera motion preview first.';
    const frames=Number(qs('#animation-max-frames')?.value||
      state.project?.animation?.max_frames);
    const fps=Number(qs('#animation-fps')?.value||state.project?.animation?.fps);
    if(!Number.isInteger(frames)||frames<1||!Number.isFinite(fps)||fps<=0||fps>240)
      return 'Invalid Editor frame count or FPS. Correct the settings before reviewing.';
    if(frames!==player.count||Math.abs(fps-player.fps)>1e-6)
      return 'Timing mismatch: preview '+player.count+' frames @ '+player.fps+
        ' FPS, Editor '+frames+' frames @ '+fps+' FPS. Regenerate camera preview.';
    return '';
  }
  function motionReviewRefreshTakes() {
    const select=motionReviewEl('take');
    if(!select)return;
    const old=select.value;
    select.replaceChildren();
    const empty=document.createElement('option');
    empty.value='';empty.textContent='Choose staged take';select.appendChild(empty);
    for(const layer of motionLabDraftLayers) {
      if(layer.type!=='recording')continue;
      const option=document.createElement('option');
      option.value=layer.id;
      option.textContent=(layer.name||'Recorded take')+' ('+
        layer.start_frame+'–'+(layer.end_frame-1)+')';
      select.appendChild(option);
    }
    if(motionLabDraftLayers.some(x=>x.type==='recording'&&x.id===old))select.value=old;
  }
  function motionReviewFrame({frame,fps,frames,previewSampleFrame}) {
    const mismatch=motionReviewMatch(),value=motionReviewEl('values');
    if(mismatch){
      motionReviewStatus(mismatch);
      motionCompareClear(mismatch);
      if(value)value.textContent='Comparison unavailable until project and preview timing match.';
      return;
    }
    motionReviewStatus('Project frame '+frame+' ('+(frame/fps).toFixed(3)+
      's) · CPU preview sample from frame '+previewSampleFrame);
    motionCompareFrame(frame);
    const visual=motionLabVisual;
    if(!value)return;
    if(!visual?.series||visual.stale||visual.count!==frames||
        Math.abs(visual.fps-fps)>1e-6){
      value.textContent='Curves unavailable, stale or mismatched. Update Curves to compare six-axis values.';
      return;
    }
    value.textContent=['translation_x','translation_y','translation_z',
      'rotation_x','rotation_y','rotation_z'].map((axis,i)=>
      ['X','Y','Z','Pitch','Yaw','Roll'][i]+' '+
      Number(visual.series[axis][frame]).toFixed(i<3?4:3))
      .join(' · ')+' · native units/frame';
  }

  // MS5.2: comparison is display-only; validated historical PNGs are shown
  // beside the existing CPU preview, never inserted into project/layer data.
  let motionCompareMetadata=null;
  let motionCompareRequest=0;
  const motionCompareEl=key=>qs('#animation-motion-compare-'+key);
  function motionCompareStatus(message){
    const node=motionCompareEl('status');
    if(node)node.textContent=message;
  }
  function motionCompareClear(message='Choose a completed render to compare.'){
    ++motionCompareRequest;
    motionCompareMetadata=null;
    const wrap=motionCompareEl('render-wrap');
    if(wrap)wrap.hidden=true;
    const img=motionCompareEl('render-image');
    if(img)img.removeAttribute('src');
    const frameLabel=motionCompareEl('frame-label');
    if(frameLabel)frameLabel.textContent='';
    motionCompareStatus(message);
  }
  function motionCompareFrame(frame) {
    const meta=motionCompareMetadata;
    if(!meta)return;
    const player=motionFramePlayer;
    const problem=motionReviewMatch();
    if(!player?.jobId || problem || meta.project_id!==state.project?.id ||
       meta.frames!==player.count || Math.abs(meta.fps-player.fps)>1e-6){
      motionCompareClear(problem||'Preview or project timing changed. Reload the comparison.');
      return;
    }
    const img=motionCompareEl('render-image');
    const url='/api/animation/renders/'+encodeURIComponent(meta.project_id)+
      '/'+encodeURIComponent(meta.render_id)+'/frames/'+frame;
    if(img && img.getAttribute('src')!==url)img.src=url;
    const frameLabel=motionCompareEl('frame-label');
    if(frameLabel)frameLabel.textContent='Exact render frame '+frame+
      ' of '+(meta.frames-1)+' · '+(frame/meta.fps).toFixed(3)+'s';
  }
  async function motionCompareRefresh() {
    const select=motionCompareEl('select');
    if(!select)return;
    const projectId=state.project?.id;
    const token=++motionCompareRequest;
    motionCompareMetadata=null;
    if(motionCompareEl('render-wrap'))motionCompareEl('render-wrap').hidden=true;
    select.replaceChildren();
    const blank=document.createElement('option');
    blank.value='';blank.textContent='Choose a saved render';
    select.appendChild(blank);
    if(!projectId || !motionFramePlayer?.jobId){
      motionCompareStatus('Generate a CPU preview for this project first.');
      return;
    }
    motionCompareStatus('Loading this project’s saved renders…');
    try {
      const data=await api('/api/animation/projects/'+encodeURIComponent(projectId)+'/renders');
      if(token!==motionCompareRequest || projectId!==state.project?.id ||
         !motionFramePlayer?.jobId)return;
      for(const render of (Array.isArray(data.renders)?data.renders:[])){
        if(!render?.id || render.project_id!==projectId)continue;
        const option=document.createElement('option');
        option.value=render.id;
        option.textContent=render.id+' · '+(render.status||'unknown')+
          ' · '+(render.total_frames||'?')+' frames';
        select.appendChild(option);
      }
      motionCompareStatus(select.options.length>1
        ?'Choose a completed render, then Compare Render. This never changes project files.'
        :'No saved renders found for this project.');
    }catch(error){
      if(token===motionCompareRequest)motionCompareStatus('Cannot list saved renders: '+error.message);
    }
  }
  async function motionCompareLoad(){
    const id=motionCompareEl('select')?.value;
    const projectId=state.project?.id;
    const player=motionFramePlayer;
    const previewId=player?.jobId;
    const problem=motionReviewMatch();
    if(!id || !projectId || !previewId || problem){
      motionCompareClear(problem||'Select a render and generate a CPU preview first.');
      return;
    }
    const token=++motionCompareRequest;
    motionCompareMetadata=null;
    if(motionCompareEl('render-wrap'))motionCompareEl('render-wrap').hidden=true;
    motionCompareStatus('Checking render manifest and PNG frame coverage…');
    try{
      const meta=await api('/api/animation/renders/'+encodeURIComponent(projectId)+
        '/'+encodeURIComponent(id)+'/review-metadata');
      if(token!==motionCompareRequest || state.project?.id!==projectId ||
         motionFramePlayer?.jobId!==previewId)return;
      if(!meta.ready){
        motionCompareStatus('Render not available for comparison: '+
          (Array.isArray(meta.issues)?meta.issues.join(' '):'incomplete metadata.'));
        return;
      }
      if(meta.project_id!==projectId || meta.render_id!==id ||
         meta.frames!==player.count || Math.abs(meta.fps-player.fps)>1e-6 ||
         motionReviewMatch()){
        motionCompareStatus('Render timing mismatch: render '+meta.frames+' frames @ '+
          meta.fps+' FPS; CPU preview '+player.count+' frames @ '+player.fps+
          ' FPS. Choose a compatible render and regenerate preview if needed.');
        return;
      }
      motionCompareMetadata={project_id:projectId,render_id:id,
        frames:meta.frames,fps:meta.fps};
      const wrap=motionCompareEl('render-wrap');
      if(wrap)wrap.hidden=false;
      motionCompareStatus('Comparing completed render '+id+
        ' with CPU preview. Both images follow the same project-frame clock.');
      motionCompareFrame(player.frame);
    }catch(error){
      if(token===motionCompareRequest)motionCompareStatus('Cannot load render metadata: '+error.message);
    }
  }
  function motionCompareBind(){
    motionCompareEl('refresh')?.addEventListener('click',()=>void motionCompareRefresh());
    motionCompareEl('load')?.addEventListener('click',()=>void motionCompareLoad());
    motionCompareEl('clear')?.addEventListener('click',()=>motionCompareClear());
    motionCompareEl('render-image')?.addEventListener('error',()=>{
      if(motionCompareMetadata)motionCompareClear('Stored PNG frame is unavailable. Render comparison was stopped.');
    });
  }


  // MS5.3: reuse existing native motion editor and punch-in controls.
  // Preparing never stages or applies a layer. The preview transport remains
  // display-only even if it is comparing an older completed render.
  let motionRefineBaseline=null;
  const motionRefineEl=key=>qs('#animation-motion-refine-'+key);
  const MOTION_REFINE_AXES=['translation_x','translation_y','translation_z',
    'rotation_x','rotation_y','rotation_z'];
  function motionRefineStatus(message) {
    if(motionRefineEl('status'))motionRefineEl('status').textContent=message;
  }
  function motionRefineClear(message='Capture Before Curves before staging a new correction.') {
    motionRefineBaseline=null;
    if(motionRefineEl('results')){
      motionRefineEl('results').hidden=true;
      motionRefineEl('results').textContent='';
    }
    if(message)motionRefineStatus(message);
  }
  function motionRefineRange() {
    const project=state.project,player=motionFramePlayer;
    if(!project || animationMode()!=='3d' || !player?.jobId ||
       motionLabBusy || motionLabRecorder?.active || motionReviewMatch() ||
       !motionReviewEl('enabled')?.checked)return null;
    const a=motionReviewEl('a'),b=motionReviewEl('b');
    if(!a?.value.trim() || !b?.value.trim())return null;
    const start=Number(a.value),end=Number(b.value);
    if(!Number.isInteger(start)||!Number.isInteger(end)||
       start<0 || end>=player.count || start>end)return null;
    return {projectId:project.id,start,end,frames:player.count,fps:player.fps};
  }
  function motionRefineRequireRange() {
    const range=motionRefineRange();
    if(!range)motionRefineStatus('Choose a 3D project, generate a matching CPU preview, enable A/B, and select valid frames. Stop recording or other Motion Lab operations first.');
    return range;
  }
  function motionRefineContinuous() {
    const range=motionRefineRequireRange();
    if(!range)return;
    const form=motionStudioArrangementFields();
    if(!form)return motionRefineStatus('Continuous Motion editor is unavailable.');
    motionFramePlayer.pause();
    // Explicitly force New Movement: do not overwrite a previously selected
    // staged preset just because the editor still remembers its selection.
    motionStudioArrangementSelection='';
    motionStudioArrangementLoaded='';
    motionStudioArrangementResetFields();
    form.start.value=String(range.start);
    form.end.value=String(range.end+1); // editor range uses exclusive end
    motionStudioArrangementSyncRange('start');
    showAnimationTab('audio');
    motionRefineStatus('Frames '+range.start+'–'+range.end+
      ' transferred to a NEW Continuous Camera Motion region. Select axes, preset and Add/Replace, then click + Stage Movement. No layer has been changed yet.');
    motionLabNotify('Ranged continuous correction prepared. Stage Movement only when ready; Undo remains available.');
  }
  function motionRefinePunch() {
    const range=motionRefineRequireRange();
    if(!range)return;
    const selected=motionReviewEl('take')?.value;
    const index=motionLabDraftLayers.findIndex(layer=>layer.type==='recording'&&layer.id===selected);
    const take=motionLabDraftLayers[index];
    if(!take)return motionRefineStatus('Select a staged recorded take in A/B Motion Review before preparing a punch-in.');
    if(Number(take.fps)!==range.fps || range.start<take.start_frame ||
       range.end>=take.end_frame || !Array.isArray(take.axes) || !take.axes.length ||
       !take.axes.every(axis=>MOTION_REFINE_AXES.includes(axis))){
      return motionRefineStatus('The A/B interval must fit entirely inside the selected take at the same FPS, with valid recorded axes. Nothing was changed.');
    }
    motionFramePlayer.pause();
    const mode=qs('#animation-motion-lab-record-mode');
    const target=qs('#animation-motion-lab-punch-target');
    const start=qs('#animation-motion-lab-record-start');
    const end=qs('#animation-motion-lab-punch-end');
    if(!mode||!target||!start||!end)
      return motionRefineStatus('Recording punch-in controls are unavailable.');
    mode.value='punch';
    motionLabPunchUi(); // regenerate index mapping from current draft order
    if(!Array.from(target.options).some(item=>item.value===String(index)))
      return motionRefineStatus('Selected take no longer exists in the draft. Refresh your selection.');
    target.value=String(index);
    start.value=String(range.start);
    end.value=String(range.end+1); // punch-in is exclusive-end
    // Match arming to the target take; punch validation rejects other axes.
    qsa('[data-motion-record-axis]').forEach(control=>{
      control.checked=take.axes.includes(control.dataset.motionRecordAxis);
    });
    motionLabRecordingUi();
    showAnimationTab('recording');
    motionRefineStatus('Punch-in prepared for frames '+range.start+'–'+range.end+
      '. Review armed axes and feather, then press Record to capture the entire interval. The take remains unchanged until recording finishes.');
    motionLabNotify('Punch-in prepared in Recording. An incomplete capture is discarded; successful punch-in supports Undo.');
  }
  function motionRefineSnapshot(range,visual) {
    return {
      projectId:range.projectId,frames:range.frames,fps:range.fps,
      start:range.start,end:range.end,
      series:Object.fromEntries(MOTION_REFINE_AXES.map(axis=>
        [axis,visual.series[axis].slice()])),
    };
  }
  function motionRefineFresh(range) {
    const visual=motionLabVisual;
    return Boolean(visual?.series && !visual.stale &&
      visual.count===range.frames && Math.abs(visual.fps-range.fps)<1e-6 &&
      MOTION_REFINE_AXES.every(axis=>Array.isArray(visual.series[axis]) &&
        visual.series[axis].length===range.frames));
  }
  async function motionRefineBefore() {
    const range=motionRefineRequireRange();
    if(!range)return;
    if(!motionLabDraftLayers.length)
      return motionRefineStatus('Add an initial draft layer, then capture its curve baseline.');
    motionRefineClear('Capturing baseline from the current Motion Lab draft…');
    motionLabVisual?.invalidate(); // a failed compilation must not look fresh
    await motionLabPreviewOrApply(false,{curvesOnly:true});
    if(state.project?.id!==range.projectId || !motionRefineFresh(range)){
      motionRefineStatus('Could not capture fresh curves. Check the Motion Lab diagnostics and try again.');
      return;
    }
    motionRefineBaseline=motionRefineSnapshot(range,motionLabVisual);
    motionRefineStatus('Before snapshot captured for frames '+range.start+'–'+range.end+
      '. Now stage a new continuous correction or finish a punch-in, then Compare Draft Curves before Apply.');
  }
  async function motionRefineDiff() {
    const range=motionRefineRequireRange(),before=motionRefineBaseline;
    if(!range)return;
    if(!before || before.projectId!==range.projectId ||
       before.frames!==range.frames || Math.abs(before.fps-range.fps)>1e-6 ||
       before.start!==range.start || before.end!==range.end){
      motionRefineStatus('Capture Before Curves for this exact A/B interval before comparing.');
      return;
    }
    motionRefineStatus('Compiling revised draft curves (no animation Apply)…');
    motionLabVisual?.invalidate();
    await motionLabPreviewOrApply(false,{curvesOnly:true});
    if(state.project?.id!==range.projectId || !motionRefineFresh(range)){
      motionRefineStatus('Updated draft curves were not available. No changes have been applied.');
      return;
    }
    const after=motionLabVisual.series;
    const details=[];
    let changesOutside=0,changedAxes=0;
    for(const axis of MOTION_REFINE_AXES) {
      let inCount=0,peak=0,outer=0;
      for(let frame=0;frame<range.frames;frame++){
        const delta=Math.abs(after[axis][frame]-before.series[axis][frame]);
        if(!Number.isFinite(delta)){
          motionRefineStatus('Comparison contains invalid motion values. Nothing was applied.');
          return;
        }
        if(delta>1e-7){
          if(frame>=range.start && frame<=range.end){
            inCount++;peak=Math.max(peak,delta);
          }else outer++;
        }
      }
      if(inCount)changedAxes++;
      changesOutside+=outer;
      if(inCount||outer)details.push(axis.replaceAll('_',' ')+
        ': '+inCount+' frame(s) inside, peak |Δ| '+peak.toFixed(5)+
        (outer?', '+outer+' outside':''));
    }
    const summary=details.length ? details.join(' · ') :
      'No changes detected from the captured baseline.';
    const out=motionRefineEl('results');
    if(out){out.hidden=false;out.textContent=summary;}
    motionRefineStatus('Draft comparison: '+changedAxes+' axis/axes changed within A/B; '+
      changesOutside+' outside-frame axis changes.'+
      (changesOutside?' Review spillover before Apply.':' Only the selected frame range differs.')+
      ' No saved animation or render was modified.');
  }
  function motionRefineBind() {
    motionRefineEl('continuous')?.addEventListener('click',motionRefineContinuous);
    motionRefineEl('punch')?.addEventListener('click',motionRefinePunch);
    motionRefineEl('before')?.addEventListener('click',()=>void motionRefineBefore());
    motionRefineEl('diff')?.addEventListener('click',()=>void motionRefineDiff());
  }

  function motionReviewSet(start,end,enabled=true) {
    if(!motionFramePlayer?.jobId||motionReviewMatch()||
        !motionFramePlayer.setReviewRange(start,end,enabled)) {
      motionReviewStatus('Invalid range or timing. Choose A ≤ B within this preview.');
      return false;
    }
    motionReviewRange={start,end};
    return true;
  }
  function motionReviewEditRange() {
    if(!motionFramePlayer?.jobId)return;
    const a=motionReviewEl('a'),b=motionReviewEl('b');
    const start=Number(a?.value),end=Number(b?.value);
    if(!a?.value.trim()||!b?.value.trim()||
        !motionReviewSet(start,end,motionReviewEl('enabled')?.checked)){
      if(a)a.value=String(motionReviewRange.start);
      if(b)b.value=String(motionReviewRange.end);
    }
  }
  function motionReviewTakeRange() {
    const id=motionReviewEl('take')?.value;
    const layer=motionLabDraftLayers.find(x=>x.type==='recording'&&x.id===id);
    if(!layer){motionReviewStatus('Select a recorded draft take first.');return;}
    if(!motionFramePlayer?.jobId||Number(layer.fps)!==motionFramePlayer.fps||
       layer.start_frame<0||layer.end_frame>motionFramePlayer.count||
       layer.end_frame<=layer.start_frame){
      motionReviewStatus('Recorded take and preview frames/FPS do not match.');
      return;
    }
    motionReviewSet(layer.start_frame,layer.end_frame-1,true);
  }
  function motionReviewOpenCurves() {
    const problem=motionReviewMatch();
    if(problem){motionReviewStatus(problem);return;}
    const frame=motionFramePlayer.frame;
    motionFramePlayer.pause();
    showAnimationTab('curves');
    if(!motionLabVisual?.series||motionLabVisual.stale||
       motionLabVisual.count!==motionFramePlayer.count||
       Math.abs(motionLabVisual.fps-motionFramePlayer.fps)>1e-6) {
      motionLabNotify('Update Curves to review frame '+frame+' at matching FPS.');
      return;
    }
    motionLabVisual.setFrame(frame);
  }
  function motionReviewBind() {
    for(const key of ['a','b','enabled'])
      motionReviewEl(key)?.addEventListener('change',motionReviewEditRange);
    motionReviewEl('mark-a')?.addEventListener('click',()=>{
      if(!motionFramePlayer?.jobId)return;
      const frame=motionFramePlayer.frame;
      motionReviewSet(frame,Math.max(frame,motionReviewRange.end),true);
    });
    motionReviewEl('mark-b')?.addEventListener('click',()=>{
      if(!motionFramePlayer?.jobId)return;
      const frame=motionFramePlayer.frame;
      motionReviewSet(Math.min(frame,motionReviewRange.start),frame,true);
    });
    motionReviewEl('use-take')?.addEventListener('click',motionReviewTakeRange);
    motionReviewEl('curves')?.addEventListener('click',motionReviewOpenCurves);
  }
  function ensureMotionFramePlayer() {
    if (motionFramePlayer || !window.MorphorumMotionFramePlayer) return motionFramePlayer;
    const root = qs('#animation-motion-frame-player');
    if (!root) return null;
    motionFramePlayer = new window.MorphorumMotionFramePlayer({
      root,
      image: qs('#animation-motion-frame-image'),
      play: qs('#animation-motion-frame-play'),
      reset: qs('#animation-motion-frame-reset'),
      loop: qs('#animation-motion-frame-loop'),
      scrub: qs('#animation-motion-frame-scrub'),
      time: qs('#animation-motion-frame-time'),
      rangeEnabled:motionReviewEl('enabled'),
      rangeStart:motionReviewEl('a'),
      rangeEnd:motionReviewEl('b'),
      onFrame:motionReviewFrame,
      onLoad:({frames})=>{
        motionReviewRange={start:0,end:frames-1};
        motionReviewRefreshTakes();
        motionCompareClear('CPU preview loaded. Select a saved render for side-by-side review.');
        void motionCompareRefresh();
        const mismatch=motionReviewMatch();
        if(mismatch)motionReviewStatus(mismatch);
      },
      getAudio: () => motionLabAudioProjectId === state.project?.id ? motionLabAudioElement : null,
      shouldSync: () => Boolean(qs('#animation-motion-lab-audio-sync')?.checked),
      canPlay: () => {
        const issue = motionReviewMatch();
        if(issue) {
          motionReviewStatus(issue);
          motionFramePlayer?.pause();
          return false;
        }
        return true;
      },
      status: message => motionGifSyncStatus(message),
    });
    return motionFramePlayer;
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
    if (motionFramePlayer?.jobId) {
      motionFramePlayer.seek(0);
      motionFramePlayer.play();
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
    motionFramePlayer?.clear();
    motionCompareClear('Generate a CPU camera preview to compare with a completed render.');
    motionRefineClear('Generate a fresh CPU preview and enable A/B to prepare corrections.');
    motionReviewRange={start:0,end:0};
    motionReviewStatus('Generate a camera preview to begin reviewing frames.');
    const values=motionReviewEl('values');
    if(values)values.textContent='Update Motion Curves to compare six-axis values.';
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
      void restoreProjectMedia();
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
      void restoreProjectMedia();
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
      let loadedFrames = false;
      if (job.result?.frame_player_samples && ensureMotionFramePlayer()) {
        try {
          motionFramePlayer.load(job);
          loadedFrames = true;
        } catch (error) {
          motionFramePlayer.clear();
          motionReviewStatus('Frame player unavailable: ' + error.message +
            '. GIF fallback has approximate timing and cannot be A/B scrubbed.');
          toast('Frame preview metadata invalid', error.message, 'warning', 6500);
        }
      }
      if (image) {
        image.hidden = loadedFrames;
        if (!loadedFrames) image.src = job.url + '?v=' + Date.now();
      }
      if (motionFramePlayer?.jobId === job.id) {
        motionGifSyncStatus('Frame player ready: seek, pause, loop and optional WAV sync.');
        if (motionLabAudioElement && qs('#animation-motion-gif-auto-audio')?.checked &&
            qs('#animation-motion-lab-audio-sync')?.checked) motionFramePlayer.play();
      } else if (motionLabAudioElement && motionLabAudioProjectId === state.project?.id &&
          qs('#animation-motion-gif-auto-audio')?.checked &&
          qs('#animation-motion-lab-audio-sync')?.checked) {
        void replayMotionGifWithAudio();
      }
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
      // A project switch clears motionJobId. Never show an old response,
      // even when the HTTP request started before the switch/reload.
      if (state.motionJobId !== jobId) return;
      updateMotionProgress(job);
      if (job.status === 'completed' || job.status === 'failed') { finishMotionPreview(job); return; }
      state.motionPollTimer = window.setTimeout(() => pollMotionPreview(jobId), 350);
    } catch (_) {
      if (state.motionJobId === jobId)
        state.motionPollTimer = window.setTimeout(() => pollMotionPreview(jobId), 1000);
    }
  }

  async function generateMotionPreview(projectOverride = null) {
    if (!state.project || state.motionJobId || motionPreviewStarting ||
        animationRenderStarting || renderIsActive()) return;
    motionPreviewStarting = true;
    const requestedProjectId = state.project.id;
    motionLabSyncQuickActions();
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
            quality: qs('#animation-motion-preview-quality')?.value || 'balanced',
          },
        }),
      });
      if (state.project?.id !== requestedProjectId) return;
      state.motionJobId = job.id;
      updateMotionProgress(job);
      motionLabSyncQuickActions();
      renderSourceState();
      pollMotionPreview(job.id);
    } catch (error) {
      if (state.project?.id !== requestedProjectId) return;
      state.motionJobId = null;
      if (button) {
        button.classList.remove('busy');
        const label = qs('.button-label', button);
        if (label) label.textContent = 'Preview Camera Motion';
      }
      renderSourceState();
      toast('Could not start motion preview', error.message, 'error', 7500);
    } finally {
      motionPreviewStarting = false;
      renderSourceState();
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
    const stability = perf.stability || {};
    if (Number.isFinite(stability.memory_delta_gib)) {
      stats.textContent += ' · GPU allocation drift ' +
        (stability.memory_delta_gib >= 0 ? '+' : '') +
        stability.memory_delta_gib.toFixed(2) + ' GiB';
    }
    if (Number.isFinite(stability.anchor_diffusion_slowdown_ratio)) {
      stats.textContent += ' · late/early anchor timing ' +
        stability.anchor_diffusion_slowdown_ratio.toFixed(2) + '×';
    }
    if (Array.isArray(stability.warnings) && stability.warnings.length) {
      stats.textContent += ' · stability advisory: ' + stability.warnings.join(' ');
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
      const versionedUrl = url + '?inline=true' + '&v=' +
        encodeURIComponent(latest.completed_at || latest.bytes || 'latest');
      if (video && video.dataset.videoUrl !== versionedUrl) {
        video.dataset.videoUrl = versionedUrl;
        video.src = versionedUrl;
        video.load();
      }
      if (link) { link.href = url; link.download = ''; }
      if (meta) meta.textContent =
        latest.format.toUpperCase() + ' · ' + latest.fps + ' fps · ' +
        latest.quality + ' · ' +
        (latest.audio_included ? 'Soundtrack included' : 'Silent video') + ' · ' +
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

  let renderHistoryGeneration = 0;
  function resetRenderUi() {
    ++renderHistoryGeneration;
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
    const projectId = state.project.id;
    const token = ++renderHistoryGeneration;
    try {
      const payload = await api('/api/animation/projects/' + encodeURIComponent(projectId) + '/renders');
      if (token !== renderHistoryGeneration || state.project?.id !== projectId) return;
      const renders = Array.isArray(payload.renders) ? payload.renders :
        [];
      populateRenderHistory(renders);
      if (!state.renderJobId && renders.length) {
        renderAnimationJob(renders[0]);
        await loadVideoExportHistory();
      } else if (!renders.length && !state.renderJobId) {
        renderAnimationJob(null);
        await loadVideoExportHistory();
      }
    } catch (error) {
      if (token === renderHistoryGeneration && state.project?.id === projectId)
        toast('Could not load animation render history', error.message, 'warning', 6000);
    }
  }

  async function showRender(renderId) {
    if (!renderId) { renderAnimationJob(null); return; }
    const projectId = state.project?.id;
    try {
      const job = await api('/api/animation/renders/' + encodeURIComponent(renderId));
      if (state.project?.id !== projectId ||
          (job.project_id && job.project_id !== projectId)) return;
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
      if (renderId !== state.renderJobId ||
          (job.project_id && job.project_id !== state.project?.id)) return;
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
    if (!state.project || renderIsActive() || animationRenderStarting ||
        state.motionJobId || motionPreviewStarting) return;
    animationRenderStarting = true;
    motionLabSyncQuickActions();
    const button = qs('#animation-start-render');
    if (button) { button.classList.add('busy'); button.disabled = true; }
    try {
      // Keep collection inside the try: invalid project inputs must not
      // strand the toolbar in its pending-render locked state.
      const project = collectProject();
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
    } finally {
      animationRenderStarting = false;
      renderSourceState();
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
      void restoreProjectMedia({ resetAudio: true });
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


  const projectManagerState = { selectedId: '', busy: false };
  function projectManagerDate(value) {
    const date = new Date(value || '');
    return Number.isNaN(date.getTime()) ? 'Unknown' : date.toLocaleString();
  }
  function projectManagerDuration(item) {
    const seconds = Number(item?.max_frames || 0) / Number(item?.fps || 1);
    return Number.isFinite(seconds) ? seconds.toFixed(seconds < 10 ? 2 : 1) + 's' : '--';
  }
  function projectManagerSummary(item) {
    return [(item.mode || '2d').toUpperCase(),
      (item.width || '--') + ' × ' + (item.height || '--'),
      (item.max_frames || 0) + ' frames', (item.fps || '--') + ' FPS'].join(' · ');
  }
  function projectManagerFact(parent, label, value) {
    const row = document.createElement('div');
    row.className = 'animation-project-manager-fact';
    const term = document.createElement('dt');
    term.textContent = label;
    const detail = document.createElement('dd');
    detail.textContent = String(value ?? '--');
    row.append(term, detail);
    parent.appendChild(row);
  }
  function renderProjectManager() {
    const list = qs('#animation-project-manager-list');
    const details = qs('#animation-project-manager-details');
    if (!list || !details) return;
    const query = String(qs('#animation-project-manager-search')?.value || '').trim().toLowerCase();
    const order = qs('#animation-project-manager-sort')?.value || 'updated';
    const filtered = state.projects.filter(item =>
      [item.name, item.model_id, item.id, item.model_family].some(value =>
        String(value || '').toLowerCase().includes(query)));
    filtered.sort((a, b) => order === 'name'
      ? String(a.name).localeCompare(String(b.name))
      : order === 'oldest'
      ? String(a.updated_at || '').localeCompare(String(b.updated_at || ''))
      : String(b.updated_at || '').localeCompare(String(a.updated_at || '')));
    const count = qs('#animation-project-manager-count');
    if (count) count.textContent = filtered.length + ' of ' + state.projects.length + ' projects';
    if (!state.projects.some(p => p.id === projectManagerState.selectedId)) {
      projectManagerState.selectedId =
        state.projects.find(p => p.id === state.project?.id)?.id || state.projects[0]?.id || '';
    }
    list.replaceChildren();
    if (!filtered.length) {
      const empty = document.createElement('p');
      empty.className = 'muted animation-project-manager-empty';
      empty.textContent = state.projects.length ? 'No projects match your search.' :
        'No projects yet. Create your first animation project to begin.';
      list.appendChild(empty);
    }
    for (const project of filtered) {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'animation-project-manager-item';
      button.classList.toggle('active', project.id === projectManagerState.selectedId);
      button.setAttribute('aria-pressed', String(project.id === projectManagerState.selectedId));
      button.disabled = projectManagerState.busy;
      const title = document.createElement('strong');
      title.textContent = project.name;
      const info = document.createElement('span');
      info.textContent = projectManagerSummary(project);
      const date = document.createElement('small');
      date.textContent = 'Modified ' + projectManagerDate(project.updated_at);
      button.append(title, info, date);
      button.addEventListener('click', () => {
        projectManagerState.selectedId = project.id;
        renderProjectManager();
      });
      list.appendChild(button);
    }
    details.replaceChildren();
    const selected = state.projects.find(p => p.id === projectManagerState.selectedId);
    for (const id of ['open', 'rename', 'trash']) {
      const button = qs('#animation-project-manager-' + id);
      if (button) button.disabled = !selected || projectManagerState.busy;
    }
    if (!selected) {
      const empty = document.createElement('p');
      empty.className = 'muted';
      empty.textContent = 'Select a project to view its details.';
      details.appendChild(empty);
      return;
    }
    const title = document.createElement('h3');
    title.textContent = selected.name;
    const info = document.createElement('p');
    info.className = 'muted';
    info.textContent = projectManagerSummary(selected);
    const facts = document.createElement('dl');
    facts.className = 'animation-project-manager-facts';
    for (const [label, value] of [
      ['Animation mode', (selected.mode || '2d').toUpperCase()],
      ['Resolution', (selected.width || '--') + ' × ' + (selected.height || '--')],
      ['Duration', projectManagerDuration(selected)],
      ['Frames / rate', selected.max_frames + ' / ' + selected.fps + ' FPS'],
      ['Model', selected.model_id || 'Not selected'],
      ['Model family', selected.model_family || 'Not selected'],
      ['Prompt keyframes', selected.prompt_keyframes ?? 0],
      ['Motion layers', selected.motion_layers ?? 0],
      ['Start mode', selected.start_mode === 'source' ? 'Source image' : 'Prompt'],
      ['Created', projectManagerDate(selected.created_at)],
      ['Last modified', projectManagerDate(selected.updated_at)],
      ['Project ID', selected.id],
    ]) projectManagerFact(facts, label, value);
    details.append(title, info, facts);
    if (selected.id === state.project?.id) {
      const active = document.createElement('p');
      active.className = 'animation-project-manager-active';
      active.textContent = state.dirty ? 'Open now · unsaved edits in Editor' :
        'Currently open in Motion Lab';
      details.appendChild(active);
    }
  }


  async function projectManagerOpen() {
    const id = projectManagerState.selectedId;
    if (!id || projectManagerState.busy) return;
    projectManagerState.busy = true;
    renderProjectManager();
    try {
      const opened = await loadProject(id);
      if (opened) showAnimationTab('editor');
    } finally {
      projectManagerState.busy = false;
      renderProjectManager();
    }
  }
  async function projectManagerRename() {
    const item = state.projects.find(p => p.id === projectManagerState.selectedId);
    if (!item || projectManagerState.busy) return;
    if (item.id === state.project?.id && state.dirty) {
      toast('Save changes before renaming',
        'This project has unsaved Editor changes. Save it first.', 'warning', 6500);
      return;
    }
    const value = await window.MorphorumDialog.prompt({
      title: 'Rename project',
      message: 'Change this project name without changing its ID or folder.',
      initialValue: item.name, inputLabel: 'Project name', maxLength: 120,
      validate: value => String(value || '').trim() ? '' : 'Enter a project name.',
      confirmText: 'Rename Project',
    });
    if (value === null || String(value).trim() === item.name) return;
    projectManagerState.busy = true;
    renderProjectManager();
    try {
      const url = '/api/animation/projects/' + encodeURIComponent(item.id);
      const original = await api(url);
      const updated = await api(url, {
        method: 'PUT',
        body: JSON.stringify({ ...original.project, name: String(value).trim() }),
      });
      if (state.project?.id === item.id) {
        state.project = updated.project;
        state.path = updated.path || state.path;
        fillForm();
      }
      await loadProjectList();
      toast('Project renamed', 'The saved project name has been updated.', 'success');
    } catch (error) {
      toast('Could not rename project', error.message, 'error', 7000);
    } finally {
      projectManagerState.busy = false;
      renderProjectManager();
    }
  }
  async function projectManagerTrash() {
    const item = state.projects.find(p => p.id === projectManagerState.selectedId);
    if (!item || projectManagerState.busy) return;
    if (item.id === state.project?.id && (
      state.dirty || motionLabRecorder?.active || motionLabBusy ||
      state.motionJobId || motionPreviewStarting || renderIsActive() ||
      animationRenderStarting
    )) {
      toast('Project is currently in use',
        'Save changes and wait for any recordings or jobs to finish before deleting.',
        'warning', 7000);
      return;
    }
    const typed = await window.MorphorumDialog.prompt({
      title: 'Move project to Trash?',
      message: 'Move "' + item.name + '" into the managed .trash folder. ' +
        'Rendered animations and exported videos are NOT deleted. ' +
        'Type the exact project name to confirm.',
      initialValue: '', inputLabel: 'Type project name', maxLength: 120,
      confirmText: 'Move to Trash',
      validate: value => String(value || '') === item.name
        ? '' : 'Enter the exact project name to confirm.',
    });
    if (typed === null || String(typed) !== item.name) return;
    projectManagerState.busy = true;
    renderProjectManager();
    try {
      await api('/api/animation/projects/' + encodeURIComponent(item.id), { method: 'DELETE' });
      if (state.project?.id === item.id) {
        clearMotionPreviewResult();
        resetRenderUi();
        state.project = null;
        state.path = '';
        state.timeline = null;
        state.timelineSelection = null;
        state.depthPreview = null;
        resetHybridForProject();
        fillForm();
      }
      projectManagerState.selectedId = '';
      await loadProjectList();
      forgetAnimationProject(item.id);
      toast('Project moved to Trash',
        'Project removed from the list. Rendered animations and exports remain intact.',
        'success', 6500);
    } catch (error) {
      toast('Could not move project to Trash', error.message, 'error', 7500);
    } finally {
      projectManagerState.busy = false;
      renderProjectManager();
    }
  }
  function setupProjectManager(panel) {
    panel.innerHTML = [
      '<div class="motion-tool-page-heading">',
      '<div><p class="eyebrow">MOTION LAB / PROJECT MANAGER</p><h2>Project Manager</h2>',
      '<p class="muted">Browse and organize projects. Open one in Editor to edit its animation settings.</p></div>',
      '<button type="button" class="primary-button compact" id="animation-project-manager-new">+ New Project</button></div>',
      '<div class="animation-project-manager-layout">',
      '<section class="card glass animation-project-manager-browser" aria-label="Project browser">',
      '<div class="animation-project-manager-toolbar">',
      '<label><span>Search projects</span><input id="animation-project-manager-search" type="search" placeholder="Name, model or ID…"></label>',
      '<label><span>Sort</span><select id="animation-project-manager-sort">',
      '<option value="updated">Recently updated</option><option value="name">Name A–Z</option>',
      '<option value="oldest">Least recently updated</option></select></label></div>',
      '<div class="animation-project-manager-count-row"><strong>Projects</strong>',
      '<span id="animation-project-manager-count" class="muted"></span>',
      '<button type="button" id="animation-project-manager-refresh" class="secondary-button compact">Refresh</button></div>',
      '<div class="animation-project-manager-list" id="animation-project-manager-list" aria-label="Animation projects"></div>',
      '</section><section class="card glass animation-project-manager-info" aria-label="Project details">',
      '<div class="card-header"><div><h2>Project Details</h2>',
      '<p class="muted">Saved project information. Unsaved Editor changes are not included.</p></div></div>',
      '<div id="animation-project-manager-details" aria-live="polite"></div>',
      '<div class="animation-project-manager-actions">',
      '<button type="button" id="animation-project-manager-open" class="primary-button" disabled>Open in Editor</button>',
      '<button type="button" id="animation-project-manager-rename" class="secondary-button" disabled>Rename</button>',
      '<button type="button" id="animation-project-manager-trash" class="secondary-button animation-project-manager-danger" disabled>Move to Trash</button>',
      '</div><p class="muted animation-project-manager-help">Trash keeps the managed project folder for manual recovery.',
      ' Rendered frames and video exports live separately and are not removed.</p></section></div>',
    ].join('');
    qs('#animation-project-manager-search')?.addEventListener('input', renderProjectManager);
    qs('#animation-project-manager-sort')?.addEventListener('change', renderProjectManager);
    qs('#animation-project-manager-refresh')?.addEventListener('click', async () => {
      try { await loadProjectList(); }
      catch (error) { toast('Could not refresh projects', error.message, 'error', 6500); }
    });
    qs('#animation-project-manager-open')?.addEventListener('click', () => void projectManagerOpen());
    qs('#animation-project-manager-rename')?.addEventListener('click', () => void projectManagerRename());
    qs('#animation-project-manager-trash')?.addEventListener('click', () => void projectManagerTrash());
    qs('#animation-project-manager-new')?.addEventListener('click', async () => {
      if (projectManagerState.busy) return;
      if (state.dirty && !(await window.MorphorumDialog.confirm({
        title: 'Create a new project?',
        message: 'Unsaved changes in the current Editor will be discarded.',
        variant: 'danger', confirmText: 'Discard & Create',
        cancelText: 'Keep Editing',
      }))) return;
      const original = state.project?.id;
      await createProject();
      if (state.project?.id && state.project.id !== original) showAnimationTab('editor');
    });
    renderProjectManager();
  }

  async function loadProjectList({ loadFirst = false } = {}) {
    const payload = await api('/api/animation/projects');
    state.projects = Array.isArray(payload.projects) ? payload.projects : [];
    renderProjectSelect();
    renderProjectManager();
    if (loadFirst && !state.project && state.projects.length) {
      const savedId = readLastAnimationProject();
      const preferred = state.projects.find(item => item.id === savedId)?.id || '';
      if (savedId && !preferred) forgetAnimationProject(savedId);
      const ordered = [preferred, state.projects[0].id].filter((id, index, list) =>
        Boolean(id) && list.indexOf(id) === index);
      let opened = false;
      for (const id of ordered) {
        if (await loadProject(id, { confirmDirty: false })) {
          opened = true;
          break;
        }
      }
      if (!opened) fillForm();
    } else if (!state.project) {
      fillForm();
    }
    renderEditorGuidance();
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
      return false;
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
      rememberAnimationProject(state.project.id);
      void restoreProjectMedia({ resetAudio: true });
      await loadTimeline();
      await loadDepthPreviewStatus();
      await loadRenderHistory();
      return true;
    } catch (error) {
      toast('Could not load animation project', error.message, 'error', 6500);
      return false;
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
      rememberAnimationProject(state.project.id);
      void restoreProjectMedia({ resetAudio: true });
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
  let motionLabBusyAction = null;
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
    const swapped = qs('#animation-motion-lab-gamepad-profile')?.value === 'swapped';
    const moveStick = swapped ? 2 : 0;
    const lookStick = swapped ? 0 : 2;
    values.translation_x += axis(moveStick);
    values.translation_y += -axis(moveStick + 1);
    values.rotation_y += axis(lookStick);
    values.rotation_x += -axis(lookStick + 1);
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
    const motionPreviewBusy = motionPreviewStarting || Boolean(state.motionJobId);
    const renderBusy = animationRenderStarting || renderIsActive();
    const locked = motionLabBusy || motionPreviewBusy || renderBusy;
    const working = motionLabBusyAction || (motionPreviewBusy ? 'preview' :
      renderBusy ? 'render' : active ? 'record' : null);
    const workingLabels = {
      record: '● Recording…', curves: '↻ Updating…',
      preview: '▶ Previewing…', apply: 'Applying…',
      render: 'Rendering…',
    };
    const workingTargets = {
      record: 'animation-motion-lab-record',
      curves: 'animation-motion-lab-update-curves',
      preview: 'animation-motion-lab-preview-draft',
      apply: 'animation-motion-lab-apply',
      render: 'animation-start-render',
    };
    for (const button of qsa('[data-motion-quick-target]')) {
      const id = button.dataset.motionQuickTarget;
      // Audio Motion's inline Apply button also mirrors the quick-action
      // target. Preserve its visible label before any busy-state repaint.
      // Only dock buttons populate data-label during construction.
      if (!button.dataset.label) button.dataset.label =
        button.textContent.trim() || (id === 'animation-motion-lab-apply'
          ? 'Apply to Animation' : '');
      const original = qs('#' + id);
      // Stop remains available during a take; all other actions honor
      // preview, curves/apply, render and live-recording operation locks.
      const isStop = id === 'animation-motion-lab-stop-recording';
      const running = id === workingTargets[working];
      button.disabled = (!isStop && (active || locked)) || !original || original.disabled;
      button.dataset.running = String(running);
      button.setAttribute('aria-busy', String(running));
      button.textContent = running ? workingLabels[working] : button.dataset.label;
    }
    const status = qs('#animation-motion-lab-quick-status');
    if (status) status.textContent = active ? '● Recording' :
      renderBusy ? 'Rendering animation…' :
      motionPreviewBusy ? 'Generating camera preview…' :
      motionLabBusy ? 'Updating camera motion…' :
      motionLabDraftLayers.length + ' draft layer(s)';
    const audioStatus = qs('#animation-audio-workspace-status');
    if (audioStatus) audioStatus.textContent = !state.project ? 'Open a project in Editor first.' :
      motionLabDraftLayers.length + ' Motion Lab draft layer(s) · Add audio, review, then apply.';
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
      ['animation-start-render', 'Render Animation'],
    ];
    for (const [id, label] of specs) {
      const button = document.createElement('button');
      button.type = 'button';
      button.textContent = label;
      button.dataset.label = label;
      button.dataset.motionQuickTarget = id;
      button.className = id === 'animation-start-render'
        ? 'primary-button compact animation-motion-quick-render'
        : id.endsWith('-apply') ? 'primary-button compact' : 'secondary-button compact';
      button.disabled = true;
      button.addEventListener('click', () => {
        const original = qs('#' + id);
        if (!original || original.disabled) return;
        // Navigate first so recording controls, live graphs, and the
        // preview player are mounted in their visible workspace.
        const destination = {
          'animation-motion-lab-record': 'recording',
          'animation-motion-lab-update-curves': 'curves',
          'animation-motion-lab-preview-draft': 'preview',
          'animation-start-render': 'monitor',
        }[id];
        if (destination) showAnimationTab(destination);
        original.click();
        motionLabSyncQuickActions();
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
  let motionLabEditedEvents = null;
  let motionLabSelectedEvent = null;
  let motionLabMarkersDirty = false;
  let motionLabMarkerUndo = [];
  let motionLabMarkerRedo = [];
  function motionLabMarkerSnapshot() {
    if (!motionLabEditedEvents) return;
    motionLabMarkerUndo.push(motionLabEditedEvents.map(e=>({...e})));
    if (motionLabMarkerUndo.length > 60) motionLabMarkerUndo.shift();
    motionLabMarkerRedo = [];
  }
  function motionLabMarkerHistory(redo) {
    const source = redo ? motionLabMarkerRedo : motionLabMarkerUndo;
    if (!source.length || !motionLabEditedEvents) return;
    const destination = redo ? motionLabMarkerUndo : motionLabMarkerRedo;
    destination.push(motionLabEditedEvents.map(e=>({...e})));
    motionLabEditedEvents = source.pop();
    motionLabMarkersDirty = true;
    motionLabStereoWaveform();
  }

  async function motionLabSaveMarkers() {
    if (!motionLabAudioAnalysis || !motionLabEditedEvents || !state.project ||
        motionLabAudioProjectId !== state.project.id) return;
    const button = qs('[data-event-persist]');
    if (button) button.disabled = true;
    try {
      const saved = await api('/api/animation/projects/' + encodeURIComponent(state.project.id) +
        '/motion-lab/audio-markers', {method:'PUT',body:JSON.stringify({
          source_sha256:motionLabAudioAnalysis.source_sha256,
          duration_seconds:motionLabAudioAnalysis.duration_seconds,
          events:motionLabEditedEvents,
        })});
      if (!saved?.markers) throw new Error('Marker save was not confirmed.');
      motionLabMarkersDirty = false;
      motionLabEventEditor();
      motionLabNotify('Drum marker edits saved for this WAV.');
    } catch(error) {
      motionLabNotify('Could not save markers: ' + (error?.message || error));
    } finally {
      if (button) button.disabled = false;
    }
  }

  function motionLabEventEditor() {
    const panel = qs('#animation-audio-event-editor');
    if (!panel || !motionLabAudioAnalysis) return;
    const events = motionLabEditedEvents || [];
    const selected = events.find(e => e.id === motionLabSelectedEvent);
    const output = panel.querySelector('[data-event-count]');
    if (output) output.textContent = events.filter(e => e.enabled).length +
      ' active / ' + events.length + ' markers · ' +
      (motionLabMarkersDirty ? 'Unsaved edits' : 'Saved or unmodified');
    const time = panel.querySelector('[data-event-time]');
    const kind = panel.querySelector('[data-event-kind]');
    const enabled = panel.querySelector('[data-event-enabled]');
    if (time) { time.disabled = !selected; time.value = selected ? String(selected.time_seconds) : ''; }
    if (kind) { kind.disabled = !selected; kind.value = selected?.kind || 'kick'; }
    if (enabled) { enabled.disabled = !selected; enabled.checked = selected?.enabled !== false; }
    const undo = panel.querySelector('[data-event-undo]');
    const redo = panel.querySelector('[data-event-redo]');
    if (undo) undo.disabled = !motionLabMarkerUndo.length;
    if (redo) redo.disabled = !motionLabMarkerRedo.length;
    const remove = panel.querySelector('[data-event-remove]');
    if (remove) remove.disabled = !selected;
    const summary = panel.querySelector('[data-event-selected]');
    if (summary) summary.textContent = selected ?
      'Selected ' + selected.kind + ' at ' + selected.time_seconds.toFixed(3) + ' s' :
      'Select a marker on the waveform to edit it';
  }
  function motionLabEventChange(action) {
    if (!motionLabAudioAnalysis || !motionLabEditedEvents) return;
    const panel = qs('#animation-audio-event-editor');
    const selected = motionLabEditedEvents.find(e => e.id === motionLabSelectedEvent);
    if (action === 'add' || action === 'remove' || action === 'reset' || action === 'clear-detected' ||
        (action === 'update' && selected)) motionLabMarkerSnapshot();
    if (action === 'add') {
      const duration = motionLabAudioAnalysis.duration_seconds;
      const time = Math.max(0, Math.min(duration - .000001,
        Number(motionLabAudioElement?.currentTime) || 0));
      const id = 'manual-' + String(Date.now()) + '-' + motionLabEditedEvents.length;
      motionLabEditedEvents.push({id, kind:'kick', time_seconds:time,
        strength:1, source:'manual',enabled:true});
      motionLabSelectedEvent = id;
    } else if (action === 'clear-detected') {
      // Preserve user-created manual markers and all camera motion cues.
      motionLabEditedEvents = motionLabEditedEvents.filter(e => e.source === 'manual' ||
        String(e.id).startsWith('manual-'));
      motionLabSelectedEvent = null;
    } else if (action === 'reset') {
      motionLabEditedEvents = (motionLabAudioAnalysis.events?.events || []).map(
        e => ({...e, enabled:true}));
      motionLabSelectedEvent = null;
    } else if (selected && action === 'remove') {
      motionLabEditedEvents = motionLabEditedEvents.filter(e => e.id !== selected.id);
      motionLabSelectedEvent = null;
    } else if (selected && action === 'update') {
      const time = Number(panel?.querySelector('[data-event-time]')?.value);
      if (!Number.isFinite(time) || time < 0 || time >= motionLabAudioAnalysis.duration_seconds) {
        motionLabNotify('Marker time must be within the audio duration.');
        return;
      }
      selected.time_seconds = Math.round(time * 1000000) / 1000000;
      selected.kind = panel.querySelector('[data-event-kind]').value;
      selected.enabled = Boolean(panel.querySelector('[data-event-enabled]').checked);
    }
    motionLabEditedEvents.sort((a,b)=>a.time_seconds-b.time_seconds);
    motionLabMarkersDirty = true;
    motionLabStereoWaveform();
  }
  function motionLabWavePlayhead() {
    const section = qs('#animation-audio-stereo-timeline');
    const line = section?.querySelector('[data-wave-playhead]');
    const readout = section?.querySelector('[data-wave-time]');
    const button = section?.querySelector('[data-wave-play]');
    const audio = motionLabAudioElement;
    const duration = Number(motionLabAudioAnalysis?.duration_seconds) || 0;
    const current = Math.max(0, Math.min(duration, Number(audio?.currentTime) || 0));
    if (readout) readout.textContent = current.toFixed(2) + ' / ' + duration.toFixed(2) + ' s';
    if (button) button.textContent = audio && !audio.paused ? 'Pause audio' : 'Play audio';
    if (!line || !duration) return;
    const begin = Number(section.dataset.waveStart || 0);
    const end = Number(section.dataset.waveEnd || duration);
    const follow = section.querySelector('[data-wave-follow]')?.checked;
    const span = end - begin;
    // Page forward before the playhead reaches the right edge. Updating the
    // Start slider redraws the waveform, then this function uses new bounds.
    if (follow && audio && !audio.paused && span > 0 && span < duration &&
        (current > begin + span * .75 || current < begin)) {
      const desired = Math.max(0, Math.min(duration - span, current - span * .25));
      const startSlider = section.querySelector('[data-wave-start]');
      const zoom = Number(section.querySelector('[data-wave-zoom]')?.value || 1);
      const available = Math.max(0, 1 - 1 / zoom);
      if (startSlider && available > 0) {
        startSlider.value = String(Math.round(desired / duration / available * 1000));
        motionLabStereoWaveform();
        return;
      }
    }
    const shown = current >= begin && current <= end;
    line.setAttribute('visibility', shown ? 'visible' : 'hidden');
    if (shown) {
      const x = (current - begin) / Math.max(1e-9, end - begin) * 800;
      line.setAttribute('x1', x.toFixed(3));
      line.setAttribute('x2', x.toFixed(3));
    }
  }
  function motionLabWaveToggle() {
    const audio = motionLabAudioElement;
    if (!audio) return;
    if (!audio.paused) { audio.pause(); return; }
    if (audio.ended || (Number.isFinite(audio.duration) && audio.currentTime >= audio.duration)) {
      audio.currentTime = 0;
    }
    const started = audio.play();
    started?.catch(error => motionLabAudioSyncStatus(
      'Audio playback blocked: ' + (error?.message || error)));
  }

  function motionLabReleaseAudio() {
    motionLabAudioElement?.pause();
    if (motionLabAudioElement) motionLabAudioElement.removeAttribute('src');
    if (motionLabAudioUrl?.startsWith('blob:')) URL.revokeObjectURL(motionLabAudioUrl);
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

  function motionLabAudioSignal() {
    const analysis = motionLabAudioAnalysis;
    if (!analysis) return [];
    const band = qs('#animation-motion-lab-audio-band')?.value || 'fullband';
    const values = band === 'fullband' ? analysis.values : analysis.bands?.[band];
    if (!Array.isArray(values) || values.length !== analysis.values.length) return [];
    const mode = qs('#animation-motion-lab-audio-detection')?.value || 'level';
    if (mode !== 'transient') return values;
    const sensitivity = Math.max(0, Math.min(1, Number(qs('#animation-motion-lab-audio-sensitivity')?.value) || 0));
    const rises = values.map((v, i) => i ? Math.max(0, v - values[i - 1]) : 0);
    const peak = Math.max(0, ...rises);
    return rises.map(v => peak > 1e-12 ? Math.max(0, Math.min(1, v / peak - sensitivity * .5)) : 0);
  }
  // DA4.2: manual choreography is independent of beat detection.
  let motionDirectorCues = [];
  let motionDirectorSelected = null;
  let motionDirectorDirty = false;
  const MOTION_DIRECTOR_PRESETS = [
    ['push_zoom_in','Push Zoom In'],['roll_right_left','Roll Right → Left'],
    ['push_return','Push & Return'],['roll_left_right','Roll Left → Right'],
    ['dolly_out','Dolly Out'],['shake','Shake'],['ripple','Ripple'],
    ['reveal_drift','Reveal Drift'],['fly_through','Fly-through'],
  ];
  let motionDirectorBulkUndo = null;
  let motionDirectorPreviewMatches = false;
  function motionDirectorFindCandidates() {
    const panel = qs('#animation-audio-motion-director');
    const analysis = motionLabAudioAnalysis;
    if (!panel || !analysis) return [];
    const kind = panel.querySelector('[data-beat-kind]')?.value || 'kick';
    const minStrength = Number(panel.querySelector('[data-beat-strength]')?.value ?? .35);
    const minGap = Number(panel.querySelector('[data-beat-gap]')?.value ?? .1);
    const start = Number(panel.querySelector('[data-beat-start]')?.value ?? 0);
    const end = Number(panel.querySelector('[data-beat-end]')?.value ?? analysis.duration_seconds);
    const every = Number(panel.querySelector('[data-beat-every]')?.value ?? 1);
    if (![minStrength,minGap,start,end,every].every(Number.isFinite) ||
        minStrength<0 || minStrength>1 || minGap<0 || minGap>2 ||
        start<0 || end<=start || end>analysis.duration_seconds + .001 ||
        !Number.isInteger(every) || every<1 || every>16) return [];
    let last = -Infinity;
    const candidates = [];
    for (const event of motionLabEditedEvents || []) {
      if (event.enabled === false || event.kind !== kind ||
          Number(event.strength ?? 1)<minStrength ||
          event.time_seconds<start || event.time_seconds>=end ||
          event.time_seconds-last<minGap) continue;
      last = event.time_seconds;
      candidates.push(event);
    }
    return candidates.filter((_,i)=>i%every===0);
  }
  function motionDirectorFindStatus() {
    const panel=qs('#animation-audio-motion-director');
    if (!panel) return;
    const status=panel.querySelector('[data-beat-summary]');
    const candidates=motionDirectorFindCandidates();
    if (status) status.textContent=candidates.length+' eligible detected or manually corrected hit(s). Review before assigning.';
    const undo=panel.querySelector('[data-beat-undo]');
    if (undo) undo.disabled=!motionDirectorBulkUndo;
  }
  function motionDirectorAssignBeats() {
    const panel=qs('#animation-audio-motion-director');
    if (!panel || !motionLabAudioAnalysis) return;
    const events=motionDirectorFindCandidates();
    if (!events.length) {motionLabNotify('No matching hits in this range.');return;}
    const preset=panel.querySelector('[data-beat-preset]').value;
    const alternate=panel.querySelector('[data-beat-alternate]').checked;
    const intensity=.5, duration=.6;
    const existing=new Set(motionDirectorCues.filter(c=>c.source_event_id)
      .map(c=>c.source_event_id+'|'+c.preset));
    const additions=[];
    for (const event of events) {
      const chosen=alternate ? (additions.length%2 ? 'roll_left_right' : 'roll_right_left') : preset;
      if (existing.has(event.id+'|'+chosen)) continue;
      const id='beatcue-'+Date.now().toString(36)+'-'+(motionDirectorCues.length+additions.length);
      additions.push({id,preset:chosen,time_seconds:event.time_seconds,
        duration_seconds:duration,intensity,easing:'ease_in_out',enabled:true,
        source_event_id:event.id});
      existing.add(event.id+'|'+chosen);
    }
    if (!additions.length) {motionLabNotify('Those hits already have matching cues.');return;}
    if (motionDirectorCues.length+additions.length>3000) {
      motionLabNotify('Cue limit is 3000. Narrow the beat range.');return;
    }
    motionDirectorBulkUndo=motionDirectorCues.map(c=>({...c}));
    motionDirectorCues.push(...additions);
    motionDirectorDirty=true;
    motionDirectorPanel();motionLabStereoWaveform();
    motionLabNotify('Added '+additions.length+' camera cues. Save cues to keep them.');
  }
  function motionDirectorPanel() {
    let panel = qs('#animation-audio-motion-director');
    const waveform = qs('#animation-audio-stereo-timeline');
    if (!waveform || !motionLabAudioAnalysis) return;
    if (panel) panel.hidden = false;
    if (!panel) {
      panel = document.createElement('section');
      panel.id = 'animation-audio-motion-director';
      panel.className = 'animation-audio-motion-director';
      panel.innerHTML = '<div class="animation-audio-director-head"><strong>Camera motion cues</strong>' +
        '<span class="muted">Place a camera move at any point, even without detected beats.</span></div>' +
        '<div class="animation-audio-director-actions"><button type="button" data-cue-add>Add cue at playhead</button>' +
        '<button type="button" data-cue-save>Save cues</button>' +
        '<button type="button" data-cue-preview>Preview camera cues</button>' +
        '<button type="button" data-cue-apply>Apply camera cues</button>' +
        '<span data-cue-status class="muted"></span></div>' +
        '<div class="animation-audio-director-fields">' +
        '<label>Movement<select data-cue-preset></select></label>' +
        '<label>Start (seconds)<input data-cue-time type="number" min="0" step=".001"></label>' +
        '<label>Duration (seconds)<input data-cue-duration type="number" min=".01" max="30" step=".05"></label>' +
        '<label>Intensity (0–1)<input data-cue-intensity type="number" min="0" max="1" step=".05"></label>' +
        '<label>Easing<select data-cue-easing><option value="ease_in_out">Ease in/out</option>' +
        '<option value="linear">Linear</option><option value="smoothstep">Smoothstep</option>' +
        '<option value="ease_in">Ease in</option><option value="ease_out">Ease out</option></select></label>' +
        '<label class="animation-audio-director-enabled"><input data-cue-enabled type="checkbox"> Enabled</label></div>' +
        '<div class="animation-audio-director-actions"><button type="button" data-cue-update>Update selected</button>' +
        '<button type="button" data-cue-delete>Delete selected</button></div>' +
        '<div data-cue-list class="animation-audio-director-list"></div>' +
        '<details class="animation-audio-find-beats"><summary>Find Beats · Optional batch cues</summary>' +
        '<div class="animation-audio-beat-grid">' +
        '<label>Find<select data-beat-kind><option value="kick">Kick</option><option value="snare">Snare</option><option value="highs">Highs</option></select></label>' +
        '<label>Minimum strength<input data-beat-strength type="number" min="0" max="1" step=".05" value=".35"></label>' +
        '<label>Min gap (s)<input data-beat-gap type="number" min="0" max="2" step=".025" value=".1"></label>' +
        '<label>From (s)<input data-beat-start type="number" min="0" step=".1" value="0"></label>' +
        '<label>To (s)<input data-beat-end type="number" min="0" step=".1"></label>' +
        '<label>Every Nth hit<input data-beat-every type="number" min="1" max="16" step="1" value="1"></label>' +
        '<label>Motion preset<select data-beat-preset></select></label>' +
        '<label class="animation-audio-beat-check"><input data-beat-alternate type="checkbox"> Alternate right/left rolls</label></div>' +
        '<div class="animation-audio-director-actions"><button type="button" data-beat-preview>Preview matches</button>' +
        '<button type="button" data-beat-assign>Assign cues to matches</button>' +
        '<button type="button" data-beat-undo disabled>Undo batch</button></div>' +
        '<p data-beat-summary class="muted">Review candidate hits before assigning.</p></details>' +
        '<p class="muted">Cues save with this WAV. Save cues, then Preview camera cues or Apply camera cues. Existing Motion Lab layers remain additive.</p>';
      waveform.after(panel);
      const options = panel.querySelector('[data-cue-preset]');
      for (const [key,label] of MOTION_DIRECTOR_PRESETS) {
        const option = document.createElement('option');
        option.value = key; option.textContent = label; options.appendChild(option);
      }
      const beatOptions=panel.querySelector('[data-beat-preset]');
      for (const [key,label] of MOTION_DIRECTOR_PRESETS) {
        const option=document.createElement('option');option.value=key;
        option.textContent=label;beatOptions.appendChild(option);
      }
      panel.querySelector('[data-beat-preview]').addEventListener('click',()=>{
        motionDirectorPreviewMatches=true;motionDirectorFindStatus();motionLabStereoWaveform();
      });
      panel.querySelector('[data-beat-assign]').addEventListener('click',motionDirectorAssignBeats);
      panel.querySelector('[data-beat-undo]').addEventListener('click',()=>{
        if (!motionDirectorBulkUndo) return;
        motionDirectorCues=motionDirectorBulkUndo;motionDirectorBulkUndo=null;
        motionDirectorDirty=true;motionDirectorPanel();motionLabStereoWaveform();
      });
      panel.querySelector('[data-cue-add]').addEventListener('click', () => {
        const time = Math.max(0,Math.min(motionLabAudioAnalysis.duration_seconds-.000001,
          Number(motionLabAudioElement?.currentTime)||0));
        const id = 'cue-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2,9);
        const cue = {id,preset:'push_zoom_in',time_seconds:time,duration_seconds:.6,
          intensity:.5,easing:'ease_in_out',enabled:true,source_event_id:null};
        motionDirectorCues.push(cue);motionDirectorSelected=id;motionDirectorDirty=true;
        motionDirectorPanel();motionLabStereoWaveform();
      });
      panel.querySelector('[data-cue-update]').addEventListener('click', () => {
        const cue = motionDirectorCues.find(c => c.id === motionDirectorSelected);
        if (!cue) return;
        const time = Number(panel.querySelector('[data-cue-time]').value);
        const duration = Number(panel.querySelector('[data-cue-duration]').value);
        const intensity = Number(panel.querySelector('[data-cue-intensity]').value);
        if (![time,duration,intensity].every(Number.isFinite) || time<0 ||
            time>=motionLabAudioAnalysis.duration_seconds || duration<.01 ||
            duration>30 || intensity<0 || intensity>1) {
          motionLabNotify('Cue timing or intensity is outside allowed limits.');return;
        }
        Object.assign(cue,{preset:panel.querySelector('[data-cue-preset]').value,
          time_seconds:time,duration_seconds:duration,intensity,
          easing:panel.querySelector('[data-cue-easing]').value,
          enabled:panel.querySelector('[data-cue-enabled]').checked});
        motionDirectorDirty=true;motionDirectorPanel();motionLabStereoWaveform();
      });
      panel.querySelector('[data-cue-delete]').addEventListener('click', () => {
        motionDirectorCues=motionDirectorCues.filter(c=>c.id!==motionDirectorSelected);
        motionDirectorSelected=null;motionDirectorDirty=true;motionDirectorPanel();motionLabStereoWaveform();
      });
      const stageCues = (apply) => {
        const project=state.project;
        if (!project || motionLabAudioProjectId !== project.id || motionLabBusy) {
          motionLabNotify('Open and analyze the project WAV first.');return;
        }
        if (motionDirectorDirty) {
          motionLabNotify('Save camera cues first, then preview or apply them.');return;
        }
        if (!motionDirectorCues.some(c=>c.enabled && c.intensity>0)) {
          motionLabNotify('Add an enabled camera cue first.');return;
        }
        const frames=Number(project.animation?.max_frames);
        if (!Number.isInteger(frames) || frames<1 || frames>3000) return;
        const cueDocument={
          source_sha256:motionLabAudioAnalysis.source_sha256,
          duration_seconds:motionLabAudioAnalysis.duration_seconds,
          cues:motionDirectorCues.map(c=>({...c})),
        };
        const id='director-'+cueDocument.source_sha256.slice(0,24);
        const replacement={
          id,type:'audio_cues',enabled:true,blend:'add',
          start_frame:0,end_frame:frames,sha256:cueDocument.source_sha256,
          name:'Audio Motion Director',cue_document:cueDocument,
        };
        const existing=motionLabDraftLayers.findIndex(l=>l.id===id);
        if (existing<0 && motionLabDraftLayers.length>=24) {
          motionLabNotify('Motion Lab supports a maximum of 24 layers.');return;
        }
        if (existing>=0) motionLabDraftLayers[existing]=replacement;
        else motionLabDraftLayers.push(replacement);
        commitMotionLabDraft();
        void motionLabPreviewOrApply(apply,{curvesOnly:false});
      };
      panel.querySelector('[data-cue-preview]').addEventListener('click',()=>stageCues(false));
      panel.querySelector('[data-cue-apply]').addEventListener('click',async()=>{
        const approved=await window.MorphorumDialog.confirm({
          title:'Apply Audio Motion Director cues?',
          message:'Replace this source\'s existing Director layer with the saved cues and apply native six-axis camera schedules to this project? Other Motion Lab layers remain in the draft.',
          confirmText:'Apply Camera Cues',cancelText:'Cancel',variant:'default',
        });
        if (approved) stageCues(true);
      });
      panel.querySelector('[data-cue-save]').addEventListener('click', async () => {
        const projectId=state.project?.id;
        if (!projectId || motionLabAudioProjectId!==projectId) return;
        const save=panel.querySelector('[data-cue-save]');save.disabled=true;
        try {
          const response=await api('/api/animation/projects/'+encodeURIComponent(projectId)+
            '/motion-lab/audio-cues',{method:'PUT',body:JSON.stringify({
              source_sha256:motionLabAudioAnalysis.source_sha256,
              duration_seconds:motionLabAudioAnalysis.duration_seconds,cues:motionDirectorCues,
            })});
          if (!response?.cues) throw new Error('Cue save not confirmed.');
          motionDirectorCues=response.cues.cues;motionDirectorDirty=false;
          motionLabNotify('Camera cues saved with this WAV.');
        } catch(error) {motionLabNotify('Cue save failed: '+(error?.message||error));}
        finally {save.disabled=false;motionDirectorPanel();}
      });
      panel.querySelector('[data-cue-list]').addEventListener('click', event => {
        const button=event.target.closest('[data-cue-id]');
        if (!button) return;
        motionDirectorSelected=button.dataset.cueId;
        const cue=motionDirectorCues.find(c=>c.id===motionDirectorSelected);
        if (cue && motionLabAudioElement) motionLabAudioElement.currentTime=cue.time_seconds;
        motionDirectorPanel();
      });
    }
    const beatEnd=panel.querySelector('[data-beat-end]');
    if (beatEnd && !beatEnd.value) beatEnd.value=motionLabAudioAnalysis.duration_seconds.toFixed(3);
    motionDirectorFindStatus();
    const selected=motionDirectorCues.find(c=>c.id===motionDirectorSelected);
    for (const [attr,key] of [['data-cue-preset','preset'],['data-cue-time','time_seconds'],
        ['data-cue-duration','duration_seconds'],['data-cue-intensity','intensity'],
        ['data-cue-easing','easing']]) {
      const input=panel.querySelector('['+attr+']');
      input.disabled=!selected;
      input.value=selected?String(selected[key]):'';
    }
    const enabled=panel.querySelector('[data-cue-enabled]');
    enabled.disabled=!selected;enabled.checked=Boolean(selected?.enabled);
    for (const attr of ['data-cue-update','data-cue-delete'])
      panel.querySelector('['+attr+']').disabled=!selected;
    const status=panel.querySelector('[data-cue-status]');
    status.textContent=motionDirectorCues.length+' cues'+(motionDirectorDirty?' · Unsaved':' · Saved');
    for (const kind of ['data-cue-preview','data-cue-apply'])
      panel.querySelector('['+kind+']').disabled=motionDirectorDirty || !motionDirectorCues.length || motionLabBusy;
    const list=panel.querySelector('[data-cue-list]');list.replaceChildren();
    for (const cue of [...motionDirectorCues].sort((a,b)=>a.time_seconds-b.time_seconds)) {
      const button=document.createElement('button');button.type='button';
      button.className='animation-audio-cue-item'+(cue.id===motionDirectorSelected?' active':'');
      button.dataset.cueId=cue.id;
      button.textContent=cue.time_seconds.toFixed(3)+'s · '+
        (MOTION_DIRECTOR_PRESETS.find(p=>p[0]===cue.preset)?.[1]||cue.preset)+
        (cue.enabled?'':' (disabled)');
      list.appendChild(button);
    }
  }
  function motionLabStereoWaveform() {
    const preview = qs('#animation-motion-lab-audio-preview');
    const analysis = motionLabAudioAnalysis;
    if (!preview) return;
    let section = qs('#animation-audio-stereo-timeline');
    if (!analysis?.waveform?.channels?.length) {
      if (section) section.hidden = true;
      const editor = qs('#animation-audio-event-editor');
      if (editor) editor.hidden = true;
      const director = qs('#animation-audio-motion-director');
      if (director) director.hidden = true;
      return;
    }
    if (section) section.hidden = false;
    const editor = qs('#animation-audio-event-editor');
    if (editor) editor.hidden = false;
    if (!section) {
      section = document.createElement('section');
      section.id = 'animation-audio-stereo-timeline';
      section.className = 'animation-audio-stereo-timeline';
      section.innerHTML = '<div class="animation-audio-wave-controls"><strong>Audio reference · Events</strong>' +
        '<label class="animation-audio-wave-mode">Display <select data-wave-mode>' +
        '<option value="envelope">Envelope + markers</option>' +
        '<option value="stereo">Stereo waveform</option>' +
        '<option value="both">Envelope + stereo</option></select></label>' +
        '<label>Zoom <input type="range" min="1" max="12" value="1" step="1" data-wave-zoom></label>' +
        '<label>Pan <input type="range" min="0" max="1000" value="0" step="1" data-wave-start></label>' +
        '<label class="animation-audio-wave-follow"><input type="checkbox" data-wave-follow checked> Follow playhead</label></div>' +
        '<div class="animation-audio-wave-transport"><button type="button" data-wave-play>Play audio</button>' +
        '<output data-wave-time>0.00 / 0.00 s</output><span>Click or tap the waveform to seek</span></div>' +
        '<svg data-wave-svg viewBox="0 0 800 180" role="img" tabindex="0" aria-label="Audio waveform with editable kick and snare events"></svg>' +
        '<div class="animation-audio-ruler"><span data-wave-left-time>0.00s</span><span data-wave-right-time>0.00s</span></div>' +
        '<p class="muted" data-wave-description></p>';
      const workspace = qs('#animation-audio-analysis-workspace');
      const diagnostics = workspace?.querySelector('.animation-audio-legacy-envelope');
      if (workspace && diagnostics) diagnostics.before(section);
      else preview.before(section);
      const editor = document.createElement('div');
      editor.id = 'animation-audio-event-editor';
      editor.className = 'animation-audio-event-editor';
      editor.innerHTML = '<div class="animation-audio-event-heading"><strong>Event detection & marker editing</strong>' +
        '<span class="muted">Drag a marker to move · double-click empty waveform to add · Shift-click marker to remove</span></div>' +
        '<p data-event-selected>Select a marker on the waveform to edit it</p>' +
        '<div class="animation-audio-event-fields">' +
        '<label>Time (seconds)<input type="number" min="0" step="0.001" data-event-time disabled></label>' +
        '<label>Type<select data-event-kind disabled><option value="kick">Kick</option>' +
        '<option value="snare">Snare</option><option value="highs">Highs</option></select></label>' +
        '<label class="animation-audio-event-checkbox"><input type="checkbox" data-event-enabled disabled> Enabled</label></div>' +
        '<div class="animation-audio-event-actions"><button type="button" data-event-save>Update marker</button>' +
        '<button type="button" data-event-add>Add at playhead</button>' +
        '<button type="button" data-event-remove disabled>Remove marker</button>' +
        '<button type="button" data-event-undo disabled>Undo</button>' +
        '<button type="button" data-event-redo disabled>Redo</button>' +
        '<button type="button" data-event-reset>Reset detections</button>' +
        '<button type="button" data-event-clear-detected>Clear all detected markers</button>' +
        '<button type="button" data-event-persist>Save marker edits</button></div>' +
        '<p data-event-count></p><p class="muted">Marker edits are stored with this WAV in the project. They do not change camera motion until a later phase.</p>';
      section.after(editor);
      editor.querySelector('[data-event-persist]')?.addEventListener('click', () => void motionLabSaveMarkers());
      editor.querySelector('[data-event-undo]')?.addEventListener('click', () => motionLabMarkerHistory(false));
      editor.querySelector('[data-event-redo]')?.addEventListener('click', () => motionLabMarkerHistory(true));
      for (const [attr, action] of [['data-event-save','update'],['data-event-add','add'],
        ['data-event-remove','remove'],['data-event-reset','reset'],
        ['data-event-clear-detected','clear-detected']]) {
        editor.querySelector('['+attr+']')?.addEventListener('click', () => motionLabEventChange(action));
      }
      const displayMode = section.querySelector('[data-wave-mode]');
      if (displayMode) displayMode.value = 'stereo';
      section.querySelector('[data-wave-mode]')?.addEventListener('change', motionLabStereoWaveform);
      section.querySelector('[data-wave-zoom]')?.addEventListener('input', motionLabStereoWaveform);
      section.querySelector('[data-wave-start]')?.addEventListener('input', () => {
        const follow = section.querySelector('[data-wave-follow]');
        if (follow) follow.checked = false; // manual navigation takes priority
        motionLabStereoWaveform();
      });
      section.querySelector('[data-wave-follow]')?.addEventListener('change', () => {
        motionLabStereoWaveform();
      });
      section.querySelector('[data-wave-play]')?.addEventListener('click', motionLabWaveToggle);
      const seekTo = ratio => {
        const audio = motionLabAudioElement;
        if (!audio || !motionLabAudioAnalysis) return;
        const begin = Number(section.dataset.waveStart || 0);
        const end = Number(section.dataset.waveEnd || 0);
        audio.currentTime = Math.max(0, Math.min(
          Number.isFinite(audio.duration) ? audio.duration : end,
          begin + Math.max(0, Math.min(1, ratio)) * (end - begin)));
        motionLabWavePlayhead();
      };
      let dragMarker = null;
      const waveform = section.querySelector('[data-wave-svg]');
      waveform?.addEventListener('dblclick', event => {
        const time = positionToTime(event);
        if (time === null || !motionLabEditedEvents) return;
        const begin = Number(section.dataset.waveStart || 0);
        const end = Number(section.dataset.waveEnd || 0);
        const rect = waveform.getBoundingClientRect();
        const closest = motionLabEditedEvents.some(e =>
          Math.abs(e.time_seconds-time) < (end-begin)*10/Math.max(1,rect.width));
        if (closest) return;
        motionLabMarkerSnapshot();
        const id = 'manual-' + String(Date.now()) + '-' + motionLabEditedEvents.length;
        motionLabEditedEvents.push({id,kind:'kick',time_seconds:Math.max(0,Math.min(
          motionLabAudioAnalysis.duration_seconds-.000001,Math.round(time*1000)/1000)),
          enabled:true,strength:1,source:'manual'});
        motionLabSelectedEvent = id;
        motionLabMarkersDirty = true;
        motionLabStereoWaveform();
      });
      const positionToTime = event => {
        const rect = waveform.getBoundingClientRect();
        if (!rect.width) return null;
        const ratio = Math.max(0,Math.min(1,(event.clientX-rect.left)/rect.width));
        const begin = Number(section.dataset.waveStart || 0);
        const end = Number(section.dataset.waveEnd || 0);
        return begin + ratio * (end - begin);
      };
      waveform?.addEventListener('pointerdown', event => {
        const cueHit=event.target.closest?.('[data-timeline-cue]');
        if (cueHit) {
          motionDirectorSelected=cueHit.getAttribute('data-timeline-cue');
          motionDirectorPanel();
          return;
        }
        if (event.button !== 0 || !motionLabEditedEvents?.length) return;
        const target = positionToTime(event);
        if (target === null) return;
        const rect = waveform.getBoundingClientRect();
        const tolerance = (Number(section.dataset.waveEnd)-Number(section.dataset.waveStart))
          * 12 / rect.width;
        const candidates = motionLabEditedEvents.filter(e => Math.abs(e.time_seconds-target) <= tolerance);
        candidates.sort((a,b)=>Math.abs(a.time_seconds-target)-Math.abs(b.time_seconds-target));
        if (!candidates.length) return;
        const selected = candidates[0];
        motionLabSelectedEvent = selected.id;
        dragMarker = {id:selected.id,startX:event.clientX,moved:false};
        waveform.setPointerCapture?.(event.pointerId);
        motionLabEventEditor();
      });
      waveform?.addEventListener('pointermove', event => {
        if (!dragMarker || !motionLabEditedEvents) return;
        if (Math.abs(event.clientX-dragMarker.startX) <= 4 && !dragMarker.moved) return;
        if (!dragMarker.moved) { motionLabMarkerSnapshot(); dragMarker.moved = true; }
        const target = positionToTime(event);
        const selected = motionLabEditedEvents.find(e=>e.id===dragMarker.id);
        if (target !== null && selected) {
          selected.time_seconds = Math.max(0,Math.min(
            motionLabAudioAnalysis.duration_seconds-.000001,Math.round(target*1000)/1000));
          motionLabMarkersDirty = true;
          // Redraw after pointer release to retain capture during drag.
          const x = (selected.time_seconds-Number(section.dataset.waveStart)) /
            Math.max(1e-9,Number(section.dataset.waveEnd)-Number(section.dataset.waveStart))*800;
          const marker = waveform.querySelector('[data-drag-preview]');
          if (marker) {marker.setAttribute('x1',x);marker.setAttribute('x2',x);}
          motionLabEventEditor();
        }
      });
      const finishDrag = event => {
        if (!dragMarker) return;
        const moved = dragMarker.moved;
        dragMarker = null;
        if (waveform.hasPointerCapture?.(event.pointerId)) waveform.releasePointerCapture(event.pointerId);
        if (moved) {section.dataset.waveSuppressClick='1'; motionLabStereoWaveform();}
      };
      waveform?.addEventListener('pointerup',finishDrag);
      waveform?.addEventListener('pointercancel',finishDrag);
      section.querySelector('[data-wave-svg]')?.addEventListener('click', event => {
        const cueHit=event.target.closest?.('[data-timeline-cue]');
        if (cueHit) {
          motionDirectorSelected=cueHit.getAttribute('data-timeline-cue');
          motionDirectorPanel(); return;
        }
        if (section.dataset.waveSuppressClick === '1') {
          delete section.dataset.waveSuppressClick;
          return;
        }
        const bounds = event.currentTarget.getBoundingClientRect();
        if (bounds.width <= 0) return;
        const ratio = Math.max(0, Math.min(1,(event.clientX - bounds.left) / bounds.width));
        const begin = Number(section.dataset.waveStart || 0);
        const end = Number(section.dataset.waveEnd || 0);
        const target = begin + ratio * (end - begin);
        const tolerance = (end - begin) * 12 / bounds.width;
        let closest = null;
        for (const candidate of motionLabEditedEvents || []) {
          const distance = Math.abs(candidate.time_seconds - target);
          if (distance <= tolerance && (!closest || distance < closest.distance)) {
            closest = {id:candidate.id,distance};
          }
        }
        if (closest) {
          motionLabSelectedEvent = closest.id;
          if (event.shiftKey) { motionLabEventChange('remove'); return; }
          motionLabStereoWaveform();
        } else {
          motionLabSelectedEvent = null;
          motionLabEventEditor();
          seekTo(ratio);
        }
      });
      section.querySelector('[data-wave-svg]')?.addEventListener('keydown', event => {
        if ((event.ctrlKey || event.metaKey) && (event.key.toLowerCase()==='z' ||
            event.key.toLowerCase()==='y')) {
          event.preventDefault();
          motionLabMarkerHistory(event.key.toLowerCase()==='y' || event.shiftKey);
          return;
        }
        const selected = motionLabEditedEvents?.find(e=>e.id===motionLabSelectedEvent);
        if (selected && (event.key==='Delete' || event.key==='Backspace')) {
          event.preventDefault(); motionLabEventChange('remove'); return;
        }
        if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return;
        event.preventDefault();
        if (selected) {
          motionLabMarkerSnapshot();
          const step = event.shiftKey ? 1/Math.max(1,Number(motionLabAudioAnalysis?.fps)||12) : .01;
          selected.time_seconds = Math.max(0,Math.min(
            motionLabAudioAnalysis.duration_seconds-.000001,
            Math.round((selected.time_seconds+(event.key==='ArrowRight'?step:-step))*1000000)/1000000));
          motionLabMarkersDirty = true;
          motionLabStereoWaveform();
          return;
        }
        const current = Number(motionLabAudioElement?.currentTime) || 0;
        const begin = Number(section.dataset.waveStart || 0);
        const end = Number(section.dataset.waveEnd || 0);
        seekTo((current - begin + (event.key === 'ArrowRight' ? .1 : -.1)) /
          Math.max(1e-9, end - begin));
      });
    }
    section.hidden = false;
    const channels = analysis.waveform.channels;
    const total = analysis.waveform.bins;
    const zoom = Number(section.querySelector('[data-wave-zoom]')?.value || 1);
    const startControl = section.querySelector('[data-wave-start]');
    const maxStart = Math.max(0, 1 - 1 / zoom);
    const from = Math.round(Number(startControl?.value || 0) / 1000 * maxStart * total);
    const to = Math.min(total, from + Math.max(1, Math.ceil(total / zoom)));
    const svg = section.querySelector('[data-wave-svg]');
    const ns = 'http://www.w3.org/2000/svg';
    svg.replaceChildren();
    const make = (tag, attributes) => {
      const el = document.createElementNS(ns, tag);
      for (const [k, v] of Object.entries(attributes)) el.setAttribute(k, String(v));
      svg.appendChild(el);
      return el;
    };
    const count = channels.length;
    const mode = section.querySelector('[data-wave-mode]')?.value || 'envelope';
    const height = count === 2 ? 64 : 120;
    if (mode !== 'envelope') channels.forEach((channel, index) => {
      const center = count === 2 ? 45 + index * 81 : 88;
      make('line', {x1:0,y1:center,x2:800,y2:center,stroke:'currentColor','stroke-opacity':'.16'});
      const d = [];
      for (let i = from; i < to; i++) {
        const x = (i - from) * 800 / Math.max(1,to-from);
        const pair = channel[i] || [0,0];
        d.push('M' + x.toFixed(2) + ' ' + (center - pair[1] * height/2).toFixed(2) +
          ' V' + (center - pair[0] * height/2).toFixed(2));
      }
      make('path', {d:d.join(' '),fill:'none',stroke:index?'#b49df3':'#73d5ed',
        'stroke-width':Math.max(.8,Math.min(2,800/(to-from))),'vector-effect':'non-scaling-stroke'});
      make('text', {x:5,y:center-25,fill:'currentColor','font-size':11}).textContent =
        count === 2 ? (index ? 'R' : 'L') : 'Mono';
    });
    if (mode !== 'stereo') {
      const values = motionLabAudioSignal();
      const fps = Number(analysis.fps) || 12;
      const startTime = from / total * analysis.duration_seconds;
      const endTime = to / total * analysis.duration_seconds;
      const peak = Math.max(.05,...values);
      const points = [];
      for (let i = 0; i < values.length; i++) {
        const time = (i + .5) / fps;
        if (time < startTime || time > endTime) continue;
        const x = (time - startTime) * 800 / Math.max(1e-9,endTime-startTime);
        const y = 164 - Math.max(0,values[i]) / peak * 140;
        points.push((points.length?'L':'M') + x.toFixed(2) + ' ' + y.toFixed(2));
      }
      if (points.length) make('path', {d:points.join(' '),fill:'none',
        stroke:'#73d5ed','stroke-width':2.4,'vector-effect':'non-scaling-stroke'});
      const gate = Math.max(0,Math.min(1,Number(qs('#animation-motion-lab-audio-threshold')?.value)||0));
      const y = 164 - gate / peak * 140;
      make('line',{x1:0,x2:800,y1:y,y2:y,stroke:'#ff857c',
        'stroke-width':1.5,'stroke-dasharray':'7 5'});
    }
    const tStart = from / total * analysis.duration_seconds;
    const tEnd = to / total * analysis.duration_seconds;
    section.dataset.waveStart = String(tStart);
    section.dataset.waveEnd = String(tEnd);
    const left = section.querySelector('[data-wave-left-time]');
    const right = section.querySelector('[data-wave-right-time]');
    if (left) left.textContent = tStart.toFixed(2) + 's · frame ' + Math.round(tStart*analysis.fps);
    if (right) right.textContent = tEnd.toFixed(2) + 's · frame ' + Math.round(tEnd*analysis.fps);
    const events = motionLabEditedEvents || analysis.events?.events || [];
    const candidateIds = motionDirectorPreviewMatches ?
      new Set(motionDirectorFindCandidates().map(e=>e.id)) : new Set();
    let visible = 0;
    for (const event of events) {
      if (event.time_seconds < tStart || event.time_seconds > tEnd) continue;
      const x = (event.time_seconds - tStart) * 800 / Math.max(1e-9,tEnd-tStart);
      make('line', {x1:x,y1:4,x2:x,y2:176,stroke:event.kind === 'kick'?'#ffba66':
        event.kind === 'snare'?'#f28fba':'#a0a0a0',
        'stroke-width':event.id===motionLabSelectedEvent?3:1.5,
        'stroke-opacity':event.enabled===false?'.2':'.85'});
      if (candidateIds.has(event.id)) {
        make('circle',{cx:x,cy:8,r:4,fill:'#6bebaf','pointer-events':'none'});
      }
      visible++;
    }
    // Explicit cue lane is separate from detected transient markers.
    const cueColors = {push_zoom_in:'#75d9b5',roll_right_left:'#c99cf2',
      roll_left_right:'#c99cf2',push_return:'#73d5ed',dolly_out:'#73d5ed',
      shake:'#ffb76b',ripple:'#ff96bd',reveal_drift:'#a8d4f5',
      fly_through:'#75d9b5'};
    for (const cue of motionDirectorCues) {
      if (cue.time_seconds < tStart || cue.time_seconds > tEnd) continue;
      const x=(cue.time_seconds-tStart)*800/Math.max(1e-9,tEnd-tStart);
      const band=make('rect',{x:Math.max(0,x-5),y:153,width:11,height:22,rx:2,
        fill:cueColors[cue.preset]||'#fff','fill-opacity':cue.enabled?'.96':'.35',
        'data-timeline-cue':cue.id,role:'button',
        'aria-label':'Motion cue '+cue.preset+' at '+cue.time_seconds.toFixed(3)+' seconds',
        stroke:cue.id===motionDirectorSelected?'#fff':'none','stroke-width':2});
      const tip=document.createElementNS(ns,'title');
      tip.textContent=cue.preset.replaceAll('_',' ')+' · '+cue.time_seconds.toFixed(3)+'s';
      band.appendChild(tip);
    }
    make('line', {x1:0,x2:0,y1:0,y2:180,stroke:'#ffed81','stroke-width':3,
      'vector-effect':'non-scaling-stroke','pointer-events':'none',
      visibility:'hidden','data-drag-preview':''});
    make('line', {x1:0,x2:0,y1:0,y2:180,stroke:'#fff','stroke-width':2,
      'vector-effect':'non-scaling-stroke','pointer-events':'none',
      visibility:'hidden','data-wave-playhead':''});
    motionLabWavePlayhead();
    motionLabEventEditor();
    const desc = section.querySelector('[data-wave-description]');
    if (desc) desc.textContent = (mode === 'envelope'?'Frame-aligned energy envelope':
      mode === 'both'?'Envelope over separate L/R channels':
      count === 2?'Separate L/R channels':'Mono channel') +
      ' · ' + tStart.toFixed(2) + '–' + tEnd.toFixed(2) + ' s · ' + visible +
      ' attack candidates in view (orange kick, pink snare, gray highs). ' +
      'Markers represent spectral candidates, not isolated instruments.';
  }
  // MS4.1: continuous motion arrangement uses canonical native preset layers
  // and the existing Motion Lab draft history/preview/apply infrastructure.
  const MOTION_STUDIO_CONTINUOUS_PRESETS = [
    ['gentle-drift', 'Gentle Drift'], ['wave', 'Wave'],
    ['spiral', 'Spiral'], ['figure-eight', 'Figure Eight'],
    ['rocking', 'Rocking'], ['push-in', 'Push In'], ['pull-out', 'Pull Out'],
    ['still', 'Still / Clear Selected Axes'],
  ];
  const MOTION_STUDIO_PRESET_AXES = {
    'gentle-drift':['translation_x','translation_y','rotation_y'],
    'wave':['translation_x','translation_y','rotation_y'],
    'spiral':['translation_x','translation_y','translation_z','rotation_z'],
    'figure-eight':['translation_x','translation_y'],
    'rocking':['rotation_x','rotation_z'],
    'push-in':['translation_z'],'pull-out':['translation_z'],
    'still':['translation_x','translation_y','translation_z',
      'rotation_x','rotation_y','rotation_z'],
  };
  const MOTION_STUDIO_AXIS_NAMES = {
    translation_x:'Move X',translation_y:'Move Y',translation_z:'Move Z',
    rotation_x:'Pitch',rotation_y:'Yaw',rotation_z:'Roll',
  };
  let motionStudioArrangementProjectId = '';
  let motionStudioArrangementSelection = '';
  let motionStudioArrangementLoaded = '';
  let motionStudioArrangementSerial = 0;
  const MS43_URL = '/api/animation/motion-studio/custom-presets';
  let ms43Presets = [];
  let ms43Busy = false;

  function motionStudioArrangementFrameCount() {
    return Math.max(1, Number(state.project?.animation?.max_frames) || 120);
  }
  function motionStudioArrangementFps() {
    return Math.max(1, Number(state.project?.animation?.fps) || 24);
  }
  function motionStudioArrangementActiveLayer() {
    return motionLabDraftLayers.find(layer =>
      layer.type !== 'audio' && layer.type !== 'audio_cues' &&
      layer.type !== 'audio_channels' && layer.type !== 'recording' &&
      layer.type !== 'keyframes' &&
      layer.id === motionStudioArrangementSelection &&
      MOTION_STUDIO_CONTINUOUS_PRESETS.some(([id]) => id === layer.preset)) || null;
  }
  function motionStudioArrangementFields() {
    const panel = qs('#animation-motion-studio-arrangement');
    return panel ? {
      panel,
      preset:panel.querySelector('[data-ms4-preset]'),
      strength:panel.querySelector('[data-ms4-strength]'),
      cycle:panel.querySelector('[data-ms4-cycle]'),
      fade:panel.querySelector('[data-ms4-fade]'),
      start:panel.querySelector('[data-ms4-start]'),
      end:panel.querySelector('[data-ms4-end]'),
      startSlide:panel.querySelector('[data-ms4-start-slide]'),
      endSlide:panel.querySelector('[data-ms4-end-slide]'),
      blend:panel.querySelector('[data-ms4-blend]'),
      axes:panel.querySelector('[data-ms4-axes]'),
    } : null;
  }
  function motionStudioArrangementResetFields() {
    const fields = motionStudioArrangementFields();
    if (!fields) return;
    const count = motionStudioArrangementFrameCount();
    fields.preset.value = 'wave';
    fields.blend.value = 'add';
    motionStudioArrangementRebuildAxes();
    fields.strength.value = '.65';
    fields.cycle.value = '2';
    fields.fade.value = '.1';
    fields.start.value = '0';
    fields.end.value = String(count);
    motionStudioArrangementSyncRange('start');
  }
  function motionStudioArrangementRebuildAxes(selectedAxes = null) {
    const fields = motionStudioArrangementFields();
    if (!fields?.axes) return;
    const available = MOTION_STUDIO_PRESET_AXES[fields.preset.value] || [];
    // Only auto-reset on a new preset; editing blend keeps checked axes.
    const old = selectedAxes || Array.from(fields.axes.querySelectorAll('input:checked'))
      .map(item=>item.value);
    fields.axes.replaceChildren();
    for (const axis of available) {
      const label = document.createElement('label');
      const input = document.createElement('input');
      input.type = 'checkbox';
      input.value = axis;
      input.checked = selectedAxes === null
        ? (old.length ? old.includes(axis) : true)
        : selectedAxes.includes(axis);
      input.dataset.ms4Axis = axis;
      label.append(input,document.createTextNode(MOTION_STUDIO_AXIS_NAMES[axis]));
      fields.axes.appendChild(label);
    }
    if (fields.preset.value === 'still' && fields.blend.value === 'add')
      fields.blend.value = 'replace';
    motionStudioArrangementShowBlendHelp();
  }
  function motionStudioArrangementShowBlendHelp() {
    const fields = motionStudioArrangementFields();
    if (!fields) return;
    const help = fields.panel.querySelector('[data-ms4-blend-help]');
    if (help) help.textContent = fields.blend.value === 'replace'
      ? 'Replace resets only the checked camera axes during the selected frame range. Other axes and frames keep their existing motion. Later layers still apply in layer order.'
      : 'Add layers movement onto the checked axes without discarding earlier motion. Change the order in Camera Motion Composer.';
  }
  function motionStudioArrangementAxisSelection() {
    const fields = motionStudioArrangementFields();
    return Array.from(fields?.axes?.querySelectorAll('input:checked') || [])
      .map(input => input.value);
  }
  function motionStudioArrangementSyncRange(edited = '') {
    const fields = motionStudioArrangementFields();
    if (!fields) return;
    const count = motionStudioArrangementFrameCount();
    let start = Number(fields.start.value);
    let end = Number(fields.end.value);
    if (!Number.isFinite(start)) start = 0;
    if (!Number.isFinite(end)) end = count;
    start = Math.max(0, Math.min(count - 1, Math.round(start)));
    end = Math.max(1, Math.min(count, Math.round(end)));
    if (start >= end) {
      if (edited === 'start') end = Math.min(count, start + 1);
      else start = Math.max(0, end - 1);
    }
    fields.start.value = String(start);
    fields.end.value = String(end);
    fields.startSlide.min = '0';
    fields.startSlide.max = String(count - 1);
    fields.endSlide.min = '1';
    fields.endSlide.max = String(count);
    fields.startSlide.value = String(start);
    fields.endSlide.value = String(end);
    const readout = fields.panel.querySelector('[data-ms4-range-label]');
    if (readout) {
      const fps = motionStudioArrangementFps();
      readout.textContent = 'Frames ' + start + '–' + (end - 1) +
        ' · ' + (start/fps).toFixed(2) + '–' + (end/fps).toFixed(2) +
        ' seconds · ' + (end-start) + ' frames';
    }
    motionStudioArrangementRenderTimeline();
  }
  function motionStudioArrangementSelect(id) {
    const layer = motionLabDraftLayers.find(item => item.id === id &&
      (item.type === 'preset' || !item.type) &&
      MOTION_STUDIO_CONTINUOUS_PRESETS.some(([key]) => key === item.preset));
    motionStudioArrangementSelection = layer?.id || '';
    motionStudioArrangementLoaded = '';
    motionStudioRenderArrangement();
  }
  function motionStudioArrangementRemove(id) {
    if (!state.project || animationMode() !== '3d' || motionLabBusy) return;
    const index = motionLabDraftLayers.findIndex(item =>
      item.id === id && (item.type === 'preset' || !item.type) &&
      MOTION_STUDIO_CONTINUOUS_PRESETS.some(([key]) => key === item.preset));
    if (index < 0) return;
    const [removed] = motionLabDraftLayers.splice(index, 1);
    if (motionStudioArrangementSelection === id) {
      motionStudioArrangementSelection = '';
      motionStudioArrangementLoaded = '';
      motionStudioArrangementResetFields();
    }
    commitMotionLabDraft();
    motionLabNotify('Removed ' + removed.preset.replaceAll('-', ' ') +
      ' from the motion draft. Apply to Animation to save the removal.');
    toast('Movement removed',
      'Removed from the draft. Undo is available in Camera Motion Composer.', 'success');
  }
  function motionStudioArrangementSeek(frame) {
    const audio = motionLabAudioElement;
    if (!audio || motionLabAudioProjectId !== state.project?.id) return;
    const seconds = Math.max(0, Math.min(
      (motionStudioArrangementFrameCount()-1) / motionStudioArrangementFps(),
      Number(frame) / motionStudioArrangementFps()));
    if (Number.isFinite(seconds)) audio.currentTime = seconds;
    motionStudioArrangementPlayhead();
  }
  function motionStudioArrangementPlayhead() {
    const panel = qs('#animation-motion-studio-arrangement');
    if (!panel) return;
    const available = Boolean(motionLabAudioElement &&
      motionLabAudioProjectId === state.project?.id);
    const count = motionStudioArrangementFrameCount();
    const position = available
      ? Math.max(0, Math.min(count-1, Number(motionLabAudioElement.currentTime || 0) *
        motionStudioArrangementFps())) : 0;
    const playhead = panel.querySelector('[data-ms4-playhead]');
    if (playhead) {
      playhead.style.left = (100 * position/count).toFixed(3) + '%';
      playhead.hidden = !available;
    }
    const seek = panel.querySelector('[data-ms4-seek]');
    if (seek) {
      if (document.activeElement !== seek) seek.value = String(Math.round(position));
      seek.disabled = !available;
    }
    const status = panel.querySelector('[data-ms4-playback-status]');
    if (status) status.textContent = available
      ? (position/motionStudioArrangementFps()).toFixed(2) + 's / ' +
        (count/motionStudioArrangementFps()).toFixed(2) + 's'
      : 'Load a WAV or attached soundtrack for synchronized seeking.';
  }
  function motionStudioArrangementRenderTimeline() {
    const panel = qs('#animation-motion-studio-arrangement');
    const lanes = panel?.querySelector('[data-ms4-lanes]');
    if (!lanes) return;
    lanes.replaceChildren();
    const count = motionStudioArrangementFrameCount();
    const fps = motionStudioArrangementFps();
    const ruler = panel.querySelector('[data-ms4-ruler]');
    if (ruler) ruler.textContent = '0.00s    ·    ' +
      (count/2/fps).toFixed(2) + 's    ·    ' + (count/fps).toFixed(2) +
      's (project end, ' + count + ' frames @ ' + fps + ' FPS)';
    const seek = panel.querySelector('[data-ms4-seek]');
    if (seek) seek.max = String(count - 1);
    const layers = motionLabDraftLayers.filter(l => l.type === 'preset' ||
      (!l.type && MOTION_STUDIO_CONTINUOUS_PRESETS.some(([id]) => id === l.preset)));
    const addLane = (label, start, end, selected, id, enabled, editable = true) => {
      const row = document.createElement('div');
      row.className = 'motion-studio-arrangement-lane';
      const title = document.createElement('span');
      title.className = 'motion-studio-arrangement-label';
      title.textContent = label;
      const track = document.createElement('div');
      track.className = 'motion-studio-arrangement-track';
      const bar = document.createElement('button');
      bar.type = 'button';
      bar.className = 'motion-studio-arrangement-bar';
      if (selected) bar.classList.add('selected');
      if (!enabled) bar.classList.add('disabled');
      bar.style.left = (100 * Math.max(0, Math.min(count,start)) / count).toFixed(3) + '%';
      bar.style.width = (100 * Math.max(1, Math.min(count,end)-start) / count).toFixed(3) + '%';
      bar.textContent = start + '–' + (end-1);
      bar.title = label + ': frame ' + start + ' through ' + (end-1) +
        '. Select to edit.';
      bar.setAttribute('aria-label',bar.title);
      if (editable) bar.addEventListener('click', () => motionStudioArrangementSelect(id));
      else {
        bar.disabled = true;
        bar.title += ' This layer uses Replace; edit in Camera Motion Composer.';
      }
      track.appendChild(bar);
      row.append(title,track);
      if (editable) {
        const remove = document.createElement('button');
        remove.type = 'button';
        remove.className = 'secondary-button compact motion-studio-arrangement-remove';
        remove.textContent = 'Remove';
        remove.title = 'Remove this staged movement from the draft (Undo available)';
        remove.setAttribute('aria-label', 'Remove ' + label +
          ', frames ' + start + ' through ' + (end-1));
        remove.disabled = !state.project || animationMode() !== '3d' || motionLabBusy;
        remove.addEventListener('click', () => motionStudioArrangementRemove(id));
        row.appendChild(remove);
      }
      lanes.appendChild(row);
    };
    for (const layer of layers) {
      const editable = MOTION_STUDIO_CONTINUOUS_PRESETS.some(([key]) => key === layer.preset);
      addLane((layer.preset || 'preset').replaceAll('-',' ') +
        (layer.enabled === false ? ' (disabled)' : '') +
        ' · ' + (layer.blend || 'add') +
        (!editable ? ' (Camera Composer)' : ''),
        Number(layer.start_frame),Number(layer.end_frame),
        layer.id === motionStudioArrangementSelection,
        layer.id,layer.enabled !== false,editable);
    }
    // The input range is a form draft, not a real layer. Never show a phantom
    // "Unstaged selection" lane that cannot be selected or removed.
    const caption = panel.querySelector('[data-ms4-lane-status]');
    if (caption) caption.textContent = layers.length
      ? layers.length + ' staged continuous movement(s) in the Motion Lab draft. ' +
        'Select a bar to edit or Remove it. Other layer types are preserved.'
      : 'No staged movements. Choose a preset and click + Stage Movement to add one.';
    motionStudioArrangementPlayhead();
  }
  function motionStudioRenderArrangement() {
    const fields = motionStudioArrangementFields();
    if (!fields) return;
    const {panel} = fields;
    const projectId = state.project?.id || '';
    if (motionStudioArrangementProjectId !== projectId) {
      motionStudioArrangementProjectId = projectId;
      motionStudioArrangementSelection = '';
      motionStudioArrangementLoaded = '';
      motionStudioArrangementResetFields();
    }
    const active = motionStudioArrangementActiveLayer();
    if (!active && motionStudioArrangementSelection) {
      motionStudioArrangementSelection = '';
      motionStudioArrangementLoaded = '';
    }
    if (active && active.id !== motionStudioArrangementLoaded) {
      fields.preset.value = active.preset;
      fields.blend.value = active.blend || 'add';
      motionStudioArrangementRebuildAxes(
        Array.isArray(active.axes) ? active.axes : MOTION_STUDIO_PRESET_AXES[active.preset]);
      fields.strength.value = String(active.strength);
      fields.cycle.value = String(active.cycle_seconds);
      fields.fade.value = String(active.fade_seconds);
      fields.start.value = String(active.start_frame);
      fields.end.value = String(active.end_frame);
      motionStudioArrangementLoaded = active.id;
    }
    const ready = Boolean(state.project && animationMode() === '3d' && !motionLabBusy);
    for (const key of ['stage','preview','apply','new']) {
      const button = panel.querySelector('[data-ms4-'+key+']');
      if (button) button.disabled = !ready ||
        (key !== 'new' && !active && motionLabDraftLayers.length >= 24);
    }
    for (const input of panel.querySelectorAll('input,select')) {
      if (input.hasAttribute('data-ms4-seek')) continue;
      input.disabled = !ready;
    }
    const action = panel.querySelector('[data-ms4-stage]');
    if (action) action.textContent = active ? 'Update Selected Layer' : '+ Stage Movement';
    const badge = panel.querySelector('[data-ms4-status]');
    if (badge) badge.textContent = !projectId ? 'Open a project' :
      !ready ? 'Choose a 3D project to edit continuous motion' :
      active ? 'Editing ' + active.preset.replaceAll('-',' ') +
        ' · changes are only a draft until applied' :
      'Compose a new continuous motion region';
    motionStudioArrangementSyncRange();
    ms43Controls();
  }

  // Reusable named presets live in Morphorum's data directory, not the project.
  const ms43El = key => qs('#animation-motion-studio-arrangement')
    ?.querySelector('[data-ms43-' + key + ']');
  const ms43Selected = () => ms43Presets.find(p => p.id === ms43El('library')?.value);
  function ms43Status(message) {
    if (ms43El('status')) ms43El('status').textContent = message;
  }
  function ms43Controls() {
    const ready = !!state.project && animationMode() === '3d' && !motionLabBusy && !ms43Busy;
    for (const key of ['load','update','delete','save']) {
      const control = ms43El(key);
      if (control) control.disabled = !ready || (key !== 'save' && !ms43Selected());
    }
    if (ms43El('refresh')) ms43El('refresh').disabled = ms43Busy;
    if (ms43El('library')) ms43El('library').disabled = ms43Busy;
    if (ms43El('name')) ms43El('name').disabled = !ready;
  }
  function ms43RenderLibrary(selected = '') {
    const control = ms43El('library');
    if (!control) return;
    const old = selected || control.value;
    control.replaceChildren();
    const blank = document.createElement('option');
    blank.value = '';
    blank.textContent = 'Choose saved preset';
    control.appendChild(blank);
    for (const item of ms43Presets) {
      const option = document.createElement('option');
      option.value = item.id;
      option.textContent = item.name + ' · ' + item.preset.replaceAll('-',' ');
      control.appendChild(option);
    }
    control.value = ms43Presets.some(item => item.id === old) ? old : '';
    ms43Controls();
  }
  async function ms43Refresh(selected = '') {
    if (ms43Busy) return;
    ms43Busy = true;
    ms43Controls();
    ms43Status('Loading saved presets…');
    try {
      const data = await api(MS43_URL);
      ms43Presets = Array.isArray(data.presets) ? data.presets : [];
      ms43RenderLibrary(selected);
      ms43Status(ms43Presets.length + ' saved custom presets on this Morphorum installation.');
    } catch (error) {
      ms43Status('Could not load preset library: ' + error.message);
      toast('Preset library unavailable', error.message, 'error');
    } finally {
      ms43Busy = false;
      ms43Controls();
    }
  }
  function ms43Select() {
    if (ms43Selected()) ms43El('name').value = ms43Selected().name;
    ms43Controls();
  }
  function ms43Load() {
    const p = ms43Selected(), f = motionStudioArrangementFields();
    if (!p || !f || ms43Busy || !state.project || animationMode() !== '3d' || motionLabBusy) return;
    const count = motionStudioArrangementFrameCount();
    const start = Math.max(0, Math.min(count-1, Math.round(p.start_ratio*count)));
    const end = Math.max(start+1, Math.min(count, Math.round(p.end_ratio*count)));
    motionStudioArrangementSelection = '';
    motionStudioArrangementLoaded = '';
    f.preset.value = p.preset;
    f.blend.value = p.blend;
    motionStudioArrangementRebuildAxes(p.axes);
    f.strength.value = String(p.strength);
    f.cycle.value = String(p.cycle_seconds);
    f.fade.value = String(p.fade_seconds);
    f.start.value = String(start);
    f.end.value = String(end);
    motionStudioRenderArrangement();
    ms43Status('Loaded "' + p.name + '" into editor. Stage Movement to add it to this project.');
    toast('Custom preset loaded', p.name + ' is ready to stage.', 'success');
  }
  function ms43Payload() {
    const f = motionStudioArrangementFields();
    if (!f) return null;
    motionStudioArrangementSyncRange();
    const count = motionStudioArrangementFrameCount();
    return {name:ms43El('name')?.value.trim() || '',
      preset:f.preset.value, blend:f.blend.value,
      axes:motionStudioArrangementAxisSelection(),
      strength:Number(f.strength.value), cycle_seconds:Number(f.cycle.value),
      fade_seconds:Number(f.fade.value),
      start_ratio:Number(f.start.value)/count,
      end_ratio:Number(f.end.value)/count};
  }
  async function ms43Save(update = false) {
    if (ms43Busy || !state.project || animationMode() !== '3d' || motionLabBusy) return;
    const original = update ? ms43Selected() : null;
    if (update && !original) return;
    const payload = ms43Payload();
    if (!payload?.name || payload.name.length > 64) {
      toast('Preset name required', 'Enter a name of up to 64 characters.', 'warning');
      return;
    }
    ms43Busy = true;
    ms43Controls();
    ms43Status(update ? 'Updating saved preset…' : 'Saving new preset…');
    try {
      const result = await api(MS43_URL +
        (update ? '/' + encodeURIComponent(original.id) : ''), {
        method:update?'PUT':'POST', body:JSON.stringify(payload),
      });
      const list = await api(MS43_URL);
      ms43Presets = Array.isArray(list.presets) ? list.presets : [];
      ms43RenderLibrary(result.preset.id);
      ms43Status('Saved "'+result.preset.name+'". Project layers were not changed.');
      toast('Custom preset saved', result.preset.name + ' is reusable across projects.', 'success');
    } catch (error) {
      ms43Status('Could not save: ' + error.message);
      toast('Custom preset not saved', error.message, 'error');
    } finally {
      ms43Busy = false;
      ms43Controls();
    }
  }
  async function ms43Delete() {
    const p = ms43Selected();
    if (!p || ms43Busy || !state.project || animationMode() !== '3d' || motionLabBusy) return;
    if (!(await window.MorphorumDialog.confirm({
      title:'Delete saved custom preset?',
      message:'Remove "'+p.name+'" from the shared library? Existing project motion layers remain unchanged.',
      variant:'danger',confirmText:'Delete Preset',cancelText:'Keep Preset',
    }))) return;
    ms43Busy = true;
    ms43Controls();
    try {
      await api(MS43_URL+'/'+encodeURIComponent(p.id), {method:'DELETE'});
      ms43Presets = ms43Presets.filter(item => item.id !== p.id);
      ms43El('library').value = '';
      ms43El('name').value = '';
      ms43RenderLibrary();
      ms43Status('Deleted "'+p.name+'". Existing project motion was not changed.');
      toast('Custom preset deleted',p.name+' removed from shared library.','success');
    } catch (error) {
      ms43Status('Could not delete: '+error.message);
      toast('Could not delete saved preset',error.message,'error');
    } finally {
      ms43Busy = false;
      ms43Controls();
    }
  }

  async function motionStudioArrange(action = 'stage') {
    const form = motionStudioArrangementFields();
    if (!form || !state.project || animationMode() !== '3d' || motionLabBusy) return;
    const count = motionStudioArrangementFrameCount();
    motionStudioArrangementSyncRange();
    const data = {
      preset:form.preset.value,
      blend:form.blend.value,
      axes:motionStudioArrangementAxisSelection(),
      strength:Number(form.strength.value),
      cycle_seconds:Number(form.cycle.value),
      fade_seconds:Number(form.fade.value),
      start_frame:Number(form.start.value),
      end_frame:Number(form.end.value),
    };
    if (!MOTION_STUDIO_CONTINUOUS_PRESETS.some(([id]) => id === data.preset) ||
        !['add','replace'].includes(data.blend) ||
        (data.preset === 'still' && data.blend !== 'replace') ||
        !Array.isArray(data.axes) || !data.axes.length ||
        data.axes.some(axis => !MOTION_STUDIO_PRESET_AXES[data.preset].includes(axis)) ||
        !Number.isFinite(data.strength) || data.strength < 0 || data.strength > 1 ||
        !Number.isFinite(data.cycle_seconds) || data.cycle_seconds < .2 ||
        data.cycle_seconds > 600 || !Number.isFinite(data.fade_seconds) ||
        data.fade_seconds < 0 || data.fade_seconds > 120 ||
        !Number.isInteger(data.start_frame) || !Number.isInteger(data.end_frame) ||
        data.start_frame < 0 || data.end_frame > count ||
        data.end_frame <= data.start_frame) {
      motionLabNotify('Check movement strength, cycle, fade and frame range.');
      toast('Invalid motion region','Choose at least one valid axis; Still requires Replace. Check timing and strength.','warning');
      return;
    }
    const existing = motionStudioArrangementActiveLayer();
    if (!existing && motionLabDraftLayers.length >= 24) {
      motionLabNotify('Motion Lab supports up to 24 layers. Remove a layer first.');
      return;
    }
    const id = existing?.id || 'motion-studio-cont-' +
      (++motionStudioArrangementSerial) + '-' + Date.now().toString(36);
    const layer = {id,type:'preset',enabled:existing?.enabled !== false,...data};
    const index = existing ? motionLabDraftLayers.findIndex(x=>x.id===existing.id) : -1;
    if (index >= 0) motionLabDraftLayers[index] = layer;
    else motionLabDraftLayers.push(layer);
    motionStudioArrangementSelection = id;
    motionStudioArrangementLoaded = id;
    commitMotionLabDraft();
    if (action === 'preview') await motionLabPreviewOrApply(false,{curvesOnly:true});
    else if (action === 'apply') await motionLabPreviewOrApply(true);
  }
  function motionStudioCreateArrangementCard(panel) {
    const card = document.createElement('article');
    card.className = 'card glass motion-studio-arrangement';
    card.id = 'animation-motion-studio-arrangement';
    card.innerHTML = `
      <div class="card-header"><div>
        <h2>Continuous Camera Motion</h2>
        <p class="muted">Choreograph sustained movement alongside the soundtrack.
          Regions are native Motion Lab layers, not another render engine.</p>
      </div></div>
      <div class="motion-studio-arrangement-playback">
        <span data-ms4-playback-status>Load a WAV for synchronized seeking.</span>
        <label>Audio playhead / seek
          <input type="range" data-ms4-seek min="0" max="120" step="1"
            value="0" aria-label="Seek project audio by frame"></label>
      </div>
      <div class="motion-studio-arrangement-timeline">
        <div class="motion-studio-arrangement-ruler" data-ms4-ruler></div>
        <div class="motion-studio-arrangement-playhead" data-ms4-playhead hidden></div>
        <div data-ms4-lanes class="motion-studio-arrangement-lanes"></div>
        <p class="muted" data-ms4-lane-status>Project motion layers appear here.</p>
      </div>
      <div class="motion-studio-arrangement-fields">
        <label>Continuous preset<select data-ms4-preset></select></label>
        <label>Blend method<select data-ms4-blend>
          <option value="add">Add motion</option>
          <option value="replace">Replace selected axes in range</option>
        </select></label>
        <label>Strength (0–1)<input type="number" data-ms4-strength
          min="0" max="1" step=".05" value=".65"></label>
        <label>Cycle (seconds)<input type="number" data-ms4-cycle
          min=".2" max="600" step=".1" value="2"></label>
        <label>Fade (seconds)<input type="number" data-ms4-fade
          min="0" max="120" step=".05" value=".1"></label>
        <label>Start frame<input type="number" data-ms4-start
          min="0" step="1" value="0"></label>
        <label>End frame (exclusive)<input type="number" data-ms4-end
          min="1" step="1" value="120"></label>
      </div>
      <fieldset class="motion-studio-arrangement-axis-mask">
        <legend>Camera axes affected by this region</legend>
        <div data-ms4-axes class="motion-studio-arrangement-axes"></div>
        <p class="muted" data-ms4-blend-help>
          Add motion only on checked camera axes.</p>
      </fieldset>
      <div class="motion-studio-arrangement-range">
        <label>Start<input type="range" data-ms4-start-slide min="0"
          max="119" step="1" value="0"></label>
        <label>End<input type="range" data-ms4-end-slide min="1"
          max="120" step="1" value="120"></label>
        <span data-ms4-range-label class="muted">Frames 0–119</span>
      </div>
      <section class="motion-studio-custom-presets" aria-label="Saved custom camera motion presets">
        <div>
          <h3>My Motion Presets</h3>
          <p class="muted">Saved separately from projects on this Morphorum installation.
            Load to the editor, then Stage Movement. Frame ranges scale with project length.</p>
        </div>
        <div class="motion-studio-custom-fields">
          <label>Saved preset<select data-ms43-library>
            <option value="">Choose saved preset</option></select></label>
          <label>Name<input type="text" data-ms43-name maxlength="64"
            placeholder="e.g. Slow cinematic orbit"></label>
        </div>
        <div class="motion-studio-custom-actions">
          <button type="button" class="secondary-button compact" data-ms43-load>Load to Editor</button>
          <button type="button" class="secondary-button compact" data-ms43-save>Save as New</button>
          <button type="button" class="secondary-button compact" data-ms43-update>Update Saved</button>
          <button type="button" class="secondary-button compact" data-ms43-delete>Delete Saved</button>
          <button type="button" class="secondary-button compact" data-ms43-refresh>Refresh Library</button>
        </div>
        <p class="muted" data-ms43-status role="status" aria-live="polite">
          Loading shared preset library…</p>
      </section>
      <div class="motion-studio-arrangement-actions">
        <button type="button" class="secondary-button compact" data-ms4-new>New Movement</button>
        <button type="button" class="secondary-button compact" data-ms4-stage>+ Stage Movement</button>
        <button type="button" class="secondary-button compact" data-ms4-preview>Preview Curves</button>
        <button type="button" class="primary-button compact" data-ms4-apply>Apply to Animation</button>
      </div>
      <p class="muted" data-ms4-status role="status" aria-live="polite">Open a 3D project.</p>
      <details class="motion-field-help"><summary>Timing, units and safety</summary>
        <p>All segments are frame aligned. Start is inclusive, end is exclusive;
        cycle and fade use seconds at the current project FPS. Movement is
        in Morphorum's native scene units per frame (translation) and degrees
        per frame (rotation). Add combines motion; Replace affects only the
        selected axes during the region. Existing manual cues, audio and other
        axes remain as separate layers. Layer order determines the final mix.
        Preview does not save schedules; Apply uses existing safeguards.</p>
      </details>`;
    for (const [key,label] of MOTION_STUDIO_CONTINUOUS_PRESETS) {
      const item=document.createElement('option');
      item.value=key;
      item.textContent=label;
      card.querySelector('[data-ms4-preset]').appendChild(item);
    }
    panel.appendChild(card);
    const s = key=>card.querySelector('[data-ms4-'+key+']');
    s('preset').addEventListener('change',()=>{
      motionStudioArrangementRebuildAxes(MOTION_STUDIO_PRESET_AXES[s('preset').value] || []);
    });
    s('blend').addEventListener('change',motionStudioArrangementShowBlendHelp);
    const sync = key=>()=>{
      motionStudioArrangementSyncRange(key);
    };
    s('start').addEventListener('input',sync('start'));
    s('end').addEventListener('input',sync('end'));
    s('start-slide').addEventListener('input',()=>{
      s('start').value=s('start-slide').value; sync('start')();
    });
    s('end-slide').addEventListener('input',()=>{
      s('end').value=s('end-slide').value; sync('end')();
    });
    s('seek').addEventListener('input',event=>motionStudioArrangementSeek(event.target.value));
    s('new').addEventListener('click',()=>{
      motionStudioArrangementSelection='';
      motionStudioArrangementLoaded='';
      motionStudioArrangementResetFields();
      motionStudioRenderArrangement();
    });
    for (const action of ['stage','preview','apply']) {
      s(action).addEventListener('click',()=>void motionStudioArrange(action));
    }
    const custom = key => card.querySelector('[data-ms43-' + key + ']');
    custom('library').addEventListener('change', ms43Select);
    custom('load').addEventListener('click', ms43Load);
    custom('save').addEventListener('click', () => void ms43Save(false));
    custom('update').addEventListener('click', () => void ms43Save(true));
    custom('delete').addEventListener('click', () => void ms43Delete());
    custom('refresh').addEventListener('click', () => void ms43Refresh());
    motionStudioRenderArrangement();
    void ms43Refresh();
  }

  // MS3: Audio-frequency channels share ONE Motion Lab layer per WAV. Draft
  // settings never write project camera schedules until explicit Apply.
  const MOTION_STUDIO_AXES = [
    ['translation_x', 'Travel X'], ['translation_y', 'Travel Y'],
    ['translation_z', 'Travel Z'], ['rotation_x', 'Pitch'],
    ['rotation_y', 'Yaw'], ['rotation_z', 'Roll'],
  ];
  let motionStudioChannelState = { projectId: '', sha: '', channels: [], dirty: false };
  let motionStudioChannelSerial = 0;
  const motionStudioBandCache = new Map();

  // MS3b spectrum is derived from a verified project WAV, never from browser
  // file paths. All edits below are local until Stage/Preview/Apply.
  let motionStudioSpectrum = {
    projectId: '', sha: '', points: [], maxHz: 20000, loading: false, error: '',
  };
  let motionStudioSelectedChannel = '';
  let motionStudioDraggingEdge = '';
  let motionStudioSpectrumToken = 0;
  const motionStudioSpectrumCache = new Map();
  let motionStudioBandPreview = { projectId: '', sha: '', fps: 0, frames: 0,
    ranges: '', bands: null };

  const motionStudioSpectrumX = (hz, max) =>
    34 + 666 * Math.log(Math.max(20, Math.min(max, hz)) / 20) /
      Math.log(max / 20);
  function motionStudioSpectrumFrequency(clientX, svg, max) {
    const bounds = svg.getBoundingClientRect();
    const px = (clientX - bounds.left) * 720 / Math.max(1, bounds.width);
    const ratio = Math.max(0, Math.min(1, (px - 34) / 666));
    return 20 * (max / 20) ** ratio;
  }

  function motionStudioSelectedBand() {
    const channels = motionStudioChannelState.channels;
    return channels.find(channel => channel.id === motionStudioSelectedChannel) ||
      channels[0] || null;
  }

  function motionStudioBandRanges(channels) {
    return channels.map(({id, low_hz, high_hz}) => ({id, low_hz, high_hz}));
  }

  function motionStudioShowBandPreview() {
    const panel = qs('#animation-motion-studio-channels');
    const svg = panel?.querySelector('[data-ms3-envelope-svg]');
    const label = panel?.querySelector('[data-ms3-envelope-status]');
    if (!svg || !label) return;
    const selected = motionStudioSelectedBand();
    const preview = motionStudioBandPreview;
    const analysis = motionLabAudioAnalysis;
    const valid = selected && analysis && state.project?.id === preview.projectId &&
      preview.sha === analysis.source_sha256 &&
      Number(state.project.animation.fps) === preview.fps &&
      Number(state.project.animation.max_frames) === preview.frames;
    const analyzed = valid && preview.bands && preview.ranges ===
      JSON.stringify(motionStudioBandRanges(motionStudioChannelState.channels));
    const envelope = analyzed && preview.bands[selected.id];
    svg.replaceChildren();
    if (!envelope?.length) {
      label.textContent = 'Analyze the current channel ranges to preview their normalized energy.';
      return;
    }
    const NS = 'http://www.w3.org/2000/svg';
    const line = document.createElementNS(NS, 'line');
    line.setAttribute('x1','24'); line.setAttribute('x2','710');
    line.setAttribute('y1','144'); line.setAttribute('y2','144');
    line.setAttribute('stroke','currentColor'); line.setAttribute('opacity','.3');
    svg.appendChild(line);
    const graph = document.createElementNS(NS, 'path');
    const stride = Math.max(1, Math.ceil(envelope.length / 340));
    const path = [];
    for (let i=0;i<envelope.length;i+=stride) {
      const energy = Math.max(0, Math.min(1, Number(envelope[i]) || 0));
      const x = 24 + 686*i / Math.max(1,envelope.length - 1);
      path.push((path.length ? 'L' : 'M') + x.toFixed(2) + ',' +
        (144 - 120*energy).toFixed(2));
    }
    graph.setAttribute('d',path.join(' '));
    graph.setAttribute('fill','none'); graph.setAttribute('stroke','var(--accent)');
    graph.setAttribute('stroke-width','2');
    graph.setAttribute('stroke-linejoin','round');
    svg.appendChild(graph);
    const gate = document.createElementNS(NS,'line');
    const y = 144 - 120 * Math.max(0, Math.min(1, Number(selected.threshold) || 0));
    for (const [key,val] of Object.entries({
      x1:24, x2:710, y1:y, y2:y,
      stroke:'var(--warn)', 'stroke-dasharray':'5 5', opacity:.85,
    })) gate.setAttribute(key,String(val));
    svg.appendChild(gate);
    label.textContent = selected.name + ' · ' + selected.low_hz + '–' +
      selected.high_hz + ' Hz · ' + envelope.length + ' project frames · ' +
      'dashed line = threshold (energy only, not camera velocity)';
  }

  function motionStudioDrawSpectrum() {
    const panel = qs('#animation-motion-studio-channels');
    const svg = panel?.querySelector('[data-ms3-spectrum-svg]');
    const caption = panel?.querySelector('[data-ms3-spectrum-caption]');
    const selected = motionStudioSelectedBand();
    const picker = panel?.querySelector('[data-ms3-select]');
    if (!svg || !caption || !picker) return;
    picker.replaceChildren();
    for (const channel of motionStudioChannelState.channels) {
      const option = document.createElement('option');
      option.value = channel.id;
      option.textContent = channel.name + ' (' + channel.low_hz + '–' + channel.high_hz + ' Hz)';
      picker.appendChild(option);
    }
    if (selected) {
      motionStudioSelectedChannel = selected.id;
      picker.value = selected.id;
    }
    picker.disabled = !selected;
    svg.replaceChildren();
    const state = motionStudioSpectrum;
    const current = state.projectId === motionLabAudioProjectId &&
      state.sha === motionLabAudioAnalysis?.source_sha256 &&
      state.projectId === motionStudioChannelState.projectId;
    const points = current ? state.points : [];
    const max = Math.max(21, state.maxHz || 20000);
    svg.setAttribute('aria-label', selected ?
      'Spectrum for ' + selected.name + ', ' + selected.low_hz + ' to ' +
      selected.high_hz + ' Hz. Drag a band edge or press arrow keys to edit.'
      : 'Frequency spectrum: no sound channel selected');
    const NS = 'http://www.w3.org/2000/svg';
    const el = (type, attributes) => {
      const node = document.createElementNS(NS,type);
      for (const [key,value] of Object.entries(attributes)) node.setAttribute(key,String(value));
      svg.appendChild(node);
      return node;
    };
    el('line',{x1:34,y1:150,x2:700,y2:150,stroke:'currentColor',opacity:.4});
    for (const hz of [20,50,100,250,500,1000,2500,5000,10000,20000]) {
      if (hz > max) continue;
      const x = motionStudioSpectrumX(hz,max);
      el('line',{x1:x,y1:18,x2:x,y2:150,stroke:'currentColor',opacity:.10});
      const text = el('text',{x,y:165,'text-anchor':'middle',fill:'currentColor',
        'font-size':'12',opacity:.75});
      text.textContent = hz >= 1000 ? (hz/1000) + 'k' : String(hz);
    }
    if (points.length) {
      const outline = points.map((point,i)=>
        (i?'L':'M') + motionStudioSpectrumX(point.hz,max).toFixed(2) +
        ',' + (150-126*Math.max(0,Math.min(1,point.level))).toFixed(2)).join(' ');
      el('path',{d:outline,fill:'none',stroke:'var(--accent)','stroke-width':2,
        'stroke-linejoin':'round'});
    }
    if (selected) {
      const low = motionStudioSpectrumX(selected.low_hz,max);
      const high = motionStudioSpectrumX(selected.high_hz,max);
      el('rect',{x:low,y:18,width:Math.max(0,high-low),height:132,
        fill:'var(--accent)',opacity:.15});
      for (const x of [low,high]) {
        el('line',{x1:x,y1:18,x2:x,y2:150,stroke:'var(--accent)',
          'stroke-width':3});
        el('circle',{cx:x,cy:22,r:6,fill:'var(--accent)'});
      }
    }
    caption.textContent = !current ? 'Open a project WAV to inspect its frequency profile.' :
      state.loading ? 'Analyzing saved WAV spectrum…' :
      state.error ? 'Spectrum unavailable: ' + state.error :
      !points.length ? 'Spectrum unavailable.' :
      'Time-averaged FFT of the saved WAV, ' + (max/1000).toFixed(1) +
      ' kHz upper range. Select a channel, then drag either band edge or use the keyboard arrows.';
    motionStudioShowBandPreview();
  }

  function motionStudioEditBandEdge(hz, edge) {
    const selected = motionStudioSelectedBand();
    if (!selected || motionLabAudioProjectId !== state.project?.id ||
        motionStudioSpectrum.loading) return;
    const upper = Math.min(20000, Math.floor(motionStudioSpectrum.maxHz || 20000));
    if (upper <= 40) return;
    const snapped = Math.max(20, Math.min(upper, Math.round(hz)));
    if (edge === 'low') selected.low_hz = Math.min(snapped, selected.high_hz - 10);
    else selected.high_hz = Math.max(snapped, selected.low_hz + 10);
    selected.low_hz = Math.max(20, Math.min(selected.low_hz, upper - 10));
    selected.high_hz = Math.min(upper, Math.max(selected.high_hz, selected.low_hz + 10));
    motionStudioChannelState.dirty = true;
    // Change the two numerical controls without discarding keyboard focus.
    const row = Array.from(qs('#animation-motion-studio-channels')?.querySelectorAll(
      '[data-ms3-channel]') || []).find(node=>node.dataset.ms3Channel === selected.id);
    if (row) {
      for (const field of ['low_hz','high_hz']) {
        const input = row.querySelector('[data-ms3-field="' + field + '"]');
        if (input) input.value = String(selected[field]);
      }
    }
    motionStudioDrawSpectrum();
    motionStudioUpdateChannelButtons();
  }

  async function motionStudioFetchSpectrum(projectId, sha, refresh = false) {
    const token = ++motionStudioSpectrumToken;
    const cacheKey = projectId + '|' + sha;
    const cached = !refresh && motionStudioSpectrumCache.get(cacheKey);
    motionStudioSpectrum = { projectId, sha, points: [], maxHz: 20000,
      loading: !cached, error: '' };
    if (cached) {
      motionStudioSpectrum = {...motionStudioSpectrum,
        points:cached.spectrum,maxHz:cached.frequency_max_hz,loading:false};
      motionStudioDrawSpectrum();
      return;
    }
    motionStudioDrawSpectrum();
    try {
      const result = await api('/api/animation/projects/' + encodeURIComponent(projectId) +
        '/motion-lab/audio/' + encodeURIComponent(sha) + '/spectrum');
      if (token !== motionStudioSpectrumToken || state.project?.id !== projectId ||
          motionLabAudioAnalysis?.source_sha256 !== sha) return;
      const data = result.analysis;
      if (!Array.isArray(data?.spectrum) || data.spectrum.length > 128 ||
          data.spectrum.length < 32 || !data.spectrum.every(item =>
            Number.isFinite(item.hz) && Number.isFinite(item.level) &&
            item.hz >= 20 && item.level >= 0 && item.level <= 1)) {
        throw new Error('Host returned invalid spectrum data.');
      }
      motionStudioSpectrumCache.set(cacheKey,data);
      if (motionStudioSpectrumCache.size > 10) motionStudioSpectrumCache.delete(
        motionStudioSpectrumCache.keys().next().value);
      motionStudioSpectrum = {projectId,sha,points:data.spectrum,
        maxHz:data.frequency_max_hz,loading:false,error:''};
    } catch (error) {
      if (token !== motionStudioSpectrumToken || state.project?.id !== projectId) return;
      motionStudioSpectrum.loading = false;
      motionStudioSpectrum.error = error.message;
    }
    motionStudioDrawSpectrum();
  }

  async function motionStudioInspectChannels() {
    const projectId = state.project?.id;
    const analysis = motionLabAudioAnalysis;
    if (!projectId || !analysis || motionLabAudioProjectId !== projectId) return;
    const sha = analysis.source_sha256;
    const frames = Number(state.project.animation.max_frames);
    const fps = Number(state.project.animation.fps);
    const ranges = motionStudioBandRanges(motionStudioChannelState.channels);
    if (!ranges.length || ranges.length > 8) return;
    const key = JSON.stringify([projectId,sha,fps,frames,ranges]);
    const btn = qs('#animation-motion-studio-channels')?.querySelector('[data-ms3-inspect]');
    if (btn) btn.disabled = true;
    try {
      let bands = motionStudioBandCache.get(key);
      if (!bands) {
        const response = await api('/api/animation/projects/' + encodeURIComponent(projectId) +
          '/motion-lab/audio/' + encodeURIComponent(sha) + '/bands', {
          method:'POST',body:JSON.stringify({ranges}),
        });
        bands = response.analysis?.bands;
        if (!bands) throw new Error('Missing saved WAV frequency analysis.');
        motionStudioBandCache.set(key,bands);
        if (motionStudioBandCache.size > 12) motionStudioBandCache.delete(
          motionStudioBandCache.keys().next().value);
      }
      if (state.project?.id !== projectId || motionLabAudioAnalysis?.source_sha256 !== sha ||
          Number(state.project.animation.fps) !== fps ||
          Number(state.project.animation.max_frames) !== frames) return;
      motionStudioBandPreview = { projectId,sha, fps, frames,
        ranges:JSON.stringify(ranges),bands };
      motionStudioShowBandPreview();
    } catch (error) {
      if (state.project?.id === projectId) {
        motionLabNotify('Frequency preview: ' + error.message);
      }
    } finally {
      if (state.project?.id === projectId) motionStudioUpdateChannelButtons();
    }
  }

  function motionStudioChannelDefaults(analysis) {
    const end = Number(analysis.values.length);
    return [
      { id:'bass', name:'Bass', enabled:true, low_hz:35, high_hz:150,
        axis:'translation_z', mode:'hits', threshold:.25, sensitivity:.35,
        strength:.4, attack_frames:2, release_frames:6, cooldown_frames:3,
        offset_frames:0, start_frame:0, end_frame:end },
      { id:'snare', name:'Snare', enabled:true, low_hz:180, high_hz:2400,
        axis:'rotation_x', mode:'hits', threshold:.3, sensitivity:.35,
        strength:.35, attack_frames:2, release_frames:5, cooldown_frames:4,
        offset_frames:0, start_frame:0, end_frame:end },
      { id:'crash', name:'Crash', enabled:true, low_hz:2500, high_hz:3500,
        axis:'rotation_z', mode:'ripple', threshold:.3, sensitivity:.35,
        strength:.25, attack_frames:2, release_frames:12, cooldown_frames:6,
        offset_frames:0, start_frame:0, end_frame:end },
    ];
  }

  function motionStudioRestoreChannels(projectId, analysis) {
    const sha = analysis?.source_sha256;
    if (!projectId || !sha || state.project?.id !== projectId) return;
    const saved = (state.project.motion_lab?.layers || []).find(layer =>
      layer.type === 'audio_channels' && layer.sha256 === sha);
    const channels = saved?.channel_document?.channels?.length
      ? saved.channel_document.channels.map(channel => {
          const { envelope, ...settings } = channel;
          return { ...settings };
        }) : motionStudioChannelDefaults(analysis);
    motionStudioChannelState = {
      projectId, sha, channels, dirty: false,
    };
    if (!channels.some(channel => channel.id === motionStudioSelectedChannel)) {
      motionStudioSelectedChannel = channels[0]?.id || '';
    }
    motionStudioBandPreview = {projectId:'',sha:'',fps:0,frames:0,ranges:'',bands:null};
    motionStudioRenderChannels();
    void motionStudioFetchSpectrum(projectId, sha);
  }

  function motionStudioUpdateChannelButtons() {
    const panel = qs('#animation-motion-studio-channels');
    if (!panel) return;
    const analysis = motionLabAudioAnalysis;
    const current = Boolean(state.project?.id && analysis &&
      motionLabAudioProjectId === state.project.id &&
      motionStudioChannelState.projectId === state.project.id &&
      motionStudioChannelState.sha === analysis.source_sha256);
    const ready = current && animationMode() === '3d' && !motionLabBusy;
    for (const key of ['stage','preview','apply']) {
      const button = panel.querySelector('[data-ms3-' + key + ']');
      if (button) button.disabled = !ready || !motionStudioChannelState.channels.length;
    }
    const add = panel.querySelector('[data-ms3-add]');
    if (add) add.disabled = !ready || motionStudioChannelState.channels.length >= 8;
    const inspect = panel.querySelector('[data-ms3-inspect]');
    if (inspect) inspect.disabled = !ready || !motionStudioChannelState.channels.length;
    const refresh = panel.querySelector('[data-ms3-refresh-spectrum]');
    if (refresh) refresh.disabled = !ready || motionStudioSpectrum.loading;
    const status = panel.querySelector('[data-ms3-status]');
    if (status) status.textContent = !state.project ? 'Open a project to configure channels.' :
      !current ? 'Analyze or restore a saved WAV to enable independent channels.' :
      motionStudioChannelState.channels.length + ' channel(s)' +
        (motionStudioChannelState.dirty ? ' · Changes not staged' :
          ' · Stage to preview, Apply to save camera motion');
  }

  function motionStudioRenderChannels() {
    const panel = qs('#animation-motion-studio-channels');
    if (!panel) return;
    const list = panel.querySelector('[data-ms3-list]');
    if (!list) return;
    list.replaceChildren();
    for (const channel of motionStudioChannelState.channels) {
      const row = document.createElement('section');
      row.className = 'motion-studio-channel';
      row.dataset.ms3Channel = channel.id;
      row.innerHTML = `
        <div class="motion-studio-channel-heading">
          <label><input type="checkbox" data-ms3-field="enabled"> Enabled</label>
          <strong data-ms3-label></strong>
          <button type="button" class="secondary-button compact" data-ms3-remove>Remove</button>
        </div>
        <div class="motion-studio-channel-fields">
          <label>Name<input data-ms3-field="name" type="text" maxlength="64"></label>
          <label>Low (Hz)<input data-ms3-field="low_hz" type="number" min="20" max="20000" step="1"></label>
          <label>High (Hz)<input data-ms3-field="high_hz" type="number" min="30" max="20000" step="1"></label>
          <label>Camera axis<select data-ms3-field="axis"></select></label>
          <label>Response<select data-ms3-field="mode">
            <option value="hits">Beat Hits</option>
            <option value="intensity">Continuous Intensity</option>
            <option value="ripple">Ripple / oscillation</option>
          </select></label>
          <label>Strength (0–1)<input data-ms3-field="strength" type="number" min="0" max="1" step=".05"></label>
          <label>Threshold (0–1)<input data-ms3-field="threshold" type="number" min="0" max="1" step=".05"></label>
          <label>Sensitivity (0–1)<input data-ms3-field="sensitivity" type="number" min="0" max="1" step=".05"></label>
          <label>Attack (frames)<input data-ms3-field="attack_frames" type="number" min="1" max="120" step="1"></label>
          <label>Release (frames)<input data-ms3-field="release_frames" type="number" min="1" max="120" step="1"></label>
          <label>Cooldown (frames)<input data-ms3-field="cooldown_frames" type="number" min="0" max="120" step="1"></label>
          <label>Offset (frames)<input data-ms3-field="offset_frames" type="number" min="-3000" max="3000" step="1"></label>
          <label>Start frame<input data-ms3-field="start_frame" type="number" min="0" max="2999" step="1"></label>
          <label>End frame (exclusive)<input data-ms3-field="end_frame" type="number" min="1" max="3000" step="1"></label>
        </div>`;
      const select = row.querySelector('[data-ms3-field="axis"]');
      for (const [axis, label] of MOTION_STUDIO_AXES) {
        const option = document.createElement('option');
        option.value = axis;
        option.textContent = label;
        select.appendChild(option);
      }
      for (const field of row.querySelectorAll('[data-ms3-field]')) {
        const name = field.dataset.ms3Field;
        if (field.type === 'checkbox') field.checked = channel[name] !== false;
        else field.value = String(channel[name] ?? '');
      }
      row.querySelector('[data-ms3-label]').textContent = channel.name;
      row.querySelector('[data-ms3-remove]').addEventListener('click', () => {
        motionStudioChannelState.channels = motionStudioChannelState.channels.filter(
          item => item.id !== channel.id);
        motionStudioChannelState.dirty = true;
        motionStudioRenderChannels();
      });
      for (const input of row.querySelectorAll('[data-ms3-field]')) {
        input.addEventListener('change', () => {
          const name = input.dataset.ms3Field;
          const index = motionStudioChannelState.channels.findIndex(
            item => item.id === channel.id);
          if (index < 0) return;
          const value = input.type === 'checkbox' ? input.checked :
            input.type === 'number' ? Number(input.value) : input.value;
          motionStudioChannelState.channels[index][name] = value;
          if (name === 'name') row.querySelector('[data-ms3-label]').textContent = value;
          motionStudioChannelState.dirty = true;
          motionStudioDrawSpectrum();
          motionStudioUpdateChannelButtons();
        });
      }
      list.appendChild(row);
    }
    motionStudioDrawSpectrum();
    motionStudioUpdateChannelButtons();
  }

  function motionStudioCreateChannelCard(panel) {
    const card = document.createElement('article');
    card.className = 'card glass animation-motion-studio-channels';
    card.id = 'animation-motion-studio-channels';
    card.innerHTML = `
      <div class="card-header"><div>
        <h2>Independent Sound Channels</h2>
        <p class="muted">Bass, Snare, Crash or custom frequency bands control
        independent camera axes. Spectral filters are approximate, not isolated
        drum stems. Manual camera cues remain separate.</p>
      </div></div>
      <p class="muted">Each response is non-drifting and frame-aligned.
      Use a saved project WAV. Settings are staged in a single editable
      Motion Lab layer and saved only on Apply.</p>
      <section class="motion-studio-spectrum-panel">
        <div class="motion-studio-spectrum-heading">
          <strong>Frequency spectrum</strong>
          <label>Channel<select data-ms3-select aria-label="Sound channel to inspect"></select></label>
          <label>Keyboard edge<select data-ms3-edge aria-label="Frequency band edge">
            <option value="low">Low frequency</option>
            <option value="high">High frequency</option>
          </select></label>
          <button type="button" class="secondary-button compact"
            data-ms3-refresh-spectrum>Refresh FFT</button>
        </div>
        <svg data-ms3-spectrum-svg viewBox="0 0 720 176" tabindex="0"
          role="img" aria-label="Saved WAV frequency spectrum"></svg>
        <p data-ms3-spectrum-caption class="muted" aria-live="polite">
          Load a saved WAV to inspect its frequency profile.</p>
      </section>
      <section class="motion-studio-response-panel">
        <div class="motion-studio-spectrum-heading">
          <strong>Channel energy preview</strong>
          <button type="button" class="secondary-button compact"
            data-ms3-inspect>Analyze channel responses</button>
        </div>
        <svg data-ms3-envelope-svg viewBox="0 0 720 160" role="img"
          aria-label="Selected channel normalized energy by project frame"></svg>
        <p data-ms3-envelope-status class="muted">
          Analyze the selected channel to see its response before staging motion.</p>
      </section>
      <div data-ms3-list class="motion-studio-channel-list"></div>
      <div class="motion-studio-channel-actions">
        <button type="button" class="secondary-button compact" data-ms3-add>Add custom channel</button>
        <button type="button" class="secondary-button compact" data-ms3-stage>Stage channels</button>
        <button type="button" class="secondary-button compact" data-ms3-preview>Preview curves</button>
        <button type="button" class="primary-button compact" data-ms3-apply>Apply to project</button>
      </div>
      <p class="muted" role="status" aria-live="polite" data-ms3-status>
        Analyze a WAV to configure audio channels.</p>`;
    panel.appendChild(card);
    const spectrum = card.querySelector('[data-ms3-spectrum-svg]');
    const edgePicker = card.querySelector('[data-ms3-edge]');
    const selectedPicker = card.querySelector('[data-ms3-select]');
    selectedPicker.addEventListener('change', event => {
      motionStudioSelectedChannel = event.target.value;
      motionStudioDrawSpectrum();
    });
    spectrum.addEventListener('pointerdown', event => {
      const band = motionStudioSelectedBand();
      if (!band || !motionStudioSpectrum.points.length ||
          motionStudioSpectrum.projectId !== state.project?.id) return;
      const upper = motionStudioSpectrum.maxHz;
      const hz = motionStudioSpectrumFrequency(event.clientX,spectrum,upper);
      const nearest = Math.abs(Math.log(Math.max(20,band.low_hz) / hz)) <
        Math.abs(Math.log(Math.max(20,band.high_hz) / hz)) ? 'low' : 'high';
      motionStudioDraggingEdge = nearest;
      edgePicker.value = nearest;
      if (spectrum.setPointerCapture) spectrum.setPointerCapture(event.pointerId);
      motionStudioEditBandEdge(hz,nearest);
      event.preventDefault();
    });
    spectrum.addEventListener('pointermove', event => {
      if (!motionStudioDraggingEdge || !motionStudioSpectrum.points.length) return;
      const hz = motionStudioSpectrumFrequency(event.clientX,spectrum,
        motionStudioSpectrum.maxHz);
      motionStudioEditBandEdge(hz,motionStudioDraggingEdge);
    });
    for (const eventName of ['pointerup','pointercancel','lostpointercapture']) {
      spectrum.addEventListener(eventName, () => { motionStudioDraggingEdge = ''; });
    }
    spectrum.addEventListener('keydown', event => {
      if (!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(event.key)) return;
      const band = motionStudioSelectedBand();
      if (!band) return;
      const edge = edgePicker.value === 'high' ? 'high' : 'low';
      const direction = event.key === 'ArrowRight' || event.key === 'ArrowUp' ? 1 : -1;
      const next = Number(band[edge + '_hz']) * 2 ** (direction / 12);
      motionStudioEditBandEdge(next,edge);
      event.preventDefault();
    });
    card.querySelector('[data-ms3-refresh-spectrum]').addEventListener('click', () => {
      const projectId = state.project?.id, sha = motionLabAudioAnalysis?.source_sha256;
      if (projectId && sha && motionLabAudioProjectId === projectId)
        void motionStudioFetchSpectrum(projectId,sha,true);
    });
    card.querySelector('[data-ms3-inspect]').addEventListener('click',
      () => void motionStudioInspectChannels());
    card.querySelector('[data-ms3-add]').addEventListener('click', () => {
      if (motionStudioChannelState.channels.length >= 8) return;
      const analysis = motionLabAudioAnalysis;
      if (!analysis || motionLabAudioProjectId !== state.project?.id) return;
      let ident;
      do { ident = 'custom-' + (++motionStudioChannelSerial); }
      while (motionStudioChannelState.channels.some(channel => channel.id === ident));
      motionStudioChannelState.channels.push({
        ...motionStudioChannelDefaults(analysis)[0], id: ident, name: 'Custom channel',
        low_hz: 450, high_hz: 1200, mode: 'intensity', axis: 'translation_y',
      });
      motionStudioChannelState.dirty = true;
      motionStudioRenderChannels();
    });
    card.querySelector('[data-ms3-stage]').addEventListener('click',
      () => void motionStudioStageChannels());
    card.querySelector('[data-ms3-preview]').addEventListener('click',
      () => void motionStudioStageChannels('preview'));
    card.querySelector('[data-ms3-apply]').addEventListener('click',
      () => void motionStudioStageChannels('apply'));
    motionStudioRenderChannels();
  }

  async function motionStudioStageChannels(action = 'stage') {
    const analysis = motionLabAudioAnalysis;
    const projectId = state.project?.id;
    if (!analysis || !projectId || motionLabAudioProjectId !== projectId ||
        motionStudioChannelState.sha !== analysis.source_sha256 ||
        animationMode() !== '3d' || motionLabBusy) return;
    const sha = analysis.source_sha256;
    const controls = motionStudioChannelState.channels.map(item => ({ ...item }));
    const fps = Number(state.project.animation.fps);
    const frames = Number(state.project.animation.max_frames);
    if (!controls.length || controls.length > 8) return;
    const ranges = controls.map(channel => ({
      id: channel.id, low_hz: channel.low_hz, high_hz: channel.high_hz,
    }));
    // Bypass remote FFT work for an unchanged set of frequency ranges.
    const cacheKey = JSON.stringify([projectId, sha, fps, frames, ranges]);
    const controlsPanel = qs('#animation-motion-studio-channels');
    const message = controlsPanel?.querySelector('[data-ms3-status]');
    for (const button of controlsPanel?.querySelectorAll('button') || []) {
      button.disabled = true;
    }
    if (message) message.textContent = 'Analyzing independent frequency bands…';
    try {
      let bands = motionStudioBandCache.get(cacheKey);
      if (!bands) {
        const response = await api('/api/animation/projects/' + encodeURIComponent(projectId) +
          '/motion-lab/audio/' + encodeURIComponent(sha) + '/bands', {
          method: 'POST', body: JSON.stringify({ ranges }),
        });
        bands = response.analysis?.bands;
        if (!bands) throw new Error('Missing channel analysis from the host.');
        motionStudioBandCache.set(cacheKey, bands);
        if (motionStudioBandCache.size > 12) motionStudioBandCache.delete(
          motionStudioBandCache.keys().next().value);
      }
      if (state.project?.id !== projectId ||
          motionLabAudioAnalysis?.source_sha256 !== sha ||
          Number(state.project.animation.fps) !== fps ||
          Number(state.project.animation.max_frames) !== frames) return;
      const channels = controls.map(channel => ({
        ...channel, envelope: bands[channel.id]?.slice(),
      }));
      if (channels.some(channel => !Array.isArray(channel.envelope) ||
          channel.envelope.length !== frames)) {
        throw new Error('Frequency response length does not match project frames.');
      }
      motionStudioBandPreview = {projectId,sha,fps,frames,
        ranges:JSON.stringify(ranges),bands};
      motionStudioShowBandPreview();
      const layer = {
        id: 'audio-channels-' + sha.slice(0, 16), type: 'audio_channels',
        name: 'Independent sound channels', enabled: true, blend: 'add',
        sha256: sha, start_frame: 0, end_frame: frames,
        channel_document: {schema_version: 1, source_sha256: sha,
          fps, max_frames: frames, channels},
      };
      const previous = motionLabDraftLayers.findIndex(item =>
        item.type === 'audio_channels' && item.sha256 === sha);
      if (previous < 0 && motionLabDraftLayers.length >= 24) {
        throw new Error('Motion Lab supports at most 24 layers. Remove one before staging.');
      }
      if (previous >= 0) motionLabDraftLayers[previous] = layer;
      else motionLabDraftLayers.push(layer);
      motionLabEditingIndex = -1;
      motionStudioChannelState.dirty = false;
      commitMotionLabDraft();
      if (action === 'preview') await motionLabPreviewOrApply(false, {curvesOnly:true});
      else if (action === 'apply') await motionLabPreviewOrApply(true);
      motionStudioRenderChannels();
      if (message && state.project?.id === projectId)
        message.textContent = channels.length + ' sound channels ' +
          (action === 'apply' ? 'applied to this project.' :
           action === 'preview' ? 'previewed in Motion Curves.' :
           'staged in Motion Lab. Preview or Apply to save.');
    } catch (error) {
      motionLabNotify('Sound channels: ' + error.message);
      toast('Sound channel analysis failed', error.message, 'error');
    } finally {
      if (state.project?.id === projectId) motionStudioUpdateChannelButtons();
    }
  }

  // Restore source-bound manual cues and editable markers for both uploaded
  // and reopened WAVs. Stale project requests never overwrite the open editor.
  async function motionStudioHydrateEdits(projectId, analysis, stillCurrent) {
    const sha = analysis?.source_sha256;
    if (!projectId || !sha) return false;
    const calls = await Promise.allSettled([
      api('/api/animation/projects/' + encodeURIComponent(projectId) +
        '/motion-lab/audio-markers/' + encodeURIComponent(sha)),
      api('/api/animation/projects/' + encodeURIComponent(projectId) +
        '/motion-lab/audio-cues/' + encodeURIComponent(sha)),
    ]);
    if (!stillCurrent() || state.project?.id !== projectId) return false;
    const original = (analysis.events?.events || []).map(e => ({ ...e, enabled: true }));
    motionLabEditedEvents = original;
    motionLabSelectedEvent = null;
    motionLabMarkersDirty = false;
    motionLabMarkerUndo = [];
    motionLabMarkerRedo = [];
    motionDirectorCues = [];
    motionDirectorSelected = null;
    motionDirectorDirty = false;
    motionDirectorBulkUndo = null;
    motionDirectorPreviewMatches = false;
    const markers = calls[0].status === 'fulfilled' ? calls[0].value?.markers : null;
    if (markers && Math.abs(Number(markers.duration_seconds) -
                           Number(analysis.duration_seconds)) <= .001) {
      const baseline = new Map(original.map(e => [e.id, e]));
      motionLabEditedEvents = markers.events.map(e => ({
        ...baseline.get(e.id), ...e,
        strength: baseline.get(e.id)?.strength ?? e.strength ?? 1,
        source: baseline.get(e.id)?.source ?? (e.id.startsWith('manual-') ? 'manual' : 'saved'),
      }));
    } else if (markers) {
      motionLabNotify('Saved audio markers have a mismatched duration; detector markers are shown.');
    } else if (calls[0].status === 'rejected') {
      motionLabNotify('Could not restore saved marker edits: ' + calls[0].reason?.message);
    }
    const doc = calls[1].status === 'fulfilled' ? calls[1].value?.cues : null;
    if (doc && Math.abs(Number(doc.duration_seconds) -
                        Number(analysis.duration_seconds)) <= .001) {
      motionDirectorCues = doc.cues.map(cue => ({ ...cue }));
    } else if (doc) {
      motionLabNotify('Saved camera cues have a mismatched audio duration.');
    } else if (calls[1].status === 'rejected') {
      motionLabNotify('Could not restore saved camera cues: ' + calls[1].reason?.message);
    }
    return true;
  }

  function motionStudioConnectAudioTransport() {
    if (!motionLabAudioElement) return;
    for (const type of ['timeupdate', 'play', 'pause', 'seeked', 'ended']) {
      motionLabAudioElement.addEventListener(type, motionLabWavePlayhead);
      motionLabAudioElement.addEventListener(type, motionStudioArrangementPlayhead);
    }
    motionLabWavePlayhead();
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
    const values = motionLabAudioSignal();
    if (!values.length) { preview.hidden = true; return; }
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
    if (summary) summary.textContent = 'Peak signal ' + peak.toFixed(3) +
      ' · ' + (qs('#animation-motion-lab-audio-band')?.value || 'fullband') +
      ' / ' + (qs('#animation-motion-lab-audio-detection')?.value || 'level') +
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
    const attached = qs('#animation-motion-lab-use-soundtrack');
    if (attached) attached.disabled = !ready || motionLabSoundtrackBusy ||
      !projectMediaAssets('soundtrack').length;
    if (add) add.disabled = !ready || motionLabDraftLayers.length >= 24 ||
      !motionLabAudioAnalysis || motionLabAudioProjectId !== state.project?.id ||
      Number(motionLabAudioAnalysis.fps) !== Number(state.project?.animation?.fps);
    motionStudioUpdateChannelButtons();
  }
  async function motionLabUseProjectSoundtrack() {
    const projectId = state.project?.id;
    const soundtrack = projectMediaAssets('soundtrack')[0];
    if (!projectId || !soundtrack || animationMode() !== '3d' ||
        motionLabSoundtrackBusy || motionLabBusy) return;
    // Prevent an in-flight selection from replacing another project or WAV.
    const token = projectAudioRestoreGeneration;
    motionLabSoundtrackBusy = true;
    motionLabSoundtrackStatus = '';
    renderProjectMedia();
    try {
      const response = await api('/api/animation/projects/' + encodeURIComponent(projectId) +
        '/motion-lab/use-soundtrack', {method:'POST'});
      if (state.project?.id !== projectId || token !== projectAudioRestoreGeneration) return;
      const sha = response.asset?.sha256;
      if (!/^[a-f0-9]{64}$/.test(String(sha || '')) ||
          response.analysis?.source_sha256 !== sha) {
        throw new Error('The host did not return a valid saved Motion Lab WAV.');
      }
      // The recovered WAV is now a project asset. Reuse the W2 loader, which
      // restores waveform, manual cues, markers, spectrum and sound channels.
      await restoreProjectMedia({preferredWav:sha});
      if (state.project?.id !== projectId) return;
      if (motionLabAudioProjectId !== projectId ||
          motionLabAudioAnalysis?.source_sha256 !== sha) {
        throw new Error('The analyzed soundtrack could not be restored into Motion Studio.');
      }
      const filename = response.soundtrack?.filename || soundtrack.filename;
      motionLabSoundtrackStatus = 'Loaded project soundtrack: ' + filename +
        (response.converted_to_pcm ? ' (converted to PCM WAV on host).' :
          ' (original PCM WAV).') +
        ' Export soundtrack and saved synchronization offset are unchanged.';
      const info = qs('#animation-motion-lab-audio-info');
      if (info) info.textContent = motionLabSoundtrackStatus;
      toast('Project soundtrack loaded', filename + ' is ready in Motion Studio.', 'success');
    } catch (error) {
      if (state.project?.id !== projectId) return;
      motionLabSoundtrackStatus = 'Could not use saved soundtrack: ' +
        (error?.message || String(error));
      toast('Project soundtrack unavailable', error?.message || String(error), 'error');
    } finally {
      motionLabSoundtrackBusy = false;
      if (state.project?.id === projectId) renderProjectMedia();
    }
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
    // A manual selection wins over any in-flight automatic project restore.
    const uploadToken = ++projectAudioRestoreGeneration;
    motionLabEditedEvents = null;
    motionDirectorCues = [];
    motionStudioChannelState = {projectId: '', sha: '', channels: [], dirty: false};
    ++motionStudioSpectrumToken;
    motionStudioSpectrum = {projectId:'',sha:'',points:[],maxHz:20000,loading:false,error:''};
    motionStudioBandPreview = {projectId:'',sha:'',fps:0,frames:0,ranges:'',bands:null};
    motionStudioSelectedChannel = '';
    motionStudioRenderChannels();
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
      const matchLength = qs('#animation-motion-lab-audio-match-length');
      const lengthStatus = qs('#animation-motion-lab-audio-length-status');
      if (lengthStatus) lengthStatus.textContent =
        'Audio ' + Number(analysis.duration_seconds).toFixed(2) + 's · project ' +
        (Number(state.project.animation.max_frames) / Number(state.project.animation.fps)).toFixed(2) +
        's at ' + state.project.animation.fps + ' FPS.';
      if (matchLength?.checked) {
        // Never silently retime recorded per-frame camera velocities.
        // Change only frame count; leave FPS untouched.
        const fps = Number(state.project.animation.fps);
        const targetFrames = Math.ceil(Number(analysis.duration_seconds) * fps - 1e-9);
        if (!Number.isInteger(targetFrames) || targetFrames < 1 || targetFrames > 3000) {
          throw new Error('Audio needs ' + targetFrames +
            ' frames at ' + fps + ' FPS. Motion Lab supports at most 3000 frames; choose a shorter WAV or lower FPS manually.');
        }
        if (targetFrames !== Number(state.project.animation.max_frames)) {
          // The UI reports DRAFT layers. Saved Motion Lab authoring metadata
          // can still exist after all visible draft layers were cleared.
          // Never discard that invisible saved history without explicit consent.
          if (motionLabDraftLayers.length) {
            throw new Error('Cannot resize with ' + motionLabDraftLayers.length +
              ' draft Motion Lab layer(s). Clear the draft first. No settings were changed.');
          }
          const storedLayerCount = Array.isArray(state.project.motion_lab?.layers)
            ? state.project.motion_lab.layers.length : 0;
          let discardStoredMotionLab = false;
          if (storedLayerCount) {
            discardStoredMotionLab = await window.MorphorumDialog.confirm({
              title: 'Clear saved Motion Lab history?',
              message: 'The composer shows 0 draft layers, but this project still has ' +
                storedLayerCount + ' saved Motion Lab layer(s). Matching audio length requires ' +
                'clearing that saved authoring history. Existing camera schedules are preserved. ' +
                'Cancel to keep the stored layers and project duration unchanged.',
              confirmText: 'Clear Saved Layers',
              cancelText: 'Keep Layers',
              variant: 'danger',
            });
            if (!discardStoredMotionLab) {
              if (lengthStatus) lengthStatus.textContent =
                'Duration unchanged. Saved Motion Lab layers preserved.';
              return;
            }
          }
          const approved = await window.MorphorumDialog.confirm({
            title: 'Match project length to WAV?',
            message: 'Audio ' + Number(analysis.duration_seconds).toFixed(2) + 's. ' +
              'Change project from ' + state.project.animation.max_frames + ' to ' +
              targetFrames + ' frames at ' + fps +
              ' FPS? This saves current project edits and reanalyzes the WAV. FPS remains unchanged.',
            confirmText: 'Match & Save',
            cancelText: 'Keep Duration',
          });
          if (!approved) {
            if (lengthStatus) lengthStatus.textContent = 'Length matching canceled. Project unchanged.';
          } else {
            const editorFrames = qs('#animation-max-frames');
            if (!editorFrames) throw new Error('Cannot locate the Editor frame-count field.');
            const previous = editorFrames.value;
            editorFrames.value = String(targetFrames);
            try {
              const draft = collectProject();
              if (discardStoredMotionLab) {
                draft.motion_lab = {
                  ...(draft.motion_lab || {}),
                  layers: [],
                  base_tracks: null,
                  last_applied_tracks: null,
                };
              }
              const payload = await api('/api/animation/projects/' + encodeURIComponent(projectId), {
                method:'PUT',body:JSON.stringify(draft),
              });
              if (state.project?.id !== projectId) return;
              state.project = payload.project;
              fillForm();
              clearDirty();
              if (Number(state.project.animation.max_frames) !== targetFrames) {
                throw new Error('Saved project frame count differs from requested audio length.');
              }
              matchLength.checked = false;
              if (lengthStatus) lengthStatus.textContent = 'Matched ' + targetFrames +
                ' frames at ' + fps + ' FPS. WAV reanalysis in progress.';
              await motionLabAnalyzeAudio();
              return;
            } catch (error) {
              editorFrames.value = previous;
              throw error;
            }
          }
        }
      }
      if (!Array.isArray(analysis?.values) ||
          analysis.values.length !== Number(state.project.animation.max_frames) ||
          Number(analysis.fps) !== Number(state.project.animation.fps)) {
        throw new Error('Audio frame alignment changed; analyze again.');
      }
      if (!(await motionStudioHydrateEdits(projectId, analysis, () =>
        projectAudioRestoreGeneration === uploadToken))) return;
      motionLabAudioAnalysis = analysis;
      motionLabAudioProjectId = projectId;
      motionStudioRestoreChannels(projectId, analysis);
      motionLabAudioUrl = URL.createObjectURL(file);
      motionLabAudioElement = new Audio(motionLabAudioUrl);
      motionLabAudioElement.preload = 'auto';
      motionLabAudioElement.load();
      motionStudioConnectAudioTransport();
      motionLabAudioSyncStatus('Ready to play with Motion Curves playback.');
      const peak = Math.max(0, ...motionLabAudioSignal());
      const thresholdField = qs('#animation-motion-lab-audio-threshold');
      if (thresholdField && peak > 0) {
        // File-specific starting point. Never require the user to guess the
        // analysis scale without seeing the envelope.
        thresholdField.value = Math.min(.1, peak * .55).toFixed(3);
      }
      motionLabStereoWaveform();
      motionDirectorPanel();
      motionLabAudioPreview();
      if (status) status.textContent = 'Analyzed ' + file.name + ': ' +
        analysis.values.length + ' frames · ' + analysis.duration_seconds.toFixed(2) +
        ' seconds · frame-aligned full-band RMS.';
      const badge = qs('#animation-motion-lab-audio-status');
      if (badge) badge.textContent = 'WAV ready';
      void restoreProjectMedia();
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
      envelope:(qs('#animation-motion-lab-audio-band')?.value === 'fullband'
        ? analysis.values : analysis.bands?.[qs('#animation-motion-lab-audio-band')?.value])?.slice() || [],
      band:qs('#animation-motion-lab-audio-band')?.value || 'fullband',
      detection:qs('#animation-motion-lab-audio-detection')?.value || 'level',
      sensitivity:read('sensitivity'),threshold,distance,
      attack_frames:attack,release_frames:release,cooldown_frames:3,offset_frames:0,
    };
    motionLabDraftLayers.push(layer);
    motionLabEditingIndex = -1;
    commitMotionLabDraft();
    motionLabNotify('Audio motion draft layer added. Preview Curves before Apply.');
    void motionLabPreviewOrApply(false,{curvesOnly:true});
  }
  const MOTION_RECORD_DEFAULT_LIMITS = {
    translation_x:.12, translation_y:.12, translation_z:.12,
    rotation_x:2, rotation_y:2, rotation_z:2,
  };
  function motionLabSyncRecordingLimits() {
    const limits = state.project?.motion_lab?.limits || {};
    qsa('[data-motion-record-limit]').forEach(input => {
      const axis = input.dataset.motionRecordLimit;
      input.value = String(limits[axis] ?? MOTION_RECORD_DEFAULT_LIMITS[axis]);
    });
    const status = qs('#animation-motion-record-limits-status');
    if (status) status.textContent = 'Limits loaded from project (translation: units/frame, rotation: degrees/frame).';
  }
  function motionLabChangeRecordingLimit(input) {
    if (!state.project || motionLabBusy || motionLabRecorder?.active) return;
    const axis = input.dataset.motionRecordLimit;
    if (!(axis in MOTION_RECORD_DEFAULT_LIMITS)) return;
    const value = Number(input.value);
    if (!input.value.trim() || !Number.isFinite(value) ||
        value < .00001 || value > 30) {
      input.value = String(state.project.motion_lab?.limits?.[axis] ??
        MOTION_RECORD_DEFAULT_LIMITS[axis]);
      toast('Invalid safety limit','Choose a value between 0.00001 and 30.','warning');
      return;
    }
    const lab = state.project.motion_lab || {};
    state.project.motion_lab = {
      ...lab, limits: {
        ...MOTION_RECORD_DEFAULT_LIMITS, ...(lab.limits || {}), [axis]:value,
      },
    };
    const status = qs('#animation-motion-record-limits-status');
    if (status) status.textContent = 'Project safety limits changed. Save or Apply to persist them.';
    markDirty({validate:false});
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
        if (control.matches('[data-motion-record-axis], [data-motion-record-invert], [data-motion-record-limit]') ||
            control.closest('.animation-motion-recording-controls')) {
          control.disabled = !ready || active;
        }
      });
    motionLabPunchUi();
    const units = qs('#animation-motion-record-unit-help');
    const fps = Number(state.project?.animation?.fps || 24);
    const move = Number(qs('#animation-motion-lab-record-translation')?.value || .025);
    const angle = Number(qs('#animation-motion-lab-record-rotation')?.value || .5);
    if (units) units.textContent = 'Sensitivity is per frame. At ' + fps +
      ' FPS, full input is up to ' + (move * fps).toFixed(3) +
      ' scene units/second or ' + (angle * fps).toFixed(2) +
      ' degrees/second before smoothing and safety limits.';
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
          window.MorphorumMotionLabSplicePunchIn(existing, take,
            {featherFrames:context.featherFrames});
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
    const featherFrames = Number(qs('#animation-motion-lab-punch-feather')?.value);
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
      punch = {index, id:target.id, snapshot:JSON.stringify(target), endFrame,
        featherFrames};
    }

    if (!Number.isInteger(startFrame) || startFrame < 0 || startFrame >= count ||
        !Number.isFinite(translationScale) || translationScale <= 0 ||
        !Number.isFinite(rotationScale) || rotationScale <= 0 ||
        !Number.isFinite(deadzone) || deadzone < 0 || deadzone > .5 ||
        !Number.isFinite(response) || response < .05 || response > 1 ||
        !Number.isInteger(tailFrames) || tailFrames < 0 || tailFrames > 12 ||
        !Number.isInteger(featherFrames) || featherFrames < 0 || featherFrames > 12) {
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
    motionLabSyncRecordingLimits();
    renderMotionLabDraft();
  }
  function renderMotionLabDraft() {
    motionReviewRefreshTakes();
    const project = state.project;
    const is3d = animationMode() === '3d';
    const ready = Boolean(project && is3d && !motionLabBusy);
    const count = Number(project?.animation?.max_frames || 120);
    motionLabRecordingUi();
    motionLabAudioUi();
    motionStudioRenderArrangement();
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
        : layer.type === 'audio_channels'
        ? (index + 1) + '. Sound channels · ' +
          (layer.channel_document?.channels?.length || 0) + ' channel(s) · additive · ' +
          layer.start_frame + '–' + (layer.end_frame - 1)
        : layer.type === 'audio_cues'
        ? (index + 1) + '. Audio Motion Director · ' +
          (layer.cue_document?.cues?.length || 0) + ' cue(s) · additive · ' +
          layer.start_frame + '–' + (layer.end_frame - 1)
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
        if (layer.type === 'audio_channels') {
          motionLabEditingIndex = -1;
          showAnimationTab('audio');
          motionLabNotify('Edit this sound channel layer in Motion Studio, then Preview or Apply.');
          return;
        }
        if (layer.type === 'audio_cues') {
          motionLabEditingIndex = -1;
          showAnimationTab('audio');
          motionLabNotify('Edit this Director layer in Motion Studio, then Save and Preview.');
          return;
        }
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
    motionLabBusyAction = apply ? 'apply' : curvesOnly ? 'curves' : 'preview';
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
      motionLabBusyAction = null;
      renderMotionLabDraft();
    }
  }

  // Motion Lab is first-class; unfinished hybrid Media controls remain mounted
  // in a non-navigable vault so existing project and API semantics stay intact.
  // Audio Motion is a dedicated Motion Lab workspace using the same draft
  // camera layers, project, and render controls.
  const ANIMATION_TAB_KEY = 'morphorum.animation.workspaceTab.v1';
  const VISIBLE_ANIMATION_TABS = ['motion', 'wizard', 'projects', 'editor', 'composer', 'recording', 'curves', 'preview', 'motion-import', 'audio', 'monitor', 'outputs'];
  const MOTION_LAB_TOOL_TABS = new Set(['motion', 'composer', 'recording', 'curves', 'preview', 'audio']);
  let animationTab = 'motion';
  let projectWizard = null;
  function showAnimationTab(name, { persist = true } = {}) {
    if (!VISIBLE_ANIMATION_TABS.includes(name)) name = 'motion';
    if (name !== 'curves') motionLabVisual?.pause();
    if (name !== 'preview') motionFramePlayer?.pause();
    if (name !== 'recording' && motionLabRecorder?.active) motionLabStopRecording('tab-change');
    animationTab = name;
    if (name === 'wizard') void projectWizard?.open();
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
    qsa('#motion-lab-sidebar [data-motion-nav]').forEach(button => {
      const selected = button.dataset.motionNav === name;
      button.classList.toggle('active', selected);
      if (selected) button.setAttribute('aria-current', 'page');
      else button.removeAttribute('aria-current');
    });
    // This dock is the same set of real buttons on every Motion Lab page.
    // Moving one element (not cloning it) keeps actions and status coherent.
    const dock = qs('#animation-motion-lab-quick-actions');
    if (dock && MOTION_LAB_TOOL_TABS.has(name)) {
      qs('#animation-panel-' + name)?.appendChild(dock);
    }
    if (dock) dock.hidden = !MOTION_LAB_TOOL_TABS.has(name);
    if (persist) try { localStorage.setItem(ANIMATION_TAB_KEY, name); } catch (_) {}
  }

  // Deforum settings inspection, guarded camera import and soundtrack attachment.
  function setupDeforumMotionImport(panel) {
    if (!panel) return;
    panel.classList.add('animation-deforum-motion-import');
    panel.innerHTML = `
      <div class="card glass dmi-workspace">
        <div class="dmi-heading"><div><h2>Import Deforum Motion Settings</h2>
        <p class="muted">Inspect camera motion exported from <a href="https://github.com/chicodog530/Deforum-Motion-Studio" target="_blank" rel="noopener noreferrer">Deforum Motion Studio</a> or Deforum. Nothing is applied during this preview.</p></div></div>
        <div class="dmi-source">
          <label>Deforum settings (.txt / .json) <input type="file" accept=".txt,.json,application/json,text/plain" data-dmi-file></label>
          <span class="muted" data-dmi-status>Select an existing project, then choose exported settings.</span>
        </div>
        <div data-dmi-results hidden>
          <div data-dmi-summary class="dmi-summary"></div>
          <div data-dmi-warnings class="dmi-warnings"></div>
          <div class="dmi-chart-head"><strong>Camera motion curves</strong><label>Axis <select data-dmi-axis><option value="translation_z">Depth Z</option>
            <option value="rotation_z">Roll Z</option><option value="translation_x">Translation X</option>
            <option value="translation_y">Translation Y</option><option value="rotation_x">Pitch X</option>
            <option value="rotation_y">Yaw Y</option></select></label></div>
          <svg data-dmi-chart viewBox="0 0 800 210" role="img" aria-label="Selected imported camera motion curve"></svg>
          <div class="dmi-audio"><strong>Optional soundtrack synchronization</strong>
            <div class="dmi-soundtrack-ref">
              <label>Referenced soundtrack path <input data-dmi-source-path type="text" readonly placeholder="No soundtrack path in settings"></label>
              <button type="button" data-dmi-copy-path class="secondary-button compact" disabled>Copy path</button>
              <button type="button" data-dmi-copy-folder class="secondary-button compact" disabled>Copy folder</button>
            </div>
            <p class="muted" data-dmi-path-note>Browsers cannot open a local file picker at an arbitrary path from imported settings. Copy the folder path to navigate there in your system's file picker.</p>
            <label>Choose local audio (WAV / MP3 / OGG / FLAC where supported) <input type="file" accept=".wav,.mp3,.ogg,.flac,audio/*" data-dmi-wav></label>
            <audio data-dmi-player controls preload="metadata"></audio>
            <div class="dmi-align"><label>Audio offset (seconds) <input type="number" data-dmi-offset step=".01" min="-30" max="30" value="0"></label>
              <label>Motion playhead (seconds) <input type="range" data-dmi-seek min="0" max="1" value="0" step=".01"></label>
              <output data-dmi-sync>0.00s</output></div>
            <canvas data-dmi-waveform width="900" height="120" aria-label="Local WAV amplitude overview"></canvas>
            <p data-dmi-length class="muted">The soundtrack path from the imported settings is informational only.</p>
            <div class="dmi-apply-actions"><button type="button" class="secondary-button compact" data-dmi-attach>Attach selected audio to project</button>
              <button type="button" class="secondary-button compact" data-dmi-save-offset>Save audio offset</button></div>
            <p data-dmi-attachment class="muted">Audio preview stays local until you explicitly attach it. Attached audio is frozen into new animation renders and muxed during MP4/WebM export; existing renders keep their original soundtrack snapshot.</p>
          </div>
          <div class="dmi-apply-review"><strong>Import camera motion into this project</strong>
            <div class="dmi-align">
              <label>Camera compatibility <select data-dmi-conversion>
                <option value="deforum">Deforum compatible (scaled translation)</option>
                <option value="raw">Raw source values (legacy)</option>
              </select></label>
              <div class="dmi-strength-control"><label>Translation strength <input type="number" data-dmi-translation-strength min="0" max="400" step="5" value="100" style="width:5.5rem">%</label>
                <input type="range" data-dmi-translation-slider min="0" max="400" step="5" value="100" aria-label="Translation strength percent" style="width:100%">
                <div class="dmi-apply-actions"><button type="button" class="secondary-button compact" data-dmi-translation-reset>Reset 100%</button><button type="button" class="secondary-button compact" data-dmi-translation-tested>Tested 200%</button></div></div>
              <div class="dmi-strength-control"><label>Rotation strength <input type="number" data-dmi-rotation-strength min="0" max="400" step="5" value="100" style="width:5.5rem">%</label>
                <input type="range" data-dmi-rotation-slider min="0" max="400" step="5" value="100" aria-label="Rotation strength percent" style="width:100%">
                <div class="dmi-apply-actions"><button type="button" class="secondary-button compact" data-dmi-rotation-reset>Reset 100%</button><button type="button" class="secondary-button compact" data-dmi-rotation-tested>Tested 200%</button></div></div>
            </div>
            <p class="muted">Deforum translation uses a 1/200 scale and X/Z sign inversion. This is an initial camera compatibility mapping, not exact renderer parity. 100% is the Deforum conversion baseline; 200% matches the previously successful test. Up to 400% is experimental.</p>
            <details><summary>Review original vs converted schedules</summary><pre data-dmi-converted style="white-space:pre-wrap;overflow-wrap:anywhere">Review safe import to show converted schedules.</pre></details>
            <p class="muted">This replaces six camera schedules only. It does not change FPS, cadence, frames, model, prompts or audio. Projects with existing Motion Lab layers require a clean project instead.</p>
            <div class="dmi-apply-actions"><button type="button" class="secondary-button compact" data-dmi-prepare>Review safe import</button>
              <button type="button" class="primary-button compact" data-dmi-apply disabled>Apply camera motion</button></div>
            <p data-dmi-review class="muted">Review is required before Apply. Your project remains unchanged until confirmation.</p>
          </div>
        </div>
      </div>`;
    const file=panel.querySelector('[data-dmi-file]');
    const status=panel.querySelector('[data-dmi-status]');
    const results=panel.querySelector('[data-dmi-results]');
    const axis=panel.querySelector('[data-dmi-axis]');
    const graph=panel.querySelector('[data-dmi-chart]');
    const player=panel.querySelector('[data-dmi-player]');
    const wav=panel.querySelector('[data-dmi-wav]');
    const sourcePath=panel.querySelector('[data-dmi-source-path]');
    const copyPath=panel.querySelector('[data-dmi-copy-path]');
    const copyFolder=panel.querySelector('[data-dmi-copy-folder]');
    const pathNote=panel.querySelector('[data-dmi-path-note]');
    const directoryOf=path=>String(path||'').replace(/[\\/][^\\/]*$/, '');
    const copyText=async text=>{
      if (!text) return;
      try {
        if (navigator.clipboard?.writeText) await navigator.clipboard.writeText(text);
        else {
          const temporary=document.createElement('textarea');
          temporary.value=text;temporary.readOnly=true;
          temporary.style.position='fixed';temporary.style.left='-9999px';
          document.body.appendChild(temporary);temporary.select();
          if (!document.execCommand('copy')) throw new Error('Clipboard unavailable');
          temporary.remove();
        }
        pathNote.textContent='Copied. Paste the path into your file picker’s address bar to find the soundtrack.';
      } catch(error) {
        sourcePath.focus();sourcePath.select();
        pathNote.textContent='Clipboard permission unavailable. The path is selected for manual copying.';
      }
    };
    copyPath.addEventListener('click',()=>copyText(sourcePath.value));
    copyFolder.addEventListener('click',()=>copyText(directoryOf(sourcePath.value)));
    const lengthText=panel.querySelector('[data-dmi-length]');
    const offset=panel.querySelector('[data-dmi-offset]');
    const seek=panel.querySelector('[data-dmi-seek]');
    const sync=panel.querySelector('[data-dmi-sync]');
    let report=null, objectUrl=null, wavDuration=0, sourceContent=null, sourceFilename='', prepared=null;
    const prepareButton=panel.querySelector('[data-dmi-prepare]');
    const applyButton=panel.querySelector('[data-dmi-apply]');
    const attachButton=panel.querySelector('[data-dmi-attach]');
    const offsetButton=panel.querySelector('[data-dmi-save-offset]');
    const attachmentText=panel.querySelector('[data-dmi-attachment]');
    attachButton.disabled=true;
    offsetButton.disabled=true;
    const attachmentProject=()=>state.project?.id;
    attachButton.addEventListener('click',async()=>{
      const chosen=wav.files?.[0],projectId=attachmentProject();
      if(!chosen || !projectId)return;
      if(chosen.size>40*1024*1024){
        progress('Soundtrack too large','Attachments must be 40 MiB or smaller.','error');return;
      }
      attachButton.disabled=true;
      progress('Attaching soundtrack',chosen.name+' · saving a project-owned copy.');
      try {
        const response=await fetch('/api/animation/projects/'+encodeURIComponent(projectId)+'/motion-import/soundtrack',{
          method:'POST',
          headers:{'Content-Type':'application/octet-stream',
            'X-Audio-Filename':encodeURIComponent(chosen.name),
            'X-Audio-Offset-Seconds':String(Number(offset.value)||0)},
          body:chosen,
        });
        const result=await response.json();
        if(!response.ok)throw new Error(typeof result.detail==='string'?result.detail:'Upload failed ('+response.status+').');
        if(attachmentProject()!==projectId)return;
        attachmentText.textContent='Attached: '+result.soundtrack.filename+
          ' · offset '+result.soundtrack.offset_seconds.toFixed(2)+'s.';
        offsetButton.disabled=false;
        void restoreProjectMedia();
        progress('Soundtrack attached',result.soundtrack.filename+' saved. New renders will freeze it for video export.','success');
      }catch(error){
        attachmentText.textContent='Attachment failed: '+error.message;
        progress('Soundtrack attachment failed',error.message,'error');
      }finally{attachButton.disabled=false;}
    });
    offsetButton.addEventListener('click',async()=>{
      const projectId=attachmentProject();
      if(!projectId)return;
      offsetButton.disabled=true;
      progress('Saving audio offset','Updating soundtrack synchronization metadata.');
      try{
        const result=await api('/api/animation/projects/'+encodeURIComponent(projectId)+'/motion-import/soundtrack-offset',{
          method:'PUT',body:JSON.stringify({offset_seconds:Number(offset.value)}),
        });
        if(attachmentProject()!==projectId)return;
        attachmentText.textContent='Attached: '+result.soundtrack.filename+
          ' · offset '+result.soundtrack.offset_seconds.toFixed(2)+'s.';
        void restoreProjectMedia();
        progress('Audio offset saved',result.soundtrack.offset_seconds.toFixed(2)+' seconds.','success');
      }catch(error){progress('Audio offset save failed',error.message,'error');}
      finally{offsetButton.disabled=false;}
    });
    const review=panel.querySelector('[data-dmi-review]');
    const conversion=panel.querySelector('[data-dmi-conversion]');
    const translationStrength=panel.querySelector('[data-dmi-translation-strength]');
    const rotationStrength=panel.querySelector('[data-dmi-rotation-strength]');
    const convertedText=panel.querySelector('[data-dmi-converted]');
    const translationSlider=panel.querySelector('[data-dmi-translation-slider]');
    const rotationSlider=panel.querySelector('[data-dmi-rotation-slider]');
    const conversionSettings=()=>({
      mode:conversion.value,
      translation_strength:Number(translationStrength.value)/100,
      rotation_strength:Number(rotationStrength.value)/100,
    });
    const progress=(heading,message,kind='info')=>toast(heading,message,kind);
    const invalidatePrepared=()=>{
      prepared=null;applyButton.disabled=true;
      convertedText.textContent='Review safe import to show converted schedules.';
      review.textContent='Review is required before Apply. No project changes have been made.';
    };
    const syncStrength=(field,slider,value)=>{
      const clamped=Math.max(0,Math.min(400,Math.round(value)));
      field.value=String(clamped);
      slider.value=String(clamped);
      invalidatePrepared();
    };
    for(const [field,slider,key] of [
      [translationStrength,translationSlider,'translation'],
      [rotationStrength,rotationSlider,'rotation'],
    ]){
      slider.addEventListener('input',()=>syncStrength(field,slider,Number(slider.value)));
      field.addEventListener('input',()=>{
        invalidatePrepared();
        if(field.value!=='' && Number.isFinite(Number(field.value))){
          slider.value=String(Math.max(0,Math.min(400,Number(field.value))));
        }
      });
      field.addEventListener('change',()=>syncStrength(field,slider,Number(field.value)));
      panel.querySelector('[data-dmi-'+key+'-reset]').addEventListener('click',()=>syncStrength(field,slider,100));
      panel.querySelector('[data-dmi-'+key+'-tested]').addEventListener('click',()=>syncStrength(field,slider,200));
    }
    conversion.addEventListener('change',invalidatePrepared);
    prepareButton.addEventListener('click',async()=>{
      invalidatePrepared();
      if(![translationStrength,rotationStrength].every(input=>
        input.value!=='' && Number.isFinite(Number(input.value)) &&
        Number(input.value)>=0 && Number(input.value)<=400
      )){
        review.textContent='Strength must be from 0% to 400% for both camera controls.';
        progress('Invalid camera strength',review.textContent,'warning');
        return;
      }
      if (!state.project?.id || !sourceContent) return;
      if (state.dirty) {
        review.textContent='Save or discard unsaved Project Editor changes before preparing the import.';
        progress('Import review blocked',review.textContent,'warning');
        return;
      }
      const projectId=state.project.id;
      prepareButton.disabled=true;
      review.textContent='Checking import compatibility…';
      progress('Reviewing motion import','Validating schedules, project timing and existing layers.');
      try {
        const result=await api('/api/animation/projects/'+encodeURIComponent(projectId)+'/motion-import/prepare',{
          method:'POST',body:JSON.stringify({
            content:sourceContent,filename:sourceFilename,conversion:conversionSettings(),
          }),
        });
        if(state.project?.id!==projectId) return;
        convertedText.textContent=Object.entries(result.converted_schedules||{}).map(([axis,schedule])=>{
          const sourceAxis=axis.startsWith('rotation_')?'rotation_3d_'+axis.split('_')[1]:axis;
          let original='Unavailable';
          try {original=String(JSON.parse(sourceContent)?.[sourceAxis]??'Unavailable');}
          catch (_) {original='Unavailable';}
          return axis+'\n  Deforum: '+original+'\n  Morphorum: '+schedule;
        }).join('\n\n');
        prepared={...result,projectId};
        applyButton.disabled=false;
        review.textContent='Safe import prepared: '+result.changed_axes.join(', ')+
          '. Existing timing and all non-camera project settings remain unchanged.';
        progress('Motion import ready', 'Six camera axes validated; review the changes before applying.','success');
      }catch(error){
        review.textContent='Import blocked: '+error.message;
        progress('Motion import blocked',error.message,'error');
      }finally{prepareButton.disabled=false;}
    });
    applyButton.addEventListener('click',async()=>{
      const ready=prepared;
      if(!ready || state.dirty || ready.projectId!==state.project?.id) {
        invalidatePrepared();return;
      }
      const approved=await window.MorphorumDialog.confirm({
        title:'Replace six camera schedules?',
        message:'This will replace all six native 3D camera motion schedules using the reviewed '+ready.conversion.mode+' conversion. Existing FPS, frame count, cadence, prompts, model and soundtrack stay unchanged. This cannot be undone from this dialog.',
        confirmText:'Apply Imported Motion',cancelText:'Cancel',variant:'default',
      });
      if (!approved) return;
      applyButton.disabled=true;
      review.textContent='Applying imported camera schedules…';
      progress('Applying motion','Saving six validated camera schedules to the project.');
      try{
        const result=await api('/api/animation/projects/'+encodeURIComponent(ready.projectId)+'/motion-import/apply',{
          method:'POST',body:JSON.stringify({
            content:sourceContent,filename:sourceFilename,
            source_sha256:ready.source_sha256,project_sha256:ready.project_sha256,
            conversion:ready.conversion,conversion_sha256:ready.conversion_sha256,
          }),
        });
        if(state.project?.id!==ready.projectId)return;
        state.project=result.project;
        state.dirty=false;
        fillForm();
        await loadTimeline();
        review.textContent='Imported six camera schedules. Project saved.';
        toast('Motion imported','Six native camera schedules updated.','success');
      }catch(error){
        review.textContent='Apply failed: '+error.message;
        progress('Motion apply failed',error.message,'error');
      }finally{invalidatePrepared();}
    });
    const draw=()=>{
      if (!report) return;
      const values=report.samples.map(s=>Number(s[axis.value])||0);
      const low=Math.min(...values),high=Math.max(...values);
      const range=Math.max(1e-6,high-low);
      const d=values.map((v,i)=>(i?'L':'M')+(i*790/Math.max(1,values.length-1)+5).toFixed(2)+' '+
        (190-(v-low)/range*170).toFixed(2)).join(' ');
      graph.replaceChildren();
      const ns='http://www.w3.org/2000/svg';
      const path=document.createElementNS(ns,'path');
      path.setAttribute('d',d);path.setAttribute('fill','none');
      path.setAttribute('stroke','#79c8ed');path.setAttribute('stroke-width','2.4');
      graph.appendChild(path);
      const ruler=document.createElementNS(ns,'text');
      ruler.setAttribute('x','9');ruler.setAttribute('y','14');
      ruler.setAttribute('font-size','12');ruler.setAttribute('fill','currentColor');
      ruler.textContent=axis.value.replaceAll('_',' ')+' · '+low.toFixed(4)+' to '+high.toFixed(4);
      graph.appendChild(ruler);
    };
    const updateSync=()=>{
      if (!report) return;
      const motionTime=Number(seek.value)||0;
      const delay=Number(offset.value)||0;
      if (player.src && Number.isFinite(player.duration)) {
        player.currentTime=Math.max(0,Math.min(player.duration,motionTime+delay));
      }
      sync.textContent='Motion '+motionTime.toFixed(2)+'s · audio '+Math.max(0,motionTime+delay).toFixed(2)+'s';
    };
    file.addEventListener('change',async()=>{
      const selected=file.files?.[0];
      if (!selected) return;
      if (!state.project?.id) {status.textContent='Open a project before inspecting settings.';progress('Choose a project',status.textContent,'warning');return;}
      if(selected.size>1024*1024){status.textContent='Settings exceed 1 MiB.';progress('Settings too large',status.textContent,'error');return;}
      invalidatePrepared();sourceContent=null;sourceFilename='';
      status.textContent='Inspecting Deforum motion…';results.hidden=true;
      progress('Loading Deforum settings',selected.name+' · reading and validating motion tracks.');
      try{
        const response=await api('/api/animation/projects/'+encodeURIComponent(state.project.id)+'/motion-import/preview',{
          method:'POST',body:JSON.stringify({content:await selected.text(),filename:selected.name}),
        });
        sourceContent=await selected.text();sourceFilename=selected.name;
        report=response;results.hidden=false;
        // Attachment metadata belongs to this project, not the exported path.
        try {
          const stored=await api('/api/animation/projects/'+encodeURIComponent(state.project.id)+
            '/motion-import/soundtrack');
          if (stored?.soundtrack) {
            const attachment=stored.soundtrack;
            offset.value=String(attachment.offset_seconds);
            attachmentText.textContent='Attached: '+attachment.filename+
              ' · saved offset '+Number(attachment.offset_seconds).toFixed(2)+'s.';
            offsetButton.disabled=false;
          } else {
            attachmentText.textContent='No project soundtrack attached. Choose audio and attach explicitly.';
            offsetButton.disabled=true;offset.value='0';
          }
        } catch(error) {
          attachmentText.textContent='Could not load saved soundtrack status: '+error.message;
          offsetButton.disabled=true;
        }
        const source=response.source,compare=response.project_comparison;
        const embeddedPath=String(source.soundtrack_path||'');
        sourcePath.value=embeddedPath;
        copyPath.disabled=!embeddedPath;
        copyFolder.disabled=!directoryOf(embeddedPath);
        pathNote.textContent=embeddedPath
          ? 'Referenced by the export only. The browser cannot set this folder as the default browse location; use Copy folder and paste it into your file picker’s address bar.'
          : 'No soundtrack path in these settings. Choose a local audio file to inspect synchronization.';
        wav.title=source.soundtrack_filename
          ? 'Look for '+source.soundtrack_filename+' when browsing for soundtrack audio'
          : 'Choose an audio file';
        const summary=panel.querySelector('[data-dmi-summary]');
        summary.replaceChildren();
        for(const [label,value] of [['Source FPS',source.fps],['Source frames',source.max_frames],
          ['Source cadence',source.cadence??'Scheduled'],['Duration',source.duration_seconds.toFixed(2)+'s'],
          ['Project FPS',compare.fps],['Project frames',compare.max_frames]]){
          const item=document.createElement('div');item.className='dmi-stat';
          const strong=document.createElement('strong');strong.textContent=String(value);
          const small=document.createElement('span');small.textContent=label;
          item.append(small,strong);summary.appendChild(item);
        }
        const warnings=panel.querySelector('[data-dmi-warnings]');
        warnings.replaceChildren();
        for(const message of response.warnings){
          const p=document.createElement('p');p.textContent=message;warnings.appendChild(p);
        }
        status.textContent=selected.name+' · '+(response.can_apply_unchanged?'Timing matches project':'Timing requires review');
        progress('Settings loaded',status.textContent,'success');
        seek.max=String(source.duration_seconds);seek.value='0';draw();updateSync();
        lengthText.textContent='Settings soundtrack: '+(source.soundtrack_filename||'none')+
          '. Choose the local audio file manually to inspect alignment. Embedded paths are never accessed automatically.';
      }catch(error){status.textContent='Preview failed: '+error.message;report=null;results.hidden=true;
        progress('Settings preview failed',error.message,'error');}
    });
    axis.addEventListener('change',draw);
    const syncChange=()=>updateSync();
    seek.addEventListener('input',syncChange);offset.addEventListener('input',syncChange);
    wav.addEventListener('change',async()=>{
      const selected=wav.files?.[0];if(!selected)return;
      if(objectUrl) URL.revokeObjectURL(objectUrl);
      attachButton.disabled=false;
      objectUrl=URL.createObjectURL(selected);player.src=objectUrl;
      progress('Loading soundtrack',selected.name+' · preparing waveform and playback.');
      player.onloadedmetadata=()=>{
        wavDuration=player.duration;
        lengthText.textContent='Audio '+wavDuration.toFixed(2)+'s · motion '+
          Number(report?.source?.duration_seconds||0).toFixed(2)+'s. Adjust audio offset for synchronization.';
        updateSync();
        progress('Soundtrack ready',selected.name+' · '+wavDuration.toFixed(2)+' seconds.','success');
      };
      // Local amplitude overview, no upload or server-side filesystem mutation.
      try {
        if(selected.size>40*1024*1024)throw new Error('Audio exceeds 40 MiB waveform preview limit.');
        const ctx=new (window.AudioContext||window.webkitAudioContext)();
        try {
          const buffer=await ctx.decodeAudioData(await selected.arrayBuffer());
          const channel=buffer.getChannelData(0);
          const canvas=panel.querySelector('[data-dmi-waveform]');
          const c=canvas.getContext('2d');c.clearRect(0,0,canvas.width,canvas.height);
          c.strokeStyle='#79c8ed';c.beginPath();
          for(let x=0;x<canvas.width;x++){
            const start=Math.floor(x*channel.length/canvas.width);
            const end=Math.min(channel.length,Math.floor((x+1)*channel.length/canvas.width));
            let peak=0;
            for(let i=start;i<end;i++) peak=Math.max(peak,Math.abs(channel[i]));
            c.moveTo(x,60-peak*57);c.lineTo(x,60+peak*57);
          }
          c.stroke();
        } finally {await ctx.close();}
      }catch(error){lengthText.textContent='Audio waveform preview unavailable: '+error.message;
        progress('Waveform unavailable',error.message,'warning');}
    });
  }

  function setupAnimationWorkspaceTabs() {
    const layout = qs('#view-animation .animation-layout');
    const root = qs('#view-animation');
    const card = qs('#view-animation .animation-render-card');
    if (!layout || !root || !card) return;
    const nav = document.createElement('nav');
    nav.id = 'animation-workspace-nav';
    nav.className = 'animation-workspace-nav';
    nav.setAttribute('aria-label', 'Motion Lab workspaces');
    nav.setAttribute('role', 'tablist');
    const panels = {};
    const names = {
      motion: 'Overview', wizard: 'New Project Wizard', projects: 'Project Manager', editor: 'Project Editor',
      composer: 'Camera Composer', recording: 'Live Recording',
      curves: 'Motion Curves', preview: 'Camera Preview',
      'motion-import': 'Import Motion Settings', audio: 'Motion Studio', monitor: 'Render Monitor', outputs: 'Outputs',
    };
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
      panel.hidden = name !== 'motion';
      panels[name] = panel;
    }
    layout.parentNode.insertBefore(nav, layout);
    layout.parentNode.insertBefore(panels.editor, layout);
    panels.editor.appendChild(layout);
    let last = panels.editor;
    for (const name of ['motion', 'wizard', 'projects', 'composer', 'recording', 'curves', 'preview', 'motion-import', 'audio', 'monitor', 'outputs']) {
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
    // Motion Studio is a first-class workspace; reuse the existing Audio Motion DOM.
    const cards = [
      ['composer', '#animation-motion-lab-composer'],
      ['recording', '#animation-motion-lab-recording'],
      ['curves', '#animation-motion-lab-visual'],
      ['preview', '.animation-motion-preview-card'],
      ['audio', '#animation-motion-lab-audio'],
    ];
    for (const [name, selector] of cards) {
      const card = qs(selector);
      if (card) panels[name].appendChild(card);
    }

    // The landing page is a concise tool selector. Original controls live in
    // exactly one dedicated panel, never copied or recreated.
    const toolGrid = document.createElement('div');
    toolGrid.className = 'motion-lab-tool-grid';
    const toolCards = [
      ['wizard', 'New Project Wizard', 'Create a project step by step, with guided defaults and explanations.'],
      ['composer', 'Camera Motion Composer', 'Layer motion presets, timing, and blend settings.'],
      ['recording', 'Live Motion Recording', 'Perform and edit a six-axis camera take.'],
      ['curves', 'Motion Curves & Camera Path', 'Edit frame-aligned keyframes using the full-width plots.'],
      ['preview', 'Camera Motion Preview', 'Inspect 2D or 3D camera motion before rendering.'],
      ['motion-import', 'Import Motion Settings', 'Preview Deforum Motion Studio schedules and align soundtrack audio.'],
      ['audio', 'Motion Studio', 'Compose manual camera cues against music, edit beats and preview or apply motion to this project.'],
      ['monitor', 'Render Monitor', 'Watch progress, frame previews, and job diagnostics.'],
      ['projects', 'Project Manager', 'Search, review, rename, and safely archive your animation projects.'],
      ['editor', 'Project Editor', 'Configure projects, prompts, resolution, and timelines.'],
      ['outputs', 'Outputs', 'Review completed animations and export videos.'],
    ];
    for (const [name, title, description] of toolCards) {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'motion-lab-tool-card';
      button.dataset.motionOpen = name;
      const heading = document.createElement('strong');
      heading.textContent = title;
      const hint = document.createElement('span');
      hint.textContent = description;
      button.append(heading, hint);
      button.addEventListener('click', () => showAnimationTab(name));
      toolGrid.appendChild(button);
    }
    panels.motion.appendChild(toolGrid);
    if (window.MorphorumProjectWizard) {
      projectWizard = new window.MorphorumProjectWizard({
        panel: panels.wizard,
        onNavigate: async destination => {
          if (destination === 'before-save') {
            if (motionLabRecorder?.active || renderIsActive() || state.motionJobId ||
                motionPreviewStarting || animationRenderStarting) {
              toast('Finish the current job first',
                'Wait for recording, preview, or rendering to finish before switching projects.',
                'warning', 6500);
              return false;
            }
            if (state.dirty) {
              return window.MorphorumDialog.confirm({
                title: 'Create and open this wizard project?',
                message: 'Your currently open project has unsaved Editor changes. Saving this new project will switch away from those edits.',
                confirmText: 'Discard Editor Changes & Continue',
                cancelText: 'Keep Editing', variant: 'danger',
              });
            }
            return true;
          }
          const button = qs('.nav-button[data-view="' + destination + '"]');
          button?.click();
          return true;
        },
        onSaved: async id => {
          await loadProjectList();
          const opened = await loadProject(id, { confirmDirty: false });
          if (opened) showAnimationTab('editor');
          else showAnimationTab('projects');
        },
      });
    }
    setupProjectManager(panels.projects);
    for (const [name, label] of [
      ['composer', 'Camera Motion Composer'],
      ['recording', 'Live Motion Recording'],
      ['curves', 'Motion Curves & Camera Path'],
      ['preview', 'Camera Motion Preview'],
    ]) {
      const heading = document.createElement('div');
      heading.className = 'motion-tool-page-heading';
      const breadcrumb = document.createElement('div');
      const eyebrow = document.createElement('p');
      eyebrow.className = 'eyebrow';
      eyebrow.textContent = 'MOTION LAB / ' + label.toUpperCase();
      const title = document.createElement('h2');
      title.textContent = label;
      breadcrumb.append(eyebrow, title);
      const back = document.createElement('button');
      back.type = 'button';
      back.className = 'secondary-button compact';
      back.textContent = '← All Motion Lab Tools';
      back.addEventListener('click', () => showAnimationTab('motion'));
      heading.append(breadcrumb, back);
      panels[name].prepend(heading);
    }

    // Audio remains a Motion Lab tool. Provide the audio-specific workflow
    // without duplicating any input, API, or motion-layer state.
    const audioIntro = document.createElement('article');
    audioIntro.className = 'card glass animation-audio-workspace-intro';
    audioIntro.innerHTML = `
      <div class="animation-audio-workspace-heading">
        <div>
          <p class="eyebrow">MOTION LAB / MOTION STUDIO</p>
          <h2>Motion Studio: compose to your soundtrack</h2>
          <p class="muted">Analyze a WAV, select the beats you want, and add
          camera movement to your Motion Lab layers. Audio motion is part of
          the same project, not a separate animation or render.</p>
        </div>
        <button class="secondary-button compact" type="button"
          id="animation-audio-back-motion">← Motion Lab</button>
      </div>
      <div class="animation-audio-workflow">
        <span><strong>1</strong> Choose WAV and analyze</span>
        <span><strong>2</strong> Adjust beats and add a layer</span>
        <span><strong>3</strong> Review curves and apply motion</span>
      </div>
      <div class="animation-audio-workspace-actions">
        <button class="secondary-button compact" type="button"
          id="animation-audio-review-motion">Review Motion Curves</button>
        <button class="primary-button compact" type="button"
          id="animation-audio-apply" data-motion-quick-target="animation-motion-lab-apply"
          disabled>Apply to Animation</button>
        <span class="muted" id="animation-audio-workspace-status" role="status"
          aria-live="polite">Select a 3D animation project to begin.</span>
      </div>
    `;
    panels.audio.prepend(audioIntro);
    motionStudioCreateArrangementCard(panels.audio);
    motionStudioCreateChannelCard(panels.audio);
    // DA3 layout: wide analysis displays are independent of the compact
    // configuration card. Reparenting preserves existing element IDs,
    // event listeners, SVG rendering and draft-marker state.
    const analysisWorkspace = document.createElement('article');
    analysisWorkspace.id = 'animation-audio-analysis-workspace';
    analysisWorkspace.className = 'card glass animation-audio-analysis-workspace';
    const analysisHeading = document.createElement('div');
    analysisHeading.className = 'animation-audio-analysis-heading';
    analysisHeading.innerHTML = '<h2>Audio analysis & drum timeline</h2>' +
      '<p class="muted">Full-width envelope, stereo waveform, playback and marker editing.</p>';
    analysisWorkspace.appendChild(analysisHeading);
    const audioPreview = qs('#animation-motion-lab-audio-preview');
    if (audioPreview) {
      const legacyDetails = document.createElement('details');
      legacyDetails.className = 'animation-audio-legacy-envelope';
      legacyDetails.innerHTML = '<summary>Additional envelope diagnostics</summary>';
      legacyDetails.appendChild(audioPreview);
      analysisWorkspace.appendChild(legacyDetails);
    }
    panels.audio.appendChild(analysisWorkspace);
    // Parseq-inspired workflow: source first, full-width waveform next,
    // detection and motion response below. Keep original live controls.
    const audioSourceDock = document.createElement('section');
    audioSourceDock.className = 'card glass animation-audio-source-dock';
    audioSourceDock.id = 'animation-audio-source-dock';
    audioSourceDock.innerHTML = '<div class="card-header"><div>' +
      '<h2>Audio Source</h2>' +
      '<p class="muted">Use the soundtrack already attached to this project, ' +
      'or select a WAV from your device. Start here before arranging motion.</p>' +
      '</div></div>';
    // Keep the actual file input, saved-soundtrack button and event handlers:
    // move the existing controls without cloning any element or creating new IDs.
    // This card stays immediately below the Motion Studio introduction.
    audioIntro.after(audioSourceDock);
    // DA3.3a: keep editable timeline and inspector together; separate configuration
    // into source, detection and camera-response groups without cloning controls.
    const audioCard = qs('#animation-motion-lab-audio');
    const controls = audioCard?.querySelector('.animation-motion-audio-controls');
    if (controls) {
      const fields = Array.from(controls.children);
      const sections = [
        ['Choose audio', fields.slice(0,2), true],
        ['Beat detection', [fields[2],fields[3],fields[4],fields[6]], false],
        ['Camera response', [fields[5],fields[7],fields[8],fields[9]], false],
      ];
      for (const [label, elements, opened] of sections) {
        const details = document.createElement('details');
        details.className = 'animation-audio-config-group';
        details.open = opened;
        const summary = document.createElement('summary');
        summary.textContent = label;
        const grid = document.createElement('div');
        grid.className = 'animation-audio-config-grid';
        for (const field of elements) if (field) grid.appendChild(field);
        details.append(summary,grid);
        controls.appendChild(details);
        if (label === 'Choose audio') {
          details.open = true;
          audioSourceDock.appendChild(details);
        }
      }
    }
    // Position source actions beside the file controls; camera/detection
    // tuning remains after the waveform rather than pushing it offscreen.
    const audioActions = audioCard?.querySelector('.animation-motion-recording-actions');
    if (audioActions) audioSourceDock.appendChild(audioActions);
    if (audioCard) panels.audio.appendChild(audioCard);
    const audioPlaceholder = document.createElement('div');
    audioPlaceholder.className = 'animation-audio-preview-placeholder';
    audioPlaceholder.innerHTML = '<strong>Beat analysis preview</strong><p>Choose a WAV file and select Analyze WAV. Your detected beats and audio levels will appear here before you add any motion.</p>';
    analysisWorkspace.querySelector('#animation-motion-lab-audio-preview')?.before(audioPlaceholder);
    qs('#animation-audio-back-motion')?.addEventListener('click', () => showAnimationTab('motion'));
    qs('#animation-audio-review-motion')?.addEventListener('click', () => showAnimationTab('curves'));
    qs('#animation-audio-apply')?.addEventListener('click', () => {
      const apply = qs('#animation-motion-lab-apply');
      if (apply && !apply.disabled) apply.click();
    });


    setupDeforumMotionImport(panels['motion-import']);
    motionLabSetupQuickActions(panels.motion);
    motionLabSyncQuickActions();
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
    let previous = 'motion';
    try { previous = localStorage.getItem(ANIMATION_TAB_KEY) || 'motion'; } catch (_) {}
    showAnimationTab(previous, { persist: false });
  }

  function bind() {
    motionReviewBind();
    motionCompareBind();
    motionRefineBind();
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
    qs('#animation-editor-open-project')?.addEventListener('click', () => showAnimationTab('projects'));
    qs('#animation-editor-create-project')?.addEventListener('click', () => showAnimationTab('wizard'));
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
    // Audio duration is only known after the browser loads the remote file's
    // metadata. Refresh the visible label without mutating project state.
    qs('#animation-media-soundtrack-player')?.addEventListener('loadedmetadata', renderProjectMedia);
    for (const id of ['animation-media-soundtrack-player', 'animation-media-wav-player']) {
      qs('#' + id)?.addEventListener('error', event => {
        const projectId = state.project?.id;
        if (!projectId || projectMedia.projectId !== projectId ||
            !event.target.currentSrc.includes('/projects/' + encodeURIComponent(projectId) + '/')) return;
        projectMediaWarning(id === 'animation-media-soundtrack-player'
          ? 'Attached soundtrack cannot be played in this browser. Check the audio file or its format.'
          : 'Saved Motion Lab WAV could not be played in this browser.');
        renderProjectMedia();
      });
    }
    qs('#animation-source-preview')?.addEventListener('error', event => {
      const id = state.project?.id;
      if (!id || !event.target.currentSrc.includes('/projects/' + encodeURIComponent(id) + '/')) return;
      if (projectMedia.projectId !== id) return;
      projectMedia.loading = false;
      projectMedia.assets = projectMedia.assets.filter(asset => asset.kind !== 'source_image');
      projectMediaWarning('Saved start image could not be decoded. Upload it again to repair the project.');
      renderProjectMedia();
    });
    qs('#animation-media-wav-select')?.addEventListener('change', event => {
      const checksum = event.target.value;
      if (!projectMediaAssets('motion_lab_wav').some(wav => wav.sha256 === checksum)) return;
      projectMedia.selectedWav = checksum;
      renderProjectMedia();
      void restoreSavedMotionWav(checksum);
    });
    qs('#animation-media-offset-save')?.addEventListener('click', async () => {
      const id = state.project?.id;
      const seconds = Number(qs('#animation-media-offset')?.value);
      if (!id || !Number.isFinite(seconds) || Math.abs(seconds) > 30) {
        toast('Invalid soundtrack offset', 'Choose an offset between -30 and 30 seconds.', 'warning');
        return;
      }
      const button = qs('#animation-media-offset-save');
      setBusy(button, true);
      try {
        const result = await api('/api/animation/projects/' + encodeURIComponent(id) +
          '/motion-import/soundtrack-offset', {
          method: 'PUT', body: JSON.stringify({ offset_seconds: seconds }),
        });
        if (state.project?.id !== id) return;
        projectMedia.soundtrack = result.soundtrack;
        renderProjectMedia();
        toast('Soundtrack offset saved', seconds.toFixed(2) + ' seconds.', 'success');
      } catch (error) {
        toast('Could not save soundtrack offset', error.message, 'error');
      } finally {
        setBusy(button, false);
      }
    });

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
    qs('#animation-motion-lab-use-soundtrack')?.addEventListener('click',
      () => void motionLabUseProjectSoundtrack());
    qs('#animation-motion-lab-add-audio')?.addEventListener('click', motionLabAddAudio);
    qs('#animation-motion-lab-audio-sync')?.addEventListener('change', event => {
      if (!event.target.checked) motionLabAudioElement?.pause();
      motionLabAudioSyncStatus(event.target.checked
        ? 'Audio will follow Motion Curves playback and seeking.'
        : 'Synchronized audio playback disabled.');
    });
    for (const id of ['threshold','attack','release','distance','band','detection','sensitivity']) {
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

    qsa('[data-motion-record-limit]').forEach(input => {
      input.addEventListener('change', () => motionLabChangeRecordingLimit(input));
    });
    for (const id of ['animation-motion-lab-record-translation',
      'animation-motion-lab-record-rotation']) {
      qs('#' + id)?.addEventListener('change', motionLabRecordingUi);
    }
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
      renderEditorGuidance();
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
    renderEditorGuidance();

    window.addEventListener('resize', () => {
      window.clearTimeout(state.timelineResizeTimer);
      state.timelineResizeTimer = window.setTimeout(() => renderTimeline(), 140);
    });
    try {
      await Promise.all([
        loadCapabilities(),
        loadModels(),
        loadDepthModels().catch(error => {
          // Optional depth discovery must not block the basic Project Editor.
          toast('Depth preview unavailable', error.message, 'warning', 6500);
        }),
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

  // First-run onboarding reuses the real editor rather than introducing a
  // second project workspace. Return false if the user declines a safe switch.
  async function openSavedProjectFromSetup(projectId) {
    if (motionLabRecorder?.active || renderIsActive() || state.motionJobId ||
        motionPreviewStarting || animationRenderStarting) {
      toast('Finish the current job first',
        'Wait for recording, preview or rendering before switching projects.', 'warning');
      return false;
    }
    await loadProjectList();
    const opened = await loadProject(projectId, { confirmDirty: true });
    if (!opened) return false;
    qs('.nav-button[data-view="animation"]')?.click();
    showAnimationTab('editor');
    return state.project?.id === projectId;
  }
  window.MorphorumAnimation = {
    openSavedProjectFromSetup,
  };

  window.addEventListener('DOMContentLoaded', start);
})();
