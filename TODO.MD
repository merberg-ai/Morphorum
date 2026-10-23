# Morphorum TODO

Deferred investigations and improvements. These entries are **not** release blockers unless a later test demonstrates a functional failure.

## PQ: Parseq hosted-manifest URL integration (planned 2026-10-20)

**Status:** Roadmap only, **NOT IMPLEMENTED**. Owner selected **Option A**: use the external Parseq editor and a saved, stable hosted JSON URL rather than rebuilding Parseq. The authoritative staged plan is [PQ Parseq URL Integration Roadmap](docs/PARSEQ_URL_INTEGRATION_ROADMAP.md), phases **PQ0–PQ7**.

- Keep work on `dev-webui`; `main` unchanged. Start implementation only when owner explicitly requests PQ0.
- Save the Parseq URL once per Morphorum project; fetch/validate the latest published JSON before each new automatic render; **freeze a verified immutable manifest per render/resume**. No silent fallback to old JSON when source is unavailable.
- Reuse existing Morphorum frame resolver, motion previews, SDXL/FLUX/managed Z-Image renderer, save/conflict rules and project archives. Map supported fields with explicit ownership; do not execute Parseq expressions or replace native tracks.
- Safeguard HTTP fetching (SSRF, private DNS/redirects, size/time limits, token redaction), cross-model guidance/retention semantics, 2D/3D delta conversions, prompt/LoRA handling, FPS/frame counts, and source provenance.
- Require golden fixtures, automated regressions, owner Windows GPU gates and explicit approval before any main merge. Mobile physical testing cannot be marked PASS unless performed.

**Next step when authorized:** PQ0 upstream contract/fixtures/threat-model baseline only. Do not implement PQ1+ preemptively.

## PS: Native Prompt Studio and AI storyboard authoring (planned 2026-10-21)

**Status:** **PS0–PS5.3 UI accepted on Windows; PS6.1 Motion Studio cue import, non-destructive scene-alignment preview and collapsible Studio sections implemented on `dev-webui`, Windows test pending; `main` unchanged.** [PS0 baseline and gaps](docs/PROMPT_STUDIO_PS0_CONTRACT.md) · [PS0–PS9 roadmap](docs/PROMPT_STUDIO_ROADMAP.md). Keep native renders/project saves and `main` unchanged; PS6.1 saved/detected WAV marker and frame-alignment physical acceptance is the next gate; formal cross-model render studies remain optional evidence rather than an untested model default.

- Standalone/manual Prompt Studio that reads the active animation project (model/family, max frames, FPS, start image, current positive/negative prompts, LoRAs) and optionally imports existing prompt keyframes into an isolated editable draft.
- Visual frame timeline, structured LoRA/trigger-word placement, scene continuity, exact resolved-frame inspection and supported Hold/Blend/advanced transitions; never invent unsupported family-specific render semantics.
- Optional AI Story Director with local/LAN Ollama first, validated structured scenes, versioned SDXL/FLUX/managed Z-Image prompt profiles, optional vision of user-selected start images, and later optional verified managed LLM.
- **PS6 is a required audio-to-storyboard synchronization milestone:** reuse Motion Studio's existing soundtrack/beat/cue analysis, align scene entrances and climaxes to chosen beats using deterministic FPS/frame snapping, provide manual locks, timeline preview and diff/undo; support offline/manual beat alignment and do not replace audio or motion schedules.
- Save/load reusable Studio drafts; **Apply to Animation** updates only the existing Project Editor's *unsaved prompt draft* after confirmation, preserving current project conflict checks. Explicit Save Project commits changes.
- Coexist with the independent PQ hosted-Parseq roadmap. If Parseq overrides runtime prompts, warn before applying native prompts, and never modify hosted Parseq manifests. No parallel renderer, automatic LoRA downloads or silently changed model settings.
- Physical Windows GPU owner verification and existing CI gates per PS milestone; later merge requires explicit owner signoff. Preserve incomplete PQ and experimental external Z-Image gating.

