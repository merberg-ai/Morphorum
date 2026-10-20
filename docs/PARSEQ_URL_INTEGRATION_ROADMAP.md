# PQ Roadmap: Parseq URL Integration for Morphorum

**Branch:** `dev-webui` only  
**Status:** PLANNED / NOT STARTED (2026-10-20)  
**Decision:** Option A. Reuse the hosted [sd-parseq](https://github.com/rewbs/sd-parseq) authoring tool and fetch its published rendered JSON manifest through a persistent URL. Do **not** rebuild the Parseq editor, port its expression language, fork Deforum, or install Automatic1111.  
**Release gate:** No implementation or merge into `main` until the project owner requests the individual milestone and physically accepts the relevant Windows/GPU tests. No repository implementation changes are authorized by this planning document.

## 1. Goal and intended experience

1. User authors and updates an animation in [Parseq](https://sd-parseq.web.app/), signs in, enables its output upload/Auto-upload, and copies the resulting **uploaded output JSON URL once**.
2. In Morphorum, a saved animation project has a **Parseq Integration** panel: Enable Parseq, Manifest URL, Validate/Refresh, status, and a clear description of what Parseq overrides.
3. Morphorum fetches the manifest **server-side** using a safe, bounded HTTP client; the frontend never needs to fetch Firebase directly and is not blocked by CORS.
4. Before **every new render** in automatic mode, Morphorum obtains the latest uploaded JSON, validates/normalizes the exact frame schedule, checks project/model compatibility, and freezes the downloaded bytes (or a content-equivalent immutable verified snapshot) into that render.
5. A running or resumed render uses **only its frozen snapshot**. Changes later uploaded by Parseq apply to the **next** render, never mid-run.
6. Native projects without Parseq enabled, saved projects, Motion Lab drafts, audio, output exports, and SDXL/FLUX/Z-Image pipelines remain unaffected.

**Non-goals:** Parseq UI duplication, importing unrendered authoring-only state for evaluation, executing arbitrary Parseq JavaScript/expressions, reverse-synchronizing edits into Parseq, automatic model/LoRA downloads, Deforum pixel-perfect rendering, arbitrary remote file hosting, or silent conversion of unsupported Deforum features.

## 2. Verified upstream and local reference points

- Parseq: `rewbs/sd-parseq` README describes an uploaded URL whose content is updated in place; `src/components/UploadButton.tsx` uploads rendered JSON to Firebase Storage and supports Auto-upload.
- Parseq contract: `src/ParseqUI.d.ts` and `src/parseq-renderer.ts` define `meta`, `options.output_fps`, `managedFields`, `keyframes`, `rendered_frames`, `rendered_frames_meta`, `deforum_prompt`, and `*_delta` values. **The rendered_frames array is authoritative for this integration.**
- Deforum: `deforum/sd-webui-deforum/scripts/deforum_helpers/parseq_adapter.py` accepts a URL/JSON and distinguishes absolute motion from per-frame delta schedules. Use as behavior reference; do not copy its assumptions about camera units untested.
- Morphorum: `backend/morphorum/schedules.py`, `animation_timeline.py`, `animation_resolution.py`, `animation_motion.py`, `animation_render.py`, `animation_projects.py`, `animation_preflight.py`, `project_archive.py`, and FastAPI endpoints in `app.py`.
- Current Morphorum renderer resolves a frame through `resolve_project_frame`; a render job stores a frozen project and seed plan. The Parseq path should extend those existing contracts, not create a second diffusion renderer.
- Morphorum 2D zoom is a **multiplicative per-frame factor**; 3D translations/rotations are applied sequentially to feedback frames. Parsed absolute Parseq values must not be mistaken for per-frame increments.
- The Parseq GitHub code is MIT licensed. If any code is copied (not currently planned), retain appropriate notices in Morphorum's third-party docs.

Review upstream changes at PQ0 implementation start; this document describes the code observed on 2026-10-20, not a promise of a stable future upstream schema.

## 3. Design invariants (non-negotiable)

- **One persistent URL per project; no recurring JSON copy/paste.** A regular Parseq editor/share page URL is not a JSON manifest. Detect accidental page HTML and explain the correct Parseq **Upload output / Copy URL** action.
- **Explicit opt-in and reversible isolation.** Disabled Parseq means existing native behavior. Project saving never mutates Parseq remotely. Enabling does not overwrite/delete native tracks or Motion Lab layers.
- **Track precedence:** Only recognized fields deliberately controlled by the validated Parseq manifest override their corresponding **runtime-resolved** Morphorum values. All other fields use the original project. Do not silently import keyframes over native tracks.
- **No surprise model changes.** Model ID/family, checkpoint, image size, sampler unless explicitly supported, LoRA library, project duration and FPS stay Morphorum-controlled.
- **Fail closed on a new render.** Missing URL, fetch error, malformed/missing frames, FPS/frame-count/cadence conflict, unsafe URL, or enabled-but-invalid Parseq must fail before GPU allocation. Do not quietly fall back to stale cached JSON or native-only settings. Offer a **separate, explicit** manual pinned-snapshot mode later if genuinely needed.
- **Deterministic render provenance.** Source URL (redacted where appropriate), fetch time, Parseq metadata, SHA-256 of original bytes, override summary, and frozen manifest identity belong to the render record. Reproducible resumes must not refetch the live URL. Preserve an original snapshot even if Parseq overwrites its hosted file.
- **No arbitrary remote execution.** Parseq formulas have already been evaluated by Parseq into rendered frame numbers/strings. Strictly parse JSON; do not run scripts, import Python code, dynamically evaluate expressions, or interpret HTML.
- **Preview/render parity.** A validated Parseq overlay should use the same mapping for frame inspection, safety preflight, camera preview, seed planning, actual rendering, and diagnostics. When snapshots differ, label which version each preview represents.
- **Safe serialization and backups.** Projects can keep the URL and settings. Exported project ZIPs continue to omit generated media and remote manifest contents by default; they may carry the URL including an access token. Document this privacy implication and redact secrets from logs/toasts/status responses.
- **No unverified acceptance.** Automated PASS is not owner physical Windows GPU PASS; keep them separate.

## 4. Proposed saved settings / runtime boundary

The following is a **design sketch**, not an implemented schema or API:

- `project.parseq.enabled`: false by default.
- `project.parseq.manifest_url`: saved uploaded Parseq JSON URL.
- `project.parseq.refresh_policy`: `before_render` initially (the default and only automatic mode). A future explicit `pinned` mode may be considered separately; never implicit on errors.
- `project.parseq.use_deltas`: true for camera channels that require per-frame movement, with per-field conversion rather than blindly copying all `_delta` fields.
- `project.parseq.field_overrides`: optional allowlist constrained to supported fields; absent means supported **declared** fields only. Disabled/undefined fields preserve native values.
- **Runtime:** server-side `ParseqValidatedManifest` (validated original/normalized per-frame data, warnings, fingerprint, metadata, capabilities) and `ParseqFrameOverlay` consumed by the existing resolution pipeline; precise names subject to design review.
- **Render-local:** immutable `parseq-manifest.json` sidecar under the existing render directory plus fingerprint/provenance reference in the render manifest. Do not embed multi-megabyte rendered frames repeatedly into each frame record, public job payload, or project.json.
- **Project archive:** settings/URL only, no live remote fetch during import/export/Save As. Do not broaden `project_archive.py` allowed ZIP members without an explicit versioned design.

Introduce small backend APIs for **validate/preview URL** and **inspect effective frame fields**; reuse the current render-submission path. Avoid an alternate parallel render endpoint or shadow project state.

## 5. Compatibility matrix and initial policy

| Parseq rendered field | Morphorum target | Initial policy |
| --- | --- | --- |
| `strength` | `generation.strength` (Morphorum image **retention**) | Supported when numeric/in [0,1]; verify semantic equivalence; the Diffusers denoise passed by Morphorum is 1 - retention. |
| `noise` | `generation.noise` | Supported after numeric validation and family-specific render checks. |
| `scale` | `generation.guidance` | Model-aware: SDXL mapping candidate, FLUX/Z-Image must be checked against capability and ranges; **never assume CFG 7 fits all families**. |
| `steps_schedule` | `generation.steps` | Supported after integer and per-family bounds checks. |
| `angle_delta`, `zoom_delta` | 2D `motion.angle`, `motion.zoom` | Conversion/preview required; zoom factors must remain positive and cumulative distortion bounded. Absolute `angle`/`zoom` may be converted to equivalent per-frame deltas. |
| `translation_x_delta`, `translation_y_delta` | 2D movement | Mode- and unit-aware conversion, not a raw blind copy. |
| `translation_x/y/z_delta`, `rotation_3d_x/y/z_delta` | Six-axis 3D camera | Separate PQ3/4 calibration and depth-preview acceptance. Derive deltas from absolute values if required and validate both forms. |
| `fov` | `camera_3d.fov` | Bound and test; check whether absolute FOV is expected by the projection path. |
| `deforum_prompt` | Per-frame positive/negative prompt state | Parse Parseq/Deforum `--neg` separator safely, preserve literal prompt text, resolve LoRA tags with current Morphorum policy. Per-frame transitions need exact semantics and conditioning validation. |
| `seed` | Resolved seed plan | **Not v1** until PQ4 seed-plan integration is implemented/tested. Do not claim support just because importer can see the field. |
| `sampler_schedule` | Sampler | **Not v1**; native selected sampler remains authoritative until verified runtime switching exists. |
| `subseed`, `subseed_strength` | Seed travel | **Not v1**; would need separate diffusion support. |
| `contrast`, antiblur, perspective flip, near/far, unknown fields | Various | **Not v1** unless separately designed and accepted. Warn clearly; do not silently pretend compatibility. |

**Model rollout:** First validate the adapter against short **SDXL 2D** cases, then 3D path, then physically test the **managed Z-Image Turbo** and FLUX compatibility as separate gates. Parser/URL support may be family-agnostic, but actual supported scheduling controls must be feature-gated.

**Temporal coherence:** This integration supplies advanced control, **not** an automatic fix for the separate ZT1 Z-Image slideshow-like animation quality investigation in `TODO.MD`.

## 6. Milestone sequence, checkpoints and exact acceptance

### PQ0: Baseline, contract, fixtures and threat model (no live integration)

**Build:** Recheck upstream Parseq output/upload URL behavior. Obtain sanitized small *real published* Parseq manifest fixture(s) and synthetic variants, including 2D, 3D, prompt, field omissions and invalids. Record exact field types and units. Document baseline dev-webui SHA, unaffected native render results, and existing frontend/backend CI state. Define URL fetch threat model, project schema migration behavior, field allowlist and conversion semantics. Decide how to snapshot URL safely without exposing Firebase bearer-like query tokens.

**Automated acceptance:** Contract fixtures committed, reproducible schema tests ready, safety cases identified, no existing project behavior changed.

**Owner gate:** Approve source URL type, initial field scope, and 2D/3D translation policy before PQ1.

### PQ1: Secure URL fetching and durable project configuration

**Build:** Add optional `parseq` project settings that survive create/load/save, Save Project As, project ZIP export/import, and UI project switching without stripping fields or clobbering legacy tracks. Implement backend-only public-HTTPS JSON fetcher with: allowed host families appropriate to Parseq's actual Firebase upload URLs (and a documented safe extension process); TLS verification; DNS resolution and **public-IP-only** checks for IPv4/IPv6, including redirected destinations and protection against DNS rebinding; no private/loopback/link-local/metadata-network access; no unsafe URL credentials; strict redirect count; explicit connect/read/total timeouts; bounded byte count before parsing; response/JSON depth/record-count bounds; no implicit proxy bypass; and redaction of sensitive query parameters from diagnostics. Never fetch on normal project save/load/import. Reject page HTML, unexpected content type where appropriate, and unauthenticated inaccessible URLs with actionable errors. Include deterministic dependency-injected HTTP mocks for tests.

**Automated acceptance:** Public valid JSON works; local/private IP, DNS rebinding, redirect-to-local, malformed URL, timeout, large/HTML payload, auth failure and network errors fail safely; old project serialization unchanged. No accidental URL fetching in unrelated paths.

**Owner gate:** A user-hosted Parseq URL can be saved once, validated/fetched twice after an upstream update, and not pasted again.

### PQ2: Rendered-manifest validation, compatibility report, read-only preview

**Build:** Strictly validate a top-level JSON object and nonempty `rendered_frames` array; valid integer, contiguous, unique, zero-indexed frame IDs with first/last coverage; exact project FPS/required frames initially; finite in-range numeric fields; bounded prompt strings; fields that are present/managed vs unsupported; Parseq `options.output_fps`, cadence metadata, metadata versions and optional `_delta` columns. Do not evaluate Parseq `keyframes` expressions in Morphorum. Resolve version and field/metadata drift as explicit, testable compatibility cases, not guesses. Return stable read-only validation status: fetch time, fingerprint, FPS, frames, fields provided/ignored, warnings/errors, effective sample values and unredacted URL **only in an edit control to authorized local users**. Use the actual validated data when rendering, never a fresh hidden parse in a second incompatible parser. Prevent huge response payloads in browser.

**Automated acceptance:** Good real fixture passes; gaps/duplicates/non-finite/bool-as-number/missing fields/wrong FPS or frame count/oversized prompts cause actionable errors; unknown fields are warned, not executed.

**Owner gate:** Preview identifies precisely which tracks Parseq will and will not control before any write or render.

### PQ3: Core per-frame adapter, 2D camera and generation/prompt overlays

**Build:** Introduce a dedicated server-side Parseq adapter returning typed per-frame overlays. Extend **one** common `resolve_project_frame` path (or its tested wrapper) so preview, preflight, generated prompts, LoRA resolution, steps, guidance, retention/noise and 2D camera use the same source values. No mutation of stored native keyframes. Parse per-frame `deforum_prompt` and `--neg` carefully (including quoted/literal occurrences); preserve Morphorum LoRA syntax and negative-prompt safety rules. Match existing prompt-conditioning cache/inference-context assumptions for SDXL, FLUX and managed Z-Image. For Parseq motion, explicitly distinguish absolute vs per-frame delta and test `zoom_delta` conversion; avoid accumulated zoom/translation blow-ups. Unsupported families/fields must fail or warn as specified, never silently run wrong values.

**Automated acceptance:** Per-frame golden tests prove value precedence and exact overlay matching at frame 0, middle, end; native-only baseline is unchanged when integration disabled; direct camera preview equals renderer's resolved camera values; LoRA-positive/negative tests pass; tests cover 2D zoom/angle direction and edge bounds.

**Owner gate:** Short **SDXL 2D** test animation demonstrates prompt, strength and camera scheduling in generated output.

### PQ4: 3D camera integration and optional seed scheduling (feature gates)

**Build:** Calibrate Parseq's six-axis data against Morphorum's sequential depth-warp units; extend known Deforum-motion conversion only where justified, track exact sign and scale, validate per-frame displacement and cumulative projection safety. Expose a conversion review and safe adjustable translation/rotation strength if needed. For seeds, **only if separately verified**, support integer per-frame seed values through the current precomputed `seed_plan`, random resolution and replay without conflicts; otherwise mark seed unsupported throughout UI/docs. Use camera preview with the same snapshot and warn on poor depth coverage/cumulative drift. Do not implement sampler/subseed features as an accidental side effect.

**Automated acceptance:** Fixed 3D golden schedules produce bounded predictable projections; no six-axis reversed signs or raw absolute-to-delta confusion; resume seeds match frozen plan; cross-mode controls cannot leak.

**Owner gate:** Separate Windows SDXL 3D depth-preview + short rendered animation. Seed support receives its own acceptance or stays disabled.

### PQ5: Render submission, immutable provenance, resume and failure semantics

**Build:** Wire new renders so fetch → validate → confirm effective settings/version → snapshot → seed plan/preflight → queued render occurs in an atomic, conflict-safe sequence. Freeze original validated JSON as a bounded, immutable render-local sidecar and store SHA-256, Parseq metadata, controlled field list, fetch timestamp, version and sanitized origin in the existing render manifest. Read frozen bytes for queued work and interruption/cancel/resume, never the remote URL. Ensure existing `_hybrid_snapshot`, soundtrack, model selection and saved project snapshot remain coherent; never refetch or apply a new live manifest to a historical render. If upstream updates between preview and submission, show a clear change indication and validate the newly downloaded version before GPU work. Project remains independently editable.

**Automated acceptance:** Mutation of hosted payload after submit has no effect on frames/resume; URL outage after job creation does not invalidate resume; corrupt/missing sidecar fails explicitly (no fallback); render manifest stores correct hash and avoids accidentally exposing signed URL credentials to public API/console; no duplicate network fetch in per-frame loop; generated PNG/video outputs, existing jobs and archives unchanged.

**Owner gate:** Start render A, change Parseq uploaded output while A is in progress, then render B. A retains original schedule, B uses changed schedule; resumed A stays original.

### PQ6: Minimal native WebUI / mobile workflow

**Build:** Add compact **Parseq Integration** panel under Project Editor or Motion Lab navigation: enable checkbox, one long URL field with sane wrapping, **Open Parseq**, **Validate/Refresh**, source state (live/pinned/disabled), last fetched timestamp, source fingerprint/changed state, observed FPS/duration, controlled/ignored field list, and actionable warnings. Clearly distinguish draft URL edits from Saved Project and Render snapshot; reuse current Save Project handler/ETag conflict behavior. Render button visibly flags invalid enabled Parseq and displays source freshness/result. Preserve existing mobile menu close/navigation, accessible keyboard focus and 200% zoom. Never require copy/paste of full JSON and never present an inert fake refresh control.

**Automated acceptance:** Browser/frontend tests for save/load/switch, invalid URL, disabled semantics, preview vs render version, responsive/mobile layout, stale edit conflict, and no accidental non-Parseq UI regressions.

**Owner gate:** On Windows and Android browser, link a real Parseq URL, save project, update upstream, refresh, preview, render, reload page and confirm URL persists. Physical mobile may be deferred explicitly but cannot be marked PASS without testing.

### PQ7: Multi-family regressions, docs and merge readiness

**Build:** Run entire supported field/model matrix. Prove managed Z-Image Turbo (including LoRA prompt changes), SDXL and FLUX do not receive unsupported CFG/step settings and that low-denoise/retention semantics are visible. Verify Render Monitor, outputs, MP4/WebM/audio export, Save Project As, ZIP portability and stale/invalid manifest handling. Update README, Getting Started, Current Status, Help docs and TODO with **only physically verified** support. Run Syntax, Backend, Installer and relevant frontend automation on branch, record run IDs and owner results.

**Acceptance:** No regression to existing native renderer; explicit tested support matrix, known limitations, secure fetch, faithful snapshots/resume, readable errors, user Windows acceptance; no unsupported family claimed as fully supported.

**Release gate:** **Stop** after dev-webui tests and owner signoff. Do **not** merge into `main` unless explicitly instructed.

## 7. Test matrix to maintain throughout

- **Source:** new valid URL, same URL updated, unreachable URL, expired/revoked Firebase token, HTML page instead of JSON, redirect, private IP/DNS rebinding, truncated/too-large payload, late upstream upload.
- **Data:** zero/missing/duplicate/gapped frames; mismatch FPS/frame count/cadence; absent or unknown fields; NaN/Infinity/huge numbers; bad prompt; true/false used as numeric; 2D/3D incompatible control channels.
- **Schedule ownership:** Parseq enabled/disabled; only one controlled parameter; native fallback for others; native project unchanged; Motion Lab applied-vs-draft layers not overwritten.
- **Model:** SDXL short 2D then 3D, managed Z-Image Turbo, FLUX, prompts with/without LoRAs; warn when a family cannot honor a field.
- **Render:** same URL edited before start, edited mid-render, deleted after submission, resume after restart, two independent jobs of same project different snapshots, queued worker, seed reproducibility, preview-vs-render fingerprint.
- **Project lifecycle:** save, reopen, new project default, Save Project As, ZIP export/import, project switch and stale editor conflict; no network during import/export; do not include rendered remote manifests in portable ZIP without explicitly extending archive format.
- **UI:** Windows desktop, Android narrow viewport, keyboard/zoom, URL long line, remote error recovery, no sensitive URL exposure in logs or status text.

## 8. Implementation boundaries and candidate touched files

Candidate new backend modules: `backend/morphorum/parseq_fetch.py`, `parseq_manifest.py`, `parseq_adapter.py` (names flexible). Candidate integration: `animation_projects.py` (optional settings/schema), `animation_resolution.py` (one overlay path), `animation_motion.py` (preview), `animation_render.py` (freeze/resume), `animation_preflight.py`, `app.py` (read-only validate/status). Candidate frontend: `frontend/dist/assets/animation.js`, existing animation CSS and navigation, without introducing React/Material UI. Tests: `tests/test_parseq_*.py`, frontend CJS tests and sanitized fixture JSON under `tests/fixtures/parseq/`. Keep additions small and reviewable per PQ step.

**Not touched unless an accepted compatibility requirement demands it:** native model loading, managed Z-Image installation, existing model/LoRA search, global animation defaults, Motion Studio audio detection, saved motion layer implementation, or `main`.

## 9. Issues to resolve explicitly before or during PQ0

1. Inspect a real Firebase Storage URL after upload/Auto-upload; verify stable URL and whether updates require a new read/download token; do not hardcode speculative Firebase host/path assumptions.
2. Choose exact maximum manifest size and render-frame cap according to current `MAX_RENDER_FRAMES`, memory, JSON nesting and prompt length; avoid using unbounded huge Parseq outputs.
3. Verify Parseq `strength` meaning against current Morphorum retention semantics using fixture and rendered output, not merely field names.
4. Decide supported prompt-escaping rules for text containing `--neg`; reject ambiguous cases explicitly rather than splitting incorrectly.
5. Decide whether preview uses explicit manual refresh or always refetch; in all cases **render** auto mode refetches and freezes once, with version mismatch made visible.
6. Define the retry policy for intermittent Firebase network errors without ever falling back to old data unintentionally.
7. Ensure URL secrets in project ZIP and Save Project As are documented; avoid putting unredacted query tokens into error messages or public job telemetry.

## 10. Resume instructions for a future chat

Say: **"Resume PQ0 Parseq URL integration on dev-webui using docs/PARSEQ_URL_INTEGRATION_ROADMAP.md. Keep main unchanged and stop for my Windows testing after the milestone."**

When resuming: read this roadmap, check `dev-webui` branch HEAD and fresh upstream Parseq/Deforum versions, complete only the named PQ milestone, add test evidence and an explicit checkpoint entry to this file, commit/push to `dev-webui`, and wait for owner results. Do not skip ahead, claim physical acceptance, or merge into main without approval.
