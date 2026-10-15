# MS6.0 Architecture Baseline and Safety Decisions

**Status:** MS6.0 architecture/baseline implemented on `dev-webui`; the first-run wizard, new setup endpoints and `--setup-wizard` CLI option are **not yet implemented**. MS5.4 automated checks passed, but its separate *physical Windows acceptance* has not been explicitly reported in this conversation; confirm before MS6.1. Work must remain on `dev-webui` and draft PR #39.

**Related contract:** [FIRST_RUN_SETUP_WIZARD.md](FIRST_RUN_SETUP_WIZARD.md). This decision record resolves discovered conflicts between idealized first-run detection and the real current installers.

## Audit results (current source, 2026-10-15)

| Area | Existing implementation | Implication for onboarding |
|---|---|---|
| Fresh Windows install | `scripts/install_windows.ps1` copies `config/default.yaml` to `data/config.yaml` and executes `python -m morphorum seed-example` on install mode | **Fresh has both config and project**. Neither presence proves prior use |
| Fresh Linux install | `scripts/install_linux.sh` does the same | Must implement identical provenance behavior on both platforms |
| Install manifest | `morphorum self-test` calls `write_install_manifest`, creating `data/install.json` | Manifest presence also cannot mean "wizard already shown" |
| Existing seed | `config/example-project.json` is a 1024×1024 120-frame `Default` project; `seed_example_animation_project()` creates only when the project library is empty | Preserve this legacy/default project. MS6.4 creates **additional selected** 512×512 examples; do not silently replace Default |
| Runtime paths | `backend/morphorum/paths.py` owns `ROOT`, `DATA_DIR`, `USER_CONFIG`, `PROJECTS_DIR` etc. | Use `data/setup-state.json` (not browser localStorage) for authoritative wizard lifecycle |
| WebUI startup | `morphorum serve` defaults to loopback port 7865; `frontend/dist/assets/app.js` boots on DOMContentLoaded | Add a **separate** wizard module and read-only server setup-status fetch after normal startup, not a second app server |
| API-only startup | `morphorum serve --backend-only` sets auth-required API mode (usually 7866) without browser assets | Forced UI wizard must be rejected in this mode; never weaken token checks or expose an unauthenticated setup surface |
| Windows launcher | `run.bat` forwards normal args to `scripts/run_windows.ps1`, which forwards to CLI. Backend-only has a special compatibility path | New `--setup-wizard` must explicitly map to `-SetupWizard`; don't change port/LAN/back-end flags |
| Linux launcher | `run.sh` delegates to `scripts/run_linux.sh`, which forwards shell arguments | New CLI flag can pass through; add mode validation |
| Config settings | `load_settings` reads shipped defaults merged with user YAML; `save_settings` atomically writes `data/config.yaml`; `validate_path` checks only directory accessibility | Directory existence does **not** prove model files are compatible |
| Model scanner | `scan_models` walks user-chosen external checkpoint/LoRA roots, indexes candidate extensions and source/family; managed model entries are separate | A candidate file can be **fake or unloadable**. Only say "recognized candidate/indexed", never "runtime verified" until a real model load is demonstrated |
| Managed Z-Image | `managed_model_manager` exposes catalog, download and status; completed installation needs verified runtime layout and marker | Download must be opt-in and state must be rechecked; no auto-download from GET or wizard mount |
| Animation creation | `create_animation_project` gives new UUID-suffixed ID and normalizes `camera_3d` and synchronized tracks | Build two small templates in MS6.4 using canonical project creation and same scene, opposite signed Z movement; no auto GPU render |
| Existing project wizard | `frontend/dist/assets/project-wizard.js` already creates arbitrary animations | **Retain** it. Installation setup is a separate workflow ending by opening the chosen project in the existing editor |

## Decision 1: Explicit fresh-install provenance, never infer from empty models

The **installer must detect fresh versus existing before it copies the default YAML or creates the Default starter project**. Add setup provenance writing in **MS6.1**, not retroactively in MS6.0. Persist the decision in a dedicated, atomically written file (suggested `data/setup-state.json`). Use a transient early installer intent flag if needed to survive interrupted installer recovery, plus an explicit `ready` flag enabled only after a successful install.

