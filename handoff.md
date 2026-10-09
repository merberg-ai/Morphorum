# Morphorum: full development handoff

**Prepared:** 2026-10-08 (Pacific time)  
**Repository:** https://github.com/merberg-ai/Morphorum  
**Canonical working development branch:** `feature/deforum-compatibility-hybrid-b6`  
**Version in `pyproject.toml`:** `0.1.0a1` (early alpha)  
**B5.5 physically verified code SHA:** `e9ea6d0491b8ad57f1bc7539514fe8cb9c7063d3`  
**B6 opening roadmap SHA:** `6992cdd342b69508030a063dd93026f64945f992`  
**B6 high-resolution planning SHA:** `855f32d920cb8d0a9cd7d29b8da6244422b4054a`  
**This file:** a project-state reference and continuation handoff; it is not evidence that B6.1 or larger-resolution rendering has already passed testing.

> **Immediate handoff:** B5 is **done and GPU-verified**. The native SDXL/Flux/Z-Image image/animation framework, Deforum-style schedules, 2D/3D camera motion, SDXL and Flux LoRAs, cadence, depth, optional future-anchor refinement, 3D preview, MP4/WebM export, performance telemetry, and interruption/resume are implemented. Preserve the B5.5 checkpoint. B6 has a new branch and complete milestone roadmap but its **Deforum import/hybrid video implementations have not begun**. Before pushing toward large frames, investigate the near-full 16 GiB CUDA allocation seen in B5.5 and implement only test-gated, opt-in memory strategies.

---

## 1. Branch and release status

| Branch or checkpoint | Commit | Meaning |
| --- | --- | --- |
| `main` | `8e985a73630b4b025f82b5edd2afea2063421a59` | Older stable/main integration baseline. **Do not assume B5/B6 changes are merged to main.** |
| `feature/3d-depth-quality-b5` | `e9ea6d0491b8ad57f1bc7539514fe8cb9c7063d3` | Final B5.5 development branch, physical acceptance passed |
| `checkpoint/b5-5-performance-stability-gpu-verified-20261008` | `e9ea6d0491b8ad57f1bc7539514fe8cb9c7063d3` | **Primary rescue / known-working B5 checkpoint** |
| `checkpoint/b5-4-video-export-windows-verified-20261008` | `f5db57cab8173c5a8038762a20bb5cc5650f2bd7` | Working video export baseline |
| `checkpoint/b5-3-preview-gpu-verified-20261008` | `cd280280...` | Working 3D motion preview baseline |
| `checkpoint/b5-2-temporal-gpu-verified-20261008` | See GitHub ref | Working temporal-continuity baseline |
| `checkpoint/b5-1-depth-quality-gpu-verified-20261008` | See GitHub ref | Working B5.1 baseline |
| `checkpoint/b4-sdxl-flux-loras-working-20261008` | See GitHub ref | SDXL + Flux single-image LoRA verified |
| `checkpoint/b5-cadence-lora-gpu-stable-20261008` | See GitHub ref | Cadence plus LoRA stability milestone |
| `feature/deforum-compatibility-hybrid-b6` | Opened from `e9ea6d0`; first roadmap commits `6992cdd` and `855f32d` | **New active B6 branch. No B6 importer/hybrid runtime code yet.** |

The B5.5 release candidate reached **247 backend tests passed, 14 browser tests passed, built-in self-test passed**, and received physical Windows acceptance. GitHub Actions reported success at the B5.5 commit on both the backend and syntax/browser workflows. These automated results are specific to the B5.5 commit, not an untested future B6 implementation.

The user also successfully validated B5.4 MP4 and WebM video output on Windows, B5.3 3D motion preview, B5.2 temporal improvements, B5.1 projection improvements, and cadence/LoRA single-image and animation paths.

**Do not rebase, reset, or force-push verified checkpoint branches.** Do not quietly port experimental B6 code to `main`.

### Current checkout workflow

In the Windows Morphorum installation (use its real directory, such as `D:\Morphorum-test`):

```powershell
git fetch origin
git switch --track origin/feature/deforum-compatibility-hybrid-b6
# If a local B6 branch already exists, instead use:
# git switch feature/deforum-compatibility-hybrid-b6
git pull --ff-only
.\update.bat
```

A simpler branch-aware updater may also be used from a compatible installation:

```powershell
.\update.bat feature/deforum-compatibility-hybrid-b6
```

To recover the physical B5.5 baseline, check out
`checkpoint/b5-5-performance-stability-gpu-verified-20261008` in a separate worktree/clone or via the guarded updater. **Preserve `data/`, `outputs/`, model paths and render manifests.**

## 2. Product and engineering goals

Morphorum is a standalone, locally operated, browser-based AI image and Deforum-style animation studio. It runs its own backend on Windows/Linux and is used from desktop and LAN/mobile browsers. The architecture is **not a fork or transplant of GPL Deforum internals**: it is a clean-room, Unlicense-licensed core with native project and timeline types, designed to import legacy settings through translation while retaining modern multi-model independence.

Goals:
- Single-image txt2img and image-to-image/animation generation using model-aware controls.
- SDXL, Flux variants, Z-Image, and their family-compatible LoRAs.
- User-owned external checkpoint/LoRA directories and a model index.
- Detailed LoRA library/metadata management including Civitai optional lookup.
- Deterministic persisted projects, seeds, schedules, frame-by-frame diagnostics, resume.
- 2D and depth-aware 3D image-space camera transforms with diffusion cadence.
- Optional temporal anchor refinement and local video export.
- Responsive, phone-usable UI, LAN operation, no dependency on keeping a browser tab open.
- Future Deforum import, hybrid video sources, compositing, interpolation, and extensions.

