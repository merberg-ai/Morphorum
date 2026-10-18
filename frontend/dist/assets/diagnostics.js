/* Morphorum Diagnostics tab. Uses only same-origin indexed model IDs and
 * read-only GET requests; intentionally no model loading or conversion. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const state = {models: [], data: null, leaves: [], filtered: [], loading: false, tab: 'logs'};
  const LIMIT = 350;
  const text = (tag, value, cls = '') => {
    const item = document.createElement(tag);
    item.textContent = String(value ?? '');
    if (cls) item.className = cls;
    return item;
  };
  function classify(key, value) {
    const k = key.toLowerCase();
    if (value === false && /loadable|ready|conversion_enabled|runtime_verified|binding_enabled/.test(k)) return 'unverified';
    if (value === true && /verified|matches|present|compatible/.test(k)) return 'pass';
    if (typeof value === 'string') {
      if (/^(blocked|rejected|schema_mismatch|reference_mismatch|error|unsupported|missing)$/.test(value)) return 'issue';
      if (/^(schema_matches|reference_matched|config_evidence_matches|planned|inspected|candidate_only)$/.test(value)) return 'pass';
      if (/unverified|incomplete|disabled|not_supported/.test(value)) return 'unverified';
    }
    if (/missing_reference_tensors|unexpected_external_tensors|shape_mismatches|mismatches/.test(k)
        && typeof value === 'number') return value === 0 ? 'pass' : 'issue';
    return '';
  }
  function flatten(data) {
    const leaves = [];
    const visit = (value, path, section, depth) => {
      if (depth > 24 || leaves.length > 20000) return;
      if (value && typeof value === 'object') {
        const entries = Array.isArray(value) ? value.map((v, i) => [String(i), v]) : Object.entries(value);
        if (!entries.length) {
          leaves.push({path, section, value: Array.isArray(value) ? '[]' : '{}', kind: ''});
        } else for (const [k, v] of entries) visit(v, path ? path + '.' + k : k, section || k, depth + 1);
      } else {
        leaves.push({path, section, value: value === null ? 'null' : String(value),
          kind: classify(path, value)});
      }
    };
    visit(data, '', '', 0);
    return leaves;
  }
  function updateModels(models) {
    state.models = (Array.isArray(models) ? models : []).filter(m =>
      m.family === 'zimage' && m.source !== 'managed' && m.kind === 'checkpoints');
    const select = $('diagnostic-model-select');
    const previous = select.value || sessionStorage.getItem('morphorum-diagnostic-model') || '';
    select.replaceChildren();
    select.append(text('option', state.models.length ? 'Choose Z-Image checkpoint…' : 'No external Z-Image checkpoints indexed'));
    select.firstChild.value = '';
    for (const model of state.models) {
      const option = text('option', model.name || model.filename || model.path?.split(/[\\/]/).pop() || model.id);
      option.value = model.id;
      select.append(option);
    }
    if (state.models.some(m => m.id === previous)) select.value = previous;
    else if (state.models.length === 1) select.value = state.models[0].id;
  }
  async function fetchModels() {
    try {
      const response = await fetch('/api/models?limit=2000');
      if (!response.ok) throw new Error('Model index HTTP ' + response.status);
      const result = await response.json();
      updateModels(result.models);
    } catch (e) {
      $('diagnostic-status-line').textContent = 'Model index unavailable: ' + e.message;
    }
  }
  function summaryItem(label, value, kind = '') {
    const card = document.createElement('div');
    card.className = 'diagnostic-summary-item ' + kind;
    card.append(text('span', label, 'diagnostic-summary-label'), text('strong', value));
    return card;
  }
  function summaryCard(data) {
    const summary = $('diagnostic-summary');
    summary.replaceChildren();
    if (!data) return;
    const t = data.checkpoint?.schema_validation || {};
    const e = data.auxiliary_encoders?.[0]?.header?.schema_validation || {};
    const scales = e.input_scale_metadata || {};
    const transformerBudget = data.checkpoint?.z218_stream_preflight || {};
    const encoderBudget = data.auxiliary_encoders?.[0]?.header?.z218_stream_preflight || {};
    const gib = bytes => Number.isFinite(bytes) ? (bytes / (1024 ** 3)).toFixed(2) + ' GiB' : 'Not available';
    const status = obj => obj.status === 'schema_matches' ? 'Verified' : obj.status || 'Unavailable';
    summary.append(
      summaryItem('Diagnostic', data.diagnostic_version || '?'),
      summaryItem('Transformer schema', status(t), t.schema_verified ? 'pass' : 'issue'),
      summaryItem('Encoder schema', status(e), e.schema_verified ? 'pass' : 'issue'),
      summaryItem('Transformer mapped', t.mapped_tensor_count == null ? '?' :
        t.mapped_tensor_count + ' / ' + t.reference_tensor_count),
      summaryItem('Encoder mapped', e.mapped_tensor_count == null ? '?' :
        e.mapped_tensor_count + ' / ' + e.reference_tensor_count),
      summaryItem('Encoder FP8 input scales', scales.count == null ? '?' :
        scales.count + ' total · ' + scales.nonunit_count + ' non-unit'),
      summaryItem('Transformer conversion', transformerBudget.status || 'Unavailable',
        transformerBudget.status === 'planned' ? 'pass' : 'issue'),
      summaryItem('Transformer scratch size', gib(transformerBudget.output_exact_bytes)),
      summaryItem('Encoder scratch size', gib(encoderBudget.output_exact_bytes)),
      summaryItem('Encoder conversion', encoderBudget.status || 'Unavailable',
        encoderBudget.status === 'planned' ? 'pass' : 'issue'),
      summaryItem('Standalone loadable', data.loadable ? 'Yes' : 'No (safeguard)', data.loadable ? 'pass' : 'unverified')
    );
  }
  function render() {
    const search = ($('diagnostic-search').value || '').trim().toLowerCase();
    const section = $('diagnostic-section').value;
    const status = $('diagnostic-status').value;
    state.filtered = state.leaves.filter(row =>
      (!section || row.section === section) && (!status || row.kind === status) &&
      (!search || (row.path + ' ' + row.value).toLowerCase().includes(search))
    );
    $('diagnostic-results-count').textContent = state.filtered.length.toLocaleString() + ' matching fields';
    const results = $('diagnostic-results');
    results.replaceChildren();
    if (!state.filtered.length) {
      results.append(text('p', 'No matching diagnostic fields.', 'muted'));
      return;
    }
    const fragment = document.createDocumentFragment();
    for (const row of state.filtered.slice(0, LIMIT)) {
      const el = document.createElement('div');
      el.className = 'diagnostic-result-row ' + row.kind;
      el.append(text('span', row.path, 'diagnostic-path'),
                text('span', row.value, 'diagnostic-value'));
      el.title = row.path;
      fragment.append(el);
    }
    results.append(fragment);
    if (state.filtered.length > LIMIT) results.append(text('p',
      'Showing the first ' + LIMIT + ' matches. Narrow the search to view more.', 'diagnostic-truncated'));
  }
  function populateSections() {
    const select = $('diagnostic-section');
    select.replaceChildren();
    const all = text('option', 'All sections'); all.value = ''; select.append(all);
    const sections = [...new Set(state.leaves.map(r => r.section))].sort();
    for (const section of sections) {
      const option = text('option', section);
      option.value = section; select.append(option);
    }
  }
  async function loadDiagnostics() {
    const model = $('diagnostic-model-select').value;
    if (!model || !state.models.some(m => m.id === model) || state.loading) return;
    state.loading = true;
    $('diagnostic-refresh').disabled = true;
    $('diagnostic-status-line').textContent = 'Inspecting ' +
      (state.models.find(m => m.id === model)?.name || 'checkpoint') + '…';
    sessionStorage.setItem('morphorum-diagnostic-model', model);
    try {
      const response = await fetch('/api/models/' + encodeURIComponent(model) + '/zimage-diagnostics', {
        headers: {'Accept': 'application/json'}, cache: 'no-store'
      });
      if (!response.ok) {
        let body; try { body = await response.json(); } catch (_) {}
        throw new Error(body?.detail || 'HTTP ' + response.status);
      }
      const payload = await response.json();
      state.data = payload;
      state.leaves = flatten(payload);
      populateSections();
      summaryCard(payload);
      render();
      $('diagnostic-copy-json').disabled = false;
      $('diagnostic-copy-filtered').disabled = false;
      $('diagnostic-status-line').textContent = 'Read-only diagnostic · ' +
        (payload.diagnostic_version || '?') + ' · ' + state.leaves.length.toLocaleString() +
        ' fields · refreshed ' + new Date().toLocaleTimeString();
    } catch (error) {
      $('diagnostic-status-line').textContent = 'Diagnostic request failed: ' + error.message;
    } finally {
      state.loading = false;
      $('diagnostic-refresh').disabled = false;
    }
  }
  async function copy(value, label) {
    try {
      await navigator.clipboard.writeText(value);
      $('diagnostic-status-line').textContent = label + ' copied.';
    } catch (error) {
      $('diagnostic-status-line').textContent = 'Copy failed: ' + error.message;
    }
  }
  function setTab(which) {
    state.tab = which;
    for (const key of ['logs', 'diagnostics']) {
      const selected = key === which;
      const button = $('console-tab-' + key);
      button.classList.toggle('active', selected);
      button.setAttribute('aria-selected', String(selected));
      $('console-panel-' + key).hidden = !selected;
    }
    if (which === 'diagnostics' && !state.models.length) fetchModels();
  }
  window.addEventListener('morphorum:models-updated', event => updateModels(event.detail?.models || []));
  window.addEventListener('DOMContentLoaded', () => {
    for (const tab of document.querySelectorAll('[data-console-inner-tab]')) {
      tab.addEventListener('click', () => setTab(tab.dataset.consoleInnerTab));
    }
    $('diagnostic-refresh').addEventListener('click', loadDiagnostics);
    $('diagnostic-model-select').addEventListener('change', () =>
      sessionStorage.setItem('morphorum-diagnostic-model', $('diagnostic-model-select').value));
    for (const id of ['diagnostic-section', 'diagnostic-status', 'diagnostic-search']) {
      $(id).addEventListener(id === 'diagnostic-search' ? 'input' : 'change', render);
    }
    $('diagnostic-copy-json').addEventListener('click', () =>
      state.data && copy(JSON.stringify(state.data, null, 2), 'Full diagnostic JSON'));
    $('diagnostic-copy-filtered').addEventListener('click', () =>
      copy(state.filtered.map(r => r.path + '\t' + r.value).join('\n'), 'Filtered diagnostic fields'));
    fetchModels();
  });
})();
