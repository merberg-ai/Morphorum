(() => {
  'use strict';
  const root = () => document.querySelector('#view-help');
  const list = () => document.querySelector('#help-document-list');
  const content = () => document.querySelector('#help-content');
  const select = () => document.querySelector('#help-document-select');
  const state = {loaded:false, documents:[], current:''};
  const escapeHtml = value => String(value).replace(/[&<>"']/g, chr =>
    ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[chr]));
  const isDoc = name => /^[A-Za-z0-9_.-]+\.md$/.test(name) && !name.startsWith('.');
  function inline(value) {
    const segments = [];
    let safe = escapeHtml(value).replace(/`([^`]+)`/g, (_, token) => '<code>'+token+'</code>');
    // Only known document links are navigable within Help; all other links stay plain text.
    safe = safe.replace(/\[([^\]]+)\]\(([^)]+)\)/g, (_, title, url) => {
      const raw = url.replace(/&amp;/g, '&');
      const relative = raw.split('#')[0].split('/').pop();
      if (/^(?:\.\/)?[\w.\/-]+\.md(?:#[\w-]+)?$/.test(raw) && isDoc(relative)) {
        return '<a href="#" data-help-doc="'+escapeHtml(relative)+'">'+title+'</a>';
      }
      return title + ' (' + escapeHtml(raw) + ')';
    });
    safe = safe.replace(/\*\*([^*]+)\*\*/g,'<strong>$1</strong>');
    safe = safe.replace(/\*([^*]+)\*/g,'<em>$1</em>');
    return safe;
  }
  function markdownToHtml(markdown) {
    const lines = String(markdown).split(/\r?\n/);
    const out = [];
    let inCode = false, inList = false, inTable = false;
    const closeList = () => { if (inList) {out.push('</ul>'); inList = false;} };
    const closeTable = () => { if (inTable) {out.push('</tbody></table>'); inTable = false;} };
    const rowCells = line => line.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map(cell => cell.trim());
    const isTableDivider = line => /^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(line);
    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];
      if (/^\s*```/.test(line)) {
        closeList(); closeTable();
        out.push(inCode ? '</code></pre>' : '<pre><code>');
        inCode = !inCode;
        continue;
      }
      if (inCode) { out.push(escapeHtml(line)+'\n'); continue; }
      if (!line.trim()) { closeList(); closeTable(); continue; }
      if (!inTable && line.includes('|') && i + 1 < lines.length && isTableDivider(lines[i + 1])) {
        closeList();
        out.push('<table><thead><tr>');
        rowCells(line).forEach(cell => out.push('<th>'+inline(cell)+'</th>'));
        out.push('</tr></thead><tbody>');
        inTable = true; i++;
        continue;
      }
      if (inTable && line.includes('|')) {
        out.push('<tr>');
        rowCells(line).forEach(cell => out.push('<td>'+inline(cell)+'</td>'));
        out.push('</tr>');
        continue;
      }
      closeTable();
      const head = /^(#{1,6})\s+(.+)$/.exec(line);
      if (head) {closeList(); const n = head[1].length; out.push('<h'+n+'>'+inline(head[2])+'</h'+n+'>'); continue;}
      const bullet = /^\s*[-*]\s+(.+)$/.exec(line);
      if (bullet) {if (!inList) {out.push('<ul>');inList = true;}out.push('<li>'+inline(bullet[1])+'</li>');continue;}
      closeList();
      if (/^>\s?/.test(line)) out.push('<blockquote>'+inline(line.replace(/^>\s?/,''))+'</blockquote>');
      else if (/^---+\s*$/.test(line)) out.push('<hr>');
      else out.push('<p>'+inline(line)+'</p>');
    }
    closeList(); closeTable();
    if (inCode) out.push('</code></pre>');
    return out.join('\n');
  }
  async function showDoc(name) {
    if (!isDoc(name) || !state.documents.some(item => item.name === name)) return;
    state.current = name;
    if (content()) content().textContent = 'Loading documentation…';
    try {
      const response = await fetch('/api/help/docs/'+encodeURIComponent(name));
      if (!response.ok) throw new Error('HTTP '+response.status);
      const payload = await response.json();
      if (content()) content().innerHTML = markdownToHtml(payload.markdown || '');
      if (select()) select().value = name;
      list()?.querySelectorAll('button[data-help-name]').forEach(button =>
        button.classList.toggle('active',button.dataset.helpName===name));
    } catch (error) {
      if (content()) content().textContent = 'Could not load '+name+': '+error.message;
    }
  }
  async function activate() {
    if (state.loaded) return;
    state.loaded = true;
    try {
      const response = await fetch('/api/help/docs');
      if (!response.ok) throw new Error('HTTP '+response.status);
      const payload = await response.json();
      state.documents = (payload.documents || []).filter(item => isDoc(item.name));
      if (select()) {
        select().replaceChildren();
        state.documents.forEach(item => select().add(new Option(item.title || item.name,item.name)));
      }
      if (list()) {
        list().replaceChildren();
        state.documents.forEach(item => {
          const button = document.createElement('button');
          button.type = 'button'; button.dataset.helpName=item.name;
          button.textContent=item.title || item.name;
          button.addEventListener('click', () => showDoc(item.name));
          list().append(button);
        });
      }
      select()?.addEventListener('change',event => showDoc(event.target.value));
      content()?.addEventListener('click',event => {
        const link = event.target.closest('a[data-help-doc]');
        if (!link) return;
        event.preventDefault(); void showDoc(link.dataset.helpDoc);
      });
      if (state.documents.length) await showDoc(state.documents.some(item => item.name==='README.md')?'README.md':state.documents[0].name);
      else if (content()) content().textContent = 'No local Markdown guides were found in the repository docs directory.';
    } catch(error) {
      state.loaded=false;
      if (content()) content().textContent = 'Help documentation is unavailable: '+error.message;
    }
  }
  window.MorphorumHelp={activate, markdownToHtml};
})();