**Not implemented merely because it appears in a roadmap:** full Deforum JSON import, hybrid video source, optical flow/RAFT, ControlNet, RIFE/FILM, audio-reactive curves, generic extension/plugin SDK, or automated high-resolution GPU memory tuning.

## 3. Target environment and installation

**Physically tested machine:** HP Omen 35L desktop, NVIDIA RTX 4080 SUPER with 16 GiB VRAM, Windows NVIDIA/CUDA/PyTorch stack, roughly 64 GiB system RAM reported in earlier Morphorum telemetry. The specific current PyTorch build, Windows version, allocator backend, and current driver should be recorded again during memory analysis; older hardware telemetry is not a fresh verification.

**Runtime:**
- Python `>=3.12,<3.13` managed by Morphorum's `uv` installer and virtual environment `.venv`.
- FastAPI + Uvicorn backend; frontend served as static HTML/CSS/JavaScript.
- `pyproject.toml` pinned `diffusers==0.40.0`, `torchvision==0.29.0`, `transformers>=5,<6`, `accelerate>=1,<2`, `peft>=0.17,<1`, Pillow, NumPy, SciPy, etc. **PyTorch proper is installed by the runtime installer; inspect its current version rather than guessing based on torchvision.**
- Default server `http://127.0.0.1:7865/`; `run-lan.bat` allows LAN listening, firewall permitting. Browser can be used from phone.
- FFmpeg on the *host*, found via PATH or `MORPHORUM_FFMPEG`, is required for video export.
- Launchers: `run.bat`, `run-lan.bat`, `install.bat`, `update.bat`, `repair.bat` (and Linux `.sh` equivalents). Entry-point CLI `morphorum`.

**Installation layout, update survival:**
- `.runtime/`: Morphorum-managed uv, Python runtime, caches.
- `.venv/`: app dependencies and CUDA inference libraries.
- `data/`: config, model indexes, databases, projects/user state.
- `outputs/`: generated images, renders, frame PNGs, video files.
- `logs/`: runtime, installation/update/repair logs.
- `backups/`: update rollback snapshots.
- External model/LoRA directories are indexed, not copied wholesale.
- These runtime/user directories must not be clobbered by Git or installer upgrades.

Important commands:

```powershell
.\run-lan.bat
.\update.bat
.\repair.bat
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m morphorum doctor
ffmpeg -version
nvidia-smi
```

If the development dependencies are installed: `uv run --group dev pytest` and `uv run --group dev ruff check backend tests`. The GitHub Actions jobs are the reference CI gates.

**Docs caveat:** some older milestone documents contain provisional language from the time they were written (such as "renderer not yet installed"). Follow **current source code, physical checkpoints, and newer B5/B6 documentation**, not stale historical paragraphs.

## 4. Repository map (files to know)

| Path | Responsibility |
| --- | --- |
| `backend/morphorum/app.py` | FastAPI routes, health/system metrics, animation projects, timelines, previews, render jobs, video export, LoRA APIs, model APIs |
| `backend/morphorum/generation.py` | Model capability table, SDXL/Flux/Z-Image pipeline loading, CUDA vs offload, txt2img/img2img conversion, LoRA attachment/activation, device/memory telemetry |
| `backend/morphorum/animation_projects.py` | Schema 2 project defaults/normalization, legacy compatibility fields, persistence, unknown-field preservation |
| `backend/morphorum/animation_timeline.py` | Canonical track/keyframe bundle, numeric and prompt tracks, legacy synchronization |
| `backend/morphorum/schedules.py` | Restricted Deforum-like schedule parsing, interpolation and validation |
| `backend/morphorum/animation_resolution.py` | Canonical resolved-frame state: prompts, motion, generation, cadence and LoRAs |
| `backend/morphorum/animation_render.py` | Animation job queue, PNG generation, cadence anchors, motion/depth, prompt conditioning, cancellation/resume, snapshots and preview |
| `backend/morphorum/animation_3d.py` | Depth-projected camera transforms / 3D image warping and exposed-pixel handling |
| `backend/morphorum/animation_depth.py` | Depth Anything V2 Small backend, cached depth, device control and previews |
| `backend/morphorum/animation_temporal.py` | Optional future-anchor depth reprojection and intermediate-frame blend |
| `backend/morphorum/animation_motion.py` | Motion-only CPU previews, presets and coverage diagnostics |
| `backend/morphorum/animation_performance.py` | JSONL per-frame timings, CUDA samples, LoRA residency, summary/restart handling |
| `backend/morphorum/animation_video.py` | Independent FFmpeg MP4/WebM background export jobs and stored export history |
| `backend/morphorum/model_index.py`, `managed_models.py` | Model scanning/lookup and managed model download |
| `frontend/dist/index.html` | Workspaces and controls |
| `frontend/dist/assets/animation.js` + `animation.css` | Animation UI, cadence/3D scheduling, preview, render monitoring, performance, video export |
| `docs/B5_3D_CADENCE_PLAN.md` | B5 implementation/physical gate history |
| `docs/PERFORMANCE_CADENCE.md` | B4 LoRA/Flux performance investigations, tested fixes and caveats |
| `docs/B6_DEFORUM_HYBRID_PLAN.md` | **Current B6 roadmap**, including prioritized high-resolution investigation |
| `docs/TIMELINE_SCHEMA.md` / `ANIMATION_PROJECTS.md` / `SCHEDULES.md` | Project compatibility contract |
| `tests/` and `.github/workflows/` | Python/JavaScript regression suites, backend/syntax CI |
| `README.md`, `docs/ARCHITECTURE.md`, `docs/ROADMAP.md` | Product overview, architecture, historical/future scope |

