# Morphorum current status (2026-10-09)

> **Authoritative milestone snapshot.** Older `handoff.md`, `docs/ROADMAP.md`, and B6 planning passages record the state *when they were written*. Use this page and the actual source/tests when historical text disagrees.

## Branches and verified checkpoints

- `main`: promoted from the physically tested `dev-ui` baseline through [PR #14](https://github.com/merberg-ai/Morphorum/pull/14) on 2026-10-09; promotion merge `fc0ba653e7c265b1ea7b39c231ce2e1696f16ea9`.
- `dev-ui`: ongoing integration branch, source for new B6.3 work. PR #13, SDXL full LoRA text-encoder loading repair, merged to `dev-ui` as `752de52069a34e22322988acd19b5a6a81a4edfa` before promotion.
- B6.2 Windows-validated source-lab checkpoint: `checkpoint/b6-2-hybrid-source-lab-validated-20261008` (`5826d2d96eedbc6fcaa0243dc6dab6eaeb8366a0`).
- SDXL FP16 GPU-verified recovery checkpoint: `checkpoint/sdxl-fp16-animation-gpu-verified-20261009` (`d22b385b4bf9ff67dd5d3419a6e6dfe1e009e8e1`).
- B5.5 performance/stability GPU-verified recovery checkpoint: `checkpoint/b5-5-performance-stability-gpu-verified-20261008` (`e9ea6d0491b8ad57f1bc7539514fe8cb9c7063d3`).
- Keep all `checkpoint/*` refs intact. Treat former feature branches and historical draft PRs as archival, not new starting points.

## Implemented and working

- Windows/Linux self-managed Python install, diagnostics, LAN browser UI, settings, and SDXL/Flux/Z-Image image generation.
- Model/LoRA indexing, metadata and trigger-word inspection, prompt insertion, scheduled LoRA activation; SDXL Transformers 5/Diffusers text-encoder compatibility repair has a verified UNet-only recovery path for problematic adapters.
- Native project save/reopen; responsive Animation Editor / Monitor / Media / Outputs organization; 2D/3D keyframed motion, depth-aware projection, cadence, and temporal anchor blending.
- Resumable image-sequence generation, performance telemetry, GIF previews, FFmpeg MP4/WebM export.
- B6.1: safe legacy Deforum JSON/JSON-serialized TXT import, mapping preview, explicit model choice, new native project creation; unsupported settings reported as passive metadata.
- **B6.2: hybrid-video Source Lab validated on Windows.** Browser-selected video upload to project-managed storage, FFprobe examination/metadata, bounded FFmpeg frame extraction with range/FPS controls, cancellation and preview/scrubbing of extracted frames. This is *video input and preparation*, **not hybrid diffusion/compositing**.

## Physical acceptance and caveats

- On 2026-10-09 the user accepted PR #13 after a 300-frame SDXL 3D cadence-3 run on an RTX 4080 SUPER, four active/scheduled LoRAs, stable reported CUDA allocation around 7.7 GiB across the provided latter portion of the render, and successful high-quality 30 FPS MP4 export.
- This excerpt did not show initial text-encoder loading diagnostics or the generated frames' dimensions. Do not treat it as proof of universal full-text-encoder compatibility or an independently established 768/1024 high-resolution GPU profile.
- `main` promotion PR #14 passed Syntax, Backend, and Installer checks, as did the post-merge `main` push.

## Next B6 implementation

**B6.3 hybrid compositing and mask tracks** starts from the latest `dev-ui`, not the stale `feature/deforum-compatibility-hybrid-b6` tip. Wire selected extracted source frames to renderer-resolved state as an *opt-in* path, with explicit frame alignment, source-vs-generated blend, mask/opacity scheduling, provenance in manifests, deterministic resume, and regression/physical acceptance tests. Preserve existing B5/3D/cadence/LoRA behavior when disabled.

Then B6.4 compatibility and delivery polish: export/preview integration, legacy option diagnostics, completed hybrid render validation, and long-run Windows checks.

**Not yet implemented or fully verified:** hybrid video synthesis/compositing, optical-flow/RAFT cadence, a general extension SDK, ControlNet/RIFE/FILM integration, and unrestricted native large-resolution SDXL animation.

## Development / repository hygiene

- Use short-lived feature branches from `dev-ui` for new work; use PRs and green CI to integrate, then periodically promote the tested baseline into `main`.
- Do not force-reset or delete verified `checkpoint/*` branches.
- Keep `data/`, `outputs/`, `.venv/`, `.runtime/`, `backups/`, and local configuration out of Git.
- Avoid copying GPL/AGPL Deforum implementation source into the Unlicensed Morphorum core. Reimplement compatible behavior independently.
- CI push branch targets are `main` and `dev-ui`; PR checks run on new feature work.
