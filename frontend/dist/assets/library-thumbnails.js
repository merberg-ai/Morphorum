(() => {
  'use strict';
  // Shared, local-only art manifest for the two installed model managers.
  // This never requests Civitai directly and never attempts to download images.
  const records = new Map();
  const endpoint = '/api/civitai/library-catalog';

  function get(id) { return records.get(String(id)) || null; }
  function set(id, value) {
    const key = String(id);
    if (value?.synced) records.set(key, value);
    else records.delete(key);
  }

  async function refresh(ids) {
    const unique = [...new Set((Array.isArray(ids) ? ids : [])
      .filter(id => typeof id === 'string' && /^[A-Za-z0-9_-]{1,100}$/.test(id)))];
    // Local cache reads only. The server caps each request to 120 IDs.
    for (let at = 0; at < unique.length; at += 120) {
      const subset = unique.slice(at, at + 120);
      try {
        const response = await fetch(endpoint, {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({model_ids: subset}),
        });
        if (!response.ok) {
          if (response.status === 403) unique.forEach(id => records.delete(id));
          break;
        }
        const payload = await response.json();
        const entries = payload.entries || {};
        for (const id of subset) set(id, entries[id]);
      } catch (_) {
        // Local file/model browsing works without Civitai enabled or available.
        break;
      }
    }
    return records;
  }

  function create(id, name, extraClass = '') {
    const meta = get(id);
    const holder = document.createElement('div');
    holder.className = 'library-artwork ' + extraClass;
    const fallback = document.createElement('span');
    fallback.className = 'library-artwork-fallback';
    fallback.textContent = 'NO PREVIEW';
    fallback.setAttribute('aria-hidden', 'true');
    holder.appendChild(fallback);
    if (meta?.preview) {
      const img = document.createElement('img');
      img.loading = 'lazy';
      img.decoding = 'async';
      img.alt = 'Cached preview for ' + String(name || 'model');
      img.src = '/api/civitai/library/' + encodeURIComponent(id) +
        '/preview?v=' + encodeURIComponent(meta.synced_at || '');
      img.addEventListener('error', () => img.remove(), {once: true});
      holder.appendChild(img);
    }
    return holder;
  }

  window.MorphorumThumbnails = { get, set, refresh, create };
})();