## 5. Native project structure and rendering contract

Native animation schema version **2** contains:
- `animation`: `max_frames`, `fps`, `width`, `height`, `mode` (2d/3d), `start_mode` (prompt/source), source-image metadata and prompt transition mode.
- `model`: selected indexed model ID, family, variant. Imported legacy filename **must not** become an implicitly trusted host path.
- `prompts` / `negative_prompts`: frame-number-to-text maps. Prompt interpolation supports hold/blend; LoRAs can be embedded via `<lora:name:weight>`.
- `motion`: 2D angle, zoom, translation X/Y, border behavior.
- `camera_3d`: translation X/Y/Z, rotation X/Y/Z, FOV, depth resolution, projection mode and hole-fill strategy.
- `generation`: strength, noise, steps, guidance, sampler, seed behavior/increment.
- `cadence.diffusion`: per-frame diffusion interval schedule.
- `temporal`: forward or future-anchor refinement with mix/contrast threshold.
- `tracks`: canonical editable prompt and numeric keyframes mirrored into legacy schedule fields.
- Unknown top-level fields are generally preserved for forward compatibility.
- Render manifests freeze a project snapshot and seed plan, so resumed renders do not silently pick up later UI edits.

**Architecture rule:** importers and new editors must translate into the canonical Morphorum project/track/resolver API, *not* add a second Deforum renderer or bypass model-family validation.

**2D/3D frame loop:**
1. Lock inference; resolve project frame, seed, model capability, active prompt and LoRA schedule.
2. Frame 0 comes from a prompt generation or uploaded source image.
3. For each subsequent frame, compute image-space camera transform. In 3D mode, estimate/reuse cached relative depth, warp using depth, and create disocclusion mask if applicable.
4. With cadence 3, diffuse at frames 3,6,9,... plus forced last anchor; otherwise save transformed intermediate frames without diffusion.
5. Diffused anchors run model-family img2img with scheduled strength/noise/LoRAs. Prompt embedding blend is wrapped in `torch.inference_mode()` and has bounded eight-entry caching to prevent graph retention.
6. Optional B5.2 future-anchor mode refines intermediate frames with future diffused anchor; otherwise use original forward transform behavior.
7. Save PNG + frame metadata + render manifest; append B5.5 performance JSONL record for completed frames. On cancel, leave resumable output.
8. Assemble GIF preview; optionally encode separately to FFmpeg MP4/WebM **without rerunning diffusion**.

### Functional API landmarks

- `GET /api/health`; `GET /api/system/telemetry`
- `GET|POST|PUT /api/animation/projects...`; source-image upload and depth preview routes
- `GET /api/animation/timeline/descriptors` and project timeline/track endpoints
- `POST /api/animation/resolve-frame`; `POST /api/animation/resolve-timeline`; `POST /api/animation/validate-schedules`
- `POST /api/animation/motion-preview` and preview status/image
- `POST /api/animation/renders`, `GET /api/animation/renders/{render_id}`, `POST .../cancel`, `POST /api/animation/renders/{project_id}/{render_id}/resume`
- `GET /api/animation/renders/{project_id}/{render_id}/performance`
- `GET /api/animation/video/availability`, `POST /api/animation/renders/{project_id}/{render_id}/video`, video jobs/history/download routes
- `GET /api/loras`, inspect/Civitai/runtime audit, and model/managed model routes
- Inspect current `app.py` OpenAPI for exact bodies, response schemas and route signatures instead of constructing them from this abbreviated list.

## 6. Model and LoRA implementation details

**SDXL:** checkpoints loaded using `StableDiffusionXLPipeline.from_single_file`, FP16 on available CUDA, then `pipe.to("cuda")`. Task switch via `StableDiffusionXLImg2ImgPipeline.from_pipe(...)` retains shared model components. SDXL LoRA loading includes a compatibility fallback to converted UNet-only weights if a known Diffusers/PEFT text-encoder rank compatibility bug triggers. This fallback has been visually verified on selected real SDXL LoRAs. Do not delete it casually; the skipped text-encoder weights are an explicit quality compatibility caveat.

**Flux:** supported Dev/Schnell-class pipeline families. Base FP8 checkpoints can use FP8 layerwise storage with BF16 compute where supported. Some PEFT LoRA wrapping causes the FP8 CUDA `addmm_cuda` incompatibility; active Flux LoRAs intentionally use a BF16/FP16-compatible transformer storage path. On 16 GiB hardware, *non-streamed* block-level group offload avoids the prior pinned-host-memory `cuMemHostAlloc` setup failure. Do not reintroduce streamed pinned-memory loading blindly.

**Z-Image:** managed model package with GPU or conservative low-VRAM offloading selected by available VRAM and model variant. External Z-Image LoRA indexing exists; do **not** claim physical Z-Image LoRA influence on this RTX 4080 SUPER without a separately logged A/B test.

**LoRA Manager:** scans configured directories by family and supports metadata inspection, trigger-word display/insert, optional Civitai hash-based metadata lookup, runtime audit and family resolution. LoRA tag syntax is `<lora:name:weight>` in positive prompts only. Dynamic weights and multiple prompt windows are applied through Diffusers/PEFT; adapters are resident/reused, not fused into checkpoints. Family mismatch is an error, not an automatic substitution.

**Physical LoRA acceptance:** user confirmed **SDXL and Flux single images with LoRAs visibly working**, plus SDXL long animation with up to three resident adapters. Treat additional combinations as future test cases, not as automatically verified.

## 7. B5 phase-by-phase acceptance record

