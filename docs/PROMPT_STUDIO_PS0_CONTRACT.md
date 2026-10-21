# PS0 — Prompt Studio native contract baseline

**Status:** Historical PS0 design baseline. PS1–PS3 were implemented and Windows-accepted; PS4 is implemented pending physical Ollama acceptance. Original audit paragraphs are retained for traceability.  
**Branch:** `dev-webui` only. Baseline inspected at commit `3fe3fd0402f4` on 2026-10-21.  
**Roadmap:** [Prompt Studio PS0–PS9](PROMPT_STUDIO_ROADMAP.md). Original PS0 proposals are followed by phase implementation notes. Current source and roadmap supersede historical gaps.

## Decision summary

Prompt Studio is a separate, optionally LLM-assisted authoring UI. Native `tracks.prompts.positive` and `tracks.prompts.negative` remain the sole runtime prompt track authority after an explicit apply/save. Studio cannot render, mutate camera/generation/audio/media settings, or write Parseq manifests. Preserve arbitrary prompt text and LoRA tags byte-for-byte on an import→export round-trip **until the user deliberately edits that text**.

**Authority chain:** saved `project.json` → in-memory Project Editor unsaved draft → isolated Studio draft → review/diff → Project Editor unsaved draft → explicit Save Project with revision guard → existing native resolver/render. At any point a project switch, model/FPS/max-frame change, conflicting edits, or stale project revision must block an unsafe apply and offer re-import/review; never silently replace the active editor state.

## 1. Verified existing native fields and source mapping

| Area | Current shape / behavior | Owner in PS |
| --- | --- | --- |
| Project | `schema_version: 2`; `id`, `name`; `animation.max_frames` integer 1–1,000,000, `animation.fps` 1–240 | Context snapshot, read-only |
| Model | `model.model_id`, `model.family`, `model.variant` | Read-only; validate current index/capabilities at apply |
| Source input | `animation.start_mode` is `prompt` or `source`; `source_image` and `source_image_name` | Read-only reference; opt-in vision later |
| Legacy prompt maps | `prompts: {"0":"...","30":"..."}`; `negative_prompts` likewise | Derived compatibility fields, **not** separate authority |
| Canonical prompt tracks | `tracks.schema_version: 1`; `tracks.prompts.positive/negative: {kind:"prompt", interpolation:"blend"\|"hold", keyframes:[{frame:0,value:"..."}]}` | **Authoritative PS export**; separate lanes and interpolation modes |
| Legacy transition | `animation.prompt_transition` mirrors **positive** interpolation in `sync_legacy_from_tracks` | Derived compatibility field, not a separate PS transition engine |
| Resolved frame | `resolve_project_frame(project, frame)` returns `prompts.positive/negative` with `mode,from_frame,from_text,to_frame,to_text,from_weight,to_weight`, plus `loras` | Inspector must compare against canonical resolver |
| LoRA | Inline `<lora:name:weight>` recognized in **positive** text; negative LoRA directives reject; `loras.py` resolves family-filtered indexed adapters | Preserve original text/tags; resolve only for validation/preview |
| Model conditioning | `animation_render._prompt_conditioning_kwargs` handles SDXL negative+long CLIP chunking, FLUX positive embedding blend, managed Z-Image positive embedding blend | Do not promise equal negative support, token limits, render parity or quality |
| Save | GET / PUT `/api/animation/projects/{id}`, GET responds with quoted SHA-256 `ETag`, PUT supports optional quoted `If-Match` and 412 on conflict | PS1 needs enforced revision capture and guarded commit |
| Studio audio input | Project-owned `motion_lab_audio/<sha256>.wav`, analyzer `source_sha256`, `duration_seconds`, `events.analysis_version=2` | Read-only source; align storyboard in PS6 |
| Edited markers | `motion_lab_audio/<sha256>.markers.json`, `schema_version:1`, `events:[{id,kind,enabled,time_seconds}]` | Read-only marker choices and provenance |
| Motion Director cues | `motion_lab_audio/<sha256>.cues.json`, `schema_version:1`, `cues:[{id,preset,time_seconds,duration_seconds,intensity,easing,enabled,source_event_id}]` | Read-only suggestions/section cues, not camera edits |

