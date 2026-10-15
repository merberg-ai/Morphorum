# Motion Studio integration roadmap

Development branch: `dev-webui`. Integration reference: immutable
`checkpoint/audio-motion-director-da4-5-windows-verified-20261011`
and the archived `dev-audio` line. Base release: `main` at merge #38.
**Do not merge to main without the project owner's physical acceptance.**

## Goal

Make the native Motion Studio a first-class workspace for the **currently open
Morphorum project**, inspired by Deforum-Motion-Studio (DMS). Compose camera
motion against a project-owned soundtrack, preview/adjust it, and explicitly
apply to the existing six-axis camera tracks and render pipeline.

We are porting tested Morphorum components from `dev-audio`, not merging the
old branch. Upstream DMS remains a behavior and workflow reference; its native
Tkinter code and Deforum-export math are not directly copied into Morphorum.

## MS1: Rebase audio foundation onto current backend (implemented, CI passed)

- Imported `audio_events.py` for high-resolution, FPS-independent spectral
  attack candidates in kick, snare and highs bands. Candidates are **not**
  source-separated drum classifications.
- Imported `audio_marker_overrides.py` for separately persisted, source-bound
  manual marker edits and `audio_motion_cues.py` for validated choreography.
- Imported `audio_motion_presets.py` for deterministic nine-preset native
  six-axis cue compilation; wired additive `audio_cues` layers into the
  *current* `motion_lab.py` normalizer and composer.
- Enhanced `audio_motion_upload.py` to return stereo waveform overviews,
  timestamped events and safe FPS recommendations without changing the
  project's FPS or number of frames.
- Added project-scoped cue and marker read/write endpoints **without replacing
  or downgrading** existing backend-only, media-inventory, Studio or soundtrack
  APIs. The project-owned WAV stays in `motion_lab_audio/<sha256>.wav`.
- Carried forward source-bound validation and audio-event/native-motion
  regression cases. CI includes all backend tests.

## MS2: Visible project-connected Motion Studio (integration pass implemented;
CI passed; physical acceptance pending)

- Exposed **Motion Studio** in the Motion Lab workspace navigation rather than
  keeping Audio Motion in a hidden panel. Deforum **Import Motion Settings**
  remains a separate tool.
- Reused the existing DOM controls: WAV selection, beat-detection settings,
  frame-aligned editor, playback and layer apply. Added an independent
  full-width waveform/detection/marker workspace, cue authoring and optional
  Find Beats/batch assignment from `dev-audio`.
- Restores source-bound marker edits and saved cue documents after both WAV
  upload and automatic WAV reload through the accepted W2 project-owned
  media workflow. Project switches and manual uploads guard against stale
  asynchronous requests. No browser file-path dependency.
- Manual cues can be authored without selecting a detected drum hit. Preview
  and Apply must be explicit; they stage or replace **one** source-keyed
  additive Director layer and use existing conflict/rebase safeguards.
- Additional Node UI regressions added to syntax checks. Existing project
  media, Deforum import and Motion Lab navigation tests were updated to
  reflect two separate visible workspaces.

**Physical test gate:** On the Omen, check that the same WAV reopens with
waveform, corrected markers and manually saved camera cues. Add a push zoom
at a riff and a roll at a later drum hit; save, preview in Motion Curves,
apply, reopen and verify that reapplication is non-doubling. Test phone
navigation, waveform zoom/seek, markers, Find Beats, and video/audio export.
Existing project media and imported motion must still work. Do not promote
MS1/MS2 to main before this gate passes.

## MS3: Independent sound channels (MS3a and MS3b physically accepted)

**MS3a now implemented** on `dev-webui`:

- Visible **Independent Sound Channels** workspace inside Motion Studio with
  Bass, Snare, Crash defaults and up to 8 editable custom channels.
- Independent low/high frequencies, native camera axis, Hits/Intensity/Ripple
  response, enable, strength, threshold, sensitivity, attack/release, cooldown,
  start/end frame and signed offset for each channel.