A **legacy installation with no setup-state file is treated as existing** by default. This is the conservative migration policy: do not retroactively force a wizard on people upgrading Morphorum. Let these users open the wizard manually from Settings/Help, or force it with a new **one-launch** CLI override. A manual checkout that bypasses the installer should also avoid guessing based on missing files; use the same manual entry points.

Setup status is **per installed server**. It must not be reset by browser/localStorage deletion, mobile access, model index rescans, no-GPU hardware, project deletion, or frontend asset updates.

### First-run decision table

| Condition | Automatic wizard? | Explanation |
|---|---|---|
| Fresh Windows/Linux installer, provenance recorded and install ready | **Yes**, until completed/skipped | Even though `config.yaml` and `Default` exist |
| Fresh installer interrupted and not ready | **No** | Finish/repair installer before exposing onboarding; retain intent |
| Existing install, setup-state missing | **No** | Legacy-safe migration policy |
| Existing install, state completed/skipped | **No** | Browser/cache/device changes do not override |
| State in_progress and installed ready | **Resume** | Server-owned step, no duplicate side effects |
| No indexed checkpoints but completed/skipped setup | **No** | Existing model setup banner remains available |
| Reopen from Settings/Help | **Yes, explicit** | Prepopulate but never overwrite without confirmation |
| New `--setup-wizard` in default WebUI launch | **Yes for this launch** | Force display; **don't clear** completed/skipped state |
| New `--setup-wizard` and `--backend-only` together | **Reject with clear CLI error** | Backend-only does not serve the wizard |

## Decision 2: Minimal, versioned server-owned state

Proposed schema (MS6.1 implementation contract; **not yet a shipped file**):

```json
{
  "schema_version": 1,
  "provenance": "fresh_installer",
  "ready": true,
  "status": "not_started",
  "step": "welcome",
  "revision": 0,
  "example_request_id": null,
  "example_project_id": null
}
```

Allowed statuses: `not_started`, `in_progress`, `completed`, `skipped`. Step IDs are known symbolic IDs (welcome, modes, models, loras, zimage, examples, finish), not arbitrary URLs. `revision` increments on server-owned state changes so stale tabs cannot silently clobber each other. Keep timestamp metadata optional and UTC if added.

No passwords, API tokens, environment variables, filesystem dumps or unsaved raw model path strings in the state file. Validated **saved** paths already belong to `data/config.yaml`. UI can hold unsaved input in memory; a resumed wizard may ask to re-enter unsaved paths, while saved settings are automatically reloaded.

State file operations must be atomic (temp file + `os.replace`), validated by schema and bounded. A malformed file is **never silently overwritten**. Surface a recoverable warning and require an explicit repair/force entry. Updates, repairs and normal server startup never unconditionally rewrite the state file.

**Installation completion rule:** Marking `completed` happens only on explicit Finish Without Example or after a successful example create/open acknowledgement. Marking `skipped` is distinct. A wizard that is merely dismissed mid-step remains resumable.

## Decision 3: Route and concurrency boundaries

MS6.1 should introduce minimal dedicated setup routes rather than modifying existing render/model endpoints. Suggested API contract (names are proposals until implemented):

- `GET /api/setup/status`: **read-only** `{schema_version, eligible, show_wizard, forced_for_launch, status, step, revision, mode}`. No default project creation, model scan, download, or settings writes.
- `POST /api/setup/progress`: validate a fixed step/status action; refuse stale revision; never write settings/models/projects.
- `POST /api/setup/complete`: mark the safe explicitly confirmed terminal choice; project completion requires verifying a project created for the current idempotency request, not an arbitrary submitted ID.
- User-facing setup model directory actions should call the **existing** validated settings and model-index endpoints, with staged confirmation. New scoped inspection endpoints must avoid arbitrary host directory enumeration or leaking filenames through unauthenticated LAN access.

