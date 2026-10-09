# SDXL Animation VRAM Investigation: October 9, 2026

## Supplied benchmark, conclusions

Source: an uploaded `performance.jsonl` for `anim-20261009-053729-80d5a0` (23 completed animation-frame records, frame 1–23). Its settings include an SDXL model, two active LoRAs, 3D depth estimation on CPU, cadence 4, and SDXL VAE tiling enabled. **The depth log reporting 512×512 is the estimator's input size, not proof of animation output resolution.**

- Before the first img2img anchor (frame 4): PyTorch CUDA allocation **6.8921 GiB**, CUDA reserved **7.2285 GiB**, free **7.4229 GiB** after transient cache reclamation.
- Directly after preparing first img2img anchor: PyTorch allocation **13.7643 GiB**, reserved **14.0781 GiB**, free **0.0791 GiB**. The **6.8722 GiB jump** happens during prepare, *before the separately timed conditioning and diffusion calls*.
- Allocation remains approximately **13.7648 GiB** from frames 4 through 23, ruling out steady frame-over-frame PyTorch allocation growth within this capture.
- The five diffusion-anchor durations are ~36.516, 36.609, 36.546, 68.454, and 49.750 seconds at frames 4, 8, 12, 16, 20. Cadence transform-only frames typically take ~0.3–0.8 seconds.
- The CUDA allocator records **0 allocation retries** and **0 OOMs** in all 23 records.
- Peak tracked PyTorch allocated **17.5208 GiB**, peak reserved **21.625 GiB**. CUDA reports physical total ~15.9917 GiB. These statistics are evidence of severe memory pressure/possible Windows GPU-memory oversubscription. They are process high-water marks, not proof of physical paging. Additional diagnostics are needed.
- Depth estimation ~0.4–0.5 seconds per uncached frame on CPU is not the dominant diffusion bottleneck; VAE tiling only affects encoding/decoding, not large UNet/attention allocations.

## Instrumentation added to dev-ui

A one-time read-only SDXL task transition profile now captures:

1. **before_conversion**, prior to `StableDiffusionXLImg2ImgPipeline.from_pipe()`.
2. **after_from_pipe**, plus whether UNet, VAE and both text encoders are the exact same component objects across the two wrappers.
3. **after_release**, after old wrapper is discarded and transient cache cleanup.
4. **after_sampler**, after scheduler selection.
5. **after_lora_setup**, after requested LoRAs are reactivated.

Each phase records allocated/reserved/free GiB and CUDA allocation-retry/OOM counters, and is emitted as a **single Console log line**. The same profile is embedded into new diffusion-anchor entries in `performance.jsonl`. No GPU-device movement, model mutation, performance optimization, rendering defaults, or periodic per-frame diagnostic sampling was added. The model API also exposes the last read-only profile.

## Next physical test

1. On Windows update `dev-ui` with `git pull --ff-only` and `.\update.bat`, then restart Morphorum.
2. Clone the previous animation configuration and **do not change output resolution**, sampler, LoRAs, or tiling. Reduce to **13 frames** (starting frame plus anchors 4, 8, 12) and run once.
3. Copy the Console line beginning **SDXL task transition CUDA allocations:** and attach the new `performance.jsonl`.
4. The critical result is where the 6.87 GiB jump appears: `after_from_pipe` suggests duplicated or unexpectedly resident model components, especially if `unet=separate`; `after_lora_setup` suggests adapter-loading or activation; `after_release` and `after_sampler` localize other mechanisms. These are hypotheses until verified on the RTX 4080 SUPER.
5. After that diagnostic run, perform an A/B run **with both LoRAs disabled** at the same output resolution and sampler. Compare allocated/peak VRAM, anchor duration, and final appearance before considering any optional memory optimization.
6. Keep the B6 and existing UI checkpoint branches untouched until a concrete improvement passes CUDA physical testing. Do not enable CPU offload or attention slicing blindly: both can reduce speed.

