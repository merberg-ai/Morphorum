# Prompt Studio (PS0–PS9) — Implementation Roadmap

**Status:** PS0 documented; PS1.1 bridge and PS1.2 guarded saves Windows-accepted; PS1.3 manual Prompt Studio workspace under test on dev-webui (2026-10-21)  
**Development branch:** `dev-webui`; preserve `main` until separately approved promotion of tested changes.  
**Purpose:** Native, model-aware, optionally LLM-assisted storyboard, prompt sequence, timeline and audio-cue authoring for Morphorum animation projects.  
**Current gate:** PS0 authorized and documented in [PS0 contract baseline](PROMPT_STUDIO_PS0_CONTRACT.md), with design fixtures. This does **not** authorize implementing PS1+ or merging experimental code.

## 1. Intended experience

- Open **Prompt Studio** from Morphorum, optionally linked to the currently opened project. Read the project's model ID/family, max frames, FPS, start image/input media, prompt keyframes (positive/negative), prompt-transition policy and supported LoRA metadata. Display data source and unsaved status.
- **Import Existing Prompts** into an isolated Studio draft, preserving exact existing text, LoRA tags, keyframe positions and negative prompts. Never silently overwrite active Project Editor edits.
- Enter a story idea, scene descriptions, or use a project-owned start image. Optionally ask an LLM to create an ordered storyboard, establish continuity rules and optimize prompts for the selected **SDXL, FLUX or supported managed Z-Image** model.
- Edit the results without an LLM: visual draggable keyframes, per-scene prompts, LoRA/trigger-word placement, Hold/Blend preview, snap/zoom, bulk move, undo/redo, frame/seconds readouts and resolved-frame inspector.
- **Sync to soundtrack** using Motion Studio's existing WAV analysis, beat/cue timeline, selected beat markers and audio provenance. Suggest scene cuts/reveals on chosen musical events, preview alignment, manually lock/move timings and explicitly apply them.
- **Save/Load Prompt Studio** drafts independently; **Apply to Animation** previews and transfers native prompt/keyframe changes into the Project Editor's *unsaved draft*. Use the existing explicit Save Project action, optimistic-concurrency checks and project archive conventions.
- Unconfigured/offline LLM is never an error for manual authoring; no account, cloud service or download is mandatory.

## 2. Non-negotiable architecture

1. **One renderer and frame resolver.** Prompt Studio authors existing native project prompt tracks; it does not add a parallel diffusion renderer or independently evaluate runtime schedules. Use `animation_timeline.py`, `animation_resolution.py`, `animation_projects.py`, `animation_render.py`, `animation_preflight.py` and the existing Project Editor workflow.
2. **No destructive import or silent save.** Import creates/edit an isolated studio draft. Apply presents frame/keyframe/LoRA and existing-edit conflicts first, writes *only* supported prompt fields into the editor draft, and requires explicit Save Project. Preserve existing prompts until the user confirms replacements. Handle concurrent edits and project switching.
3. **One consistent timebase.** Valid discrete frames are `0..max_frames-1`; duration `max_frames/fps` seconds. Convert proposed times/beat timestamps to bounded integer frames deterministically, with declared rounding/snap policies and collision resolution. Do not assume 24 FPS or conflate final frame number with frame count.
4. **Model-family honesty.** Detect actual saved/selected model and capabilities; identify unsupported or unverified controls. Native SDXL already supports long-prompt chunking and embedding interpolation; FLUX and managed Z-Image behavior, negative prompts, and LoRA transitions must be verified separately. Never present text blending as equivalent to embedding interpolation.
5. **LoRA controls are user-owned.** Model-family filtered local adapters only. Reuse Civitai-cached triggers and preview thumbnails as optional metadata. Preserve exact `<lora:name:weight>` tags/weights from imported prompts; avoid duplicate triggers; never automatically download, enable, remove, reweight or invent adapters. Prompt serialization must preserve recognized literal text and user-ordered sections.
6. **Strict AI output boundary.** LLM returns *structured, schema-validated suggestions*, not executable code, Python snippets, Parseq formulas, direct project JSON patches or untrusted runtime schedules. Clamp/reject invalid frame counts, FPS, scene durations, weights, model identifiers, huge outputs, dangerous local paths and unknown settings; reject rather than hallucinate support.
7. **Parseq coexists, not merged into PS.** The independent [PQ0–PQ7 Parseq URL roadmap](PARSEQ_URL_INTEGRATION_ROADMAP.md) remains authoritative for hosted external scheduling. If enabled Parseq overrides runtime prompts, visibly warn that edited native prompts may not govern renders. No stealth toggling of Parseq, no bi-directional writeback and no modification of its published manifests. Resolve effective frames through the shared pipeline.
8. **No GPU resource surprises.** Avoid concurrent loading of managed LLM and large diffusion pipeline on a 16 GB GPU; provide explicit unload and VRAM guards. An external Ollama host on a trusted LAN is allowed through an opt-in backend connection.
9. **Provenance and portability.** Save studio-draft schema version, project/model reference, positive/negative prompts, frame positions, LLM/profile identification, input media references and optional audio cue provenance; distinguish source inputs vs generated suggestions. No fabricated claims of rendered quality or physical tests.
10. **Safety and privacy.** Browser WebUI is unauthenticated on trusted LAN; no arbitrary external fetch, path traversal, credential logging or LAN-to-public exposure through a user-controlled Ollama URL. Local/LAN endpoint validation, request limits, timeouts, redaction and explicit media sharing apply. No automatic upload of input images or audio to third-party hosted models.

