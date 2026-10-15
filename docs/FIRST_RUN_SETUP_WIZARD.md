# MS6 first-run setup wizard: implementation specification

**Status:** MS6.1 passed physical acceptance; **MS6.2 implemented on `dev-webui`, pending separate Windows physical acceptance**. Host folder and LoRA setup screens, family-aware read-only inspection and explicit save/scan are in place. **MS6.3–MS6.5 remain planned**. Z-Image downloading, starter animation creation and final completion are not wired yet. See [MS6_ARCHITECTURE_BASELINE.md](MS6_ARCHITECTURE_BASELINE.md) for the installer/migration rules.

## Purpose and boundaries

A new user should be able to install Morphorum, visit its default local WebUI, understand how it runs, configure or download a compatible image model, and open a usable 512 × 512 sample animation in the **existing Project Editor** without already knowing where every setting lives.

This is a **first-run installation wizard**, separate from the already implemented **New Project Wizard** (`frontend/dist/assets/project-wizard.js` and `docs/NEW_PROJECT_WIZARD.md`). Do not replace that project wizard. Use existing settings, model-index, managed-download, and animation-project endpoints wherever possible.

The **WebUI is Morphorum's default mode**. The local Python backend performs all rendering; the browser is its control interface. **Backend-only** starts an authenticated API service for external clients without the WebUI, usually on a different port. Neither the wizard nor the browser can magically switch the running server between modes. Explain the command-line choice and require an explicit restart to change modes. A normal installation must not be auto-converted to backend-only.

This feature is **optional for existing installations**, should be restart-safe on fresh installations, and must not modify existing user projects, models, download directories, or settings without explicit confirmation.

## Triggering and ownership

- On **first WebUI load after a fresh installation**, present the full-screen, theme-aware setup wizard automatically. Detect this on the **server**, not from a browser's local storage or from the mere absence of indexed models.
- **Use explicit fresh-installer provenance, not presence/absence of settings or projects.** Both current installers already copy `config/default.yaml` to `data/config.yaml` and seed a 120-frame `Default` project on a fresh install. Installation self-tests also write `data/install.json`. MS6.1 must inspect the installation *before* those actions and write an atomic server-owned marker. A legacy/upgraded installation with **no** setup marker is treated as existing and must **not** auto-launch onboarding. A prior user's **zero models indexed** is not proof that they need onboarding. See the decision table in [MS6_ARCHITECTURE_BASELINE.md](MS6_ARCHITECTURE_BASELINE.md).
- Persist `not_started | in_progress | completed | skipped`, **installer readiness/provenance**, schema version, revision and safe step metadata in an installation-owned, atomically written `data/setup-state.json`. Do not store credentials, raw unsaved folder inventories or tokens. Make the server state authoritative across browser changes and reloads; malformed state must be reported without silent overwrite.
- **MS6.1 implemented:** `morphorum serve --setup-wizard` forces the entry wizard for the current WebUI server process. Linux `./run.sh --setup-wizard`, Windows `run.bat --setup-wizard`, and Windows PowerShell `scripts/run_windows.ps1 -SetupWizard` forward the override. It does not reset persisted completion or replace saved config. `--setup-wizard` plus `--backend-only` is rejected with a clear startup error. Backend-only keeps the authenticated API with no WebUI wizard.
- **MS6.1 implemented:** **Setup Wizard** in WebUI Settings reopens Welcome/Mode screens on demand, without clearing model settings, projects, or installer state. The CLI override also reopens previously skipped/completed setup for that process. Saved step and optimistic revision enable resume and conflict warnings. A new browser, device, or cleared browser cache must not reset a completed/skipped installation.
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

## MS6.1 entry flow available now (2026-10-15)

