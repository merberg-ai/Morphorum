# dev-ui: Morphorum UI and usability backlog

This is a planning backlog only. Do not implement entries until the list has been collected and the user requests the implementation pass.

Base branch: `dev-ui`, originally branched from B6.2 validated checkpoint `5826d2d96eedbc6fcaa0243dc6dab6eaeb8366a0`.
Keep `feature/deforum-compatibility-hybrid-b6` and `checkpoint/b6-2-hybrid-source-lab-validated-20261008` unchanged. B6 resumes at B6.3 Hybrid Animation Integration after this UI pass.

## 1. Persist Image Generation form fields in browser local storage

**Status:** Planned, not yet implemented.

**Requested:** Preserve the prompt and other Image Generation tab inputs so they survive browser refresh, tab navigation, and reopening Morphorum.

**Current finding:** `frontend/dist/assets/image.js` has no localStorage persistence for the Image Generation form. `frontend/dist/index.html` contains the following form state:

- Positive prompt (`image-prompt`), negative prompt (`image-negative-prompt`).
- Selected model (`image-model-select`), resolution preset (`image-resolution-preset`), width (`image-width`), height (`image-height`).
- Steps (`image-steps`), sampler (`image-sampler`), guidance/CFG (`image-guidance`).
- Seed (`image-seed`), seed mode (`image-seed-mode`), seed increment (`image-seed-increment`), number of images (`image-count`).
- LoRA picker selection (`image-lora-select`) and weight (`image-lora-weight`) where available. Embedded LoRA directives inside the positive prompt naturally persist with it.

**Implementation requirements for later:**

1. Save only allowlisted form values to versioned `localStorage` key, e.g. `morphorum.image.form.v1`. Debounce text input writes; save selects/numeric changes on change, including programmatic UI actions (seed reuse, randomize, swap resolution, preset changes, LoRA insertion).
2. Restore asynchronously and in correct order: load models, select a model if still available, rebuild model-family capabilities/samplers/presets/LoRA list, and only then reapply valid persisted field values. Avoid overwriting restored values with hard-coded defaults during startup.
3. For missing models, unsupported samplers, removed LoRAs, or out-of-range numbers, safely use current valid defaults instead of preventing rendering. Preserve prompt text even if no model is available.
4. Keep form draft entirely in the current browser; no backend project writes or automatic cloud/network sync. Browser storage is per origin, so `localhost:7865` and `192.168.x.x:7865` are separate drafts, as are phone and PC.
5. Provide a deliberate **Reset Image Form** / **Clear Saved Draft** action with confirmation, without clearing unrelated site settings or generated images.
6. Add browser regression tests for restore order, changes, missing/stale models, and browser storage unavailability.

**Acceptance:** Enter prompts and generation settings, refresh browser, switch tabs and return, close/reopen browser, and verify values persist on the same browser origin; verify stale model gracefully falls back. Nothing persists as server-side project settings.

## Next entries

Append items #2, #3, etc. as supplied by the user. Collect the list before changing Image Generation behavior.
