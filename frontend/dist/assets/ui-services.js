(() => {
  'use strict';
  // Centralized, browser-only UI services. No server calls or HTML interpolation.
  function clipboard(text) {
    const value = String(text ?? '');
    if (navigator.clipboard?.writeText && window.isSecureContext) {
      return navigator.clipboard.writeText(value);
    }
    const previous = document.activeElement;
    const input = document.createElement('textarea');
    input.value = value;
    input.readOnly = true;
    input.setAttribute('aria-hidden', 'true');
    Object.assign(input.style, { position: 'fixed', left: '0', top: '0', width: '1px', height: '1px', opacity: '0' });
    document.body.appendChild(input);
    let succeeded = false;
    try {
      input.focus();
      input.select();
      input.setSelectionRange(0, value.length);
      succeeded = Boolean(document.execCommand?.('copy'));
    } finally {
      input.remove();
      if (previous?.isConnected && previous.focus) previous.focus({ preventScroll: true });
    }
    return succeeded ? Promise.resolve() : Promise.reject(new Error('Clipboard access was blocked. Select and copy the text manually.'));
  }
  window.MorphorumClipboard = { writeText: clipboard };


  // P4.1: a shared, non-blocking operation lifecycle. Track work by key and
  // request token: old network responses cannot overwrite a newer operation.
  function createOperationTracker(publish) {
    const active = new Map();
    const settledResults = new Map();
    const dismissed = new Set();
    let sequence = 0;
    let presentationOrder = 0;
    const priority = tone => ({error: 4, warning: 3, busy: 2, success: 1})[tone] || 0;
    let current = null;
    function select() {
      const entries = [...active.values(), ...settledResults.values()]
        .filter(entry => !dismissed.has(entry.token));
      entries.sort((a, b) => priority(b.tone) - priority(a.tone) || b.order - a.order);
      return entries[0] || null;
    }
    function visible() {
      current = select();
      publish(current ? { ...current } : null);
    }
    function remember(entry) {
      settledResults.delete(entry.key);
      settledResults.set(entry.key, entry);
      while (settledResults.size > 12) {
        const oldest = settledResults.keys().next().value;
        dismissed.delete(settledResults.get(oldest).token);
        settledResults.delete(oldest);
      }
    }
    return {
      begin(key, title, message = '', view = '') {
        const token = ++sequence;
        active.delete(key);
        settledResults.delete(key); // Explicit retry retires that key's old error.
        active.set(key, {key, token, title, message, view, tone: 'busy', progress: null,
          order: ++presentationOrder});
        visible();
        return token;
      },
      update(key, token, options = {}) {
        const existing = active.get(key);
        if (!existing || existing.token !== token) return false;
        active.set(key, {...existing, ...options, tone: 'busy', key, token});
        visible();
        return true;
      },
      finish(key, token, options = {}) {
        const existing = active.get(key);
        if (!existing || existing.token !== token) return false;
        active.delete(key);
        remember({...existing, ...options, key, token, order: ++presentationOrder,
          tone: ['success', 'warning', 'error'].includes(options.tone)
            ? options.tone : 'success', progress: null});
        dismissed.delete(token); // A dismissed progress notice can still report the result.
        visible();
        return true;
      },
      dismiss() {
        if (current) {
          dismissed.add(current.token);
          if (current.tone !== 'busy') settledResults.delete(current.key);
          else {
            // Do not resurface an unrelated, already-finished success when
            // the user explicitly dismisses the current progress notice.
            for (const [key, entry] of settledResults)
              if (entry.tone === 'success') settledResults.delete(key);
          }
        }
        visible(); // Only the notice is dismissed, never the backend work.
      },
      retire(key) {
        // Forget a stale job notice (e.g. project switched), not the job itself.
        const running = active.get(key);
        const settled = settledResults.get(key);
        if (running) dismissed.delete(running.token);
        if (settled) dismissed.delete(settled.token);
        active.delete(key);
        settledResults.delete(key);
        visible();
      },
      snapshot() {
        const results = [...settledResults.values()].map(value => ({...value}));
        return { active: [...active.values()].map(value => ({...value})),
          settled: results.at(-1) || null, results, visible: current && {...current} };
      },
    };
  }

  // P4.3: One actionable warning per contiguous polling outage. Recovery is
  // distinct from job completion; retries continue in the existing job monitor.
  function createPollHealth(ops) {
    const failures = new Map();
    return {
      failed(key, label, view = '') {
        const state = failures.get(key) || { count: 0, reported: false };
        state.count += 1;
        if (state.count === 3) {
          const operation = ops.begin('poll:' + key, label + ' updates interrupted',
            'Morphorum cannot confirm the current job status. It may still be running. ' +
            'Check your backend connection and Console before resubmitting.', view);
          ops.finish('poll:' + key, operation, {
            tone: 'warning', title: label + ' updates interrupted',
            message: 'Live status checks failed repeatedly. The job may still be running; ' +
              'check your connection and Console before attempting another submission.', view,
          });
          state.reported = true;
          console.warn('[Morphorum] Polling interrupted for ' + label + '; retrying status checks.');
          window.MorphorumClientDiagnostics?.record('warning',
            label + ' polling interrupted; backend job status is not confirmed.');
        }
        failures.set(key, state);
      },
      recovered(key) {
        const state = failures.get(key);
        if (!state) return;
        failures.delete(key);
        if (state.reported) {
          const operation = ops.begin('poll:' + key, 'Connection restored',
            'Live job status is available again.', '');
          ops.finish('poll:' + key, operation, {
            tone: 'success', title: 'Live status restored',
            message: 'Morphorum can check the job again. Review its current status before taking action.',
          });
          window.MorphorumClientDiagnostics?.record('info',
            'Polling resumed for ' + key + '; status is available again.');
        }
      },
      reset(key) {
        failures.delete(key);
        ops.retire('poll:' + key);
      },
      snapshot(key) { return failures.get(key) ? {...failures.get(key)} : null; },
    };
  }

  function renderOperationFeedback(entry) {
    if (typeof document === 'undefined') return;
    const panel = document.getElementById('operation-feedback');
    if (!panel) return;
    panel.hidden = !entry;
    if (!entry) return;
    panel.dataset.tone = entry.tone;
    panel.setAttribute('aria-busy', String(entry.tone === 'busy'));
    // A separate live region announces transitions, not every progress tick.
    const announcement = document.getElementById('operation-feedback-announcement');
    if (announcement) {
      const signature = [entry.token, entry.tone, entry.title].join(':');
      if (announcement.dataset.signature !== signature) {
        announcement.dataset.signature = signature;
        announcement.setAttribute('role', entry.tone === 'error' ? 'alert' : 'status');
        announcement.setAttribute('aria-live', entry.tone === 'error' ? 'assertive' : 'polite');
        announcement.textContent = String(entry.title || 'Operation update') +
          '. ' + String(entry.message || '');
      }
    }
    document.getElementById('operation-feedback-title').textContent =
      String(entry.title || 'Operation status');
    document.getElementById('operation-feedback-message').textContent =
      String(entry.message || '');
    const progress = document.getElementById('operation-feedback-progress');
    const fill = document.getElementById('operation-feedback-fill');
    const percent = Number(entry.progress);
    const determinate = entry.progress != null && Number.isFinite(percent);
    progress.hidden = entry.tone !== 'busy';
    progress.classList.toggle('indeterminate', !determinate);
    if (determinate) {
      const bounded = Math.max(0, Math.min(100, percent));
      fill.style.width = bounded + '%';
      progress.setAttribute('aria-valuenow', String(Math.round(bounded)));
    } else {
      fill.style.width = '';
      progress.removeAttribute('aria-valuenow');
    }
    const action = document.getElementById('operation-feedback-open');
    action.hidden = !['settings','models','image','animation'].includes(entry.view);
    if (!action.hidden) {
      action.dataset.view = entry.view;
      action.textContent = entry.view === 'animation'
        ? 'Open Motion Lab' : 'Open ' + entry.view[0].toUpperCase() + entry.view.slice(1);
    }
  }

  const operations = createOperationTracker(renderOperationFeedback);
  window.MorphorumOperations = operations;
  window.MorphorumPollHealth = createPollHealth(operations);
  if (typeof document !== 'undefined' && typeof document.addEventListener === 'function') {
    document.addEventListener('DOMContentLoaded', () => {
      document.getElementById('operation-feedback-dismiss')?.addEventListener('click',
        () => operations.dismiss());
      document.getElementById('operation-feedback-open')?.addEventListener('click', event => {
        const view = event.currentTarget.dataset.view;
        if (!['settings','models','image','animation'].includes(view)) return;
        document.querySelector('.nav-button[data-view="' + view + '"]')?.click();
      });
    });
  }

  const queue = [];
  let active = null;
  const typeDefault = type => type === 'prompt' ? null : false;
  function ensureHost() {
    let dialog = document.getElementById('morphorum-shared-dialog');
    if (dialog) return dialog;
    dialog = document.createElement('dialog');
    dialog.id = 'morphorum-shared-dialog';
    dialog.className = 'morphorum-modal';
    dialog.setAttribute('aria-labelledby', 'morphorum-modal-title');
    dialog.setAttribute('aria-describedby', 'morphorum-modal-message');
    document.body.appendChild(dialog);
    return dialog;
  }
  function next() {
    if (active || !queue.length) return;
    const entry = queue.shift();
    active = entry;
    const dialog = ensureHost();
    if (typeof dialog.showModal !== 'function') {
      active = null;
      entry.resolve(typeDefault(entry.type));
      window.MorphorumToast?.('Dialog unavailable', 'This browser cannot display a confirmation. The action was cancelled.', 'warning', 6500);
      next();
      return;
    }
    const previous = document.activeElement;
    dialog.replaceChildren();
    const card = document.createElement('div');
    card.className = 'morphorum-modal-body';
    card.dataset.variant = entry.variant;
    const title = document.createElement('h2');
    title.id = 'morphorum-modal-title';
    title.textContent = entry.title;
    const message = document.createElement('p');
    message.id = 'morphorum-modal-message';
    message.textContent = entry.message;
    card.append(title, message);
    let input = null;
    let error = null;
    if (entry.details) {
      const more = document.createElement('details');
      const summary = document.createElement('summary');
      summary.textContent = 'Technical details';
      const detailText = document.createElement('pre');
      detailText.textContent = entry.details;
      more.append(summary, detailText);
      card.appendChild(more);
    }
    if (entry.type === 'prompt') {
      const label = document.createElement('label');
      label.textContent = entry.inputLabel || 'Value';
      input = document.createElement('input');
      input.type = 'text';
      input.value = entry.initialValue;
      if (entry.placeholder) input.placeholder = entry.placeholder;
      input.maxLength = entry.maxLength;
      label.appendChild(input);
      error = document.createElement('small');
      error.className = 'morphorum-modal-error';
      error.setAttribute('aria-live', 'polite');
      card.append(label, error);
    }
    const form = document.createElement('form');
    form.method = 'dialog';
    form.className = 'morphorum-modal-actions';
    const cancel = document.createElement('button');
    cancel.type = 'button';
    cancel.className = 'secondary-button';
    cancel.textContent = entry.cancelText;
    if (entry.type === 'alert') cancel.hidden = true;
    const accept = document.createElement('button');
    accept.type = 'submit';
    accept.className = entry.variant === 'danger' ? 'secondary-button danger' : 'primary-button';
    accept.textContent = entry.confirmText;
    form.append(cancel, accept);
    card.appendChild(form);
    dialog.appendChild(card);
    let settled = false;
    const finish = value => {
      if (settled) return;
      settled = true;
      dialog.removeEventListener('cancel', onCancel);
      dialog.removeEventListener('click', onBackdrop);
      form.removeEventListener('submit', onSubmit);
      cancel.removeEventListener('click', onCancel);
      if (dialog.open) dialog.close();
      active = null;
      entry.resolve(value);
      if (previous?.isConnected && previous.focus) previous.focus({ preventScroll: true });
      next();
    };
    const onCancel = event => { event?.preventDefault?.(); finish(entry.type === 'alert' ? undefined : typeDefault(entry.type)); };
    const onBackdrop = event => { if (event.target === dialog) onCancel(event); };
    const onSubmit = event => {
      event.preventDefault();
      if (entry.type !== 'prompt') { finish(entry.type === 'confirm' ? true : undefined); return; }
      const value = input.value.trim();
      const result = typeof entry.validate === 'function' ? entry.validate(value) : (value ? '' : 'Enter a value.');
      if (result) { error.textContent = String(result); input.focus(); return; }
      finish(value);
    };
    cancel.addEventListener('click', onCancel);
    dialog.addEventListener('cancel', onCancel);
    dialog.addEventListener('click', onBackdrop);
    form.addEventListener('submit', onSubmit);
    try {
      dialog.showModal();
      (input || (entry.type === 'alert' ? accept : cancel)).focus();
    } catch (err) {
      onCancel();
    }
  }
  function ask(type, options = {}) {
    return new Promise(resolve => {
      queue.push({
        resolve, type,
        title: String(options.title || (type === 'confirm' ? 'Please confirm' : type === 'prompt' ? 'Enter a value' : 'Notice')),
        message: String(options.message || ''),
        details: options.details ? String(options.details) : '',
        variant: ['info','normal','warning','error','danger'].includes(options.variant) ? options.variant : 'normal',
        initialValue: String(options.initialValue || ''),
        inputLabel: String(options.inputLabel || ''),
        placeholder: String(options.placeholder || ''),
        maxLength: Math.min(1024, Math.max(1, Number(options.maxLength) || 120)),
        validate: options.validate,
        confirmText: String(options.confirmText || (type === 'confirm' ? 'Continue' : type === 'prompt' ? 'Create' : 'OK')),
        cancelText: String(options.cancelText || 'Cancel'),
      });
      next();
    });
  }
  window.MorphorumDialog = {
    alert: options => ask('alert', options),
    confirm: options => ask('confirm', options),
    prompt: options => ask('prompt', options),
  };
  function makeLoraSnippet({ name, weight = 1, triggers = [] } = {}) {
    const identifier = String(name || '').trim();
    if (!identifier || /[:<>\r\n]/.test(identifier)) throw new Error('This LoRA name cannot be used in a prompt tag.');
    const value = Number(weight);
    if (!Number.isFinite(value) || value < -4 || value > 4) throw new Error('LoRA strength must be between -4 and 4.');
    const words = [...new Set((Array.isArray(triggers) ? triggers : [])
      .filter(item => typeof item === 'string' && !/[<>\r\n]/.test(item))
      .map(item => item.trim()).filter(Boolean))].slice(0, 20);
    const tag = '<lora:' + identifier + ':' + Number(value.toFixed(4)) + '>';
    return [...words, tag].join(', ');
  }
  window.MorphorumPromptTags = { lora: makeLoraSnippet };
  // Shared P1.6 contextual-help service. Trusted static text, no HTML injection.
  const HELP_TOPICS = Object.freeze({
    "animation-model": {title: "Project checkpoint", body: "Still-image and animation model selections are separate. Select a checkpoint for this saved animation, then check resolution, sampler and guidance."},
    "animation-mode": {title: "2D versus 3D", body: "2D warps the flat image. 3D estimates depth, then reprojects the previous image each frame. Too much camera travel can leave no visible scene."},
    "animation-resolution-preset": {title: "Resolution", body: "Model-specific presets provide a starting point. Bigger frames use more VRAM and render more slowly."},
    "animation-fps": {title: "Frame rate", body: "Frames per second controls playback duration and camera timing. Duration equals total frames divided by FPS."},
    "animation-cadence": {title: "Diffusion cadence", body: "Cadence 1 redraws every eligible frame. Higher cadence transforms some frames without diffusion. Large motions between anchors can drift."},
    "animation-strength": {title: "Frame retention", body: "Morphorum uses retention strength: 1 preserves the image and skips diffusion; 0 allows full redraw. Moderate values help preserve continuity."},
    "animation-steps": {title: "Steps", body: "Higher diffusion steps may take longer, and the useful range depends on model and sampler. Turbo models commonly use fewer steps."},
    "animation-guidance": {title: "Guidance", body: "Sets prompt influence; recommended values vary by model family. Use the automatically recommended starting point before tuning."},
    "animation-sampler": {title: "Sampler", body: "Controls the denoising algorithm. Options depend on the selected model family."},
    "animation-seed": {title: "Seed", body: "With otherwise matching conditions, a fixed seed helps reproduce an image. -1 selects a random seed."},
    "animation-seed-behavior": {title: "Seed behavior", body: "Fixed reuses the same seed; Increment changes it by a step each frame; Random chooses new seeds. This can affect animation continuity."},
    "animation-3d-translation-z": {title: "Depth motion (Z)", body: "Signed Z camera movement repeats per frame, not as one final position. Excessive cumulative movement can push the visible scene behind the camera."},
    "animation-3d-rotation-y": {title: "Yaw rotation (Y)", body: "Rotation Y turns the camera around the vertical axis. A constant schedule repeats the turn on each frame; too much accumulated yaw can turn away from the scene."},
    "animation-3d-fov": {title: "Camera field of view", body: "FOV is measured in degrees; 40° is the default. A narrow FOV paired with aggressive camera movement can project every pixel outside the image."},
    "animation-3d-depth-resolution": {title: "Depth resolution", body: "Higher depth resolution may preserve more detail, but can require more CPU time and memory. Auto is a sensible starting point."},
    "animation-3d-projection-mode": {title: "3D projection quality", body: "Smooth projection can improve edge detail over classic nearest-pixel projection, but neither mode prevents extreme camera travel from losing the image."},
    "animation-motion-lab-strength": {title: "Motion layer strength", body: "Scales the amount of camera motion from this layer. It is different from diffusion retention strength."},
    "animation-motion-lab-cycle": {title: "Cycle duration", body: "Length of a repeated movement in seconds. Shorter cycles repeat more often."},
    "animation-motion-lab-blend": {title: "Layer blending", body: "Add combines motion with existing curves; Replace overwrites affected axes. Preview the result before applying."},
    "image-model-select": {title: "Image checkpoint", body: "This checkpoint is used for single-image generation. Animation projects save a separate checkpoint selection."},
    "image-resolution-preset": {title: "Image size presets", body: "Choose a model-aware image size or enter width and height in pixels. Larger images demand more GPU memory."},
    "image-width": {title: "Image width", body: "Output width in pixels. SDXL requires multiples of 8; Flux and Z-Image require multiples of 16."},
    "image-height": {title: "Image height", body: "Output height in pixels. The swap control exchanges width and height without changing pixel count."},
    "image-steps": {title: "Diffusion steps", body: "Denoising iterations per image. Turbo and Schnell models often use fewer steps; more steps are not always better."},
    "image-sampler": {title: "Image sampler", body: "The model-dependent denoising algorithm. Image Generation and the animation Project Editor have independent sampler selectors."},
    "image-guidance": {title: "CFG / guidance", body: "Controls how strongly prompt text steers generation. Supported ranges vary by model; some variants require guidance zero."},
    "image-seed": {title: "Image seed", body: "Seeds help reproduce noise with identical settings. A value of -1 requests an automatic random seed; dice fills a random value."},
    "image-seed-mode": {title: "Image seed mode", body: "Fixed reuses a seed, Increment changes it per image, and Random chooses a new seed for each batch output."},
    "image-seed-increment": {title: "Image seed increment", body: "Signed integer added to the seed for each successive image when Increment mode is selected."},
    "image-count": {title: "Batch image count", body: "Number of images to generate in one request, from 1 to 32. More outputs increase rendering time and storage."},
    "animation-max-frames": {title: "Animation length", body: "Total number of animation frames. Duration in seconds is the total divided by FPS; schedules use frame indices."},
    "animation-width": {title: "Animation width", body: "Output width in pixels. Match the selected checkpoint's resolution alignment and GPU memory."},
    "animation-height": {title: "Animation height", body: "Output height in pixels. SDXL aligns to 8 pixels, Flux and Z-Image to 16."},
    "animation-prompt-transition": {title: "Prompt transitions", body: "Blend interpolates text between prompt keyframes; Hold retains one prompt until the next keyframe."},
    "animation-cadence-preset": {title: "Cadence preset", body: "Fixed presets redraw every N frames; Custom enables a keyframed cadence schedule. Camera transforms run between anchors."},
    "animation-temporal-mode": {title: "Temporal blending mode", body: "Forward uses previous-frame information; Depth-aligned blending also uses neighbor anchors where projected depth is reliable."},
    "animation-temporal-mix": {title: "Temporal blend strength", body: "Fraction from 0 to 1 controlling how neighboring 3D frames contribute during depth-aligned blending."},
    "animation-temporal-contrast": {title: "Appearance guard", body: "RGB intensity difference threshold, 1–255, used to guard blending where frame appearances differ."},
    "animation-start-mode": {title: "Animation start mode", body: "Prompt generates frame 0 from text. Starting Image uses an uploaded image exactly for frame 0."},
    "animation-source-file": {title: "Starting image", body: "Upload PNG, JPEG, WebP or BMP. Required for Starting Image mode, optional as a camera preview reference for Prompt mode."},
    "animation-border-mode": {title: "Border handling", body: "Replicate stretches visible edge pixels; Wrap samples the opposite edge when 2D motion exposes empty borders."},
    "animation-angle": {title: "2D rotation", body: "Flat-image rotation in degrees per frame. A constant nonzero value repeatedly rotates the image."},
    "animation-zoom": {title: "2D zoom", body: "Multiplicative factor per frame. 1.0 means no zoom, 1.005 slowly zooms in, 0.995 slowly zooms out. Must be positive."},
    "animation-translation-x": {title: "2D pan X", body: "Signed horizontal shift in pixels per frame. Motion accumulates over successive frames."},
    "animation-translation-y": {title: "2D pan Y", body: "Signed vertical shift in pixels per frame. Use the camera preview to confirm direction."},
    "animation-noise": {title: "Animation noise", body: "Uniform noise amount in the generation schedule. Try subtle values such as 0:(0.02) to maintain frame continuity."},
    "animation-seed-increment": {title: "Frame seed increment", body: "Signed integer added to the per-frame seed when Seed behavior is Increment. Fixed and Random ignore it."},
    "animation-3d-preset": {title: "3D camera preset", body: "Applying a preset replaces six camera schedules with gentle per-frame values; it does not change FOV or automatically save."},
    "animation-3d-translation-x": {title: "3D translation X", body: "Signed horizontal movement in scene units per frame, based on estimated depth rather than pixel positions."},
    "animation-3d-translation-y": {title: "3D translation Y", body: "Signed vertical movement in scene units per frame. Cumulative movement can shift the whole scene out of view."},
    "animation-3d-rotation-x": {title: "3D pitch", body: "Rotation about camera X in degrees per frame. Repeated pitch can point the camera away from the scene."},
    "animation-3d-rotation-z": {title: "3D roll", body: "Rotation about camera Z in degrees per frame. Small values accumulate across long animations."},
    "animation-3d-hole-fill": {title: "3D hole fill", body: "Nearest or background-aware filling handles uncovered pixels. It cannot recover a projection with no visible pixels."},
    "animation-motion-lab-preset": {title: "Composer preset", body: "Select a layer motion shape; Add creates a draft. Applying draft motion to the animation is a separate action."},
    "animation-motion-lab-fade": {title: "Composer fade", body: "Fade time in seconds for easing the start and end of a motion layer."},
    "animation-motion-lab-start": {title: "Composer start frame", body: "Zero-based animation frame where this draft motion layer begins."},
    "animation-motion-lab-end": {title: "Composer end frame", body: "End frame for this draft layer; enter zero to continue until the project ends."},
  });
  const HELP_PANEL_ID = 'morphorum-context-help-tooltip';
  let helpEnabled = true, activeHelp = null, helpPinned = false, helpPanel = null;

  function getHelpPanel() {
    if (helpPanel) return helpPanel;
    const panel = document.createElement('div');
    panel.id = HELP_PANEL_ID;
    panel.className = 'morphorum-context-help-panel';
    panel.setAttribute('role', 'tooltip');
    panel.hidden = true;
    const title = document.createElement('strong');
    title.className = 'morphorum-context-help-title';
    const body = document.createElement('p');
    body.className = 'morphorum-context-help-body';
    panel.append(title, body);
    document.body.appendChild(panel);
    helpPanel = panel;
    return panel;
  }

  function closeHelp() {
    if (activeHelp) {
      activeHelp.setAttribute('aria-expanded', 'false');
      activeHelp.removeAttribute('aria-describedby');
    }
    activeHelp = null;
    helpPinned = false;
    if (helpPanel) helpPanel.hidden = true;
  }

  function positionHelp() {
    if (!activeHelp || !helpPanel || helpPanel.hidden) return;
    if (!activeHelp.isConnected) { closeHelp(); return; }
    const rect = activeHelp.getBoundingClientRect();
    const width = Math.min(360, Math.max(120, window.innerWidth - 24));
    helpPanel.style.width = width + 'px';
    helpPanel.style.left = Math.max(12, Math.min(rect.left, window.innerWidth - width - 12)) + 'px';
    const height = helpPanel.getBoundingClientRect().height;
    const y = rect.bottom + 8 + height <= window.innerHeight - 12
      ? rect.bottom + 8 : rect.top - height - 8;
    helpPanel.style.top = Math.max(12, Math.min(y, window.innerHeight - height - 12)) + 'px';
  }

  function showHelp(button, pin = false) {
    if (!helpEnabled || !button?.isConnected) return;
    if (activeHelp === button && pin && helpPinned) { closeHelp(); return; }
    const topic = HELP_TOPICS[button.dataset.helpTopic];
    if (!topic) return;
    if (activeHelp && activeHelp !== button) closeHelp();
    activeHelp = button;
    helpPinned = helpPinned || pin;
    const panel = getHelpPanel();
    panel.querySelector('.morphorum-context-help-title').textContent = topic.title;
    panel.querySelector('.morphorum-context-help-body').textContent = topic.body;
    panel.hidden = false;
    button.setAttribute('aria-expanded', 'true');
    button.setAttribute('aria-describedby', HELP_PANEL_ID);
    positionHelp();
  }

  function addHelpButton(label) {
    if (label.dataset.helpReady === '1') return;
    const topic = HELP_TOPICS[label.dataset.helpTopic];
    if (!topic || !label.parentNode) return;
    // Keep the button *outside* the label to avoid activating its input.
    const wrapper = document.createElement('div');
    wrapper.className = 'morphorum-help-field';
    // Retain spanning labels in their original grid column after wrapping.
    for (const layoutClass of ['animation-span-2', 'image-resolution-preset-field']) {
      if (label.classList.contains(layoutClass)) wrapper.classList.add(layoutClass);
    }
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'morphorum-help-trigger';
    button.dataset.helpTopic = label.dataset.helpTopic;
    button.textContent = '?';
    button.setAttribute('aria-label', 'Help: ' + topic.title);
    button.setAttribute('aria-controls', HELP_PANEL_ID);
    button.setAttribute('aria-expanded', 'false');
    button.title = 'Explain ' + topic.title.toLowerCase();
    label.parentNode.insertBefore(wrapper, label);
    wrapper.append(label, button);
    label.dataset.helpReady = '1';
    button.addEventListener('pointerenter', event => {
      if (event.pointerType === 'mouse') showHelp(button);
    });
    button.addEventListener('pointerleave', () => {
      if (!helpPinned && document.activeElement !== button) closeHelp();
    });
    button.addEventListener('focus', () => showHelp(button));
    button.addEventListener('blur', closeHelp);
    button.addEventListener('click', () => showHelp(button, true));
  }

  function refreshHelp(root = document) {
    root.querySelectorAll('label[data-help-topic]').forEach(addHelpButton);
  }
  function setHelpEnabled(enabled) {
    helpEnabled = enabled !== false;
    document.documentElement.dataset.helpHints = helpEnabled ? 'on' : 'off';
    if (!helpEnabled) closeHelp();
  }
  window.MorphorumHelp = {refresh: refreshHelp, setEnabled: setHelpEnabled};
  // UI utilities are also loaded in Node test sandboxes without a DOM.
  // Register document listeners only in a real browser.
  if (typeof document !== 'undefined' && typeof document.addEventListener === 'function') {
    document.addEventListener('click', event => {
      if (!event.target.closest?.('.morphorum-help-trigger')) closeHelp();
    });
    document.addEventListener('keydown', event => {
      if (event.key === 'Escape') closeHelp();
    });
    document.addEventListener('scroll', positionHelp, true);
    window.addEventListener('resize', positionHelp);
    document.addEventListener('DOMContentLoaded', () => refreshHelp());
  }

})();
