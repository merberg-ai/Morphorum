(() => {
  'use strict';
  const byId = id => document.getElementById(id);
  const state = { enabled: false, layout: 'grid', serial: 0, busy: false, loaded: false, detailSerial: 0, cursors: [''], page: 0, next: null };
  const toast = (title, message, type) => window.MorphorumToast?.(title, message, type, 6500);
  const form = () => byId('civitai-search-form');
  const status = message => { byId('civitai-result-status').textContent = message; };
  const elt = (tag, className, content) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (content != null) node.textContent = String(content);
    return node;
  };

  async function refreshDownloads() {
    if (!state.enabled) return;
    try {
      const response = await fetch('/api/civitai/downloads');
      if (!response.ok) return;
      const payload = await response.json();
      const root = byId('civitai-download-jobs');
      if (!root) return;
      root.replaceChildren();
      for (const job of payload.jobs || []) {
        const row = elt('div', 'civitai-download-job');
        row.append(elt('strong', '', job.name), elt('span', 'muted', job.status));
        if (job.total_bytes) {
          const progress = elt('progress', 'civitai-download-progress');
          progress.max = job.total_bytes;
          progress.value = job.bytes || 0;
          row.append(progress);
        } else row.append(elt('span', 'muted', ((job.bytes || 0) / 1048576).toFixed(1) + ' MB'));
        if (['queued','downloading'].includes(job.status)) {
          const cancel = elt('button', 'secondary-button compact', 'Cancel');
          cancel.addEventListener('click', async () => {
            cancel.disabled = true;
            await fetch('/api/civitai/downloads/' + encodeURIComponent(job.id) + '/cancel', {method: 'POST'});
            void refreshDownloads();
          });
          row.append(cancel);
        }
        if (job.error) row.append(elt('p', 'muted', job.error));
        root.append(row);
      }
      if (!root.children.length) root.append(elt('p', 'muted', 'No downloads queued.'));
    } catch (error) { toast('Download queue unavailable', error.message, 'warning'); }
  }
  async function queueDownload(modelId, versionId, fileName, button) {
    button.disabled = true;
    button.classList.add('busy');
    button.textContent = 'Queueing…';
    try {
      const response = await fetch('/api/civitai/downloads', {method:'POST', headers:{'Content-Type':'application/json'},
        body:JSON.stringify({model_id:modelId, version_id:versionId, file_name:fileName})});
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || 'Download request failed');
      toast('Download queued', fileName, 'success');
      void refreshDownloads();
      if (!state.downloadTimer) state.downloadTimer = setInterval(refreshDownloads, 2000);
    } catch (error) { toast('Unable to queue download', error.message, 'error'); }
    finally { button.disabled = false; button.classList.remove('busy'); button.textContent = 'Add to download queue'; }
  }
  function settingsChanged(config = {}) {
    state.enabled = config.enabled === true;
    state.layout = config.layout === 'list' ? 'list' : 'grid';
    const nav = byId('civitai-nav');
    if (nav) nav.hidden = !state.enabled;
    byId('civitai-results')?.classList.toggle('civitai-list', state.layout === 'list');
    if (!state.enabled) {
      if (state.downloadTimer) clearInterval(state.downloadTimer);
      state.downloadTimer = null;
      state.serial++;
      state.detailSerial++;
      byId('civitai-detail-dialog')?.close();
      state.loaded = false;
      if (byId('civitai-search-button')) setBusy(false);
      const current = document.querySelector('#view-civitai.active');
      if (current) document.querySelector('.nav-button[data-view="models"]')?.click();
      byId('civitai-results')?.replaceChildren();
      status('Civitai Hub is disabled. Enable it under Settings.');
    }
  }
  function setBusy(busy) {
    state.busy = busy;
    const button = byId('civitai-search-button');
    button.disabled = busy;
    button.classList.toggle('busy', busy);
    button.querySelector('.button-label').textContent = busy ? 'Searching…' : 'Search models';
    byId('civitai-next').disabled = busy || !state.next;
    byId('civitai-previous').disabled = busy || state.page === 0;
  }
  async function showDetails(id) {
    if (!state.enabled || !Number.isSafeInteger(id) || id <= 0) return;
    const dialog = byId('civitai-detail-dialog');
    const body = byId('civitai-detail-content');
    if (!dialog || !body) return;
    const request = ++state.detailSerial;
    body.replaceChildren(elt('p', 'muted', 'Loading model details…'));
    if (!dialog.open) dialog.showModal();
    try {
      const response = await fetch('/api/civitai/models/' + id, {headers: {Accept: 'application/json'}});
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || 'Model details unavailable');
      if (request !== state.detailSerial || !state.enabled) return;
      byId('civitai-detail-title').textContent = data.name || 'Model details';
      body.replaceChildren();
      body.append(elt('p', 'muted', 'By ' + (data.creator || 'Unknown creator') + ' · ' + (data.type || 'Model')));
      if (data.description) body.append(elt('div', 'civitai-description-panel', data.description));
      if (Array.isArray(data.tags) && data.tags.length) body.append(elt('p', 'muted', 'Tags: ' + data.tags.join(', ')));
      const versions = Array.isArray(data.versions) ? data.versions : [];
      if (!versions.length) { body.append(elt('p', 'muted', 'No versions available.')); return; }
      const selectLabel = elt('label', 'civitai-detail-version-label', 'Model version');
      const select = elt('select', 'civitai-detail-version');
      versions.forEach((v, i) => {
        const opt = elt('option', '', (v.name || 'Version') + ' · ' + (v.base_model || 'Unknown base'));
        opt.value = String(i);
        select.append(opt);
      });
      selectLabel.append(select);
      const area = elt('section', 'civitai-detail-version-content');
      function renderVersion() {
        area.replaceChildren();
        const v = versions[Number(select.value)] || versions[0];
        area.append(elt('p', 'civitai-detail-compatibility', v.compatibility || 'Compatibility not verified'));
        if (v.description) area.append(elt('div', 'civitai-description-panel', v.description));
        if (v.trained_words?.length) area.append(elt('p', '', 'Trigger words: ' + v.trained_words.join(', ')));
        const files = elt('div', 'civitai-detail-files');
        for (const file of (v.files || [])) {
          const line = elt('div', 'civitai-detail-file');
          line.append(elt('p', 'muted', [file.name, file.format, Number.isFinite(Number(file.size_kb)) ? (Number(file.size_kb)/1024).toFixed(1) + ' MB' : ''].filter(Boolean).join(' · ')));
          if (/\\.safetensors$/i.test(file.name || '')) {
            const download = elt('button', 'secondary-button compact busy-button', 'Add to download queue');
            download.type = 'button';
            download.addEventListener('click', () => void queueDownload(id, v.id, file.name, download));
            line.append(download);
          }
          files.append(line);
        }
        if (files.childNodes.length) {
          area.append(elt('h3', '', 'Available files'), files);
        }
        const gallery = elt('div', 'civitai-detail-images');
        for (const item of (v.images || [])) {
          if (!/^https:\/\//.test(item.url || '')) continue;
          const image = elt('img');
          image.src = item.url;
          image.alt = 'Civitai version example image';
          image.loading = 'lazy';
          image.referrerPolicy = 'no-referrer';
          gallery.append(image);
        }
        if (gallery.childNodes.length) area.append(elt('h3', '', 'Example images'), gallery);
      }
      select.addEventListener('change', renderVersion);
      body.append(selectLabel, area);
      renderVersion();
      const link = elt('a', 'secondary-button compact civitai-detail-external', 'Open on Civitai ↗');
      link.href = 'https://civitai.com/models/' + id;
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
      body.append(link);
    } catch (error) {
      if (request !== state.detailSerial) return;
      body.replaceChildren(elt('p', 'muted', error.message));
      toast('Model details failed', error.message, 'error');
    }
  }
  function card(item) {
    const root = elt('article', 'civitai-model-card');
    const preview = elt('div', 'civitai-model-preview');
    if (item.thumbnail_url && /^https:\/\//.test(item.thumbnail_url)) {
      const image = document.createElement('img');
      image.src = item.thumbnail_url;
      image.loading = 'lazy';
      image.referrerPolicy = 'no-referrer';
      image.alt = 'Preview for ' + (item.name || 'model');
      image.addEventListener('error', () => { image.remove(); preview.classList.add('civitai-preview-unavailable'); });
      preview.append(image);
    } else preview.classList.add('civitai-preview-unavailable');
    const body = elt('div', 'civitai-model-copy');
    body.append(elt('span', 'civitai-type', item.type || 'Model'), elt('h3', '', item.name || 'Untitled model'));
    body.append(elt('p', 'muted', 'By ' + (item.creator || 'Unknown creator')));
    body.append(elt('p', 'civitai-model-meta', [item.base_model, item.version_name].filter(Boolean).join(' · ')));
    body.append(elt('p', 'civitai-model-meta', Number(item.downloads || 0).toLocaleString() + ' downloads'));
    const link = elt('a', 'secondary-button compact civitai-view-link', 'View on Civitai ↗');
    link.href = 'https://civitai.com/models/' + encodeURIComponent(item.id);
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
    body.append(link);
    const details = elt('button', 'primary-button compact civitai-detail-open', 'Details & versions');
    details.type = 'button';
    details.addEventListener('click', () => void showDetails(item.id));
    body.append(details);
    root.append(preview, body);
    return root;
  }
  async function search(page = 0) {
    if (state.busy || !state.enabled) return;
    const current = ++state.serial;
    const values = new FormData(form());
    const params = new URLSearchParams({limit: '20'});
    for (const key of ['query','model_type','base_model','sort','period','username','tag']) {
      const value = String(values.get(key) || '').trim();
      if (value) params.set(key, value);
    }
    if (page && state.cursors[page]) params.set('cursor', state.cursors[page]);
    setBusy(true);
    status('Searching Civitai…');
    try {
      const response = await fetch('/api/civitai/models?' + params.toString(), {headers:{Accept:'application/json'}});
      const json = await response.json();
      if (!response.ok) throw new Error(json.detail || 'Civitai search failed');
      if (current !== state.serial) return;
      const gallery = byId('civitai-results');
      gallery.replaceChildren();
      const items = Array.isArray(json.items) ? json.items : [];
      for (const item of items) gallery.append(card(item));
      if (!items.length) gallery.append(elt('p', 'civitai-empty', 'No matching models on this page. Try different filters.'));
      state.loaded = true;
      state.page = page;
      state.next = json.next_cursor || null;
      if (state.next) state.cursors[page + 1] = state.next;
      byId('civitai-result-page').textContent = 'Page ' + (page + 1);
      status(items.length + ' model' + (items.length === 1 ? '' : 's') + ' on this page' + (state.next ? ' · More available' : ''));
    } catch (error) {
      if (current !== state.serial) return;
      status('Search failed. ' + error.message);
      toast('Civitai search failed', error.message, 'error');
    } finally { if (current === state.serial) setBusy(false); }
  }
  function activate() { if (state.enabled && !state.loaded && !state.busy) void search(0); if (state.enabled) { void refreshDownloads(); if (!state.downloadTimer) state.downloadTimer = setInterval(refreshDownloads, 2000); } }
  document.addEventListener('DOMContentLoaded', () => {
    byId('civitai-refresh-downloads')?.addEventListener('click', refreshDownloads);
    byId('civitai-detail-close')?.addEventListener('click', () => byId('civitai-detail-dialog')?.close());
    form()?.addEventListener('submit', event => {
      event.preventDefault();
      state.cursors = [''];
      state.next = null;
      void search(0);
    });
    byId('civitai-next')?.addEventListener('click', () => {
      if (state.next && !state.busy) void search(state.page + 1);
    });
    byId('civitai-previous')?.addEventListener('click', () => {
      if (state.page > 0 && !state.busy) void search(state.page - 1);
    });
    fetch('/api/settings').then(res => res.json()).then(json => {
      settingsChanged(json.settings?.civitai || {});
      if (location.hash === '#civitai' && state.enabled) {
        byId('civitai-nav')?.click();
      }
    }).catch(() => {});
  });
  window.MorphorumCivitai = { activate, settingsChanged };
})();