| Phase | Delivered | Acceptance |
| --- | --- | --- |
| B5.0 / cadence hardening | Fixed SDXL prompt-conditioning CUDA graph retention, bounded embeddings, cadence UI and anchors, native GPU behavior | Windows generation verified; prior 75s latency outliers resolved |
| B5.1 | Depth-aware subpixel splat projection, hole-fill and disocclusion masks, backward-compatible legacy mode | Physical 3D generation verified |
| B5.2 | Optional future-anchor depth-aligned refinement with protection of legacy forward-only cadence | User accepted on Windows |
| B5.3 | CPU-only 3D motion GIF preview, camera presets, red exposed-pixel diagnostics and projection coverage | User supplied successful preview and accepted |
| B5.4 | Async FFmpeg H.264 MP4/VP9 WebM, quality/FPS settings, browser playback/download, persisted history | User confirmed video export works |
| B5.5 | Per-frame GPU and stage telemetry, LoRA residency monitoring, crash-safe JSONL, resume/long-render regression | **User accepted on Windows**, checkpointed at `e9ea6d0` |

B5.5 suite: **247 backend and 14 browser tests**, plus self-test, passed at final B5 commit. Do not label any later B6 head as tested at this count until its own CI completes.

### B5.5 real render: exact observed evidence

From user-supplied completed JSON report:
- Project ID: `b5-test-1-9a350a88`
- Render ID: `anim-20261008-193424-a59fce`
- 75 frame outputs, detailed records for frames 1–74 (**74 observed**, because frame 0 is the starting image).
- **25** diffused anchor records at cadence 3, including forced last anchor.
- **Average frame elapsed:** 3.098 s over the profiled frames.
- **Average anchor diffusion:** 7.487 s.
- **Total recorded frame work:** 229.247 s, including **187.167 s diffusion**, **30.566 s prepare**, **1.813 s conditioning**.
- **Slow anchor list:** empty for the 30s threshold.
- **Max observed current CUDA tensors allocated:** 14.413 GiB.
- **Max observed current allocator reserved:** 14.52 GiB.
- **PyTorch process peak allocated:** 15.3563 GiB.
- **PyTorch process peak reserved:** 16.4258 GiB, although reported device total was 15.9917 GiB.
- **Reported GPU free:** 0.0 GiB in the later per-frame CUDA samples. This requires interpretation: see section 8.
- **Active execution:** device `cuda`, optimization `native-gpu`, task `img2img`.
- **Resident LoRAs:** 2 initially; third LoRA first introduced at frame 27; no continuing growth thereafter.
- **Prompt-conditioning cache:** reached its configured 8-entry cap without unbounded growth.
- **First diffusion anchor frame 3:** 32.735 s total; 25.36 s of that was *pipeline/LoRA preparation*, diffusion itself ~6.718 s. Later anchors had small prepare times except the 3rd adapter addition at frame 27 (~4.438 s prepare).
- **Steady diffused anchors:** around 6.36 s early; around 7.08 s after third adapter was introduced; approximately 9.1 s near the end. Still correct CUDA inference, not evidence of CPU fallback.
- **Transform-only frames:** typically ~0.08–0.16 s, with no diffusion.
- User additionally confirmed pause/resume/cancel and telemetry work as expected.

**Bottom line:** The B5.5 report does not show an accumulating allocator memory leak after the third LoRA. It shows that the model and adapters consume **most of 16 GiB already at 512x512** and that an unknown amount of headroom remains under actual peak inference conditions. Rendering at 1024 is **not yet certified**.

## 8. CUDA / VRAM investigation and large-resolution engineering plan

### 8.1 What is actually happening, and what is not yet proven

**Confirmed from code:**
- SDXL CUDA loader chooses `torch.float16`, instantiates the complete Diffusers pipeline and calls `pipe.to(device)`; it does **not** currently configure SDXL VAE tiling or SDXL CPU model offload as an automatic memory mode.
- All requested LoRAs are loaded into shared PEFT-enabled pipeline components and remain resident to allow fast dynamic reweighting. A new adapter adds some VRAM; the same adapter's repeated use is cheap.
- Frame-based depth uses Depth Anything V2 Small explicitly on CPU; **CPU depth prediction is not CPU diffusion**.
- Prompt embedding generation uses inference-only tensors with eight-entry bounded cache; this fixed a prior true VRAM growth problem.
- The hot loop attempts to preserve allocator caches; `maintain_inference_memory()` only trims reclaimable cache on substantial pressure, to prevent throughput destruction from gratuitous `empty_cache()` calls.
- `cuda_memory_status()` reads `torch.cuda.mem_get_info()`, `memory_allocated()`, `memory_reserved()` and lifetime peaks. **It currently does not record the PyTorch CUDA allocator backend or WDDM dedicated/shared memory residency.**
- The single-image request validator accepts dimensions 64–4096, divisible by 8 for SDXL or 16 for Flux/Z-Image; native animation normalization permits dimensions up to 8192. These are **input validation ceilings, not GPU memory guarantees**.

**Not proven from a single JSON report:**
- Whether physical VRAM was overcommitted and paged into shared system memory, or whether the driver and allocator were simply near their residency budgets.
- Whether `max_memory_reserved` > 16 GiB represents simultaneous physical VRAM allocation. PyTorch documents that, when using the `cudaMallocAsync` allocator, the process high-water figure can *sum independent mempool peaks at different instants*, yielding a conservative upper bound above the true simultaneous peak. Check `torch.cuda.get_allocator_backend()` before interpreting that number.
- Whether larger 768/1024 images fail, slow, or fit with optimizations.
- Whether VAE decoding, UNet activations, prompt encoding or dynamic LoRA residency dominate the *transient peak*. The current per-frame snapshot is taken after inference, so it can miss a higher intermediate peak.

