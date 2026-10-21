(() => {
  'use strict';

  let FAMILY_LABELS = {
    sdxl: 'SDXL',
    flux: 'Flux',
    zimage: 'Z-Image',
  };

  const state = {
    models: [],
    families: [],
    managedModels: [],
    managedPollTimer: null,
    downloadOperations: new Map(),
    downloadPendingChecks: new Map(),
    scanning: false,
    bulkSelected: new Set(),
    bulkBusy: false,
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
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || `${response.status} ${response.statusText}`);
    return payload;
  }

  async function loadFamilies() {
    const payload = await api('/api/models/families');
    state.families = Array.isArray(payload.families) ? payload.families : [];
    if (state.families.length) {
      FAMILY_LABELS = Object.fromEntries(state.families.map(item => [item.id, item.label || item.id]));
    }

    const filter = qs('#model-family-filter');
    if (filter) {
      const previous = filter.value;
      filter.replaceChildren();
      const all = document.createElement('option');
      all.value = '';
      all.textContent = 'All families';
      filter.appendChild(all);
      for (const family of state.families) {
        const option = document.createElement('option');
        option.value = family.id;
        option.textContent = family.label || family.id;
        filter.appendChild(option);
      }
      if ([...filter.options].some(option => option.value === previous)) filter.value = previous;
    }
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

  function managedStatusLabel(model) {
    if (model.status === 'checking') return 'Checking…';
    if (model.status === 'downloading') return 'Downloading';
    if (model.status === 'installed') return 'Installed';
    if (model.status === 'failed') return 'Download failed';
    if (model.status === 'interrupted') return 'Interrupted · resumable';
    if (model.status === 'partial') return 'Incomplete package';
    return 'Not installed';
  }

  function managedModelCard(model) {
    const card = document.createElement('div');
    card.className = 'managed-model-row';

    const info = document.createElement('div');
    info.className = 'managed-model-info';
    const titleRow = document.createElement('div');
    titleRow.className = 'managed-model-title-row';
    const title = document.createElement('strong');
    title.textContent = model.name;
    const status = document.createElement('span');
    status.className = `managed-status ${model.status || 'not_installed'}`;
    status.textContent = managedStatusLabel(model);
    titleRow.append(title, status);

    const description = document.createElement('p');
    description.className = 'muted managed-description';
    description.textContent = model.description || '';

    const meta = document.createElement('div');
    meta.className = 'managed-model-meta';
    meta.textContent = `${model.repo_id} · ${model.license || 'Model license'} · ${formatBytes(model.expected_bytes || model.advertised_size_bytes)}`;

    const destination = document.createElement('div');
    destination.className = 'managed-model-path';
    destination.textContent = model.destination || '';
    destination.title = model.destination || '';

    info.append(titleRow, description, meta, destination);

    const progressWrap = document.createElement('div');
    progressWrap.className = 'managed-progress-wrap';
    const percent = Math.max(0, Math.min(100, Number(model.progress_percent) || 0));
    const progressHeading = document.createElement('div');
    progressHeading.className = 'managed-progress-heading';
    const progressText = document.createElement('span');
    if (model.status === 'downloading' || model.status === 'checking') {
      progressText.textContent = `${formatBytes(model.downloaded_bytes)} / ${formatBytes(model.expected_bytes || model.advertised_size_bytes)}`;
    } else if (model.installed) {
      progressText.textContent = `${formatBytes(model.downloaded_bytes)} installed`;
    } else {
      progressText.textContent = 'Ready to download';
    }
    const progressPercent = document.createElement('span');
    progressPercent.className = 'managed-progress-percent';
    progressPercent.textContent = model.status === 'downloading' ? `${percent.toFixed(1)}%` : '';
    progressHeading.append(progressText, progressPercent);

    const track = document.createElement('div');
    track.className = 'managed-progress-track';
    const fill = document.createElement('div');
    fill.className = 'managed-progress-fill';
    fill.style.width = `${model.installed ? 100 : percent}%`;
    track.appendChild(fill);

    const error = document.createElement('div');
    error.className = 'managed-model-error';
    error.hidden = !model.error;
    error.textContent = model.error || '';

    progressWrap.append(progressHeading, track, error);

    const actions = document.createElement('div');
    actions.className = 'managed-model-actions';

    const verifiedInstalled = model.installed === true && model.status === 'installed';
    if (verifiedInstalled) {
      const use = document.createElement('button');
      use.className = 'primary-button';
      use.type = 'button';
      use.textContent = 'Use Model';
      use.addEventListener('click', async () => {
        await loadModels();
        if (state.models.some(item => item.id === model.index_id)) {
          useModel(model.index_id);
        } else {
          toast('Model index is updating', 'Refresh the managed model list and try again.', 'warning');
        }
      });
      actions.appendChild(use);
    } else if (['checking', 'downloading'].includes(model.status)) {
      const downloading = document.createElement('button');
      downloading.className = 'secondary-button busy-button busy';
      downloading.type = 'button';
      downloading.disabled = true;
      const spinner = document.createElement('span');
      spinner.className = 'spinner';
      const label = document.createElement('span');
      label.className = 'button-label';
      label.textContent = model.status === 'checking' ? 'Preparing…' : 'Downloading…';
      downloading.append(spinner, label);
      actions.appendChild(downloading);
    } else {
      const download = document.createElement('button');
      download.className = 'primary-button busy-button';
      download.type = 'button';
      const spinner = document.createElement('span');
      spinner.className = 'spinner';
      const label = document.createElement('span');
      label.className = 'button-label';
      label.textContent = model.status === 'failed' ? 'Retry Download' :
        ['interrupted','partial'].includes(model.status) ? 'Resume / Repair' : 'Download';
      download.append(spinner, label);
      download.addEventListener('click', () => startManagedDownload(model.id));
      actions.appendChild(download);
    }

    card.append(info, progressWrap, actions);
    return card;
  }

  function renderManagedModels() {
    const list = qs('#managed-model-list');
    if (!list) return;
    list.replaceChildren();
    if (!state.managedModels.length) {
      const empty = document.createElement('div');
      empty.className = 'model-empty';
      empty.innerHTML = '<strong>No managed models available</strong><span>The managed catalog is currently empty.</span>';
      list.appendChild(empty);
      return;
    }
    state.managedModels.forEach(model => list.appendChild(managedModelCard(model)));
  }

  function scheduleManagedPoll() {
    window.clearTimeout(state.managedPollTimer);
    state.managedPollTimer = null;
    // The download request can be accepted before status changes from idle
    // to checking. Continue polling pending requests until they resolve.
    const active = state.downloadOperations.size > 0 ||
      state.managedModels.some(model => ['checking', 'downloading'].includes(model.status));
    if (active) {
      state.managedPollTimer = window.setTimeout(() => loadManagedModels(), 900);
    }
  }


  function reportManagedDownloads() {
    const ops = window.MorphorumOperations;
    if (!ops) return;
    for (const model of state.managedModels) {
      const key = 'download:' + model.id;
      const running = ['checking','downloading'].includes(model.status);
      let token = state.downloadOperations.get(model.id);
      if (!token && running) {
        token = ops.begin(key, 'Downloading ' + (model.name || model.id),
          'Managed package is being prepared or downloaded…', 'models');
        state.downloadOperations.set(model.id, token);
      }
      if (!token) continue;
      const percent = Math.max(0, Math.min(100, Number(model.progress_percent) || 0));
      if (running) state.downloadPendingChecks.delete(model.id);
      if (running) {
        const bytes = formatBytes(model.downloaded_bytes) + ' / ' +
          formatBytes(model.expected_bytes || model.advertised_size_bytes);
        ops.update(key, token, { title: (model.status === 'checking'
          ? 'Preparing ' : 'Downloading ') + (model.name || model.id),
          message: model.status === 'checking' ? 'Checking managed package files…'
            : bytes + ' · ' + percent.toFixed(1) + '%',
          progress: model.status === 'downloading' ? percent : null });
      } else if (model.installed && model.status === 'installed') {
        ops.finish(key, token, {
          title: 'Managed model installed',
          message: (model.name || model.id) + ' is ready. Select Use Model in Models.',
          view: 'models' });
        state.downloadOperations.delete(model.id);
        state.downloadPendingChecks.delete(model.id);
      } else if (['failed','interrupted','partial'].includes(model.status)) {
        ops.finish(key, token, {
          tone: model.status === 'failed' ? 'error' : 'warning',
          title: model.status === 'failed' ? 'Model download failed' : 'Model download paused',
          message: (model.error || model.name || model.id) +
            '. Review the package in Models and use Resume / Repair if needed.',
          view: 'models' });
        state.downloadOperations.delete(model.id);
        state.downloadPendingChecks.delete(model.id);
      } else if (state.downloadPendingChecks.has(model.id)) {
        // Bounded wait for catalog to acknowledge an accepted POST. An idle
        // model forever is not evidence of a running background download.
        const checks = (state.downloadPendingChecks.get(model.id) || 0) + 1;
        if (checks >= 15) {
          ops.finish(key, token, {
            tone: 'error', title: 'Model download did not start',
            message: 'The host accepted the request but did not report download activity. Check Models and retry or review the Console.',
            view: 'models' });
          state.downloadOperations.delete(model.id);
          state.downloadPendingChecks.delete(model.id);
        } else {
          state.downloadPendingChecks.set(model.id, checks);
        }
      }
    }
  }

  async function loadManagedModels() {
    const previousInstalled = new Set(
      state.managedModels.filter(model => model.installed).map(model => model.id)
    );
    try {
      const payload = await window.MorphorumPollHealth.request(signal =>
        api('/api/managed-models', {signal}));
      state.managedModels = Array.isArray(payload.models) ? payload.models : [];
      window.MorphorumPollHealth?.recovered('managed-models');
      renderManagedModels();
      reportManagedDownloads();
      scheduleManagedPoll();

      const newlyInstalled = state.managedModels.some(
        model => model.installed && !previousInstalled.has(model.id)
      );
      if (newlyInstalled) await loadModels();
    } catch (error) {
      const list = qs('#managed-model-list');
      if (list) {
        const empty = document.createElement('div');
        empty.className = 'model-empty';
        const title = document.createElement('strong');
        title.textContent = 'Could not refresh managed catalog';
        const detail = document.createElement('span');
        detail.textContent = 'Check the backend connection. In-progress downloads may still be running.';
        empty.append(title, detail);
        list.replaceChildren(empty);
      }
      const hasDownloads = state.downloadOperations.size > 0 ||
        state.managedModels.some(model => ['checking', 'downloading'].includes(model.status));
      if (hasDownloads) {
        window.MorphorumPollHealth?.failed('managed-models', 'Managed download', 'models');
        // Preserve accepted download IDs; losing contact is not a failed download.
        window.clearTimeout(state.managedPollTimer);
        state.managedPollTimer = window.setTimeout(() => loadManagedModels(), 6000);
      } else {
        toast('Managed catalog unavailable',
          'Could not reach the host. Check the connection and refresh Models.', 'warning', 7000);
      }
    }
  }

  async function startManagedDownload(modelId) {
    if (state.downloadOperations.has(modelId)) return;
    const model = state.managedModels.find(item => item.id === modelId);
    const token = window.MorphorumOperations?.begin('download:' + modelId,
      'Starting ' + (model?.name || modelId),
      'Requesting managed package download from the host…', 'models');
    if (token) state.downloadOperations.set(modelId, token);
    try {
      await api(`/api/managed-models/${encodeURIComponent(modelId)}/download`, {
        method: 'POST',
        body: '{}',
      });
      state.downloadPendingChecks.set(modelId, 0);
      window.MorphorumOperations?.update('download:' + modelId, token, {
        title: 'Preparing ' + (model?.name || modelId),
        message: 'Downloading in the background. Model Manager shows live bytes and percentage.',
        progress: null });
      toast(
        'Model download started',
        `${model?.name || modelId} is downloading in the background. You can leave this page open to watch progress.`,
        'info',
        6000
      );
      await loadManagedModels();
    } catch (error) {
      window.MorphorumOperations?.finish('download:' + modelId, token, {
        tone: 'error', title: 'Could not start model download',
        message: error.message + '. Check storage/network access and retry in Models.',
        view: 'models' });
      state.downloadOperations.delete(modelId);
      state.downloadPendingChecks.delete(modelId);
      toast('Could not start model download', error.message, 'error', 8000);
    }
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

  function copyText(text) { return window.MorphorumClipboard.writeText(text); }

  function updateBulkControls() {
    const count = state.bulkSelected.size;
    for (const [id, label] of [['model-bulk-identify','Identify Selected'],['model-bulk-updates','Check Updates'],['model-bulk-sync','Sync Civitai Info']]) {
      const button = qs('#' + id);
      if (button) { button.disabled = state.bulkBusy || !count; button.textContent = label + ' (' + count + ')'; }
    }
    for (const id of ['model-select-visible','model-clear-selected']) {
      const button = qs('#' + id);
      if (button) button.disabled = state.bulkBusy;
    }
    const status = qs('#model-bulk-status');
    if (status && !state.bulkBusy) status.textContent = count + ' selected';
  }
  async function bulkCheck(mode) {
    if (state.bulkBusy || !state.bulkSelected.size) return;
    const selected = [...state.bulkSelected].filter(id => state.models.some(model => model.id === id));
    state.bulkBusy = true;
    updateBulkControls();
    let matched = 0, unmatched = 0, failed = 0, syncedWithPreview = 0;
    const errors = [];
    try {
      for (let index = 0; index < selected.length; index++) {
        const id = selected[index];
        const model = state.models.find(item => item.id === id);
        qs('#model-bulk-status').textContent = (index + 1) + '/' + selected.length + ' · ' + (model?.name || id);
        try {
          const suffix = mode === 'identify' ? 'identify/' : mode === 'updates' ? 'updates/' : 'library/';
          const response = await api('/api/civitai/' + suffix + encodeURIComponent(id) +
            (mode === 'sync' ? '/sync' : ''), {method:'POST'});
          if (mode === 'sync') {
            window.MorphorumThumbnails?.set(id, response);
            if (response.preview) syncedWithPreview++;
          }
          if (mode === 'identify' ? response.found : mode === 'sync' ? response.synced :
            response.status === 'newer_available') matched++;
          else unmatched++;
        } catch (error) {
          failed++;
          if (errors.length < 3) errors.push((model?.name || id) + ': ' + error.message);
        }
      }
      if (mode === 'sync') renderModels();
      toast('Bulk Civitai ' + (mode === 'identify' ? 'identification' : mode === 'sync' ? 'sync' : 'update check') + ' completed',
        (mode === 'sync' ? matched + ' metadata synced · ' + syncedWithPreview + ' thumbnails downloaded · ' +
          (matched - syncedWithPreview) + ' without thumbnails · ' + failed + ' failed.' :
          matched + ' matches/newer · ' + unmatched + ' no match/no newer · ' + failed + ' failed.') +
          (errors.length ? ' ' + errors.join(' | ') : ''),
        failed || (mode === 'sync' && matched > syncedWithPreview) ? 'warning' : 'success', 9000);
    } finally {
      state.bulkBusy = false;
      updateBulkControls();
      qs('#model-bulk-status').textContent = matched + ' found · ' + unmatched + ' unchanged/unmatched · ' + failed + ' errors';
    }
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
    const pathDetails = document.createElement('details');
    pathDetails.className = 'model-path-details';
    const pathSummary = document.createElement('summary');
    pathSummary.textContent = 'Show full file path';
    pathDetails.append(pathSummary, path);

    const size = document.createElement('div');
    size.className = 'model-size';
    size.textContent = formatBytes(model.size_bytes);

    let action;
    if (model.kind === 'checkpoints') {
      action = document.createElement('button');
      action.className = 'primary-button use-model-button';
      action.textContent = (model.family === 'zimage' && model.source !== 'managed') ? 'Indexed only' : 'Use';
      if (model.family === 'zimage' && model.source !== 'managed') {
        action.disabled = true;
        action.title = 'Standalone Civitai Z-Image checkpoints need a single-file loader before generation is supported.';
      }
      action.addEventListener('click', () => useModel(model.id));
    } else {
      action = document.createElement('button');
      action.className = 'secondary-button use-model-button';
      action.textContent = 'Copy Tag';
      action.addEventListener('click', async () => {
        const tag = window.MorphorumPromptTags.lora({ name: model.name, weight: 1 });
        try {
          await copyText(tag);
          toast('LoRA tag copied', tag, 'success');
        } catch (error) {
          toast('Could not copy LoRA tag', error.message, 'error');
        }
      });
    }

    const identify = document.createElement('button');
    identify.type = 'button';
    identify.className = 'secondary-button compact busy-button';
    identify.textContent = 'Identify on Civitai';
    identify.title = 'Explicit SHA-256 lookup; sends only the file hash to Civitai.';
    const identityResult = document.createElement('div');
    identityResult.className = 'model-civitai-identity';
    nameWrap.append(identityResult);
    identify.addEventListener('click', async () => {
      identify.disabled = true;
      identify.classList.add('busy');
      identify.textContent = 'Identifying…';
      try {
        const response = await fetch('/api/civitai/identify/' + encodeURIComponent(model.id), {method: 'POST'});
        const result = await response.json();
        if (!response.ok) throw new Error(result.detail || 'Identification failed');
        if (result.found) {
          const link = document.createElement('a');
          link.href = result.url;
          link.target = '_blank';
          link.rel = 'noopener noreferrer';
          link.textContent = 'Verified: ' + (result.name || 'Civitai model') + ' · ' + (result.version || 'version') + ' ↗';
          identityResult.replaceChildren(link);
          toast('Exact SHA-256 match', model.name + ' identified on Civitai.', 'success');
        } else {
          identityResult.replaceChildren();
          toast('No verified Civitai match', result.message || model.name, 'info');
        }
      } catch (error) { toast('Civitai identification failed', error.message, 'error'); }
      finally {
        identify.disabled = false;
        identify.classList.remove('busy');
        identify.textContent = 'Identify on Civitai';
      }
    });
    const update = document.createElement('button');
    update.type = 'button';
    update.className = 'secondary-button compact busy-button';
    update.textContent = 'Check Updates';
    update.title = 'Read-only Civitai version check. Does not download or replace files.';
    const updateResult = document.createElement('div');
    updateResult.className = 'model-civitai-identity';
    nameWrap.append(updateResult);
    update.addEventListener('click', async () => {
      update.disabled = true;
      update.classList.add('busy');
      update.textContent = 'Checking…';
      try {
        const response = await fetch('/api/civitai/updates/' + encodeURIComponent(model.id), {method:'POST'});
        const result = await response.json();
        if (!response.ok) throw new Error(result.detail || 'Update check failed');
        updateResult.replaceChildren();
        if (result.status === 'newer_available') {
          const heading = document.createElement('strong');
          heading.textContent = result.candidates.length + ' newer version(s): ';
          updateResult.append(heading);
          result.candidates.slice(0, 3).forEach((candidate, index) => {
            const link = document.createElement('a');
            link.href = candidate.url;
            link.target = '_blank';
            link.rel = 'noopener noreferrer';
            link.textContent = candidate.version + (candidate.potentially_compatible ? ' (same base)' : ' (verify compatibility)') + ' ↗';
            if (index) updateResult.append(document.createTextNode(' · '));
            updateResult.append(link);
          });
          toast('Civitai updates found', model.name + ': ' + result.candidates.length + ' newer versions.', 'info');
        } else {
          updateResult.textContent = result.message || 'No newer versions found.';
          toast('Civitai update check', updateResult.textContent, 'info');
        }
      } catch (error) { toast('Update check failed', error.message, 'error'); }
      finally { update.disabled = false; update.classList.remove('busy'); update.textContent = 'Check Updates'; }
    });
    const sync = document.createElement('button');
    sync.type = 'button';
    sync.className = 'secondary-button compact busy-button';
    sync.textContent = 'Sync Civitai Info';
    sync.title = 'Explicitly cache verified Civitai metadata and an optional preview.';
    const metadataResult = document.createElement('div');
    metadataResult.className = 'model-civitai-metadata';
    nameWrap.append(metadataResult);
    const showMetadata = data => {
      metadataResult.replaceChildren();
      if (!data?.synced) return;
      const title = document.createElement('strong');
      title.textContent = 'Cached: ' + (data.name || model.name) + ' · ' + (data.version || '');
      metadataResult.append(title);
      const line = document.createElement('div');
      line.textContent = [data.creator, data.base_model, data.synced_at ? 'Synced ' + new Date(data.synced_at).toLocaleDateString() : ''].filter(Boolean).join(' · ');
      metadataResult.append(line);
      // The prominent thumbnail lives on the card, not buried in this caption.
      if (!data.preview) {
        const note = document.createElement('small');
        note.className = 'model-preview-diagnostic';
        note.textContent = data.preview_warning || 'No usable cached Civitai thumbnail was found.';
        metadataResult.append(note);
      }
      if (data.preview_source === 'same_model_other_version') {
        const source = document.createElement('small');
        source.className = 'muted';
        source.textContent = 'Representative image from another version of this Civitai model.';
        metadataResult.append(source);
      }
      if (data.trained_words?.length) {
        const words = document.createElement('div');
        words.textContent = 'Triggers: ' + data.trained_words.slice(0, 8).join(', ');
        metadataResult.append(words);
      }
    };
    sync.addEventListener('click', async () => {
      sync.disabled = true;
      sync.classList.add('busy');
      sync.textContent = 'Syncing…';
      try {
        const response = await fetch('/api/civitai/library/' + encodeURIComponent(model.id) + '/sync', {method:'POST'});
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || 'Metadata sync failed');
        window.MorphorumThumbnails?.set(model.id, data);
        const oldArt = row.querySelector('.library-artwork');
        if (oldArt) oldArt.replaceWith(window.MorphorumThumbnails.create(model.id, model.name, 'model-entry-art'));
        showMetadata(data);
        toast(data.preview ? 'Civitai info + thumbnail cached' : 'Civitai info saved, no thumbnail',
          data.preview ? model.name + ': image stored locally.' :
            (data.preview_warning || 'No suitable Civitai image was available for this model.'),
          data.preview ? 'success' : 'warning', 7500);
      } catch (error) { toast('Metadata sync failed', error.message, 'error'); }
      finally { sync.disabled = false; sync.classList.remove('busy'); sync.textContent = 'Sync Civitai Info'; }
    });
    const viewCache = document.createElement('button');
    viewCache.type = 'button';
    viewCache.className = 'secondary-button compact';
    viewCache.textContent = 'View Cached Info';
    viewCache.addEventListener('click', async () => {
      try {
        const response = await fetch('/api/civitai/library/' + encodeURIComponent(model.id));
        const data = await response.json();
        if (!response.ok) throw Error(data.detail || 'Cache unavailable');
        window.MorphorumThumbnails?.set(model.id, data);
        const oldArt = row.querySelector('.library-artwork');
        if (oldArt) oldArt.replaceWith(window.MorphorumThumbnails.create(model.id, model.name, 'model-entry-art'));
        showMetadata(data);
        if (!data.synced) toast('No cached metadata', 'Use Sync Civitai Info first.', 'info');
      } catch (error) { toast('Cannot read Civitai cache', error.message, 'error'); }
    });
    const checked = document.createElement('input');
    checked.type = 'checkbox';
    checked.className = 'model-bulk-checkbox';
    checked.checked = state.bulkSelected.has(model.id);
    checked.disabled = state.bulkBusy;
    checked.setAttribute('aria-label', 'Select ' + model.name + ' for bulk Civitai actions');
    checked.addEventListener('change', () => {
      if (checked.checked) state.bulkSelected.add(model.id);
      else state.bulkSelected.delete(model.id);
      updateBulkControls();
    });
    // Four coherent regions: selection, artwork, summary, then actions.
    const artwork = window.MorphorumThumbnails?.create(model.id, model.name, 'model-entry-art');
    const summary = document.createElement('div');
    summary.className = 'model-entry-summary';
    const pills = document.createElement('div');
    pills.className = 'model-entry-pills';
    pills.append(family, kind, size);
    summary.append(nameWrap, pills, pathDetails);
    const actions = document.createElement('div');
    actions.className = 'model-entry-actions';
    actions.append(action, identify, update, sync, viewCache);
    row.append(checked);
    if (artwork) row.append(artwork);
    row.append(summary, actions);
    const cached = window.MorphorumThumbnails?.get(model.id);
    if (cached?.synced) showMetadata(cached);
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
      empty.innerHTML = '<strong>No indexed models yet</strong><span>Configure SDXL/Flux directories or download a managed model above.</span>';
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
    updateBulkControls();
  }

  function updateImageBadge() {
    const select = qs('#image-model-select');
    const badge = qs('#image-model-family-badge');
    if (!select || !badge) return;
    const model = state.models.find(item => item.id === select.value);
    badge.textContent = model ? (FAMILY_LABELS[model.family] || model.family) : 'No model';
    if (model) localStorage.setItem('morphorum.image.modelId', model.id);
  }

  function notifyImageSelection(select) {
    select.dispatchEvent(new Event('change', { bubbles: true }));
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
      if (model.family === 'zimage' && model.source !== 'managed') {
        option.disabled = true;
        option.title = 'Indexed Civitai checkpoint. Standalone Z-Image weights are not supported by the current Diffusers package loader.';
      }
      option.value = model.id;
      option.textContent = `[${FAMILY_LABELS[model.family] || model.family}] ${model.name}` + (option.disabled ? ' · indexed only (loader unsupported)' : '');
      option.title = model.path;
      select.appendChild(option);
    }
    select.disabled = models.length === 0;
    if (models.some(model => model.id === previous && !(model.family === 'zimage' && model.source !== 'managed'))) select.value = previous;
    updateImageBadge();
    notifyImageSelection(select);
  }

  function useModel(modelId) {
    const select = qs('#image-model-select');
    const model = state.models.find(item => item.id === modelId);
    if (!select || !model) return;
    if (model.family === 'zimage' && model.source !== 'managed') {
      toast('Indexed but not loadable', 'Standalone Z-Image Civitai checkpoints require a compatible single-file loader. The existing runtime supports managed Diffusers packages.', 'warning');
      return;
    }
    select.value = modelId;
    updateImageBadge();
    notifyImageSelection(select);
    qs('.nav-button[data-view="image"]')?.click();
    toast('Model selected', `${model.name} is selected for image generation.`, 'success');
  }

  async function selectExisting(modelId) {
    await loadModels();
    const model = state.models.find(item => item.id === modelId && item.kind === 'checkpoints');
    const select = qs('#image-model-select');
    if (!model || !select || (model.family === 'zimage' && model.source !== 'managed')) return false;
    select.value = modelId;
    updateImageBadge();
    notifyImageSelection(select);
    return true; // Selection only: never load weights or navigate away from setup.
  }

  async function loadModels({ announce = false, propagate = false } = {}) {
    const list = qs('#model-list');
    try {
      const payload = await api('/api/models?limit=2000');
      state.models = Array.isArray(payload.models) ? payload.models : [];
      const validIds = new Set(state.models.map(item => item.id));
      for (const id of state.bulkSelected) if (!validIds.has(id)) state.bulkSelected.delete(id);
      window.dispatchEvent(new CustomEvent('morphorum:models-updated', {
        detail: { models: state.models, loaded: true },
      }));
      updateSummary();
      renderModels();
      // Display immediately, then populate previews from local disk only.
      const ids = state.models.map(model => model.id);
      void window.MorphorumThumbnails?.refresh(ids).then(() => renderModels());
      populateImageModelSelect();
      if (announce) toast('Model index loaded', `${state.models.length} file(s) available.`, 'success');
    } catch (error) {
      if (list) {
          const empty = document.createElement('div');
          empty.className = 'model-empty';
          const title = document.createElement('strong');
          title.textContent = 'Could not load ' + 'model index';
          const detail = document.createElement('span');
          detail.textContent = String(error.message);
          empty.append(title, detail);
          list.replaceChildren(empty);
        }
      window.dispatchEvent(new CustomEvent('morphorum:models-updated', {
        detail: { models: [], loaded: false },
      }));
      toast('Model index unavailable', error.message, 'error', 6500);
      if (propagate) throw error;
    }
  }

  async function scanModels() {
    if (state.scanning || state.bulkBusy) return;
    state.scanning = true;
    const button = qs('#scan-models');
    setBusy(button, true);
    const operation = window.MorphorumOperations?.begin('model-scan',
      'Scanning model directories', 'Checking configured checkpoint and LoRA folders…', 'models');
    try {
      const result = await api('/api/models/scan', { method: 'POST', body: '{}' });
      window.MorphorumOperations?.update('model-scan', operation, {
        title: 'Refreshing model index',
        message: 'Scan completed. Updating checkpoint selectors across the WebUI…' });
      await loadModels({ propagate: true });
      if (result.warnings?.length) {
        const message = `${result.total} file(s) indexed with ${result.warnings.length} warning(s). Review Models and paths in Settings.`;
        window.MorphorumOperations?.finish('model-scan', operation, {
          tone: 'warning', title: 'Model scan completed with warnings',
          message, view: 'models' });
        toast('Model scan complete', message, 'warning', 6000);
      } else {
        const message = `${result.total} file(s) indexed from ${result.scanned_roots} configured directories.`;
        window.MorphorumOperations?.finish('model-scan', operation, {
          title: 'Model scan complete', message, view: 'models' });
        toast('Model scan complete', message, 'success');
      }
    } catch (error) {
      window.MorphorumOperations?.finish('model-scan', operation, {
        tone: 'error', title: 'Model scan failed',
        message: error.message + '. Check model paths in Settings and retry the scan.',
        view: 'models' });
      toast('Model scan failed', error.message, 'error', 7000);
    } finally {
      state.scanning = false;
      setBusy(button, false);
    }
  }

  function bind() {
    qs('#scan-models')?.addEventListener('click', scanModels);
    qs('#model-select-visible')?.addEventListener('click', () => {
      for (const item of currentFilteredModels()) state.bulkSelected.add(item.id);
      renderModels();
    });
    qs('#model-clear-selected')?.addEventListener('click', () => { state.bulkSelected.clear(); renderModels(); });
    qs('#model-bulk-identify')?.addEventListener('click', () => bulkCheck('identify'));
    qs('#model-bulk-updates')?.addEventListener('click', () => bulkCheck('updates'));
    qs('#model-bulk-sync')?.addEventListener('click', () => bulkCheck('sync'));
    qs('#model-search')?.addEventListener('input', renderModels);
    qs('#model-family-filter')?.addEventListener('change', renderModels);
    qs('#model-kind-filter')?.addEventListener('change', renderModels);
    qs('#model-filters-clear')?.addEventListener('click', () => {
      qs('#model-search').value = '';
      qs('#model-family-filter').value = '';
      qs('#model-kind-filter').value = '';
      renderModels();
    });
    qs('#image-model-select')?.addEventListener('change', updateImageBadge);
  }

  async function start() {
    bind();
    try {
      await loadFamilies();
    } catch (error) {
      toast('Model family registry unavailable', error.message, 'warning');
    }
    await loadManagedModels();
    await loadModels();
  }

  window.MorphorumModels = {
    reload: loadModels,
    scan: scanModels,
    reloadManaged: loadManagedModels,
    selectExisting,
  };
  window.addEventListener('morphorum:settings-changed', () => {
    void loadManagedModels();
    void loadModels(); // Respect changed Civitai preview / mature-content preferences.
  });
  window.addEventListener('DOMContentLoaded', start);
})();
