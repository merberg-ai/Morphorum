# B6 physical acceptance gate

**Branch:** `feature/deforum-compatibility-hybrid-b6`  
**Automated code checkpoint entering this gate:** `d982a323e946fb652cb11fdaf6b50d99a1e8adcb`  
**Known-good recovery checkpoint:** `checkpoint/b5-5-performance-stability-gpu-verified-20261008` at `e9ea6d0491b8ad57f1bc7539514fe8cb9c7063d3`

This gate is intentionally physical. CI cannot prove Windows WDDM accounting, RTX 4080 SUPER headroom, visual LoRA influence, Deforum camera equivalence, or VAE-tiling quality. Do not checkpoint B6.1 or call 768/1024 supported until the relevant sections below pass.

## 1. Update and record the environment

From the Windows Morphorum install:

```powershell
git fetch origin
git switch feature/deforum-compatibility-hybrid-b6
git pull --ff-only
.\update.bat
.\.venv\Scripts\python.exe -m morphorum doctor
nvidia-smi
```

Record:
- current Git SHA;
- Windows version;
- NVIDIA driver;
- PyTorch/CUDA build reported by the runtime;
- the exact SDXL checkpoint and LoRA set used;
- whether any other GPU-heavy application is running.

Start Morphorum normally or with `run-lan.bat`.

Before the first render, capture the new diagnostic endpoint:

```powershell
Invoke-RestMethod http://127.0.0.1:7865/api/system/gpu-memory |
  ConvertTo-Json -Depth 8
```

Expected:
- `cuda_available: true`;
- CUDA device name is the target NVIDIA GPU;
- allocator backend is reported when PyTorch exposes it;
- current/free/allocated/reserved values are present;
- on Windows, `windows_wddm` should report per-process dedicated/shared values when the performance counters are available.

The WDDM process counter is corroborating diagnostic data, not the sole definition of physical residency. Also watch Windows Task Manager → Performance → GPU dedicated/shared memory during the high-resolution runs.

## 2. B6.1 Deforum import UI gate

### 2.1 Golden 2D import

In **Animation → Import Deforum**, select:

`tests\fixtures\deforum\golden_2d.json`

If the browser is running on another LAN device, copy/download the fixture to that device first. File selection is intentionally browser-local.

Verify before choosing a model:
- preview opens without modifying the currently loaded project;
- **Create New Project** remains disabled;
- imported `model_path` is reported as ignored/passive and is never selected automatically;
- `hybrid_video_motion` is reported as unsupported/passive;
- source values and mapped Morphorum fields are visible.

Choose the same installed/indexed SDXL checkpoint used for the B5.5 control. Verify:
- name: **Deforum Golden 2D** unless manually changed;
- 24 frames, 12 fps, 768×512, 2D;
- prompt keyframes at 0 and 12;
- negative-prompt keyframes at 0 and 12;
- angle, zoom, X/Y translation schedules are present;
- strength/noise/steps/guidance are present;
- cadence schedule contains 1 at frame 0 and 3 at frame 12;
- seed 424242, increment behavior, increment 2;
- `DPM++ 2M Karras` maps to Morphorum `dpmpp_2m`.

Create the project. Confirm it gets a new project ID and does not overwrite any existing project.

Run a short render. Visual gate:
- prompt transition changes around the expected window;
- 2D motion direction looks reasonable;
- selected model is the explicit indexed SDXL model;
- no imported host model path is touched;
- no CPU fallback occurs;
- cancel/resume still behaves normally if exercised.

### 2.2 Golden 3D import

Repeat with:

`tests\fixtures\deforum\golden_3d.json`

Verify:
- 30 frames, 15 fps, 640×640, 3D;
- translation X/Y/Z, rotation X/Y/Z and FOV schedules are present;
- importer clearly warns that copied Deforum/Morphorum 3D units/signs may not be visually identical;
- `use_mask` and `mask_file` remain unsupported/passive;
- no arbitrary source mask path is opened.

Run a short render and inspect camera direction. A numerical import is not considered equivalent merely because it parsed.

### 2.3 Real legacy settings

After the golden fixtures pass, import at least one real Deforum settings file you care about.

Record:
- unsupported/unmapped keys;
- any sampler or model-family substitution;
- any camera schedule that looks reversed or scaled incorrectly;
- missing LoRAs or prompt directives;
- whether the native timeline matches the source intent.

If a mapping is uncertain, keep the warning and fix the translator from observed evidence. Do not silently invent an equivalence.

**B6.1 passes only when preview, explicit model binding, new-project persistence, timeline inspection and a short Windows SDXL render all behave correctly.**

