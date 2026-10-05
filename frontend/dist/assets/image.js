(() => {
  'use strict';

  const state = {
    capabilities: {},
    model: null,
    activeJobId: null,
    pollTimer: null,
    renderedResults: new Set(),
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

  function setEnabled(enabled) {
    for (const id of [
      '#image-resolution-preset', '#image-width', '#image-height', '#swap-resolution',
      '#image-steps', '#image-guidance', '#image-seed', '#random-seed',
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
    const first = capability.resolutions?.[0];
    if (first) {
      select.value = `${first.width}x${first.height}`;
      qs('#image-width').value = first.width;
      qs('#image-height').value = first.height;
    }
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

  async function configureModel() {
    const select = qs('#image-model-select');
    const modelId = select?.value || '';
    state.model = null;
    if (!modelId) {
      setEnabled(false);
      qs('#image-capability-note').textContent = 'Select an indexed checkpoint to begin.';
      qs('#image-model-family-badge').textContent = 'No model';
      return;
    }

    try {
      const model = await api(`/api/models/${encodeURIComponent(modelId)}`);
      state.model = model;
      const capability = state.capabilities[model.family];
      qs('#image-model-family-badge').textContent = capability?.label || model.family;
      if (!capability?.supported) {
        setEnabled(false);
        const note = qs('#image-capability-note');
        note.textContent = capability?.reason || 'This model family is not supported yet.';
        note.classList.add('unsupported-note');
        return;
      }

      qs('#image-capability-note').classList.remove('unsupported-note');
      qs('#image-capability-note').textContent = `Ready for ${capability.label} txt2img.`;
      qs('#image-steps').value = capability.steps?.default ?? 25;
      qs('#image-steps').min = capability.steps?.min ?? 1;
      qs('#image-steps').max = capability.steps?.max ?? 150;
      qs('#guidance-label').textContent = capability.guidance?.label || 'CFG / Guidance';
      qs('#image-guidance').value = capability.guidance?.default ?? 7;
      qs('#image-guidance').min = capability.guidance?.min ?? 0;
      qs('#image-guidance').max = capability.guidance?.max ?? 30;
      qs('#image-negative-prompt').disabled = capability.negative_prompt === false;
      populatePresets(capability);
      setEnabled(true);
      updateSeedMode();
    } catch (error) {
      setEnabled(false);
      toast('Could not load model details', error.message, 'error');
    }
  }

  function randomSeed() {
    const values = new Uint32Array(1);
    crypto.getRandomValues(values);
    qs('#image-seed').value = String(values[0]);
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
      qs('#generation-step').textContent = `Image ${job.current_image}/${job.request.images} · Step ${job.current_step}/${job.total_steps}`;
    } else if (job.status === 'loading_model') {
      qs('#generation-step').textContent = 'Loading checkpoint and pipeline configuration…';
    } else if (job.status === 'queued') {
      qs('#generation-step').textContent = 'Waiting for generation worker…';
    } else {
      qs('#generation-step').textContent = job.message || '';
    }
    qs('#generation-eta').textContent = formatEta(job.eta_seconds);
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
    imageWrap.appendChild(image);

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
    const empty = qs('#image-empty-preview');
    const results = job.results || [];
    if (!results.length) return;
    empty.hidden = true;
    gallery.hidden = false;

    for (const result of results) {
      const key = `${job.id}:${result.filename}`;
      if (state.renderedResults.has(key)) continue;
      state.renderedResults.add(key);
      gallery.appendChild(resultCard(result));
    }
    qs('#result-count-badge').textContent = `${gallery.children.length} image${gallery.children.length === 1 ? '' : 's'}`;
  }

  function finishJob(job) {
    window.clearTimeout(state.pollTimer);
    state.pollTimer = null;
    state.activeJobId = null;
    setGenerateBusy(false);
    qs('#cancel-generation').hidden = true;
    updateProgress(job);
    renderResults(job);

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
      state.renderedResults.clear();
      const gallery = qs('#image-gallery');
      gallery.replaceChildren();
      gallery.hidden = true;
      qs('#image-empty-preview').hidden = false;
      qs('#result-count-badge').textContent = '0 images';
      toast('Generation started', `Job ${job.id} was queued.`, 'info');
      pollJob(job.id);
    } catch (error) {
      state.activeJobId = null;
      setGenerateBusy(false);
      qs('#cancel-generation').hidden = true;
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
    });
    qs('#random-seed')?.addEventListener('click', randomSeed);
    qs('#image-seed-mode')?.addEventListener('change', updateSeedMode);
    qs('#generate-image')?.addEventListener('click', generate);
    qs('#cancel-generation')?.addEventListener('click', cancel);
  }

  window.MorphorumImage = { configureModel, loadCapabilities };
  window.addEventListener('DOMContentLoaded', async () => {
    bind();
    await loadCapabilities();
  });
})();
