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

## MS3: Independent sound channels (not implemented)

Add DMS-inspired Bass/Snare/Crash/custom channels with per-channel frequency
bands, thresholds, transient/intensity/ripple modes, attack/return,
strength, offsets, active intervals, overlap and non-drifting pulse math.
Offer cached analysis and per-channel recalculation. Keep manual cues and
raw events independent. Include a readable spectrum display and optional
channel-from-peak controls after the core channel engine is stable.

## MS4: Continuous presets and recording improvements (not implemented)

Bring DMS-style drift, wave, spiral, rocking, reveal and fly-through
compositions to current Motion Lab. Add range-based Add/Replace, named custom
presets, explicit velocity units and axis limits, and improved controller
configurations without rewriting existing recorded takes or advanced tracks.

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