- On-demand, checksum-verified managed WAV FFT analysis per frequency range.
  This never changes or uploads another copy of the soundtrack; the new
  `POST /api/animation/projects/<id>/motion-lab/audio/<sha256>/bands`
  endpoint analyzes the **saved** PCM WAV at the current project FPS and frame
  count. Per-band results are normalized and cached for repeated previews.
- One native, additive, source-bound `audio_channels` Motion Lab layer carries
  up to eight separately editable channels. Re-stage replaces the existing
  layer for that WAV, preventing doubling; unrelated manual cues, recordings,
  camera base tracks, prompts and soundtrack remain untouched.
- Explicit Stage, Preview Curves and Apply buttons. Apply uses the existing
  camera-conflict/rebase protections. Channel editing resumes from the saved
  layer when reopening a project WAV.
- Hits use balanced attack/return pulses. Intensity and Ripple calculate
  bounded camera **displacements** before converting to per-frame velocities;
  all responses return to the original camera path with no persistent drift.
- Windows/mobile responsive controls; CI tests cover input bounds, short and
  corrupt WAV, overlap, additive composition, no-doubling, and API wiring.

**MS3b implemented and physically accepted:**
- A **time-averaged logarithmic spectrum** (20 Hz to the WAV Nyquist or
  20 kHz), calculated from up to 48 PCM windows and returned as a bounded
  96-point visualization by
  `GET /api/animation/projects/<id>/motion-lab/audio/<sha256>/spectrum`.
  This is not a real-time spectrogram or source separation.
- Select any Bass/Snare/Crash/custom channel to highlight its passband on
  the spectrum. Drag the low/high edge with mouse or touch, or focus the
  spectrum and use arrow keys with the keyboard edge selector. The numeric
  inputs stay synchronized and nothing is applied until Stage/Apply.
- **Analyze channel responses** previews the selected channel's normalized
  energy per project frame, with a visible threshold guide. Changing band
  frequencies invalidates that preview until rerun; the existing Preview
  Curves control is the authoritative native camera velocity preview.
- Bounded spectrum and frame-analysis caching by project/WAV SHA-256,
  with project-switch race guards and no new file upload or project mutation.
  The existing single-layer non-doubling and source-bound behavior remains.
- CI: 646 Python tests passed, 1 skipped; Morphorum self-test, frontend
  regressions and Windows/Linux installer workflows passed.

**Remaining optional MS3 polish:** live/time-varying spectrogram, combined
multi-channel velocity overlay and additional preset packs. Those are not
claimed as implemented. Spectral targeting does **not** separate instrumental
stems.

**MS3 physical test gate:** open an existing 3D project with a saved WAV;
inspect Motion Studio's Independent Sound Channels card. Start with Bass
on Translation Z, Snare on Pitch, Crash on Roll; change one channel's
frequency, threshold or response; Stage, Preview Curves, Apply, reopen the
project and confirm settings and camera movement persist. Apply again to
verify no additional contribution. Test disabling a channel, adding a custom
one, 24/30 FPS, phone layout, and existing manual cue editing. Confirm audio
analysis errors are shown rather than silently changing camera tracks.

## MS4: Continuous presets and recording improvements (MS4.1–MS4.3 accepted; MS4.4 physical gate pending)

Morphorum already implements gentle drift, wave, spiral, figure-eight, rocking,
push-in and pull-out native presets. MS4 should **reuse and extend** these,
rather than copy them into a second composer or replace the camera engine.

Proposed testable batches:

- **MS4.1: Unified motion arrangement (implemented, physically accepted).**
  A visible **Continuous Camera Motion** card in Motion Studio reuses the
  native Motion Lab preset engine and layer stack. It shows existing preset
  regions across the project frame timeline, synchronized audio playhead and
  frame-accurate seek, editable numerical and touch/keyboard range sliders,
  preset, strength, cycle, fade, and start/end controls. Select any existing
  preset region to update it in place rather than doubling its contribution.
  Explicit **Stage Movement**, **Preview Curves**, and **Apply to Animation**
  reuse the current layer history and conflict-checked compositor. No audio
  or GPU rendering is required to edit continuous movement. MS4.1 uses
  **additive** movement only; axis-specific Replace belongs to MS4.2.