**PS1.2 (2026-10-21):** Core Editor Save Project, form autosave before timeline edits, the four native timeline mutation routes, project rename, audio length matching and Motion Lab's Editor pre-save/direct Apply now use revision-aware conditional writes. Timeline backend changes are atomic and return a fresh ETag; stale saves keep unsaved form edits. Studio-staged prompts block indirect duration/Motion Lab saves. **CI and owner acceptance are separate gates.** Source-image upload/clear now have guarded writes; soundtrack, ZIP and other independent API mutations still warrant a separate concurrency audit. No Studio workspace or draft library; do not merge main without approval.

## Z-Image Turbo LoRA stability and animation coherence (reported 2026-10-19)

**Status:** **ZL1 passed on Windows and released on `main` in PR #51 (2026-10-21)**. The owner reported successful managed Z-Image still generations with and without LoRAs and an animation without the previous inference-tensor exception. The fix preserves managed Z-Image group offloading; [release merge](https://github.com/merberg-ai/Morphorum/pull/51). **ZT1 remains open** for animation temporal coherence and has not been modified.

### ZL1: Managed Z-Image + LoRA inference stability (bug)

**Observed:** Managed Z-Image Turbo animation completes when the `<lora:Horror Style ZIT:1>` directive is removed from an otherwise unchanged prompt, but fails after a few generated frames when that LoRA is active. The same error has also occurred intermittently during single-image generation with a LoRA:

```text
Setting requires_grad=True on inference tensor outside InferenceMode is not allowed.
```

**Fix and verification (2026-10-20):** Managed Z-Image keeps group offloading, but its still-image inference, animation-anchor inference, and blended prompt encoding use `torch.no_grad()` instead of `torch.inference_mode()`. The inferred failure mechanism is that Diffusers offloading can create inference tensors in PEFT adapter parameters, conflicting with a later `requires_grad_(True)` operation. SDXL and FLUX retain their previous inference contexts. CPU regression coverage exercises repeated adapter activation/disable/reweight cycles and blended Z-Image conditioning. GitHub Actions backend tests passed (run 39421028500, commit e0c88ee). User verified on physical Windows GPU: multiple managed Z-Image generations both with and without LoRAs, and an animation, without recurrence of the reported error.

**Acceptance:** **Passed by user report** for repeated physical Windows GPU still-image generation with and without LoRAs, and an animation without recurrence of the reported error. Automated CPU tests passed. The exact animation length, number of diffusion anchors, and LoRA scheduling variations were not separately recorded, so this is not a claim of exhaustive coverage. Keep the regression tests in place and reopen if the exception recurs.

### ZT1: Z-Image animation temporal coherence (quality improvement)

**Observed:** Managed Z-Image animation renders successfully without LoRA but can look like a sequence of substantially reimagined stills instead of the smoother frame-to-frame progression seen with SDXL. This is a subjective quality report, not yet a proven renderer defect.

**Investigation / proposed work:**
- Inspect per-frame img2img handoff, transformed frame feedback, fixed/incremented seeds, added pixel noise, cadence, step count, and prompt/LoRA transitions. Compare short renders with controlled settings and identical camera motion.
- Explicitly expose/document Morphorum's **retention** Strength convention: Diffusers `img2img strength = 1 - Morphorum retention strength`. Higher Morphorum Strength retains more of the preceding frame.
- Establish an empirical Z-Image Turbo baseline: try retention Strength `0.75` (denoise `0.25`), 9 steps, guidance 0, noise 0, cadence 1, fixed seed; compare to retention `0.65` and other values. These are *test settings*, not validated defaults. Check effective step counts at low denoise strengths.
- Investigate model-aware Smooth / Balanced / Creative animation presets and appropriate Z-Image-specific defaults. Apply only to newly chosen presets/new projects; never silently overwrite saved projects or other model-family settings.
- Consider bounded per-frame visual-change diagnostics; evaluate motion-aware temporal methods (including optional optical-flow interpolation or depth-aligned blending) only if strength/noise/step tuning does not provide acceptable continuity.
- Compare visual continuity, subject identity, motion smoothness, output detail, and render time against SDXL on the same short animation; retain existing SDXL/FLUX paths.

**Acceptance:** A short Z-Image test animation shows visibly steadier frame-to-frame subject/scene continuity without collapsing motion or detail; settings are explicit, reproducible, and documented. Complete ZL1 before reintroducing LoRAs to these quality tests.

## SDXL LoRA diagnostics and console warnings (deferred, 2026-10-18)