Read points: `backend/morphorum/animation_projects.py`, `animation_timeline.py`, `animation_resolution.py`, `schedules.py`, `loras.py`, `animation_render.py`, `audio_motion_upload.py`, `audio_events.py`, `audio_marker_overrides.py`, `audio_motion_cues.py`, `project_archive.py`, `app.py`, `frontend/dist/assets/animation.js`, `loras.js` and `motion-lab-visual.js`.

### Baseline integration gaps found (do not hide)

1. `animation.js` keeps editable form fields plus `state.project` / `state.dirty` privately. There is **no exported read-unsaved-draft or prompt-only apply interface**. `window.MorphorumAnimation` exposes unrelated operations. PS1 must implement an explicit controlled bridge; querying saved project JSON is not a substitute.
2. The main editor's `saveProject()` calls PUT **without If-Match** even though backend supports it. Adding concurrency checks to Studio alone is insufficient if an unrelated editor save can overwrite the same project. PS1 must capture/recheck revisions and decide how to integrate guarded editor saves without breaking other workflows. Existing timeline edits may persist dirty form state before applying.
3. The basic prompt rows are built from the **union** of positive/negative frames, and `collectPromptMaps()` emits both entries for each row. Native tracks can independently keyframe and interpolate. A naive row round-trip can create new empty/duplicate negative frames or merge two interpolation modes. The PS bridge must preserve track-level distinctions and test editor interoperation.
4. `normalize_animation_project` resolves clashes between legacy maps and `tracks` via change detection; `sync_legacy_from_tracks` derives maps. PS1 must use a tested canonical patch utility, rather than writing only legacy fields or blindly editing both with inconsistent values.
5. Audio analyzers/cue-frame helpers enforce **at most 3,000 frames**, while the general project schema permits up to **1,000,000**. PS6 must gate availability and show a clear unsupported message or implement an independently reviewed scalable mapping; it must not silently truncate projects.
6. Two existing audio quantizers have **different out-of-range policies**: `audio_events.event_frame_index` returns `None` when rounded beyond last frame; `audio_motion_cues.cue_frame_index` clamps to the end. PS6 proposes an explicit canonical policy rather than reusing either implicitly.
7. Parseq URL support is planned under the separate PQ roadmap, **not currently implemented**. PS will show a runtime-authority warning *if* that integration is later enabled, not pretend Parseq already takes precedence.

## 2. Proposed Prompt Studio draft schema v1 (PS1 contract target)

Drafts are standalone data, **not** a new `project.json` schema. Proposed JSON members:

```json
{
  "format": "morphorum.prompt-studio-draft",
  "schema_version": 1,
  "draft_id": "uuid-or-stable-local-id",
  "project_context": {
    "project_id": "existing-project-id",
    "base_project_etag": "\"<64 hex sha256>\"",
    "project_schema_version": 2,
    "timeline_schema_version": 1,
    "model": {"model_id": "saved-model", "family": "sdxl", "variant": ""},
    "max_frames": 120,
    "fps": 24.0,
    "start_mode": "prompt",
    "source_image_name": ""
  },
  "prompt_tracks": {
    "positive": {"kind":"prompt","interpolation":"blend","keyframes":[{"frame":0,"value":"..."}]},
    "negative": {"kind":"prompt","interpolation":"hold","keyframes":[{"frame":0,"value":""}]}
  },
  "scenes": [],
  "composer": {"global_blocks":[],"scene_blocks":[]},
  "continuity": {"fixed":[],"variable":[]},
  "audio_alignment": null,
  "ai_provenance": null,
  "source": "imported_editor_draft"
}
```

