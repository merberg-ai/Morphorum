(() => {
  'use strict';

  const state = {
    capabilities: {},
    model: null,
    activeJobId: null,
    pollTimer: null,
    renderedResults: new Set(),
    previewLimit: 5,
    currentResults: [],
    currentResultJobId: null,
    modelLoaded: false,
    loras: [],
    draft: null,
    restoredModel: '',
    modelRequest: 0,
  };

  const qs = (selector, root = document) => root.querySelector(selector);
  const toast = (title, message, type = 'info', timeout) => {
    if (window.MorphorumToast) return window.MorphorumToast(title, message, type, timeout);
    console.log(`[${type}] ${title}: ${message}`);
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

  // Browser-local Image draft. Model fields restore only after capabilities/LoRAs resolve.
  const IMAGE_DRAFT_KEY = 'morphorum.image.form.v1';
  const DRAFT_FIELDS = [
    'image-prompt', 'image-negative-prompt', 'image-resolution-preset',
    'image-width', 'image-height', 'image-steps', 'image-sampler', 'image-guidance',
    'image-seed', 'image-seed-mode', 'image-seed-increment', 'image-count',
    'image-lora-select', 'image-lora-weight'
  ];
  let draftTimer = null;
  function readImageDraft() {
    try {
      const draft = JSON.parse(localStorage.getItem(IMAGE_DRAFT_KEY) || 'null');
      return draft?.version === 1 && draft.values && typeof draft.values === 'object' ? draft : null;
    } catch (_) { return null; }
  }
  function saveImageDraft() {
    if (draftTimer) window.clearTimeout(draftTimer);
    draftTimer = null;
    const values = {};
    DRAFT_FIELDS.forEach(id => { const element = document.getElementById(id); if (element) values[id] = element.value; });
    const modelId = qs('#image-model-select')?.value || state.draft?.modelId || '';
    const draft = { version: 1, modelId, values };
    state.draft = draft;
    try {
      localStorage.setItem(IMAGE_DRAFT_KEY, JSON.stringify(draft));
      if (modelId) localStorage.setItem('morphorum.image.modelId', modelId);
    } catch (_) { /* Storage may be restricted or full. */ }
  }
  function scheduleDraftSave() {
    if (draftTimer) window.clearTimeout(draftTimer);
    draftTimer = window.setTimeout(saveImageDraft, 300);
  }
  function restoreNumeric(id, value) {
    const input = document.getElementById(id);
    if (!input || input.type !== 'number') return;
    if (value == null || String(value).trim() === '') return;
    const n = Number(value);
    if (!Number.isFinite(n)) return;
    if (input.min !== '' && n < Number(input.min)) return;
    if (input.max !== '' && n > Number(input.max)) return;
    input.value = String(n);
  }
  function restoreImageDraft(modelId) {
    const draft = state.draft;
    if (!draft || draft.modelId !== modelId || state.restoredModel === modelId) return;
    const values = draft.values;
    const selectFields = ['image-sampler', 'image-seed-mode', 'image-lora-select'];
    for (const id of selectFields) {
      const node = document.getElementById(id);
      const value = values[id];
      if (node && typeof value === 'string' && [...node.options].some(option => option.value === value)) node.value = value;
    }
    for (const id of ['image-width','image-height','image-steps','image-guidance','image-seed','image-seed-increment','image-count','image-lora-weight']) {
      restoreNumeric(id, values[id]);
    }
    const preset = qs('#image-resolution-preset');
    if (preset) {
      const match = values['image-width'] + 'x' + values['image-height'];
      preset.value = [...preset.options].some(opt => opt.value === match) ? match : 'custom';
    }
    updateSeedMode();
    state.restoredModel = modelId;
  }
  async function resetImageDraft() {
    const accepted = await window.MorphorumDialog.confirm({
      title: 'Reset Image Generation form?',
      message: 'Clear locally saved prompts and Image Generation settings for this browser. Generated files will not be deleted.',
      variant: 'warning', confirmText: 'Reset Image Form', cancelText: 'Keep Draft'
    });
    if (!accepted) return;
    if (draftTimer) window.clearTimeout(draftTimer);
    draftTimer = null;
    state.draft = null;
    state.restoredModel = '';
    try { localStorage.removeItem(IMAGE_DRAFT_KEY); } catch (_) {}
    qs('#image-prompt').value = '';
    qs('#image-negative-prompt').value = '';
    qs('#image-seed').value = '-1';
    qs('#image-seed-mode').value = 'fixed';
    qs('#image-seed-increment').value = '1';
    qs('#image-count').value = '1';
    qs('#image-lora-weight').value = '1';
    const model = state.model;
    if (model) {
      const cap = effectiveCapability(model);
      populatePresets(cap);
      populateSamplers(cap);
      applyModelDefaults(cap);
      updateSeedMode();
    }
    try { localStorage.removeItem(IMAGE_DRAFT_KEY); } catch (_) {}
    toast('Image draft cleared', 'Current form reset. Generated images remain untouched.', 'success');
  }

  function resultKey(result) {
    return `${state.currentResultJobId || 'job'}:${result.filename}`;
  }

  function syncPreviewVisibility(hasImages) {
    const gallery = qs('#image-gallery');
    const empty = qs('#image-empty-preview');
    if (empty) {
      empty.hidden = hasImages;
      empty.style.display = hasImages ? 'none' : '';
    }
    if (gallery) {
      gallery.hidden = !hasImages;
      gallery.style.display = hasImages ? '' : 'none';
    }
  }

  function updateResultBadge(total, visible) {
    const badge = qs('#result-count-badge');
    if (!badge) return;
    if (!total) {
      badge.textContent = '0 images';
    } else if (visible < total) {
      badge.textContent = `${visible} of ${total} previews`;
    } else {
      badge.textContent = `${total} image${total === 1 ? '' : 's'}`;
    }
  }

  function rebuildPreviewGallery() {
    const gallery = qs('#image-gallery');
    if (!gallery) return;
    gallery.replaceChildren();
    const visible = state.currentResults.slice(-state.previewLimit);
    for (const result of visible) gallery.appendChild(resultCard(result));
    state.renderedResults = new Set(state.currentResults.map(resultKey));
    syncPreviewVisibility(visible.length > 0);
    updateResultBadge(state.currentResults.length, visible.length);
  }

  function applySettings(settings) {
    const requested = Number(settings?.ui?.image_preview_limit);
    state.previewLimit = Number.isFinite(requested)
      ? Math.max(1, Math.min(50, Math.trunc(requested)))
      : 5;
    rebuildPreviewGallery();
  }

  function updateUnloadButton() {
    const button = qs('#unload-model');
    if (!button) return;
    button.disabled = !state.modelLoaded || Boolean(state.activeJobId);
  }

  async function refreshModelStatus() {
    try {
      const status = await api('/api/generation/model');
      state.modelLoaded = Boolean(status.loaded);
      const button = qs('#unload-model');
      if (button) {
        button.title = status.loaded && status.model_name
          ? `Unload ${status.model_name} from memory`
          : 'No model is currently loaded';
      }
      updateUnloadButton();
      return status;
    } catch (_) {
      state.modelLoaded = false;
      updateUnloadButton();
      return null;
    }
  }

  async function unloadModel() {
    if (state.activeJobId) return;
    const button = qs('#unload-model');
    if (!button) return;
    button.classList.add('busy');
    button.disabled = true;
    try {
      const result = await api('/api/generation/model/unload', {
        method: 'POST',
        body: '{}',
      });
      state.modelLoaded = false;
      updateUnloadButton();
      toast(
        result.status === 'unloaded' ? 'Model unloaded' : 'No model loaded',
        result.status === 'unloaded'
          ? 'The diffusion pipeline was removed from memory and CUDA cache cleanup was requested.'
          : 'There was no loaded diffusion pipeline to unload.',
        result.status === 'unloaded' ? 'success' : 'info'
      );
    } catch (error) {
      toast('Could not unload model', error.message, 'error', 7000);
      await refreshModelStatus();
    } finally {
      button.classList.remove('busy');
      updateUnloadButton();
    }
  }

  function setEnabled(enabled) {
    for (const id of [
      '#image-resolution-preset', '#image-width', '#image-height', '#swap-resolution',
      '#image-steps', '#image-sampler', '#image-guidance', '#image-seed', '#random-seed',
      '#image-seed-mode', '#image-seed-increment', '#image-count'
    ]) {
      const element = qs(id);
      if (element) element.disabled = !enabled;
    }
    const generate = qs('#generate-image');
    if (generate && !state.activeJobId) generate.disabled = !enabled;
  }

  function setGenerateBusy(busy) {
    const button = qs('#generate-image');
    if (!button) return;
    button.classList.toggle('busy', busy);
    const label = qs('.button-label', button);
    if (label) label.textContent = busy ? 'Generating…' : 'Generate';
    button.disabled = busy || !(state.model && state.capabilities[state.model.family]?.supported);
    updateUnloadButton();
  }

  function populatePresets(capability) {
    const select = qs('#image-resolution-preset');
    if (!select) return;
    select.replaceChildren();
    for (const preset of capability.resolutions || []) {
      const option = document.createElement('option');
      option.value = `${preset.width}x${preset.height}`;
      option.textContent = `${preset.label} · ${preset.width} × ${preset.height}`;
      select.appendChild(option);
    }
    const custom = document.createElement('option');
    custom.value = 'custom';
    custom.textContent = 'Custom';
    select.appendChild(custom);
  }

  function populateSamplers(capability) {
    const select = qs('#image-sampler');
    if (!select) return;
    select.replaceChildren();
    const samplerConfig = capability.samplers || {};
    const options = Array.isArray(samplerConfig.options) ? samplerConfig.options : [];
    for (const sampler of options) {
      const option = document.createElement('option');
      option.value = sampler.id;
      option.textContent = sampler.label || sampler.id;
      select.appendChild(option);
    }
  }

  function applyModelDefaults(capability) {
    const steps = qs('#image-steps');
    steps.value = capability.steps?.default ?? 25;
    steps.min = capability.steps?.min ?? 1;
    steps.max = capability.steps?.max ?? 150;

    const guidance = qs('#image-guidance');
    qs('#guidance-label').textContent = capability.guidance?.label || 'CFG / Guidance';
    guidance.value = capability.guidance?.default ?? 7;
    guidance.min = capability.guidance?.min ?? 0;
    guidance.max = capability.guidance?.max ?? 30;
    guidance.disabled = Number(capability.guidance?.min) === Number(capability.guidance?.max);

    const sampler = qs('#image-sampler');
    const samplerOptions = capability.samplers?.options || [];
    const samplerDefault = capability.samplers?.default || samplerOptions[0]?.id || '';
    if ([...sampler.options].some(option => option.value === samplerDefault)) {
      sampler.value = samplerDefault;
    }

    const resolution = capability.default_resolution || capability.resolutions?.[0];
    if (resolution) {
      const width = Number(resolution.width);
      const height = Number(resolution.height);
      qs('#image-width').value = width;
      qs('#image-height').value = height;
      const presetValue = `${width}x${height}`;
      const preset = qs('#image-resolution-preset');
      preset.value = [...preset.options].some(option => option.value === presetValue)
        ? presetValue
        : 'custom';
    }

    const negativePrompt = qs('#image-negative-prompt');
    negativePrompt.disabled = capability.negative_prompt === false;
    negativePrompt.title = capability.negative_prompt === false
      ? 'Negative prompts are not used by this model family.'
      : '';
  }

  function updateSeedMode() {
    const mode = qs('#image-seed-mode')?.value || 'fixed';
    const increment = qs('#image-seed-increment');
    if (increment) increment.disabled = !state.model || mode !== 'increment';
    const seed = qs('#image-seed');
    const randomButton = qs('#random-seed');
    if (seed) seed.disabled = !state.model || mode === 'random';
    if (randomButton) randomButton.disabled = !state.model || mode === 'random';
  }

  function effectiveCapability(model) {
    const base = state.capabilities[model?.family] || {};
    const variant = String(model?.variant || '').toLowerCase();
    const override = base.variants?.[variant] || {};
    const merged = { ...base, ...override };
    for (const key of ['steps', 'guidance', 'samplers']) {
      if (base[key] || override[key]) merged[key] = { ...(base[key] || {}), ...(override[key] || {}) };
    }
    merged.variant = variant;
    return merged;
  }

  function renderLoraPicker() {
    const select = qs('#image-lora-select');
    const weight = qs('#image-lora-weight');
    const insert = qs('#image-insert-lora');
    if (!select) return;

    select.replaceChildren();
    if (!state.model) {
      const option = document.createElement('option');
      option.value = '';
      option.textContent = 'Select a model to browse LoRAs';
      select.appendChild(option);
      select.disabled = true;
      if (weight) weight.disabled = true;
      if (insert) insert.disabled = true;
      return;
    }

    if (!state.loras.length) {
      const option = document.createElement('option');
      option.value = '';
      option.textContent = `No indexed ${state.model.family} LoRAs`;
      select.appendChild(option);
      select.disabled = true;
      if (weight) weight.disabled = true;
      if (insert) insert.disabled = true;
      return;
    }

    for (const lora of state.loras) {
      const option = document.createElement('option');
      option.value = lora.name || lora.filename || lora.id;
      option.textContent = lora.name || lora.filename || lora.id;
      select.appendChild(option);
    }
    select.disabled = false;
    if (weight) weight.disabled = false;
    if (insert) insert.disabled = false;
  }

  async function loadLorasForModel() {
    state.loras = [];
    renderLoraPicker();
    if (!state.model?.family) return;
    try {
      const payload = await api(
        `/api/models?family=${encodeURIComponent(state.model.family)}&kind=loras&limit=2000`
      );
      state.loras = Array.isArray(payload.models) ? payload.models : [];
    } catch (error) {
      state.loras = [];
      toast('Could not load LoRAs', error.message, 'warning', 6000);
    }
    renderLoraPicker();
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

  function insertSelectedLora() {
    const select = qs('#image-lora-select');
    const textarea = qs('#image-prompt');
    const name = String(select?.value || '').trim();
    if (!name || !textarea) return;
    const rawWeight = Number(qs('#image-lora-weight')?.value);
    const weight = Number.isFinite(rawWeight) ? rawWeight : 1;
    try {
      insertAtCursor(textarea, window.MorphorumPromptTags.lora({ name, weight }));
    } catch (error) { toast('Invalid LoRA tag', error.message, 'warning'); }
  }

  async function configureModel() {
    const requestId = ++state.modelRequest;
    const select = qs('#image-model-select');
    const modelId = select?.value || '';
    state.model = null;
    if (!modelId) {
      setEnabled(false);
      state.loras = [];
      renderLoraPicker();
      qs('#image-capability-note').textContent = 'Select an indexed checkpoint to begin.';
      qs('#image-model-family-badge').textContent = 'No model';
      return;
    }

    try {
      const model = await api(`/api/models/${encodeURIComponent(modelId)}`);
      if (requestId !== state.modelRequest) return;
      state.model = model;
      await loadLorasForModel();
      if (requestId !== state.modelRequest) return;
      const capability = effectiveCapability(model);
      qs('#image-model-family-badge').textContent = capability?.label || model.family;
      if (!capability?.supported) {
        setEnabled(false);
        const note = qs('#image-capability-note');
        note.textContent = capability?.reason || 'This model family is not supported yet.';
        note.classList.add('unsupported-note');
        return;
      }

      qs('#image-capability-note').classList.remove('unsupported-note');
      const variantLabel = capability.label || state.capabilities[model.family]?.label || model.family;
      qs('#image-capability-note').textContent = `Ready for ${variantLabel} txt2img. Model defaults applied.`;
      populatePresets(capability);
      populateSamplers(capability);
      setEnabled(true);
      applyModelDefaults(capability);
      updateSeedMode();
      restoreImageDraft(modelId);
      saveImageDraft();
    } catch (error) {
      setEnabled(false);
      toast('Could not load model details', error.message, 'error');
    }
  }

  function randomSeed() {
    const values = new Uint32Array(1);
    crypto.getRandomValues(values);
    qs('#image-seed').value = String(values[0]);
    saveImageDraft();
  }

  function formatEta(seconds) {
    if (seconds == null || !Number.isFinite(Number(seconds))) return '';
    let value = Math.max(0, Math.round(Number(seconds)));
    if (value < 60) return `ETA ${value}s`;
    const minutes = Math.floor(value / 60);
    value %= 60;
    if (minutes < 60) return `ETA ${minutes}m ${value}s`;
    const hours = Math.floor(minutes / 60);
    return `ETA ${hours}h ${minutes % 60}m`;
  }

  function updateProgress(job) {
    const panel = qs('#generation-progress');
    panel.hidden = false;
    const percent = Math.max(0, Math.min(100, Math.round((Number(job.progress) || 0) * 100)));
    qs('#generation-status').textContent = job.message || job.status;
    qs('#generation-percent').textContent = `${percent}%`;
    qs('#generation-progress-fill').style.width = `${percent}%`;
    if (job.status === 'generating') {
      const speed = Number(job.average_step_seconds);
      const speedText = Number.isFinite(speed) && speed > 0 ? ` · ${speed.toFixed(1)}s/step` : '';
      qs('#generation-step').textContent = `Image ${job.current_image}/${job.request.images} · Step ${job.current_step}/${job.total_steps}${speedText}`;
    } else if (job.status === 'loading_model') {
      qs('#generation-step').textContent = 'Loading checkpoint and pipeline configuration…';
    } else if (job.status === 'queued') {
      qs('#generation-step').textContent = 'Waiting for generation worker…';
    } else {
      qs('#generation-step').textContent = job.message || '';
    }
    qs('#generation-eta').textContent = formatEta(job.eta_seconds);
    window.dispatchEvent(new CustomEvent('morphorum:job-status', {detail: {
      type:'image', id:job.id, status:job.status, progress:Number(job.progress || 0),
      current:Number(job.current_image || 0), total:Number(job.request?.images || 0),
      eta_seconds:job.eta_seconds
    }}));
  }

  function openImageLightbox(result) {
    const dialog = qs('#image-result-lightbox');
    if (!dialog || !result.url) return;
    qs('#image-lightbox-details').textContent = 'Image ' + result.index + ' · Seed ' + result.seed;
    qs('#image-lightbox-full').src = result.url;
    const download = qs('#image-lightbox-download');
    download.href = result.url;
    download.download = result.filename || 'morphorum.png';
    if (typeof dialog.showModal === 'function') dialog.showModal();
  }
  async function loadImageJobHistory({ reconnect = false } = {}) {
    try {
      const payload = await api('/api/generation/jobs?limit=20');
      const jobs = Array.isArray(payload.jobs) ? payload.jobs : [];
      const select = qs('#image-job-history');
      const selected = state.activeJobId || (reconnect ? '' : select.value);
      select.replaceChildren();
      const placeholder = document.createElement('option');
      placeholder.value = '';
      placeholder.textContent = jobs.length ? 'Choose a recent job…' : 'No recent jobs';
      select.appendChild(placeholder);
      jobs.forEach(job => {
        const option = document.createElement('option');
        option.value = job.id;
        option.textContent = (job.status || 'unknown') + ' · ' + job.id;
        select.appendChild(option);
      });
      if (jobs.some(j => j.id === selected)) select.value = selected;
      if (reconnect) {
        const job = jobs.find(j => ['queued','loading_model','generating'].includes(j.status)) || jobs[0];
        if (job) await showImageJob(job.id);
      }
    } catch (error) { toast('Image history unavailable', error.message, 'warning'); }
  }
  async function showImageJob(jobId) {
    if (!jobId) return;
    if (state.pollTimer) window.clearTimeout(state.pollTimer);
    state.pollTimer = null;
    try {
      const job = await api('/api/generation/jobs/' + encodeURIComponent(jobId));
      state.currentResultJobId = job.id;
      state.currentResults = [];
      state.renderedResults.clear();
      qs('#image-gallery')?.replaceChildren();
      state.activeJobId = ['queued','loading_model','generating'].includes(job.status) ? job.id : null;
      updateProgress(job);
      renderResults(job);
      setGenerateBusy(Boolean(state.activeJobId));
      qs('#cancel-generation').hidden = !state.activeJobId;
      if (state.activeJobId) pollJob(job.id);
    } catch (error) { toast('Could not open image job', error.message, 'warning'); }
  }
  function resultCard(result) {
    const card = document.createElement('div');
    card.className = 'result-card';

    const imageWrap = document.createElement('div');
    imageWrap.className = 'result-image-wrap';
    const image = document.createElement('img');
    image.className = 'result-image';
    image.loading = 'lazy';
    image.alt = `Generated image, seed ${result.seed}`;
    image.src = `${result.url}?v=${Date.now()}`;
    const open = document.createElement('button');
    open.type = 'button';
    open.title = 'View generated image full-size';
    open.setAttribute('aria-label', 'View image ' + result.index + ' full-size');
    open.appendChild(image);
    open.addEventListener('click', () => openImageLightbox(result));
    imageWrap.appendChild(open);

    const meta = document.createElement('div');
    meta.className = 'result-meta';
    const seedWrap = document.createElement('div');
    seedWrap.className = 'result-seed';
    const strong = document.createElement('strong');
    strong.textContent = `Image ${result.index}`;
    const seed = document.createElement('span');
    seed.textContent = `Seed ${result.seed}`;
    seedWrap.append(strong, seed);

    const actions = document.createElement('div');
    actions.className = 'result-actions';
    const reuse = document.createElement('button');
    reuse.className = 'secondary-button';
    reuse.type = 'button';
    reuse.textContent = 'Reuse seed';
    reuse.addEventListener('click', () => {
      qs('#image-seed-mode').value = 'fixed';
      qs('#image-seed').value = result.seed;
      updateSeedMode();
      saveImageDraft();
      toast('Seed reused', `Seed ${result.seed} is ready for the next generation.`, 'success');
    });
    const save = document.createElement('a');
    save.className = 'secondary-button';
    save.href = result.url;
    save.download = result.filename;
    save.textContent = 'Save';
    actions.append(reuse, save);
    meta.append(seedWrap, actions);
    card.append(imageWrap, meta);
    return card;
  }

  function renderResults(job) {
    const gallery = qs('#image-gallery');
    if (!gallery) return;
    const results = Array.isArray(job.results) ? job.results : [];

    if (state.currentResultJobId !== job.id) {
      state.currentResultJobId = job.id;
      state.currentResults = [];
      state.renderedResults.clear();
      gallery.replaceChildren();
    }
    state.currentResults = results.slice();

    if (!results.length) {
      syncPreviewVisibility(false);
      updateResultBadge(0, 0);
      return;
    }

    syncPreviewVisibility(true);
    for (const result of results) {
      const key = resultKey(result);
      if (state.renderedResults.has(key)) continue;
      state.renderedResults.add(key);
      gallery.appendChild(resultCard(result));
    }

    while (gallery.children.length > state.previewLimit) {
      gallery.firstElementChild?.remove();
    }
    updateResultBadge(results.length, gallery.children.length);
  }

  function finishJob(job) {
    window.clearTimeout(state.pollTimer);
    state.pollTimer = null;
    state.activeJobId = null;
    setGenerateBusy(false);
    qs('#cancel-generation').hidden = true;
    updateProgress(job);
    renderResults(job);
    refreshModelStatus();

    if (job.status === 'completed') {
      toast('Generation complete', `${job.results.length} image${job.results.length === 1 ? '' : 's'} generated.`, 'success', 5500);
    } else if (job.status === 'cancelled') {
      toast('Generation cancelled', 'Completed images were kept.', 'warning');
    } else if (job.status === 'failed') {
      toast('Generation failed', job.error || job.message || 'Unknown generation error.', 'error', 9000);
    }
  }

  async function pollJob(jobId) {
    try {
      const job = await api(`/api/generation/jobs/${encodeURIComponent(jobId)}`);
      updateProgress(job);
      renderResults(job);
      if (['completed', 'failed', 'cancelled'].includes(job.status)) {
        finishJob(job);
        return;
      }
      state.pollTimer = window.setTimeout(() => pollJob(jobId), 500);
    } catch (error) {
      toast('Could not read generation progress', error.message, 'error');
      state.pollTimer = window.setTimeout(() => pollJob(jobId), 1500);
    }
  }

  function buildPayload() {
    return {
      model_id: qs('#image-model-select').value,
      prompt: qs('#image-prompt').value,
      negative_prompt: qs('#image-negative-prompt').value,
      width: Number(qs('#image-width').value),
      height: Number(qs('#image-height').value),
      steps: Number(qs('#image-steps').value),
      sampler: qs('#image-sampler').value,
      guidance_scale: Number(qs('#image-guidance').value),
      seed: Number(qs('#image-seed').value),
      seed_mode: qs('#image-seed-mode').value,
      seed_increment: Number(qs('#image-seed-increment').value),
      images: Number(qs('#image-count').value),
    };
  }

  async function generate() {
    if (state.activeJobId) return;
    setGenerateBusy(true);
    const unloadButton = qs('#unload-model');
    if (unloadButton) unloadButton.disabled = true;
    qs('#cancel-generation').hidden = false;
    qs('#generation-progress').hidden = false;
    qs('#generation-status').textContent = 'Submitting generation job…';
    qs('#generation-progress-fill').style.width = '0%';
    try {
      const job = await api('/api/generation/jobs', {
        method: 'POST',
        body: JSON.stringify(buildPayload()),
      });
      state.activeJobId = job.id;
      state.currentResultJobId = job.id;
      state.currentResults = [];
      state.renderedResults.clear();
      const gallery = qs('#image-gallery');
      gallery.replaceChildren();
      syncPreviewVisibility(false);
      updateResultBadge(0, 0);
      updateUnloadButton();
      toast('Generation started', `Job ${job.id} was queued.`, 'info');
      pollJob(job.id);
      loadImageJobHistory();
    } catch (error) {
      state.activeJobId = null;
      setGenerateBusy(false);
      qs('#cancel-generation').hidden = true;
      refreshModelStatus();
      toast('Could not start generation', error.message, 'error', 8500);
    }
  }

  async function cancel() {
    if (!state.activeJobId) return;
    const button = qs('#cancel-generation');
    button.disabled = true;
    try {
      await api(`/api/generation/jobs/${encodeURIComponent(state.activeJobId)}/cancel`, {
        method: 'POST',
        body: '{}',
      });
      toast('Cancellation requested', 'Morphorum will stop at the next safe denoising step.', 'warning');
    } catch (error) {
      toast('Could not cancel generation', error.message, 'error');
    } finally {
      button.disabled = false;
    }
  }

  async function loadCapabilities() {
    try {
      const payload = await api('/api/generation/capabilities');
      state.capabilities = payload.families || {};
      await configureModel();
    } catch (error) {
      toast('Generation capabilities unavailable', error.message, 'error');
    }
  }

  function bind() {
    qs('#image-model-select')?.addEventListener('change', configureModel);
    qs('#image-insert-lora')?.addEventListener('click', insertSelectedLora);
    qs('#image-resolution-preset')?.addEventListener('change', event => {
      if (event.target.value === 'custom') return;
      const [width, height] = event.target.value.split('x').map(Number);
      if (width && height) {
        qs('#image-width').value = width;
        qs('#image-height').value = height;
      }
    });
    qs('#image-width')?.addEventListener('input', () => { qs('#image-resolution-preset').value = 'custom'; });
    qs('#image-height')?.addEventListener('input', () => { qs('#image-resolution-preset').value = 'custom'; });
    qs('#swap-resolution')?.addEventListener('click', () => {
      const width = qs('#image-width').value;
      qs('#image-width').value = qs('#image-height').value;
      qs('#image-height').value = width;
      qs('#image-resolution-preset').value = 'custom';
      saveImageDraft();
    });
    qs('#random-seed')?.addEventListener('click', randomSeed);
    qs('#image-seed-mode')?.addEventListener('change', updateSeedMode);
    qs('#generate-image')?.addEventListener('click', generate);
    qs('#cancel-generation')?.addEventListener('click', cancel);
    qs('#unload-model')?.addEventListener('click', unloadModel);
    qs('#image-reset-draft')?.addEventListener('click', resetImageDraft);
    qs('#image-jump-results')?.addEventListener('click', () => qs('#image-results-heading')?.scrollIntoView({behavior:'smooth',block:'start'}));
    qs('#image-job-history')?.addEventListener('change', event => showImageJob(event.target.value));
    qs('#image-history-refresh')?.addEventListener('click', () => loadImageJobHistory());
    qs('#image-lightbox-close')?.addEventListener('click', () => qs('#image-result-lightbox')?.close());
    const root = qs('#view-image');
    root?.addEventListener('input', event => {
      if (event.target?.id?.startsWith('image-') && event.target.id !== 'image-model-select') scheduleDraftSave();
    });
    root?.addEventListener('change', event => {
      if (event.target?.id?.startsWith('image-') && event.target.id !== 'image-model-select') scheduleDraftSave();
    });
    state.draft = readImageDraft();
    if (state.draft) {
      for (const id of ['image-prompt','image-negative-prompt']) {
        if (typeof state.draft.values[id] === 'string') qs('#' + id).value = state.draft.values[id];
      }
    }
  }

  function reportManagerInsertion({ id, event, reason = '', weight, imageFamily = '', triggerCount = 0 }) {
    if (!id) return;
    // Send diagnostic facts, not the user's prompt or third-party sidecar text.
    api('/api/loras/' + encodeURIComponent(id) + '/activity', {
      method: 'POST',
      body: JSON.stringify({
        event, reason, weight,
        image_family: imageFamily, trigger_count: triggerCount,
      }),
    }).catch(error => console.warn('LoRA Manager console event unavailable:', error.message));
  }

  function insertFromManager({ id, family, name, weight = 1, triggers = [] } = {}) {
    const prompt = qs('#image-prompt');
    const model = state.model;
    const rawWeight = Number(weight);
    const imageFamily = model?.family || '';
    const reject = (reason, title, message) => {
      reportManagerInsertion({
        id, event: 'prompt_rejected', reason,
        weight: Number.isFinite(rawWeight) ? rawWeight : 1,
        imageFamily, triggerCount: 0,
      });
      toast(title, message, 'warning');
      return false;
    };

    if (!prompt || !model) {
      return reject('no_model', 'Select an image model',
        'Choose a checkpoint in the Image tab first.');
    }
    if (model.family !== family) {
      return reject('wrong_family', 'LoRA family mismatch',
        'Selected image checkpoint is ' + model.family + '; this LoRA is ' +
        family + '. Choose a matching checkpoint first.');
    }
    // IDs are unambiguous even when two directories contain the same filename.
    const candidate = state.loras.find(lora => lora.id === id) ||
      (!id && state.loras.find(lora => lora.name === name || lora.filename === name));
    if (!candidate) {
      return reject('not_indexed', 'LoRA not indexed for image model',
        'Refresh the library and reselect your checkpoint before inserting.');
    }
    if (!Number.isFinite(rawWeight) || rawWeight < -4 || rawWeight > 4) {
      return reject('invalid_strength', 'Invalid LoRA strength', 'Use a finite value between -4 and 4.');
    }
    // Only literal colons, angle brackets and real CR/LF characters are invalid.
    // Do not double-escape CR/LF patterns: doing so rejects ordinary r and n in names.
    if (!name || /[:<>\r\n]/.test(name)) {
      return reject('invalid_name', 'Invalid LoRA name',
        'This filename cannot be represented by a Deforum-style directive.');
    }
    const words = Array.isArray(triggers)
      ? [...new Set(triggers.filter(value => typeof value === 'string' && !/[<>\r\n]/.test(value))
        .map(value => value.trim()).filter(Boolean))].slice(0, 20)
      : [];
    insertAtCursor(prompt, window.MorphorumPromptTags.lora({ name, weight: rawWeight, triggers: words }));
    reportManagerInsertion({
      id, event: 'prompt_inserted', weight: rawWeight,
      imageFamily, triggerCount: words.length,
    });
    qs('.nav-button[data-view="image"]')?.click();
    return true;
  }

  window.MorphorumImage = {
    configureModel, loadCapabilities, refreshModelStatus,
    refreshLoras: loadLorasForModel, insertFromManager,
  };
  window.addEventListener('morphorum:settings-changed', event => applySettings(event.detail || {}));
  window.addEventListener('DOMContentLoaded', async () => {
    bind();
    syncPreviewVisibility(false);
    await Promise.all([loadCapabilities(), refreshModelStatus()]);
    await loadImageJobHistory({ reconnect: true });
  });
})();
