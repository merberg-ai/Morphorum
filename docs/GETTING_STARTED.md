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

Open **Motion Lab → Project Manager → Default → Open in Editor**, choose a compatible model, and review its settings. This is a *separate existing example*, not the unsaved wizard draft. For an early GPU test, try fewer frames and a model-supported resolution.

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

> [!TIP]
> Camera previews and AI renders are different operations. Previewing a camera path can help you catch mistakes before running a full diffusion render. A final animation may still look different after frame-by-frame generation.

## 6. Render and export a video

1. Confirm that your project has a model and valid settings.
2. Start with a short run. For example, try a few seconds rather than hundreds of frames.
3. Use **Render Animation** or the Editor's render action.
4. Follow the job under **Render Monitor**. Supported jobs can be cancelled or resumed as indicated by the interface.
5. Open **Outputs** after completion to preview the animation and export it as **MP4** or **WebM** where supported.

**FFmpeg is required** for video encoding. If video export is unavailable, run `ffmpeg -version` in a terminal and see [Troubleshooting](TROUBLESHOOTING.md#video-export-fails-or-ffmpeg-is-missing).

For **Deforum Motion Settings Import**, explicitly attach the selected soundtrack before starting a new render to include it in MP4/WebM exports at the original render FPS. Source paths from exported settings are only references; see the [complete import guide](DEFORUM_MOTION_SETTINGS_IMPORT.md).

## 7. Personalize and maintain Morphorum

Open **Settings** to select the UI theme, interface font, console font, and model directories.

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