**Normative draft rules:**
- `format` and `schema_version` required. v1 schema unknown fields must be preserved for known-version round trips where safe, but never executed. Reject future major versions until a migration exists. Validate bounds/finite floats, payload size, frames, string limits and unique frame numbers before apply.
- `project_context` is a **snapshot**, never a request to change project/model/FPS/media. The saved project revision is quoted as received from GET response; a newly unsaved editor draft must additionally have its own in-memory revision token/counter. If no safe base revision is available, mark status **unverified** and block applying to another saved revision.
- `prompt_tracks` are **canonical output**, with independent positive/negative keyframe lists and interpolation. Import and re-export preserve every `value` string exactly (including case, punctuation, newlines, trigger placement and LoRA tag spelling). A structured composer must retain the original raw-text path when it cannot reversibly parse content.
- `scenes`, `composer`, `continuity` are optional authoring metadata; none are copied into `project.json` or evaluated by renderer. Scene IDs stay stable when moving frames; locks are authoring-only.
- `audio_alignment` proposed only for PS6: `{source_sha256, duration_seconds, analysis_version, selected_event_ids, mapping_policy, snapped_frames, source_type}`; preserve source identity and mark stale after SHA/FPS/frame-count/marker edits. No embedded PCM or absolute host path.
- `ai_provenance` proposed only for PS4+: provider/model/profile version, input action and user-accepted suggestion identity. AI suggestions cannot patch this schema directly without strict validation.
- Saving a Studio draft persists only Studio-owned data; it never invokes PUT on animation project. Opening and editing a draft offline requires no LLM.
- Draft migration v1→v2 must be explicit and reversible via copied backup; missing optional fields get safe defaults, unsupported major versions remain read-only, and incompatible project context requires a deliberate rebase/import.

**Portable policy:** draft library location is TBD. Prefer project-owned `prompt_studio/drafts/<draft_id>.json` with strictly validated IDs. **Current ZIP archive v1 has an allowlist; new drafts are not portable today.** A later phase must explicitly extend archive allowlist/manifest validation and demonstrate Save As/import/overwrite/Trash behavior before advertising portable Studio drafts. Never smuggle drafts into `notes` or unvalidated top-level project fields. Project-owned source media stay owned by existing media manager.

## 3. PS1 transfer API/UX design (proposed, not implemented)

- **Read context:** a small `MorphorumAnimation` bridge must return a structured snapshot of the *live unsaved editor draft*, project ID, editor dirty flag, editor mutation counter, saved ETag, model capabilities and selected start media. It must never force Save Project. Current `collectProject()` is private; export a safe explicit snapshot method, not access to mutable state.
- **Import:** always explicit. Create Studio draft from `tracks.prompts.*` as native authority, reconcile any currently edited form fields, and preserve field-level provenance. Show warning if canonical tracks and legacy row edits would differ and ask for a deliberate source choice.
- **Preview diff:** list added/deleted/moved keyframes separately by lane, changed `value` strings, Hold/Blend mode changes, LoRA tag changes, and editor-vs-saved conflict. Suppress no-op edits. Only selected prompt-related fields may transfer.
- **Apply:** require matching project ID/model/fps/frames and a recognized editor mutation/revision; confirm diff; update only `tracks.prompts.positive`, `tracks.prompts.negative`, synchronized `prompts`, `negative_prompts`, and positive `animation.prompt_transition` in the **in-memory Editor draft**. Preserve all other track groups and project fields. Surface per-track negative interpolation if current row UI cannot represent it. Mark the Editor dirty, invalidate previews, do **not** call save endpoint.
- **Save:** explicit existing Save Project, with `If-Match` based on last observed ETag (or equivalent atomic revision guard). On 412 show reload/rebase/cancel and retain Studio draft. Guard against project-switch races and animation/timeline jobs. Never silently change the model, start image, LoRA weight or audio.
- **Inspector:** evaluate a **normalized copy** of the preview project via existing backend resolver (read-only proposed API); use `from_text/to_text/from_weight/to_weight` and resolved LoRA list. Label availability vs GPU-verified conditioning; do not run a second JS renderer.

## 4. PS6 audio alignment contract (planning now, implementing in PS6)

- **Inputs:** attached project media via existing `use-soundtrack` analysis, or already project-owned managed WAV; restored analysis by source SHA, manual marker overrides and optional existing Motion Director cues. Never upload entire audio to an LLM by default.
- **Timebase:** project frames are integers `0..max_frames-1`; project duration `max_frames/fps`. Event snap candidate is `floor(time_seconds * fps + 0.5)` for nonnegative seconds. Reject non-finite/negative and **out-of-animation** candidates by default instead of silently clamping; user may explicitly choose an endpoint clamp later. Record original timestamp, snapped frame, snapped time and drift.
- **Collision policy:** stable order by `(time_seconds, id)`; protect locked scenes; if two requested events quantize to the same frame, show conflict and require drop/offset/manual selection. Never overwrite a prompt or insert duplicate frame silently. Disabled markers ignored. Different audio source SHA, edited marker ID set, FPS/frame-count or unavailable analysis mark alignment stale.
- **Scope:** existing WAV and camera/motion tracks are read-only. Music sections and dramatic pacing are suggestions; saved prompt frame positions change only after user diff/confirmation. Clear availability warning for `max_frames > 3000` under present audio analysis limits.