**Permission boundary:** WebUI may be bound to LAN; `/api/settings` already exposes host configuration. Wizard must not expand that threat surface via unrestricted filesystem browsers or privileged actions. Reuse current host API access policy and add explicit checks for any *new* privileged setup/host-path exploration endpoints; default localhost, and require trusted context before mutations over LAN. The browser must never silently alter server modes or issue a backend access token.

**No side effects on status or frontend load**. Do not call `POST /api/models/scan`, `POST /api/managed-models/zimage-turbo/download`, `POST /api/animation/projects`, or GPU generation from `GET` or page mount. User confirms those actions separately. No model/LoRA files are moved or deleted.

## Decision 4: Model validity and folder semantics

There are three separate checks:

1. **Host path accessible**: existing `validate_path` `exists && is_directory && readable`. This only confirms a directory.
2. **Indexed candidate(s)**: existing `scan_models` + `list_models(family,kind)` show checkpoint or LoRA entries for the selected roots. The scan accepts common extensions, so a `.safetensors` filename can appear even if its contents are incompatible. A LoRA folder never fulfills base-model prerequisite.
3. **Loadability**: actual runtime/model metadata compatibility (and optionally a trial load) can prove a usable model. Do not claim this from filename/extension alone. During onboarding, report **indexed candidate** and separate **not verified by loading** status when runtime loading is deferred.

Disallow unsupported SD1/2 as selectable base families. LoRA paths are family-specific and optional. Use paths on the **host running Morphorum** rather than expecting a browser file picker to see remote host drives. Never scan every disk.

## Decision 5: The two example projects are opt-in and idempotent

At MS6.4 implement two **new** starter templates (Gentle Dolly In / Gentle Dolly Out) with **512×512, 48 frames, 12 FPS**, `mode=3d`, a constant/simple scene prompt, fixed seed, other five camera axes stationary and equal/opposite conservative native Z. Verify *direction* in the native camera transformer, not just the plus/minus label.

Use `create_animation_project` to assign distinct unique project IDs and maintain canonical camera tracks. Leave existing `Default` template, its project ID and user projects untouched. No model weights are bundled, and a user lacking any usable checkpoint can open/edit the sample with render disabled/warned until a model is chosen. Never auto-render.

The final confirmation submits a bounded, unique idempotency key. On retries/network failure, resolve that key to the *same project*. Persist the mapping/reconciliation in backend setup state and/or canonical project metadata, so a crash between project creation and state update never creates two examples. Reject stale tabs and simultaneous clicks. The browser must load the returned project ID through the existing animation editor before acknowledging completion; a failed editor navigation leaves a resumable project, not silent completion.

## MS6.0 baseline tests and CI

Add a small Python regression suite exercising the unchanged existing behavior:

1. Both install scripts seed `Default` *and* materialize `data/config.yaml`; future detection may **not** rely on absence of either.
2. Default `serve` remains WebUI, `--backend-only` remains opt-in, without starting actual Uvicorn.
3. Existing model path validation distinguishes a readable folder from an indexed **checkpoint**; a LoRA-only folder must not qualify.
4. `save_settings` preserves user-supplied model paths and unknown settings and does not fabricate a checkpoint.
5. Creating a 512×512/48-frame sample draft using the existing canonical project API leaves an existing project byte-for-byte unchanged; a second request creates a **different** ID under current API. MS6.4 must add its own idempotent wrapper.

These tests establish guardrails, **not** claims that the setup wizard exists. Later MS6 phases add first-run state, CLI launcher, model-folder, download and UI tests to CI.

## MS6.0 exit criteria

- [x] Audit documented, including preseeded fresh-install conflict and legacy-safe migration.
- [x] Installation state, status semantics, API/CLI permissions, no-side-effects rule and idempotency contract decided.
- [x] Implementation phases and physical acceptance unchanged.
- [ ] Safety baseline tests committed and CI green.
- [ ] Owner physical MS5.4 acceptance explicitly confirmed before feature-bearing MS6.1.

**Main, current stable project data, and the draft PR merge state stay unchanged.**
