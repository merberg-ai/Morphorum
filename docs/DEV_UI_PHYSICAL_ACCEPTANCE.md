# dev-ui physical acceptance and B6 handoff

**Branch:** `dev-ui`

**Base checkpoint, keep untouched:** `checkpoint/b6-2-hybrid-source-lab-validated-20261008`, SHA `5826d2d96eedbc6fcaa0243dc6dab6eaeb8366a0`.

**B6 feature branch:** `feature/deforum-compatibility-hybrid-b6`, deliberately unchanged. After dev-ui validation, merge dev-ui into the active B6 branch and resume **B6.3 Hybrid Animation Integration**. Do not treat dev-ui as a new B6 feature milestone by itself.

## Installation for Windows physical acceptance

```powershell
cd D:\Morphorum-test
git fetch origin
git switch dev-ui
git pull --ff-only
.\update.bat
```

Restart Morphorum. On phone and laptop, **hard-refresh** (or close/reopen the page) to ensure the versioned frontend assets are refreshed. GitHub Actions static browser tests are not a substitute for actual Chromium layout tests or RTX 4080 SUPER renders.

## Test order, with specific observations

1. **Safety and shared dialogs (items 4, 10):** From Animation create a new project, leave name empty and test inline validation, Escape/cancel and valid Create. Modify project then switch project and cancel discard. Import a JSON-format Deforum `.txt` while edits are dirty and cancel the confirmation from inside importer. High-resolution render warning should use the dark Morphorum dialog and Cancel must not render. Console Clear Buffer must require a danger confirmation, while Clear View remains local.
2. **Image draft (item 1):** Choose a supported SDXL checkpoint; enter positive/negative prompts, LoRA tag, custom dimensions, steps, sampler, guidance, seed mode, count. Reload same browser origin and confirm values are restored. Switch model family and confirm invalid stale samplers aren't restored. Click Reset Image Form and cancel; then confirm, and verify generated files remain. Laptop `localhost`, LAN IP and Android origins have distinct browser-local drafts by design.
3. **Image results (item 8):** Generate >5 images (or adjust preview limit to 2), view thumbnail in full-size lightbox, close/download, and use the Recent Jobs selector. With a 10+ step image job in progress, refresh the browser. It should reattach to the still-running server job using `GET /api/generation/jobs` if the same backend process remains alive. Check Reuse Seed saves it to the draft.
4. **LoRA Quick Use (item 3):** Select indexed SDXL LoRA. Verify checkbox glyph is normal size on phone, the strength updates copied snippet, local recorded trigger words are included only when checked, Copy works on HTTP LAN or reports failure truthfully, and Add to Image Prompt matches copied text. Test an unavailable trigger metadata case and a different model family. Inspect expandable diagnostics and optional Civitai results.
5. **Models (item 6):** Search/filter, clear filters, expand very long file paths, select checkpoint for Image, collapse/expand managed download catalog. If a managed model is downloading, verify live progress and error/retry survive. No install/download needed for basic UI gate.
6. **Settings (item 7):** Visit Appearance, Generation, Model Paths and Storage internal tabs. Change a path, confirm Unsaved changes shows, cancel Reload, then Save and verify Saved badge. On phone validate a path explicitly using Check. Do not toggle VAE tiling mid-long render; opt-in takes effect after model unload/reload.
7. **Animation workspace (item 2):** Open an existing short 2D SDXL project. Switch Editor/Monitor/Media/Outputs repeatedly, verify current project persists, Deforum import and timeline work, and Media B6.2 extraction/preview still work. Start a 20–50 frame render. Confirm Monitor becomes active, latest frame is visible, overall frame progress and *effective* diffusion step bar update. Cadence-only frames must show no diffusion rather than stale percentages. Check Cancel and Resume where available; video export should work under Outputs. Monitor Diagnostics shows prompts/camera/VRAM as before.
8. **Header, mobile dock and mini-progress (item 5):** On Android at `http://192.168.1.24:7865`, portrait and landscape, check CPU/RAM/GPU/VRAM values don't clip, More opens Settings/Console, all controls fit above Chrome browser chrome, and keyboard focus on prompt hides dock instead of covering text. During Image and Animation jobs the header progress strip should display correct job and navigate to source tab. Check desktop layout remains unchanged.
9. **Console (item 9):** Test All, Errors, Warnings+, Source filters, text search, count, Jump to Latest, live SSE append and autoscroll manual disable. On mobile line text should wrap and remain readable. Copy View/Buffer should give real clipboard feedback.
10. **Regression (all):** Basic still image SDXL/Flux/Z-Image operations where models are present, Animation non-hybrid render, LoRA prompt insertion, B6.1 Deforum import, B6.2 video upload/extract/preview, no unintended changes to existing B5/B6 render semantics.

## Diagnostics to capture if anything fails

Open browser Developer Tools → Console and Network; attach the actual error message and a screenshot, plus Morphorum Console events for the matching action. Include **the exact browser URL/origin**, branch/commit shown in the header, model family, and whether the problem occurred after a hard refresh. For overlapping UI send a screenshot with viewport/orientation, zoom and Android browser chrome visible.

## Rollback

To restore the last physically validated hybrid-source UI, return to checkpoint branch:

```powershell
git fetch origin
git switch checkpoint/b6-2-hybrid-source-lab-validated-20261008
.\update.bat
```

Do **not** merge `dev-ui` into the B6 feature branch or move the B6 checkpoint until these UI changes pass physical acceptance. B6.3 remains the exact next feature phase.
