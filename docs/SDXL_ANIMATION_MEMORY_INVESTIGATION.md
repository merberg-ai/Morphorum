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
