# Motion Studio: synchronize camera motion with audio

**Motion Studio** is part of **Motion Lab** in Morphorum's browser interface. It lets you prepare, preview and apply frame-aligned camera motion using a project soundtrack, manually placed motion cues, and frequency-based sound channels. It works with the project's native six-axis 3D camera tracks rather than starting another animation engine.

> **Before you start:** Open a saved **3D animation project** with a defined frame count and FPS. Motion Studio changes motion only when you explicitly stage, preview or apply it. Saving a project or browsing these controls does not start an AI render. For installation/model setup, see [Getting started](GETTING_STARTED.md).

## 1. Open Motion Studio and choose audio

1. In **Motion Lab**, open a 3D project in **Project Manager** or **Project Editor**.
2. Choose **Motion Studio** in the Motion Lab navigation.
3. In **Audio Source**, choose a local PCM WAV, or select **Use Saved Project Soundtrack** if one is already attached to the project.
4. Wait for analysis to complete before making audio-linked motion. Check that the displayed soundtrack, project duration and FPS are correct.

The saved-project shortcut reuses a verified project-owned soundtrack; it does not require you to browse for the same file again. If the attachment is not PCM WAV, the backend may convert a supported input using FFmpeg. Errors or missing FFmpeg will be reported instead of silently replacing the previous audio.

An imported Deforum settings file can reference a local soundtrack path, but that **reference alone is not an uploaded soundtrack**. You still need to choose/attach audio explicitly. See [Import Deforum Motion Settings](DEFORUM_MOTION_SETTINGS_IMPORT.md).

## 2. Choose how audio affects motion

Motion Studio offers complementary workflows:

| Tool | Purpose |
| --- | --- |
| **Manual cues and event markers** | Inspect detected musical events, adjust their timing/enabled state, and stage camera responses at specific points |
| **Independent sound channels** | Use frequency ranges such as bass, snare and crash to drive separately configured camera axes |
| **Frequency spectrum** | View a time-averaged spectrum of the saved WAV and adjust a channel's low/high frequency bounds with controls or handles |
| **Continuous Camera Motion** | Add sustained camera movement over a frame range, independently of individual beats |
| **My Motion Presets** | Save/reload reusable continuous motion settings on the current Morphorum installation |
| **Live Motion Recording** | Perform a keyboard, touch or optional compatible-gamepad camera take, including supported punch-in editing |

These all feed Motion Lab's native camera-layer stack. Their parameters are not interchangeable: audio event detection, frequency envelopes, continuous preset motion and recording are different ways to author motion.

## 3. Stage a continuous movement

1. Find **Continuous Camera Motion** and choose a preset.
2. Select a blend method: **Add motion** to combine with existing movement or **Replace selected axes in range** to change only the chosen axes within that segment.
3. Set strength, cycle, fade, start and end frames. The **end frame is exclusive**.
4. Check the axes that the movement should affect. Leave unwanted axes unchecked to preserve existing motion on them.
5. Choose **Stage Movement**, then **Preview Curves** to inspect the result.
6. Choose **Apply to Animation** when satisfied. Applying updates the project's native 3D camera schedules using the usual save/conflict safeguards.

Stage and Preview are different from Apply, and neither is the AI animation render. You can edit, reorder, disable, remove and undo draft layers before applying. The shared preset library stores reusable movement settings, not an independent copy of a completed render.

## 4. Add frequency-driven channels or beat cues

For frequency-driven movement, start with the example **Bass**, **Snare** and **Crash** channels or customize each channel's frequency band, target camera axis, hit/ripple response, intensity and timing. Use the spectrum to check which frequencies you are selecting. Stage channels, preview their curves, then Apply to write the motion.

For manual musical timing, review detected events and any editable marker overrides, place or revise cues, then preview before applying. Changes belong to the selected project/soundtrack rather than modifying your original audio file.

A channel or manual cue can produce strong motion even when its strength looks modest. Preview with conservative values before increasing the response, especially when multiple layers affect the same axis.

## 5. Review, render and refine

After **Apply**, inspect **Motion Curves & Camera Path** or **Camera Motion Preview**. A preview can show frame-aligned motion without rendering an AI animation.

Select a valid generation model in **Project Editor**, then explicitly choose **Render Animation**. Use **Render Monitor** for progress and **Outputs** to inspect completed frames or export MP4/WebM where FFmpeg is available. If a soundtrack is included in the render's frozen audio snapshot, supported video exports can carry it.

Supported Motion Lab review/refinement tools can compare a completed render with saved motion and apply bounded adjustments to selected frames. Make sure you are comparing the intended **saved render**, and inspect which frames and axes will be affected before applying a refinement. Existing project settings and source media are protected by their normal confirmation and conflict checks.

## Constraints and troubleshooting

- Motion Studio authoring is for **3D projects**. If controls are disabled, verify that a project is open in 3D mode and no conflicting preview, recording or render is active.
- Project **FPS and frame count** determine the frame-aligned audio analysis and motion ranges. Changing them may require reanalysis or adjustment to existing layers.
- The **soundtrack's original file**, project prompts, model settings and source images are not altered simply by staging camera motion.
- Supported audio conversion/export functions use **FFmpeg**. Check `ffmpeg -version` if conversion or export is unavailable.
- The detected rhythm/frequency profile is an estimate; some soundtracks require manual markers or frequency tuning.
- Always start with a short preview or render and keep important projects backed up. Morphorum is still early alpha software.

For general error recovery, see [Troubleshooting](TROUBLESHOOTING.md). For safe model/installation setup, see [Installation and maintenance](INSTALLATION.md).
