(() => {
  'use strict';
  const STEPS = ['welcome','modes','models','loras','zimage','examples','finish'];
  const TITLES = [
    'Welcome to Morphorum', 'WebUI or Backend-Only?', 'Model folder setup',
    'Optional LoRA folders', 'Z-Image-Turbo download', 'Example animations', 'Review and finish',
  ];
  const qs = id => document.getElementById('first-run-' + id);
  let snapshot = null;
  let step = 'welcome';
  let manual = false;
  let busy = false;
  let previousFocus = null;

  function showError(message) {
    const el = qs('error');
    if (!el) return;
    el.hidden = !message;
    el.textContent = message || '';
  }
  function dismiss() {
    const overlay = qs('overlay');
    if (overlay) overlay.hidden = true;
    previousFocus?.focus?.();
  }
  function page() {
    const position = Math.max(0, STEPS.indexOf(step));
    qs('title').textContent = TITLES[position];
    qs('progress').textContent = 'Step ' + (position + 1) + ' of 7 · MS6.1 onboarding entry';
    const content = qs('description');
    content.replaceChildren();
    const paragraph = message => {
      const p = document.createElement('p');
      p.textContent = message;
      content.appendChild(p);
    };
    const heading = message => {
      const h = document.createElement('h3');
      h.textContent = message;
      content.appendChild(h);
    };
    if (step === 'welcome') {
      paragraph('Morphorum creates AI images and camera-driven animations on your computer. This setup will help you configure model folders, optional LoRAs, and a small starter project.');
      paragraph('Models are not included in a fresh installation. Downloads require your permission; opening this wizard will never download weights, generate frames or alter existing projects.');
      paragraph('This milestone establishes the setup entry and resumable progress. Directory setup, model downloads and example creation will follow in MS6.2–MS6.4.');
    } else if (step === 'modes') {
      heading('WebUI: the default');
      paragraph('Morphorum runs a local Python backend and opens a browser interface, normally at http://127.0.0.1:7865. Closing a browser tab does not automatically stop a running render.');
      heading('Backend-only: advanced integration');
      paragraph('An authenticated API for external clients such as Morphorum Studio, normally on port 7866. It does not provide this browser wizard. Changing modes requires stopping and restarting Morphorum, for example with run.bat --backend-only or ./run.sh --backend-only.');
      paragraph('Stay in the normal WebUI to finish the setup steps.');
    } else {
      heading('This page is scheduled for the next MS6 implementation pass');
      paragraph('Your progress is saved on the Morphorum host, not in browser storage. Model and LoRA folder verification begins in MS6.2, followed by the optional Z-Image download and two 512 × 512 dolly examples.');
      paragraph('Close to resume here later, or Skip for now to return to the normal WebUI. Your existing settings and projects remain untouched.');
    }
    qs('back').disabled = position === 0;
    qs('next').disabled = position >= 2;
    qs('next').textContent = position === 1 ? 'Continue to Model Setup' : 'Next';
    showError('');
  }
  async function fetchStatus() {
    const response = await fetch('/api/setup/status', {cache:'no-store'});
    if (!response.ok) throw new Error('Cannot inspect installation setup state.');
    return response.json();
  }
  async function action(kind, destination) {
    if (busy || !snapshot) return;
    busy = true;
    for (const name of ['next','back','skip']) qs(name).disabled = true;
    try {
      const response = await fetch('/api/setup/progress', {
        method:'POST',
        headers:{'Content-Type':'application/json','X-Morphorum-Setup':'1'},
        body:JSON.stringify({
          action:kind, step:destination, revision:snapshot.revision,
          manual:manual || snapshot.forced_for_launch,
        }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(String(data.detail || 'Setup update failed.'));
      snapshot = data;
      if (kind === 'skip') {dismiss(); return;}
      step = destination;
      page();
    } catch (error) {
      showError(error.message + ' Reload setup to refresh its server state.');
    } finally {
      busy = false;
      // Restore the correct step-specific disabled states.
      if (!qs('overlay').hidden) {
        qs('skip').disabled = false;
        qs('back').disabled = STEPS.indexOf(step) === 0;
        qs('next').disabled = STEPS.indexOf(step) >= 2;
      }
    }
  }
  async function open({reopen=false}={}) {
    if (busy) return;
    try {
      const latest = await fetchStatus();
      if (latest.status === 'error') {
        window.MorphorumToast?.('Setup state needs attention', latest.warning, 'warning', 7000);
        return;
      }
      if (!reopen && !latest.show_wizard) return;
      snapshot = latest;
      manual = reopen || latest.forced_for_launch;
      step = reopen && ['completed','skipped','legacy'].includes(latest.status)
        ? 'welcome' : STEPS.includes(latest.step) ? latest.step : 'welcome';
      previousFocus = document.activeElement;
      qs('overlay').hidden = false;
      page();
      qs('next').focus();
    } catch (error) {
      window.MorphorumToast?.('First-run setup unavailable', error.message, 'warning', 6500);
    }
  }
  function bind() {
    qs('next')?.addEventListener('click', () => {
      const i=STEPS.indexOf(step);
      if (i < 2) void action('advance',STEPS[i+1]);
    });
    qs('back')?.addEventListener('click', () => {
      const i=STEPS.indexOf(step);
      if (i > 0) void action('advance',STEPS[i-1]);
    });
    qs('skip')?.addEventListener('click', () => void action('skip',null));
    qs('close')?.addEventListener('click',dismiss);
    document.getElementById('reopen-first-run-setup')?.addEventListener(
      'click', () => void open({reopen:true}));
    qs('overlay')?.addEventListener('keydown', event => {
      if (event.key === 'Escape') {
        event.preventDefault();
        dismiss();
      }
      // Keep focus inside the modal on Tab, including on narrow layouts.
      if (event.key !== 'Tab') return;
      const visible = ['close','back','skip','next'].map(qs).filter(e=>!e.disabled);
      const i=visible.indexOf(document.activeElement);
      if(event.shiftKey && i===0) {event.preventDefault();visible.at(-1)?.focus();}
      else if(!event.shiftKey && i===visible.length-1) {event.preventDefault();visible[0]?.focus();}
    });
    void open();
  }
  window.MorphorumFirstRunSetup = {open};
  window.addEventListener('DOMContentLoaded',bind);
})();