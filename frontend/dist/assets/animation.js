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
  };

  const SCHEDULE_INPUTS = {
    'motion.angle': '#animation-angle',
    'motion.zoom': '#animation-zoom',
    'motion.translation_x': '#animation-translation-x',
    'motion.translation_y': '#animation-translation-y',
    'generation.strength': '#animation-strength',
    'generation.noise': '#animation-noise',
    'generation.steps': '#animation-steps',
    'generation.guidance': '#animation-guidance',
  };

  const INSPECTOR_INPUT_IDS = new Set([
    'animation-inspector-frame',
    'animation-inspector-slider',
    'animation-curve-field',
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
    return Array.isArray(tracks)
      ? tracks.filter(item => item?.editable && item?.keyframe_editable)
      : [];
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
    const scaleInput = qs('#animation-timeline-scale');

    if (refresh) refresh.disabled = !state.project || state.timelineBusy;
    if (frameInput) {
      frameInput.disabled = !state.project || state.timelineBusy;
      frameInput.max = String(timelineMaxFrame());
    }
    if (scaleInput) {
      scaleInput.disabled = !state.project;
      scaleInput.value = String(state.timelineScale);
    }

    if (!grid || !state.project || !state.timeline) {
      if (grid) {
        grid.hidden = true;
        grid.replaceChildren();
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
      timelineStatus('No tracks');
      renderTimelineEditor();
      return;
    }

    if (!state.timelineSelection) {
      state.timelineSelection = {
        group: descriptors[0].group,
        name: descriptors[0].name,
        frame: null,
      };
    }

    const maxFrames = Math.max(1, Number(state.timeline.max_frames || 1));
    const contentWidth = Math.max(640, Math.round(maxFrames * state.timelineScale));
    grid.style.setProperty('--timeline-content-width', contentWidth + 'px');
    grid.replaceChildren();
    grid.hidden = false;
    if (empty) empty.hidden = true;

    const rulerRow = document.createElement('div');
    rulerRow.className = 'animation-timeline-ruler-row';
    const rulerLabel = document.createElement('div');
    rulerLabel.className = 'animation-timeline-ruler-label';
    rulerLabel.textContent = maxFrames + 'f · ' + formatNumber(state.timeline.fps, 2) + 'fps';
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

    for (const descriptor of descriptors) {
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
          Number(state.timelineSelection?.frame) === frame
        ) {
          keyframe.classList.add('selected');
        }
        keyframe.style.left = timelinePosition(frame) + '%';
        keyframe.title = descriptor.label + ' · F' + frame + ' · ' + String(item.value ?? '');
        keyframe.setAttribute('aria-label', descriptor.label + ' keyframe at frame ' + frame);
        keyframe.addEventListener('click', event => {
          event.stopPropagation();
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

    syncTimelinePlayhead(qs('#animation-timeline-frame')?.value || 0);
    timelineStatus('Ready', 'saved');
    renderTimelineEditor();
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
      ? 'Deforum syntax · weight can animate between prompt keyframes'
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
    refreshInspector();
  }

  function fillForm() {
    const project = state.project;
    state.loading = true;
    try {
      renderProjectSelect();
      setEditorEnabled(Boolean(project));
      if (!project) {
        renderPromptRows();
        qs('#animation-project-path').textContent = 'Create or select an animation project.';
        qs('#animation-schema-badge').textContent = 'Schema 2';
        clearInspector();
        clearDirty();
        return;
      }

      qs('#animation-name').value = project.name || 'Untitled Animation';
      qs('#animation-max-frames').value = project.animation?.max_frames ?? 120;
      qs('#animation-fps').value = project.animation?.fps ?? 24;
      qs('#animation-width').value = project.animation?.width ?? 1024;
      qs('#animation-height').value = project.animation?.height ?? 1024;
      qs('#animation-prompt-transition').value = project.animation?.prompt_transition || 'blend';
      qs('#animation-start-mode').value = project.animation?.start_mode || (project.animation?.source_image ? 'source' : 'prompt');
      qs('#animation-angle').value = project.motion?.angle || '0:(0)';
      qs('#animation-zoom').value = project.motion?.zoom || '0:(1.0)';
      qs('#animation-translation-x').value = project.motion?.translation_x || '0:(0)';
      qs('#animation-translation-y').value = project.motion?.translation_y || '0:(0)';
      qs('#animation-border-mode').value = project.motion?.border_mode || 'replicate';
      qs('#animation-strength').value = project.generation?.strength || '0:(0.65)';
      qs('#animation-noise').value = project.generation?.noise || '0:(0.02)';
      qs('#animation-steps').value = project.generation?.steps || '0:(20)';
      qs('#animation-guidance').value = project.generation?.guidance || '0:(0)';
      qs('#animation-seed').value = project.generation?.seed ?? -1;
      qs('#animation-seed-behavior').value = project.generation?.seed_behavior || 'fixed';
      qs('#animation-seed-increment').value = project.generation?.seed_increment ?? 1;
      qs('#animation-notes').value = project.notes || '';
      qs('#animation-schema-badge').textContent = `Schema ${project.schema_version || 1}`;

      const projectFile = qs('#animation-project-path');
      if (projectFile) {
        projectFile.textContent = `${project.name || 'Untitled Animation'} · project.json`;
        projectFile.title = state.path || project.id;
      }

      populateModelSelect();
      populateSamplerSelect(project.generation?.sampler || '');
      renderPromptRows();
      renderSourceState();
      syncInspectorBounds();
      clearDirty();
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
    set('#resolved-strength', formatNumber(resolved.generation?.strength));
    set('#resolved-noise', formatNumber(resolved.generation?.noise));
    set('#resolved-steps', formatNumber(resolved.generation?.steps));
    set('#resolved-guidance', formatNumber(resolved.generation?.guidance));
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
      '#resolved-strength',
      '#resolved-noise',
      '#resolved-steps',
      '#resolved-guidance',
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
    if (fileInput) fileInput.disabled = !state.project || Boolean(state.motionJobId) || renderActive;
    if (clear) clear.disabled = !state.project || !hasSource || Boolean(state.motionJobId) || renderActive;
    if (preview) preview.disabled = !state.project || !hasSource || Boolean(state.motionJobId) || renderActive;
    const renderButton = qs('#animation-start-render');
    if (renderButton) {
      const hasModel = Boolean(qs('#animation-model')?.value);
      renderButton.disabled = !state.project || !hasModel || (requiresSource && !hasSource) || renderActive;
    }
  }

  function clearMotionPreviewResult() {
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
      clearMotionPreviewResult();
      renderSourceState();
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
      clearMotionPreviewResult();
      renderSourceState();
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
      if (image) image.src = job.url + '?v=' + Date.now();
      if (meta && job.result) meta.textContent = job.result.preview_width + ' × ' + job.result.preview_height + ' · ' + job.result.captured_frames + ' preview frames from ' + job.result.source_frames + ' project frames · ' + Number(job.result.duration_seconds || 0).toFixed(2) + 's · ' + job.result.border_mode;
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

  async function generateMotionPreview() {
    if (!state.project?.animation?.source_image || state.motionJobId) return;
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
      const job = await api('/api/animation/motion-preview', { method: 'POST', body: JSON.stringify({ project: collectProject() }) });
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

  function resetRenderUi() {
    window.clearTimeout(state.renderPollTimer);
    state.renderPollTimer = null;
    state.renderJobId = null;
    state.renderJob = null;
    state.renderHistory = [];
    state.lastRenderFrameUrl = '';
    const loadProgress = qs('#animation-model-load-progress');
    if (loadProgress) loadProgress.hidden = true;
    const progress = qs('#animation-render-progress');
    if (progress) progress.hidden = true;
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
    const frameStat = qs('#animation-render-frame');
    if (frameStat) frameStat.textContent = job ? ((Number(job.current_frame || 0) + 1) + ' / ' + Number(job.total_frames || 0)) : '--';
    const stepStat = qs('#animation-render-step');
    if (stepStat) stepStat.textContent = job ? String(job.current_step ?? 0) : '--';
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
      if (!state.renderJobId && renders.length) renderAnimationJob(renders[0]);
      else if (!renders.length && !state.renderJobId) renderAnimationJob(null);
    } catch (error) {
      toast('Could not load animation render history', error.message, 'warning', 6000);
    }
  }

  async function showRender(renderId) {
    if (!renderId) { renderAnimationJob(null); return; }
    try {
      const job = await api('/api/animation/renders/' + encodeURIComponent(renderId));
      renderAnimationJob(job);
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
    const button = qs('#animation-start-render');
    if (button) { button.classList.add('busy'); button.disabled = true; }
    try {
      const job = await api('/api/animation/renders', { method: 'POST', body: JSON.stringify({ project: collectProject() }) });
      state.renderJobId = job.id;
      renderAnimationJob(job);
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
      populateSamplerSelect(state.project?.generation?.sampler || '');
    } catch (error) {
      toast('Animation model list unavailable', error.message, 'warning', 6000);
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
      !window.confirm('Discard unsaved animation project changes?')
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
      state.path = payload.path || '';
      fillForm();
      await loadRenderHistory();
    } catch (error) {
      toast('Could not load animation project', error.message, 'error', 6500);
    } finally {
      if (select) select.disabled = state.projects.length === 0;
    }
  }

  async function createProject() {
    const requestedName = window.prompt('New animation project name:', 'New Animation');
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
      state.path = payload.path || '';
      await loadProjectList();
      fillForm();
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

  function bind() {
    qs('#animation-new')?.addEventListener('click', createProject);
    qs('#animation-save')?.addEventListener('click', saveProject);
    qs('#animation-reload')?.addEventListener('click', reloadProject);
    qs('#animation-add-prompt')?.addEventListener('click', addPromptKeyframe);
    qs('#animation-validate-schedules')?.addEventListener('click', () => validateSchedules(true));

    qs('#animation-source-file')?.addEventListener('change', event => {
      const file = event.target.files?.[0];
      if (file) uploadSourceImage(file);
    });
    qs('#animation-clear-source')?.addEventListener('click', clearSourceImage);
    qs('#animation-generate-motion-preview')?.addEventListener('click', generateMotionPreview);

    qs('#animation-start-render')?.addEventListener('click', startAnimationRender);
    qs('#animation-cancel-render')?.addEventListener('click', cancelAnimationRender);
    qs('#animation-resume-render')?.addEventListener('click', resumeAnimationRender);
    qs('#animation-render-select')?.addEventListener('change', event => {
      showRender(event.target.value);
    });

    qs('#animation-project-select')?.addEventListener('change', event => {
      loadProject(event.target.value);
    });

    qs('#animation-model')?.addEventListener('change', () => {
      populateSamplerSelect('');
      renderPromptRows();
      markDirty();
      renderSourceState();
    });

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
        input.id === 'animation-model' ||
        input.id === 'animation-source-file' ||
        input.id === 'animation-start-mode' ||
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
    });
  }

  async function start() {
    bind();
    setEditorEnabled(false);
    try {
      await Promise.all([
        loadCapabilities(),
        loadModels(),
        loadProjectList({ loadFirst: true }),
      ]);
      populateSamplerSelect(state.project?.generation?.sampler || '');
    } catch (error) {
      toast('Animation workspace initialization failed', error.message, 'error', 7000);
    }
  }

  window.addEventListener('DOMContentLoaded', start);
})();
