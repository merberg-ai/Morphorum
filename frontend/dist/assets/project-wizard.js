(() => {
  'use strict';

  // The wizard is deliberately separate from the Editor. It owns only an
  // unsaved draft until the final POST, using canonical server defaults.
  const STORAGE_KEY = 'morphorum.project-wizard.draft.v1';
  const STEPS = [
    ['Welcome & Name', 'Give your animation a name before making any settings. Nothing is saved yet.'],
    ['Choose a Model', 'The model is the AI engine that creates each generated frame.'],
    ['Animation Setup', 'Decide how long and how large the animation should be.'],
    ['Prompts & Keyframes', 'Tell the AI what to draw and optionally change the scene at a later frame.'],
    ['Camera Motion', 'Pick a gentle starting camera path. You can customize every axis later.'],
    ['Generation Settings', 'Choose how each frame is redrawn. Recommended model defaults are a safe starting point.'],
    ['Review & Save', 'Review your choices, then save the finished project.'],
  ];
  const $ = (selector, root = document) => root.querySelector(selector);

  function readPath(root, dotted) {
    return dotted.split('.').reduce((value, key) => value?.[key], root);
  }
  function writePath(root, dotted, value) {
    const keys = dotted.split('.');
    let target = root;
    for (const key of keys.slice(0, -1)) {
      target[key] ||= {};
      target = target[key];
    }
    target[keys[keys.length - 1]] = value;
  }
  function node(tag, className, text) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined) element.textContent = text;
    return element;
  }
  async function getJson(url, options = {}) {
    const response = await fetch(url, {
      headers: { 'Content-Type': 'application/json' }, ...options,
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'The server could not complete this request.');
    return data;
  }
  function range(value, min, max) {
    const number = Number(value);
    return Number.isFinite(number) && number >= min && number <= max;
  }
  const presetHelp = {
    still: 'No camera motion. A good first test.',
    pan: 'Slide to the right during the animation.',
    zoom: 'Slowly push toward the scene.',
    orbit: 'Rotate gently around the subject (3D).',
    spiral: 'Push in while turning around the subject (3D).',
  };

  class MorphorumProjectWizard {
    constructor({ panel, onSaved, onNavigate }) {
      this.panel = panel;
      this.onSaved = onSaved;
      this.onNavigate = onNavigate;
      this.draft = null;
      this.step = 0;
      this.loading = false;
      this.busy = false;
      this.models = [];
      this.capabilities = {};
      this.preset = 'still';
      this.nextPrompt = '';
      this.nextFrame = 30;
      this.errors = '';
      this.ready = false;
      this.dirtyDraft = false;
      window.addEventListener('morphorum:models-updated', event => {
        if (event.detail?.loaded === true) {
          this.models = (event.detail.models || []).filter(m => m.kind === 'checkpoints');
          if (this.ready && this.step === 1) this.render();
        }
      });
      window.addEventListener('beforeunload', event => {
        if (this.draft && this.dirtyDraft && !this.saved) {
          event.preventDefault();
          event.returnValue = '';
        }
      });
      this.panel.classList.add('project-wizard');
      this.panel.innerHTML = '<div class="card glass project-wizard-loading">Open this page to begin a new animation project.</div>';
    }

    remember() {
      if (!this.draft) return;
      try {
        sessionStorage.setItem(STORAGE_KEY, JSON.stringify({
          draft: this.draft, step: this.step,
          preset: this.preset, nextPrompt: this.nextPrompt,
          nextFrame: this.nextFrame,
        }));
      } catch (_) { /* Storage can be disabled by the browser. */ }
    }

    async open() {
      if (this.ready || this.loading) return;
      this.loading = true;
      this.panel.innerHTML = '<div class="card glass project-wizard-loading">Preparing the new project wizard…</div>';
      try {
        const [template, models, caps] = await Promise.all([
          getJson('/api/animation/project-template'),
          getJson('/api/models?limit=2000'),
          getJson('/api/generation/capabilities'),
        ]);
        this.models = (models.models || []).filter(model => model.kind === 'checkpoints');
        this.capabilities = caps.families || {};
        this.draft = template.project;
        this.saved = false;
        try {
          const restored = JSON.parse(sessionStorage.getItem(STORAGE_KEY) || 'null');
          if (restored?.draft && !restored.draft.id && restored.draft.animation &&
              restored.draft.generation && restored.draft.motion) {
            this.draft = restored.draft;
            this.dirtyDraft = true;
            this.step = Math.min(STEPS.length - 1, Math.max(0, Number(restored.step) || 0));
            this.preset = restored.preset || 'still';
            this.nextPrompt = String(restored.nextPrompt || '');
            this.nextFrame = Number(restored.nextFrame) || 30;
          }
        } catch (_) { /* Ignore damaged old draft. */ }
        this.ready = true;
        this.render();
      } catch (error) {
        this.panel.replaceChildren();
        const card = node('article', 'card glass project-wizard-error');
        card.append(node('h2', '', 'Could not start the wizard'),
          node('p', 'muted', error.message));
        const retry = node('button', 'secondary-button', 'Retry');
        retry.type = 'button';
        retry.addEventListener('click', () => { this.loading = false; this.open(); });
        card.appendChild(retry);
        this.panel.append(card);
      } finally {
        this.loading = false;
      }
    }

    familyCapability() {
      const model = this.models.find(m => m.id === this.draft?.model?.model_id);
      const base = this.capabilities[model?.family] || {};
      return { ...base, ...(base.variants?.[model?.variant] || {}) };
    }

    field(parent, label, dotted, help, options = {}) {
      const block = node('label', 'project-wizard-field');
      const heading = node('span', 'project-wizard-field-heading');
      heading.append(node('strong', '', label));
      const info = node('span', 'project-wizard-help-wrap');
      const hint = node('details', 'project-wizard-hint');
      const summary = node('summary', '', '?');
      summary.setAttribute('aria-label', 'Explain ' + label);
      hint.append(summary, node('p', '', help));
      info.appendChild(hint);
      heading.appendChild(info);
      block.appendChild(heading);
      const tag = options.type === 'textarea' ? 'textarea' : options.choices ? 'select' : 'input';
      const control = node(tag);
      control.id = 'project-wizard-' + dotted.replace(/[^a-z0-9]+/gi, '-');
      control.name = dotted;
      if (tag === 'input') control.type = options.type || 'text';
      if (options.min !== undefined) control.min = String(options.min);
      if (options.max !== undefined) control.max = String(options.max);
      if (options.step !== undefined) control.step = String(options.step);
      if (options.placeholder) control.placeholder = options.placeholder;
      if (options.maxLength) control.maxLength = options.maxLength;
      if (tag === 'textarea') control.rows = 4;
      if (options.choices) {
        for (const [key, title] of options.choices) {
          const option = node('option', '', title);
          option.value = String(key);
          control.append(option);
        }
      }
      control.value = String(options.value !== undefined ? options.value : readPath(this.draft, dotted) ?? '');
      control.addEventListener(tag === 'select' ? 'change' : 'input', () => {
        const number = options.type === 'number';
        const value = number && control.value !== '' ? Number(control.value) : control.value;
        if (options.onChange) options.onChange(value);
        else writePath(this.draft, dotted, value);
        this.errors = '';
        this.dirtyDraft = true;
        this.remember();
      });
      block.append(control);
      parent.append(block);
      return control;
    }

    info(parent, text, variant = 'muted') {
      parent.append(node('p', 'project-wizard-info ' + variant, text));
    }

    button(parent, label, action, secondary = false) {
      const item = node('button', secondary ? 'secondary-button' : 'primary-button', label);
      item.type = 'button';
      item.disabled = this.busy;
      item.addEventListener('click', action);
      parent.append(item);
      return item;
    }

    selectModel(id) {
      const model = this.models.find(x => x.id === id);
      this.draft.model = {
        model_id: model?.id || '',
        family: model?.family || '',
        variant: model?.variant || '',
      };
      if (model) {
        const cap = this.familyCapability();
        this.draft.generation.sampler = cap.samplers?.default || 'euler';
        this.draft.generation.steps = '0:(' + (cap.steps?.default ?? 20) + ')';
        this.draft.generation.guidance = '0:(' + (cap.guidance?.default ?? 0) + ')';
        this.draft.animation.width = cap.default_resolution?.width || 1024;
        this.draft.animation.height = cap.default_resolution?.height || 1024;
      }
      this.dirtyDraft = true;
      this.remember();
      this.render();
    }

    configureCamera(preset) {
      this.preset = preset;
      const total = Math.max(1, Number(this.draft.animation.max_frames) - 1);
      // Keep the full default schema; change only authored motion schedules.
      for (const axis of ['angle', 'translation_x', 'translation_y']) {
        this.draft.motion[axis] = '0:(0)';
      }
      this.draft.motion.zoom = '0:(1.0)';
      for (const axis of ['translation_x', 'translation_y', 'translation_z',
        'rotation_x', 'rotation_y', 'rotation_z']) {
        this.draft.camera_3d[axis] = '0:(0)';
      }
      if (preset === 'pan') this.draft.motion.translation_x = '0:(0), ' + total + ':(30)';
      if (preset === 'zoom') this.draft.motion.zoom = '0:(1.0), ' + total + ':(1.08)';
      if (preset === 'orbit' || preset === 'spiral') {
        this.draft.animation.mode = '3d';
        this.draft.camera_3d.rotation_y = '0:(0), ' + total + ':(12)';
      }
      if (preset === 'spiral') {
        this.draft.camera_3d.translation_z = '0:(0), ' + total + ':(3)';
        this.draft.camera_3d.rotation_z = '0:(0), ' + total + ':(8)';
      }
      this.dirtyDraft = true;
      this.remember();
      this.render();
    }

    stage(container) {
      const p = this.draft;
      switch (this.step) {
        case 0:
          this.field(container, 'Project name', 'name',
            'This is how the animation appears in Project Manager. You can rename it later.',
            { maxLength: 120, placeholder: 'My First Animation' });
          this.info(container, 'Your project is kept as an unsaved wizard draft until the final step. Existing animations will not be changed.');
          break;
        case 1: {
          const options = [['', 'Choose a model…'],
            ...this.models.map(m => [m.id, '[' + m.family.toUpperCase() + '] ' + m.name])];
          this.field(container, 'Image generation model', 'model.model_id',
            'Choose a checkpoint available on the computer hosting Morphorum. LoRAs need a matching base checkpoint.',
            { choices: options, onChange: id => this.selectModel(id) });
          if (!this.models.length) {
            this.info(container, 'No models are indexed. Download Z-Image-Turbo from Models, or configure your SDXL/FLUX folders in Settings and scan. Then return here.', 'warning');
          } else {
            this.info(container, 'Using a different model family updates the starting sampler, steps, guidance and resolution to its recommended defaults.');
          }
          const tools = node('div', 'project-wizard-shortcuts');
          this.button(tools, 'Open Models / Download', () => this.onNavigate('models'), true);
          this.button(tools, 'Configure Model & LoRA Folders', () => this.onNavigate('settings'), true);
          this.button(tools, 'Refresh Models', async () => {
            try {
              const payload = await getJson('/api/models?limit=2000');
              this.models = (payload.models || []).filter(m => m.kind === 'checkpoints');
              this.render();
            } catch (error) { this.fail(error.message); }
          }, true);
          container.append(tools);
          break;
        }
        case 2: {
          this.field(container, 'Animation mode', 'animation.mode',
            '2D moves a flat image. 3D uses depth estimation for more realistic camera translation and rotation.',
            { choices: [['2d', '2D animation'], ['3d', '3D depth-aware animation']] });
          this.field(container, 'Number of frames', 'animation.max_frames',
            'Total frames in the animation. More frames take longer to generate.',
            { type: 'number', min: 1, max: 1000000, step: 1 });
          this.field(container, 'Frames per second (FPS)', 'animation.fps',
            'How many frames play in one second. Duration is frame count divided by FPS.',
            { type: 'number', min: 1, max: 240, step: 'any' });
          this.field(container, 'Width (pixels)', 'animation.width',
            'Choose a model-supported width. Higher resolutions need more GPU memory. Use a multiple of 8.',
            { type: 'number', min: 64, max: 8192, step: 8 });
          this.field(container, 'Height (pixels)', 'animation.height',
            'Choose a model-supported height. Use a multiple of 8 to avoid pipeline errors.',
            { type: 'number', min: 64, max: 8192, step: 8 });
          this.info(container, 'Estimated duration: ' +
            (Number(p.animation.max_frames) / Math.max(1, Number(p.animation.fps))).toFixed(2) +
            ' seconds. A short test render is recommended before a long project.');
          break;
        }
        case 3:
          this.field(container, 'Opening prompt (frame 0)', 'prompts.0',
            'Describe the subject, lighting, style, and environment. Frame 0 is always the starting prompt.',
            { type: 'textarea', placeholder: 'A moonlit forest with mist and cinematic lighting' });
          this.field(container, 'Opening negative prompt (optional)', 'negative_prompts.0',
            'Negative prompts discourage unwanted content where the selected model supports them. FLUX/Z-Image may ignore this field.',
            { type: 'textarea' });
          this.field(container, 'Prompt transition', 'animation.prompt_transition',
            'Hold changes the prompt at the keyframe; Blend gradually blends supported model conditioning between prompts.',
            { choices: [['blend', 'Blend between keyframes'], ['hold', 'Hold until next keyframe']] });
          this.field(container, 'Additional keyframe (optional)', 'wizard.nextFrame',
            'Frame where a second prompt should begin. Keep it below the total frame count.',
            { type: 'number', min: 1, max: Math.max(1, Number(p.animation.max_frames) - 1),
              value: this.nextFrame, onChange: value => { this.nextFrame = value; } });
          this.field(container, 'Second prompt (optional)', 'wizard.nextPrompt',
            'Leave empty for one continuous scene. Add text to change the scene at the chosen frame.',
            { type: 'textarea', value: this.nextPrompt, onChange: value => { this.nextPrompt = value; } });
          break;
        case 4: {
          const options = Object.entries(presetHelp).map(([key, label]) => [key, key[0].toUpperCase()+key.slice(1)+': '+label]);
          this.field(container, 'Camera movement preset', 'wizard.cameraPreset',
            'Select a preset as a starting point. The full Camera Composer and Motion Curves editor remain available after saving.',
            { choices: options, value: this.preset, onChange: value => this.configureCamera(value) });
          if (p.animation.mode === '3d') {
            this.field(container, 'Depth field of view', 'camera_3d.fov',
              'A scheduled camera field of view, default 40 degrees. Edit full schedules in Project Editor.');
          } else {
            this.field(container, 'Border mode', 'motion.border_mode',
              'Replicate extends edge pixels when the camera moves; Wrap repeats the image on the other side.',
              { choices: [['replicate', 'Replicate edges'], ['wrap', 'Wrap around']] });
          }
          this.info(container, 'Camera presets modify native motion schedules, not an independent rendering engine. Motion Lab Composer, Live Recording, and Curves can refine them after saving.');
          break;
        }
        case 5: {
          const cap = this.familyCapability();
          const samplerOptions = cap.samplers?.options?.map(x => [x.id, x.label || x.id]) ||
            [['flowmatch_euler', 'FlowMatch Euler'], ['euler', 'Euler']];
          this.field(container, 'Sampler', 'generation.sampler',
            'Controls how the AI samples each image. The options depend on the selected model.',
            { choices: samplerOptions });
          this.field(container, 'Steps schedule', 'generation.steps',
            'How many diffusion steps to perform per generated frame. Example: 0:(9). Larger values usually take longer.');
          this.field(container, 'Guidance schedule', 'generation.guidance',
            'How strongly the prompt guides each frame; Z-Image Turbo normally uses 0, FLUX often 1, SDXL uses CFG.');
          this.field(container, 'Image preservation strength schedule', 'generation.strength',
            'Higher Deforum-style strength tends to keep more of the previous frame. Default 0:(0.65).');
          this.field(container, 'Diffusion cadence schedule', 'cadence.diffusion',
            'How often to run diffusion. 0:(1) means every frame. Higher cadence may increase speed, with different motion blending.');
          this.field(container, 'Seed behavior', 'generation.seed_behavior',
            'Fixed repeats seeds, increment changes the seed every frame, random uses unpredictable seeds.',
            { choices: [['fixed', 'Fixed'], ['increment', 'Increment'], ['random', 'Random']] });
          this.field(container, 'Seed (-1 for random)', 'generation.seed',
            'A number to reproduce results. -1 delegates seed selection to the renderer.',
            { type: 'number', min: -1, max: 4294967295, step: 1 });
          break;
        }
        case 6: {
          const model = this.models.find(m => m.id === p.model.model_id);
          const details = [
            ['Project name', p.name],
            ['Model', model ? model.name : 'None selected'],
            ['Animation', p.animation.mode.toUpperCase() + ' · ' + p.animation.width + ' × ' + p.animation.height],
            ['Timing', p.animation.max_frames + ' frames at ' + p.animation.fps + ' FPS'],
            ['Prompt transition', p.animation.prompt_transition],
            ['Opening prompt', p.prompts['0']],
            ['Camera preset', this.preset],
            ['Sampler', p.generation.sampler],
            ['Steps / guidance', p.generation.steps + ' / ' + p.generation.guidance],
          ];
          const summary = node('dl', 'project-wizard-review');
          for (const [key, value] of details) {
            const fact = node('div');
            fact.append(node('dt', '', key), node('dd', '', String(value || '--')));
            summary.appendChild(fact);
          }
          container.append(summary);
          this.info(container, 'Optional advanced feature: Audio Motion can analyze a WAV soundtrack, synchronize frequency bands with camera movement, and include audio in supported video exports. You can explore it after saving; it is not required to create a project.');
          break;
        }
      }
    }

    validate(step = this.step) {
      const p = this.draft;
      if (!String(p?.name || '').trim()) return 'Enter a project name.';
      if (step === 0 && p.name.trim().length > 120) return 'Project names must be at most 120 characters.';
      if (step >= 1 && !this.models.some(model => model.id === p.model?.model_id)) {
        return 'Select a usable checkpoint. Configure or download a model from Models first.';
      }
      if (step >= 2) {
        if (!range(p.animation.max_frames, 1, 1000000) || !Number.isInteger(Number(p.animation.max_frames)))
          return 'Frame count must be a whole number between 1 and 1,000,000.';
        if (!range(p.animation.fps, 1, 240)) return 'FPS must be between 1 and 240.';
        for (const key of ['width', 'height']) {
          const value = Number(p.animation[key]);
          if (!range(value, 64, 8192) || !Number.isInteger(value) || value % 8)
            return key + ' must be a multiple of 8 between 64 and 8192.';
        }
      }
      if (step >= 3) {
        if (!String(p.prompts?.['0'] || '').trim()) return 'Enter an opening prompt.';
        if (this.nextPrompt.trim() && (!Number.isInteger(this.nextFrame) ||
            this.nextFrame < 1 || this.nextFrame >= Number(p.animation.max_frames)))
          return 'The second prompt frame must be after frame 0 and before the final frame.';
      }
      if (step >= 5) {
        for (const key of ['steps', 'guidance', 'strength']) {
          if (!String(p.generation?.[key] || '').trim()) return 'Enter a ' + key + ' schedule.';
        }
        if (!String(p.cadence?.diffusion || '').trim()) return 'Enter a cadence schedule.';
      }
      return '';
    }

    syncPrompts() {
      this.draft.prompts = { '0': String(this.draft.prompts?.['0'] || '') };
      this.draft.negative_prompts = { '0': String(this.draft.negative_prompts?.['0'] || '') };
      if (this.nextPrompt.trim()) {
        this.draft.prompts[String(this.nextFrame)] = this.nextPrompt.trim();
        this.draft.negative_prompts[String(this.nextFrame)] = '';
      }
    }

    next() {
      const validation = this.validate();
      if (validation) { this.fail(validation); return; }
      if (this.step === 3) this.syncPrompts();
      this.step = Math.min(this.step + 1, STEPS.length - 1);
      this.errors = '';
      this.remember();
      this.render();
    }

    fail(message) {
      this.errors = String(message);
      this.render();
      $('#project-wizard-error')?.focus();
    }

    async reset() {
      if (!await window.MorphorumDialog.confirm({
        title: 'Start the wizard over?',
        message: 'This clears your unsaved wizard answers. Existing projects are not changed.',
        confirmText: 'Start Over', cancelText: 'Keep Draft', variant: 'danger',
      })) return;
      sessionStorage.removeItem(STORAGE_KEY);
      this.ready = false;
      this.draft = null;
      this.step = 0;
      this.nextPrompt = '';
      this.nextFrame = 30;
      this.preset = 'still';
      this.dirtyDraft = false;
      await this.open();
    }

    async save() {
      if (this.busy) return;
      this.syncPrompts();
      const validation = this.validate(6);
      if (validation) { this.fail(validation); return; }
      const currentProjectDirty = await this.onNavigate('before-save');
      if (currentProjectDirty === false) return;
      this.busy = true;
      this.errors = '';
      this.render();
      try {
        const payload = JSON.parse(JSON.stringify(this.draft));
        // Let the server construct canonical synchronized timeline tracks.
        delete payload.tracks;
        delete payload.id;
        delete payload.created_at;
        delete payload.updated_at;
        delete payload.wizard;
        const checked = await getJson('/api/animation/validate-schedules', {
          method: 'POST',
          body: JSON.stringify({ project: { ...payload, id: 'wizard-validation' } }),
        });
        if (!checked.valid) {
          const problem = checked.issues?.find(issue => issue.severity === 'error');
          throw new Error(problem
            ? (problem.field + ': ' + problem.message)
            : 'One or more animation schedules are invalid. Review your settings.');
        }
        const result = await getJson('/api/animation/projects', {
          method: 'POST', body: JSON.stringify(payload),
        });
        this.saved = true;
        sessionStorage.removeItem(STORAGE_KEY);
        this.draft = null;
        this.ready = false;
        try {
          await this.onSaved(result.project.id);
        } catch (error) {
          window.MorphorumToast?.('Project saved', result.project.name +
            ' was saved, but could not be opened automatically: ' + error.message,
            'warning', 8000);
          return;
        }
        window.MorphorumToast?.('Project created', result.project.name +
          ' was saved. Open the Editor to refine advanced settings.', 'success');
      } catch (error) {
        this.fail(error.message);
      } finally {
        this.busy = false;
        if (this.draft) this.render();
      }
    }

    render() {
      if (!this.draft) return;
      this.panel.replaceChildren();
      const heading = node('header', 'project-wizard-heading');
      heading.append(node('p', 'eyebrow', 'MOTION LAB / NEW PROJECT WIZARD'),
        node('h2', '', 'Create a new animation'));
      this.panel.append(heading);
      const card = node('article', 'card glass project-wizard-card');
      const counter = node('div', 'project-wizard-counter', 'Step ' + (this.step + 1) + ' of ' + STEPS.length);
      const progress = node('div', 'project-wizard-progress');
      progress.setAttribute('role', 'progressbar');
      progress.setAttribute('aria-label', 'Wizard progress');
      progress.setAttribute('aria-valuemin', '1');
      progress.setAttribute('aria-valuemax', String(STEPS.length));
      progress.setAttribute('aria-valuenow', String(this.step + 1));
      for (let i = 0; i < STEPS.length; i += 1) {
        const bar = node('span', i <= this.step ? 'complete' : '');
        progress.append(bar);
      }
      const title = node('h3', '', STEPS[this.step][0]);
      const intro = node('p', 'muted', STEPS[this.step][1]);
      card.append(counter, progress, title, intro);
      const section = node('div', 'project-wizard-fields');
      this.stage(section);
      card.append(section);
      if (this.errors) {
        const warning = node('p', 'project-wizard-error-text', this.errors);
        warning.id = 'project-wizard-error';
        warning.tabIndex = -1;
        warning.setAttribute('role', 'alert');
        card.append(warning);
      }
      const footer = node('footer', 'project-wizard-footer');
      this.button(footer, '← Back', () => {
        this.step = Math.max(0, this.step - 1);
        this.errors = '';
        this.remember();
        this.render();
      }, true).disabled = this.busy || this.step === 0;
      const spacer = node('span', 'project-wizard-footer-spacer');
      footer.append(spacer);
      this.button(footer, 'Start Over', () => this.reset(), true);
      if (this.step < STEPS.length - 1) {
        this.button(footer, 'Next →', () => this.next());
      } else {
        this.button(footer, this.busy ? 'Saving…' : 'Save Project & Open Editor', () => this.save());
      }
      card.append(footer);
      this.panel.append(card);
    }
  }
  window.MorphorumProjectWizard = MorphorumProjectWizard;
})();