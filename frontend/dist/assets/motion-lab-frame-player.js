/* Morphorum ML3.3 frame-clock motion preview. No canvas/GPU dependency. */
(() => {
  'use strict';
  class FramePlayer {
    constructor({root, image, play, reset, loop, scrub, time, getAudio, shouldSync, status}) {
      Object.assign(this, {root, image, playButton:play, resetButton:reset, loop, scrub, time, getAudio, shouldSync, status});
      this.active = false;
      this.frame = 0;
      this.startMs = 0;
      this.frameAtStart = 0;
      this.tickId = null;
      this.boundTick = stamp => this.tick(stamp);
      this.jobId = null;
      play.addEventListener('click', () => this.active ? this.pause() : this.play());
      reset.addEventListener('click', () => { this.pause(); this.seek(0); });
      scrub.addEventListener('input', () => this.seek(Number(scrub.value)));
    }
    load(job) {
      this.pause();
      this.jobId = String(job.id);
      const result = job.result || {};
      this.fps = Math.max(1, Number(result.fps) || 12);
      this.count = Math.max(1, Number(result.source_frames) || 1);
      this.positions = Array.isArray(result.captured_frame_numbers) &&
        result.captured_frame_numbers.length ? result.captured_frame_numbers :
        Array.from({length:Number(result.frame_player_samples || result.captured_frames || 1)},
          (_,i) => Math.round(i * (this.count - 1) /
            Math.max(1, Number(result.frame_player_samples || result.captured_frames || 1) - 1)));
      this.scrub.max = String(this.count - 1);
      this.root.hidden = false;
      this.seek(0);
    }
    clear() {
      this.pause();
      this.jobId = null;
      this.root.hidden = true;
      this.image.removeAttribute('src');
    }
    sampleFor(frame) {
      let low = 0, high = this.positions.length - 1;
      while (low < high) {
        const mid = Math.floor((low + high + 1) / 2);
        if (this.positions[mid] <= frame) low = mid;
        else high = mid - 1;
      }
      return low;
    }
    draw(frame) {
      if (!this.jobId) return;
      this.frame = Math.max(0, Math.min(this.count - 1, Math.floor(frame)));
      this.scrub.value = String(this.frame);
      this.time.textContent = (this.frame / this.fps).toFixed(2) + 's · frame ' +
        this.frame + '/' + (this.count - 1);
      const sample = this.sampleFor(this.frame);
      const url = '/api/animation/motion-preview/' + encodeURIComponent(this.jobId) +
        '/frames/' + sample;
      if (this.image.getAttribute('src') !== url) this.image.src = url;
    }
    seek(frame) {
      this.draw(frame);
      const audio = this.getAudio?.();
      if (audio && this.shouldSync?.() && audio.readyState >= 1 &&
          Number.isFinite(audio.duration)) {
        audio.currentTime = Math.min(this.frame / this.fps, Math.max(0, audio.duration - .001));
      }
      this.startMs = performance.now();
      this.frameAtStart = this.frame;
    }
    play() {
      if (!this.jobId || this.count < 2) return;
      if (this.frame >= this.count - 1) this.seek(0);
      this.active = true;
      this.playButton.textContent = 'Ⅱ Pause';
      this.frameAtStart = this.frame;
      this.startMs = performance.now();
      const audio = this.getAudio?.();
      if (audio && this.shouldSync?.() && audio.readyState >= 1 &&
          this.frame / this.fps < audio.duration) {
        audio.currentTime = this.frame / this.fps;
        audio.play()?.catch(error => this.status?.('Audio playback blocked: ' + error.message));
      }
      this.tickId = requestAnimationFrame(this.boundTick);
    }
    tick(now) {
      if (!this.active) return;
      const audio = this.getAudio?.();
      const syncAudio = audio && this.shouldSync?.() && !audio.paused &&
        audio.readyState >= 1 && Number.isFinite(audio.duration);
      let targetTime = syncAudio ? audio.currentTime :
        this.frameAtStart / this.fps + (now - this.startMs) / 1000;
      let next = Math.floor(targetTime * this.fps + 1e-7);
      if (next >= this.count) {
        if (this.loop.checked) {
          next %= this.count;
          this.frameAtStart = next;
          this.startMs = now;
          if (audio && this.shouldSync?.() && audio.readyState >= 1 &&
              Number.isFinite(audio.duration) && audio.duration > 0) {
            audio.currentTime = next / this.fps;
            audio.play()?.catch(error => this.status?.('Audio replay blocked: ' + error.message));
          }
        } else {
          this.draw(this.count - 1);
          this.pause();
          return;
        }
      }
      this.draw(next);
      this.tickId = requestAnimationFrame(this.boundTick);
    }
    pause() {
      this.active = false;
      if (this.tickId !== null) cancelAnimationFrame(this.tickId);
      this.tickId = null;
      this.playButton.textContent = '▶ Play';
      this.getAudio?.()?.pause();
    }
  }
  window.MorphorumMotionFramePlayer = FramePlayer;
})();
