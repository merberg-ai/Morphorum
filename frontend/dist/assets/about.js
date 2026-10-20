(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  let latestCheck = null;
  let latestStatus = null;
  let busy = false;
  let polling = null;

  async function request(path, options = {}) {
    const response = await fetch(path, {
      ...options,
      headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    });
    const body = await response.json();
    if (!response.ok) throw new Error(body.detail || response.statusText);
    return body;
  }
  function text(id, value) { if ($(id)) $(id).textContent = String(value ?? 'Unavailable'); }
  function setMessage(message) { text('about-update-message', message); }
  function setBusy(value) {
    busy = value;
    $('about-check-update').disabled = value || latestStatus?.update?.running || !latestStatus?.supported;
    refreshApply();
  }
  function refreshApply() {
    $('about-apply-update').disabled = busy || !latestStatus?.host_local ||
      !latestCheck?.can_apply || latestStatus?.update?.running ||
      latestStatus?.branch !== latestCheck?.branch ||
      latestStatus?.head !== latestCheck?.head;
  }
  function commandFor(platform) { return platform === 'windows' ? '.\\update.bat' : './update.sh'; }
  function showStatus(status) {
    latestStatus = status;
    text('about-branch', status.branch || 'Not a Git checkout');
    text('about-commit', status.head ? status.head.slice(0, 12) : 'Unavailable');
    text('about-update-command', commandFor(status.platform));
    if (status.check?.branch === status.branch && status.check?.head === status.head) {
      latestCheck = status.check;
    } else {
      latestCheck = null;
    }
    if (!status.supported) {
      text('about-update-state', 'Unavailable');
      setMessage(status.message || 'Updates require a Git checkout.');
    } else if (status.update?.running) {
      text('about-update-state', 'Installing…');
      setMessage('The existing updater is installing the current branch. Keep this page open; restart Morphorum when it finishes.');
    } else if (status.update?.restart_required) {
      text('about-update-state', 'Restart required');
      setMessage('Update completed successfully. Stop and restart Morphorum to load the new version.');
    } else if (status.update?.exit_code != null) {
      text('about-update-state', 'Update failed');
      setMessage('The updater failed or rolled back. Review the log and follow the recovery instructions.');
    } else if (latestCheck) {
      showCheck(latestCheck);
    } else {
      text('about-update-state', 'Not checked');
      setMessage('Only your currently checked-out branch is eligible. No automatic branch switching.');
    }
    const tail = status.update?.log_tail || '';
    const log = $('about-update-log');
    log.hidden = !tail;
    log.textContent = tail;
    if (!status.host_local) {
      $('about-update-safety').textContent =
        'Read-only update checks are available from this browser. Applying an update is restricted to a browser on the Morphorum host, because LAN WebUI access is unauthenticated. Run the manual update command on the host after stopping Morphorum.';
    }
    setBusy(busy);
    if (status.update?.running) schedulePoll();
  }
  function showCheck(check) {
    if (!check) return;
    latestCheck = check;
    const branch = check.branch;
    if (check.dirty) {
      text('about-update-state', 'Local changes');
      setMessage('Tracked local files have changes. Commit or revert them before updating ' + branch + '.');
    } else if (check.state === 'current') {
      text('about-update-state', 'Up to date');
      setMessage(branch + ' is already at the newest fetched commit.');
    } else if (check.state === 'behind') {
      text('about-update-state', check.behind + ' commit(s) available');
      setMessage('origin/' + branch + ' is ' + check.behind + ' commit(s) ahead. Update is fast-forward-only.');
    } else {
      text('about-update-state', 'Manual Git action needed');
      setMessage('Your local ' + branch + ' is ahead of or diverged from origin/' + branch +
        '. Automatic update is disabled to protect commits.');
    }
    refreshApply();
  }
  function schedulePoll() {
    if (polling) return;
    polling = setTimeout(async () => {
      polling = null;
      try { showStatus(await request('/api/about/git')); }
      catch (error) { setMessage('Update status unavailable: ' + error.message); }
    }, 1800);
  }
  async function status() {
    try {
      const [health, git] = await Promise.all([
        request('/api/health'), request('/api/about/git'),
      ]);
      text('about-version', health.version || 'Unknown');
      showStatus(git);
    } catch (error) {
      text('about-update-state', 'Unavailable');
      setMessage('Cannot read Git status: ' + error.message);
    }
  }
  async function check() {
    setBusy(true);
    try {
      const result = await request('/api/about/check', {method:'POST',body:'{}'});
      const next = await request('/api/about/git');
      showStatus(next);
      showCheck(result.check);
      window.MorphorumToast?.('Branch check complete',
        'Checked origin/' + result.check.branch + ' only.', 'success');
    } catch (error) {
      latestCheck = null;
      text('about-update-state', 'Check failed');
      setMessage(error.message);
      window.MorphorumToast?.('Update check failed', error.message, 'warning');
    } finally { setBusy(false); }
  }
  async function apply() {
    if (busy || !latestCheck?.can_apply || !latestStatus?.host_local) return;
    const selected = latestCheck;
    const confirmed = await window.MorphorumDialog?.confirm({
      title:'Update Morphorum?',
      message:'Update only branch ' + selected.branch + ' (' + selected.behind +
        ' newer commit(s))? The existing updater backs up/rolls back on failure. ' +
        'Do not close Morphorum during an active render. Restart the server when complete.',
      variant:'warning',confirmText:'Update current branch',
    });
    if (!confirmed) return;
    setBusy(true);
    try {
      const update = await request('/api/about/update', {
        method:'POST',
        body:JSON.stringify({
          branch:selected.branch,head:selected.head,remote_head:selected.remote_head,
        }),
      });
      latestCheck = null;
      text('about-update-state','Installing…');
      setMessage('Update started for ' + update.update.branch +
        '. Follow the log and restart Morphorum after completion.');
      showStatus(await request('/api/about/git'));
    } catch (error) {
      text('about-update-state','Update not started');
      setMessage(error.message);
      window.MorphorumToast?.('Update not started',error.message,'error');
    } finally { setBusy(false); }
  }
  function bind() {
    const logo = $('about-logo');
    const placeholder = $('about-logo-fallback');
    if (logo) {
      logo.addEventListener('load', () => {
        logo.hidden = false;
        if (placeholder) placeholder.hidden = true;
      });
      logo.addEventListener('error', () => { logo.hidden = true; });
      if (logo.complete && logo.naturalWidth > 0) {
        logo.hidden = false;
        if (placeholder) placeholder.hidden = true;
      }
    }
    $('about-check-update')?.addEventListener('click', check);
    $('about-apply-update')?.addEventListener('click', apply);
    $('about-copy-command')?.addEventListener('click', async () => {
      try {
        await window.MorphorumClipboard.writeText($('about-update-command').textContent);
        window.MorphorumToast?.('Copied', 'Current-branch update command copied.', 'success');
      } catch (error) {
        window.MorphorumToast?.('Copy failed', error.message, 'warning');
      }
    });
  }
  let initialized = false;
  window.MorphorumAbout = {
    activate: () => { if (!initialized) { initialized = true; bind(); } void status(); },
  };
})();