- **MS4.2: Range-based Add/Replace (implemented, physically accepted).**
  Select Add or Replace for a continuous preset and check only the camera
  axes it should affect. The native Motion Lab compiler now accepts an
  optional, strictly validated `axes` list on preset layers; existing
  presets without that list retain their original behavior. Replace resets
  only the selected axis increments, **only inside the selected frame range**,
  respecting the existing layer order, project camera-base conflict policy and
  per-axis safety limits. The 'Still / Clear Selected Axes' preset is exposed
  in Replace mode. Editing an existing movement retains its ID and avoids
  doubling layers. Save/reopen and native animation render use the same layer
  data, not a separate preview renderer. Existing manual audio cues,
  sound-channel layers, recordings, prompts, model and soundtrack are
  unchanged by staging. Automated tests cover axis/frame isolation, input
  validation, legacy preset compatibility and no-double-apply.
- **MS4.3: Named custom presets (implemented; physically accepted).**
  Use **My Motion Presets** inside Continuous Camera Motion to save a named
  reusable template from the current editor, choose it again, load it into the
  editor, update its settings, or delete it. A named template includes native
  preset, Add/Replace, selected axes, strength, cycle/fade seconds and
  **project-relative start/end fractions**; loading it scales the range to
  the destination project's frame count. Templates are saved atomically in
  `data/motion-studio-presets.json` and shared by any browser/client connected
  to the same Morphorum instance. They are **not** stored inside individual
  project files and do **not** change motion layers until the user explicitly
  clicks **Stage Movement** and later **Apply to Animation**. Names must be
  unique (case-insensitive), 1–64 printable characters, with up to 64 templates.
  Refresh Library syncs from the server; the API validates every motion
  field and protects other layer types. These templates contain neither
  audio nor recordings, and do not change the native motion compiler.
- **MS4.4: Recording integration and polish (implemented; physical gate pending).**
  Uses the existing native six-axis keyboard/touch/gamepad recorder and
  frame-aligned punch-in splicer. Adds Standard/Swap Sticks controller layouts,
  contextual per-frame and per-second sensitivity guidance, six project-owned
  camera increment limits, and an adjustable 0–12-frame feather for transitions
  inside a punch-in. No new recording engine, FPS conversion or independent
  render schedule is introduced.

Each batch must pass CI and owner physical tests before the next. Main remains
untouched without explicit authorization.

## MS5: Synchronized preview and render/refine (not implemented)

Offer frame-mapped motion preview, recorded frame playback or split view,
soundtrack-linked seek, A/B loops, ranged correction/take replacement,
and non-destructive review of completed renders. Detect FPS/frame-count
mismatches. Reuse Morphorum frame-player and stored render assets.

## MS6: Release integration and acceptance (not implemented)

Run complete Python, Node and installer CI plus physical Windows and mobile
regressions; validate 12/24/30/60 FPS, long music, multiple channels/cues,
save/close/reopen, disabled/missing media, native render/audio mux and no
duplicate contribution after reapply. Update public docs after acceptance
and merge by explicit project-owner approval only.

## Safety and interoperability

Never silently alter FPS, max_frames, prompts, seeds, source image, soundtrack
or existing Motion Lab layers while analyzing or restoring audio.
Save editable cues/markers separately and generate camera tracks only on
explicit Apply. Keep existing strict project asset API contracts for Studio.
Upstream Deforum-Motion-Studio is publicly readable but has no declared
LICENSE file; independent implementation is preferred until source reuse
terms are documented, despite the project's owner's informal permission.

## MS1/MS2 source-integration checkpoint (2026-10-15)

The first integration pass on `dev-webui` has passed the draft PR #39 checks:

- **Syntax checks:** passed, including all five newly integrated Audio Motion
  frontend regression files and existing shared WebUI tests.
- **Backend tests:** 613 passed, 1 skipped, including new source-bound marker,
  cue, spectral event, short-clip and native-six-axis tests.
- **Morphorum self-test:** passed.
- **Installer checks:** passed on the CI Windows/Linux paths.

The initial port briefly exposed a short-WAV SciPy STFT overlap issue and
sidebar test index assumptions. Both are repaired. The accepted W1/W2 project
media contract remains intact, and this work does not change `main`.