**Working hypothesis to test:** On 16 GiB with 2–3 LoRAs, SDXL resident weights and activation peaks leave little margin for larger spatial tensor sizes. WDDM budget/residency under Windows may additionally constrain behavior, but must not be blamed without dedicated/shared GPU memory measurements. `free_gib=0.0` means the CUDA driver reported no free heap space in that query; it does not alone identify who owns each allocation or prove CPU execution.

**Official technical references:**
- PyTorch allocator peaks, including `cudaMallocAsync` caveat: https://docs.pytorch.org/docs/stable/generated/torch.cuda.memory.max_memory_reserved.html
- PyTorch CUDA semantics and memory tuning: https://docs.pytorch.org/docs/stable/notes/cuda.html
- PyTorch detailed CUDA memory profiling: https://docs.pytorch.org/docs/stable/torch_cuda_memory.html
- Diffusers memory approaches, tiling/offload tradeoffs: https://huggingface.co/docs/diffusers/optimization/memory
- Microsoft WDDM 2.0 GPU virtual-memory/residency model: https://learn.microsoft.com/en-us/windows-hardware/drivers/display/gpu-virtual-memory-in-wddm-2-0

### 8.2 High-priority B6.0-P instrumentation

**Before enabling any offload mode**, add low-cost, opt-in diagnostics:

1. At startup/model load record GPU device, total physical VRAM, PyTorch version and `torch.cuda.get_allocator_backend()` (native or cudaMallocAsync), CUDA capability, active model family/dtype, driver info where available, platform and CUDA availability.
2. Record **current** allocated/reserved and the separate **peak** allocated/reserved at phase boundaries; distinguish "process peak since launch" from "peak of this image / anchor." If using `reset_peak_memory_stats()`, only do so at safely controlled boundaries and document that it alters cumulative counters. Alternatively track per-phase deltas and independent sampling while retaining existing lifetime counters.
3. Add separate optional checkpoints after model load, LoRA load, text conditioning, VAE image encode, UNet diffusion, VAE decode, depth projection, and cleanup. Do not insert blocking CUDA synchronization every frame unless running a deliberate profiling experiment.
4. Snapshot `torch.cuda.memory_stats()` and allocator backend on errors; allow a manually requested `memory_summary()` or `memory_snapshot()` only while debugging and with an output-size/sensitivity cap. Avoid continuously storing giant allocator dumps.
5. Capture Windows Task Manager **Dedicated GPU memory** and **Shared GPU memory**, alongside the process's system RAM/commit and overall free system RAM. `nvidia-smi` may expose different or incomplete accounting under WDDM. Correlate timestamps, don't assume PyTorch allocator metrics measure OS residency.
6. Show VRAM safety state clearly: *allocated CUDA tensors*, *cached/reserved*, *CUDA driver free*, *Windows shared GPU usage*, *measurement backend*. Warn on pressure; don't silently switch from CUDA to CPU diffusion.
7. Produce a short report that correlates resolution, model, # adapters, diffusion seconds and peak allocations. Keep masks, prompts and model paths out of logs unless explicitly exported by user.

Non-invasive baseline commands (run in Windows PowerShell, from Morphorum folder):

```powershell
nvidia-smi
nvidia-smi --query-gpu=name,memory.total,memory.used,utilization.gpu --format=csv -l 1
.\.venv\Scripts\python.exe -c "import torch; print('torch:',torch.__version__); print('allocator:',torch.cuda.get_allocator_backend()); print('GPU:',torch.cuda.get_device_name(0)); print('VRAM GiB:',round(torch.cuda.get_device_properties(0).total_memory/1024**3,2))"
```

Do not run a separate Python process's `torch.cuda.memory_summary()` and mistake it for **Morphorum's** allocations; each process has its own CUDA allocator. Log/inspect allocator state **in Morphorum's server process**.

### 8.3 Staged, opt-in memory strategies (ranked)

**Mode A: existing native CUDA (control case).** Preserve current SDXL FP16 full-GPU pipeline and all tested LoRA behavior. Compare the same seed/steps/prompt/LoRAs against every new mode. Avoid surprise output changes.

**Mode B: VAE tiling first.** Diffusers provides `pipe.vae.enable_tiling()` to decode/encode large images using tiled processing; this can reduce large-image VAE memory use without relocating the diffusion UNet. Useful if VAE peaks are material. Validate SDXL image-to-image encode and decode, tile seams, slight visual/tone differences, output dimensions and native/tiling reproducibility. Tiling will not fix UNet activation peaks and is not a magic 1024px guarantee. `enable_vae_slicing()` is mainly useful for multi-image batches, not a single image per animation frame.

**Mode C: attention/backend review.** Confirm Diffusers/PyTorch scaled-dot-product attention backend and any memory-efficient implementation are actually used. Benchmark alternatives only after profiling; a blanket `xformers`/`torch.compile` dependency or allocator switch is not a proven optimization for this environment.

**Mode D: text-encoder lifecycle.** Since animation consumes text prompts chiefly at diffusion anchors and caches detached embeddings, investigate keeping UNet CUDA-resident but offloading inactive text encoder components to CPU between encoding windows. **Caution:** text-encoder LoRAs, active adapter state, `encode_prompt()` outside pipeline call, and `from_pipe()` task conversions all interact with device/offload hooks. Keep such mode opt-in, comprehensively test dynamic prompts/LoRAs, and fail explicitly on incompatible adapters.

