# Features and current limitations

Morphorum **0.1.0a1** is an early-alpha application for running local AI image and animation workflows. Its standard interface runs in your browser; an optional API-only mode lets separate desktop clients connect.

## Supported today

| Area | Availability |
| --- | --- |
| Platforms | Windows 10/11, 64-bit Linux installers and browser UI |
| Models | SDXL, FLUX and Z-Image, including managed Z-Image-Turbo; external checkpoint folders |
| Image generation | Text-to-image, supported image-to-image, seed/batch controls and LoRAs; SDXL-specific sampler/schedule selection, chunked CLIP prompt conditioning and adapter integrity reporting |
| Animations | Saved projects, prompts/keyframes, 2D and depth-aware 3D motion, camera presets, curve editing, preview |
| Motion Lab | Six-axis composer, keyboard/touch motion recording, supported gamepad controls; curve preview, ranged recording/refinement and saved-motion comparison |
| Onboarding | Seven-step First-Run Setup Wizard with diagnostics, model/LoRA folders, optional Z-Image and 512 × 512 sample projects; separate seven-step New Project Wizard |
| Audio / video | Motion Studio manual beat cues, soundtrack reuse, independent frequency channels, spectrum selection and continuous camera presets; optional audio attachment, FFmpeg MP4/WebM exports |
| FFmpeg Manager | System detection or custom FFmpeg/FFprobe paths; optional SHA-256-verified managed FFmpeg install/update/remove on supported Windows/Linux hosts; host-side encoder checks |
| Import | Compatible Deforum Motion Studio camera schedules into existing 3D projects |
| Remote operation | Authenticated API-only server, versioned client capabilities, project assets, telemetry, previews and job recovery |

## Current workflow and tested milestone

The main menu includes Project Manager, New Project Wizard, and Project Editor directly. Project Editor groups its controls into five sections. Motion Lab Overview displays a read-only project/motion summary and workflow navigation for Preview, Apply, Save, Render, and Export. Motion Studio offers guided WAV analysis, beat detection, assignment, continuous/channel motion, and preview/apply stages. The project manager can move selected projects to Trash with confirmation; this is not permanent deletion.

Owner Windows testing reported a successful 237-frame, 24 FPS animation with H.264 video and AAC audio export. On 2026-10-17, the owner also reported **G5.5 SDXL acceptance passed** and explicitly approved promotion of the G1–G5 SDXL improvements to `main`. The candidate's automated Backend, Syntax, and Windows/Linux Installer checks passed. The changes include expanded SDXL sampler/schedule selection, dual-CLIP long-prompt and negative-prompt handling, LoRA validation, animation cache/performance telemetry, and clearer render diagnostics. Individual G5 acceptance-matrix results were not provided separately; treat this as owner acceptance rather than independent verification of every scenario. Physical mobile testing is deferred, and the remaining P5.3 soundtrack provenance, P5.4 consistency, and P5.5 closeout are not complete.

## Important limits

- **FFmpeg and FFprobe are separately installed tools.** Use an existing pair or explicitly download Morphorum-managed FFmpeg in Settings. The optional BtbN static GPL package is third-party software with its own license. Windows managed install and media checks received owner acceptance; Linux-managed installation and selected resilience cases require further testing. See [FFmpeg Manager](FFMPEG_MANAGER.md).
- **No model weights are included.** AI checkpoints are large; managed Z-Image-Turbo is approximately 33 GB.
- **CUDA is recommended.** CPU use, where possible, can be extremely slow. Performance, memory use, and high-resolution animation stability depend on the model and graphics card.
- **Not every Deforum setting is supported.** Imported camera motion is converted, not guaranteed to reproduce Deforum rendering pixel-for-pixel.
- **Some workflows remain experimental.** Complex hybrid video and depth workflows can require extra testing. An arbitrary plugin SDK and all-purpose model compatibility are not provided.
- **Backend-only is single-host.** An actual server restart interrupts active GPU work; completed project and media state can remain recoverable. Event streams do not store an unlimited history.
- **LAN security differs by mode.** The ordinary browser server has no built-in login. Backend-only requires authentication, but unencrypted HTTP still needs a trusted LAN or secure tunnel. Do not expose either port directly to the public internet.
- **Native Studio is separate.** [Morphorum-Studio](https://github.com/merberg-ai/Morphorum-Studio) has its own release and feature status. A compatible API does not guarantee every client feature is complete.

## Next steps

Read [Getting started](GETTING_STARTED.md) for a small first render, [Motion Studio](MOTION_STUDIO.md) for synchronized audio motion, [Installation](INSTALLATION.md) for setup requirements, and [Troubleshooting](TROUBLESHOOTING.md) if anything fails.

Report reproducible issues at [GitHub Issues](https://github.com/merberg-ai/Morphorum/issues). Please share your OS, GPU, Morphorum version, and error message, **never authentication tokens or private files**.

## Standalone Z-Image research boundary

An isolated experimental single-file Z-Image path was owner-tested through milestone **Z2.20c3c4** on Windows: converted external BF16 encoder/transformer weights, native prompt processing, two guarded CUDA denoising steps and a finite 32×32 RGB tensor decoded with the existing managed VAE. **No image file was generated or saved.** These scratch checkpoints are deliberately `loadable=false` and `runtime_verified=false`, and are **not supported by the normal Z-Image image-generation UI**. The managed Z-Image-Turbo package remains the supported path. See [milestone history](ZIMAGE_SINGLE_FILE_ROADMAP.md) and the [planned c3c5 PNG test](ZIMAGE_C3C5_IMPLEMENTATION_PLAN.md).

## Current WebUI and Project Editor controls

- **Image:** Generation progress is above the preview in Results; the empty-preview shortcut buttons were removed. The optional SDXL LoRA verification report expands/collapses, defaults closed on first use, and persists locally in the browser.
- **Image → open animation project:** Apply Image Settings to Project copies model, resolution, step count, sampler, scheduler/schedule type, and seed mode/seed values to the active **unsaved** Project Editor draft. It preserves positive and negative prompts and CFG. Explicit **Save Project** is required.
- **Prompt Keyframes:** **+ Keyframe** adds a prompt and automatically evens frame assignments; **Evenly Space** evens existing prompt rows. Prompt text/order is retained, frame numbers can still be edited manually, and duplicate/out-of-range automatic assignments are refused.
- **Responsive navigation and Help:** Expanded phone navigation is bounded. Desktop Help or phone More → Help reads bundled Markdown documentation inside the application.

Developer note: deferred SDXL LoRA console/alpha-pattern follow-up is tracked in [TODO.MD](../TODO.MD). Standalone Z-Image scratch inference milestones remain *research-only*, not product model compatibility.
