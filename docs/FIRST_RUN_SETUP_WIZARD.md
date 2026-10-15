# MS6 first-run setup wizard: implementation specification

**Status:** Planned for MS6, **not yet implemented**. Prepared on `dev-webui` after the owner requested an installation-wide guided first run. This specification is the contract for development and physical acceptance. It does not claim that `--setup-wizard` or the UI exists yet.

## Purpose and boundaries

A new user should be able to install Morphorum, visit its default local WebUI, understand how it runs, configure or download a compatible image model, and open a usable 512 × 512 sample animation in the **existing Project Editor** without already knowing where every setting lives.

This is a **first-run installation wizard**, separate from the already implemented **New Project Wizard** (`frontend/dist/assets/project-wizard.js` and `docs/NEW_PROJECT_WIZARD.md`). Do not replace that project wizard. Use existing settings, model-index, managed-download, and animation-project endpoints wherever possible.

The **WebUI is Morphorum's default mode**. The local Python backend performs all rendering; the browser is its control interface. **Backend-only** starts an authenticated API service for external clients without the WebUI, usually on a different port. Neither the wizard nor the browser can magically switch the running server between modes. Explain the command-line choice and require an explicit restart to change modes. A normal installation must not be auto-converted to backend-only.

This feature is **optional for existing installations**, should be restart-safe on fresh installations, and must not modify existing user projects, models, download directories, or settings without explicit confirmation.

## Triggering and ownership

- On **first WebUI load after a fresh installation**, present the full-screen, theme-aware setup wizard automatically. Detect this on the **server**, not from a browser's local storage or from the mere absence of indexed models.
- Distinguish shipped default settings from **persisted user setup**. For an upgraded installation with an existing `data/config.yaml`, existing projects, or existing model-folder configuration, do **not** assume a fresh install or forcibly enter the wizard. A prior user's **zero models indexed** is not proof that they need onboarding.
- Persist `not_started | in_progress | completed | skipped` and safe step/progress metadata in an installation-owned, atomically written state file under `data/` (e.g. `data/setup-state.json`). Keep only nonsecret setup choices; do not put credentials or complete filesystem inventories in browser storage. Make the server state authoritative across browser changes and reloads.
- Add a **future** CLI option `morphorum serve --setup-wizard` for an explicit **one-launch** wizard override. Provide forwarders for Linux `./run.sh --setup-wizard`, Windows `run.bat --setup-wizard`, and Windows PowerShell `scripts/run_windows.ps1 -SetupWizard`. These are *proposed commands*, **not valid in the current implementation**. Keep the existing `--backend-only`/`-BackendOnly` options unchanged and reject or clearly explain an incompatible forced WebUI wizard in backend-only mode.
- Make **Reopen Setup Wizard** available from WebUI Settings/Help for ordinary local users. Reopening may populate existing values but must **not wipe** or overwrite them. The CLI override can reopen a completed wizard without clearing its completion state. A new browser, device, or cleared browser cache must not reset a completed installation.
- If there are no models and onboarding was previously skipped/completed, retain the existing **No generation models available** helpful banner; do not repeatedly force the wizard.
- No automatic model download, background GPU load, project creation, or animation generation simply from opening a page.

## Page-by-page experience

### Page 1: Welcome and installation check

- Explain what the local Morphorum service does and that AI weights are not included.
- Display installed version, platform, GPU/CUDA detection if available, free storage, and a concise diagnostics summary using `doctor_report` and existing capabilities as a foundation. Treat unavailable GPU as a **warning**, not a false claim that a GPU exists.
- Explain the expected disk space for a large managed model before offering it.
- Show a visible progress indicator, **Back**, **Next**, **Skip for now**, and safe **Resume** behavior. The full flow must work at phone widths and be keyboard accessible.

### Page 2: Running mode explained

- **WebUI (default/recommended):** User opens a browser at the running Morphorum server (normally port **7865**); generation runs on the host computer. Show local WebUI access and explain why closing a tab does not automatically stop a server-side render.
- **Backend-only (advanced):** No browser UI; authenticated API for Morphorum Studio and other clients (normally port **7866**). Explain token handling, local-only defaults and LAN security. Show the actual already-supported startup commands, not a clickable browser toggle. Explicitly say changing modes requires restarting the service.
- Do **not** ask the user to choose backend-only inside the wizard and accidentally shut off the WebUI required to complete setup. Acknowledge the information and continue with WebUI configuration.

### Page 3: Model folder discovery and verification