## 3. Planned workspace

**Project Context bar:** project name, model checkpoint/family and readiness, FPS, max frames and duration, source media preview (when available), prompts imported/unsaved indicators, supported negative-prompt and LoRA capabilities.

**Story Director:** story/idea text input; target pacing, number of scenes, mood/style, narration-free visual constraints and user-defined recurring characters/objects. Continuity Bible stores immutable and scene-variable details. Offer *Build Storyboard*, *Optimize Sequence*, *Enhance Selected Scene*, *Regenerate Selected Only* and *Review Consistency*. Preserve user locks and present before/after diffs.

**Structured Prompt Composer:** reorderable LoRA directives, cached trigger words, character/setting/style blocks, scene action, optional negative prompt. Support shared/global blocks plus scene-level overrides, prefix/suffix/custom order, duplication warnings, exact generated text preview and token/chunk diagnostics where available.

**Timeline:** draggable zero-indexed prompt keyframes, scrub/inspect, scene range visualization, Hold/Blend choice, easing preview where actually supported, snap to frames/seconds and optional beats, lock/unlock positions, multi-select, undo/redo, keyboard and touch gestures. Use existing Motion Lab visual interaction conventions; accessible mobile full-width editor with horizontal scrolling.

**Resolved Frame Inspector:** selected frame/time, actual prompt/negative text, interpolation endpoints/weights when supported, active LoRAs, unsupported features, and conflicts with enabled Parseq. Compare against the canonical Morphorum resolver and show when preview cannot prove render-family parity.

**Save/Apply:** standalone draft library with load/save/duplicate, optional project attachment in the existing project archive, diff and confirmation against Project Editor; preserve unsaved changes and stale-write safeguards.

## 4. Provider and model strategy

**Priority A: Existing Ollama, host-local and LAN.** Backend-managed configured endpoint (local `http://127.0.0.1:11434` by default), connection test, discovery of installed models, text vs image input capability checks, cancellation, structured-output schema, progress/errors and response validation. LAN mode requires user opt-in and trusted-network guidance; reject public/untrusted endpoints by default. Never expose server filesystem paths or arbitrary image data in logs.

**Priority B: Native managed local LLM.** After provider-independent contracts pass, assess a separately installed, explicitly downloaded GGUF runtime (for example, llama.cpp-style backend), independently verified artifact provenance, accepted third-party licenses, host platform/CPU support, caching, resource limits, unload controls and rollback. No bundled weights. Prefer a small candidate first; choose specific model versions only after measured structured-output accuracy, visual comprehension and Windows 16 GB VRAM performance. Qwen-family 4B/9B variants are *evaluation candidates*, not promised defaults.

**Profiles:** versioned SDXL, FLUX and managed Z-Image prompt-authoring profiles. Separate creative scene planning from renderer-specific syntax optimization. Keep existing LoRA tags/trigger words untouched unless user authorizes explicit edits. For SDXL count actual CLIP chunks/tokens with renderer-provided diagnostics where possible; no universal 77-token truncation claim. Do not assume all models use negative prompts, CFG or identical blend conditioning.

**Vision:** a supported image-aware model may describe *only* the currently attached, user-selected start image/asset, with an explicit preview of the content sent to the selected provider. Fail gracefully when text-only. Audio waveform/beat features do not require the LLM to ingest full audio.

## 5. Audio-to-storyboard synchronization (required feature)

This is a **committed, named scope** of Prompt Studio, not a speculative future wish-list feature.