**Next gate:** physical Windows + Android browser workflow testing of Motion
Studio with existing project WAVs, edited markers and saved camera cues. Do
not treat a successful CI run as proof that touch/desktop interaction or GPU
animation previews are physically accepted. Keep draft PR #39 unmerged.

## MS1/MS2 physical acceptance (2026-10-15)

The project owner tested the Motion Studio integration on the physical
Morphorum installation and confirmed it **works as expected**. This records
physical acceptance of the first Motion Studio integration pass, alongside
the previously verified automated checks (613 passed, 1 skipped).
Proceed with MS3 on `dev-webui` without merging the draft PR or changing
`main`. Retain `dev-audio` as a reference checkpoint only.


## MS3a source checkpoint (2026-10-15)

The independent frequency-channel engine and WebUI are implemented on the
permanent `dev-webui` branch, **not merged into `main`**. Draft PR #39
continues as a review/test gate. Automated checks completed: **638 Python
tests passed, 1 skipped**, successful Morphorum self-test, Syntax/browser
regressions and Windows/Linux installer workflows. The accepted MS1/MS2
foundation remains part of the branch.

**Physical Windows and Android browser acceptance of MS3a is still pending.**
MS3b spectrum and channel authoring polish, MS4/MS5/MS6 remain future work.

## MS3a physical acceptance and MS3b checkpoint (2026-10-15)

The project owner tested MS3a on the physical installation and confirmed
independent sound channels **work as expected**. MS3a is accepted.
On that basis MS3b was built on the same `dev-webui` branch. CI for the
spectrum/preview implementation: **646 passed, 1 skipped** in Python,
successful Morphorum self-test, Syntax, installer and Node browser checks.

**MS3b physical acceptance remains pending.** Open a saved-WAV project in
Motion Studio; the new frequency spectrum should appear above the channel
list. Select Bass, Snare and Crash in turn, verify each highlighted range,
drag low/high limits, test touch/keyboard arrows, choose Analyze channel
responses, review the envelope and threshold, then Stage, Preview Curves
and Apply. Reopen the project and confirm range persistence and unchanged
manual cue layers. Do not merge into `main` before acceptance.

## MS3b physical acceptance / saved project soundtrack reuse (2026-10-15)

The project owner confirmed the MS3b interactive spectrum and channel energy
preview **work as expected** in the physical Morphorum test installation.
MS3b is accepted; no merge to `main` is authorized.

### New quality-of-life integration: Use Saved Project Soundtrack

The user observed that Motion Studio previously required another WAV upload
even when the open project already had a soundtrack attachment. The
**Use Saved Project Soundtrack** button now appears next to the regular PCM
WAV selector, enabled only for a 3D project with a verified saved soundtrack.

- The endpoint `POST /api/animation/projects/<id>/motion-lab/use-soundtrack`
  verifies the existing project-owned soundtrack via its SHA-256 and size.
- Compatible PCM WAV is analyzed directly, with no browser upload or host-side
  conversion. MP3, OGG, FLAC and incompatible WAV formats use the Morphorum
  host's configured FFmpeg (`MORPHORUM_FFMPEG` or `PATH`) to create a bounded
  PCM WAV copy for Motion Lab. FFmpeg is not needed for valid PCM WAV.
- Conversion remains bounded by the existing Motion Lab **3-minute** maximum
  and **20 MiB** analyzed WAV limit. Conversion errors and missing FFmpeg
  are shown in the WebUI with a practical explanation.
- The resulting managed WAV goes through the existing W2 media inventory and
  restoration flow. Motion Studio recovers waveform, markers, manual camera
  cues, spectrum and independent sound channels using that WAV.
- This is **explicitly initiated** by the user. Opening a project does not
  automatically start an expensive audio conversion or modify any camera
  tracks. Repeating the action with the same WAV is idempotent.
- The original attached soundtrack, checksum, export offset, project FPS,
  frame count, camera tracks and unrelated Motion Lab layers remain unchanged.
  The video-export offset is not baked into analysis.
- The old manual WAV selection still works and is available as an alternative.
  If the soundtrack cannot be used, the previous Motion Studio audio remains
  selected.