- Separate **SDXL checkpoint folders** and **FLUX checkpoint folders**, since these are externally indexed. Z-Image-Turbo itself is managed under the existing configured managed-model location.
- Let users enter **one or more paths** to folders on the **computer running Morphorum** (not folders on the browser client device). Offer a native/server filesystem chooser only if a secure, bounded host-side picker can be implemented; never assume a browser file picker can select arbitrary host directories, especially on LAN.
- Reuse `POST /api/settings/validate-path` as an initial check, then use the existing model-index scan and inspect indexed entries **per selected folder, family and kind**. An existing/readable folder by itself is **not** proof it contains a correct model.
- Label outcomes separately: **folder invalid/unreadable**, **valid but empty**, **files found but incompatible or wrong family**, **recognized model files**, **indexed and selectable model(s)**. File-extension detection is only an initial filter; do not misrepresent arbitrary `.safetensors` files as proven loadable. Check model family/variant and metadata where supported; give conservative warnings and offer a non-destructive re-scan.
- Never automatically create directories, move model files, recursively scan the user's entire drive, or copy large checkpoints. Do not save an invalid path as though it passed. Preserve existing paths unless the user explicitly removes one.
- Show that having at least one compatible **checkpoint** is required before generation. Warn if no usable checkpoint is selected but allow the user to continue to the managed-model download or defer generation.

### Page 4: LoRA folders and compatibility

- Offer family-specific LoRA directories for **SDXL**, **FLUX**, and **Z-Image**. LoRAs are *optional* and are not substitute base models.
- Verify server-side folder existence/access and actual detected LoRA candidates; display count and family. Distinguish an empty but readable folder from an incompatible file, and avoid presenting metadata/filename heuristics as guaranteed runtime compatibility.
- Allow the user to skip the entire LoRA page without a warning requiring action. Do not attempt to auto-load a LoRA into a sample project.
- Save model/LoRA directories through the existing settings validation and persistence pipeline, then run an explicit model scan. Preserve any already configured folder paths and present a confirmation before overwriting saved configuration.

### Page 5: Optional managed Z-Image-Turbo download

- Explain that **Z-Image-Turbo** is a supported, managed Diffusers model for text-to-image and image-to-image, not a separate LoRA or directory of SDXL checkpoints.
- Show the existing catalog's description/license, destination, advertised size (roughly **33 GB**), available storage and download/integrity status. The published figure is an estimate, not an exact file size.
- Present **Download Now** and **Not Now**. Calling `POST /api/managed-models/zimage-turbo/download` requires a **clear user action**. Reuse existing download progress/status reporting and make it robust to page reload and an interrupted or resumed download.
- Don't imply a pending download means the model is ready to generate; gate actual model selection on existing installed/verified state and refreshed index. Warn about insufficient space and network failures without blocking the entire wizard.
- If already installed, say so and offer **Use Existing Model** rather than downloading again.

### Page 6: Choose a tiny starter animation

Offer **exactly two** friendly, selectable cards with an intelligible description of the motion and the same simple subject/prompt:

| Example | Camera | Output |
| --- | --- | --- |
| **Gentle Dolly In** | Slow forward movement on the native 3D Z axis toward the subject | 512 × 512, 48 frames at 12 FPS (4 seconds) |
| **Gentle Dolly Out** | Same path and magnitude in reverse, moving slowly away | 512 × 512, 48 frames at 12 FPS (4 seconds) |

Implementation details:

- Package both templates as **versioned, reviewable data** in `config/examples/` (or a similarly stable bundle), and instantiate through existing `create_animation_project` / `normalize_animation_project` semantics with a **new unique project ID**, not by copying an existing project ID from the bundle.
- Both templates should be **3D** with one conservative `camera_3d.translation_z` dolly schedule and all other axes held at zero; use equal and opposite, verified signs so the preview visibly matches its card label. Derive schedules with the normal synchronized timeline/track converter, not manually authored contradictory `tracks` vs text schedules. The source prompt and generation settings should be simple, deterministic and small enough for a first attempt, with a fixed seed; use a model-family-appropriate sampler/steps/guidance after an actual model is chosen.
- Choose the small **512 × 512** size intentionally for onboarding; explain that bigger images, longer animations and full 3D refinement are available later.
- **Never auto-render** the sample. On creation, use the normal project save API and **open that exact project in the existing Animation Project Editor**. Explain where Preview Camera Motion, Generate/Render, Models and Motion Lab are located.
- If no model is installed or the managed download is still in progress, let the user **create/open the example as an editable, explicitly non-render-ready project**, with a visible "choose/download a model before rendering" warning. Do not fake a valid model ID or launch a generation that will fail. Optional **Configure model first** returns to the appropriate setup page.