**Mode E: model-level CPU offload as memory-constrained fallback.** Diffusers `enable_model_cpu_offload()` may fit bigger frames by moving whole components when inactive, but adds transfer overhead. Sequential CPU offload is much slower and should be *explicitly last-resort*, not a default for the RTX 4080 SUPER. Existing Flux/Z-Image offload strategies have separate model-specific code; never apply an SDXL setting globally to those families.

**Mode F: optional active/resident LoRA budget.** Cap or unload inactive adapters only if the telemetry actually shows that LoRA residence drives memory exhaustion. Cache invalidation must keep adapter names/signatures synchronized and must never drop the weights currently active in a window. Repeat-loaded LoRAs might cost performance; preserve the unmodified option.

**Mode G: larger-than-native output workflows.** For 1536/2048/4K aspirations, consider a separate image/video **upscale and tiled-refinement** pipeline once true native generation is characterized. Distinguish "native 2048 diffusion" from "1024 diffusion plus 2x upscale" in the UI and metadata; these are not identical quality paths. Consider future tile-aware temporal coherence, optical-flow reuse, and export dimensions.

**Do not** start by globally enabling `empty_cache()` after every frame, auto-switching to CPU, quantizing LoRA layers without tests, or assuming that changing `PYTORCH_CUDA_ALLOC_CONF` will cure a model that's genuinely too large. Changing allocator backend may invalidate comparisons and affect available statistics.

### 8.4 Physical high-resolution acceptance matrix

| Image dimensions | Relative pixels vs 512² | Gate |
| --- | ---: | --- |
| 512×512 | 1× | Existing B5.5 verified SDXL baseline |
| 768×768 | 2.25× | First 1-image, then 3-frame CUDA + LoRA test |
| 896×1152 | 3.94× | Portrait aspect ratio stress |
| 1024×1024 | 4× | **Primary SDXL high-resolution target**, no current GPU acceptance |
| 1216×832 | 3.86× | Landscape aspect stress |
| 1536×1024 | 6× | Only after measured safety margin |
| 1536×1536 | 9× | High-risk, optional memory mode and physical tests required |
| 2048×2048 | 16× | Stretch target; likely requires specialized tiled/upscaling approach on 16 GiB |

**Important:** pixel multipliers do *not* imply exact 2.25×/4×/9× VRAM or time: model weights are roughly fixed but activation and attention work depend on architecture/resolution, sampler and batch. SDXL is normally designed around ~1024px composition, but existing VRAM pressure makes a native 1024 **unverified here**.

For every attempted size:
1. Restart Morphorum or explicitly unload model to establish the controlled baseline.
2. Use identical checkpoint, scheduler, steps, seed, prompts and LoRA weight; compare no-LoRA / one-LoRA / three-LoRA cases.
3. Run still image first, then 3–6 frames in 2D and 3D with cadence 3, then a longer render only if stable.
4. Record preparation, diffusion and decode times, current/peak CUDA allocations and Windows dedicated/shared memory, and visual LoRA/prompt influence.
5. Verify cancellation/resume, depth masks, temporal mode, PNG frame count and FFmpeg exports at the target size.
6. Stop on repeated OOM or obvious system-memory spill. Preserve logs, restore the safe mode; never let failed trial settings poison a previously working pipeline.
7. Document device placement and memory mode in each frame/render manifest.

**Release gate:** do not promote a high-resolution optimization based on CI alone. Physical quality/performance validation on the RTX 4080 SUPER is required, and B5.5 must remain untouched as a rollback.

## 9. Complete B6 roadmap

**B6 theme:** native Deforum project compatibility plus browser-first hybrid-video workflows, while retaining B5 reliability and adding a parallel, test-gated higher-resolution capability.

**Current source of truth:** `docs/B6_DEFORUM_HYBRID_PLAN.md`. The milestone order below is deliberately additive. B6.0-P is a diagnostic/preflight priority; it may proceed alongside B6.1 but must be accepted before promising full-resolution B6 animation.

### B6.0-P: VRAM profiling and high-resolution guardrails

**Deliverables:** allocator-backend-aware reporting; phase-memory sampling and error diagnostics; Windows dedicated/shared residency correlation; explicit profile modes; bounded first high-resolution test matrix; non-destructive safeguards/clear OOM recovery.

**Implementation restrictions:** no automatic CPU fallback, no forced allocator reset every frame, no renderer quality changes by default. New VAE tiling/text-encoder/offload modes are separately switchable and independently regression/physical tested.

**Gate:** baseline 512px preserved, 768px GPU tested, 1024px path characterized and either accepted or clearly reported as requiring specific opt-in mode. No invented success.

### B6.1: Legacy Deforum JSON/TXT import into native projects

**A. Input parser and safety**
- Identify common Deforum settings JSON formats and key naming. Support documented TXT serialization only when unambiguous; otherwise return useful diagnostic.
- Strict size and nesting limits, keyframe count caps, syntax validation, safe expressions: no `eval`/arbitrary Python, no uncontrolled imports, no arbitrary paths from external JSON.
- Deterministic importer version and a fixture-driven translator; original source input retained only in a passive namespaced compatibility metadata field, with limits.
- Explicit warnings for unmapped, partially mapped, ambiguous, unsupported, or family-incompatible parameters.
- Pure **preview/dry-run** operation that cannot mutate a project. A separate user confirmation saves to a **new** native project.

