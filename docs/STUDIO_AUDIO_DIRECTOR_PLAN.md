# Morphorum Studio: Audio Director product and technical plan

**Status:** planning/specification only, 2026-10-11. No implementation started.
**Source of truth for backend:** `merberg-ai/Morphorum` `dev-backend`, which provides the API-only/remote LAN service. **Studio desktop UI** belongs in proposed separate `merberg-ai/Morphorum-Studio` repository.
**Priority:** music-to-motion, prompt, and seed synchronization in SDXL animations. Upscaling, other diffusion families, and extra effects are later milestones. This document does not alter or block DB1 backend-only startup.

## Product vision

Build a complete dark Windows desktop animation studio (PySide6/Qt; obsidian, midnight blue, dark purple and graphite) with **Audio Director** as the centerpiece. The soundtrack is the master timeline; users can see and edit a waveform, per-band energy, detected events, motion curves, prompt sections, and generation/seed automation together. SDXL is the first physical quality/performance target. Existing Morphorum backend performs model loading, CUDA inference, animation rendering, frame retrieval, project storage, video/audio mux and telemetry. Do not create another model stack.

## Master clock / data model

- **Audio source:** user-supplied project-owned WAV/MP3/FLAC/OGG (as supported by decoder); hash original content, decode a deterministic PCM analysis representation once; all paths are server-managed after upload, including for remote LAN clients. Do not assume a desktop client file path is a backend path.
- **Time base:** source sample timestamps and project FPS are canonical. Map audio event time `t_seconds` to project frame `round(t_seconds * fps)` **after applying explicit soundtrack offset**. Preserve both raw event time and derived frame. Enforce bounded error of at most half a video frame for quantized event display. Maintain existing imported-soundtrack convention `audio_time = motion_time + offset`; show direction clearly and do not silently reverse sign.
- **Read-only analysis:** waveform, RMS envelope, spectral-band energy, onset candidates, optionally tempo/downbeat confidence. Existing `audio_motion.py` includes frame-envelope, four practical FFT bands (kick/bass/snare/highs), onset_strength, and balanced camera pulses. This is frequency targeting, *not* reliable isolated-instrument separation; allow manual event correction and per-channel thresholds.
- **User-adjustable channels:** selectable frequency bands, detection (transient/continuous), threshold, minimum-gap, attack/release, gain, signed offset, start/end range, target, channel mute/solo, enable/disable, and visual color. Audio analysis is performed before GPU rendering, with no beat decisions depending on wall-clock render speed.
- **Automation tracks:** independent editable layers for camera motion, positive/negative prompt sections, seed policy/events, and carefully limited generation settings (noise, retention/denoise, guidance, LoRA strength only when supported). Explicit layering and user-authored overrides; don't overwrite base motion or hand-edited keyframes silently.
- **Reproducibility:** save the analyzed audio digest, analyzer version, sample rate, FFT/threshold parameters, quantized event markers, FPS, offsets, channel/rule revisions, base seed, generated anchor seed schedule, and effective render settings as a frozen render snapshot. Resume/re-export must not silently recompute different beats or change the soundtrack.

## Motion Director

- Reuse native six-axis Motion Lab layer composition and calibrated Deforum-compatible import conversion; no second renderer or uncalibrated units.
- Per-frame camera movement can react to hits, sustain, envelope, oscillation, and balanced push/return; honor axis limits, smoothing, blending, and existing layer order.
- Show per-track motion curves against waveform with editable keyframes and audible frame-synced playhead.
- Distinguish geometric preview from actual diffusion result; same compiled native camera schedules feed rendering.

## Prompt Director

- Author user-defined scenes/prompt sections with hold or supported embedding-blend transitions, markers, and manual nudge/snap to transients, beats, bars or structure change.
- Preserve Morphorum's existing per-frame positive/negative prompt resolver and model-family differences. In v1, permit events to place/snap *prompt keyframes*; no unsupported audio-to-text automatic prompt generation claim.
- Morphorum diffusion cadence means actual new conditioning is evaluated on *generation anchor* frames. Indicate cadence/anchor grid and provide a policy: snap to nearest anchor, defer to next anchor, or optionally schedule an additional anchor when renderer supports it. Never suggest sub-cadence prompt changes have already been diffused.
- A major soundtrack transition can trigger both a scene/prompt transition and matching camera action, but editor retains independent control of each.

## Seed Director

Current Morphorum `animation_resolution._resolved_seed` supports `fixed`, `increment` (base plus frame × increment), and `random`. New **audio-driven** mode requires a separate stable event/anchor schedule plus schema and render integration:

1. **Locked:** base seed remains fixed across section.
2. **Beat-change:** selected transient events cause discrete new seeds, held between events. New seed can be deterministic hash(base_seed, event_id) or constrained increments. Avoid global unseeded randomness.
3. **Phrase/scene-change:** seed changes only on selected structural markers; primary stability mode.
4. **Mutation burst:** seed change on event combined with a bounded, optionally decaying change to denoise/noise, while honoring the existing SDXL img2img retention/denoise conventions.

**Seeds are integers, not visually interpolatable values.** Do not present arithmetic interpolation of seed numbers as smooth image morphing. Noise/latent interpolation is a separate research feature only after an accepted baseline. Preserve chosen seed for each *actual diffusion anchor* and record it; for frames generated by camera warping at cadence >1, changing seed alone has no effect until the next anchor. Make this visible in the timeline. Sudden seed changes can cause incoherence/flicker; default to section-based or accent-only use with optional mutation envelopes and include clear UI controls.

## Studio workspace / UX

- Main dockable preview, track editor and contextual inspector. Dark themes: black, dark blue, dark purple, grey; accessibility and scalable text.
- **Top audio waveform** with time ruler, zoom, scroll, playback/scrub, region loops, detected beat/transient markers, source/quantization confidence.
- Stacked tracks: kick/bass/snare/highs or custom channel envelopes; six camera axes; prompt scenes/transition; seed events; generation automation; video output previews.
- Clicking a detected event displays what it will trigger: camera movement, prompt change, seed change, and any generation parameter envelope.
- Simulate/preview **event schedule and motion without loading the diffusion model**; distinguish this from GPU-rendered frame preview.
- Studio's backend connection panel supports loopback or authenticated LAN PC; local audio playback must remain frame synchronized with displayed preview. Use background networking and file transfer rather than blocking the Qt UI.
- UI shows last-generated image, render state, frame/step/progress/ETA, SDXL model details, prompt telemetry and CPU/GPU/RAM/VRAM live stats.
- Keep manual correction and per-target automation disabling. Provide presets like Ambient Drift, Bass Thrust, Breakdown Morph, Chorus Scene Change, Controlled Mutation.

## Implementation sequencing (after required backend integration foundations)

- **AD0: Timeline and file ownership prototype.** Qt multitrack ruler/playhead, waveform, source asset transfer, loopback/LAN backend connection. Data saved independently from generated video.
- **AD1: Deterministic analysis and markers.** FFT envelopes/onsets/band controls, manual hit editing, per-frame mapping and audio offset.
- **AD2: Audio-driven camera.** Layering, motion preview and six-axis render parity.
- **AD3: Prompt event automation.** Audio snap and scenes, transition windows and cadence awareness.
- **AD4: Seed event automation.** Locked/beat/phrase/mutation modes with frozen per-anchor seeds and retention envelopes; SDXL first.
- **AD5: End-to-end SDXL video.** Audio-synced motion + prompt + seed in one real 3D animation with live preview/progress; final MP4/WebM includes the correct audio, offset and FPS.
- **AD6: Polish/performance.** Handling long tracks, resume/determinism, network reconnection, recording and iterative clip-region workflows. Upscaling and other families later.

## Acceptance gates / golden scenarios

1. Synthetic soundtrack with known transient times: analyzer correctly tags raw seconds, FPS-rounded frame, and can reproduce the same derived schedule after restart.
2. Two events near the same frame: deterministic ordering, no duplicates or unbounded pulses. Change FPS/offset explicitly and verify refit/confirmation.
3. SDXL short soundtrack with kick-driven Z pulses, breakdown prompt switch and chorus seed change. Validate video by visual frames, saved manifest, frame/seed/prompt telemetry and audible track, not merely an event graph.
4. Cadence 1 vs cadence 3: camera moves each video frame but prompts/seeds change only on diffusion anchors, unless explicit extra anchors are implemented.
5. Same project, audio digest and parameters render twice with identical event/seed schedules even after save/reopen and resuming an interrupted job. Image bit-for-bit identity is not guaranteed across incompatible GPU/library environments.
6. LAN Studio client uploads soundtrack, scrubs local waveform, sees remote previews/telemetry and downloads completed video without shared-drive assumptions.
7. Old projects with no Audio Director tracks render unchanged in both normal and backend-only modes.

**Out of current scope:** automatic instrument isolation with high accuracy, direct audio-to-text generative prompts, latent interpolation, full video upscaling, new model family integration, or rebuilding Morphorum's existing API/render pipeline. All require separate design and physical acceptance.