- Reuse **Motion Studio** analysis/cue data and attached project WAV/media. Read verified duration, timebase, sample/index identity, beat cues, intensity/selected markers, optionally channel tags or arrangements when available. Do not implement a duplicate beat detector or claim AI hears the waveform if no audio-capable model is used.
- Offer **Match scenes to selected beats**, **Align reveals/climaxes**, **Distribute scenes between musical sections** and manual snapping. Scene/story LLM can suggest *which* beats matter, but discrete timing/quantization must be deterministic and editable.
- Map marker time to integer animation frames using active FPS; show exact beat timestamp vs snapped frame/time and drift. Warn for markers outside duration, differing audio versions, sparse/dense cues, conflicting locked keyframes, cadence constraints and bad/missing analysis.
- User selects allowable cue types and sensitivity; retain existing locked prompt keyframes. Preview before/after beat markers and scene blocks, allow move/undo/redo, and apply only on explicit confirmation. Preserve positive/negative prompts, LoRAs and model identity.
- Soundtrack attachment and Motion Studio motion tracks are **read-only** for this operation; never overwrite an existing audio source or camera motion. Save cue provenance (media identity/hash where available, analysis version or identifier, cue selection, mapping policy), so project reload or audio replacement produces detectable stale-alignment warnings.
- Mobile timeline shows musical events and snaps with usable touch targets. Tests cover non-24 FPS, max-frame edges, adjacent beats on same frame, manual locks, missing/stale cues and repeatable round-trips.

## 6. Milestones and owner acceptance

### PS0 — Baseline, schema and architecture (design-only code contract)
**Design artifacts prepared for review on `dev-webui`:** [PS0 contract baseline](PROMPT_STUDIO_PS0_CONTRACT.md) and `tests/fixtures/prompt_studio/*.json` synthetic fixtures. The audit maps current fields, import/apply hazards, ETag gap, Hold/Blend behavior, LoRA/trigger preservation, SDXL/FLUX/Z-Image render-conditioning code paths, audio markers/cues and current 3000-frame analyzer limits. Draft v1 schema, migration/ZIP policy and acceptance matrix are proposed, **not implemented or executed**. **Gate:** owner contract review before PS1; no runtime modifications in PS0.

### PS1 — Native project context and non-destructive prompt import/apply

**Progress:** PS1.1 communication bridge and PS1.2 guarded saves passed owner Windows acceptance. PS1.3 adds a visible Project-menu workspace with explicit import of the unsaved Editor prompt draft, independent positive/negative keyframe text/frame editing, Hold/Blend, reset, diff preview and confirmation-gated apply to unsaved Project Editor. Studio draft remains browser memory only. Persisted/portable drafts, visual drag/snap timeline, archive integration and PS1.3 physical acceptance are not yet completed.
Add Prompt Studio navigation/workspace and read-only project context. Implement explicit import/round-trip of existing prompt keyframes, positive/negative text, LoRA directives and transition mode, with draft lifecycle. Apply via existing Project Editor *unsaved* model, diff/confirm and Save Project; conflict/stale checks and archive compatibility. **Gate:** Windows load/import/edit/apply/save/reload; no camera/generation/media changes.

### PS2 — Visual prompt timeline and frame inspector
Desktop/touch keyframe lanes, scene order/durations, frame-time labels, drag/snap/zoom, duplicate/delete, evenly space, locks, multi-select, undo/redo and scrub. Canonical frame inspector using the same resolved-frame path as generation. Start with existing Hold/Blend behavior, no new interpolator. **Gate:** edge frames, drag collisions, mobile tests, exact prompt-state parity.

### PS3 — Structured composer and LoRA metadata
Shared/global and scene-local blocks; prefix/suffix placement; cached Civitai LoRA thumbnails/trigger words; family filter; exact prompt preview and duplication diagnostics. Make import and export lossless, with a raw-text escape hatch. LoRA weights remain user-confirmed. **Gate:** SDXL and managed Z-Image LoRA round-trips with no unwanted tag rewriting; FLUX controls only when supported.

### PS4 — Ollama local/LAN provider and structured storyboards
Settings, test connection, model selection/capabilities, cancellation/timeouts/error UX, optional vision metadata, strict schema output, and story→scene→frame compiler. Add continuity bible, targeted scene regeneration, AI suggestion diff/accept/undo. No automatic prompt application. **Gate:** local Windows Ollama and LAN mock/live testing; offline/no-model manual path unaffected; all AI output validation.

### PS5 — Family-aware refinement and input-image analysis
Independent versioned SDXL/FLUX/managed Z-Image prompt profiles; optional start-image description by vision-capable model; visual consistency locks, negative prompt and token/chunk diagnostics. Benchmark candidate 4B/9B local models with representative horror, character, landscape, and mixed-LoRA scenes; do not adopt a default based on model marketing. **Gate:** family-specific physical render spot checks; no invented support for unsupported model controls.

