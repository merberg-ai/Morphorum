(() => {
  'use strict';
  // MS6.3: managed download is never started by mounting, polling or navigating.
  const MODEL_ID = 'zimage-turbo';
  const STATUS_URL = '/api/managed-models/' + MODEL_ID;
  const DOWNLOAD_URL = STATUS_URL + '/download';
  const POLL_MS = 1400;
  let lifetime = 0;
  let timer = null;
  let current = null;
  let working = false;
  let lastInstalled = false;

  function el(tag, className, value) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (value !== undefined) node.textContent = value;
    return node;
  }
  const size = bytes => {
    if (bytes === null || bytes === undefined || !Number.isFinite(Number(bytes))) return 'unknown';
    let n = Math.max(0, Number(bytes));
    for (const unit of ['B','KiB','MiB','GiB','TiB']) {
      if (n < 1024 || unit === 'TiB') return n.toFixed(unit === 'B' ? 0 : 1) + ' ' + unit;
      n /= 1024;
    }
    return 'unknown';
  };
  const notify = (title, message, type='info') =>
    window.MorphorumToast?.(title, message, type, 6500);
  const active = token => token === lifetime;
  function leave() {
    lifetime++;
    if (timer !== null) window.clearTimeout(timer);
    timer = null;
    current = null;
    working = false;
    lastInstalled = false;
  }
  async function api(url, options = {}) {
    const result = await fetch(url, {cache:'no-store', ...options});
    const body = await result.json();
    if (!result.ok) throw new Error(String(body.detail || result.statusText || 'Request failed'));
    return body;
  }
  function show(container, next) {
    leave();
    const token = lifetime;
    const description = el('p','first-run-note',
      'Z-Image-Turbo is an optional, managed Diffusers base model for text-to-image and image-to-image. ' +
      'It is not an SDXL checkpoint folder or a LoRA. Downloading is optional, and no model is loaded into GPU memory by this screen.');
    const detail = el('div','first-run-zimage-meta');
    const name = el('h3','', 'Z-Image-Turbo');
    const info = el('p','first-run-note','Reading the managed model catalog…');
    const location = el('p','first-run-zimage-path');
    const space = el('p','first-run-note');
    const state = el('p','first-run-zimage-state','Checking existing model status…');
    state.setAttribute('role','status');
    state.setAttribute('aria-live','polite');
    const progressWrap = el('div','first-run-zimage-progress');
    const progressTrack = el('div','first-run-zimage-progress-track');
    progressTrack.setAttribute('role','progressbar');
    progressTrack.setAttribute('aria-label','Z-Image-Turbo download progress');
    progressTrack.setAttribute('aria-valuemin','0');
    progressTrack.setAttribute('aria-valuemax','100');
    progressTrack.setAttribute('aria-valuenow','0');
    const fill = el('span','first-run-zimage-progress-fill');
    progressTrack.appendChild(fill);
    const progressLabel = el('p','first-run-note','No verified download yet.');
    progressWrap.append(progressTrack, progressLabel);
    const issue = el('p','first-run-zimage-error');
    issue.setAttribute('role','alert');
    issue.hidden = true;
    const actions = el('div','first-run-zimage-actions');
    const primary = el('button','primary-button compact','Download Now');
    primary.type = 'button';
    primary.disabled = true;
    const later = el('button','secondary-button compact','Not Now · Continue');
    later.type = 'button';
    later.addEventListener('click',()=>{
      if (working) return;
      next();
    });
    const refresh = el('button','secondary-button compact','Refresh Status');
    refresh.type='button';
    refresh.addEventListener('click',()=>void reload(token));
    actions.append(primary,later,refresh);
    detail.append(name,info,location,space,state,progressWrap,issue,actions);
    container.append(description,detail);
    const mount = {token, primary,info,location,space,state,progressTrack,fill,
      progressLabel,issue,refresh,later,next};

    function update(model) {
      if(!active(token)) return;
      current=model;
      name.textContent=model.name || 'Z-Image-Turbo';
      info.textContent=(model.description || 'Managed image model')+
        ' · ' + (model.license || 'License unspecified') +
        ' · Expected download approximately ' + size(model.advertised_size_bytes || model.expected_bytes) +
        ' (estimate, not a guaranteed exact file size).';
      location.textContent='Destination on Morphorum host: ' + (model.destination || 'unknown');
      const installed=model.installed===true && model.status==='installed';
      const ongoing=['checking','downloading'].includes(model.status);
      const interrupted=['interrupted','partial'].includes(model.status);
      const insufficient=model.space_sufficient===false && !installed;
      const free=model.available_bytes;
      space.textContent='Available on destination volume: '+size(free)+
        ' · Approximate remaining: '+size(model.estimated_remaining_bytes)+
        ' · Recommended free space including reserve: '+size(model.required_free_bytes)+
        (insufficient ? '. Insufficient space: free up storage before starting or resuming.' : '');
      const labels={
        not_installed:'Not installed. No download is running.',
        checking:'Preparing download: checking the official model snapshot and destination.',
        downloading:'Downloading. You may leave this page; progress is tracked by Morphorum on the host.',
        failed:'Download failed. Partial files are not a usable model. Retry when the problem is resolved.',
        interrupted:'Previous download was interrupted. Existing partial files may be reused when resumed.',
        partial:'An incomplete package exists. Resume to download and verify remaining files.',
        installed:'Verified installed and indexed. Ready to select; this wizard will not load it automatically.',
      };
      state.textContent=labels[model.status] || 'Unrecognized download status: '+String(model.status);
      const pct=installed?100:Math.max(0,Math.min(99.9,Number(model.progress_percent)||0));
      progressTrack.setAttribute('aria-valuenow',pct.toFixed(1));
      fill.style.width=pct.toFixed(1)+'%';
      progressLabel.textContent=(installed?'100% verified':pct.toFixed(1)+'% estimated')+
        ' · '+size(model.downloaded_bytes)+' of '+size(model.expected_bytes)+
        ' · Partial size and progress do not prove model integrity.';
      issue.hidden=!model.error && !insufficient;
      issue.textContent=model.error || (insufficient?'Insufficient disk space at the selected destination.':'');
      if(installed) primary.textContent='Use Existing Model';
      else if(model.status==='failed') primary.textContent='Retry Download';
      else if(interrupted) primary.textContent='Resume / Repair Download';
      else if(ongoing) primary.textContent='Download In Progress';
      else primary.textContent='Download Now';
      primary.disabled=working || ongoing || insufficient;
      refresh.disabled=working;
      later.disabled=working;
      if (installed && !lastInstalled) {
        // Read existing verified index into model selectors; no GPU load.
        window.MorphorumModels?.reload?.();
        window.MorphorumModels?.reloadManaged?.();
      }
      lastInstalled=installed;
    }

    async function reload(requestToken) {
      if(!active(requestToken)) return;
      try {
        const model=await api(STATUS_URL);
        if(!active(requestToken)) return;
        update(model);
        issue.hidden=!model.error && model.space_sufficient!==false;
        if(['checking','downloading'].includes(model.status)) {
          if(timer!==null) window.clearTimeout(timer);
          timer=window.setTimeout(()=>{timer=null;void reload(requestToken);},POLL_MS);
        }
      } catch(error) {
        if(!active(requestToken)) return;
        issue.hidden=false;
        issue.textContent='Cannot fetch current download status: '+error.message+
          '. Use Refresh Status to retry.';
        primary.disabled=true;
        notify('Managed model status unavailable',error.message,'warning');
      }
    }

    primary.addEventListener('click',async()=>{
      if(working || !current) return;
      working=true;
      primary.disabled=true;
      later.disabled=true;
      try {
        // Recheck before confirmation to account for progress in another tab.
        const live=await api(STATUS_URL);
        if(!active(token)) return;
        update(live);
        if(live.installed===true && live.status==='installed') {
          const selected=await window.MorphorumModels?.selectExisting?.(live.index_id);
          if(!active(token)) return;
          if(selected) notify('Existing model selected',
            'Z-Image-Turbo is selected in Image Generation. No weights were loaded by setup.','success');
          else notify('Model index not ready',
            'The package is installed, but it could not yet be selected. Try Refresh Status.','warning');
          return;
        }
        if(['checking','downloading'].includes(live.status) || live.space_sufficient===false) return;
        const confirm=window.MorphorumDialog?.confirm;
        if(typeof confirm!=='function') {
          notify('Confirmation unavailable','Download cancelled: this browser cannot show the confirmation dialog.','warning');
          return;
        }
        const accepted=await confirm({
          title:'Download Z-Image-Turbo?',
          message:'Download the official '+(live.name||'Z-Image-Turbo')+' package ('+
            (live.license||'license not reported')+') into '+(live.destination||'the configured managed-model directory')+
            '. Advertised download: approximately '+size(live.advertised_size_bytes)+
            '. Destination free: '+size(live.available_bytes)+
            '. The actual size may differ. Downloading can take significant time and disk space. Continue?',
          confirmText:live.resumable?'Resume Download':'Download Now',
          cancelText:'Not Now',
          variant:'warning',
        });
        if(!active(token) || !accepted) return;
        const started=await api(DOWNLOAD_URL,{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
        if(!active(token)) return;
        update(started);
        notify('Managed download requested',
          'Downloading on the Morphorum host. You can continue setup while it runs.','info');
      } catch(error) {
        if(!active(token)) return;
        issue.hidden=false;
        issue.textContent='Could not start or select model: '+error.message;
        notify('Z-Image setup failed',error.message,'error');
      } finally {
        if(active(token)) {
          working=false;
          later.disabled=false;
          void reload(token);
        }
      }
    });
    void reload(token);
    return mount;
  }
  window.MorphorumSetupZImage={show,leave};
})();
