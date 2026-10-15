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

## MS4: Continuous presets and recording improvements (next stage)

Morphorum already implements gentle drift, wave, spiral, figure-eight, rocking,
push-in and pull-out native presets. MS4 should **reuse and extend** these,
rather than copy them into a second composer or replace the camera engine.

Proposed testable batches:

- **MS4.1: Unified motion arrangement.** Add a visible, frame-ranged continuous
  motion layer editor in Motion Studio, synchronized with the project audio
  waveform. Preset choice, intensity, cycle, fade and start/end time should
  be intuitive on desktop and mobile. Stage and Preview before Apply.
- **MS4.2: Range-based Add/Replace.** Make it explicit whether a motion
  pattern layers on the existing camera path or replaces motion on selected
  axes inside a specified time range; avoid overwriting other axes, manual
  cues, sound channels, original source image or project configuration.
- **MS4.3: Named custom presets.** Save and reload user-defined combinations,
  including axis mappings, strength and timing, with a clear distinction
  between a reusable preset and a project's saved motion layers.
- **MS4.4: Recording integration and polish.** Reuse existing keyboard/touch
  six-axis recording, improve optional controller mapping, add velocity-unit
  help and configurable axis limits, and validate no abrupt segment jumps.

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
