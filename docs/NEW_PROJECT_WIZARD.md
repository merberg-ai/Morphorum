# New Project Wizard

**Create your first animation without needing to understand every Motion Lab control.**

The **New Project Wizard** guides you through a seven-step setup using Morphorum's current built-in animation defaults. It lives under **Motion Lab → New Project Wizard** on the desktop sidebar and in the Motion Lab workspace navigation on smaller screens.

The wizard is ideal for a new animation. To work on an existing project, use **Motion Lab → Project Manager → Open in Editor** instead.

> [!IMPORTANT]
> The wizard does **not** render anything or create a project when you open it. Your answers stay in a temporary browser-session draft until you select **Save Project & Open Editor** on the last page. A model must be available and selected before you can complete the wizard.

## Before you start

1. Open Morphorum in your browser and keep the Morphorum server running.
2. Go to **Models** and confirm that a usable checkpoint appears. You can download **Z-Image-Turbo** through the managed catalog or configure existing **SDXL** or **FLUX** checkpoint directories in **Settings** and select **Scan Models**.
3. Open **Motion Lab → New Project Wizard**.

If there are no usable checkpoints, Morphorum displays a translucent **No generation models available** banner. Select **Configure Models / Help** for instructions on setting checkpoint and LoRA directories, downloading Z-Image-Turbo, scanning, and selecting a model.

**LoRAs are optional accessories for a matching base checkpoint.** Having LoRAs but no checkpoint does not satisfy the model requirement.

## Wizard walkthrough

### Step 1: Welcome & Name

Give your new animation a descriptive name, such as `Moonlit Forest` or `Haunted Computer Test`.

The name is shown in Project Manager. You can rename the project later.

- A nonempty name is required.
- The name can contain up to 120 characters.
- Naming a project does **not** create it yet.

### Step 2: Choose a Model

Choose one of the locally indexed image-generation **checkpoints**.

Morphorum supports the SDXL, FLUX, and Z-Image model families. When you select a model, the wizard fills in that model's recommended initial **sampler, steps, guidance, and resolution**. You can review or adjust them on later pages.

Use the buttons on this page if you need to:

- Open **Models / Download** to obtain managed Z-Image-Turbo.
- Open **Settings** to configure the directories on the computer **running Morphorum** that contain your SDXL, FLUX, or LoRA files.
- Select **Refresh Models** after scanning or downloading new checkpoints.

> [!NOTE]
> Z-Image-Turbo's official Diffusers package is shared between text-to-image and image-to-image workflows. A separate img2img download is unnecessary. A usable model must be selected to advance from this step.

### Step 3: Animation Setup

| Setting | What it does | Default from project template |
| --- | --- | --- |
| **Animation mode** | 2D moves a flat frame; 3D uses depth-aware camera movement | 2D |
| **Number of frames** | Total length measured in frames | 120 |
| **Frames per second (FPS)** | Playback speed | 24 |
| **Width / Height** | Frame dimensions; affects VRAM usage and speed | 1024 × 1024 |

**Duration = frames ÷ FPS.** For example, 120 frames at 24 FPS is approximately **5 seconds**.

Choose a resolution appropriate for your selected model and available GPU memory. The wizard checks that width and height are multiples of eight and between 64 and 8192 pixels, but passing this check **does not guarantee** a particular GPU can render that size.

For a first experiment, consider a short animation and a moderate, model-supported resolution.

### Step 4: Prompts & Keyframes

Enter the **opening positive prompt** at frame 0. A prompt explains what you want the AI to generate.

You can also configure:

- **Opening negative prompt:** optional, and only meaningful if your model supports negative prompts.
- **Prompt transition:** `Blend` for supported gradual transitions or `Hold` for changing prompts at specified keyframes.
- **Second prompt and frame number:** optional. Provide a second scene description and a frame after 0 but before the final frame to introduce a change during the animation.

For example, the frame 0 prompt could describe an empty haunted room, while a second prompt at frame 40 introduces a glowing computer.

The wizard supports an opening prompt and **one optional later prompt** to keep setup simple. Once saved, **Project Editor** supports more sophisticated keyframe editing.

### Step 5: Camera Motion

Choose a starting camera preset:

