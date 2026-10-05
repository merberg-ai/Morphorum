(() => {
  'use strict';

  const FAMILY_DEFS = [
    ['sd15', 'Stable Diffusion 1.x'],
    ['sd2', 'Stable Diffusion 2.x'],
    ['sdxl', 'SDXL'],
    ['flux', 'Flux'],
    ['zimage', 'Z-Image'],
  ];

  const PATH_KINDS = [
    ['checkpoints', 'Model / checkpoint directories'],
    ['loras', 'LoRA directories'],
  ];

  const state = {
    settings: null,
    validation: new Map(),
    events: [],
    lastEventId: 0,
    eventSource: null,
  };

  const qs = (selector, root = document) => root.querySelector(selector);
  const qsa = (selector, root = document) => [...root.querySelectorAll(selector)];

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

  function setBusy(button, busy) {
    if (!button) return;
    button.classList.toggle('busy', busy);
    button.disabled = busy;
  }

  function toast(title, message = '', type = 'info', timeout = 4200) {
    const stack = qs('#toast-stack');
    if (!stack) return;

    const item = document.createElement('div');
    item.className = `toast ${type}`;
    item.innerHTML = `
      <div class="toast-bar"></div>
      <div><div class="toast-title"></div><div class="toast-message"></div></div>
      <button class="toast-close" aria-label="Dismiss">×</button>`;
    qs('.toast-title', item).textContent = title;
    qs('.toast-message', item).textContent = message;
    const close = () => item.remove();
    qs('.toast-close', item).addEventListener('click', close);
    stack.appendChild(item);
    if (timeout > 0) window.setTimeout(close, timeout);
    return item;
  }

  function switchView(name) {
    qsa('.nav-button').forEach(button => button.classList.toggle('active', button.dataset.view === name));
    qsa('.view').forEach(view => view.classList.toggle('active', view.id === `view-${name}`));
    if (name === 'console') renderConsole();
    try { history.replaceState(null, '', `#${name}`); } catch (_) {}
  }

  function validationKey(family, kind, path) {
    return `${family}|${kind}|${String(path || '').trim()}`;
  }

  function ingestValidation(items = []) {
    state.validation.clear();
    for (const item of items) {
      state.validation.set(validationKey(item.family, item.kind, item.path), item);
    }
  }

  function ensureFamily(family) {
    state.settings ||= {};
    state.settings.models ||= {};
    state.settings.models[family] ||= {};
    state.settings.models[family].checkpoints ||= [];
    state.settings.models[family].loras ||= [];
    return state.settings.models[family];
  }

  function makeButton(label, className = 'secondary-button') {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = className;
    button.textContent = label;
    return button;
  }

  function createPathRow(family, kind, index, value) {
    const row = document.createElement('div');
    row.className = 'path-row';

    const inputWrap = document.createElement('div');
    inputWrap.className = 'path-input-wrap';
    const input = document.createElement('input');
    input.type = 'text';
    input.className = 'path-input';
    input.value = value || '';
    input.placeholder = navigator.userAgent.includes('Windows') ? 'D:\\AI\\models\\…' : '/home/user/models/…';
    input.autocomplete = 'off';
    input.spellcheck = false;
    const dot = document.createElement('span');
    dot.className = 'path-status-dot';
    inputWrap.append(input, dot);

    const validate = makeButton('Check', 'secondary-button compact validate-path');
    const remove = makeButton('×', 'icon-button');
    remove.title = 'Remove this path';
    remove.setAttribute('aria-label', 'Remove path');

    const message = document.createElement('div');
    message.className = 'path-message';

    function refreshStatus() {
      const current = input.value.trim();
      const result = state.validation.get(validationKey(family, kind, current));
      dot.className = 'path-status-dot';
      message.className = 'path-message';
      if (!current) {
        message.textContent = 'No directory configured.';
        return;
      }
      if (!result) {
        message.textContent = 'Not validated yet.';
        return;
      }
      if (result.exists && result.is_directory && result.readable) {
        dot.classList.add('ok');
        message.classList.add('ok');
      } else if (!result.exists) {
        dot.classList.add('warn');
        message.classList.add('bad');
      } else {
        dot.classList.add('bad');
        message.classList.add('bad');
      }
      message.textContent = result.message || '';
    }

    async function checkPath(silent = false) {
      const path = input.value.trim();
      if (!path) {
        refreshStatus();
        return;
      }
      validate.disabled = true;
      try {
        const result = await api('/api/settings/validate-path', {
          method: 'POST',
          body: JSON.stringify({ path }),
        });
        result.family = family;
        result.kind = kind;
        state.validation.set(validationKey(family, kind, path), result);
        refreshStatus();
        if (!silent) {
          toast(
            result.exists && result.is_directory && result.readable ? 'Path available' : 'Path warning',
            result.message,
            result.exists && result.is_directory && result.readable ? 'success' : 'warning'
          );
        }
      } catch (error) {
        if (!silent) toast('Path check failed', error.message, 'error');
      } finally {
        validate.disabled = false;
      }
    }

    input.addEventListener('input', () => {
      const familyData = ensureFamily(family);
      familyData[kind][index] = input.value;
      refreshStatus();
    });
    input.addEventListener('blur', () => { if (input.value.trim()) checkPath(true); });
    validate.addEventListener('click', () => checkPath(false));
    remove.addEventListener('click', () => {
      ensureFamily(family)[kind].splice(index, 1);
      renderSettings();
    });

    row.append(inputWrap, validate, remove, message);
    refreshStatus();
    return row;
  }

  function createPathSection(family, kind, label) {
    const section = document.createElement('div');
    section.className = 'path-section';

    const header = document.createElement('div');
    header.className = 'path-section-header';
    const title = document.createElement('strong');
    title.textContent = label;
    const add = makeButton('+ Add path', 'secondary-button add-path');
    add.addEventListener('click', () => {
      ensureFamily(family)[kind].push('');
      renderSettings();
      const inputs = qsa(`.family-card[data-family="${family}"] .path-input`);
      inputs.at(-1)?.focus();
    });
    header.append(title, add);

    const list = document.createElement('div');
    list.className = 'path-list';
    const paths = ensureFamily(family)[kind];
    if (!paths.length) {
      const empty = document.createElement('div');
      empty.className = 'path-message';
      empty.textContent = 'No directories configured.';
      list.appendChild(empty);
    } else {
      paths.forEach((path, index) => list.appendChild(createPathRow(family, kind, index, path)));
    }

    section.append(header, list);
    return section;
  }

  function renderSettings() {
    const container = qs('#model-path-cards');
    const loader = qs('#settings-loading');
    if (!container || !state.settings) return;

    container.replaceChildren();
    for (const [family, fallbackLabel] of FAMILY_DEFS) {
      const familyData = ensureFamily(family);
      const card = document.createElement('article');
      card.className = 'card glass family-card';
      card.dataset.family = family;

      const header = document.createElement('div');
      header.className = 'family-card-header';
      const headingWrap = document.createElement('div');
      const heading = document.createElement('h2');
      heading.textContent = familyData.label || fallbackLabel;
      const code = document.createElement('div');
      code.className = 'family-code';
      code.textContent = family;
      headingWrap.append(heading, code);
      const count = document.createElement('span');
      count.className = 'badge';
      count.textContent = `${familyData.checkpoints.length} model path${familyData.checkpoints.length === 1 ? '' : 's'}`;
      header.append(headingWrap, count);
      card.appendChild(header);

      for (const [kind, label] of PATH_KINDS) {
        card.appendChild(createPathSection(family, kind, label));
      }
      container.appendChild(card);
    }

    loader.hidden = true;
    container.hidden = false;
  }

  async function loadSettings({ announce = false } = {}) {
    const button = qs('#load-settings');
    setBusy(button, true);
    try {
      const payload = await api('/api/settings');
      state.settings = payload.settings || {};
      ingestValidation(payload.validation || []);
      renderSettings();
      if (announce) toast('Settings loaded', 'Configuration reloaded from the Morphorum server.', 'success');
    } catch (error) {
      toast('Could not load settings', error.message, 'error', 7000);
      qs('#settings-loading').innerHTML = `<strong>Settings failed to load.</strong><span>${escapeHtml(error.message)}</span>`;
    } finally {
      setBusy(button, false);
    }
  }

  function modelSettingsPayload() {
    const models = {};
    for (const [family] of FAMILY_DEFS) {
      const source = ensureFamily(family);
      models[family] = {
        checkpoints: (source.checkpoints || []).map(value => String(value).trim()).filter(Boolean),
        loras: (source.loras || []).map(value => String(value).trim()).filter(Boolean),
      };
    }
    return { models };
  }

  async function saveSettings() {
    const button = qs('#save-settings');
    setBusy(button, true);
    try {
      const payload = await api('/api/settings', {
        method: 'PUT',
        body: JSON.stringify(modelSettingsPayload()),
      });
      state.settings = payload.settings || state.settings;
      ingestValidation(payload.validation || []);
      renderSettings();
      const warnings = (payload.validation || []).filter(item => !(item.exists && item.is_directory && item.readable));
      if (warnings.length) {
        toast('Settings saved', `${warnings.length} configured path${warnings.length === 1 ? '' : 's'} need attention.`, 'warning', 6000);
      } else {
        toast('Settings saved', 'Model and LoRA locations were saved successfully.', 'success');
      }
    } catch (error) {
      toast('Settings save failed', error.message, 'error', 7000);
    } finally {
      setBusy(button, false);
    }
  }

  function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>'"]/g, char => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
    })[char]);
  }

  function checkedValues(containerSelector) {
    return new Set(qsa(`${containerSelector} input[type="checkbox"]:checked`).map(input => input.value));
  }

  function renderConsole() {
    const windowEl = qs('#console-window');
    if (!windowEl) return;
    const levels = checkedValues('#level-filters');
    const categories = checkedValues('#category-filters');
    const filtered = state.events.filter(event => levels.has(event.level) && categories.has(event.category));

    if (!filtered.length) {
      windowEl.innerHTML = '<div class="console-empty">No messages match the current filters.</div>';
      return;
    }

    windowEl.innerHTML = filtered.map(event => {
      const date = new Date(event.timestamp);
      const time = Number.isNaN(date.getTime()) ? '--:--:--' : date.toLocaleTimeString([], { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
      return `<div class="console-line">
        <span class="console-time">${escapeHtml(time)}</span>
        <span class="console-level ${escapeHtml(event.level)}">${escapeHtml(event.level)}</span>
        <span class="console-category">${escapeHtml(event.category)}</span>
        <span class="console-message">${escapeHtml(event.message)}</span>
      </div>`;
    }).join('');

    if (qs('#auto-scroll')?.checked) windowEl.scrollTop = windowEl.scrollHeight;
  }

  function addConsoleEvent(event) {
    const id = Number(event.id) || 0;
    if (id && state.events.some(existing => Number(existing.id) === id)) return;
    state.events.push(event);
    if (state.events.length > 1200) state.events.splice(0, state.events.length - 1200);
    state.lastEventId = Math.max(state.lastEventId, id);
    if (qs('#view-console')?.classList.contains('active')) renderConsole();
  }

  function setConsoleConnection(ok, text) {
    const dot = qs('#console-dot');
    const label = qs('#console-status');
    dot?.classList.toggle('ok', ok);
    dot?.classList.toggle('bad', !ok);
    if (label) label.textContent = text;
  }

  async function connectConsole() {
    try {
      const initial = await api('/api/console?limit=500');
      state.events = initial.events || [];
      state.lastEventId = state.events.reduce((max, event) => Math.max(max, Number(event.id) || 0), 0);
      renderConsole();
    } catch (error) {
      toast('Console history unavailable', error.message, 'warning');
    }

    state.eventSource?.close();
    const source = new EventSource(`/api/console/stream?after_id=${state.lastEventId}`);
    state.eventSource = source;
    source.addEventListener('open', () => setConsoleConnection(true, 'Live'));
    source.addEventListener('console', message => {
      try { addConsoleEvent(JSON.parse(message.data)); } catch (_) {}
    });
    source.addEventListener('error', () => setConsoleConnection(false, 'Reconnecting…'));
  }

  async function clearServerConsole() {
    try {
      await api('/api/console', { method: 'DELETE' });
      state.events = [];
      state.lastEventId = 0;
      renderConsole();
      toast('Console buffer cleared', 'New server events will continue to appear.', 'success');
    } catch (error) {
      toast('Could not clear console', error.message, 'error');
    }
  }

  async function loadHealth() {
    const dot = qs('#runtime-dot');
    const text = qs('#runtime-text');
    try {
      const health = await api('/api/health');
      dot?.classList.add('ok');
      dot?.classList.remove('bad');
      if (text) text.textContent = `v${health.version} · API ready`;
    } catch (error) {
      dot?.classList.add('bad');
      dot?.classList.remove('ok');
      if (text) text.textContent = 'API offline';
    }
  }

  function bindUi() {
    qsa('.nav-button').forEach(button => button.addEventListener('click', () => switchView(button.dataset.view)));
    qsa('[data-jump]').forEach(button => button.addEventListener('click', () => switchView(button.dataset.jump)));
    qs('#load-settings')?.addEventListener('click', () => loadSettings({ announce: true }));
    qs('#save-settings')?.addEventListener('click', saveSettings);
    qsa('#level-filters input, #category-filters input').forEach(input => input.addEventListener('change', renderConsole));
    qs('#auto-scroll')?.addEventListener('change', renderConsole);
    qs('#clear-console-view')?.addEventListener('click', () => {
      state.events = [];
      renderConsole();
      toast('Console view cleared', 'The server buffer was left intact.', 'info');
    });
    qs('#clear-console-server')?.addEventListener('click', clearServerConsole);

    const requested = location.hash.replace('#', '');
    if (['image', 'models', 'settings', 'console'].includes(requested)) switchView(requested);
  }

  async function start() {
    bindUi();
    await Promise.allSettled([loadHealth(), loadSettings(), connectConsole()]);
  }

  window.MorphorumToast = toast;
  window.addEventListener('DOMContentLoaded', start);
})();