**B. Initial settings mapping**
- `max_frames`, `fps`, `W`, `H` → animation dimensions/length/playback.
- `animation_mode` → native 2D/3D where supported; mark others as unsupported.
- `animation_prompts` and supported negatives → prompt tracks/keyframes and legacy mirrors.
- `angle`, `zoom`, `translation_x/y` → native 2D camera schedules.
- `translation_z`, `rotation_3d_x/y/z` → 3D camera schedules **only after checking conventions/units**. Do not silently assume identical geometry.
- `strength_schedule`, `noise_schedule`, `steps`, `cfg_scale/_schedule` → supported generation schedules, preserving expression syntax when safe.
- `diffusion_cadence` → native cadence schedule (1–64).
- `seed`, `seed_behavior` and known sampler names → native equivalents where family-compatible.
- Deforum masks, ControlNet, hybrid video, optical flow and model paths → warnings and passive source metadata until explicit support is delivered; preserve source rather than fabricating working settings.
- Resolve checkpoint and LoRA names only through indexed Morphorum libraries. Do not launch with unverified local paths or nonexistent families.

**C. UI/UX**
- Desktop/mobile import dialog: drop/upload JSON; structured preview; mapping status; side-by-side settings; warning badges as appropriate; deliberate model selection; create-new-project confirmation.
- Imported project opens in the normal Animation timeline and resolved-frame inspector; no special legacy editing mode.
- Always allow cancel/discard, and preserve original JSON in a user-visible compatibility report.

**D. Tests and physical acceptance**
- Golden 2D and 3D Deforum JSON fixtures with prompt and schedule scenarios.
- Round-trip import → normalized schema 2 project → save/reload → native resolved frames; source never mutated; unknown fields retained.
- Invalid JSON, oversized/corrupt payloads, unsafe expression strings, traversal paths, unsupported models, unknown sampler, ambiguous 3D motion.
- UI must show warnings before creation, never silently overwrite an existing project.
- Real Windows test: select known Deforum settings file, map to installed SDXL checkpoint, inspect timeline and output short GPU render with prompt+LoRA schedule. **Checkpoint B6.1 after acceptance.**

### B6.2: Video input and reproducible source frame extraction

- Browser-native upload and project-owned managed files. Avoid any host-computer file picker being opened remotely on the wrong machine.
- Use FFmpeg/ffprobe to inspect codec/duration/FPS/dimensions; validate input size, safe file path and upload caps.
- Source frame trim, target FPS resampling policy, start/end timestamps, frame numbering, optional input audio metadata, aspect fit/crop and color metadata.
- Deterministic extracted PNG sequence with source-video hash/provenance and time-map manifest; robust progress/cancel/restart.
- Frame-source mode opt-in; native prompt-start and source-image-start B5 workflows remain unmodified.
- Tests for VFR source, missing file, invalid format, short clip, non-square pixels, rotation/orientation metadata, resampling policy, size limits and interrupted extraction.
- Physical acceptance: browser/phone upload over LAN, reproducible frames, no server-side file chooser, safe error behavior.
- **Checkpoint B6.2 after acceptance.**

### B6.3: Hybrid render pipeline and compositing controls

- Explicit selectable hybrid modes (source frame / generated frame / blend), scheduleable source-versus-generated contribution, opacity and mask tracks.
- Order of operations documented: frame acquisition, camera/motion transforms, depth, source alignment, mask logic, denoise/conditioning, temporal blending and final composite.
- Source-frame masks, compositing alpha and motion warp in consistent pixel coordinates. Validate source/resolution mismatch and frames with missing reference data.
- Persist exact resolved hybrid state, source-frame index/time, mask and composite settings in each frame metadata and render manifest to guarantee resume.
- CPU/GPU memory budget considered before enabling multi-frame buffers; do not hold entire video in GPU RAM.
- Frame preview shows source, warped, mask and composite diagnostics. Outputs can use existing MP4/WebM exporter unchanged where possible.
- Automated 2D/3D, cadence, multiple prompts and LoRA regression suite.
- Physical acceptance: 75+ frames with source video, SDXL LoRAs, three prompt windows, cadence 3, save/resume, stable memory and correct exported video.
- **Checkpoint B6.3 after acceptance.**

### B6.4: Compatibility polish, hardening and B6 release gate

- Report unsupported Deforum keys, import fidelity and native-equivalent settings; optionally export the subset of interoperable settings without claiming 100% Deforum parity.
- Refine mobile/touch UX, saved presets, validation messages and project portability metadata.
- Optional 3D/hybrid preview and comparison tools, plus repeatable performance profiling at the accepted resolution modes.
- End-to-end CI for source import, video extraction, hybrid frames, LoRA transitions, cancellation/resume, export and bad/corrupt input.
- Windows GPU acceptance: visual fidelity, deterministic output, long render, high-resolution diagnostics and graceful OOM/rollback.
- Tag/checkpoint verified B6; only then merge/release according to existing repository policy.

### Beyond B6 (do not claim as B6 implemented)

Longer-term backlog in `docs/ROADMAP.md` includes optical flow (RAFT or equivalent), ControlNet, RIFE/FILM interpolation, Parseq concepts, audio/reactive schedules, plugins, model adapter expansion, queue/notifications and richer camera visualization. Schedule after B6 acceptance and based on actual GPU headroom.

## 10. Tests, expected safeguards and definition of done

**Baseline verification (B5.5):** 247 Python backend tests, 14 Node/browser tests, Morphorum self-test; successful real SDXL/Flux LoRA and long 3D/cadence tests. The exact B5.5 CI result is the reference, not a permanent count.

**Every B6 work packet:**
1. Inspect current branch + latest commit and create a small-scoped plan.
2. Write regression tests *before or alongside* new code. Run backend pytest, JavaScript syntax/browser checks, built-in self-test and validate GitHub Actions on final SHA.
3. Confirm renderer nonregression and no change to frame/seed/LoRA schedules for pre-existing projects.
4. Put any new high-VRAM or output-quality-changing optimization behind an explicit opt-in.
5. Preserve render metadata and crash-safe resume. Avoid exposing arbitrary filesystem access to LAN clients.
6. Update docs, changelog/roadmap, and exact GPU physical gate.
7. Stop at test gate for user's real machine; never call CI "GPU-verified."
8. Upon real acceptance, branch/commit a checkpoint from the verified SHA and advance to next milestone. **Never replace B5.5 checkpoint.**