## 5. PS0 golden fixtures

- `tests/fixtures/prompt_studio/import_independent_tracks.json`: schema-v1 **design fixture** with distinct positive/negative keyframe positions and interpolation, exact LoRA tag, and expected Hold/Blend endpoints. **Not** a recorded GPU result.
- `tests/fixtures/prompt_studio/audio_alignment_edges.json`: deterministic 23.976 FPS snap cases (duplicate frame, valid event, and beyond-duration rejection) with a synthetic source SHA. **Not** an attached WAV or recorded detector output.

Fixture contents become executable golden tests in PS1/PS2/PS6. No runtime code change is implied by adding them.

## 6. Regression/acceptance matrix and gates

| Gate | Mandatory cases | Owner physical acceptance |
| --- | --- | --- |
| PS0 review | Native field audit, draft v1 schema, source/version provenance, fixture examples, gap list | Review PS0 plan before PS1 |
| PS1 import/apply | Clean project, unsaved form, independent lanes, exact raw prompt/LoRA bytes, no-op, editor switch, stale ETag, model/FPS change, Save As/ZIP policy | Windows import→Apply→Save→reload; verify no camera/media modification |
| PS2 timeline/inspector | Frame 0, last frame, 1-frame project, 543 frames, separately keyed negatives, hold/blend, drag collisions, undo/redo, canonical resolver parity | Desktop + real mobile touch; no false render-parity claims |
| PS3 LoRA composer | Literal tags, multiple tags, whitespace, trigger duplicates, unknown names, out-of-family adapters, negative-tag refusal | Physical SDXL and managed Z-Image; FLUX gated |
| PS4/PS5 AI | Offline/manual path, invalid JSON, frames outside range, invented adapters, text/vision capability, opt-in source-image privacy, VRAM limits | Owner Windows/LAN model tests |
| PS6 audio | No audio, original/edited markers, source SHA change, cue collisions, `23.976` FPS, 3000+ limit, locked scenes, preview/diff, AI disconnected | WAV → storyboard → rendered aligned clip on Windows |
| PS7/PS9 | Family-specific blend, renderer parity, Parseq if independently enabled, ZIP/Save As, installer, full CI and user docs | Separate signoff before any `main` merge |

**PS0 exit condition:** Design and fixtures are reviewed; unresolved PS1 issues are identified. PS0 documentation creation alone is **not** a claim of tests passing or permission to implement PS1. Keep PQ, Z-Image single-file research, and `main` unchanged.

## PS1.1 communication bridge (2026-10-21)

Implementation: `frontend/dist/assets/prompt-studio-bridge.js` with side-effect-free track validators and patch/diff helpers; `window.MorphorumAnimation.getPromptStudioEditorSnapshot()`, `previewPromptStudioTransfer(snapshot, tracks)` and `applyPromptStudioTransfer(snapshot, tracks)` (async confirmation, fresh ETag check, in-memory-only). No Prompt Studio UI or persistent Studio drafts yet.

- Imported text/LoRA directives and separate positive/negative lanes are copied without silent rewriting. Combined legacy Editor row text edits are reflected lane by lane; structural row changes are intentionally **not importable** until a safe lane-aware UI is ready. Existing Editor controls still work.
- Captures server ETag on project load; snapshots are rejected on stale project ID/editor revision/input signature/saved revision. After PS apply, normal **Save Project** sends If-Match for that staged draft. No PUT on bridge apply. Timeline auto-save refuses while staged PS changes await explicit Save Project.
- Browser/editor mutations outside the PS apply flow still include legacy save paths without unconditional If-Match; complete them and the cross-operation revision lifecycle in **PS1.2**. This bridge is **not** a declaration that full PS1 is tested. Node source/logic regression: `tests/frontend_prompt_studio_bridge.test.cjs`. Physical Windows and real browser testing remain pending.