- A **genuinely fresh** Windows/Linux install receives `data/setup-state.json` during provisioning **before** default user config and the bundled Default project are created. The marker is finalized only after successful installer checks. Existing installations and updates without a marker are treated as legacy and do not auto-open a wizard.
- The normal WebUI performs a read-only `GET /api/setup/status`. If installation provenance is fresh and setup is incomplete, the **Welcome** screen opens automatically. The first screen also reads host diagnostics (`GET /api/system`), while page 2 explains WebUI versus backend-only; MS6.2 implements model and optional LoRA folder screens.
- A user may **Skip for now** (persistently suppress future automatic startup) or **Close** (resume later at the server-saved step). Open Settings → **Setup Wizard** to return at any time.
- `POST /api/setup/progress` requires an explicit setup interaction header and same-origin browser context, validates known steps and a revision, and supports **advance** and **skip** only. Completion, Z-Image downloads, sample creation and rendering remain deliberately unwired.
- A corrupted setup state is preserved and reported without silently rewriting it. The backend-only browser shell is not exposed.

**MS6.1 physical acceptance:** test on clean Windows and Linux installs, a legacy/upgraded installation, Windows `run.bat --setup-wizard`, PowerShell `-SetupWizard`, Linux `./run.sh --setup-wizard`, server restart, browser reload, Skip and Settings reopen. Check existing config/projects/model weights remain unchanged and backend-only rejects the wizard. The substantive model/LoRA configuration begins in MS6.2; managed downloading and sample projects are for MS6.3–MS6.4.


## MS6.2 folder configuration and acceptance (2026-10-15)

- **Separate frontend controller:** `frontend/dist/assets/first-run-folders.js`, not the New Project Wizard or general Settings editor. The model page offers SDXL/FLUX checkpoint directories; the optional LoRA page offers SDXL/FLUX/Z-Image LoRA directories. Multiple paths are supported on the **Morphorum host**. Back/Next resumes through the MS6.1 server-owned step record; unsaved folder edits block **Next**.
- **Bounded read-only check:** `POST /api/setup/folders/check` requires the wizard header and same-origin browser context. It calls host path validation, limits traversal to 1,500 inspected entries, 128 directories and depth 6, reads no model tensor data, and reports `invalid`, `empty`, `incompatible`, `candidates`, `indexed` or `partial`. Header/filename family hints are **not proof of loadability**; `indexed` means the existing model index has entries under the chosen family/path, not that inference succeeded. The existing recursive scan preference is respected.
- **Explicit save + refresh:** `POST /api/setup/folders/save` validates every specified directory before writing, protects against stale expected folder lists and updates **only** the specified checkpoint or LoRA kind through the normal settings pipeline. Existing unrelated model families, user settings and projects stay unchanged. An explicit **Save Folders & Scan** click then calls the existing `POST /api/models/scan`; no scan, file changes, downloads or model loads occur from merely viewing the wizard.
- **No-model continuation:** An empty checkpoint folder, absent external models or skipped LoRAs do not prevent moving forward to the planned managed Z-Image step. The UI warns that render requires a usable base model. The Z-Image step is an honest placeholder until MS6.3, with Next disabled; setup cannot be spuriously marked complete in MS6.2.
- **Automated regressions:** `tests/test_ms62_setup_folders.py`, `tests/frontend_first_run_folders.test.cjs` and updated `tests/frontend_first_run_setup.test.cjs` cover family hints, read-only checks, save conflicts, validation, same-origin guard, explicit frontend writes and wizard progression.

**MS6.2 physical acceptance checklist:** On Windows, run the current `dev-webui`, open Settings → Setup Wizard or start with `run.bat --setup-wizard`. Advance to Model Folders. Add and check one valid SDXL checkpoint directory and one FLUX directory, including empty/wrong-family paths; inspect clear candidate vs indexed outcomes. Save & Scan and verify both folders persist in the normal Settings page after reload. On the optional LoRA page, add an SDXL LoRA directory, verify counts, save and re-open; also test leaving the page empty. Confirm that the original settings, selected model, projects and model files are unchanged except for explicit folder-path changes. Test Back/Next, narrow/phone width, stale-tab conflict and no-model continuation to the not-yet-enabled Z-Image page. Do **not** trigger any model download or rendering for this milestone.