CI after this integration: **652 Python tests passed, 1 skipped**, Morphorum
self-test, browser Node regressions and installer checks passed. Physical
Windows/mobile acceptance of this soundtrack-reuse control is still pending.

**Physical test:** Open a project with an attached soundtrack. Under Motion
Lab → Motion Studio, click **Use Saved Project Soundtrack**. Confirm the
waveform, spectrum, markers and channel controls appear without a file
upload. Repeat with another project, and with MP3 if FFmpeg is configured.
Verify manual cues still persist and export audio offset is unchanged.

## Saved soundtrack reuse physical acceptance (2026-10-15)

The project owner confirmed **Use Saved Project Soundtrack** works as expected
on the physical Morphorum test installation. The completed integration
checkpoint is `c85d6f6`; the feature reuses the verified project attachment
without asking for another browser upload. Existing manual WAV import remains
available. Mark this quality-of-life batch **accepted**.

Next: MS4.1 continuous camera motion arrangement in the visible Motion Studio
workspace, built on the already existing native preset system rather than
introducing duplicate math. This is a planned stage, **not yet implemented**.
Leave draft PR #39 unmerged and `main` unchanged.

## MS4.1 native continuous-motion arrangement checkpoint (2026-10-15)

The new continuous motion editor is installed on `dev-webui` in the existing
Motion Studio. Its UI and native preset layers share **one** motion-layer
history, validation, preview/apply API and project persistence. This is a
front-end integration of already-tested native presets, not new camera math.

Features to exercise in physical acceptance:

1. Open a 3D project with saved soundtrack; navigate to Motion Studio.
2. Locate **Continuous Camera Motion** (above the Sound Channels card).
   Observe the project-length ruler, audio frame seek and initial empty
   arrangement.
3. Stage a **Gentle Drift** for the entire timeline. Adjust the Start/End
   sliders or numerical frame fields (end frame is exclusive), then Preview
   Curves. Apply to Animation and verify camera movement.
4. Select the existing colored region. Edit it to **Spiral** for a portion of
   the timeline and re-stage. The same layer must be updated (not duplicated).
   Undo/Redo and Preview Curves should reflect these changes.
5. Keep a saved audio-reactive channel and manual cue in the same project;
   staging/updating a continuous preset must **not** remove either.
6. Save, reopen, verify the continuous preset layer is retained; test audio
   seeking and sliders on desktop and phone, and a no-soundtrack project.
7. Verify prompts, model settings, attached soundtrack, source image,
   original render and offsets remain unchanged by draft edits.

**MS4.1 physical acceptance is pending.** Do not proceed to MS4.2 Replace
modes until this gate is accepted. Keep draft PR #39 unmerged and `main`
unchanged.

## MS4.1 acceptance and MS4.2 / Audio Source layout checkpoint (2026-10-15)

The project owner confirmed that **MS4.1 works as expected** on the physical
Morphorum installation. MS4.1 is accepted.

**MS4.2 implementation:** the existing continuous-motion editor now has an
Add/Replace selector and a preset-aware checkbox group for camera axes.
The native compiler filters a preset to those selected axes. The selected
frame interval is unchanged and exclusive at the end; Replace does not
clear camera motion outside the range, nor any unchecked axis. The user can
stage, inspect curves, apply, reopen and edit the existing layer rather than
creating duplicates. The existing ML0 Camera Motion Composer continues to
work with legacy preset layers and their default full-preset axis set.

**Audio Source layout improvement:** the real source controls (local WAV
selector, saved-project soundtrack button, action buttons) are reparented as
the first card directly below the Motion Studio introduction, above both the
continuous-motion arrangement and Independent Sound Channels. No duplicate
IDs or event handlers are introduced. The existing WAV and saved-soundtrack
restore paths are unchanged.

**MS4.2 physical test:**
1. Open a saved-soundtrack 3D project. Confirm **Audio Source** appears first
   and still loads the saved audio and/or local WAV successfully.
2. In Continuous Camera Motion choose Wave, Add, only Move X. Stage and
   preview. Other axes should retain their earlier movement.
3. Change that same region to Replace, choose Move X and Y, adjust frame
   range and preview. Motion on unchecked axes and outside the range should
   be preserved.
