# Morphorum documentation

Welcome to the Morphorum documentation. Pick the guide that matches what you want to do. **New users do not need to read the technical design documents** to install or run Morphorum.

## For users

| Guide | Purpose |
| --- | --- |
| **[Main README](../README.md)** | What Morphorum does, the shortest install instructions, and the main links |
| **[Getting started](GETTING_STARTED.md)** | Open the app, select a model, generate an image, try Motion Lab, export a video |
| **[New Project Wizard](NEW_PROJECT_WIZARD.md)** | All seven guided setup steps, model choices, motion presets, help hints, validation and safe saving |
| **[Deforum Motion Settings Import](DEFORUM_MOTION_SETTINGS_IMPORT.md)** | Import Deforum six-axis camera curves into an existing 3D project, calibrate strength, attach a soundtrack and export |
| **[Installation and maintenance](INSTALLATION.md)** | Detailed setup on Windows/Linux, port settings, LAN access, updates, repair and file locations |
| **[Troubleshooting](TROUBLESHOOTING.md)** | Startup, model downloads, CUDA, RAM/VRAM, video encoding, and update errors |
| **[Current features and status](CURRENT_STATUS.md)** | Implemented capabilities, known limitations and branch/checkpoint policy |

## For developers and advanced users

| Area | Documents |
| --- | --- |
| Architecture | [Architecture](ARCHITECTURE.md), [Contributing](../CONTRIBUTING.md), [Testing](TESTING.md) |
| Models and LoRAs | [LoRA behavior](LORAS.md), [Performance and cadence](PERFORMANCE_CADENCE.md), [SDXL memory investigation](SDXL_ANIMATION_MEMORY_INVESTIGATION.md), [SDXL LoRA text encoder investigation](SDXL_LORA_TEXT_ENCODER_INVESTIGATION.md) |
| Animation projects and engine | [Project format](ANIMATION_PROJECTS.md), [Schedule engine](SCHEDULES.md), [Timeline schema](TIMELINE_SCHEMA.md), [Timeline API](TIMELINE_API.md), [Timeline UI](TIMELINE_UI.md) |
| Renders and preview | [Render pipeline](ANIMATION_RENDERING.md), [Camera preview](MOTION_PREVIEW.md), [2D hardening](2D_HARDENING.md), [3D camera MVP](3D_CAMERA_MVP.md) |
| Motion Lab | [Implementation roadmap and phase notes](MOTION_LAB_ROADMAP.md) |
| Deforum/hybrid video development | [Hybrid plan](B6_DEFORUM_HYBRID_PLAN.md), [Hybrid source](B6_2_IMPLEMENTATION.md), [Hybrid input](B6_3_1_HYBRID_RENDER_INPUT.md), [Hybrid compositing](B6_3_2_HYBRID_COMPOSITING.md), [Physical acceptance](B6_PHYSICAL_ACCEPTANCE.md) |
| Planning and UX acceptance | [Roadmap](ROADMAP.md), [UI backlog](DEV_UI_BACKLOG.md), [UI acceptance](DEV_UI_PHYSICAL_ACCEPTANCE.md), [Copy cleanup](DEV_UI_COPY_CLEANUP.md) |

> [!IMPORTANT]
> Many engineering documents are **historical design notes**, written while a milestone was under development. They intentionally preserve experiments, branches, open issues, and acceptance checkpoints as they were **at the time**. A phrase such as "coming next" in an old file does not necessarily describe the latest build. For current user-visible capabilities, consult [Current status](CURRENT_STATUS.md), current code, and tests.

## Branches and release workflow

- **`main`**: published baseline and source for the beginner install URLs.
- **`dev-ui`**: integration and testing branch.
- **`feature/*`**: short-lived feature development.
- **`checkpoint/*`**: preserved, known recovery refs. Do not delete as part of normal cleanup.

The repository's automated checks include frontend syntax/regressions, Python/backend tests, and Windows/Linux installer checks. Green tests do **not** replace actual model/GPU and browser testing.

See [Contributing](../CONTRIBUTING.md) for the independent implementation and licensing requirements.
