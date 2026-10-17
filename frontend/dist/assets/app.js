(() => {
  'use strict';

  let FAMILY_DEFS = [
    ['sdxl', 'SDXL', 'external', 'external', true],
    ['flux', 'Flux', 'external', 'external', true],
    ['zimage', 'Z-Image', 'managed', 'external', true],
  ];

  const PATH_KINDS = [
    ['checkpoints', 'Model / checkpoint directories'],
    ['loras', 'LoRA directories'],
  ];

  const THEME_OPTIONS = [
    ['midnight-glass', 'Midnight Glass · Black'],
    ['deep-ocean', 'Deep Ocean · Dark Blue'],
    ['amethyst-night', 'Amethyst Night · Dark Purple'],
    ['slate-graphite', 'Slate Graphite · Grey'],
  ];
  const FONT_STYLE_OPTIONS = [
    ['modern', 'Modern'],
    ['humanist', 'Humanist'],
    ['geometric', 'Geometric'],
    ['technical', 'Technical'],
  ];
  const MONO_FONT_STYLE_OPTIONS = [
    ['modern-mono', 'Modern Mono'],
    ['cascadia', 'Cascadia'],
    ['classic-mono', 'Classic Mono'],
    ['compact-mono', 'Compact Mono'],
  ];
  const UI_SCALE_OPTIONS = [
    ['compact', 'Compact'],
    ['standard', 'Standard'],
    ['comfortable', 'Comfortable'],
  ];
  const UI_FONT_FACES = {
    modern: 'Inter',
    humanist: 'Source Sans 3',
    geometric: 'Space Grotesk',
    technical: 'IBM Plex Sans Condensed',
  };
  const MONO_FONT_FACES = {
    'modern-mono': 'JetBrains Mono',
    cascadia: 'Cascadia Code',
    'classic-mono': 'IBM Plex Mono',
    'compact-mono': 'Roboto Mono',
  };

  const state = {
    settings: null,
    validation: new Map(),
    events: [],
    lastEventId: 0,
    eventSource: null,
    telemetryTimer: null,
    jobs: { image: null, animation: null },
    settingsDirty: false,
    settingsRequestBusy: false,
    settingsTab: 'appearance',
    foregroundJobType: null,
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

  const recentToasts = new Map();
  function toast(title, message = '', type = 'info', timeout = 4200) {
    const stack = qs('#toast-stack');
    if (!stack) return;
    const level = {info: 0, success: 1, warning: 2, error: 3};
    const severity = level[type] ?? 0;
    const signature = JSON.stringify([type, String(title), String(message)]);
    const now = Date.now();
    // Background reconnection failures must not generate a wall of identical toasts.
    if (now - (recentToasts.get(signature) || 0) < 30000) return;
    recentToasts.set(signature, now);
    if (recentToasts.size > 80) recentToasts.delete(recentToasts.keys().next().value);
    const displayed = [...stack.querySelectorAll('.toast')];
    if (displayed.length >= 4) {
      const evict = displayed.reduce((a, b) =>
        (level[b.dataset.type] ?? 0) < (level[a.dataset.type] ?? 0) ? b : a);
      if ((level[evict.dataset.type] ?? 0) > severity) return;
      evict.remove();
    }
    const item = document.createElement('div');
    item.className = 'toast ' + type;
    item.dataset.type = type;
    item.setAttribute('role', type === 'error' ? 'alert' : 'status');
    item.innerHTML = `
      <div class="toast-bar"></div>
      <div><div class="toast-title"></div><div class="toast-message"></div></div>
      <button class="toast-close" aria-label="Dismiss notification">×</button>`;
    qs('.toast-title', item).textContent = title;
    qs('.toast-message', item).textContent = message;
    const close = () => item.remove();
    qs('.toast-close', item).addEventListener('click', close);
    stack.appendChild(item);
    const visibleMs = type === 'error' ? Math.max(10000, timeout) :
      type === 'warning' ? Math.max(7000, timeout) : timeout;
    if (visibleMs > 0) window.setTimeout(close, visibleMs);
    return item;
  }

  function updateGlobalJobStatus() {
    const panel = qs('#global-job-status');
    if (!panel) return;
    const active = Object.values(state.jobs).filter(job => job &&
      ['queued','loading_model','generating','rendering','finalizing','paused','pause_requested'].includes(job.status));
    if (!active.some(job => job.type === state.foregroundJobType)) {
      state.foregroundJobType = active[0]?.type || null;
    }
    const current = active.find(job => job.type === state.foregroundJobType);
    panel.hidden = !current;
    panel.dataset.jobType = current?.type || '';
    if (!current) return;
    const percent = Math.max(0, Math.min(100, Math.round(Number(current.progress || 0) * 100)));
    const kind = current.type === 'image' ? 'Image' : 'Animation';
    const phase = String(current.status || '').replaceAll('_',' ');
    const count = current.total ? ' · ' + Math.min(current.current, current.total) + '/' + current.total : '';
    const eta = current.eta_seconds == null || !Number.isFinite(Number(current.eta_seconds))
      ? '' : ' · ETA ' + Math.round(Number(current.eta_seconds)) + 's';
    qs('#global-job-label').textContent = kind + count + ' · ' + phase + eta;
    qs('#global-job-percent').textContent = percent + '%';
    qs('#global-job-progress-fill').style.width = percent + '%';
    qs('.global-job-progress', panel)?.setAttribute('aria-valuenow', String(percent));
  }
  function openActiveJob() {
    const kind = qs('#global-job-status')?.dataset.jobType;
    if (!kind) return;
    switchView(kind === 'image' ? 'image' : 'animation');
    if (kind === 'animation') {
      qs('#animation-tab-monitor')?.click();
    } else {
      qs('#generation-progress')?.scrollIntoView({behavior:'smooth',block:'start'});
    }
  }
  function closeNavMore() {
    const menu = qs('#nav-more-menu'), toggle = qs('#nav-more-toggle');
    if (menu) menu.hidden = true;
    if (toggle) toggle.setAttribute('aria-expanded', 'false');
  }
  function refreshNavMore(name) {
    const more = qs('#nav-more-toggle');
    if (more) more.classList.toggle('active', name === 'settings' || name === 'console');
    closeNavMore();
  }

  function switchView(name) {
    qsa('.nav-button').forEach(button => button.classList.toggle('active', button.dataset.view === name));
    if (name !== 'animation') qsa('.main-nav [data-project-nav]').forEach(button => {
      button.classList.remove('active');
      button.removeAttribute('aria-current');
    });
    qs('.main-nav')?.classList.toggle('motion-section-active', name === 'animation');
    qsa('.view').forEach(view => view.classList.toggle('active', view.id === `view-${name}`));
    refreshNavMore(name);
    if (name === 'console') renderConsole();
    const projectToggle = qs('#project-nav-toggle');
    if (projectToggle) projectToggle.classList.toggle('active', name === 'animation' && !qs('.main-nav.motion-section-active [data-motion-nav].active'));
    if (name === 'civitai') window.MorphorumCivitai?.activate?.();
    if (name === 'loras') window.MorphorumLoras?.refreshRuntime?.();
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

  function updateAppearanceDiagnostic(ui = {}) {
    const diagnostic = qs('#appearance-font-diagnostic');
    const sample = qs('#appearance-ui-sample');
    const monoSample = qs('#appearance-mono-sample');
    if (!diagnostic) return;

    const fontStyle = String(ui.font_style || 'modern');
    const monoStyle = String(ui.mono_font_style || 'modern-mono');
    const uiFace = UI_FONT_FACES[fontStyle] || UI_FONT_FACES.modern;
    const monoFace = MONO_FONT_FACES[monoStyle] || MONO_FONT_FACES['modern-mono'];
    const rootSize = getComputedStyle(document.documentElement).fontSize;
    const computedUi = getComputedStyle(document.body).fontFamily;
    const computedMono = monoSample ? getComputedStyle(monoSample).fontFamily : '';

    const uiLoaded = document.fonts?.check ? document.fonts.check('16px "' + uiFace + '"') : null;
    const monoLoaded = document.fonts?.check ? document.fonts.check('16px "' + monoFace + '"') : null;

    if (sample) sample.textContent = 'Interface sample · ' + uiFace;
    if (monoSample) monoSample.textContent = 'seed=2745621820 · FlowMatch Euler';
    diagnostic.textContent =
      'UI: ' + uiFace + ' ' + (uiLoaded === false ? '(fallback)' : '(loaded)') + ' · ' +
      'Mono: ' + monoFace + ' ' + (monoLoaded === false ? '(fallback)' : '(loaded)') + ' · ' +
      'root ' + rootSize;
    diagnostic.title = 'Computed UI: ' + computedUi + '\nComputed mono: ' + computedMono;
  }

  function applyAppearance(ui = {}) {
    const root = document.documentElement;
    const requestedTheme = String(ui.theme || 'midnight-glass');
    const theme = THEME_OPTIONS.some(([id]) => id === requestedTheme)
      ? requestedTheme : 'midnight-glass';
    const fontStyle = UI_FONT_FACES[ui.font_style] ? ui.font_style : 'modern';
    const monoStyle = MONO_FONT_FACES[ui.mono_font_style] ? ui.mono_font_style : 'modern-mono';
    const uiScale = UI_SCALE_OPTIONS.some(([id]) => id === ui.ui_scale)
      ? ui.ui_scale : 'compact';

    root.dataset.theme = theme;
    root.dataset.fontStyle = fontStyle;
    root.dataset.monoStyle = monoStyle;
    root.dataset.uiScale = uiScale;
    // A single document-level contract controls body text, dialogs, form
    // widgets, editors, and dynamically injected Motion Lab panels.
    const themeColor = getComputedStyle(root).getPropertyValue('--bg').trim();
    const metaTheme = qs('meta[name="theme-color"]');
    if (metaTheme && themeColor) metaTheme.setAttribute('content', themeColor);

    try {
      localStorage.setItem('morphorum.ui.theme', theme);
      localStorage.setItem('morphorum.ui.fontStyle', fontStyle);
      localStorage.setItem('morphorum.ui.monoStyle', monoStyle);
      localStorage.setItem('morphorum.ui.uiScale', uiScale);
    } catch (_) {}

    requestAnimationFrame(() => updateAppearanceDiagnostic(ui));
    if (document.fonts?.load) {
      const uiFace = UI_FONT_FACES[fontStyle] || UI_FONT_FACES.modern;
      const monoFace = MONO_FONT_FACES[monoStyle] || MONO_FONT_FACES['modern-mono'];
      Promise.allSettled([
        document.fonts.load('16px "' + uiFace + '"'),
        document.fonts.load('16px "' + monoFace + '"'),
      ]).then(() => updateAppearanceDiagnostic(ui));
    }
  }
  function ensurePreferences() {
    state.settings ||= {};
    state.settings.ui ||= {};
    state.settings.performance ||= {};
    state.settings.ui.theme ||= 'midnight-glass';
    state.settings.ui.font_style ||= 'modern';
    state.settings.ui.mono_font_style ||= 'modern-mono';
    state.settings.ui.ui_scale ||= 'compact';
    state.settings.ui.show_help_hints = state.settings.ui.show_help_hints !== false;
    if (!Number.isFinite(Number(state.settings.ui.image_preview_limit))) {
      state.settings.ui.image_preview_limit = 5;
    }
    state.settings.performance.unload_after_generation = Boolean(
      state.settings.performance.unload_after_generation
    );
    state.settings.performance.sdxl_vae_tiling = Boolean(
      state.settings.performance.sdxl_vae_tiling
    );
  }

  function ensureManagedModels() {
    state.settings ||= {};
    state.settings.managed_models ||= {};
    state.settings.managed_models.locations ||= {};
    state.settings.managed_models.locations.zimage ||= '.\\ckpts\\z-image';
    return state.settings.managed_models;
  }

  function markSettingsDirty() {
    state.settingsDirty = true;
    renderSettingsDirtyState();
  }
  function setSettingsClean() {
    state.settingsDirty = false;
    renderSettingsDirtyState();
  }
  function renderSettingsDirtyState() {
    const badge = qs('#settings-dirty-state');
    if (badge) {
      badge.textContent = state.settingsDirty ? 'Unsaved changes' : 'All changes saved';
      badge.classList.toggle('dirty', state.settingsDirty);
    }
  }
  function selectSettingsTab(tab, { persist = true } = {}) {
    if (!['appearance','generation','paths','storage','civitai'].includes(tab)) return;
    state.settingsTab = tab;
    qsa('#settings-internal-tabs button[data-settings-tab]').forEach(button => {
      const selected = button.dataset.settingsTab === tab;
      button.classList.toggle('active', selected);
      button.setAttribute('aria-selected', String(selected));
    });
    qsa('#model-path-cards .settings-pane').forEach(pane => {
      pane.hidden = pane.dataset.settingsPane !== tab;
    });
    if (persist) try { localStorage.setItem('morphorum.settings.tab.v1', tab); } catch (_) {}
  }

  function createSelectField(id, labelText, options, value, onChange) {
    const label = document.createElement('label');
    const title = document.createElement('span');
    title.textContent = labelText;
    const select = document.createElement('select');
    select.id = id;
    for (const [optionValue, optionLabel] of options) {
      const option = document.createElement('option');
      option.value = optionValue;
      option.textContent = optionLabel;
      select.appendChild(option);
    }
    select.value = value;
    select.addEventListener('change', () => onChange(select.value));
    label.append(title, select);
    return label;
  }

  function createAppearanceCard() {
    ensurePreferences();
    const ui = state.settings.ui;

    const card = document.createElement('article');
    card.className = 'card glass settings-preferences-card appearance-settings-card';

    const header = document.createElement('div');
    header.className = 'card-header';
    const headingWrap = document.createElement('div');
    const heading = document.createElement('h2');
    heading.textContent = 'Theme & Appearance';
    const sub = document.createElement('p');
    sub.className = 'muted';
    sub.textContent = 'Choose the visual theme, typography, and interface density.';
    headingWrap.append(heading, sub);
    header.appendChild(headingWrap);

    const grid = document.createElement('div');
    grid.className = 'field-grid appearance-grid';

    const apply = () => applyAppearance(ui);

    const themeField = createSelectField(
      'ui-theme',
      'Theme',
      THEME_OPTIONS,
      ui.theme || 'midnight-glass',
      value => { ui.theme = value; apply(); }
    );

    const fontField = createSelectField(
      'ui-font-style',
      'Interface font',
      FONT_STYLE_OPTIONS,
      ui.font_style || 'modern',
      value => { ui.font_style = value; apply(); }
    );

    const monoField = createSelectField(
      'ui-mono-font-style',
      'Technical / console font',
      MONO_FONT_STYLE_OPTIONS,
      ui.mono_font_style || 'modern-mono',
      value => { ui.mono_font_style = value; apply(); }
    );

    const scaleField = createSelectField(
      'ui-scale',
      'UI scale',
      UI_SCALE_OPTIONS,
      ui.ui_scale || 'compact',
      value => { ui.ui_scale = value; apply(); }
    );

    const preview = document.createElement('div');
    preview.className = 'appearance-preview';

    const previewTitle = document.createElement('strong');
    previewTitle.textContent = 'Morphorum UI Preview';

    const uiSample = document.createElement('span');
    uiSample.id = 'appearance-ui-sample';
    uiSample.textContent = 'Interface sample';

    const monoSample = document.createElement('code');
    monoSample.id = 'appearance-mono-sample';
    monoSample.textContent = 'seed=2745621820 · FlowMatch Euler';

    const diagnostic = document.createElement('small');
    diagnostic.id = 'appearance-font-diagnostic';
    diagnostic.className = 'appearance-diagnostic';
    diagnostic.textContent = 'Checking active fonts…';

    preview.append(previewTitle, uiSample, monoSample, diagnostic);

    grid.append(themeField, fontField, monoField, scaleField);
    card.append(header, grid, preview);
    window.setTimeout(() => updateAppearanceDiagnostic(ui), 0);
    return card;
  }

  function createHelpPreferencesCard() {
    ensurePreferences();
    const card = document.createElement('article');
    card.className = 'card glass settings-preferences-card context-help-settings-card';
    const header = document.createElement('div');
    header.className = 'card-header';
    const heading = document.createElement('div');
    const title = document.createElement('h2');
    title.textContent = 'Contextual Help';
    const description = document.createElement('p');
    description.className = 'muted';
    description.textContent = 'Optional explanations beside generation and camera settings.';
    heading.append(title, description);
    header.appendChild(heading);
    const row = document.createElement('label');
    row.className = 'setting-toggle';
    const toggleRow = document.createElement('div');
    toggleRow.className = 'toggle-row';
    const input = document.createElement('input');
    input.id = 'ui-show-help-hints';
    input.type = 'checkbox';
    input.checked = state.settings.ui.show_help_hints !== false;
    input.addEventListener('change', () => {
      state.settings.ui.show_help_hints = input.checked;
      window.MorphorumHelp?.setEnabled(input.checked);
    });
    const copy = document.createElement('div');
    const name = document.createElement('strong');
    name.textContent = 'Show (?) help buttons';
    const detail = document.createElement('small');
    detail.textContent = 'Hover, focus or tap for explanations. Important error and disabled-control messages stay visible.';
    copy.append(name, detail);
    toggleRow.append(input, copy);
    row.appendChild(toggleRow);
    card.append(header, row);
    return card;
  }

  // P4.4.2: FFmpeg belongs to the host, not the browser. An unsaved choice
  // can be checked safely; only Save Settings changes the active resolver.
  function ensureFFmpegSettings() {
    state.settings ||= {};
    state.settings.tools ||= {};
    state.settings.tools.ffmpeg ||= {mode: 'auto', custom_path: ''};
    const config = state.settings.tools.ffmpeg;
    if (!['auto', 'custom', 'managed'].includes(config.mode)) config.mode = 'auto';
    config.custom_path = String(config.custom_path || '');
    return config;
  }

  function renderFFmpegStatus(info) {
    const status = qs('#ffmpeg-manager-status');
    const details = qs('#ffmpeg-manager-details');
    if (!status || !details) return;
    status.dataset.ready = info.available && info.probe_available ? 'yes' : 'no';
    status.textContent = info.message || 'FFmpeg detection completed.';
    const lines = [
      'Source: ' + (info.source || info.mode || 'unknown'),
      'FFmpeg: ' + (info.version || 'Not available'),
      'FFprobe: ' + (info.probe_version || 'Not available'),
      'FFmpeg executable: ' + (info.ffmpeg_path || 'Not found'),
      'FFprobe executable: ' + (info.ffprobe_path || 'Not found'),
    ];
    details.textContent = lines.join('\n');
    // Test results apply only to the unsaved selection until Save Settings.
  }

  async function checkFFmpegSettings({quiet = false} = {}) {
    const config = ensureFFmpegSettings();
    const selection = {mode: config.mode, custom_path: config.custom_path.trim()};
    const serial = (state.ffmpegRequestId || 0) + 1;
    state.ffmpegRequestId = serial;
    const button = qs('#ffmpeg-manager-check');
    const status = qs('#ffmpeg-manager-status');
    const details = qs('#ffmpeg-manager-details');
    if (button) {button.disabled = true;button.classList.add('busy');}
    if (status) status.textContent = 'Checking selected FFmpeg and FFprobe…';
    if (details) details.textContent = '';
    const operation = quiet ? null : window.MorphorumOperations?.begin(
      'ffmpeg-check','Checking FFmpeg tools',
      'Testing the selected executables on the Morphorum host…','settings');
    try {
      const info = await api('/api/tools/ffmpeg/check', {
        method: 'POST', body: JSON.stringify(selection),
      });
      if (serial !== state.ffmpegRequestId) return;
      renderFFmpegStatus(info);
      if (!quiet) window.MorphorumOperations?.finish('ffmpeg-check', operation, {
        tone: info.available && info.probe_available ? 'success' : 'warning',
        title: info.available && info.probe_available
          ? 'FFmpeg and FFprobe verified' : 'FFmpeg setup needs attention',
        message: info.message, view: 'settings',
      });
    } catch (error) {
      if (serial !== state.ffmpegRequestId) return;
      if (status) status.textContent = 'FFmpeg check failed: ' + error.message;
      if (!quiet) window.MorphorumOperations?.finish('ffmpeg-check', operation, {
        tone: 'error', title: 'FFmpeg check failed',
        message: error.message + ' Check the selected path and backend connection.',
        view: 'settings',
      });
    } finally {
      if (serial === state.ffmpegRequestId && button) {
        button.disabled = false; button.classList.remove('busy');
      }
    }
  }

  const FFMPEG_BUSY_STATES = new Set([
    'checking', 'downloading', 'verifying', 'extracting', 'installing',
  ]);
  function displayBytes(value) {
    const number = Number(value);
    if (!Number.isFinite(number) || number < 0) return '0 MB';
    return (number / (1024 * 1024)).toFixed(1) + ' MB';
  }
  function renderManagedFFmpeg(info) {
    const box = qs('#ffmpeg-manager-install-panel');
    if (!box) return;
    const job = info.job || null;
    const active = job && FFMPEG_BUSY_STATES.has(job.status);
    const install = qs('#ffmpeg-manager-install');
    const cancel = qs('#ffmpeg-manager-cancel');
    const remove = qs('#ffmpeg-manager-remove');
    const progress = qs('#ffmpeg-manager-install-progress');
    const label = qs('#ffmpeg-manager-install-status');
    const meta = qs('#ffmpeg-manager-install-meta');
    if (install) {
      install.disabled = !info.supported || active || state.ffmpegManagerActionBusy;
      install.textContent = info.installed ? 'Update / Reinstall managed FFmpeg' :
        info.repair_needed ? 'Repair managed FFmpeg' : 'Install managed FFmpeg';
    }
    if (cancel) {
      cancel.hidden = !active;
      cancel.disabled = !active || state.ffmpegManagerActionBusy;
    }
    if (remove) {
      remove.hidden = !info.installed && !info.repair_needed;
      remove.disabled = active || state.ffmpegManagerActionBusy;
    }
    if (progress) {
      progress.hidden = !active;
      progress.value = Math.max(0, Math.min(100, Number(job?.progress) || 0));
    }
    if (label) label.textContent = job
      ? (job.message || job.status) +
        (job.error ? ' ' + job.error : '') +
        (active && job.total_bytes
          ? ' (' + displayBytes(job.downloaded_bytes) + ' / ' +
            displayBytes(job.total_bytes) + ')' : '')
      : info.installed ? 'Managed FFmpeg installed.' :
        info.repair_needed ? 'Managed FFmpeg files are incomplete. Repair or remove the installation.' :
          info.message;
    if (meta) meta.textContent =
      'Package: ' + (info.asset_name || 'Unsupported architecture') +
      '\nInstalled location: ' + info.managed_path +
      '\nProvider: BtbN FFmpeg-Builds · GPL static builds';
    if (job) {
      const ops = window.MorphorumOperations;
      const key = 'ffmpeg-managed';
      if (active) {
        if (state.ffmpegManagerJobId !== job.id || !state.ffmpegManagerOperation) {
          if (state.ffmpegManagerOperation) ops?.retire(key);
          state.ffmpegManagerJobId = job.id;
          state.ffmpegManagerOperation = ops?.begin(key, 'Installing managed FFmpeg',
            'Fetching and verifying an upstream package…', 'settings');
        }
        ops?.update(key, state.ffmpegManagerOperation, {
          title: 'Managed FFmpeg: ' + job.status,
          message: label?.textContent || job.message,
          progress: Number(job.progress) || 0,
        });
      } else if (state.ffmpegManagerJobId !== job.id) {
        // Recover a completed job after browser reload without claiming to
        // have submitted it from this tab.
        state.ffmpegManagerJobId = job.id;
        if (job.status === 'installed' && ensureFFmpegSettings().mode === 'managed') {
          // A fast completion or browser reconnection still refreshes
          // video availability; no fictitious operation success is emitted.
          void checkFFmpegSettings({quiet: true});
          window.dispatchEvent(new CustomEvent('morphorum:settings-changed',
            {detail: state.settings}));
        }
      } else if (state.ffmpegManagerOperation) {
        ops?.finish(key, state.ffmpegManagerOperation, {
          tone: job.status === 'installed' ? 'success' :
            job.status === 'cancelled' ? 'warning' : 'error',
          title: job.status === 'installed'
            ? 'Managed FFmpeg installed'
            : job.status === 'cancelled'
              ? 'Managed FFmpeg installation cancelled' : 'Managed FFmpeg installation failed',
          message: label?.textContent || job.message, view: 'settings',
        });
        state.ffmpegManagerOperation = null;
        if (job.status === 'installed' && ensureFFmpegSettings().mode === 'managed') {
          void checkFFmpegSettings({quiet: true});
          window.dispatchEvent(new CustomEvent('morphorum:settings-changed',
            {detail: state.settings}));
        }
      }
    }
  }

  async function refreshManagedFFmpeg() {
    window.clearTimeout(state.ffmpegManagedTimer);
    state.ffmpegManagedTimer = null;
    const request = (state.ffmpegManagedRequest || 0) + 1;
    state.ffmpegManagedRequest = request;
    try {
      const info = await api('/api/tools/ffmpeg/managed');
      if (request !== state.ffmpegManagedRequest) return;
      window.MorphorumPollHealth?.recovered('ffmpeg-managed');
      renderManagedFFmpeg(info);
      if (info.job && FFMPEG_BUSY_STATES.has(info.job.status))
        state.ffmpegManagedTimer = window.setTimeout(refreshManagedFFmpeg, 900);
    } catch (error) {
      if (request !== state.ffmpegManagedRequest) return;
      const status = qs('#ffmpeg-manager-install-status');
      if (status) status.textContent =
        'Could not check managed FFmpeg installation. Check backend connectivity.';
      if (state.ffmpegManagerOperation) {
        window.MorphorumPollHealth?.failed('ffmpeg-managed', 'Managed FFmpeg', 'settings');
        state.ffmpegManagedTimer = window.setTimeout(refreshManagedFFmpeg, 5000);
      } else {
        // No known in-flight install: allow a manual retry on the next
        // Settings load rather than polling an offline host forever.
        window.MorphorumClientDiagnostics?.record('warning',
          'Could not inspect managed FFmpeg; check the backend connection.');
      }
    }
  }

  async function managedFFmpegAction(action) {
    if (state.ffmpegManagerActionBusy) return;
    if (action === 'remove') {
      const accepted = await window.MorphorumDialog.confirm({
        title: 'Remove Morphorum-managed FFmpeg?',
        message: 'Only the verified FFmpeg installation in this Morphorum folder is removed. ' +
          'Existing videos, projects and separately installed FFmpeg copies are kept.',
        variant: 'danger', confirmText: 'Remove managed FFmpeg', cancelText: 'Keep installed',
      });
      if (!accepted) return;
    }
    state.ffmpegManagerActionBusy = true;
    const key = 'ffmpeg-manager-action';
    const token = window.MorphorumOperations?.begin(key,
      action === 'install' ? 'Starting managed FFmpeg install' :
        action === 'remove' ? 'Removing managed FFmpeg' : 'Cancelling installation',
      'Contacting Morphorum backend…', 'settings');
    try {
      await api('/api/tools/ffmpeg/managed' +
        (action === 'install' ? '/install' : action === 'cancel' ? '/cancel' : ''),
        {method: action === 'remove' ? 'DELETE' : 'POST'});
      window.MorphorumOperations?.finish(key, token, {
        title: action === 'install' ? 'Managed FFmpeg download accepted'
          : action === 'cancel' ? 'Cancel requested' : 'Managed FFmpeg removed',
        message: action === 'install'
          ? 'Checking upstream release; progress appears below.'
          : action === 'cancel' ? 'The installer will stop safely at its next checkpoint.'
          : 'Managed FFmpeg binaries were removed. Existing renders and exports are unchanged.',
        view: 'settings',
      });
      if (action === 'remove' && ensureFFmpegSettings().mode === 'managed') {
        void checkFFmpegSettings({quiet: true});
        window.dispatchEvent(new CustomEvent('morphorum:settings-changed',
          {detail: state.settings}));
      }
    } catch (error) {
      window.MorphorumOperations?.finish(key, token, {
        tone: 'error',
        title: action === 'install' ? 'Could not start managed FFmpeg' :
          action === 'cancel' ? 'Could not cancel FFmpeg installation' :
            'Managed FFmpeg removal failed',
        message: error.message, view: 'settings',
      });
    } finally {
      state.ffmpegManagerActionBusy = false;
      void refreshManagedFFmpeg();
    }
  }

  function createFFmpegManagerCard() {
    const config = ensureFFmpegSettings();
    const card = document.createElement('article');
    card.className = 'card glass settings-preferences-card ffmpeg-manager-card';
    const header = document.createElement('div');
    header.className = 'card-header';
    const heading = document.createElement('div');
    const title = document.createElement('h2');
    title.textContent = 'FFmpeg Manager';
    const intro = document.createElement('p');
    intro.className = 'muted';
    intro.textContent = 'Select the host installation used for video export, hybrid video and audio conversion.';
    heading.append(title, intro); header.appendChild(heading);
    const grid = document.createElement('div');
    grid.className = 'field-grid settings-preference-grid';
    const modeField = document.createElement('label');
    const modeLabel = document.createElement('span');
    modeLabel.textContent = 'FFmpeg source';
    const mode = document.createElement('select');
    mode.id = 'ffmpeg-manager-mode';
    for (const [value, label] of [
      ['auto','Auto-detect from host PATH (or MORPHORUM_FFMPEG)'],
      ['custom','Custom installed executable'],
      ['managed','Morphorum-managed local FFmpeg'],
    ]) {
      const option = document.createElement('option');
      option.value = value; option.textContent = label; mode.appendChild(option);
    }
    mode.value = config.mode;
    modeField.append(modeLabel, mode);
    const pathField = document.createElement('label');
    pathField.id = 'ffmpeg-manager-path-field';
    const pathTitle = document.createElement('span');
    pathTitle.textContent = 'Custom FFmpeg executable path';
    const customPath = document.createElement('input');
    customPath.id = 'ffmpeg-manager-path';
    customPath.className = 'path-input';
    customPath.type = 'text';
    customPath.spellcheck = false;
    customPath.autocomplete = 'off';
    customPath.placeholder = navigator.userAgent.includes('Windows')
      ? 'D:\\Tools\\ffmpeg\\bin\\ffmpeg.exe' : '/usr/local/bin/ffmpeg';
    customPath.value = config.custom_path;
    pathField.append(pathTitle, customPath);
    const managedPanel = document.createElement('section');
    managedPanel.id = 'ffmpeg-manager-install-panel';
    managedPanel.className = 'ffmpeg-install-panel';
    const managedNote = document.createElement('div');
    managedNote.id = 'ffmpeg-manager-managed-note';
    managedNote.className = 'path-message';
    managedNote.textContent =
      'Optional: download a verified GPL static FFmpeg/FFprobe pair into ' +
      'tools/ffmpeg/current/bin. The download is started only by clicking Install.';
    const actions = document.createElement('div');
    actions.className = 'ffmpeg-install-actions';
    const install = makeButton('Install managed FFmpeg', 'primary-button compact busy-button');
    install.id = 'ffmpeg-manager-install';
    install.addEventListener('click', () => void managedFFmpegAction('install'));
    const cancel = makeButton('Cancel download', 'secondary-button compact');
    cancel.id = 'ffmpeg-manager-cancel';
    cancel.hidden = true;
    cancel.addEventListener('click', () => void managedFFmpegAction('cancel'));
    const remove = makeButton('Remove managed FFmpeg', 'secondary-button compact');
    remove.id = 'ffmpeg-manager-remove';
    remove.hidden = true;
    remove.addEventListener('click', () => void managedFFmpegAction('remove'));
    actions.append(install, cancel, remove);
    const installProgress = document.createElement('progress');
    installProgress.id = 'ffmpeg-manager-install-progress';
    installProgress.max = 100;
    installProgress.value = 0;
    installProgress.hidden = true;
    installProgress.setAttribute('aria-label', 'Managed FFmpeg installation progress');
    const installStatus = document.createElement('div');
    installStatus.id = 'ffmpeg-manager-install-status';
    installStatus.className = 'path-message';
    installStatus.setAttribute('role','status');
    installStatus.textContent = 'Checking local installation…';
    const installMeta = document.createElement('pre');
    installMeta.id = 'ffmpeg-manager-install-meta';
    installMeta.className = 'ffmpeg-manager-details';
    const provider = document.createElement('a');
    provider.href = 'https://github.com/BtbN/FFmpeg-Builds';
    provider.target = '_blank';
    provider.rel = 'noopener noreferrer';
    provider.textContent = 'Provider, sources and GPL license details';
    managedPanel.append(managedNote, actions, installProgress, installStatus,
      installMeta, provider);
    const status = document.createElement('p');
    status.id = 'ffmpeg-manager-status';
    status.className = 'path-message';
    status.setAttribute('role','status');
    status.textContent = 'Select Test FFmpeg to check this host.';
    const details = document.createElement('pre');
    details.id = 'ffmpeg-manager-details';
    details.className = 'ffmpeg-manager-details';
    const test = makeButton('Test FFmpeg / FFprobe', 'secondary-button compact busy-button');
    test.id = 'ffmpeg-manager-check';
    test.addEventListener('click', () => void checkFFmpegSettings());
    function syncMode() {
      config.mode = mode.value;
      pathField.hidden = config.mode !== 'custom';
      managedPanel.hidden = config.mode !== 'managed';
      status.textContent = 'Selection changed. Test this configuration, then Save Settings to activate it.';
      details.textContent = '';
      state.ffmpegRequestId = (state.ffmpegRequestId || 0) + 1;
      window.MorphorumOperations?.retire('ffmpeg-check');
      test.disabled = false; test.classList.remove('busy');
      markSettingsDirty();
    }
    mode.addEventListener('change', syncMode);
    customPath.addEventListener('input', () => {
      config.custom_path = customPath.value;
      status.textContent = 'Path edited. Test the executable, then Save Settings.';
      details.textContent = '';
      state.ffmpegRequestId = (state.ffmpegRequestId || 0) + 1;
      window.MorphorumOperations?.retire('ffmpeg-check');
      test.disabled = false; test.classList.remove('busy');
      markSettingsDirty();
    });
    pathField.hidden = config.mode !== 'custom';
    managedPanel.hidden = config.mode !== 'managed';
    grid.append(modeField, pathField);
    card.append(header, grid, managedPanel, status, details, test);
    return card;
  }

  function createManagedModelsCard() {
    const managed = ensureManagedModels();
    const card = document.createElement('article');
    card.className = 'card glass settings-preferences-card managed-settings-card';

    const header = document.createElement('div');
    header.className = 'card-header';
    const headingWrap = document.createElement('div');
    const heading = document.createElement('h2');
    heading.textContent = 'Managed Models';
    const sub = document.createElement('p');
    sub.className = 'muted';
    sub.textContent = 'Storage used by models downloaded and maintained by Morphorum.';
    headingWrap.append(heading, sub);
    header.appendChild(headingWrap);

    const body = document.createElement('div');
    body.className = 'path-section';

    const label = document.createElement('label');
    label.className = 'field-label';
    label.htmlFor = 'managed-zimage-path';
    label.textContent = 'Z-Image storage';

    const input = document.createElement('input');
    input.id = 'managed-zimage-path';
    input.className = 'path-input';
    input.type = 'text';
    input.value = managed.locations.zimage || '.\\ckpts\\z-image';
    input.placeholder = '.\\ckpts\\z-image';
    input.addEventListener('input', () => {
      managed.locations.zimage = input.value;
    });

    const help = document.createElement('div');
    help.className = 'path-message';
    help.textContent = 'Z-Image packages downloaded from Model Manager are stored here. Relative paths are resolved from the Morphorum install folder.';

    body.append(label, input, help);
    card.append(header, body);
    return card;
  }

  function createPreferencesCard() {
    ensurePreferences();
    const card = document.createElement('article');
    card.className = 'card glass settings-preferences-card';

    const header = document.createElement('div');
    header.className = 'card-header';
    const headingWrap = document.createElement('div');
    const heading = document.createElement('h2');
    heading.textContent = 'Generation Behavior';
    const sub = document.createElement('p');
    sub.className = 'muted';
    sub.textContent = 'Control browser previews and model memory behavior.';
    headingWrap.append(heading, sub);
    header.appendChild(headingWrap);

    const grid = document.createElement('div');
    grid.className = 'field-grid settings-preference-grid';

    const previewLabel = document.createElement('label');
    const previewTitle = document.createElement('span');
    previewTitle.textContent = 'Visible image previews';
    const previewInput = document.createElement('input');
    previewInput.type = 'number';
    previewInput.id = 'image-preview-limit';
    previewInput.min = '1';
    previewInput.max = '50';
    previewInput.step = '1';
    previewInput.value = String(state.settings.ui.image_preview_limit || 5);
    previewInput.addEventListener('input', () => {
      const value = Math.max(1, Math.min(50, Number(previewInput.value) || 5));
      state.settings.ui.image_preview_limit = value;
    });
    previewLabel.append(previewTitle, previewInput);

    const unloadLabel = document.createElement('label');
    unloadLabel.className = 'setting-toggle';
    const unloadTitle = document.createElement('span');
    unloadTitle.textContent = 'Model memory';
    const unloadRow = document.createElement('div');
    unloadRow.className = 'toggle-row';
    const unloadInput = document.createElement('input');
    unloadInput.type = 'checkbox';
    unloadInput.id = 'unload-after-generation';
    unloadInput.checked = Boolean(state.settings.performance.unload_after_generation);
    unloadInput.addEventListener('change', () => {
      state.settings.performance.unload_after_generation = unloadInput.checked;
    });
    const unloadCopy = document.createElement('div');
    const unloadStrong = document.createElement('strong');
    unloadStrong.textContent = 'Unload after generation';
    const unloadHelp = document.createElement('small');
    unloadHelp.textContent = 'Unload only after the full batch completes.';
    unloadCopy.append(unloadStrong, unloadHelp);
    unloadRow.append(unloadInput, unloadCopy);
    unloadLabel.append(unloadTitle, unloadRow);

    const tilingLabel = document.createElement('label');
    tilingLabel.className = 'setting-toggle';
    const tilingTitle = document.createElement('span');
    tilingTitle.textContent = 'SDXL high-resolution memory';
    const tilingRow = document.createElement('div');
    tilingRow.className = 'toggle-row';
    const tilingInput = document.createElement('input');
    tilingInput.type = 'checkbox';
    tilingInput.id = 'sdxl-vae-tiling';
    tilingInput.checked = Boolean(state.settings.performance.sdxl_vae_tiling);
    tilingInput.addEventListener('change', () => {
      state.settings.performance.sdxl_vae_tiling = tilingInput.checked;
    });
    const tilingCopy = document.createElement('div');
    const tilingStrong = document.createElement('strong');
    tilingStrong.textContent = 'VAE tiling (optional)';
    const tilingHelp = document.createElement('small');
    tilingHelp.textContent =
      'Split SDXL VAE processing into smaller tiles to reduce memory pressure at larger sizes. Turn on only if needed, then unload and reload the model.';
    tilingCopy.append(tilingStrong, tilingHelp);
    tilingRow.append(tilingInput, tilingCopy);
    tilingLabel.append(tilingTitle, tilingRow);

    grid.append(previewLabel, unloadLabel, tilingLabel);
    card.append(header, grid);
    return card;
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
      markSettingsDirty();
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
      markSettingsDirty();
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

  function createCivitaiSettingsCard() {
    state.settings.civitai ||= {};
    const cfg = state.settings.civitai;
    const card = document.createElement('article');
    card.className = 'card glass settings-preferences-card civitai-settings-card';
    const heading = document.createElement('div');
    heading.className = 'civitai-settings-heading';
    const title = document.createElement('h2');
    title.textContent = 'Civitai Hub';
    const description = document.createElement('p');
    description.className = 'muted';
    description.textContent = 'Optional online model discovery. Local models and LoRA inspection remain available when disabled.';
    heading.append(title, description);
    card.append(heading);

    const toggles = document.createElement('div');
    toggles.className = 'civitai-settings-options';
    const toggle = (label, key, fallback = false, hint = '') => {
      const wrap = document.createElement('label');
      wrap.className = 'civitai-settings-toggle';
      const copy = document.createElement('span');
      copy.className = 'civitai-settings-toggle-copy';
      const strong = document.createElement('strong');
      strong.textContent = label;
      copy.append(strong);
      if (hint) {
        const small = document.createElement('small');
        small.className = 'muted';
        small.textContent = hint;
        copy.append(small);
      }
      const input = document.createElement('input');
      input.type = 'checkbox';
      input.checked = cfg[key] === undefined ? fallback : cfg[key] === true;
      input.addEventListener('change', () => { cfg[key] = input.checked; markSettingsDirty(); });
      wrap.append(copy, input);
      toggles.append(wrap);
    };
    toggle('Enable Civitai Hub', 'enabled', false, 'Enable online discovery and Civitai connectivity.');
    toggle('Allow mature previews', 'allow_mature');
    toggle('Load model thumbnails', 'load_previews', true);
    toggle('Check for updates automatically', 'auto_check_updates', false, 'Reserved for future update scanning.');
    card.append(toggles);

    const selects = document.createElement('div');
    selects.className = 'civitai-settings-selects';
    const selectField = (label, key, values, fallback) => {
      const field = document.createElement('label');
      field.className = 'civitai-settings-field';
      const caption = document.createElement('span');
      caption.textContent = label;
      const select = document.createElement('select');
      for (const [value, text] of values) {
        const option = document.createElement('option');
        option.value = String(value);
        option.textContent = text;
        select.append(option);
      }
      select.value = String(cfg[key] ?? fallback);
      select.addEventListener('change', () => {
        cfg[key] = key === 'concurrent_downloads' ? Number(select.value) : select.value;
        markSettingsDirty();
      });
      field.append(caption, select);
      selects.append(field);
    };
    selectField('Browsing layout', 'layout', [['grid', 'Thumbnail grid'], ['list', 'Compact list']], 'grid');
    selectField('Concurrent downloads (future feature)', 'concurrent_downloads', [[1,'1'],[2,'2'],[3,'3']], 1);
    card.append(selects);

    const connection = document.createElement('section');
    connection.className = 'civitai-settings-connection';
    const connectionTitle = document.createElement('h3');
    connectionTitle.textContent = 'Connection';
    const notice = document.createElement('p');
    notice.className = 'muted';
    notice.textContent = 'Optional API token: configure CIVITAI_API_TOKEN on the Morphorum host. Save settings before testing.';
    const test = document.createElement('button');
    test.type = 'button';
    test.className = 'secondary-button busy-button civitai-test-button';
    const spinner = document.createElement('span');
    spinner.className = 'spinner';
    spinner.setAttribute('aria-hidden', 'true');
    const testLabel = document.createElement('span');
    testLabel.textContent = 'Test Connection';
    test.append(spinner, testLabel);
    const status = document.createElement('span');
    status.className = 'civitai-settings-sr-only';
    status.setAttribute('role', 'status');
    status.setAttribute('aria-live', 'polite');
    test.addEventListener('click', async () => {
      test.disabled = true;
      test.classList.add('busy');
      testLabel.textContent = 'Testing connection…';
      status.textContent = 'Testing Civitai connection';
      try {
        const result = await api('/api/civitai/test-connection', {method:'POST', body:'{}'});
        const summary = result.message + (result.status ? ' HTTP ' + result.status : '') +
          (result.authenticated ? ' (token configured)' : ' (public access)');
        status.textContent = summary;
        toast(result.ok ? 'Civitai connected' : 'Civitai connection failed', summary, result.ok ? 'success' : 'warning');
      } catch (error) {
        status.textContent = error.message;
        toast('Civitai test failed', error.message, 'error');
      } finally {
        test.disabled = false;
        test.classList.remove('busy');
        testLabel.textContent = 'Test Connection';
      }
    });
    connection.append(connectionTitle, notice, test, status);
    card.append(connection);
    return card;
  }

  function renderSettings() {
    const container = qs('#model-path-cards');
    const loader = qs('#settings-loading');
    if (!container || !state.settings) return;

    state.ffmpegRequestId = (state.ffmpegRequestId || 0) + 1;
    window.MorphorumOperations?.retire('ffmpeg-check');
    container.replaceChildren();
    const tabs = document.createElement('nav');
    tabs.id = 'settings-internal-tabs';
    tabs.className = 'settings-internal-tabs';
    tabs.setAttribute('aria-label', 'Settings groups');
    const panes = {};
    for (const [name,label] of [['appearance','Appearance'],['generation','Generation'],['paths','Model Paths'],['storage','Storage'],['civitai','Civitai Hub']]) {
      const button = document.createElement('button');
      button.type = 'button';
      button.dataset.settingsTab = name;
      button.textContent = label;
      button.addEventListener('click', () => selectSettingsTab(name));
      tabs.appendChild(button);
      const pane = document.createElement('section');
      pane.className = 'settings-pane';
      pane.dataset.settingsPane = name;
      panes[name] = pane;
    }
    container.appendChild(tabs);
    for (const pane of Object.values(panes)) container.appendChild(pane);
    panes.appearance.appendChild(createAppearanceCard());
    panes.appearance.appendChild(createHelpPreferencesCard());
    panes.generation.appendChild(createPreferencesCard());
    panes.storage.appendChild(createManagedModelsCard());
    panes.storage.appendChild(createFFmpegManagerCard());
    panes.civitai.appendChild(createCivitaiSettingsCard());
    for (const [family, fallbackLabel, source, loraSource, supportsLoras] of FAMILY_DEFS) {
      if (source === 'managed' && !(supportsLoras && loraSource === 'external')) continue;
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
      const modelCount = source === 'external' ? familyData.checkpoints.length : 0;
      const loraCount = supportsLoras && loraSource === 'external' ? familyData.loras.length : 0;
      count.textContent = `${modelCount} model path${modelCount === 1 ? '' : 's'} · ${loraCount} LoRA path${loraCount === 1 ? '' : 's'}`;
      header.append(headingWrap, count);
      card.appendChild(header);

      if (source === 'external') {
        card.appendChild(createPathSection(family, 'checkpoints', 'Model / checkpoint directories'));
      }
      if (supportsLoras && loraSource === 'external') {
        card.appendChild(createPathSection(family, 'loras', 'LoRA directories'));
      }
      panes.paths.appendChild(card);
    }

    selectSettingsTab(state.settingsTab, { persist: false });
    renderSettingsDirtyState();
    loader.hidden = true;
    container.hidden = false;
    void refreshManagedFFmpeg();
  }

  async function loadSettings({ announce = false } = {}) {
    if (state.settingsRequestBusy) return;
    if (announce && state.settingsDirty) {
      const allowed = await window.MorphorumDialog.confirm({
        title:'Discard unsaved settings?',
        message:'Reloading from the server will discard edits to model paths and preferences that you have not saved.',
        variant:'danger', confirmText:'Discard & Reload', cancelText:'Keep Editing'
      });
      if (!allowed) return;
    }
    const button = qs('#load-settings');
    state.settingsRequestBusy = true;
    setBusy(button, true);
    if (announce) qs('#save-settings').disabled = true;
    const operation = announce
      ? window.MorphorumOperations?.begin('settings', 'Reloading settings',
        'Reading configuration from the Morphorum host…', 'settings') : null;
    try {
      const payload = await api('/api/settings');
      state.settings = payload.settings || {};
      if (Array.isArray(payload.model_families) && payload.model_families.length) {
        FAMILY_DEFS = payload.model_families.map(item => [
          item.id,
          item.label || item.id,
          item.source || 'external',
          item.lora_source || 'external',
          Boolean(item.supports_loras),
        ]);
      }
      ingestValidation(payload.validation || []);
      ensurePreferences();
      applyAppearance(state.settings.ui);
      window.MorphorumHelp?.setEnabled(state.settings.ui.show_help_hints);
      renderSettings();
      window.MorphorumCivitai?.settingsChanged?.(state.settings.civitai || {});
      setSettingsClean();
      void checkFFmpegSettings({quiet: true});
      window.dispatchEvent(new CustomEvent('morphorum:settings-changed', { detail: state.settings }));
      if (announce) {
        window.MorphorumOperations?.finish('settings', operation, {
          title: 'Settings reloaded', message: 'Server configuration loaded successfully.',
          view: 'settings' });
        toast('Settings loaded', 'Configuration reloaded from the Morphorum server.', 'success');
      }
    } catch (error) {
      if (announce) window.MorphorumOperations?.finish('settings', operation, {
        tone: 'error', title: 'Settings reload failed', message: error.message,
        view: 'settings' });
      toast('Could not load settings', error.message, 'error', 7000);
      qs('#settings-loading').innerHTML = `<strong>Settings failed to load.</strong><span>${escapeHtml(error.message)}</span>`;
    } finally {
      state.settingsRequestBusy = false;
      setBusy(button, false);
      if (announce) qs('#save-settings').disabled = false;
    }
  }

  function modelSettingsPayload() {
    const models = {};
    for (const [family, , familySource, loraSource, supportsLoras] of FAMILY_DEFS) {
      const source = ensureFamily(family);
      const familyPayload = {};
      if (familySource === 'external') {
        familyPayload.checkpoints = (source.checkpoints || []).map(value => String(value).trim()).filter(Boolean);
      }
      if (supportsLoras && loraSource === 'external') {
        familyPayload.loras = (source.loras || []).map(value => String(value).trim()).filter(Boolean);
      }
      if (Object.keys(familyPayload).length) models[family] = familyPayload;
    }
    ensurePreferences();
    const managed = ensureManagedModels();
    return {
      models,
      tools: {ffmpeg: {
        mode: ensureFFmpegSettings().mode,
        custom_path: ensureFFmpegSettings().custom_path.trim(),
      }},
      managed_models: {
        locations: {
          zimage: String(managed.locations.zimage || '.\\ckpts\\z-image').trim() || '.\\ckpts\\z-image',
        },
      },
      ui: {
        theme: state.settings.ui.theme || 'midnight-glass',
        font_style: state.settings.ui.font_style || 'modern',
        mono_font_style: state.settings.ui.mono_font_style || 'modern-mono',
        ui_scale: state.settings.ui.ui_scale || 'compact',
        show_help_hints: state.settings.ui.show_help_hints !== false,
        image_preview_limit: Math.max(1, Math.min(50, Number(state.settings.ui.image_preview_limit) || 5)),
      },
      civitai: state.settings.civitai || { enabled: false },
      performance: {
        unload_after_generation: Boolean(state.settings.performance.unload_after_generation),
        sdxl_vae_tiling: Boolean(state.settings.performance.sdxl_vae_tiling),
      },
    };
  }

  async function saveSettings() {
    if (state.settingsRequestBusy) return;
    const button = qs('#save-settings');
    state.settingsRequestBusy = true;
    setBusy(button, true);
    qs('#load-settings').disabled = true;
    const operation = window.MorphorumOperations?.begin('settings', 'Saving settings',
      'Validating and saving host configuration…', 'settings');
    try {
      const payload = await api('/api/settings', {
        method: 'PUT',
        body: JSON.stringify(modelSettingsPayload()),
      });
      state.settings = payload.settings || state.settings;
      ingestValidation(payload.validation || []);
      ensurePreferences();
      applyAppearance(state.settings.ui);
      window.MorphorumHelp?.setEnabled(state.settings.ui.show_help_hints);
      renderSettings();
      setSettingsClean();
      void checkFFmpegSettings({quiet: true});
      window.dispatchEvent(new CustomEvent('morphorum:settings-changed', { detail: state.settings }));
      const warnings = (payload.validation || []).filter(item => !(item.exists && item.is_directory && item.readable));
      if (warnings.length) {
        const message = `${warnings.length} configured path${warnings.length === 1 ? '' : 's'} need attention. Check the path status in Settings.`;
        window.MorphorumOperations?.finish('settings', operation, {
          tone: 'warning', title: 'Settings saved with path warnings',
          message, view: 'settings' });
        toast('Settings saved', message, 'warning', 6000);
      } else {
        window.MorphorumOperations?.finish('settings', operation, {
          title: 'Settings saved', message: 'Model and LoRA locations saved.',
          view: 'settings' });
        toast('Settings saved', 'Model and LoRA locations were saved successfully.', 'success');
      }
    } catch (error) {
      window.MorphorumOperations?.finish('settings', operation, {
        tone: 'error', title: 'Settings save failed', message: error.message,
        view: 'settings' });
      toast('Settings save failed', error.message, 'error', 7000);
    } finally {
      state.settingsRequestBusy = false;
      setBusy(button, false);
      qs('#load-settings').disabled = false;
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

  function filteredConsoleEvents(events = state.events) {
    const levels = checkedValues('#level-filters');
    const categories = checkedValues('#category-filters');
    const search = (qs('#console-search')?.value || '').trim().toLowerCase();
    return (events || []).filter(event => levels.has(event.level) && categories.has(event.category) &&
      (!search || [event.message,event.category,event.level].some(value => String(value || '').toLowerCase().includes(search))));
  }

  function consoleEventTime(event) {
    const date = new Date(event.timestamp);
    return Number.isNaN(date.getTime())
      ? '--:--:--'
      : date.toLocaleTimeString([], {
          hour12: false,
          hour: '2-digit',
          minute: '2-digit',
          second: '2-digit',
        });
  }

  function consoleEventText(event) {
    const time = consoleEventTime(event);
    const level = String(event.level || 'info').toUpperCase().padEnd(7, ' ');
    const category = String(event.category || 'runtime').padEnd(10, ' ');
    const message = String(event.message || '');
    return `${time}  ${level}  ${category}  ${message}`;
  }

  async function writeClipboardText(text) {
    return window.MorphorumClipboard.writeText(text);
  }

  async function copyConsoleEvents(events, title) {
    if (!events.length) {
      toast('Nothing to copy', 'There are no console lines available for this action.', 'warning');
      return;
    }

    const text = events.map(consoleEventText).join('\n');
    await writeClipboardText(text);
    toast(
      title,
      `Copied ${events.length} console line${events.length === 1 ? '' : 's'} to the clipboard.`,
      'success'
    );
  }

  async function copyConsoleView() {
    try {
      await copyConsoleEvents(filteredConsoleEvents(), 'Console view copied');
    } catch (error) {
      toast('Clipboard copy failed', error.message, 'error', 6500);
    }
  }

  async function copyConsoleBuffer() {
    const button = qs('#copy-console-buffer');
    setBusy(button, true);
    try {
      const payload = await api('/api/console?limit=1500');
      await copyConsoleEvents(payload.events || [], 'Console buffer copied');
    } catch (error) {
      toast('Clipboard copy failed', error.message, 'error', 6500);
    } finally {
      setBusy(button, false);
    }
  }

  function renderConsole() {
    const windowEl = qs('#console-window');
    if (!windowEl) return;
    const filtered = filteredConsoleEvents();
    const count = qs('#console-count');
    if (count) count.textContent = filtered.length + ' matching messages';

    if (!filtered.length) {
      windowEl.innerHTML = '<div class="console-empty">No messages match the current filters.</div>';
      return;
    }

    windowEl.innerHTML = filtered.map(event => {
      const time = consoleEventTime(event);
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

  // Browser-side diagnostics appear in the normal Console, without sending
  // filesystem paths, request URLs, job payloads or credentials to the server.
  window.MorphorumClientDiagnostics = {
    record(level, message) {
      addConsoleEvent({id: 0, origin: 'browser', timestamp: new Date().toISOString(),
        level: ['info', 'warning', 'error'].includes(level) ? level : 'info',
        category: 'runtime', message: String(message).slice(0, 300)});
    },
  };

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
      const browserEvents = state.events.filter(event => event.origin === 'browser');
      state.events = [...(initial.events || []), ...browserEvents].slice(-1200);
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
    const accepted = await window.MorphorumDialog.confirm({
      title: 'Clear server console buffer?',
      message: 'This deletes the current server-side log buffer for every connected browser. Local filtering is unaffected.',
      variant: 'danger', confirmText: 'Clear Server Buffer', cancelText: 'Keep Buffer',
    });
    if (!accepted) return;
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

  function clampPercent(value) {
    const number = Number(value);
    if (!Number.isFinite(number)) return 0;
    return Math.max(0, Math.min(100, number));
  }

  function formatGiB(bytes) {
    const value = Number(bytes);
    if (!Number.isFinite(value)) return '--';
    return (value / (1024 ** 3)).toFixed(value >= 10 * 1024 ** 3 ? 1 : 2);
  }

  function setTelemetryGauge(fillSelector, valueSelector, percent, label) {
    const fill = qs(fillSelector);
    const value = qs(valueSelector);
    if (fill) fill.style.width = `${clampPercent(percent)}%`;
    if (value) value.textContent = label;
  }

  async function loadTelemetry() {
    try {
      const data = await api('/api/system/telemetry');
      setTelemetryGauge('#telemetry-cpu-fill', '#telemetry-cpu-value', data.cpu_percent, `${Math.round(clampPercent(data.cpu_percent))}%`);

      const ram = data.ram || {};
      const compact = window.matchMedia('(max-width: 640px)').matches;
      const compactMemory = bytes => {
        const n = Number(bytes) / (1024 ** 3);
        return Number.isFinite(n) ? (n >= 10 ? Math.round(n) : n.toFixed(1)) + ' GB' : '--';
      };
      setTelemetryGauge(
        '#telemetry-ram-fill',
        '#telemetry-ram-value',
        ram.free_percent,
        compact ? compactMemory(ram.available_bytes) : `${formatGiB(ram.available_bytes)} / ${formatGiB(ram.total_bytes)} GiB`
      );

      const gpuItems = qsa('.gpu-telemetry');
      const gpu = data.gpu?.devices?.[0];
      gpuItems.forEach(item => { item.hidden = !gpu; });
      if (gpu) {
        setTelemetryGauge(
          '#telemetry-gpu-fill',
          '#telemetry-gpu-value',
          gpu.utilization_percent,
          `${Math.round(clampPercent(gpu.utilization_percent))}%`
        );
        const totalBytes = Number(gpu.memory_total_mib) * 1024 ** 2;
        const freeBytes = Number(gpu.memory_free_mib) * 1024 ** 2;
        setTelemetryGauge(
          '#telemetry-vram-fill',
          '#telemetry-vram-value',
          gpu.memory_free_percent,
          compact ? compactMemory(freeBytes) : `${formatGiB(freeBytes)} / ${formatGiB(totalBytes)} GiB`
        );
        const strip = qs('#telemetry-strip');
        if (strip) strip.title = `${gpu.name} · ${gpu.temperature_c}°C`;
      }
      return true;
    } catch (_) {
      return false;
    }
  }

  async function telemetryLoop() {
    const ok = await loadTelemetry();
    if (!ok) {
      // Telemetry can fail independently; only mark host offline if /health
      // also fails. A failed optional GPU probe is not a render failure.
      await loadHealth();
    }
    window.clearTimeout(state.telemetryTimer);
    state.telemetryTimer = window.setTimeout(telemetryLoop, ok ? 2500 : 6000);
  }

  function compactRuntimeBranch(branch) {
    return branch.replace(/^(feature|fix|chore|checkpoint)\//, '');
  }

  async function loadHealth() {
    const dot = qs('#runtime-dot');
    const pill = qs('#runtime-pill');
    const version = qs('#runtime-version');
    const branchLabel = qs('#runtime-branch');
    const shortBranchLabel = qs('#runtime-branch-short');
    const versionFull = qs('#runtime-version-full');
    const branchFull = qs('#runtime-branch-full');
    const commitFull = qs('#runtime-commit');
    const repoLink = qs('#runtime-repository-link');
    const branchLink = qs('#runtime-branch-link');
    const commitLink = qs('#runtime-commit-link');
    const repoUrl = 'https://github.com/merberg-ai/Morphorum';
    if (repoLink) repoLink.href = repoUrl;
    try {
      const health = await api('/api/health');
      const buildVersion = String(health.version || 'unknown');
      const branch = String(health.git_branch || 'Unknown branch');
      const fullCommit = String(health.git_commit_full || health.git_commit || '');
      const commit = fullCommit.slice(0, 12);
      const validBranch = branch && !['Unknown branch', 'HEAD', 'detached'].includes(branch)
        && !/[?#\\]/.test(branch) && !/[.]{2}/.test(branch);
      const validCommit = /^[0-9a-f]{40}$/i.test(fullCommit);
      if (branchLink) {
        branchLink.hidden = !validBranch;
        if (validBranch) branchLink.href = repoUrl + '/tree/' +
          branch.split('/').map(encodeURIComponent).join('/');
        else branchLink.removeAttribute('href');
      }
      if (commitLink) {
        commitLink.hidden = !validCommit;
        if (validCommit) commitLink.href = repoUrl + '/commit/' + fullCommit;
        else commitLink.removeAttribute('href');
      }
      const displayVersion = buildVersion.startsWith('v') ? buildVersion : `v${buildVersion}`;
      dot?.classList.add('ok');
      dot?.classList.remove('bad');
      if (version) version.textContent = displayVersion;
      if (branchLabel) branchLabel.textContent = branch;
      if (shortBranchLabel) shortBranchLabel.textContent = compactRuntimeBranch(branch);
      if (versionFull) versionFull.textContent = displayVersion;
      if (branchFull) branchFull.textContent = branch;
      if (commitFull) commitFull.textContent = commit;
      if (pill) pill.title = `Morphorum ${displayVersion} · ${branch} @ ${commit} · Tap for details`;
      return true;
    } catch (error) {
      dot?.classList.add('bad');
      dot?.classList.remove('ok');
      if (version) version.textContent = 'Offline';
      if (branchLabel) branchLabel.textContent = 'Server unavailable';
      if (shortBranchLabel) shortBranchLabel.textContent = 'Unavailable';
      if (versionFull) versionFull.textContent = 'Unavailable';
      if (branchFull) branchFull.textContent = 'Unavailable';
      if (commitFull) commitFull.textContent = 'Unavailable';
      if (pill) pill.title = 'Morphorum server unavailable';
      for (const link of [branchLink, commitLink]) {
        if (link) { link.hidden = true; link.removeAttribute('href'); }
      }
      return false;
    }
  }

  function syncMobileViewport() {
    const mobile = window.matchMedia('(max-width: 640px)').matches;
    const viewport = window.visualViewport;
    if (!mobile || !viewport) {
      document.documentElement.style.setProperty('--mobile-viewport-inset', '0px');
      document.body.classList.remove('mobile-keyboard-open');
      return;
    }
    const obstructed = Math.max(0, window.innerHeight - viewport.height - viewport.offsetTop);
    const keyboard = obstructed > 170 && document.activeElement?.matches?.('input,textarea,[contenteditable="true"]');
    document.body.classList.toggle('mobile-keyboard-open', Boolean(keyboard));
    document.documentElement.style.setProperty('--mobile-viewport-inset',
      (keyboard ? 0 : Math.min(110, Math.round(obstructed))) + 'px');
  }

  function updateModelSetupBanner(models, loaded = true) {
    const banner = qs('#model-setup-banner');
    if (!banner) return;
    const usable = Array.isArray(models) && models.some(model =>
      model.kind === 'checkpoints' && model.id);
    banner.hidden = !loaded || usable;
  }

  function openModelSetupHelp() {
    const dialog = qs('#model-setup-help');
    if (!dialog) return;
    if (typeof dialog.showModal === 'function' && !dialog.open) dialog.showModal();
    else if (typeof dialog.showModal !== 'function') {
      toast('Help is unavailable', 'Open Models or Settings to configure model paths.', 'warning');
    }
  }

  function bindModelSetupHelp() {
    window.addEventListener('morphorum:models-updated', event => {
      updateModelSetupBanner(event.detail?.models, event.detail?.loaded === true);
    });
    qs('#model-setup-help-open')?.addEventListener('click', openModelSetupHelp);
    qs('#model-setup-help-close')?.addEventListener('click', () => qs('#model-setup-help')?.close());
    for (const [id, view] of [
      ['model-setup-help-settings', 'settings'],
      ['model-setup-help-models', 'models'],
    ]) {
      qs('#' + id)?.addEventListener('click', () => {
        qs('#model-setup-help')?.close();
        switchView(view);
      });
    }
    qs('#model-setup-help')?.addEventListener('click', event => {
      if (event.target.id === 'model-setup-help') event.target.close();
    });
  }

  function bindUi() {
    bindModelSetupHelp();
    qsa('.nav-button[data-view]').forEach(button => button.addEventListener('click', () => {
      switchView(button.dataset.view);
      if (button.dataset.view === 'animation') qs('#animation-tab-motion')?.click();
    }));
    qs('#project-nav-toggle')?.addEventListener('click', () => {
      const menu = qs('#project-nav-submenu');
      if (!menu) return;
      menu.hidden = !menu.hidden;
      qs('#project-nav-toggle').setAttribute('aria-expanded', String(!menu.hidden));
    });
    qsa('.main-nav [data-project-nav]').forEach(button => button.addEventListener('click', () => {
      switchView('animation');
      qs('#animation-tab-' + button.dataset.projectNav)?.click();
      qs('#project-nav-submenu').hidden = false;
      qs('#project-nav-toggle').setAttribute('aria-expanded', 'true');
    }));
    qsa('#motion-lab-sidebar [data-motion-nav]').forEach(button => button.addEventListener('click', () => {
      switchView('animation');
      qs('#animation-tab-' + button.dataset.motionNav)?.click();
    }));
    const moreToggle = qs('#nav-more-toggle');
    moreToggle?.addEventListener('click', () => {
      const menu = qs('#nav-more-menu');
      if (!menu) return;
      menu.hidden = !menu.hidden;
      moreToggle.setAttribute('aria-expanded', String(!menu.hidden));
    });
    qsa('#nav-more-menu [data-more-view]').forEach(button => button.addEventListener('click', () => switchView(button.dataset.moreView)));
    document.addEventListener('click', event => {
      if (!event.target.closest('.main-nav')) closeNavMore();
    });
    qs('#global-job-status')?.addEventListener('click', openActiveJob);
    window.addEventListener('morphorum:job-status', event => {
      const job = event.detail || {};
      if (!['image','animation'].includes(job.type)) return;
      state.jobs[job.type] = job.id ? { ...job, updated: Date.now() } : null;
      updateGlobalJobStatus();
    });
    qsa('[data-jump]').forEach(button => button.addEventListener('click', () => switchView(button.dataset.jump)));
    qs('#load-settings')?.addEventListener('click', () => loadSettings({ announce: true }));
    const settingsArea = qs('#model-path-cards');
    settingsArea?.addEventListener('input', markSettingsDirty);
    settingsArea?.addEventListener('change', markSettingsDirty);
    try { state.settingsTab = localStorage.getItem('morphorum.settings.tab.v1') || 'appearance'; } catch (_) {}
    qs('#save-settings')?.addEventListener('click', saveSettings);
    qsa('#level-filters input, #category-filters input').forEach(input => input.addEventListener('change', renderConsole));
    qs('#console-search')?.addEventListener('input', renderConsole);
    qsa('[data-console-preset]').forEach(button => button.addEventListener('click', () => {
      const type = button.dataset.consolePreset;
      qsa('#level-filters input').forEach(input => {
        input.checked = type === 'all' || (type === 'errors' ? input.value === 'error' :
          ['warning','error'].includes(input.value));
      });
      qsa('#category-filters input').forEach(input => { input.checked = true; });
      renderConsole();
    }));
    qs('#console-jump-latest')?.addEventListener('click', () => {
      const element = qs('#console-window');
      if (element) element.scrollTop = element.scrollHeight;
      const auto = qs('#auto-scroll');
      if (auto) auto.checked = true;
    });
    qs('#console-window')?.addEventListener('scroll', event => {
      const el = event.currentTarget;
      const auto = qs('#auto-scroll');
      if (auto?.checked && el.scrollHeight - el.scrollTop - el.clientHeight > 100) auto.checked = false;
    });
    qs('#auto-scroll')?.addEventListener('change', renderConsole);
    qs('#copy-console-view')?.addEventListener('click', copyConsoleView);
    qs('#copy-console-buffer')?.addEventListener('click', copyConsoleBuffer);
    qs('#clear-console-view')?.addEventListener('click', () => {
      state.events = [];
      renderConsole();
      toast('Console view cleared', 'The server buffer was left intact.', 'info');
    });
    qs('#clear-console-server')?.addEventListener('click', clearServerConsole);

    window.visualViewport?.addEventListener('resize', syncMobileViewport);
    window.visualViewport?.addEventListener('scroll', syncMobileViewport);
    window.addEventListener('resize', syncMobileViewport);
    document.addEventListener('focusin', syncMobileViewport);
    document.addEventListener('focusout', () => window.setTimeout(syncMobileViewport, 120));
    syncMobileViewport();
    const requested = location.hash.replace('#', '');
    if (['image', 'animation', 'models', 'loras', 'civitai', 'settings', 'console'].includes(requested)) switchView(requested);
  }

  async function start() {
    try {
      applyAppearance({
        theme: localStorage.getItem('morphorum.ui.theme') || 'midnight-glass',
        font_style: localStorage.getItem('morphorum.ui.fontStyle') || 'modern',
        mono_font_style: localStorage.getItem('morphorum.ui.monoStyle') || 'modern-mono',
        ui_scale: localStorage.getItem('morphorum.ui.uiScale') || 'compact',
      });
    } catch (_) {
      applyAppearance({});
    }
    bindUi();
    await Promise.allSettled([loadHealth(), loadSettings(), connectConsole(), telemetryLoop()]);
  }

  window.MorphorumToast = toast;
  window.addEventListener('DOMContentLoaded', start);
})();
