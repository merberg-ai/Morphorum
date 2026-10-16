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
    if (label.classList.contains('animation-span-2')) {
      label.classList.remove('animation-span-2');
      wrapper.classList.add('animation-span-2');
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