### PS1.1 canonical-prompt save boundary

For a Studio-staged editor draft, Save Project sends `If-Match` and `X-Morphorum-Prompt-Tracks: canonical`. The backend rejects that special mode without `If-Match`; under the project save lock it preserves **only** the two incoming canonical prompt tracks during legacy reconciliation while still merging unrelated unsaved legacy camera/generation changes. Ordinary Save Project and other API callers retain their previous legacy precedence rules. Backend regression: `test_ps1_staged_prompt_save_preserves_independent_lanes_and_unsaved_camera_changes`. This is not a claim that all other save/mutation paths have been hardened yet.

## PS1.2 guarded Editor saves and timeline boundary (2026-10-21)

- **Ordinary Save Project**, form autosave before timeline editing, audio-length Save, Motion Lab's form pre-save and Project Manager rename now send the saved project's quoted revision via `If-Match`. A stale HTTP 412 leaves the local unsaved form intact with a reload/review error.
- **Native timeline CRUD:** upsert/delete/move/interpolation use backend `mutate_animation_project` under `_PROJECT_SAVE_LOCK`; optional `If-Match` is checked atomically before reading/editing. New ETag is returned for sequential browser operations. Legacy external clients can omit If-Match for compatibility.
- **Studio staging:** Prompt-only Apply remains in-memory. Project Editor explicit Save uses canonical prompt tracks with If-Match. Indirect Motion Lab/duration saves are blocked until a Studio-staged prompt is explicitly saved.
- **While-save edits:** The browser tracks an `editorRevision`; newer form edits made during a slow network request are not automatically cleared/repainted. This is not a multi-workspace transaction.
- **Remaining boundaries:** source-image media writes, independent project imports, Motion Lab direct Apply and other endpoints are not all revision-guarded by this milestone; concurrent external mutations still change the saved project ETag and block subsequent Editor guarded saves. Do not claim exhaustive concurrency hardening or physical Windows acceptance.
- Tests: `tests/test_ps12_project_revision.py`, existing `tests/test_animation_projects.py`, `tests/frontend_prompt_studio_bridge.test.cjs`, CI. No standalone Prompt Studio UI in PS1.2.

### PS1.2 Motion Lab direct Apply

`POST /motion-lab/apply` now accepts an optional `If-Match` and uses the atomic backend mutation helper. The browser sends the project's loaded revision for Apply and camera rebase; preview remains read-only. Studio-staged prompt edits must be explicitly saved before Motion Lab Apply. Stale revisions return HTTP 412, separate from the existing camera conflict/rebase decision. Legacy clients may omit If-Match.

### Source-image mutation safeguard

Upload and Clear Source Image now accept optional `If-Match` and perform their project update **inside the same atomic saved-revision check** as timeline writes. Stale writes return HTTP 412 before replacing or unlinking the source image. The Project Editor supplies its loaded ETag and reconciles the saved revision after a successful asset change, preserving other unsaved form edits. Legacy API clients may still omit If-Match. The broader soundtrack/ZIP/import side-effect audit remains separate.

## PS1.3 visible manual workspace (2026-10-21)

`frontend/dist/assets/prompt-studio.js` mounts `Project → Prompt Studio` as a separate panel within the existing animation workspaces, accessible from the Editor's prompt-keyframe card. The user must explicitly **Import Existing Prompts**. A browser-memory Studio draft holds independent positive/negative lanes, supports frame/text edits, Hold/Blend, add/move/remove, and rejects duplicate frames or changes to frame zero. **Preview Changes** compares the imported tracks with edited tracks and consults the live Editor guard; **Apply to Animation** invokes the existing confirmation-gated prompt-only in-memory bridge, then navigates to Editor for explicit Save Project. Studio and Editor controls are isolated; ordinary Editor enable/disable and dirty-state observers exclude the Studio panel. There is no separate renderer, network AI request, prompt archive, or automatic project save. Draft changes are lost on browser reload; later phases will add persistent drafts and visual drag/snap timeline. See [manual acceptance guide](PROMPT_STUDIO_PS1_MANUAL.md).