**Status:** Current SDXL single-image generation appears to work. Investigate later; do not suppress warnings without understanding them. Findings came from a Windows console capture plus the Image section's SDXL LoRA verification card on `dev-webui`.

- **Adapter teardown warnings:** PEFT warns that an active `morphorum_…` adapter was deleted and automatically switches to another adapter. Inspect the cleanup/retry path, ensure no unintended active-adapter switching or stale LoRA effects, and consider lower-noise diagnostics only after proving correctness.
- **Transformers CLIP `MISSING` load reports:** Large reports include adapter parameters newly initialized during intermediate loading/retries. The later checkpoint comparison verified the CLIP weights for five adapters, so do not equate intermediate reports with a final loading failure. Confirm expected loader behavior and whether any unexpected key initialization survives in final active adapters.
- **Unmatched `alpha_pattern` keys:** PEFT says several `*.processor.to_*_lora.down.weight` entries do not match target modules and are ignored. Trace the source checkpoint(s), key conversion, and per-module network alpha handling. Determine whether the effective UNet scaling differs from the source and add precise warnings/tests if necessary.
- **Unverified LoRA:** `BloodPunkAIp` at strength `0.400` reports **Active; source weight comparison unavailable**. Determine whether it uses the normal load path, UNet-only structure, or unsupported source comparison; improve verification honestly without relabeling as verified.
- **Long SDXL prompt:** Transformers warned about `121 > 77` CLIP tokens. Check whether Morphorum's chunked prompt conditioning handled the actual render, and confirm that the warning is not hiding truncation or indexing errors.
- **Zero-strength LoRA:** `ral-melting-sdxl_217057` was verified as loaded at strength `0.000`; exclude it from claims about visible stylistic contribution even if listed as active.

### Physical verification snapshot

| LoRA | CLIP result | Strength |
| --- | --- | ---: |
| DonM1ns0mn14XL | CLIP-L 144/144, CLIP-G 384/384 matched | 0.600 |
| DonMCr33pyD0115XL_529922 | CLIP-L 144/144, CLIP-G 384/384 matched | 0.200 |
| aidmaPsychadelicChaosWorldMorphXL-V0.1 | CLIP-L 144/144, CLIP-G 384/384 matched | 0.600 |
| BloodPunkAIp | Active; source comparison unavailable | 0.400 |
| zkeleton-sdxl | CLIP-L 144/144, CLIP-G 384/384 matched | 0.200 |
| ral-melting-sdxl_217057 | CLIP-L 144/144, CLIP-G 384/384 matched | 0.000 |

**Proposed later work:** An isolated `G5.6` diagnostics milestone with source-aligned alpha/key checks and actionable summaries. Keep actual inference, verified-LoRA behavior, and managed Z-Image unchanged. Run tests on `dev-webui` before any future merge.

## Project Editor prompt/keyframe UX

The Prompt Studio PS0–PS9 roadmap supersedes this open-ended item. PS0–PS5.3 have owner UI acceptance; PS6.1 read-only audio preview requires Windows testing, and PS6.2–PS9 require separate implementation/acceptance gates.

### PS1.3 Prompt Studio manual workspace (2026-10-21)

Project → Prompt Studio and the Editor's Prompt Keyframes shortcut now open a **manual-only** Prompt Studio page. Import Existing Prompts snapshots live/unsaved Editor prompts; separate positive/negative lanes support text/frame/transition edits, frame-zero protection, add/remove/move with collisions refused. Preview Changes shows a diff before confirmation-gated Apply to Animation; Apply updates the unsaved Project Editor only, never project.json or camera/media/other schedules. Reset Draft restores the import; Studio drafts are **in memory only** (lost on browser reload) until later persistence work. No AI/LoRA composer, audio synchronization, or draggable timeline yet. User Windows/mobile acceptance needed before more phases.

