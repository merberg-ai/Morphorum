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
  let exampleReady = false;
  let previousFocus = null;

  function showError(message) {
    const el = qs('error');
    if (!el) return;
    el.hidden = !message;
    el.textContent = message || '';
  }
  function dismiss() {
    const overlay = qs('overlay');
    if (busy) return;
    if (overlay) overlay.hidden = true;
    window.MorphorumSetupZImage?.leave();
    window.MorphorumSetupExamples?.leave();
    previousFocus?.focus?.();
  }
  function page() {
    const position = Math.max(0, STEPS.indexOf(step));
    qs('title').textContent = TITLES[position];
    qs('progress').textContent = 'Step ' + (position + 1) + ' of 7 · First-run configuration';
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
      paragraph('Choose checkpoint folders and optional LoRAs, install Z-Image-Turbo if you wish, then open a small 3D starter animation. The two example projects take only 4 seconds each and are not rendered automatically.');
      void window.MorphorumSetupFolders?.welcome(content);
    } else if (step === 'modes') {
      heading('WebUI: the default');
      paragraph('Morphorum runs a local Python backend and opens a browser interface, normally at http://127.0.0.1:7865. Closing a browser tab does not automatically stop a running render.');
      heading('Backend-only: advanced integration');
      paragraph('An authenticated API for external clients such as Morphorum Studio, normally on port 7866. It does not provide this browser wizard. Changing modes requires stopping and restarting Morphorum, for example with run.bat --backend-only or ./run.sh --backend-only.');
      paragraph('Stay in the normal WebUI to finish the setup steps.');
    } else if (step === 'models' || step === 'loras') {
      void window.MorphorumSetupFolders?.render(content,step);
    } else if (step === 'zimage') {
      window.MorphorumSetupZImage?.show(content,()=>void action('advance','examples'));
    } else if (step === 'examples') {
      exampleReady = false;
      void window.MorphorumSetupExamples?.showExamples(content,snapshot,{
        onReady:ready=>{
          if(step==='examples' && !qs('overlay').hidden) {
            exampleReady=ready;
            qs('next').disabled=busy || !ready;
          }
        },
      });
    } else if (step === 'finish') {
      void window.MorphorumSetupExamples?.showFinish(content,snapshot,{
        reserved:(revision,id)=>{snapshot.revision=revision;snapshot.example_project_id=id;},
        complete:extras=>action('complete','finish',extras),
        openEditor:id=>window.MorphorumAnimation?.openSavedProjectFromSetup?.(id) ?? false,
        toast:(...args)=>window.MorphorumToast?.(...args),
        manual,
      });
    }
    qs('back').disabled = position === 0;
    qs('next').disabled = position >= 6 || step==='examples';
    qs('next').textContent = position === 1 ? 'Continue to Model Setup' : position === 2 ? 'Optional LoRA Folders' : position === 3 ? 'Continue to Z-Image' : position === 4 ? 'Continue Without Waiting' : position === 5 ? 'Review & Finish' : 'Next';
    showError('');
  }
  async function fetchStatus() {
    const response = await fetch('/api/setup/status', {cache:'no-store'});
    if (!response.ok) throw new Error('Cannot inspect installation setup state.');
    return response.json();
  }
  async function action(kind, destination, extras = {}) {
    if (busy || !snapshot) return;
    busy = true;
    for (const name of ['next','back','skip','close']) qs(name).disabled = true;
    try {
      const response = await fetch('/api/setup/progress', {
        method:'POST',
        headers:{'Content-Type':'application/json','X-Morphorum-Setup':'1'},
        body:JSON.stringify({
          action:kind, step:destination, revision:snapshot.revision,
          manual:manual || snapshot.forced_for_launch,
          ...extras,
        }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(String(data.detail || 'Setup update failed.'));
      snapshot = data;
      if (kind === 'skip' || kind === 'complete') {
        dismiss();
        if(kind==='complete') window.MorphorumToast?.('Setup complete','Morphorum is configured. Your projects and settings are saved.','success');
        return;
      }
      if (step === 'zimage') window.MorphorumSetupZImage?.leave();
      if (step === 'examples' || step === 'finish') window.MorphorumSetupExamples?.leave();
      step = destination;
      page();
    } catch (error) {
      showError(error.message + ' Reload setup to refresh its server state.');
    } finally {
      busy = false;
      // Restore the correct step-specific disabled states.
      qs('close').disabled = false;
      if (!qs('overlay').hidden) {
        qs('skip').disabled = false;
        qs('back').disabled = STEPS.indexOf(step) === 0;
        qs('next').disabled = STEPS.indexOf(step) >= 6 || (step==='examples' && !exampleReady);
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
      if (latest.provenance === 'fresh_installer' && !latest.ready) {
        window.MorphorumToast?.('Installation unfinished',
          'Finish or repair Morphorum before continuing first-run setup.', 'warning', 7000);
        return;
      }
      if (!reopen && !latest.show_wizard) return;
      snapshot = latest;
      window.MorphorumSetupFolders?.reset();
      window.MorphorumSetupZImage?.leave();
      window.MorphorumSetupExamples?.leave();
      manual = reopen || latest.forced_for_launch;
      step = reopen && ['completed','skipped','legacy'].includes(latest.status)
        ? 'welcome' : STEPS.includes(latest.step) ? latest.step : 'welcome';
      previousFocus = document.activeElement;
      qs('overlay').hidden = false;
      page();
      (qs('next').disabled ? qs('close') : qs('next')).focus();
    } catch (error) {
      window.MorphorumToast?.('First-run setup unavailable', error.message, 'warning', 6500);
    }
  }
  function bind() {
    qs('next')?.addEventListener('click', () => {
      const i=STEPS.indexOf(step);
      if (i < 6) {
        try {
          if (i === 2 || i === 3) window.MorphorumSetupFolders?.beforeNext(STEPS[i]);
          const extras=i===5?window.MorphorumSetupExamples?.selection():{};
          void action('advance',STEPS[i+1],extras);
        } catch (error) {showError(error.message);}
      }
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
      const overlay=qs('overlay');
      const candidates=overlay.querySelectorAll?.(
        'button:not([disabled]), a[href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
      );
      const visible=candidates ? [...candidates].filter(e=>
        !e.disabled && !e.hidden && !e.closest?.('[hidden]') &&
        (typeof e.getClientRects!=='function' || e.getClientRects().length>0)
      ) : ['close','back','skip','next'].map(qs).filter(e=>!e.disabled);
      const i=visible.indexOf(document.activeElement);
      if(!visible.length) return;
      if(event.shiftKey && i===0) {event.preventDefault();visible.at(-1)?.focus();}
      else if(!event.shiftKey && i===visible.length-1) {event.preventDefault();visible[0]?.focus();}
    });
    void open();
  }
  window.MorphorumFirstRunSetup = {open,
    goto:destination=>STEPS.includes(destination)?action('advance',destination):undefined,
  };
  window.addEventListener('DOMContentLoaded',bind);
})();