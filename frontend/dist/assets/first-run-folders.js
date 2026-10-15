(() => {
  'use strict';
  // MS6.2 lives separately from the New Project Wizard and settings editor.
  const FAMILIES = {models:['sdxl','flux'], loras:['sdxl','flux','zimage']};
  const LABELS = {sdxl:'SDXL', flux:'FLUX', zimage:'Z-Image'};
  const cache = {};
  let currentView = null;
  let renderGeneration = 0;
  const tags = (tag, className, label) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (label !== undefined) node.textContent = label;
    return node;
  };
  const append = (parent, ...children) => children.forEach(child => parent.appendChild(child));
  const same = (a,b) => JSON.stringify(a) === JSON.stringify(b);
  const toast = (title,message,type='info') =>
    window.MorphorumToast?.(title,message,type,6000);

  async function api(url, options={}) {
    const response = await fetch(url, {
      cache:'no-store',
      ...options,
      headers:{
        ...(options.method ? {'X-Morphorum-Setup':'1','Content-Type':'application/json'} : {}),
        ...(options.headers || {}),
      },
    });
    const data = await response.json();
    if (!response.ok) throw new Error(String(data.detail || 'Request failed (' + response.status + ')'));
    return data;
  }
  const paths = kind => Object.fromEntries(FAMILIES[kind].map(f => [f,[]]));
  const normalized = value => Array.from(new Set(
    value.map(p => String(p).trim()).filter(Boolean)
  ));

  async function getState(kind) {
    if (!cache[kind]) {
      const result = await api('/api/settings');
      const defaults = paths(kind);
      FAMILIES[kind].forEach(family => {
        const configured = result.settings?.models?.[family]?.[
          kind === 'models' ? 'checkpoints' : 'loras'
        ];
        defaults[family] = Array.isArray(configured) ? configured.slice() : [];
      });
      cache[kind] = {
        saved:defaults,
        draft:Object.fromEntries(FAMILIES[kind].map(f => [f,defaults[f].slice()])),
        inspection:new Map(),
        working:false,
      };
    }
    return cache[kind];
  }
  const modified = state => FAMILIES[state.kind || 'models'].some(family =>
    !same(normalized(state.draft[family]),state.saved[family]));

  function statusText(result) {
    if (!result) return 'Not checked. Select Check to inspect this host folder.';
    const label = {
      invalid:'Invalid or unreadable folder',
      empty:'Readable but empty',
      incompatible:'Possible wrong-family files',
      candidates:'Possible model/LoRA files',
      indexed:'Indexed and selectable',
      partial:'Inspection limit reached',
    }[result.status] || 'Folder status';
    const count = ' · ' + result.candidates + ' candidate(s)' +
      ' · ' + result.indexed + ' indexed' +
      (result.wrong_family ? ' · ' + result.wrong_family + ' wrong-family hint(s)' : '');
    return label + count + '. ' + result.message;
  }
  function build(container, kind, state) {
    state.kind = kind;
    currentView = {container,kind,state};
    container.replaceChildren();
    append(container,
      tags('p','first-run-note',
        kind==='models'
          ? 'Add checkpoint directories on the computer running Morphorum. SDXL and FLUX use separate folders; managed Z-Image is covered on the next page. A folder existing does not prove its models can load.'
          : 'LoRAs are optional. They customize a compatible base model but cannot replace one. Add family-specific LoRA folders or continue without any.'),
      tags('p','first-run-note','You can add multiple paths. Nothing is moved, downloaded, deleted or loaded into GPU memory. Checking does not change saved settings.')
    );
    FAMILIES[kind].forEach(family => {
      const group = tags('section','first-run-folder-group');
      const heading = tags('h3','',LABELS[family] + (kind==='models'?' checkpoints':' LoRAs'));
      const rows = tags('div','first-run-folder-rows');
      state.draft[family].forEach((raw,index) => {
        const row = tags('div','first-run-folder-row');
        const input = tags('input','first-run-folder-input');
        input.type='text';
        input.value=raw;
        input.setAttribute('aria-label',LABELS[family] + ' ' + kind + ' directory ' + (index+1));
        input.placeholder='Folder on the Morphorum host, not this browser';
        input.spellcheck=false;
        const check = tags('button','secondary-button compact','Check');
        check.type='button';
        const remove = tags('button','secondary-button compact','Remove');
        remove.type='button';
        const report = tags('p','first-run-folder-report');
        report.setAttribute('role','status');
        report.textContent=statusText(state.inspection.get(family+'|'+raw.trim()));
        input.addEventListener('input', () => {
          state.draft[family][index]=input.value;
          report.textContent='Not checked. Save changes explicitly before leaving this page.';
        });
        check.addEventListener('click', async () => {
          const path = input.value.trim();
          if (!path) {report.textContent='Enter a directory to check.';return;}
          check.disabled=true;
          report.textContent='Checking folder and known index entries…';
          try {
            const result = await api('/api/setup/folders/check',{
              method:'POST',body:JSON.stringify({
                family,kind:kind==='models'?'checkpoints':'loras',path,
              }),
            });
            state.inspection.set(family+'|'+path,result);
            report.textContent=statusText(result);
          } catch(error) {
            report.textContent='Check failed: '+error.message;
            toast('Folder check failed',error.message,'error');
          } finally {check.disabled=false;}
        });
        remove.addEventListener('click', () => {
          state.draft[family].splice(index,1);
          build(container,kind,state);
        });
        append(row,input,check,remove,report);
        append(rows,row);
      });
      const add = tags('button','secondary-button compact','+ Add path');
      add.type='button';
      add.disabled=state.draft[family].length>=20 || state.working;
      add.addEventListener('click',()=>{
        state.draft[family].push('');
        build(container,kind,state);
      });
      append(group,heading,rows,add);
      append(container,group);
    });
    const actions = tags('div','first-run-folder-actions');
    const save = tags('button','primary-button compact','Save Folders & Scan');
    save.type='button';
    save.disabled=state.working;
    const notice = tags('p','first-run-folder-report');
    notice.setAttribute('role','status');
    notice.textContent=kind==='models'
      ? 'No checkpoints? You can continue and decide about Z-Image-Turbo later. Render requires a usable base model.'
      : 'Optional. There is no need to configure a LoRA to create an animation.';
    save.addEventListener('click', async () => {
      if (state.working) return;
      const next=Object.fromEntries(FAMILIES[kind].map(f => [f,normalized(state.draft[f])]));
      const hasDuplicate=FAMILIES[kind].some(f =>
        next[f].length !== state.draft[f].filter(p=>p.trim()).length);
      if(hasDuplicate) {notice.textContent='Remove duplicate paths before saving.';return;}
      const replacing=FAMILIES[kind].some(f =>
        state.saved[f].some(old=>!next[f].includes(old)));
      if(replacing) {
        const permitted=window.MorphorumDialog?.confirm
          ? await window.MorphorumDialog.confirm({
              title:'Replace existing model folders?',
              message:'You are changing or removing saved folder paths. Model files remain untouched, but they will no longer be indexed from removed paths.',
              confirmText:'Update saved folders',cancelText:'Keep existing',variant:'warning',
            })
          : window.confirm('Update existing saved model/LoRA folder paths? Files will not be deleted.');
        if(!permitted) return;
      }
      state.working=true;
      save.disabled=true;
      notice.textContent='Saving only this page’s folder settings…';
      try {
        const kindKey=kind==='models'?'checkpoints':'loras';
        const result=await api('/api/setup/folders/save',{
          method:'POST',body:JSON.stringify({
            kind:kindKey,paths:next,expected:state.saved,
          }),
        });
        state.saved=Object.fromEntries(FAMILIES[kind].map(f=>[f,result.paths[f].slice()]));
        state.draft=Object.fromEntries(FAMILIES[kind].map(f=>[f,result.paths[f].slice()]));
        notice.textContent='Saved. Scanning configured model and LoRA libraries…';
        const scan=await api('/api/models/scan',{method:'POST',body:'{}'});
        const warning=scan.warnings?.length || 0;
        toast('Folder settings saved',scan.total+' external files indexed; '+warning+' scan warning(s).',
          warning?'warning':'success');
        notice.textContent='Saved and scanned: '+scan.total+' file(s). '+
          (warning ? warning+' folder warning(s). ' : '')+
          'Check individual paths to see counts for their family. Indexed files still require runtime compatibility.';
        window.MorphorumModels?.reload?.();
      } catch(error) {
        notice.textContent='Save/scan failed: '+error.message+
          '. If saving succeeded, your folders are preserved. Reopen this step to verify.';
        toast('Folder setup issue',error.message,'error');
      } finally {state.working=false;save.disabled=false;}
    });
    append(actions,save);
    append(container,actions,notice);
  }
  async function render(container,kind) {
    if(!FAMILIES[kind]) return;
    const generation=++renderGeneration;
    container.replaceChildren();
    append(container,tags('p','first-run-note','Loading existing host folder settings…'));
    try {
      const state=await getState(kind);
      if (generation !== renderGeneration) return;
      build(container,kind,state);
    } catch(error) {
      if (generation !== renderGeneration) return;
      container.replaceChildren();
      append(container,tags('p','first-run-folder-report','Could not load folder settings: '+error.message));
      toast('Setup folders unavailable',error.message,'error');
    }
  }
  function beforeNext(kind) {
    const state=cache[kind];
    if(!state) throw new Error('Folder settings are still loading. Try again.');
    if(state.working) throw new Error('Please allow the folder save/scan to finish.');
    if(modified(state)) throw new Error('There are unsaved folder edits. Use Save Folders & Scan, or remove/revert those edits before continuing.');
    return true;
  }
  async function welcome(container) {
    const details = tags('p','first-run-note','Checking host installation diagnostics…');
    append(container,details);
    try {
      const info = await api('/api/system');
      const disk = (info.checks || []).find(c => c.name === 'disk space');
      const cuda = (info.checks || []).find(c => c.name === 'CUDA');
      const devices = info.gpu?.devices || [];
      const gpu = devices.length ? devices.map(d => d.name).join(', ')
        : 'No NVIDIA GPU detected (generation may be unavailable or slower)';
      details.textContent = 'Morphorum ' + (info.version || 'unknown version') +
        ' · ' + (info.platform || 'Unknown platform') +
        ' · GPU: ' + gpu +
        ' · CUDA: ' + (cuda ? (cuda.ok ? 'available' : 'unavailable') : 'not reported') +
        ' · Storage: ' + (disk?.detail || 'not available');
      if(!info.ok) append(container,
        tags('p','first-run-folder-report',
          'Some host checks need attention. You can continue configuring folders; review system diagnostics before attempting generation.'));
    } catch(error) {
      details.textContent='Installation diagnostics unavailable: '+error.message+
        '. You can still configure model directories.';
    }
  }
  function reset(){delete cache.models;delete cache.loras;currentView=null;renderGeneration++;}
  window.MorphorumSetupFolders={render,beforeNext,reset,welcome};
})();