### PS1.4 Persistent Prompt Studio drafts (2026-10-21)
- Draft format `morphorum.prompt-studio-draft` v1 at `<project>/prompt_studio/drafts/<32hex>.json` is separate from `project.json`. Max 30 drafts per project and 8 MiB per draft; exact lane text/LoRA tags, frame order, model and timing validated.
- Project draft API: list/create/get/update/delete. ETags and mandatory If-Match on overwrite/delete; stale writers rejected with HTTP 412. WebUI: Save Draft, Save As New Draft, Load Draft, Delete Draft, per-project selector.
- Saved drafts can be edited even after an Editor change, but Apply remains blocked unless the original imported lanes, model, FPS, frame count and source reference match a fresh live Editor snapshot. No automatic rebase or project save.
- ZIP export/import includes only validated, manifest-hashed draft JSON. Save Project As copies these draft files and updates their ownership to the new project. No generated media or caches. Windows/mobile acceptance pending; PS2 not started.

### PS2 Prompt Studio visual timeline (2026-10-21)
On `dev-webui` PS2 adds a native positive/negative keyframe visual timeline to the PS1.4 workspace: pointer/touch diamond dragging, Hold/Blend prompt-only frame inspector (uses `resolve_prompt_transition` shared with native rendering), zoom, frame/time ruler, snap 1/2/5/10/24, scrubbing, multiselection, duplication, even spacing, per-lane editing locks, atomic delete and 80-step in-session undo/redo. A positive-lane scene strip displays scene lengths in seconds. Frame zero/last frame bounds, collisions and selected-group moves fail atomically; raw prompts/LoRA tags remain exact. All edits remain Studio draft-only until preview, confirmed Apply, and explicit Editor Save. Owner-requested scene-order/visual polish remains a follow-up within PS2 after Windows/mobile testing. Keep `main` untouched.

### PS3: Structured Prompt Composer (2026-10-21)
On `dev-webui` PS3 introduces global and scene-local prompt blocks with separate beginning/end placement, text/LoRA types, order, activation and inline editing. The positive-only LoRA picker reuses indexed same-family local adapters plus optional cached Civitai trained words and thumbnails (no automatic sync). Exact composed prompt preview and duplicate-LoRA diagnostics precede a deliberate Commit to Studio Draft. Only the existing guarded Preview Changes / Apply to Animation / Save Project persists into the animation. Validated `composer` metadata is an optional backwards-compatible property of v1 Studio drafts, surviving ZIP and Save As. **PS3 owner Windows-accepted; PS4 is implemented separately and awaiting physical acceptance.**

### PS4: Ollama AI Story Director (2026-10-21)
- **Implemented on `dev-webui`, Windows/mobile acceptance pending.** New text-only PS4 Ollama AI Story Director: backend-controlled loopback default, opt-in private numeric LAN host, no public endpoint or redirect support, bounded model catalog and chat requests, strict schema/timeout errors. No arbitrary network fetches, image/file upload or silent project writes.
- User selects installed local Ollama model, Create or Refine, story direction and 1–16 scenes (Refine uses existing positive frames). Backend deterministically assigns keyframes and validates returned text without executing LLM code/frames. Existing negative track retained unless "Also generate negative prompts" explicitly selected. Existing LoRA tag bytes retained for Refine; new AI LoRA directives rejected. Prefix placement is warned.
- Browser supports Cancel/Discard, before/after proposal review, stale-draft rejection and confirmation-gated Accept into Studio draft only. Undo works through PS2. Optional `ai_provenance` records Ollama model/mode/family/profile/time in saved draft v1, project ZIP and Save As. PS5 model-family advanced profiles and image understanding; PS6 AI-assisted audio-to-storyboard synchronization remain **not implemented**. Physical Windows/Ollama tests required; do not merge main.

### PS4.1 Ollama progress hotfix (2026-10-21)
The user observed silent "waiting for Ollama" behavior. Replaced the WebUI's one-shot generation call with `/api/prompt-studio/ollama/generate-stream` returning bounded NDJSON stage/heartbeat/result/error events and a 240-second generation deadline. An indeterminate activity UI shows elapsed seconds, current stage and real received-character counts, with Cancel. Backend emits Prompt Studio console start/heartbeat/progress/failure/completion messages; a checked Prompt Studio source filter was added to the WebUI Console. Raw story and generated text are never logged; original `/generate` is retained for compatibility. Automated mocked stream tests added; physical Windows Ollama confirmation is still required. `main` remains unchanged.

