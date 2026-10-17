# Features and current limitations

Morphorum **0.1.0a1** is an early-alpha application for running local AI image and animation workflows. Its standard interface runs in your browser; an optional API-only mode lets separate desktop clients connect.

## Supported today

| Area | Availability |
| --- | --- |
| Platforms | Windows 10/11, 64-bit Linux installers and browser UI |
| Models | SDXL, FLUX and Z-Image, including managed Z-Image-Turbo; external checkpoint folders |
| Image generation | Text-to-image, supported image-to-image, seed/batch controls and LoRAs |
| Animations | Saved projects, prompts/keyframes, 2D and depth-aware 3D motion, camera presets, curve editing, preview |
| Motion Lab | Six-axis composer, keyboard/touch motion recording, supported gamepad controls; curve preview, ranged recording/refinement and saved-motion comparison |
| Onboarding | Seven-step First-Run Setup Wizard with diagnostics, model/LoRA folders, optional Z-Image and 512 × 512 sample projects; separate seven-step New Project Wizard |
| Audio / video | Motion Studio manual beat cues, soundtrack reuse, independent frequency channels, spectrum selection and continuous camera presets; optional audio attachment, FFmpeg MP4/WebM exports |
| FFmpeg Manager | System detection or custom FFmpeg/FFprobe paths; optional SHA-256-verified managed FFmpeg install/update/remove on supported Windows/Linux hosts; host-side encoder checks |
| Import | Compatible Deforum Motion Studio camera schedules into existing 3D projects |
| Remote operation | Authenticated API-only server, versioned client capabilities, project assets, telemetry, previews and job recovery |

## Current workflow and tested milestone

The main menu includes Project Manager, New Project Wizard, and Project Editor directly. Project Editor groups its controls into five sections. Motion Lab Overview displays a read-only project/motion summary and workflow navigation for Preview, Apply, Save, Render, and Export. Motion Studio offers guided WAV analysis, beat detection, assignment, continuous/channel motion, and preview/apply stages. The project manager can move selected projects to Trash with confirmation; this is not permanent deletion.

Owner Windows testing reported a successful 237-frame, 24 FPS animation with H.264 video and AAC audio export. Automated Syntax, Backend, and Installer checks passed at the pre-release development checkpoint. Physical mobile testing is deferred, and P5.3 soundtrack provenance, P5.4 consistency, and P5.5 closeout are not complete.

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
