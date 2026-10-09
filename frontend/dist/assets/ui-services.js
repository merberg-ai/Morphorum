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
})();
