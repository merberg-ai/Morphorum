/* Morphorum ML3.3 frame-clock motion preview. No canvas/GPU dependency. */
(() => {
  'use strict';
  class FramePlayer {
    constructor({root, image, play, reset, loop, scrub, time, getAudio, shouldSync, status,
      rangeEnabled=null, rangeStart=null, rangeEnd=null, onFrame=null, onLoad=null}) {
      Object.assign(this, {root, image, playButton:play, resetButton:reset, loop, scrub, time, getAudio, shouldSync, status});
      this.active = false;
      this.frame = 0;
      this.startMs = 0;
      this.frameAtStart = 0;
      this.tickId = null;
      this.boundTick = stamp => this.tick(stamp);
      this.jobId = null;
      Object.assign(this,{rangeEnabled,rangeStart,rangeEnd,onFrame,onLoad});
      play.addEventListener('click', () => this.active ? this.pause() : this.play());
      reset.addEventListener('click', () => { this.pause(); this.seek(0); });
      scrub.addEventListener('input', () => this.seek(Number(scrub.value)));
    }
    load(job) {
      this.pause();
      this.jobId = String(job.id);
      const result = job.result || {};
      const fps = Number(result.fps), count = Number(result.source_frames);
      if (!Number.isFinite(fps) || fps <= 0 || fps > 240 ||
          !Number.isInteger(count) || count < 1 || count > 3000) {
        this.clear();
        throw new Error('Preview has invalid FPS or source frame count.');
      }
      this.fps = fps;
      this.count = count;
      const captures = result.captured_frame_numbers;
      const sampleCount = Number(result.frame_player_samples || result.captured_frames || 1);
      if (Array.isArray(captures) && captures.length) {
        if (captures.some((v,i)=>!Number.isInteger(v) || v<0 || v>=count ||
            (i>0 && v<=captures[i-1]))) {
          this.clear();
          throw new Error('Preview sample frame map is invalid.');
        }
        this.positions = captures.slice();
      } else {
        if (!Number.isInteger(sampleCount) || sampleCount<1 || sampleCount>3000) {
          this.clear();
          throw new Error('Preview has invalid sample count.');
        }
        this.positions = Array.from({length:sampleCount},
          (_,i)=>Math.round(i*(count-1)/Math.max(1,sampleCount-1)));
      }
      this.scrub.max=String(count-1);
      if (this.rangeStart) {this.rangeStart.max=String(count-1);this.rangeStart.value='0';}
      if (this.rangeEnd) {this.rangeEnd.max=String(count-1);this.rangeEnd.value=String(count-1);}
      if (this.rangeEnabled) this.rangeEnabled.checked=false;
      this.root.hidden=false;
      this.seek(0);
      this.onLoad?.({fps:this.fps,frames:this.count,samples:this.positions.length});
    }
    clear() {
      this.pause();
      this.jobId = null;
      this.root.hidden = true;
      this.image.removeAttribute('src');
    }
    reviewRange() {
      const last = Math.max(0,(this.count||1)-1);
      if (!this.rangeEnabled?.checked) return {start:0,end:last,limited:false};
      const from = Math.max(0,Math.min(last,Math.floor(Number(this.rangeStart?.value)||0)));
      const to = Math.max(0,Math.min(last,Math.floor(Number(this.rangeEnd?.value)||0)));
      return {start:Math.min(from,to),end:Math.max(from,to),limited:true};
    }
    setReviewRange(start,end,enable=true) {
      if (!this.jobId) return false;
      if (!Number.isInteger(start) || !Number.isInteger(end) || start<0 ||
          end>=this.count || start>end) return false;
      if (this.rangeStart) this.rangeStart.value=String(start);
      if (this.rangeEnd) this.rangeEnd.value=String(end);
      if (this.rangeEnabled) this.rangeEnabled.checked=enable;
      if (this.active) this.pause();
      this.seek(start);
      return true;
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
      this.onFrame?.({frame:this.frame,fps:this.fps,frames:this.count,
        sample,previewSampleFrame:this.positions[sample]});
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
      const range=this.reviewRange();
      if (this.frame<range.start || this.frame>=range.end) this.seek(range.start);
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
      const range=this.reviewRange();
      if (next>range.end || next<range.start) {
        if (this.loop.checked) {
          next=range.start+((Math.max(0,next-range.start))%(range.end-range.start+1));
          this.frameAtStart=next;
          this.startMs=now;
          if (audio && this.shouldSync?.() && audio.readyState>=1 &&
              Number.isFinite(audio.duration) && audio.duration>0) {
            audio.currentTime=Math.min(next/this.fps,Math.max(0,audio.duration-.001));
            audio.play()?.catch(error=>this.status?.('Audio replay blocked: '+error.message));
          }
        } else {
          this.draw(range.end);
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