### Success criterion for an optimization

Demonstrate a lower steady and peak PyTorch allocation or lower anchor times, with image quality and LoRA influence preserved; repeat the same 13-frame test to exclude transient WDDM scheduling artifacts.


## October 9 follow-up: root cause found and corrected on dev-ui

The second uploaded `performance.jsonl` (render `anim-20261009-060611-15b17a`, 89 post-start frame records) contains the new one-time `sdxl_transition_profile`. It shows:

| Stage | Allocated GiB |
|---|---:|
| before_conversion | 6.8921 |
| after_from_pipe | 13.7646 |
| after_release | 13.7646 |
| after_sampler | 13.7643 |
| after_lora_setup | 13.7643 |

Both pipeline wrappers identify the exact same UNet, VAE and two text encoder objects as shared. Subsequent memory does not keep doubling. Across this longer run, 23 diffusion anchors average ~28.82 seconds at frames 4–16, ~54.04 seconds at frames 20–28, and ~70.55 seconds from frames 32–89. A third LoRA enters at frame 32, adding about 0.34 GiB live memory, but frame 20 was already slow. Peak PyTorch allocated reached 17.8612 GiB, peak reserved reached 21.877 GiB, and zero allocator retries/OOMs were recorded. This is a severe memory-pressure pattern, not proof of physical shared-memory paging.

**Verified upstream cause:** Morphorum pinned Diffusers `0.40.0`. In `DiffusionPipeline.from_pipe()`, the source at `v0.40.0/src/diffusers/pipelines/pipeline_utils.py` defaults to `torch.float32` when neither `dtype` nor `torch_dtype` is supplied, and calls `new_pipeline.to(dtype=dtype)`. Morphorum previously called `StableDiffusionXLImg2ImgPipeline.from_pipe(pipe)` without explicit dtype. Since the wrappers share components, that **upcast the existing FP16 weights to FP32** on the first task switch. This exactly accounts for the near-2× live-memory increase and likely causes Windows WDDM memory pressure and erratic diffusion performance.

**Fix:** `GenerationManager._convert_pipeline_task` now passes the existing SDXL UNet `dtype` to `from_pipe()` for both directions of SDXL task conversion, rejecting a missing dtype instead of silently defaulting to FP32. Flux and Z-Image conversion code is unchanged. Two regression checks cover source FP16/FP32 precision and the missing-dtype guard. No generation scheduling, LoRA activation, image pixels or depth processing code was intentionally changed.

### Acceptance test after applying the fix

1. Update `dev-ui`, restart the runtime (a browser refresh alone does not reload Python), and **unload/reload SDXL** before the test.
2. Repeat **13 frames at the same actual project output resolution used in the earlier benchmark** (verify Width/Height in the project or render manifest; the 512×512 depth log only reports depth-estimator input), with the same sampler, two LoRAs, cadence 4, and unchanged VAE tiling.
3. In Console and `performance.jsonl`, check that `before_conversion` and `after_from_pipe` allocated GiB are nearly identical, with UNet/VAE/encoders shared and both model precisions still FP16.
4. Compare anchor diffusion times with the old **~29–37 second** values, noting other GPU activity. Peak allocated/reserved should remain significantly lower and available VRAM should increase substantially.
5. If step 3 succeeds, repeat at **1024×1024** using the same controlled setup; treat runtime and image quality as physical acceptance criteria. Benchmark with and without the additional third LoRA only after the core precision issue is resolved.
6. Keep the prior UI and B6 checkpoints untouched until results are verified. If unexpectedly no memory benefit, inspect live tensor dtype and keep the precise five-stage profiler enabled.

Source: https://raw.githubusercontent.com/huggingface/diffusers/v0.40.0/src/diffusers/pipelines/pipeline_utils.py (`from_pipe`, default dtype and `new_pipeline.to`).
