(() => {
  'use strict';
  const byId = id => document.getElementById(id);
  const state = { enabled: false, layout: 'grid', serial: 0, busy: false, loaded: false, cursors: [''], page: 0, next: null };
  const toast = (title, message, type) => window.MorphorumToast?.(title, message, type, 6500);
  const form = () => byId('civitai-search-form');
  const status = message => { byId('civitai-result-status').textContent = message; };
  const elt = (tag, className, content) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (content != null) node.textContent = String(content);
    return node;
  };
  function settingsChanged(config = {}) {
    state.enabled = config.enabled === true;
    state.layout = config.layout === 'list' ? 'list' : 'grid';
    const nav = byId('civitai-nav');
    if (nav) nav.hidden = !state.enabled;
    byId('civitai-results')?.classList.toggle('civitai-list', state.layout === 'list');
    if (!state.enabled) {
      state.serial++;
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
  function activate() { if (state.enabled && !state.loaded && !state.busy) void search(0); }
  document.addEventListener('DOMContentLoaded', () => {
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
