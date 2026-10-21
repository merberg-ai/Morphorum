(() => {
  'use strict';

  const state = { records: [], selected: null, detail: null, civitai: null, identity: null, identifying: false, updateCheck: null, updateBusy: false, cached: null, syncing: false, bulkSelected: new Set(), bulkBusy: false, request: 0 };
  const qs = selector => document.querySelector(selector);
  const toast = (title, message, type = 'info') => window.MorphorumToast?.(title, message, type, 6000);
  const api = async (url, options = {}) => {
    const response = await fetch(url, {
      ...options,
      headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    });
    const result = await response.json();
    if (!response.ok) throw Error(result.detail || 'Request failed');
    return result;
  };

  const text = (tag, value, className = '') => {
    const node = document.createElement(tag);
    node.textContent = String(value ?? '');
    if (className) node.className = className;
    return node;
  };

  function field(parent, label, value) {
    const row = document.createElement('div');
    row.className = 'lora-manager-field';
    row.append(text('span', label, 'muted'), text('strong', value == null || value === '' ? 'Not recorded' : value));
    parent.appendChild(row);
  }

  function section(title, content) {
    const container = document.createElement('section');
    container.className = 'lora-manager-section';
    container.appendChild(text('h3', title));
    container.appendChild(content);
    return container;
  }

  function pillRow(values, key, limit = 32) {
    const el = document.createElement('div');
    el.className = 'lora-manager-pills';
    if (!values?.length) {
      el.appendChild(text('span', 'Not recorded', 'muted'));
      return el;
    }
    for (const item of values.slice(0, limit)) {
      const value = typeof item === 'string' ? item : item[key];
      const chip = text('span', value, 'lora-manager-pill');
      if (key === 'tag') chip.title = 'Training frequency: ' + item.count + '. Not a verified trigger word.';
      el.appendChild(chip);
    }
    return el;
  }

  function renderDetail() {
    const target = qs('#lora-manager-detail-body');
    const title = qs('#lora-manager-title');
    const subtitle = qs('#lora-manager-subtitle');
    const insert = qs('#lora-manager-insert');
    const advanced = qs('#lora-manager-detail-advanced');
    const preview = qs('#lora-manager-preview');
    if (!target || !title || !subtitle || !insert || !advanced) return;
    if (preview) {
      preview.replaceChildren();
      if (state.selected) {
        preview.append(window.MorphorumThumbnails?.create(state.selected.id, state.selected.name,
          'lora-detail-art') || text('span', 'NO PREVIEW', 'muted'));
      } else {
        preview.append(text('span', 'Select a LoRA to view its cached artwork.', 'muted'));
      }
    }
    target.replaceChildren();
    advanced.replaceChildren();
    const d = state.detail;
    insert.disabled = !d;
    qs('#lora-manager-copy').disabled = !d;
    updatePromptSnippet();
    qs('#lora-manager-civitai').disabled = !d;
    renderCivitai();
    if (!d) {
      title.textContent = state.selected?.name || 'Choose a LoRA';
      subtitle.textContent = state.selected ? 'Reading local metadata…' : 'Metadata and architecture diagnostics appear here.';
      target.appendChild(text('div', state.selected ? 'Inspecting safetensors header…' : 'Select a LoRA from the library.', 'model-empty'));
      return;
    }
    title.textContent = d.name;
    subtitle.textContent = d.filename + ' · ' + d.family.toUpperCase();
    const overview = document.createElement('div');
    overview.className = 'lora-manager-fields';
    field(overview, 'Base model (metadata)', d.metadata_base_model);
    field(overview, 'Indexed family', d.family.toUpperCase());
    field(overview, 'Weight format', d.adapter_format);
    field(overview, 'Container', d.format);
    field(overview, 'File size', (d.size_bytes / (1024 * 1024)).toFixed(1) + ' MiB');
    field(overview, 'Trigger source', d.trigger_source);
    field(overview, 'JSON sidecar', d.sidecar);
    field(overview, 'HTML sidecar', d.html_sidecar?.filename);
    const identityPanel = document.createElement('div');
    identityPanel.className = 'lora-exact-identity';
    const identify = text('button', state.identifying ? 'Identifying…' : 'Identify on Civitai');
    identify.type = 'button';
    identify.className = 'secondary-button compact busy-button';
    identify.disabled = state.identifying;
    identify.classList.toggle('busy', state.identifying);
    identify.title = 'Opt-in exact SHA-256 file match on Civitai';
    identify.addEventListener('click', identifySelectedLora);
    identityPanel.append(identify);
    const check = text('button', state.updateBusy ? 'Checking…' : 'Check Updates');
    check.type = 'button';
    check.className = 'secondary-button compact busy-button';
    check.disabled = state.updateBusy;
    check.classList.toggle('busy', state.updateBusy);
    check.addEventListener('click', checkSelectedLoraUpdates);
    identityPanel.append(check);
    const sync = text('button', state.syncing ? 'Syncing…' : 'Sync Civitai Info');
    sync.type = 'button';
    sync.className = 'secondary-button compact busy-button';
    sync.disabled = state.syncing;
    sync.classList.toggle('busy', state.syncing);
    sync.addEventListener('click', () => syncSelectedLora(true));
    identityPanel.append(sync);
    const view = text('button', 'View Cached Info');
    view.type = 'button';
    view.className = 'secondary-button compact';
    view.addEventListener('click', () => syncSelectedLora(false));
    identityPanel.append(view);
    if (state.cached?.synced) {
      const cached = document.createElement('div');
      cached.className = 'lora-civitai-cached';
      cached.append(text('strong', 'Cached: ' + (state.cached.name || '') + ' · ' + (state.cached.version || '')));
      cached.append(text('p', [state.cached.creator, state.cached.base_model].filter(Boolean).join(' · '), 'muted'));
      // Cached artwork is presented prominently above Quick Use.
      if (state.cached.trained_words?.length) cached.append(text('p', 'Triggers: ' + state.cached.trained_words.slice(0, 16).join(', '), 'muted'));
      if (state.cached.description) cached.append(text('p', state.cached.description.slice(0, 650), 'muted'));
      identityPanel.append(cached);
    }
    if (state.updateCheck) {
      const result = document.createElement('div');
      result.className = 'lora-update-results';
      result.append(text('p', state.updateCheck.message || 'Update check completed.', 'muted'));
      for (const candidate of (state.updateCheck.candidates || []).slice(0, 5)) {
        const link = document.createElement('a');
        link.href = candidate.url;
        link.target = '_blank';
        link.rel = 'noopener noreferrer';
        link.textContent = candidate.version + (candidate.potentially_compatible ? ' · same base model' : ' · compatibility unverified') + ' ↗';
        result.append(link);
      }
      identityPanel.append(result);
    }
    if (state.identity?.found) {
      const link = document.createElement('a');
      link.href = state.identity.url;
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
      link.textContent = 'Verified: ' + (state.identity.name || 'Civitai model') + ' · ' + (state.identity.version || 'version') + ' ↗';
      identityPanel.append(link);
    } else if (state.identity && !state.identity.found) {
      identityPanel.append(text('p', state.identity.message || 'No exact SHA-256 match found.', 'muted lora-manager-small'));
    }
    overview.append(identityPanel);
    target.appendChild(section('Identification', overview));
    if (d.html_sidecar?.text_excerpt) {
      const htmlData = document.createElement('div');
      htmlData.append(text('p', d.html_sidecar.text_excerpt, 'muted lora-manager-small'));
      if (d.html_sidecar.civitai_model_id) field(htmlData, 'Civitai model ID', d.html_sidecar.civitai_model_id);
      advanced.appendChild(section('Local HTML information', htmlData));
    }

    target.appendChild(section('Recorded trigger words', pillRow(d.trigger_words)));
    const tags = document.createElement('div');
    tags.appendChild(text('p', 'Most frequent training tags, not automatically confirmed triggers.', 'muted lora-manager-small'));
    tags.appendChild(pillRow(d.top_training_tags, 'tag', 24));
    advanced.appendChild(section('Training vocabulary', tags));

    const components = document.createElement('div');
    components.className = 'lora-manager-fields';
    field(components, 'Tensor keys', d.tensor_count);
    for (const [name, amount] of Object.entries(d.components || {})) field(components, name, amount);
    field(components, 'LoRA ranks (A/down weights)', (d.ranks || []).map(item => item.rank + ' × ' + item.modules).join(', ') || 'Unavailable');
    advanced.appendChild(section('Static tensor diagnostics', components));

    const training = document.createElement('div');
    training.className = 'lora-manager-fields';
    for (const [key, value] of Object.entries(d.training || {})) field(training, key.replace(/^ss_/, ''), value);
    if (!training.childElementCount) training.appendChild(text('p', 'No training parameters recorded.', 'muted'));
    advanced.appendChild(section('Training metadata', training));

    const notes = document.createElement('div');
    for (const warning of [...(d.warnings || []), ...(d.errors || [])]) {
      notes.appendChild(text('p', warning, 'lora-manager-warning'));
    }
    notes.appendChild(text('p', d.inspection, 'muted lora-manager-small'));
    advanced.appendChild(section('Compatibility and limitations', notes));

    const more = document.createElement('details');
    more.className = 'lora-manager-more';
    more.appendChild(text('summary', 'Raw metadata and tensor key samples'));
    const raw = document.createElement('pre');
    raw.textContent = JSON.stringify({
      metadata: d.metadata, tensor_key_examples: d.key_examples,
      tensor_shape_examples: d.shape_examples,
    }, null, 2);
    more.appendChild(raw);
    advanced.appendChild(more);
  }

  function bulkVisible() {
    const family = qs('#lora-manager-family')?.value || 'sdxl';
    const search = (qs('#lora-manager-search')?.value || '').trim().toLowerCase();
    return state.records.filter(record => record.family === family &&
      (!search || [record.name, record.filename].some(value => String(value || '').toLowerCase().includes(search))));
  }
  function updateBulkToolbar() {
    const count = state.bulkSelected.size;
    const button = qs('#lora-sync-selected');
    if (button) {
      button.disabled = state.bulkBusy || count === 0;
      button.classList.toggle('busy', state.bulkBusy);
      const label = button.querySelector('.button-label');
      if (label) label.textContent = state.bulkBusy ? 'Syncing…' : 'Sync Selected (' + count + ')';
    }
    const status = qs('#lora-bulk-status');
    if (status && !state.bulkBusy) status.textContent = count + ' selected';
    for (const id of ['lora-select-visible', 'lora-clear-selected']) {
      const control = qs('#' + id);
      if (control) control.disabled = state.bulkBusy;
    }
  }
  async function syncBulkSelected() {
    if (state.bulkBusy || !state.bulkSelected.size) return;
    const ids = [...state.bulkSelected].filter(id => state.records.some(record => record.id === id));
    state.bulkBusy = true;
    updateBulkToolbar();
    let success = 0, failed = 0;
    const errors = [];
    try {
      for (let index = 0; index < ids.length; index++) {
        const id = ids[index];
        const record = state.records.find(item => item.id === id);
        const status = qs('#lora-bulk-status');
        if (status) status.textContent = 'Syncing ' + (index + 1) + ' / ' + ids.length + ': ' + (record?.name || id);
        try {
          const result = await api('/api/civitai/library/' + encodeURIComponent(id) + '/sync',
            {method: 'POST', body: '{}'});
          if (!result.synced) throw Error('No verified metadata returned');
          success++;
          window.MorphorumThumbnails?.set(id, result);
          if (state.selected?.id === id) {
            state.cached = result;
            updatePromptSnippet();
            renderDetail();
          }
        } catch (error) {
          failed++;
          if (errors.length < 3) errors.push((record?.name || id) + ': ' + error.message);
        }
      }
      toast(failed ? 'LoRA sync finished with errors' : 'LoRA sync complete',
        success + ' succeeded, ' + failed + ' failed.' + (errors.length ? ' ' + errors.join(' | ') : ''),
        failed ? 'warning' : 'success');
    } finally {
      state.bulkBusy = false;
      renderLibrary();
      updateBulkToolbar();
      const status = qs('#lora-bulk-status');
      if (status) status.textContent = success + ' synced, ' + failed + ' failed · ' + state.bulkSelected.size + ' selected';
    }
  }

  function renderLibrary() {
    const target = qs('#lora-manager-list');
    const family = qs('#lora-manager-family')?.value || 'sdxl';
    const search = (qs('#lora-manager-search')?.value || '').trim().toLowerCase();
    const shown = bulkVisible();
    qs('#lora-manager-count').textContent = shown.length + ' matching / ' + state.records.filter(r => r.family === family).length + ' indexed';
    target.replaceChildren();
    if (!shown.length) {
      target.appendChild(text('div', 'No matching LoRAs. Check configured directories, then scan.', 'model-empty'));
      return;
    }
    for (const record of shown) {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'lora-manager-item' + (state.selected?.id === record.id ? ' selected' : '');
      button.setAttribute('role', 'option');
      button.setAttribute('aria-selected', state.selected?.id === record.id ? 'true' : 'false');
      const label = document.createElement('span');
      label.className = 'lora-item-label';
      label.append(text('strong', record.name), text('small', record.filename));
      button.append(window.MorphorumThumbnails?.create(record.id, record.name, 'lora-library-art') ||
        text('span', 'NO PREVIEW', 'library-artwork-fallback'), label);
      button.addEventListener('click', () => selectLora(record));
      const row = document.createElement('div');
      row.className = 'lora-manager-select-row';
      const checkbox = document.createElement('input');
      checkbox.type = 'checkbox';
      checkbox.className = 'lora-bulk-checkbox';
      checkbox.checked = state.bulkSelected.has(record.id);
      checkbox.disabled = state.bulkBusy;
      checkbox.setAttribute('aria-label', 'Select ' + record.name + ' for Civitai sync');
      checkbox.addEventListener('change', () => {
        if (checkbox.checked) state.bulkSelected.add(record.id);
        else state.bulkSelected.delete(record.id);
        updateBulkToolbar();
      });
      row.append(checkbox, button);
      target.append(row);
    }
    updateBulkToolbar();
  }

  async function syncSelectedLora(write) {
    const selected = state.selected;
    if (!selected || state.syncing) return;
    const request = state.request;
    state.syncing = true;
    renderDetail();
    try {
      const url = '/api/civitai/library/' + encodeURIComponent(selected.id) + (write ? '/sync' : '');
      const result = await api(url, write ? {method:'POST', body:'{}'} : {});
      if (request !== state.request) return;
      state.cached = result.synced ? result : null;
      window.MorphorumThumbnails?.set(selected.id, result);
      renderLibrary();
      if (state.cached?.trained_words?.length) updatePromptSnippet();
      toast(write ? 'Civitai metadata cached' : 'Civitai cache',
            result.synced ? 'Verified metadata available locally.' : 'No valid cached metadata. Sync first.',
            result.synced ? 'success' : 'info');
    } catch (error) {
      if (request === state.request) toast('Civitai metadata failed', error.message, 'error');
    } finally {
      if (request === state.request) { state.syncing = false; renderDetail(); }
    }
  }

  async function checkSelectedLoraUpdates() {
    const selected = state.selected;
    if (!selected || state.updateBusy) return;
    const request = state.request;
    state.updateBusy = true;
    renderDetail();
    try {
      const result = await api('/api/civitai/updates/' + encodeURIComponent(selected.id), {method:'POST', body:'{}'});
      if (request !== state.request) return;
      state.updateCheck = result;
      toast('Civitai update check', result.message || 'Checked versions.', 'info');
    } catch (error) {
      if (request === state.request) toast('Update check failed', error.message, 'error');
    } finally {
      if (request === state.request) { state.updateBusy = false; renderDetail(); }
    }
  }

  async function identifySelectedLora() {
    const selected = state.selected;
    if (!selected || state.identifying) return;
    const request = state.request;
    state.identifying = true;
    renderDetail();
    try {
      const result = await api('/api/civitai/identify/' + encodeURIComponent(selected.id), {method:'POST', body:'{}'});
      if (request !== state.request) return;
      state.identity = result;
      toast(result.found ? 'Exact SHA-256 match' : 'No verified Civitai match',
            result.found ? selected.name + ' identified on Civitai.' : result.message,
            result.found ? 'success' : 'info');
    } catch (error) {
      if (request === state.request) {
        state.identity = null;
        toast('Civitai identification failed', error.message, 'error');
      }
    } finally {
      if (request === state.request) { state.identifying = false; renderDetail(); }
    }
  }

  async function selectLora(record) {
    state.selected = record;
    state.detail = null;
    state.civitai = null;
    state.identity = null;
    state.identifying = false;
    state.updateCheck = null;
    state.updateBusy = false;
    state.cached = null;
    state.syncing = false;
    const request = ++state.request;
    renderLibrary();
    renderDetail();
    try {
      const detail = await api('/api/loras/' + encodeURIComponent(record.id) + '/inspect');
      if (request !== state.request) return;
      state.detail = detail;
      renderDetail();
      // Offline cached metadata only: no Civitai request when selecting a LoRA.
      try {
        const cached = await api('/api/civitai/library/' + encodeURIComponent(record.id));
        if (request === state.request && cached.synced) {
          state.cached = cached;
          window.MorphorumThumbnails?.set(record.id, cached);
          renderLibrary();
          renderDetail();
          updatePromptSnippet();
        }
      } catch (_) { /* Hub disabled or no cache: keep existing local trigger words. */ }
      // Refresh the selected adapter's actual runtime state and log an audit.
      refreshRuntime();
    } catch (error) {
      if (request !== state.request) return;
      qs('#lora-manager-detail-body').replaceChildren(text('p', error.message, 'lora-manager-warning'));
      qs('#lora-manager-subtitle').textContent = 'Inspection failed';
      toast('LoRA inspection failed', error.message, 'warning');
    }
  }

  async function reload() {
    try {
      const result = await api('/api/loras');
      state.records = result.loras || [];
      // Read only cached files; selecting a LoRA never downloads Civitai media.
      await window.MorphorumThumbnails?.refresh(state.records.map(item => item.id));
      const valid = new Set(state.records.map(item => item.id));
      for (const id of state.bulkSelected) if (!valid.has(id)) state.bulkSelected.delete(id);
      const selected = state.records.find(item => item.id === state.selected?.id);
      if (!selected) { state.selected = null; state.detail = null; state.civitai = null; state.identity = null; state.identifying = false; state.updateCheck = null; state.updateBusy = false; state.cached = null; state.syncing = false; ++state.request; }
      renderLibrary();
      if (selected) await selectLora(selected);
      else renderDetail();
    } catch (error) {
      toast('LoRA library unavailable', error.message, 'error');
    }
  }

  async function scan() {
    const button = qs('#lora-manager-scan');
    button.disabled = true;
    button.classList.add('busy');
    try {
      const result = await api('/api/models/scan', { method: 'POST', body: '{}' });
      await reload();
      await window.MorphorumModels?.reload?.();
      await window.MorphorumImage?.refreshLoras?.();
      toast('Library scanned', result.total + ' files indexed. ' + (result.warnings?.length || 0) + ' path warnings.', result.warnings?.length ? 'warning' : 'success');
    } catch (error) {
      toast('LoRA scan failed', error.message, 'error');
    } finally {
      button.disabled = false;
      button.classList.remove('busy');
    }
  }

  function renderCivitai() {
    const holder = qs('#lora-manager-civitai-result');
    if (!holder) return;
    holder.replaceChildren();
    const info = state.civitai;
    if (!info) return;
    if (!info.found) {
      holder.append(text('p', info.message || 'No matching version found.', 'muted lora-manager-small'));
      return;
    }
    const content = document.createElement('div');
    content.className = 'lora-manager-fields';
    field(content, 'Match confidence', info.confidence);
    field(content, 'Model / version', [info.model_name, info.version_name].filter(Boolean).join(' · '));
    field(content, 'Civitai base model', info.base_model);
    field(content, 'Creator', info.creator);
    field(content, 'Model type', info.type);
    field(content, 'Reported triggers', (info.trained_words || []).join(', ') || 'Not recorded');
    field(content, 'Version ID', info.version_id);
    const card = section('Civitai model version', content);
    if (typeof info.url === 'string' && /^https:\/\/civitai\.com\/models\/\d+\?modelVersionId=\d+$/.test(info.url)) {
      const link = document.createElement('a');
      link.href = info.url;
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
      link.textContent = 'Open this version on Civitai ↗';
      link.className = 'lora-manager-civitai-link';
      card.append(link);
    }
    if (info.description_text) card.appendChild(text('p', info.description_text, 'muted lora-manager-small'));
    holder.append(card);
  }

  async function lookupCivitai() {
    const detail = state.detail;
    if (!detail) return;
    const button = qs('#lora-manager-civitai');
    const request = state.request;
    button.disabled = true;
    button.classList.add('busy');
    try {
      const result = await api('/api/loras/' + encodeURIComponent(detail.id) + '/civitai-lookup', {
        method: 'POST', body: '{}',
      });
      if (request !== state.request) return;
      state.civitai = result;
      renderCivitai();
      updatePromptSnippet();
      toast('Civitai lookup finished', result.found ? 'Version found (' + result.confidence + ').' : result.message, result.found ? 'success' : 'warning');
    } catch (error) {
      if (request !== state.request) return;
      toast('Civitai unavailable', error.message, 'warning');
    } finally {
      if (request === state.request) {
        button.disabled = false;
        button.classList.remove('busy');
      }
    }
  }

  async function refreshRuntime() {
    const holder = qs('#lora-manager-runtime-details');
    if (!holder) return;
    try {
      const selectedId = state.selected?.id;
      const status = selectedId
        ? await api('/api/loras/' + encodeURIComponent(selectedId) + '/runtime-audit', {
            method: 'POST', body: '{}',
          })
        : await api('/api/generation/model');
      holder.replaceChildren();
      field(holder, 'Checkpoint', status.model_name || 'Not loaded');
      field(holder, 'Model family', status.family || 'None');
      field(holder, 'Task', status.task);
      field(holder, 'Pipeline adapter count', (status.loras || []).length);
      field(holder, 'Active adapters', (status.active_loras || []).map(x => x.adapter_name + '=' + x.weight).join(', ') || 'None');
      const current = (status.loras || []).find(item => item.id === state.selected?.id);
      if (current) {
        field(holder, 'Selected adapter status', current.compatibility || 'normal loader');
        const stats = current.diagnostics || {};
        field(holder, 'Injected UNet tensors', stats.tensors);
        field(holder, 'Injected UNet modules', stats.modules);
        field(holder, 'Injected parameters', stats.parameters);
        field(holder, 'Injected abs-sum', stats.abs_sum);
        const active = (status.active_loras || []).find(a => a.adapter_name === current.adapter_name);
        field(holder, 'Selected adapter weight', active?.weight ?? 'Not active');
      } else if (state.selected) {
        field(holder, 'Selected LoRA', 'Not loaded on this pipeline');
      }
    } catch (error) {
      holder.replaceChildren(text('p', error.message, 'lora-manager-warning'));
    }
  }

  function snippetData() {
    const detail = state.detail;
    if (!detail) return null;
    return {
      id: detail.id, family: detail.family, name: detail.name,
      weight: Number(qs('#lora-manager-weight').value),
      triggers: qs('#lora-manager-add-triggers').checked
        ? ((state.cached?.trained_words || []).length ? state.cached.trained_words : (detail.trigger_words || []).length ? detail.trigger_words : state.civitai?.trained_words || [])
        : [],
    };
  }
  function updatePromptSnippet() {
    const output = qs('#lora-manager-snippet');
    if (!output) return;
    const data = snippetData();
    try {
      output.textContent = data ? window.MorphorumPromptTags.lora(data) : 'Select a LoRA to preview its prompt tag.';
    } catch (error) {
      output.textContent = error.message;
    }
  }
  async function copyPromptSnippet() {
    const data = snippetData();
    if (!data) return;
    try {
      const snippet = window.MorphorumPromptTags.lora(data);
      await window.MorphorumClipboard.writeText(snippet);
      toast('Prompt tag copied', 'Snippet copied with recorded trigger words when available.', 'success');
    } catch (error) {
      toast('Could not copy tag', error.message, 'warning');
    }
  }
  function insertIntoImage() {
    const data = snippetData();
    if (!data) return;
    try {
      window.MorphorumPromptTags.lora(data); // Validate the exact text that Copy uses.
    } catch (error) {
      toast('Invalid LoRA prompt tag', error.message, 'warning');
      return;
    }
    const applied = window.MorphorumImage?.insertFromManager?.(data);
    if (applied) toast('Prompt updated', data.name + ' added to Image generation.', 'success');
  }

  function init() {
    qs('#lora-manager-family')?.addEventListener('change', () => {
      state.selected = null; state.detail = null; state.civitai = null; ++state.request;
      renderLibrary(); renderDetail();
    });
    qs('#lora-manager-search')?.addEventListener('input', renderLibrary);
    qs('#lora-manager-scan')?.addEventListener('click', scan);
    qs('#lora-select-visible')?.addEventListener('click', () => {
      for (const item of bulkVisible()) state.bulkSelected.add(item.id);
      renderLibrary();
    });
    qs('#lora-clear-selected')?.addEventListener('click', () => {
      state.bulkSelected.clear();
      renderLibrary();
    });
    qs('#lora-sync-selected')?.addEventListener('click', syncBulkSelected);
    qs('#lora-manager-civitai')?.addEventListener('click', lookupCivitai);
    qs('#lora-manager-refresh-runtime')?.addEventListener('click', refreshRuntime);
    qs('#lora-manager-insert')?.addEventListener('click', insertIntoImage);
    qs('#lora-manager-copy')?.addEventListener('click', copyPromptSnippet);
    qs('#lora-manager-weight')?.addEventListener('input', updatePromptSnippet);
    qs('#lora-manager-add-triggers')?.addEventListener('change', updatePromptSnippet);
    reload();
    refreshRuntime();
  }

  window.MorphorumLoras = { reload, refreshRuntime };
  window.addEventListener('morphorum:settings-changed', reload);
  window.addEventListener('DOMContentLoaded', init);
})();