| Preset | Effect |
| --- | --- |
| **Still** | No initial camera motion |
| **Pan** | Move horizontally |
| **Zoom / Push** | Move toward the subject |
| **Orbit** | Gently rotate around the subject in 3D |
| **Spiral** | Push in while rotating in 3D |

Presets write to Morphorum's **native camera-motion schedules**, so they are a starting point for the existing motion engine, not an unrelated animation effect. Pan and Push use the appropriate 2D or 3D controls based on the selected mode. Orbit and Spiral automatically switch the project to 3D.

Depending on the active animation mode, the wizard also offers **border mode** (2D) or a scheduled **field of view** (3D).

After saving, you can create more elaborate movement in **Camera Composer**, **Motion Curves & Path**, or **Live Recording**.

### Step 6: Generation Settings

| Setting | Why it matters |
| --- | --- |
| **Sampler** | Method used to produce generated frames; options depend on the model |
| **Steps schedule** | Number of diffusion steps at each frame; more steps take more time |
| **Guidance schedule** | Prompt influence; recommended values vary by model |
| **Strength schedule** | How much the previous frame is changed during img2img. **Higher denoising strength generally allows more change; lower strength preserves more** |
| **Diffusion cadence** | How frequently diffusion is run; `0:(1)` means every frame |
| **Seed behavior / seed** | Repeat, increment, or randomize the starting seed; `-1` requests a random seed |

Values such as `0:(9)` are *Deforum-style frame schedules*: the value in parentheses begins at frame 0. The wizard starts these fields using the project default or the chosen model's recommended values.

Use the **?** hint beside a setting when its purpose is unclear. More extensive schedules and controls remain available in Project Editor.

### Step 7: Review & Save

Review the project name, selected model, 2D/3D mode, dimensions, timing, prompt, camera preset, and generation values.

Select **Save Project & Open Editor** when the summary looks right.

On Save, Morphorum:

1. Confirms the required fields, dimensions, prompt, and selected model.
2. Checks animation schedules through the existing backend validator.
3. Warns if your currently open project has unsaved Editor edits or an incompatible active operation.
4. **Creates the new project only after validation succeeds**, using the normal animation-project API and synchronized native timeline tracks.
5. Loads the created project in **Project Editor**, where you can refine it, preview motion, or start rendering.

The final page introduces optional advanced work after the beginner wizard. **Motion Lab → Import Motion Settings** can load Deforum Motion Studio camera schedules into a matching saved 3D project and optionally attach an audio track; it is not part of the wizard. See [Import Deforum Motion Settings](DEFORUM_MOTION_SETTINGS_IMPORT.md).

## Navigation, draft recovery, and safety

- **Back** and **Next** let you move between pages while keeping your answers.
- Each field provides a small **? help hint**.
- **Start Over** asks for confirmation, then clears the unsaved wizard draft and loads fresh defaults.
- The wizard remembers an unfinished draft in your browser's **session storage**. Refreshing the same browser tab can restore it; this is **not** a saved project or cross-device backup.
- The wizard warns before closing/reloading a page with modified, unsaved answers.
- The final Save is blocked when a conflicting render, preview, or recording is active. If Project Editor has unsaved edits, you'll be asked whether to discard those changes before switching.
- Once a project is saved, it appears in **Project Manager**. You can reopen it even after the wizard's temporary draft has been cleared.

> [!TIP]
> If you have an existing animation you'd like to edit rather than creating another copy, start from **Project Manager** instead of the wizard. The wizard always creates a **new** project.

## After creating your project

Try this short route through Motion Lab:

1. **Project Editor:** inspect prompts, timing, and the model.
2. **Camera Composer** or **Motion Curves & Path:** tune the camera.
3. **Camera Preview:** check the motion before an expensive render.
4. **Render Monitor:** start and follow a short render.
5. **Outputs:** inspect finished frames and video exports.
6. **Import Motion Settings (optional):** after saving, import compatible Deforum camera motion and synchronize an attached soundtrack in a separate workspace.

## Need help?

- [Getting started](GETTING_STARTED.md)
- [Installation and maintenance](INSTALLATION.md)
- [Troubleshooting](TROUBLESHOOTING.md)
- [Current features and limitations](CURRENT_STATUS.md)
- [Return to the main README](../README.md)
