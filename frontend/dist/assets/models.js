(() => {
  'use strict';

  const FAMILY_LABELS = {
    sd15: 'SD 1.x',
    sd2: 'SD 2.x',
    sdxl: 'SDXL',
    flux: 'Flux',
    zimage: 'Z-Image',
  };

  const state = { models: [] };
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
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || `${response.status} ${response.statusText}`);
    return payload;
  }

  function setBusy(button, busy) {
    if (!button) return;
    button.classList.toggle('busy', busy);
    button.disabled = busy;
  }

  function formatBytes(bytes) {
    const value = Number(bytes) || 0;
    if (value < 1024) return `${value} B`;
    const units = ['KiB', 'MiB', 'GiB', 'TiB'];
    let current = value / 1024;
    let unit = units[0];
    for (let i = 1; i < units.length && current >= 1024; i += 1) {
      current /= 1024;
      unit = units[i];
    }
    return `${current >= 10 ? current.toFixed(1) : current.toFixed(2)} ${unit}`;
  }

  function updateSummary() {
    const checkpoints = state.models.filter(model => model.kind === 'checkpoints').length;
    const loras = state.models.filter(model => model.kind === 'loras').length;
    if (qs('#model-total')) qs('#model-total').textContent = String(state.models.length);
    if (qs('#checkpoint-total')) qs('#checkpoint-total').textContent = String(checkpoints);
    if (qs('#lora-total')) qs('#lora-total').textContent = String(loras);
  }

  function currentFilteredModels() {
    const family = qs('#model-family-filter')?.value || '';
    const kind = qs('#model-kind-filter')?.value || '';
    const search = (qs('#model-search')?.value || '').trim().toLowerCase();
    return state.models.filter(model => {
      if (family && model.family !== family) return false;
      if (kind && model.kind !== kind) return false;
      if (search) {
        const haystack = `${model.name} ${model.filename} ${model.path}`.toLowerCase();
        if (!haystack.includes(search)) return false;
      }
      return true;
    });
  }

  function copyText(text) {
    if (navigator.clipboard?.writeText && window.isSecureContext) return navigator.clipboard.writeText(text);
    const area = document.createElement('textarea');
    area.value = text;
    area.style.position = 'fixed';
    area.style.opacity = '0';
    document.body.appendChild(area);
    area.select();
    try { document.execCommand('copy'); } finally { area.remove(); }
    return Promise.resolve();
  }

  function modelRow(model) {
    const row = document.createElement('div');
    row.className = 'model-row';

    const nameWrap = document.createElement('div');
    nameWrap.className = 'model-name-wrap';
    const name = document.createElement('div');
    name.className = 'model-name';
    name.textContent = model.name;
    name.title = model.name;
    const file = document.createElement('div');
    file.className = 'model-file';
    file.textContent = model.filename;
    nameWrap.append(name, file);

    const family = document.createElement('span');
    family.className = 'model-family-badge';
    family.textContent = FAMILY_LABELS[model.family] || model.family;

    const kind = document.createElement('span');
    kind.className = 'model-kind-badge';
    kind.textContent = model.kind === 'checkpoints' ? 'Model' : 'LoRA';

    const path = document.createElement('div');
    path.className = 'model-path';
    path.textContent = model.path;
    path.title = model.path;

    const size = document.createElement('div');
    size.className = 'model-size';
    size.textContent = formatBytes(model.size_bytes);

    let action;
    if (model.kind === 'checkpoints') {
      action = document.createElement('button');
      action.className = 'primary-button use-model-button';
      action.textContent = 'Use';
      action.addEventListener('click', () => useModel(model.id));
    } else {
      action = document.createElement('button');
      action.className = 'secondary-button use-model-button';
      action.textContent = 'Copy Tag';
      action.addEventListener('click', async () => {
        const tag = `<lora:${model.name}:1.0>`;
        try {
          await copyText(tag);
          toast('LoRA tag copied', tag, 'success');
        } catch (error) {
          toast('Could not copy LoRA tag', error.message, 'error');
        }
      });
    }

    row.append(nameWrap, family, kind, path, size, action);
    return row;
  }

  function renderModels() {
    const list = qs('#model-list');
    if (!list) return;
    const models = currentFilteredModels();
    list.replaceChildren();

    if (!state.models.length) {
      const empty = document.createElement('div');
      empty.className = 'model-empty';
      empty.innerHTML = '<strong>No indexed models yet</strong><span>Configure directories under Settings, then press Scan Models.</span>';
      list.appendChild(empty);
      return;
    }

    if (!models.length) {
      const empty = document.createElement('div');
      empty.className = 'model-empty';
      empty.innerHTML = '<strong>No matching files</strong><span>Try changing the search or filters.</span>';
      list.appendChild(empty);
      return;
    }

    models.forEach(model => list.appendChild(modelRow(model)));
    const note = document.createElement('div');
    note.className = 'model-count-note';
    note.textContent = `Showing ${models.length} of ${state.models.length} indexed file${state.models.length === 1 ? '' : 's'}.`;
    list.appendChild(note);
  }

  function updateImageBadge() {
    const select = qs('#image-model-select');
    const badge = qs('#image-model-family-badge');
    if (!select || !badge) return;
    const model = state.models.find(item => item.id === select.value);
    badge.textContent = model ? (FAMILY_LABELS[model.family] || model.family) : 'No model';
    if (model) localStorage.setItem('morphorum.image.modelId', model.id);
  }

  function populateImageModelSelect() {
    const select = qs('#image-model-select');
    if (!select) return;
    const previous = select.value || localStorage.getItem('morphorum.image.modelId') || '';
    const models = state.models.filter(model => model.kind === 'checkpoints');
    select.replaceChildren();

    const placeholder = document.createElement('option');
    placeholder.value = '';
    placeholder.textContent = models.length ? 'Select a model…' : 'No checkpoint models indexed';
    select.appendChild(placeholder);

    for (const model of models) {
      const option = document.createElement('option');
      option.value = model.id;
      option.textContent = `[${FAMILY_LABELS[model.family] || model.family}] ${model.name}`;
      option.title = model.path;
      select.appendChild(option);
    }
    select.disabled = models.length === 0;
    if (models.some(model => model.id === previous)) select.value = previous;
    updateImageBadge();
  }

  function useModel(modelId) {
    const select = qs('#image-model-select');
    const model = state.models.find(item => item.id === modelId);
    if (!select || !model) return;
    select.value = modelId;
    updateImageBadge();
    qs('.nav-button[data-view="image"]')?.click();
    toast('Model selected', `${model.name} is selected for image generation.`, 'success');
  }

  async function loadModels({ announce = false } = {}) {
    const list = qs('#model-list');
    try {
      const payload = await api('/api/models?limit=2000');
      state.models = Array.isArray(payload.models) ? payload.models : [];
      updateSummary();
      renderModels();
      populateImageModelSelect();
      if (announce) toast('Model index loaded', `${state.models.length} file(s) available.`, 'success');
    } catch (error) {
      if (list) list.innerHTML = `<div class="model-empty"><strong>Could not load model index</strong><span>${String(error.message)}</span></div>`;
      toast('Model index unavailable', error.message, 'error', 6500);
    }
  }

  async function scanModels() {
    const button = qs('#scan-models');
    setBusy(button, true);
    try {
      const result = await api('/api/models/scan', { method: 'POST', body: '{}' });
      await loadModels();
      if (result.warnings?.length) {
        toast('Model scan complete', `${result.total} file(s) indexed with ${result.warnings.length} warning(s).`, 'warning', 6000);
      } else {
        toast('Model scan complete', `${result.total} file(s) indexed from ${result.scanned_roots} configured directorie(s).`, 'success');
      }
    } catch (error) {
      toast('Model scan failed', error.message, 'error', 7000);
    } finally {
      setBusy(button, false);
    }
  }

  function bind() {
    qs('#scan-models')?.addEventListener('click', scanModels);
    qs('#model-search')?.addEventListener('input', renderModels);
    qs('#model-family-filter')?.addEventListener('change', renderModels);
    qs('#model-kind-filter')?.addEventListener('change', renderModels);
    qs('#image-model-select')?.addEventListener('change', updateImageBadge);
  }

  async function start() {
    bind();
    await loadModels();
  }

  window.MorphorumModels = { reload: loadModels, scan: scanModels };
  window.addEventListener('DOMContentLoaded', start);
})();