### Page 7: Review and Finish

- Summarize configured checkpoint/LoRA folders and verification results, managed model download state, selected usable base model if any, chosen sample name, and any outstanding warnings.
- Require explicit **Create Example & Open Editor** confirmation to create the example. Do it at most once per successful submission (idempotent request/lock), and handle network failure without creating duplicates.
- Mark setup completed **only after** successfully opening the selected saved example, or after explicit **Finish Without Example** / **Skip Setup** choice. Distinguish skipped from completed for later Settings/Help re-entry.
- On future launches, open the normal WebUI without replaying onboarding.

## Technical implementation plan

1. **MS6.0: baseline and architecture.** Establish MS5.4 physical acceptance; confirm `main` untouched. Define a minimal setup-state schema, migration/new-install detection, CLI overrides and backend-only semantics. Avoid side effects from import/startup or bare `GET` requests.
2. **MS6.1: server-owned setup state and mode/CLI path.** Add persisted status/draft endpoints and launcher flag wiring for Windows/Linux; ensure server decides if the WebUI should show onboarding. Add explicit permission and concurrency checks; status reads never download files or create projects.
3. **MS6.2: welcome, model paths and LoRA validation.** Separate install wizard JS/CSS from `project-wizard.js` and apply the current glass theme/toasts/spinners. Reuse settings, path validation and model scan; add folder-scoped, type-aware validation where existing endpoints cannot establish correctness. Confirm writes.
4. **MS6.3: Z-Image managed download, progress and resume.** Reuse catalog and status endpoints; require a confirmation before a `~33 GB` download. Provide real installed/error/progress and continue-later.
5. **MS6.4: two verified starter project templates and editor handoff.** Package 512 × 512, 48-frame, 12-FPS 3D dolly-in/dolly-out templates. Verify compiled camera sign, no unrequested model loading or render, unique project IDs, no overwrite and exact opening of the created project.
6. **MS6.5: release regression, docs and acceptance.** Update README, INSTALLATION, GETTING_STARTED and first-run screenshots as appropriate. Run complete Python/Node/installer CI and physical Windows + Linux + mobile checks, then separately review any merge into `main`.

## Acceptance matrix

| Scenario | Required behavior |
| --- | --- |
| Clean Windows install, first WebUI load | Wizard launches once, no legacy folder assumption |
| Clean Linux install, first WebUI load | Same behavior and path separator handling |
| Existing install, models configured and/or projects present | **Do not** force onboarding or reset anything |
| CLI `--setup-wizard` / Windows PowerShell `-SetupWizard` | Force wizard for this WebUI launch; safely prepopulate existing settings |
| CLI backend-only mode | Authenticated API only; no WebUI wizard; report incompatible forcing clearly |
| Browser reload midway / same host from phone | Server-owned step can resume; does not create duplicate projects |
| Empty, wrong-family, unreadable, or LoRA-only folders | Correct warning; don't claim a usable checkpoint |
| Valid external checkpoints + optional LoRAs | Counts/models per folder/family, save, scan, re-open persistently |
| Z-Image not installed | Download only on explicit click; visible space/network status and progress |
| Download interrupted or already installed | Honest paused/error/already-installed behavior, no redundant download |
| Skip LoRAs / decline download | Still able to proceed to example project or finish |
| No usable model at example creation | Example editable in Project Editor, rendering visibly blocked until a model is selected |
| Dolly In versus Dolly Out | Opposite signed native Z motion, other axes stable, exactly 512 × 512, 48 frames, 12 FPS |
| Example creation repeated / network retry | At most one new project for the confirmed action, originals unchanged |
| Return visit or cleared browser cache | Setup does not auto-repeat after completed/skipped state |
| Mobile widths and keyboard-only navigation | Labels, progress, Back/Next, focus and errors usable without overflow |

## Security and preservation rules

- Existing projects/settings/models/LoRA files, seeds, render outputs and downloads **must remain intact** unless the user knowingly edits a setting or creates a new project.
- Keep filesystem path verification on the host; do not trust browser device-local directory paths or accept arbitrary uploaded directory trees. No model moves, deletes or secret exposures.
- Do not present backend-only mode as an unauthenticated LAN toggle. Default loopback binding and existing bearer-token requirements must remain.
- Reuse the current persistent server state and progress APIs. If a future worker/download fails, do not mark setup done or conceal errors.
- Avoid starting large downloads, loading models or generating any image/video by merely opening the wizard.
- `dev-webui` remains the development branch until release acceptance. `main` and draft PR #39 are not merged without separate owner approval.