### PS5.1 model-family profiles and precise continuity (2026-10-21)
- Implemented on `dev-webui`: read-only versioned prompt profile catalog (`ps5-sdxl-v1`, `ps5-flux-v1`, `ps5-zimage-v1`), strict family selection, explicit recurring subject/style immutable text locks (max 1000 chars each), targeted Refine one existing positive frame and frame-preserving negative-lane merge when negative generation is explicitly enabled.
- Existing PS4 streaming Ollama request path, cancellation, provenance, editor/studio isolation, and native rendering unchanged. Old PS4 generic profile remains a valid default for clients without `profile`; only PS5 WebUI opts in. Generated proposals carry heuristic word counts and warning labels, not CLIP tokenizer output.
- **PS5.1 Windows-accepted (2026-10-22). PS5.2 implemented, Windows testing pending:** project-owned `assets/source.png` only, explicit preview and checkbox consent per request, SHA-256 preview match and bounded PNG decoding/JPEG reduction, loopback-only Ollama endpoint, verified `/api/show` `vision` capability before sending any image, editable response and explicit Add Description to Story. Invalid/unknown capabilities, mismatched images, symlinks, paths/URLs and malformed responses fail closed; no changes to Studio draft, project, audio or renderer. Automated mocked-provider tests added; physical Windows vision and mobile privacy acceptance remain outstanding. **PS5.3** evaluate actual local models on Windows, not assume performance. PS6 audio synchronization remains required. Do not merge `main`.


### PS5.3 serial local model evaluation (2026-10-23)
- On `dev-webui`, **PS5.3 Compare local Ollama models** runs two user-selected installed text models sequentially through one chosen, fixed 96-frame/24-FPS benchmark case (horror, same-character, landscape or synthetic mixed-LoRA refinement). It reuses the PS4.1 bounded `/api/prompt-studio/ollama/generate-stream` contract; it does not send active project prompts, images or audio, automatically load LoRA weights, or modify Studio drafts/renderer.
- Side-by-side outputs include individual frame prompts, returned Ollama token/evaluation metrics where available, request elapsed time, per-model failures, explicit human fidelity/continuity/clarity ratings and manually recorded *physical* render spot-check status. Exports one JSON report only on user click; no backend/database persistence and **no automatic model winner**. Model name/size alone does not establish quality.
- Added deterministic JS fixture/result-validation tests and syntax workflow coverage. **Next gate:** owner Windows test two installed local models, four cases, SDXL/FLUX/managed Z-Image family context, repeated runs, cancellation, failure recovery, and same-settings actual image render comparison. Confirm PS5.2 privacy remains unchanged. No `main` promotion without separate approval.


### PS6.1 read-only Motion Studio beat-alignment preview + Studio organization (2026-10-23)
- **Implemented on `dev-webui`, owner Windows acceptance pending.** Audio → Storyboard is an expandable Prompt Studio section. It lists only verified `motion_lab_wav` assets belonging to the open project; **Load Beats** reuses Motion Studio's existing `GET /motion-lab/audio/{sha}/analysis` and source-bound `GET /motion-lab/audio-markers/{sha}` APIs. Saved manual marker edits take precedence; otherwise use existing transient detection. No new detector, uploaded media, camera motion edits or audio overwrite.
- Filter enabled kick/snare/highs markers by time range, select from an accessible beat timeline or list (up to 120 visible per filter/range), view WAV SHA/source metadata, exact timestamp, snapped integer frame and drift. Frame mapping: `floor(seconds * fps + 0.5)` and **reject** out-of-animation frames rather than clamp. Flag marker collisions and missing/disabled/out-of-range cues.
- Lock existing positive scenes, keep frame 0 fixed, preview chronological beat-to-scene position changes with exact original prompt/LoRA text and untouched negative lane. Insufficient distinct beat frames, lane locks and destination collisions block previews. This milestone only **previews** and discards: no changes to Studio drafts, camera schedules, project JSON, audio file or Ollama provider requests. PS6.2 must add confirmation-gated staging, audio provenance/revalidation, undo/redo, stale-source handling and actual saved/rendered acceptance.
- Prompt Studio's Saved Drafts, Composer and Manual Prompt sections, plus AI Director's PS5 authoring/vision/comparison, use native expandable disclosures to reduce clutter while leaving the primary Director accessible. Syntax and frontend regression tests added; acceptance includes Android layout and old workflow regression.