4. Choose Still / Clear Selected Axes in Replace mode for a short range,
   select only Roll, and verify other five axes remain.
5. Apply, reopen and reapply the same region, confirming mask/blend persistence
   and that movement isn't doubled. Recheck audio-reactive layers and cues.
6. Check phone-width layout and ensure the soundtrack source control remains
   above the motion editors.

At the time of this checkpoint MS4.2 was **not yet physically accepted**.
See the newer checkpoint below. Keep draft PR #39 and `main` unchanged.

## MS4.2 physical acceptance and timeline deletion cleanup (2026-10-15)

The owner reports MS4.2 Add/Replace and relocated Audio Source **working as
expected on the physical installation**. MS4.2 is accepted. Two timeline UX
issues were identified for a targeted follow-up, before MS4.3:

- The previous "Unstaged selection" bar was always rendered even after
  staging a real layer. It had no layer ID and could not be selected, so it
  looked like a second, stuck region. **Removed:** only actual staged draft
  preset layers now appear in the timeline. The editable form remains available
  whether or not it has been staged. Empty timeline explains how to stage.
- Staged continuous-motion timeline bars now have a **Remove** button. This
  deletes only that native preset layer from the **draft** via the existing
  Motion Lab undo/history mechanism. Selected-layer removal clears selection
  and resets the form; removing a different layer keeps the current selection.
  Audio/cue/channel/recording/custom layers are never removed from this panel.
  Final animation schedules are not changed until **Apply to Animation**.

The UI uses the existing theme and responsive layout. Automated frontend tests
cover staged deletion, selection state, unrelated layer preservation, busy-state
protection, and the removed phantom bar.

**Physical test for the cleanup:** Stage two movements, remove one, verify the
remaining bar can still be selected and updated. Remove the selected bar and
verify it disappears, the editor returns to New Movement, and no Unstaged
Selection reappears. Use Motion Lab Undo if needed. Apply to Animation, save
and reopen the project; verify the deleted preset is absent. Recheck audio
layers and narrow/mobile layout.

**Gate:** This cleanup still needs Windows physical verification. After it
passes, proceed with **MS4.3 named custom presets**. Keep draft PR #39 and
`main` untouched until a separate merge review.

## MS4.2 timeline cleanup acceptance and MS4.3 implementation (2026-10-15)

The project owner confirmed the MS4.2 follow-up timeline cleanup **works as
expected** on Windows. MS4.2 and its Remove control / phantom-bar correction
are accepted. **MS4.3 is implemented on `dev-webui`, awaiting owner physical
verification.** Leave `main` unchanged, and keep draft PR #39 unmerged.

### My Motion Presets behavior

1. Open a 3D animation project and visit **Motion Studio → Continuous Camera
   Motion → My Motion Presets**. Set movement type, Add/Replace, axis mask,
   strength, cycle/fade, and start/end frame selection in the editor.
2. Enter a unique name and choose **Save as New**. The preset persists on the
   Morphorum server and does not create a project motion layer.
3. Choose the saved preset and click **Load to Editor**. Loading does **not**
   stage it. Verify the current editor's mode, axis mask and numeric values.
   On a longer/shorter target project, start/end frames are proportionally
   scaled to the target frame count with at least one frame of coverage.
4. Click **+ Stage Movement** to add a new Motion Lab draft layer (existing
   selected layer is deselected when a named preset loads). **Preview Curves**
   and **Apply to Animation** continue through the native compiler.
5. To revise a named template, select it, change the editor fields or name,
   then click **Update Saved**. This updates the library item only; it does
   not rewrite any existing project layer.
6. **Delete Saved** uses the standard confirmation dialog. Deleting a library
   item does not delete a staged motion layer or camera schedules. Removing a
   staged movement instead uses the separate MS4.2 timeline **Remove** action.
7. Open a different project and/or different browser connected to the same
   Morphorum server, choose **Refresh Library**, and verify the template
   remains available. Restart Morphorum to verify on-disk persistence.