## PS1.4: project-owned persistent drafts and portable archives (2026-10-21)

`backend/morphorum/prompt_studio_drafts.py` stores verified version-1 `morphorum.prompt-studio-draft` JSON files at `prompt_studio/drafts/<32hex>.json` inside the current project's directory, never in `project.json`. Every draft retains its originally imported positive and negative tracks, edited tracks, model/timing/start-image reference, and human-readable name. A maximum of 30 drafts and 8 MiB per draft is enforced. HTTP list/create/read/update/delete operations are provided at `/api/animation/projects/{id}/prompt-studio/drafts`; update/delete require a strong draft ETag and refuse stale writes with HTTP 412.

The WebUI includes Save Draft, Save As New Draft, Load Draft, Delete Draft and a per-project selector. Resume fetches the current Editor snapshot. It only enables Preview/Apply when the recorded baseline tracks and model/FPS/frame count/start image match the live Editor. Mismatched drafts remain editable and persistable without any automatic rebase, but **cannot transfer over newer Editor prompts**.

Project ZIP export includes verified Studio drafts under a strict filename allowlist with manifest hashes. Import validates version, identity, track structure, archive entry hashes and size. Save Project As copies validated drafts and rewrites only the owning `project_id`. No generated renders, media caches, renderer changes, LLM integrations, or audio scheduling are introduced. This phase awaits owner Windows/mobile acceptance.

## PS4 Ollama suggestion boundary (2026-10-21)

`backend/morphorum/prompt_studio_ollama.py` restricts configured HTTP endpoints to loopback or explicitly enabled private numeric LAN addresses. Public/hostname URLs (except `localhost`), credentials, arbitrary paths and redirects are rejected. Bounded requests/responses, timeouts and `trust_env=False` mitigate unintended outbound access. `POST /api/prompt-studio/ollama/models` reads installed model names and informative metadata only; it does not download models or infer vision support. `POST /api/prompt-studio/ollama/generate` accepts a bounded story, selected model family, native prompt tracks, timeline/FPS and Create/Refine mode, and returns strictly validated scene text compiled to integer frames by Morphorum. Native frames never come from the LLM.

Create generates new positive tracks without editing existing negatives unless explicitly requested. Refine retains positive frame positions and exact raw LoRA tag bytes (placed at the front of the rewritten prompt with a warning). The LLM cannot insert a new LoRA directive, project patch, formula or executable code via the scene schema. Results are nonpersistent suggestions until the browser's explicit review and **Accept Into Studio Draft**; Editor Apply and Project Save remain separately gated. Draft v1 optionally stores `ai_provenance` (Ollama model/family/mode/scene count/version/timestamp), carried through Save As and verified project ZIP. Old drafts are compatible. No media is sent, no AI weights are installed, and audio/vision processing remains PS5/PS6. Physical Windows/live Ollama acceptance is pending.

## PS5.1 profile catalog and targeted continuity refinement (2026-10-21)

`backend/morphorum/prompt_studio_profiles.py` defines a versioned, read-only authoring catalog for SDXL/FLUX/managed Z-Image. `GET /api/prompt-studio/profiles` returns guidance and clearly labels length signals as heuristic approximate words, not renderer tokenizer/conditioning evidence. A PS5-aware request sends an exact family profile ID, optional bounded `continuity.subject/style` strings and an optional positive `target_frame` valid only in Refine mode. These are never executable syntax or project settings. Existing PS4 requests without a profile retain `ps4-generic-v1` provenance.

Create compiles the full selected frame schedule. Refine Selected compiles **only** the chosen positive keyframe and retains all other positive prompt bytes/frame positions; negative generation requires a separate existing checkbox and target merges with the existing negative lane rather than replacing unaffected frames. LoRA directives from the targeted existing positive prompt are retained literally, with a warning for moved prefix placement. Lock strings are prepended unchanged when absent from generated description. All proposals remain subject to separate preview/accept, Studio draft save, guarded Editor Apply and explicit Project Save. Saved v1 draft `ai_provenance.profile` supports known versioned family IDs without reinterpreting old provenance. No vision data or renderer configuration is changed.

PS5.2 explicit consent and model-verified vision capability is still pending, as is PS5.3 physical evaluation on 16GB GPU.
