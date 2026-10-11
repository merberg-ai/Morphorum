(() => {
  'use strict';

  const AXES = [
    'translation_x','translation_y','translation_z',
    'rotation_x','rotation_y','rotation_z',
  ];

  function clamp(value, low, high) {
    return Math.max(low, Math.min(high, Number(value) || 0));
  }

  function deadzoned(value, deadzone) {
    const v = clamp(value, -1, 1);
    const a = Math.abs(v);
    if (a <= deadzone) return 0;
    const scaled = (a - deadzone) / Math.max(1e-9, 1 - deadzone);
    return Math.sign(v) * scaled;
  }

  class MotionLabFrameRecorder {
    constructor(options = {}) {
      this.now = options.now || (() => performance.now());
      this.requestFrame = options.requestFrame || (callback => requestAnimationFrame(callback));
      this.cancelFrame = options.cancelFrame || (id => cancelAnimationFrame(id));
      this.active = false;
      this.tickId = 0;
      this.boundTick = stamp => this.tick(stamp);
      this.samples = [];
      this.sources = new Set();
      this.current = new Array(AXES.length).fill(0);
      this.nextLocalFrame = 0;
      this.startStamp = 0;
      this.options = null;
      this.completed = false;
    }

    start(options = {}) {
      if (this.active) throw new Error('Motion recording is already active.');
      const fps = Number(options.fps);
      const startFrame = Number(options.startFrame);
      const maxFrames = Number(options.maxFrames);
      if (!Number.isFinite(fps) || fps <= 0 || fps > 240) {
        throw new Error('Recording FPS must be between 1 and 240.');
      }
      if (!Number.isInteger(startFrame) || startFrame < 0) {
        throw new Error('Recording start frame must be a non-negative integer.');
      }
      if (!Number.isInteger(maxFrames) || maxFrames < 1) {
        throw new Error('Recording must have at least one available project frame.');
      }
      const armedAxes = Array.isArray(options.armedAxes) ? options.armedAxes.slice() : AXES.slice();
      if (!armedAxes.length || armedAxes.some(axis => !AXES.includes(axis)) ||
          new Set(armedAxes).size !== armedAxes.length) {
        throw new Error('Recording armed axes are invalid.');
      }
      this.options = {
        fps,
        startFrame,
        maxFrames,
        armedAxes,
        translationScale: clamp(options.translationScale ?? .025, .00001, 30),
        rotationScale: clamp(options.rotationScale ?? .5, .00001, 30),
        deadzone: clamp(options.deadzone ?? .08, 0, .95),
        response: clamp(options.response ?? .55, .05, 1),
        tailFrames: Math.max(0, Math.min(12, Math.trunc(Number(options.tailFrames) || 0))),
        sampleInput: typeof options.sampleInput === 'function'
          ? options.sampleInput : (() => ({values:{}, sources:[]})),
        onFrame: typeof options.onFrame === 'function' ? options.onFrame : null,
        onComplete: typeof options.onComplete === 'function' ? options.onComplete : null,
      };
      this.samples = [];
      this.sources = new Set();
      this.current = new Array(AXES.length).fill(0);
      this.nextLocalFrame = 0;
      this.startStamp = this.now();
      this.completed = false;
      this.active = true;
      this.captureCurrent();
      if (this.active) this.tickId = this.requestFrame(this.boundTick);
      return this;
    }

    inputTarget(input) {
      const values = input && typeof input.values === 'object' ? input.values : {};
      const sourceList = Array.isArray(input?.sources) ? input.sources : [];
      for (const source of sourceList) {
        const label = String(source || '').trim().toLowerCase();
        if (label) this.sources.add(label);
      }
      const armed = new Set(this.options.armedAxes);
      return AXES.map((axis, index) => {
        if (!armed.has(axis)) return 0;
        const normalized = deadzoned(values[axis] ?? 0, this.options.deadzone);
        const scale = index < 3 ? this.options.translationScale : this.options.rotationScale;
        return normalized * scale;
      });
    }

    captureCurrent(inputOverride = null, forceZero = false) {
      if (!this.active || this.nextLocalFrame >= this.options.maxFrames) return false;
      const globalFrame = this.options.startFrame + this.nextLocalFrame;
      const input = inputOverride || this.options.sampleInput();
      const target = this.inputTarget(input);
      const sample = new Array(AXES.length).fill(0);
      if (globalFrame === 0) {
        this.current.fill(0);
      } else {
        for (let i = 0; i < AXES.length; i += 1) {
          if (!this.options.armedAxes.includes(AXES[i])) {
            this.current[i] = 0;
            continue;
          }
          this.current[i] += (target[i] - this.current[i]) * this.options.response;
          if (Math.abs(this.current[i]) < 1e-12) this.current[i] = 0;
          sample[i] = this.current[i];
        }
      }
      if (forceZero) {
        this.current.fill(0);
        sample.fill(0);
      }
      this.samples.push(sample);
      this.nextLocalFrame += 1;
      this.options.onFrame?.({
        frame: globalFrame,
        localFrame: this.nextLocalFrame - 1,
        sample: sample.slice(),
        count: this.samples.length,
      });
      if (this.nextLocalFrame >= this.options.maxFrames) {
        this.finish('project-end');
      }
      return true;
    }

    fillToStamp(stamp) {
      if (!this.active) return;
      const elapsed = Math.max(0, Number(stamp) - this.startStamp);
      const targetLocal = Math.floor(elapsed * this.options.fps / 1000);
      while (this.active && this.nextLocalFrame <= targetLocal) {
        this.captureCurrent();
      }
    }

    tick(stamp) {
      if (!this.active) return;
      this.fillToStamp(stamp);
      if (this.active) this.tickId = this.requestFrame(this.boundTick);
    }

    appendTail() {
      if (!this.active || this.options.tailFrames <= 0) return;
      const remaining = this.options.maxFrames - this.nextLocalFrame;
      const count = Math.min(this.options.tailFrames, remaining);
      for (let n = 0; n < count && this.active; n += 1) {
        const final = n === count - 1;
        this.captureCurrent({values:{}, sources:[]}, final);
      }
    }

    snapshot(reason) {
      return {
        reason,
        fps: this.options.fps,
        startFrame: this.options.startFrame,
        endFrame: this.options.startFrame + this.samples.length,
        armedAxes: this.options.armedAxes.slice(),
        samples: this.samples.map(row => row.slice()),
        sources: Array.from(this.sources).sort(),
      };
    }

    finish(reason) {
      if (this.completed) return this.snapshot(reason);
      this.completed = true;
      this.active = false;
      if (this.tickId) this.cancelFrame(this.tickId);
      this.tickId = 0;
      const take = this.snapshot(reason);
      this.options.onComplete?.(take);
      return take;
    }

    stop(reason = 'manual') {
      if (!this.active) return this.options ? this.snapshot(reason) : null;
      this.fillToStamp(this.now());
      if (!this.active) return this.snapshot('project-end');
      this.appendTail();
      if (!this.active) return this.snapshot('project-end');
      return this.finish(reason);
    }
  }

  // ML2.3 punch-in edits a copy, preserving all frames outside the interval
  // and all axes not armed in the new take.
  function splicePunchIn(target, take) {
    if (!target || target.type !== 'recording' || !take) throw new Error('Select a recorded target take.');
    const fps = Number(target.fps);
    if (!Number.isFinite(fps) || fps !== Number(take.fps)) throw new Error('Recording FPS mismatch.');
    if (!Number.isInteger(take.startFrame) || !Number.isInteger(take.endFrame) ||
        take.startFrame < target.start_frame || take.endFrame > target.end_frame ||
        take.startFrame >= take.endFrame ||
        !Array.isArray(take.samples) ||
        take.samples.length !== take.endFrame - take.startFrame) {
      throw new Error('Punch-in must fully cover the selected range inside the take.');
    }
    const armed = take.armedAxes;
    if (!Array.isArray(armed) || !armed.length || armed.some(axis =>
        !target.axes.includes(axis)) || new Set(armed).size !== armed.length) {
      throw new Error('Punch-in axes must be armed in the original recording.');
    }
    const copy = JSON.parse(JSON.stringify(target));
    for (let frame = take.startFrame; frame < take.endFrame; frame += 1) {
      const incoming = take.samples[frame - take.startFrame];
      const row = copy.samples[frame - target.start_frame];
      if (!Array.isArray(row) || row.length !== 6 || !Array.isArray(incoming) ||
          incoming.length !== 6 || incoming.some(v => !Number.isFinite(v))) {
        throw new Error('Invalid six-axis punch-in samples.');
      }
      for (const axis of armed) {
        const i = AXES.indexOf(axis);
        if (i < 0) throw new Error('Invalid punch-in axis.');
        row[i] = frame === 0 ? 0 : incoming[i];
      }
    }
    copy.source = target.source === (take.sources?.[0] || 'unknown') ?
      target.source : 'mixed';
    return copy;
  }

  window.MorphorumMotionLabFrameRecorder = MotionLabFrameRecorder;
  window.MorphorumMotionLabSplicePunchIn = splicePunchIn;
  window.MorphorumMotionLabRecordingAxes = AXES.slice();
})();