## 3. B6.0-P native high-resolution matrix

Use the same SDXL checkpoint, prompt, seed and LoRA set for comparisons. Prefer the B5.5 three-LoRA setup because it represents the known stressful real workload.

In **Settings → Generation Behavior**:
- leave **Experimental VAE tiling** **OFF**;
- save settings;
- manually unload/reload the model after any memory-mode change.

For every row:
1. capture `/api/system/gpu-memory` before the run;
2. run the test;
3. capture the endpoint after the run;
4. for animation, save/open the frame-by-frame performance JSON;
5. watch Task Manager dedicated/shared GPU memory;
6. verify LoRA influence visually;
7. verify execution remains CUDA/native and does not silently fall back to CPU.

| Stage | Resolution | First test | Advance only if |
| --- | ---: | --- | --- |
| Control | 512×512 | single image, then short cadence-3 animation | reproduces known B5 behavior |
| Step 1 | 768×768 | single image, then 3-frame/short cadence test | no OOM, corruption, severe paging/slowdown or lost LoRA effect |
| Step 2 | 896×1152 | single image only initially | 768 remains clean and memory evidence is understandable |
| Step 3 | 1024×1024 | single image, then 3-frame/short cadence test | prior level clean; no suspicious fallback or instability |
| Later | 1216×832 / 1536×1024 | only after 1024 evidence | measured headroom/performance justifies it |
| Experimental | 1536×1536 / 2048×2048 | not part of initial acceptance | explicitly approved after lower levels |

The Animation UI will show an advisory confirmation above the physically verified 512×512 pixel count. It reports pixel-count ratio and a live memory snapshot where available. It is **not** a VRAM estimator or hard limit.

## 4. SDXL VAE tiling A/B

Only after the native baseline above is recorded:

1. enable **Settings → Generation Behavior → Experimental VAE tiling**;
2. save settings;
3. unload the current model, then reload it by starting the next generation;
4. verify the performance report/model status identifies `native-gpu+vae-tiling`;
5. repeat the exact same seed, prompt, SDXL checkpoint, LoRAs and resolution used in the native run.

Compare:
- total generation/frame time;
- current/free/allocated/reserved memory;
- allocator peak/active memory;
- allocation retries and OOM count;
- WDDM dedicated/shared process memory;
- Task Manager dedicated/shared memory;
- image dimensions and visible color/detail/seam artifacts;
- LoRA influence;
- 2D/3D/cadence behavior if testing animation.

VAE tiling stays **off by default** unless the target-machine evidence shows a worthwhile high-resolution memory benefit without unacceptable quality or performance regressions. A native success does not automatically make tiling preferable.

## 5. Stop conditions

Stop the resolution ladder at the current level if any of these occurs:
- CUDA OOM;
- Morphorum unexpectedly reports CPU execution for SDXL;
- large persistent shared-GPU-memory use or severe latency jump without a clear explanation;
- LoRA influence disappears or changes unexpectedly;
- VAE seams/color/detail corruption;
- broken 3D depth/cadence behavior;
- cancel/resume corrupts the render;
- output or manifest becomes inconsistent.

Do not jump to a higher resolution after a failed lower level. Do not add model CPU offload or sequential offload merely to make the next number render; that is a separate explicit strategy and acceptance gate.

## 6. Evidence to save

For each meaningful run record:

| Field | Record |
| --- | --- |
| Git commit | exact SHA |
| GPU / driver | model and driver |
| PyTorch / CUDA | runtime versions |
| Allocator backend | `native`, `cudaMallocAsync`, etc. |
| Model | exact SDXL checkpoint |
| LoRAs | names + weights |
| Resolution | W×H |
| Animation settings | mode, cadence, frames, depth/temporal settings |
| Memory mode | native or `native-gpu+vae-tiling` |
| Timing | image time / average diffusion anchor time |
| PyTorch memory | current + peak allocated/reserved/active |
| Windows memory | WDDM dedicated/shared + Task Manager observation |
| Output | visual pass/fail + any artifacts |
| LoRA | visual influence pass/fail |
| Resume/export | pass/fail if exercised |
| Performance report | render ID / JSON path or URL |

## 7. Checkpoint rules

- If B6.1 import UI + short-render acceptance passes, create a dedicated B6.1 verified checkpoint from the exact tested SHA.
- Do **not** move or replace the B5.5 checkpoint.
- High-resolution support should be described by the exact tested model/mode/resolution, not as a universal GPU promise.
- Start B6.2 hybrid video upload/extraction only after the B6.1 checkpoint is secured; high-resolution optimization can continue as a parallel, separately gated track.
