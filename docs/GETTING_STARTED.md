# Getting started with Morphorum

This guide starts **after you have installed Morphorum**. For the installer itself, go to the [README](../README.md#quick-start). You do not need to install Python manually or know AI animation beforehand. Morphorum runs locally on your computer.

> [!TIP]
> Try one small image before a long animation. A single test image is the fastest way to confirm your model and GPU are working.

## 1. Open the application

Launch Morphorum from the folder where you installed it.

**Windows, default location** (PowerShell):

```powershell
cd C:\Morphorum
.\run.bat
```

**Linux, default location** (terminal):

```bash
cd ~/Morphorum
./run.sh
```

Keep that window running, and visit **http://127.0.0.1:7865** in your browser. If you chose another port during installation, use that number instead.

Morphorum runs on your own computer. The browser is only the interface: closing the browser tab does not necessarily stop a server-side job. To shut down Morphorum, press **Ctrl+C** in the terminal.

## First-run setup wizard

If this is a **fresh installation**, Morphorum opens a separate seven-step setup wizard when you first visit the WebUI. This is distinct from **Motion Lab → New Project Wizard**, which is for creating ordinary animation projects later.

1. Review host diagnostics and the explanation of WebUI (the recommended default) versus authenticated backend-only mode.
2. Add paths to existing **SDXL** or **FLUX** checkpoint folders on the computer running Morphorum. Check the folders and choose **Save Folders & Scan**. File detection is preliminary, not proof that every model will load.
3. Add optional SDXL, FLUX or Z-Image LoRA folders, or simply continue. LoRAs do not replace a base checkpoint.
4. Optionally download **Z-Image-Turbo** (approximately 33 GB). The download requires a separate confirmation. You can continue while the download runs and return to inspect its status.
5. Select **Gentle Dolly In** or **Gentle Dolly Out**. Both use a small 512 × 512 3D animation, 48 frames at 12 FPS. Choose an available checkpoint, or use **No model yet** to make an editable but not render-ready example.
6. On **Review & Finish**, choose **Create Example & Open Editor** to save a new project and open it in the existing Animation Project Editor. You can also select **Finish Without Example**. Neither action automatically starts an AI render.

Use **Back** and **Next** to review the settings. **Skip for now** ends onboarding without deleting your existing configuration. Your progress is stored on the Morphorum host, so you can resume after reopening a browser or restarting the server. The completed or skipped wizard does not appear again automatically.

To reopen onboarding on an existing installation, go to **Settings → Setup Wizard**. You can also restart in WebUI mode with `.\run.bat --setup-wizard` (Windows) or `./run.sh --setup-wizard` (Linux). Changing to backend-only requires a server restart; the browser setup wizard does not run in that mode.

If your example has no base model, first configure one in **Models**, then select it in **Project Editor** before rendering. For full setup details, see [Installation](INSTALLATION.md#first-launch-guided-setup) and [Troubleshooting](TROUBLESHOOTING.md).

## 2. Download or locate an image model

Image generation cannot start until Morphorum has a usable model.

### Easiest option: managed Z-Image-Turbo

1. Select **Models** in the navigation.
2. Find **Z-Image-Turbo** in the managed model download area.
3. Click **Download** and wait for the progress indicator to complete. The package is approximately **33 GB**, so allow considerable time and space.
4. Click **Use Model** when the download has finished.

This official download supports **both text-to-image and image-to-image**. There is no need to find a separate img2img checkpoint.

### Already have SDXL or FLUX checkpoints?

Use **Settings** to choose the directories where Morphorum should scan for your supported models and LoRAs. Return to **Models** and refresh the model index. Morphorum can use compatible checkpoint files in other locations without copying them into the installation.

> [!NOTE]
> Not every checkpoint is interchangeable. SDXL, FLUX, and Z-Image have different controls, schedulers, and requirements. Select the appropriate model family and use its recommended settings. Morphorum does not support SD 1.x/2.x checkpoints as runtime models.

## 3. Generate a still image

1. Open **Image Generation**.
2. Select the model you downloaded or indexed.
3. Enter a prompt, for example: *An orange cat wearing a tiny black top hat, cinematic lighting, detailed fur*.
4. Choose a **resolution preset** supported by your selected model. For your first test, prefer a smaller preset if memory is limited.
5. Keep the other recommended settings at their defaults and start generation.
6. Watch progress and then view the image in **Results**.

After your first success, experiment with **seed behavior**, **batch count**, **steps**, **guidance**, and supported **LoRAs**. The available settings change with the model family.

### If generation is slow or runs out of memory

Lower resolution, batch size, or the number of competing GPU applications first. Very large images and some models need considerably more VRAM. See [Troubleshooting](TROUBLESHOOTING.md#out-of-memory-or-extremely-slow-generation).

## 4. Create your first animation with the wizard

The easiest way to start a new animation is **Motion Lab → New Project Wizard**, available in the desktop sidebar or Motion Lab workspace navigation.

The wizard has seven guided pages, with explanations and **?** hints beside individual settings:

1. **Welcome & Name:** name your new animation.
2. **Choose a Model:** select an installed SDXL, FLUX, or Z-Image checkpoint. The wizard chooses model-aware starting values for resolution, sampler, steps, and guidance.
3. **Animation Setup:** choose 2D/3D, frame count, FPS, and dimensions. The wizard displays approximate duration.
4. **Prompts & Keyframes:** write an opening prompt and, optionally, a second scene starting at a later frame.
5. **Camera Motion:** start with Still, Pan, Zoom, Orbit, or Spiral. Orbit/Spiral select 3D.
6. **Generation Settings:** review sampler, steps, guidance, img2img denoising strength, cadence, and seeds.
7. **Review & Save:** examine your choices, see guidance about optional advanced import workflows, then select **Save Project & Open Editor**.

Use **Back** and **Next** freely; the wizard preserves your choices and can restore a modified draft after a browser refresh in the same session. **Nothing is created until the final Save**. The server validates the schedules first and prevents replacing unsaved Editor edits without confirmation.

If no checkpoints are available, use the translucent **No generation models available** banner and its **Configure Models / Help** dialog to set your checkpoint/LoRA folders or download Z-Image-Turbo. A LoRA by itself is not a base generation model.

Read the [complete New Project Wizard guide](NEW_PROJECT_WIZARD.md) for field explanations, example presets, safe defaults, and troubleshooting.

### Alternative: Open the bundled Default example

A fresh installation with no existing projects also includes a **Default** animation:

- 120 frames at 24 FPS, approximately 5 seconds
- 1024 × 1024 resolution, 3D mode
- Two positive-prompt keyframes with cat/top-hat scenes
- No model selected until you choose one

Open **Motion Lab → Project Manager → Default → Open in Editor**, choose a compatible model, and review its settings. This is a *separate existing example*, not the unsaved wizard draft. The Project Editor explains why controls are locked until a project opens and provides shortcuts to Project Manager and the New Project Wizard. The browser remembers your last opened project when it is still available. Still-image model selection does not automatically select a model for an animation project. For an early GPU test, try fewer frames and a model-supported resolution.

## 5. Explore the Motion Lab workspaces

Motion Lab divides the animation workflow into separate pages so the editing tools have enough room:

| Workspace | When to use it |
| --- | --- |
| **Overview** | Choose what to do next. |
| **New Project Wizard** | Create a new project through seven explained setup and review steps. |
| **Project Manager** | Find, rename, inspect, or move projects to Trash. |
| **Project Editor** | Edit prompts, timing, resolution, schedules, and model. |
| **Camera Composer** | Build six-axis camera movement with presets and layers. |
| **Live Recording** | Record camera motion with keyboard/touch or a compatible gamepad. |
| **Motion Curves & Path** | Inspect or edit animation curves and the camera trajectory. |
| **Camera Preview** | Preview camera movement before spending time on AI rendering. |
| **Motion Studio** | Synchronize manual cues, beat markers, frequency bands, continuous camera movement and saved soundtrack audio. |
| **Import Motion Settings** | Inspect Deforum Motion Studio camera schedules, safely apply compatible six-axis curves, and optionally attach soundtrack audio. |
| **Render Monitor** | Follow the render and inspect progress. |
| **Outputs** | Review completed animations and available exports. |

**Typical workflow:** edit project → compose/record motion (or use **Motion Studio** for audio-linked cues) → review curves → preview camera path → **Apply** the motion → **Render Animation** → review **Outputs**.

For music-driven movements, use [Motion Studio](MOTION_STUDIO.md) to select a saved/uploaded soundtrack, tune beat cues or independent frequency channels, and stage continuous movement before applying the camera schedules.

The floating Motion Lab toolbar offers shortcuts to **Record**, **Stop**, **Curves**, **Preview**, **Apply**, and **Render Animation**. The buttons disable themselves during incompatible background actions.

The slim **Motion Lab next steps** guide shows your current workspace, active project, saved/unsaved Editor state and one or two useful destinations. For example, after Camera Composer it suggests Motion Curves and Camera Preview; after Render Monitor it suggests Outputs. Its buttons **only navigate**: they do not save a project, apply curves, switch the selected project or start a render. When no project is open it directs you to Project Manager or the New Project Wizard.

> [!TIP]
> Camera previews and AI renders are different operations. Previewing a camera path can help you catch mistakes before running a full diffusion render. A final animation may still look different after frame-by-frame generation.

## 6. Render and export a video

1. Confirm that your project has a model and valid settings.
2. Start with a short run. For example, try a few seconds rather than hundreds of frames.
3. Use **Render Animation** or the Editor's render action.
4. Follow the job under **Render Monitor**. Supported jobs can be cancelled or resumed as indicated by the interface.
5. Open **Outputs** after completion to preview the animation and export it as **MP4** or **WebM** where supported.

**FFmpeg is required** for video encoding. Open **Settings → Storage → FFmpeg Manager** to auto-detect it, set a custom executable path or test the currently selected binary and matching FFprobe. Save Settings to activate a tested choice. A fully managed one-click download is planned but not yet included. If export is unavailable, see [Troubleshooting](TROUBLESHOOTING.md#video-export-fails-or-ffmpeg-is-missing).

For **Deforum Motion Settings Import**, explicitly attach the selected soundtrack before starting a new render to include it in MP4/WebM exports at the original render FPS. Source paths from exported settings are only references; see the [complete import guide](DEFORUM_MOTION_SETTINGS_IMPORT.md).

## 7. Personalize and maintain Morphorum

Open **Settings** to select the UI theme, interface font, console font, and model directories. Under **Appearance → Contextual Help**, the **Show (?) help buttons** checkbox controls explanations beside common generation and camera settings. Hover, focus or tap a help button; press **Escape** or click elsewhere to dismiss it. Saving Settings remembers the choice without disabling warnings or errors.

The four themes are **Midnight Glass**, **Deep Ocean**, **Amethyst Night**, and **Slate Graphite**. Your choices are saved and reused when you reopen the app.

To update the installed source:

- Windows: run `.\update.bat` in the installation directory.
- Linux: run `./update.sh` in the installation directory.

**Keep your files safe:** the `projects/`, `outputs/`, and `data/` directories contain work and settings. Normal updates preserve them, but you should periodically copy the important ones to another drive. **Move to Trash** in Project Manager relocates project data into the application's project Trash area; it is not an automatic cloud backup or a permanent undo system.

## Want to use a separate desktop client?

The optional [backend-only mode](BACKEND_ONLY.md) lets a compatible native client connect to the same generation engine without the browser UI. This is an advanced workflow; it requires authentication and secure network configuration. The default browser mode is simpler for a first run.

## Need help?

- [Installation and maintenance](INSTALLATION.md)
- [Motion Studio guide](MOTION_STUDIO.md)
- [Troubleshooting](TROUBLESHOOTING.md)
- [Current features and limitations](CURRENT_STATUS.md)
- [Documentation index](README.md)

## Refreshing models while editing

Each animation project stores its own checkpoint selection independently of
the Image Generation model selector. After changing model directories or
installing a managed checkpoint, open **Models → Scan Models**. The animation
Project Editor and Deforum importer automatically refresh their checkpoint
lists without needing a browser reload. The current project's unsaved edits,
checkpoint choice and compatible sampler remain intact. If a previously used
model disappears from the index, it is shown as missing instead of silently
choosing another checkpoint; restore its directory and scan again, or
explicitly choose a replacement. An unsuccessful scan keeps the last known
checkpoint list until a later successful refresh.

## Animation checkpoint compatibility

In **Motion Lab → Project Editor**, the **Checkpoint compatibility** panel
shows the indexed model's family and variant, currently selected sampler and
render size. It compares the settings against the backend's published model
capabilities. SDXL images must be aligned to 8 pixels; Flux and Z-Image use
16-pixel alignment. Image sizes must be 64–4096 pixels on each side.

Warnings explain when a saved checkpoint is missing, the sampler is unsupported,
or dimensions are incompatible. **Open Model Manager** takes you to the existing
model inventory; **Choose a Sampler** and **Edit Resolution** focus the relevant
control. A high-resolution VRAM notice is advisory. None of these actions
automatically modifies the project, and an indexed model is not a guarantee
that its weights still exist or GPU memory is sufficient. Complete pre-render
validation is planned for a later milestone.

## Contextual generation help and units

Image Generation and Motion Lab offer small **(?)** help buttons alongside
common model, seed, sampler, resolution, cadence, generation and camera controls.
Hover, focus or tap to show explanations. **Settings → Appearance → Contextual
Help** can hide these tips without hiding errors or warnings.

Image dimensions and 2D pan use pixels (px); 2D/3D rotations use degrees per
frame; 3D translation uses estimated scene units per frame. These are repeated
per-frame motions, not final camera positions. Camera Composer fade and cycle
are seconds. Duration equals total frames divided by FPS.

Schedules accept frame-indexed values such as `0:(0.65), 48:(0.5)`; the
timeline's interpolation controls how values change between keyframes.
Help messages never mutate a saved project or trigger generation.

## Check Render before generation (P2.5)

In **Motion Lab → Render Monitor**, choose **Check Render** to inspect your
current browser project settings without starting a job or saving changes.
The report identifies blocking errors and non-blocking warnings, including
missing model weights, incompatible sampler and dimensions, invalid schedules,
required starting image, and unsupported step/guidance ranges. **Fix in
Editor** opens the relevant setting; missing checkpoints can be repaired
through Models. The check also runs automatically when you click **Render
Animation**. Errors prevent submission; warnings require explicit approval.

For very long projects, generation step/guidance ranges are checked at up to
500 evenly distributed frames, and the report discloses the sampling.
The renderer still validates the actual frames during generation. Preflight
does not guarantee that a GPU has enough free VRAM or that a complex 3D
camera projection will remain visible for every frame. No project data is
changed or saved by the check.

## 3D Camera Safety (P2.6)

Camera translation and rotation are per-frame changes, not absolute end
positions. A constant 3D Z move or Y rotation accumulates across dozens of
frames, and a 3D projection may eventually contain **no visible pixels**.

In Project Editor under **3D Camera Schedules**, choose **Review 3D Render
Safety**. Morphorum opens Render Monitor and runs the normal read-only
preflight check, which gives warnings about unusually strong movement,
cumulative camera travel, and narrow fields of view. These estimates use
sampled schedules. They do not run the depth model or predict pixel coverage.
A real **Camera Preview** helps evaluate projected coverage before a render.

If a live render's depth/camera warp fails, its error now reports the failed
frame, resolved camera-axis values, the count of source samples remaining
inside the view, and last successfully measured coverage when available.
The guidance explains which settings to soften. No camera values are
automatically modified, and no synthetic replacement frames are inserted.

Physical Windows/Android acceptance for P2.5 and P2.6 is bundled for the
next available test session. Do not merge these development changes to
main before that acceptance.

## Responsive Render Monitor controls (P3.1)

The **Check Render**, **Resume**, **Cancel** and **Render Animation**
controls wrap on desktop; at phone widths they reorganize into a grid, with
**Check Render** and **Render Animation** in full-width rows. On particularly
narrow screens each control receives its own row. The preflight issue list,
**Fix in Editor** button and 3D motion-safety guidance also wrap rather than
requiring a horizontal page scroll. Actual device and browser-zoom acceptance
is postponed to the combined physical test pass.

## Responsive Models, Settings, LoRAs and Image Results (P3.2)

Morphorum arranges Model Manager filters in one column on very narrow
screens, keeps model paths keyboard-expandable and selectable, and wraps
managed download metadata. Settings groups wrap into a two-column phone
layout; directory inputs and Check/Remove buttons stack at the smallest
widths. LoRA Manager details and Image Generation's result actions also
wrap rather than forcing a page-wide horizontal scrollbar. This is a
layout-only update; scans, model downloads, generation and saved settings
behave as before. Physical browser/zoom verification is deferred to the
combined acceptance test.

## Motion Lab timeline and controls at narrow widths (P3.3)

The Visual Timeline uses a keyboard-focusable scroll region on desktop,
with independent horizontal scrolling for many frames. At phone widths the
focused single-track display fits the real available card width, including
when the browser is zoomed in. Use the phone track picker, keyframe list and
frame scrubber for precise edits. Motion Curves, 3D Camera and Inspector
inputs, charts, dialogs and action buttons wrap to the available space.
Deforum Import keeps long mapping values inside its vertically scrollable
dialog. None of these responsive changes modifies project settings.
Physical Windows/Android acceptance through P3.3 is included in the
combined test plan and still pending.

## Operation feedback (P4.1)

A persistent operation notice at the top of the WebUI shows what the host
is doing while you save/reload Settings, scan model directories, or install
a managed checkpoint. It provides running progress (including live download
bytes and percentage where available), completion, path warnings and
actionable error details. **Open Models** or **Open Settings** returns to
the relevant page. Dismissing the notice never cancels ongoing work; model
downloads continue in the backend. The existing image and animation render
progress panels remain authoritative for GPU work. Progress for an
indeterminate task does not imply a percentage or ETA.

## Image and Motion Lab operation feedback (P4.2)

Image Generation now reports **Submitting** and **Queued** as separate
operations. The existing job-progress panel remains the place to monitor
the denoiser, inspect images, or cancel a running job. Refreshing recent
image jobs and unloading a model show a busy state, completion, or
actionable errors. Image generation submissions cannot be repeated while
the first request is still in flight.

In Motion Lab, **Preview Camera Motion** displays a status and CPU-preview
progress, including failure information, without loading the diffusion
model. **Preview Draft** compiles motion without saving; **Apply to Animation**
continues to require existing Save/Rebase confirmations and reports when
the user cancels. **Render Animation** describes preflight checks,
warnings, blocking errors and queue submission without inventing a GPU
ETA. Detailed diffusion/frame metrics remain in **Render Monitor**.
A queued render remains queued even if refreshing its history fails.
The operation notice is dismissible and does not cancel background work.