Potential additional tests for VRAM features:
- Simulated CUDA OOM during load, LoRA activation, img2img, VAE, and hot frame; cleanup and actionable errors.
- Repeated cold-start/reuse cycles; assert adapter registry and LoRA active signatures.
- Peak-memory telemetry with `native` vs `cudaMallocAsync` backend mocks; clear label semantics.
- Native vs tiling output dimensions/alpha/color handling; text-encoder LoRA compatibility.
- No unbounded GPU references or cached tensors across prompt windows.
- Large PNG and depth map memory use, backpressure on CPU queues and FFmpeg exports.
- No automatic slow sequential-offload downgrade.

## 11. Known risks and unresolved questions

| Risk | Current evidence | Follow-up |
| --- | --- | --- |
| Large-resolution SDXL VRAM pressure | 512² native CUDA + up to 3 LoRAs left little headroom; process peak tensor allocation ~15.36 GiB | B6.0-P allocator/OS profiling and 768/1024 tests |
| `max_memory_reserved` > device total | 16.4258 GiB peak statistic vs 15.9917 GiB physical | Record allocator backend and WDDM shared/dedicated residency; don't assert paging solely from peak |
| SDXL fallback UNet-only LoRAs | Known Diffusers/PEFT text-encoder compatibility issue; real visual effectiveness works for tested LoRAs | Preserve diagnostics; compare text-encoder effects in targeted tests |
| Flux FP8 plus LoRA | FP8 PEFT wrappers can fail on CUDA; higher-precision transformer LoRA fallback works physically | Preserve BF16 compatibility and nonstreamed 16GB offload |
| GPU stress with VAE/3D at 1024+ | No Windows acceptance yet | Phase-specific memory profiling and opt-in tiles |
| Legacy Deforum format complexity | No actual importer exists on B6 branch yet | Fixture-based parser with warnings and no arbitrary code/path evaluation |
| Deforum 3D coordinate semantics | Possible differences in rotation/translation and camera units | Explicit mapping tests; warn on non-equivalent keys |
| Hybrid video pipeline | Not implemented | B6.2 + B6.3 opt-in and FFmpeg provenance |
| Historical documentation inconsistencies | Old docs reflect provisional phase status | Use source+verified checkpoints as truth; update docs while implementing |

### Useful repository links

- Repo: https://github.com/merberg-ai/Morphorum
- B6 branch: https://github.com/merberg-ai/Morphorum/tree/feature/deforum-compatibility-hybrid-b6
- B5.5 recovery: https://github.com/merberg-ai/Morphorum/tree/checkpoint/b5-5-performance-stability-gpu-verified-20261008
- B5 roadmap: https://github.com/merberg-ai/Morphorum/blob/feature/3d-depth-quality-b5/docs/B5_3D_CADENCE_PLAN.md
- B6 roadmap: https://github.com/merberg-ai/Morphorum/blob/feature/deforum-compatibility-hybrid-b6/docs/B6_DEFORUM_HYBRID_PLAN.md
- CUDA/LoRA historical notes: https://github.com/merberg-ai/Morphorum/blob/feature/3d-depth-quality-b5/docs/PERFORMANCE_CADENCE.md
- SDXL loader: https://github.com/merberg-ai/Morphorum/blob/feature/deforum-compatibility-hybrid-b6/backend/morphorum/generation.py
- Performance renderer: https://github.com/merberg-ai/Morphorum/blob/feature/deforum-compatibility-hybrid-b6/backend/morphorum/animation_performance.py

## 12. Specific instructions to the next development session

**Start here:**

1. Fetch `feature/deforum-compatibility-hybrid-b6` and read this `handoff.md`, `docs/B6_DEFORUM_HYBRID_PLAN.md`, `docs/PERFORMANCE_CADENCE.md`, `backend/morphorum/generation.py`, `animation_render.py`, `animation_projects.py` and `animation_timeline.py`.
2. Verify branch HEAD and latest CI independently; B6 only contains opening roadmap and handoff until new features are committed. Do not invent B6.1 implementation status.
3. **Priority discussion:** B6.0-P. Propose an explicit memory profile API/CLI mode that reports allocator backend and captures peak memory at SDXL load, conditioning, UNet and VAE. Collect Windows dedicated/shared GPU evidence from the user's 4080 SUPER before changing placement/offload.
4. In parallel, prepare B6.1 input fixture schema and importer mapping tests; implement safe parser/preview first, then UI and new-project persistence. Do not wire a Deforum setting to live inference until compatibility is validated.
5. Perform the first 768/1024 test in a small separate GPU test gate, while leaving native 512 settings and B5.5 recovery untouched.
6. Keep user informed of scope, CI counts, commit IDs and any physical test prerequisites. Checkpoint verified milestones, **never** claim an actual GPU rendering result merely from unit tests.

**Current acceptance boundary:** B5.5 complete, B6 planning committed; VRAM optimization, native 1024+ generation and Deforum import/hybrid rendering remain **unverified / not implemented**.

---

*Prepared from current GitHub source at B6 opening, the repository's architecture/installation/timeline/LoRA/B5 docs, and the physically tested B5.5 frame telemetry. External PyTorch, Diffusers and Microsoft documentation inform the VRAM interpretation and options. The larger-resolution recommendations are engineering proposals, not claims of tested success.*
