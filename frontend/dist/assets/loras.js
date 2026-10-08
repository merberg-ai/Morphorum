(() => {
  'use strict';

  const state = { records: [], selected: null, detail: null, civitai: null, request: 0 };
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
    if (!target || !title || !subtitle || !insert) return;
    target.replaceChildren();
    const d = state.detail;
    insert.disabled = !d;
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
    target.appendChild(section('Identification', overview));
    if (d.html_sidecar?.text_excerpt) {
      const htmlData = document.createElement('div');
      htmlData.append(text('p', d.html_sidecar.text_excerpt, 'muted lora-manager-small'));
      if (d.html_sidecar.civitai_model_id) field(htmlData, 'Civitai model ID', d.html_sidecar.civitai_model_id);
      target.appendChild(section('Local HTML information', htmlData));
    }

    target.appendChild(section('Recorded trigger words', pillRow(d.trigger_words)));
    const tags = document.createElement('div');
    tags.appendChild(text('p', 'Most frequent training tags, not automatically confirmed triggers.', 'muted lora-manager-small'));
    tags.appendChild(pillRow(d.top_training_tags, 'tag', 24));
    target.appendChild(section('Training vocabulary', tags));

    const components = document.createElement('div');
    components.className = 'lora-manager-fields';
    field(components, 'Tensor keys', d.tensor_count);
    for (const [name, amount] of Object.entries(d.components || {})) field(components, name, amount);
    field(components, 'LoRA ranks (A/down weights)', (d.ranks || []).map(item => item.rank + ' × ' + item.modules).join(', ') || 'Unavailable');
    target.appendChild(section('Static tensor diagnostics', components));

    const training = document.createElement('div');
    training.className = 'lora-manager-fields';
    for (const [key, value] of Object.entries(d.training || {})) field(training, key.replace(/^ss_/, ''), value);
    if (!training.childElementCount) training.appendChild(text('p', 'No training parameters recorded.', 'muted'));
    target.appendChild(section('Training metadata', training));

    const notes = document.createElement('div');
    for (const warning of [...(d.warnings || []), ...(d.errors || [])]) {
      notes.appendChild(text('p', warning, 'lora-manager-warning'));
    }
    notes.appendChild(text('p', d.inspection, 'muted lora-manager-small'));
    target.appendChild(section('Compatibility and limitations', notes));

    const more = document.createElement('details');
    more.className = 'lora-manager-more';
    more.appendChild(text('summary', 'Raw metadata and tensor key samples'));
    const raw = document.createElement('pre');
    raw.textContent = JSON.stringify({
      metadata: d.metadata, tensor_key_examples: d.key_examples,
      tensor_shape_examples: d.shape_examples,
    }, null, 2);
    more.appendChild(raw);
    target.appendChild(more);
  }

  function renderLibrary() {
    const target = qs('#lora-manager-list');
    const family = qs('#lora-manager-family')?.value || 'sdxl';
    const search = (qs('#lora-manager-search')?.value || '').trim().toLowerCase();
    const shown = state.records.filter(record =>
      record.family === family &&
      (!search || [record.name, record.filename].some(value => String(value || '').toLowerCase().includes(search)))
    );
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
      button.append(text('strong', record.name), text('small', record.filename));
      button.addEventListener('click', () => selectLora(record));
      target.append(button);
    }
  }

  async function selectLora(record) {
    state.selected = record;
    state.detail = null;
    state.civitai = null;
    const request = ++state.request;
    renderLibrary();
    renderDetail();
    try {
      const detail = await api('/api/loras/' + encodeURIComponent(record.id) + '/inspect');
      if (request !== state.request) return;
      state.detail = detail;
      renderDetail();
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
      const selected = state.records.find(item => item.id === state.selected?.id);
      if (!selected) { state.selected = null; state.detail = null; state.civitai = null; ++state.request; }
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

  function insertIntoImage() {
    const detail = state.detail;
    if (!detail) return;
    const raw = Number(qs('#lora-manager-weight').value);
    if (!Number.isFinite(raw) || raw < -4 || raw > 4) {
      toast('Invalid LoRA strength', 'Use a value between -4 and 4.', 'warning');
      return;
    }
    const triggers = qs('#lora-manager-add-triggers').checked
      ? ((detail.trigger_words || []).length ? detail.trigger_words : state.civitai?.trained_words || [])
      : [];
    const applied = window.MorphorumImage?.insertFromManager?.({
      id: detail.id, family: detail.family, name: detail.name, weight: raw, triggers,
    });
    if (applied) toast('Prompt updated', detail.name + ' added to Image generation.', 'success');
  }

  function init() {
    qs('#lora-manager-family')?.addEventListener('change', () => {
      state.selected = null; state.detail = null; state.civitai = null; ++state.request;
      renderLibrary(); renderDetail();
    });
    qs('#lora-manager-search')?.addEventListener('input', renderLibrary);
    qs('#lora-manager-scan')?.addEventListener('click', scan);
    qs('#lora-manager-civitai')?.addEventListener('click', lookupCivitai);
    qs('#lora-manager-refresh-runtime')?.addEventListener('click', refreshRuntime);
    qs('#lora-manager-insert')?.addEventListener('click', insertIntoImage);
    reload();
    refreshRuntime();
  }

  window.MorphorumLoras = { reload };
  window.addEventListener('morphorum:settings-changed', reload);
  window.addEventListener('DOMContentLoaded', init);
})();
