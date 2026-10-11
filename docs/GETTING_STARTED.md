# Getting started with Morphorum

This guide starts **after you have installed Morphorum**. For the installer itself, go to the [README](../README.md#get-started-in-three-steps). You don't need prior experience with Python, command lines, or AI animation to follow this walkthrough.

> [!TIP]
> Try one small image before a long animation. A single test image is the fastest way to confirm your model and GPU are working.

## 1. Open the application

Launch Morphorum from the folder where you installed it.

**Windows, default location** (PowerShell):

\`\`\`powershell
cd C:\Morphorum
.\run.bat
\`\`\`

**Linux, default location** (terminal):

\`\`\`bash
cd ~/Morphorum
./run.sh
\`\`\`

Keep that window running, and visit **http://127.0.0.1:7865** in your browser. If you chose another port during installation, use that number instead.

Morphorum runs on your own computer. The browser is only the interface: closing the browser tab does not necessarily stop a server-side job. To shut down Morphorum, press **Ctrl+C** in the terminal.

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

## 4. Open the starter animation

If this is a fresh installation with no pre-existing projects, Morphorum adds the **Default** animation:

- 120 frames at 24 FPS, about 5 seconds of animation
- 1024 × 1024 resolution, 3D animation mode
- Two positive-prompt keyframes with cat/top-hat scenes
- No model selected until you choose one

To open it:

1. Open **Motion Lab** in the main menu.
2. Select **Project Manager** from the Motion Lab sidebar or subsection navigation.
3. Select **Default**, then **Open in Editor**.
4. Pick a compatible image model. Review the frame count, FPS, resolution, prompts, and motion schedules.
5. **Save** your changes.

The example is a starting point, not an indication that your hardware can render every setting at full resolution. If you're new, start by reducing the frame count and using a model-recommended size.

## 5. Explore the Motion Lab workspaces

Motion Lab divides the animation workflow into separate pages so the editing tools have enough room:

| Workspace | When to use it |
| --- | --- |
| **Overview** | Choose what to do next. |
| **Project Manager** | Find, rename, inspect, or move projects to Trash. |
| **Project Editor** | Edit prompts, timing, resolution, schedules, and model. |
| **Camera Composer** | Build six-axis camera movement with presets and layers. |
| **Live Recording** | Record camera motion with keyboard/touch or a compatible gamepad. |
| **Motion Curves & Path** | Inspect or edit animation curves and the camera trajectory. |
| **Camera Preview** | Preview camera movement before spending time on AI rendering. |
| **Audio Motion** | Load audio, inspect frequency/rhythm responses, and map them to motion. |
| **Render Monitor** | Follow the render and inspect progress. |
| **Outputs** | Review completed animations and available exports. |

**Typical workflow:** edit project → compose/record motion → review curves → preview camera path → **Apply** the motion → **Render Animation** → review **Outputs**.

The floating Motion Lab toolbar offers shortcuts to **Record**, **Stop**, **Curves**, **Preview**, **Apply**, and **Render Animation**. The buttons disable themselves during incompatible background actions.

> [!TIP]
> Camera previews and AI renders are different operations. Previewing a camera path can help you catch mistakes before running a full diffusion render. A final animation may still look different after frame-by-frame generation.

## 6. Render and export a video

1. Confirm that your project has a model and valid settings.
2. Start with a short run. For example, try a few seconds rather than hundreds of frames.
3. Use **Render Animation** or the Editor's render action.
4. Follow the job under **Render Monitor**. Supported jobs can be cancelled or resumed as indicated by the interface.
5. Open **Outputs** after completion to preview the animation and export it as **MP4** or **WebM** where supported.

**FFmpeg is required** for video encoding. If video export is unavailable, run \`ffmpeg -version\` in a terminal and see [Troubleshooting](TROUBLESHOOTING.md#video-export-fails-or-ffmpeg-is-missing).

Audio Motion can incorporate a soundtrack with supported exports. Confirm the audio source and resulting export settings before assuming every output has sound.

## 7. Personalize and maintain Morphorum

Open **Settings** to select the UI theme, interface font, console font, and model directories.

The four themes are **Midnight Glass**, **Deep Ocean**, **Amethyst Night**, and **Slate Graphite**. Your choices are saved and reused when you reopen the app.

To update the installed source:

- Windows: run \`.\update.bat\` in the installation directory.
- Linux: run \`./update.sh\` in the installation directory.

**Keep your files safe:** the \`projects/\`, \`outputs/\`, and \`data/\` directories contain work and settings. Normal updates preserve them, but you should periodically copy the important ones to another drive. **Move to Trash** in Project Manager relocates project data into the application's project Trash area; it is not an automatic cloud backup or a permanent undo system.

## Need help?

- [Installation and maintenance](INSTALLATION.md)
- [Troubleshooting](TROUBLESHOOTING.md)
- [Current features and limitations](CURRENT_STATUS.md)
- [Documentation index](README.md)