### PS6 — Audio-to-storyboard sync using Motion Studio
Implement the **required audio feature from section 5**: cue import, beat lane, marker snapping, scene arrangement proposals, deterministic frame mapping, diff/apply, stale audio provenance, manual locks and mobile interaction. AI proposes creative pacing but existing analysis determines timestamps. **Gate:** a user-attached WAV, verified Motion Studio markers, synced scene changes and short Windows rendered animation with confirmed audio alignment. Test beat sync with AI disconnected.

### PS7 — Advanced transitions, blending and Parseq interoperability
Expose editable weighting/easing where the underlying native renderer supports it. SDXL first with actual embedding behavior, LoRA transition diagnostics, and long-prompt test cases. Gate FLUX and managed Z-Image separately; display disabled/unsupported rather than claim parity. Warn explicitly about Parseq-controlled runtime prompts. **Gate:** frame-accurate resolver tests + real Windows GPU transition comparisons; no changes to remote Parseq manifests.

### PS8 — Optional Morphorum-managed LLM
Opt-in managed runtime/model installation, SHA verification, license presentation, storage accounting, CPU/GPU mode detection, resource handling and clean unload before diffusion. Fail safely on interrupted downloads and never modify existing managed Z-Image. **Gate:** fresh Windows 16 GB install, offline control, repeated loading/unloading and image render afterward; Linux verification tracked separately.

### PS9 — Regression, documentation and promotion review
Run project ZIP/export/Save As, editing conflicts, saved drafts, SDXL/FLUX/managed Z-Image, prompt conditioning/LoRAs, audio cue sync, mobile, Parseq coexistence, full backend/frontend CI, installers and render/resume. Update README, current status, Help, TODO, design docs and third-party licenses/attributions. Mark owner physical checks explicitly vs automated CI. **Gate:** user approves merge to `main` separately.

## 7. Acceptance matrix (minimum)

- Project: no project open; new/load/save/switch; unsaved editor; stale concurrent edits; import exact old prompts; draft version migration; Save As; ZIP archive with only allowed project-owned input media; invalid or absent model.
- Timing: FPS 12/23.976-equivalent where supported/24/30, 1 and 2 frames, 543 frames, final keyframe `max_frames-1`, duplicate/out-of-range frames, seconds→frames rounding, snapped cue collisions, locked scenes and preserving scene order.
- Prompts: positive/negative, literal LoRA-like text, unknown trigger words, multiple LoRAs, different family, long SDXL CLIP conditioning, empty scenes, undo/redo, step/hold, validated supported blends.
- AI: no provider; offline Ollama; bad endpoint; unreachable/malformed response; strict schema; hallucinated frames/families/LoRA; excessive length; cancellation; vision absent or denied; resource exhaustion; prompt injection in story/image description treated as data.
- Audio: no soundtrack; WAV available with no analysis; selected vs unselected beat cues; clip shorter/longer than animation; changed audio after draft; deterministic snapped frames and provenance; AI-free synchronization; beat-aligned render output.
- Parseq: disabled; enabled external prompt override; stale/missing remote source; native preview must not misrepresent actual runtime ownership. No automatic remote fetch as part of PS.
- Security/performance: SSRF/LAN restrictions, no credentials logged, image/audio opt-in, no arbitrary file reads, large malicious payload limits, VRAM unload boundary, cross-platform start/stop.

## 8. Implementation safeguards and candidate files

Inspect before touching (not necessarily exhaustive): `backend/morphorum/animation_projects.py`, `animation_timeline.py`, `animation_resolution.py`, `animation_render.py`, `animation_preflight.py`, `project_archive.py`, audio/Motion Studio analysis modules and `frontend/dist/assets/animation.js`, `motion-lab-*.js`, `loras.js`, project wizard/client state and related tests. Candidate new isolated `prompt_studio_*.py` backend units and `frontend/dist/assets/prompt-studio.*` UI assets should depend on existing validated project/frame contracts.

Build one phase at a time on `dev-webui`. Run automated CI and request explicit Windows owner acceptance at each physical-gate phase. Do **not** implement PS1+ automatically, silently change native project schema, or merge PS implementation into `main` without separate authorization. Keep separate PQ roadmap untouched.

**Related plans:** [PQ: Parseq hosted-manifest URL integration](PARSEQ_URL_INTEGRATION_ROADMAP.md), [Motion Studio](MOTION_STUDIO.md), [SDXL generation](SDXL_GENERATION.md), [Project archives](PROJECT_ARCHIVES.md), and [TODO](../TODO.MD).