**Storage:** `data/motion-studio-presets.json` is managed by Morphorum, using
atomic replacement on writes. It can be backed up together with the `data/`
directory. This implementation shares templates within **one Morphorum
installation**; cross-installation exchange/import is a separate enhancement.
The API routes are `GET/POST /api/animation/motion-studio/custom-presets`,
`PUT/DELETE /api/animation/motion-studio/custom-presets/{preset_id}`.

**Regression gate:** Backend API tests cover persistence, create/update/delete,
name conflicts, invalid axes/values, corrupt library protection and the
64-preset bound. Browser regression tests cover saving without staging,
loading into the new-editor state, percentage-based frame scaling and
non-destructive stage. Syntax/backend/installer GitHub Actions must pass,
then Windows and mobile behavior must be physically verified before MS4.4.

## MS4.3 acceptance and MS4.4 recording polish checkpoint (2026-10-15)

The owner physically verified **MS4.3 My Motion Presets works as expected**.
MS4.3 is accepted. MS4.4 is now implemented on `dev-webui`, awaiting
physical verification. `main` remains unchanged; PR #39 remains draft.

### MS4.4 implementation

- **Optional gamepad layout:** Standard mapping retains left-stick translate
  X/Y, right-stick look (yaw/pitch), triggers Z and shoulder buttons roll.
  Swap Sticks reverses the two thumbsticks only. Axis invert checkboxes still
  apply after all keyboard/touch/gamepad sources are combined. No controller
  access is required; unavailable browser gamepads leave other inputs intact.
- **Velocity units:** Recording sensitivity is a native **per-frame**
  increment: X/Y/Z in scene units/frame, pitch/yaw/roll in degrees/frame.
  A live hint shows equivalent peak movement per second at project FPS.
  The actual movement is lower while easing, inside the deadzone or at partial
  stick pressure, and later clips under the project safety limits.
- **Project-specific axis limits:** A collapsible **Camera safety limits**
  panel exposes the six existing `motion_lab.limits` values. Each input
  validates finite values from 0.00001 to 30, preserves other axes, and marks
  the project dirty; limits are not saved without **Save** or **Apply**.
  Composition still enforces the already-existing native limit logic and
  reports per-axis clipping in diagnostics. Limits control final composed
  signals from **all** motion layers, not just recordings. Changing limits
  does not destructively clamp raw sample rows in the saved recording.
- **Punch-in transition feather:** A 0–12 frame option defaults to 3.
  During a punch-in, the original take's armed axis samples are crossfaded
  into the incoming interval using smoothstep near both ends. Unarmed axes,
  frame 0, and all frames outside the punch window are unchanged. A value of
  zero retains the previous exact hard replacement behavior. Short windows
  may not reach 100% replacement when both feathers overlap.
- Existing response easing, release tail, deterministic sample clock,
  take undo/history, end-frame validation, armed-axis restrictions, and
  protection against incomplete punch-ins remain intact.

### Physical acceptance checklist

1. Load a 3D project and inspect **Live Motion Recording**. Confirm the
   safety limits display the project defaults, the sensitivity hint reflects
   project FPS, and touch/keyboard recording still makes a draft take.
2. Enable gamepad if available. Try **Standard** and **Swap Sticks**; verify
   that only translation/look sticks swap, while Z and Roll remain on the
   triggers/shoulder buttons. Without a controller, verify keyboard/touch.
3. Set a smaller Move X or Yaw limit (e.g., 0.015 scene units/frame and
   0.15 degrees/frame). Confirm the Editor reports unsaved settings.
   Preview existing layers and check per-axis clipping diagnostics. Save or
   Apply and reopen; limits should persist. Restore preferred limits afterward.
4. Record a long take with movement on X and yaw. Punch into a short middle
   frame range on X only. With feather set to 3, verify the edges join more
   gently, yaw and outside frames remain unchanged, and Undo restores the
   original take. Test feather 0 for exact replacement. A punch-in must
   still complete its entire selected interval to be committed.
5. Recheck phone-width layout, axis inversion, release tail, optional
   gamepad security messaging, and unchanged soundtrack/audio layers.

**CI gate:** Node recorder frame-clock and punch-in tests run from Syntax
checks; Python recording/camera composition tests run in Backend tests;
installer checks remain required. Do not begin MS5 or merge PR #39 before
physical approval of MS4.4.
