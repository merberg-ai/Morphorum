(() => {
  'use strict';

  const AXES = ['translation_x', 'translation_y', 'translation_z',
                'rotation_x', 'rotation_y', 'rotation_z'];
  const LABELS = ['X', 'Y', 'Z', 'Pitch', 'Yaw', 'Roll'];
  const COLORS = ['#46d5e5', '#e596d7', '#f7c265',
                  '#77aeff', '#a998fa', '#87dfb3'];
  const find = id => document.getElementById(id);
  const clamp = (value, min, max) => Math.max(min, Math.min(max, value));
  const fixed = value => Number(value).toFixed(4);

  function pathPoints(series) {
    // Native camera tracks are per-frame increments, not absolute positions.
    // Integrate from zero, omitting frame 0 (the unwarped first frame).
    const count = series.translation_x.length;
    const positions = [[0, 0, 0]];
    for (let f = 1; f < count; f++) {
      const prev = positions[f - 1];
      positions.push([
        prev[0] + series.translation_x[f],
        prev[1] + series.translation_y[f],
        prev[2] + series.translation_z[f],
      ]);
    }
    return positions;
  }

  function projectedPath(series) {
    const raw = pathPoints(series).map(([x, y, z]) => [x + 0.45 * z, -y + 0.30 * z]);
    const minX = Math.min(...raw.map(p => p[0]));
    const maxX = Math.max(...raw.map(p => p[0]));
    const minY = Math.min(...raw.map(p => p[1]));
    const maxY = Math.max(...raw.map(p => p[1]));
    const sx = Math.max(0.001, maxX - minX);
    const sy = Math.max(0.001, maxY - minY);
    const scale = Math.min(352 / sx, 228 / sy);
    const centerX = (minX + maxX) / 2;
    const centerY = (minY + maxY) / 2;
    return raw.map(([x, y]) => [
      220 + (x - centerX) * scale,
      148 + (y - centerY) * scale,
    ]);
  }

  function validateSeries(payload) {
    if (!payload || typeof payload !== 'object' || !payload.series) {
      throw new Error('No resolved motion curve data returned by the composer.');
    }
    const count = Number(payload.frames);
    const fps = Number(payload.fps);
    if (!Number.isInteger(count) || count < 1 || count > 3000 ||
        !Number.isFinite(fps) || fps <= 0) {
      throw new Error('Invalid frame count or frame rate in Motion Lab preview.');
    }
    const series = {};
    for (const axis of AXES) {
      const input = payload.series[axis];
      if (!Array.isArray(input) || input.length !== count) {
        throw new Error('Incomplete ' + axis + ' motion series.');
      }
      const numbers = input.map(Number);
      if (!numbers.every(Number.isFinite)) {
        throw new Error('Non-finite values in ' + axis + ' motion series.');
      }
      series[axis] = numbers;
    }
    return {series, count, fps};
  }

  class MotionLabVisualizer {
    constructor() {
      this.series = null;
      this.points = null;
      this.count = 0;
      this.fps = 12;
      this.frame = 0;
      this.stale = false;
      this.playing = false;
      this.tickId = 0;
      this.lastTick = null;
      this.carry = 0;
      this.status = find('animation-motion-lab-curve-state');
      this.curves = find('animation-motion-lab-curves');
      this.path = find('animation-motion-lab-path');
      this.slider = find('animation-motion-lab-frame');
      this.button = find('animation-motion-lab-play');
      this.loop = find('animation-motion-lab-loop');
      this.value = find('animation-motion-lab-frame-value');
      this.time = find('animation-motion-lab-time-value');
      this.readout = find('animation-motion-lab-axis-readout');
      this.boundTick = stamp => this.tick(stamp);
      this.slider?.addEventListener('input', () => this.setFrame(Number(this.slider.value)));
      this.button?.addEventListener('click', () => this.playing ? this.pause() : this.play());
      if (this.curves) {
        const seek = event => {
          if (!this.series) return;
          const rect = this.curves.getBoundingClientRect();
          if (rect.width < 1) return;
          const x = (event.clientX - rect.left) * 800 / rect.width;
          this.setFrame(Math.round((x - 43) / 735 * Math.max(1, this.count - 1)));
        };
        this.curves.addEventListener('pointerdown', event => {
          event.preventDefault();
          seek(event);
          this.curves.setPointerCapture?.(event.pointerId);
        });
        this.curves.addEventListener('pointermove', event => {
          if (event.buttons & 1) seek(event);
        });
        this.curves.addEventListener('keydown', event => {
          if (!this.series || !['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
          event.preventDefault();
          this.setFrame(event.key === 'Home' ? 0 : event.key === 'End' ? this.count - 1 :
            this.frame + (event.key === 'ArrowRight' ? 1 : -1));
        });
      }
    }
    clear() {
      this.pause();
      this.series = null;
      this.points = null;
      this.count = 0;
      this.frame = 0;
      this.stale = false;
      if (this.curves) this.curves.replaceChildren();
      if (this.path) this.path.replaceChildren();
      if (this.slider) { this.slider.value = '0'; this.slider.disabled = true; this.slider.max = '1'; }
      if (this.status) this.status.textContent = 'Curves not compiled';
      if (this.button) this.button.disabled = true;
      if (this.value) this.value.textContent = '0 / 0';
      if (this.time) this.time.textContent = '0.00s';
      if (this.readout) this.readout.textContent = 'Add a layer and select Update Curves.';
    }
    invalidate() {
      if (!this.series) return;
      this.stale = true;
      this.pause();
      if (this.status) this.status.textContent = 'Draft changed · Update Curves';
      if (this.curves) this.curves.dataset.stale = 'true';
      if (this.path) this.path.dataset.stale = 'true';
    }
    setData(data) {
      const {series, count, fps} = validateSeries(data);
      this.pause();
      this.series = series;
      this.count = count;
      this.fps = fps;
      this.stale = false;
      this.points = projectedPath(series);
      this.frame = clamp(this.frame, 0, count - 1);
      if (this.curves) this.curves.dataset.stale = 'false';
      if (this.path) this.path.dataset.stale = 'false';
      if (this.slider) { this.slider.max = String(count - 1); this.slider.disabled = count <= 1; }
      this.draw();
      this.setFrame(this.frame);
      if (this.status) this.status.textContent = count + ' frames · ' + fps + ' FPS · draft curves';
      if (this.button) this.button.disabled = count <= 1;
    }
    draw() {
      if (!this.series) return;
      const lines = ['<rect width="800" height="300" fill="transparent"/>'];
      const groupCenters = [86, 226];
      for (let group = 0; group < 2; group++) {
        const center = groupCenters[group];
        const axes = AXES.slice(group * 3, group * 3 + 3);
        const maximum = Math.max(0.0001, ...axes.flatMap(axis => this.series[axis].map(Math.abs)));
        for (let fraction = -1; fraction <= 1; fraction += 1) {
          const y = center + fraction * 48;
          lines.push('<line x1="43" y1="' + y + '" x2="778" y2="' + y +
                     '" stroke="currentColor" stroke-opacity="' + (fraction ? '.12' : '.34') + '"/>');
        }
        lines.push('<text x="8" y="' + (center - 58) + '" fill="currentColor" opacity=".7" font-size="11">' +
                   (group ? 'ROTATION °/FRAME' : 'TRANSLATION /FRAME') + '</text>');
        lines.push('<text x="3" y="' + (center - 37) + '" fill="currentColor" opacity=".5" font-size="10">' + maximum.toFixed(3) + '</text>');
        axes.forEach((axis, offset) => {
          const i = group * 3 + offset;
          const pts = this.series[axis].map((v, f) =>
            (43 + f * 735 / Math.max(1, this.count - 1)).toFixed(2) + ',' +
            (center - v / maximum * 48).toFixed(2)).join(' ');
          lines.push('<polyline points="' + pts + '" fill="none" stroke="' + COLORS[i] +
                     '" stroke-width="2.2" stroke-linejoin="round" stroke-linecap="round"/>');
        });
      }
      lines.push('<line id="ml1-curve-marker" x1="43" y1="12" x2="43" y2="289" stroke="#fff" stroke-width="1.6" stroke-dasharray="4 3"/>');
      if (this.curves) this.curves.innerHTML = lines.join('');
      const pts = this.points.map(([x,y]) => x.toFixed(2) + ',' + y.toFixed(2)).join(' ');
      const path = [
        '<rect width="440" height="300" fill="transparent"/>',
        '<line x1="220" y1="14" x2="220" y2="282" stroke="currentColor" opacity=".1"/>',
        '<line x1="20" y1="148" x2="420" y2="148" stroke="currentColor" opacity=".1"/>',
        '<polyline points="' + pts + '" fill="none" stroke="#41c9d4" stroke-width="3" stroke-linejoin="round" stroke-linecap="round"/>',
        '<circle cx="' + this.points[0][0] + '" cy="' + this.points[0][1] + '" r="4" fill="#87dfb3"/>',
        '<circle id="ml1-path-marker" cx="' + this.points[0][0] + '" cy="' + this.points[0][1] + '" r="7" fill="#f7c265" stroke="#101922" stroke-width="2"/>'
      ];
      if (this.path) this.path.innerHTML = path.join('');
    }
    setFrame(next) {
      if (!this.series) return;
      this.frame = clamp(Math.round(Number(next) || 0), 0, this.count - 1);
      if (this.slider) this.slider.value = String(this.frame);
      if (this.value) this.value.textContent = this.frame + ' / ' + (this.count - 1);
      if (this.time) this.time.textContent = (this.frame / this.fps).toFixed(2) + 's';
      const x = 43 + this.frame * 735 / Math.max(1, this.count - 1);
      const marker = this.curves?.querySelector('#ml1-curve-marker');
      if (marker) { marker.setAttribute('x1', x.toFixed(2)); marker.setAttribute('x2', x.toFixed(2)); }
      const pathMarker = this.path?.querySelector('#ml1-path-marker');
      if (pathMarker && this.points) {
        pathMarker.setAttribute('cx', this.points[this.frame][0].toFixed(2));
        pathMarker.setAttribute('cy', this.points[this.frame][1].toFixed(2));
      }
      if (this.readout) {
        this.readout.replaceChildren();
        AXES.forEach((axis, i) => {
          const cell = document.createElement('span');
          cell.className = 'animation-motion-lab-axis-value';
          cell.style.borderColor = COLORS[i];
          cell.textContent = LABELS[i] + ': ' + fixed(this.series[axis][this.frame]);
          this.readout.appendChild(cell);
        });
      }
    }
    play() {
      if (!this.series || this.stale || this.count <= 1) return;
      this.pause();
      this.playing = true;
      this.lastTick = null;
      this.carry = 0;
      if (this.button) this.button.textContent = 'Pause';
      this.tickId = requestAnimationFrame(this.boundTick);
    }
    tick(stamp) {
      if (!this.playing || !this.series) return;
      if (this.lastTick === null) this.lastTick = stamp;
      this.carry += Math.min(1000, Math.max(0, stamp - this.lastTick));
      this.lastTick = stamp;
      const steps = Math.floor(this.carry * this.fps / 1000);
      if (steps > 0) {
        this.carry -= steps * 1000 / this.fps;
        const next = this.frame + steps;
        if (next >= this.count) {
          if (this.loop?.checked) this.setFrame(next % this.count);
          else { this.setFrame(this.count - 1); this.pause(); return; }
        } else this.setFrame(next);
      }
      this.tickId = requestAnimationFrame(this.boundTick);
    }
    pause() {
      this.playing = false;
      if (this.tickId) cancelAnimationFrame(this.tickId);
      this.tickId = 0;
      this.lastTick = null;
      if (this.button) {
        this.button.textContent = 'Play';
        this.button.disabled = !this.series || this.count <= 1 || this.stale;
      }
    }
  }

  window.MorphorumMotionLabVisualizer = MotionLabVisualizer;
})();
