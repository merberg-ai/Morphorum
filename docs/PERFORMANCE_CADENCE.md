# B4 Performance, Cadence, and LoRA Correctness

B4 is the first animation performance pass after the depth-aware 3D renderer became
physically usable.

It has two acceptance gates:

1. SDXL LoRA-on and LoRA-off renders using identical generation inputs must produce a
   real image difference.
2. Stage timing on the physical RTX 4080 SUPER must identify the dominant 1024x1024
   cost and show whether the hot-loop changes reduce it.

CI can verify contracts and state handling. It cannot prove those two GPU/model-specific
facts.

## October 8 checkpoint and shared generation pipeline audit

**User-reported result:** SDXL LoRA Manager prompt insertion and visible LoRA effect
in still-image generation now appear to work after local physical testing.
This is a promising SDXL still-image acceptance report, not yet a completed
multi-family or animation acceptance gate.

A fixed snapshot of that state is preserved on GitHub:
`checkpoint/b4-sdxl-lora-working-20261008` at
`2698ed27781a72a1f36517bcb716865e822501fb`.
The active `feature/perf-cadence-lora-b4` branch remains the integration line
for Flux and Z-Image tests and any further fixes. Do not merge into main yet.

**Code path verified:** Still images call `GenerationManager._run_job()` and
then `GenerationManager.configure_loras()`. Prompt-start animation calls
`prepare_txt2img()`; all subsequent diffusion frames call
`prepare_img2img()`; both methods use the same
`GenerationManager.configure_loras()` with the resolved per-frame adapters.
Family-specific pipelines are handled by the same loader, not by an
animation-specific LoRA implementation.

**Handoff bug fixed after snapshot:** Conversion from txt2img to img2img can
retain active PEFT layers on the new pipeline wrapper. Clearing the internal
LoRA activation signature alone did not deactivate those layers when the
next frame requested no LoRA. B4 now explicitly calls `disable_lora()`
on the converted wrapper before reapplying any new per-frame adapter state,
and fails explicitly if a previously active LoRA cannot be disabled.
Tests exercise reweighting, disabling, re-enabling, and no-adapter handoff
for all three model families without a GPU. The independent saved checkpoint
remains unchanged.

**Physical tests still needed:** SDXL short animations with prompt-start and
source-start modes; Flux LoRA still-image A/B/C effect; Z-Image LoRA still-image
A/B/C effect; adapter state and effectiveness across real task conversions;
LoRA keyframe scheduling and cleanup. Static CI tests verify integration
control flow but cannot prove real-world pixel effect.

## Flux FP8 / PEFT LoRA failure and compatibility mode (Oct 8)

**Physical bug report:** `artsyDream_v6FP8.safetensors` (Flux Dev) generated
successfully without an adapter. Adding
`Flux_Unsettling_Horror_Style_v1.1_898175.safetensors` produced successful
Diffusers `load_lora_weights()` and active-adapter logs, followed by
`"addmm_cuda" not implemented for 'Float8_e4m3fn'` at inference.

This is a **Flux layerwise FP8 storage / PEFT wrapper compatibility failure**,
not evidence that the LoRA file targets the wrong model. The manager should
still check Civitai/sidecar base-model metadata for Flux Dev versus Schnell
and the model's actual architecture.

The B4 implementation now deliberately separates Flux execution modes:

- **No LoRA requested:** retain the optimized FP8 layerwise storage with BF16
  compute and streamed group offload on supported NVIDIA hardware.
- **LoRA requested (from Image or animation):** load the original checkpoint
  with BF16/FP16 transformer storage, *without* layerwise FP8 casting.
  Streamed group offloading stays enabled for VRAM control.
- **LoRA added to already-loaded FP8 Flux base pipeline:** release the FP8
  pipeline and reload the same checkpoint with original higher-precision
  weights before calling `load_lora_weights()`. Merely calling
  `.to(torch.bfloat16)` on an already-cast FP8 pipeline is not a safe
  recovery strategy.
- **Animation task conversions:** `prepare_txt2img()` and
  `prepare_img2img()` use the same model-specific precision gate and shared
  `configure_loras()`; compatible BF16-loaded Flux pipelines are reused
  across frames, reweights and disable/re-enable transitions.

LoRA mode may use more **system RAM** and take longer to initialize than
the FP8 base mode. Group offloading limits VRAM use, but real GPU testing
is still required on the 16 GB RTX 4080 SUPER.

The regression suite covers FP8/LoRA gating, switching an existing cached FP8
pipeline for both txt2img and img2img, and reusing both the no-LoRA FP8
pipeline and the BF16 LoRA pipeline.

**Physical retest:** restart Morphorum after updating B4, select
`artsyDream_v6FP8`, keep all generation parameters and seed identical,
and run A (base), B (Flux style LoRA weight 1.0), C (base). The transition
from A to B should log a BF16 compatibility reload, followed by adapter
activation. B should change the image versus A if the LoRA is effective;
C must disable the adapter and restore base behavior. Compare B and C
for the cleanest evidence of LoRA influence because both use the same warm
BF16 transformer. A was likely produced using FP8 weight storage, so A/C
need not be pixel-identical due solely to the change in numerical precision.
Comparing output otherwise requires matching sampler, steps, guidance,
resolution, seed, and prompt text after stripping `<lora:...>` directives.
A base image generated after a LoRA may continue using the warm BF16
pipeline until unloaded.

**Still not accepted:** Flux LoRA pixel influence and performance on real
hardware are not verified by CI. The successful SDXL known-working checkpoint
`checkpoint/b4-sdxl-lora-working-20261008` is unchanged.

## B4 priority gate: LoRAs before further 3D development

After physical testing of `ChalkDustStyleSDXL`, LoRA registration and
nonzero injected parameters were verified, but a convincing visual A/B difference
was not observed. The LoRA-on and LoRA-off samples must be compared with an
**identical sampler and every other generation setting**. Prior console
captures included both `dpmpp_2m_sde` and `dpmpp_2m`, which confounds
some comparisons.

The LoRA Manager introduced on B4 provides metadata inspection, safe local
Civitai sidecar reading, exact SHA-256 Civitai lookup, and live adapter status.
Its presence does **not** constitute LoRA inference acceptance.

Do not resume new 3D renderer features until physical tests establish:
- visible same-seed SDXL LoRA-on/off effects and correct restoration;
- verified Flux and Z-Image LoRA impact with compatible real checkpoints;
- correct reweight, disable, and img2img/task-switch behavior;
- animated/keyframed LoRA application without adapter leakage.

This is a release gate and not a prohibition on bug fixes to existing 3D code.

## SDXL LoRA correctness

### Why the old verification was insufficient

Some community SDXL LoRAs trigger a Diffusers/PEFT failure while the pipeline loader is
processing text-encoder weights. The failed load can leave an adapter name registered on
the UNet.

An adapter name appearing in the PEFT registry, or even in the active-adapter list, does
not prove that a complete useful LoRA payload was injected.

B4 no longer accepts that state as success.

### Clean UNet-only recovery

When the known SDXL loader IndexError occurs, Morphorum now:

1. asks Diffusers to parse/convert the original LoRA state dict using the live
   SDXL UNet configuration (required to map Kohya/SGM block indices correctly),
2. separates UNet state from text-encoder state,
3. deletes the partially-created adapter from pipeline components,
4. injects the converted state directly through Diffusers' UNet LoRA loader,
5. audits the resulting PEFT payload,
6. only then allows adapter activation.

The text-encoder portion is skipped only on this compatibility path.

#### B4 SDXL SGM remapping correction

Physical test of `ChalkDustStyleSDXL` on `colossusSdxl_v10` showed that the
initial B4 compatibility path called `lora_state_dict()` without
`unet_config`. For Kohya/SGM checkpoints, this incorrectly interpreted
input/output block IDs as Diffusers block IDs, producing missing UNet targets
such as `down_blocks.7.1`. The fallback now passes the loaded UNet config and
requests LoRA metadata, matching Diffusers 0.40.0's native SDXL loader.
The test suite includes a real SGM-format state-dict conversion regression.
This fix still needs the physical A/B gate below; CI alone does not prove image
appearance.

### Payload audit

For SDXL, the loaded UNet adapter is inspected for:

- injected LoRA parameter tensors,
- total LoRA parameter count,
- absolute weight sum,
- adapter module presence when exposed by PEFT.

A registered adapter with no nonzero injected payload is rejected.

The runtime console reports the audit for compatibility-loaded SDXL LoRAs.

Strict payload rejection is intentionally SDXL-only in B4. Flux and Z-Image keep their
existing adapter path until they receive separate physical acceptance.

### Conditioning cache isolation

Prompt conditioning caches now include the active LoRA signature.

Changing an adapter or its weight therefore invalidates/re-separates cached SDXL, Flux,
and Z-Image prompt conditioning. A base-model prompt embedding cannot be reused as the
LoRA-on embedding merely because the prompt text matches.

## CUDA hot-loop behavior

The old animation path aggressively called Python garbage collection and CUDA allocator
cleanup around every frame. That is appropriate on model unload or OOM recovery, but
counterproductive for a persistent animation pipeline.

B4 separates memory handling into:

- aggressive cleanup for model/task transitions, unloads, failures, and OOM recovery,
- lightweight hot-loop maintenance after each animation frame.

Hot-loop maintenance normally does nothing. It calls `torch.cuda.empty_cache()` only
when both conditions are true:

- free VRAM is below the low-memory threshold,
- there is a meaningful amount of reclaimable reserved-but-unallocated CUDA cache.

It does not perform a per-frame `gc.collect()` or `cuda.synchronize()`.

## Performance telemetry

Each completed animation frame records live timing for:

- schedule/frame resolve,
- depth estimation,
- camera/affine warp,
- scheduled noise,
- pipeline preparation,
- prompt conditioning,
- diffusion,
- PNG save,
- render-manifest checkpoint,
- memory maintenance,
- total frame time.

The UI summarizes the most useful stages in the render-state panel, while the Morphorum
console prints the detailed timing line.

This is intentionally diagnostic. A 1024x1024 physical run should tell us whether time is
actually spent in diffusion, conditioning, VAE work hidden inside the pipeline call,
disk I/O, or allocator maintenance instead of making us guess.

## 3D depth resolution

3D Camera now exposes an internal **Depth resolution** setting:

- Auto
- 384
- 512
- 768
- Full

Auto caps the depth-estimation image at a 512-pixel maximum dimension while preserving
aspect ratio. Smaller render sizes are not enlarged.

The normalized float32 depth map is bilinearly resized back to render resolution before
3D projection.

This does not reduce the final animation resolution and does not resize the diffusion
input. It only reduces the monocular-depth inference cost and cache size.

Live depth telemetry includes the internal depth resolution actually used.

## Frame output

Animation PNG frames remain lossless.

B4 uses PNG compression level 1 with optimization disabled. The files may be larger than
the old defaults, but frame writing requires less CPU time. This is a render-cache format,
not the final distribution format.

## Diffusion cadence

B4 activates the canonical `cadence.diffusion` timeline track.

The schedule is an integer from 1 through 64.

### Cadence 1

```text
0:(1)
```

Every eligible frame receives the normal camera transform, scheduled noise, and img2img
diffusion. This is the pre-B4 behavior.

### Cadence N

For cadence greater than 1, frame numbering is global:

```text
anchor when frame % cadence == 0
```

The final animation frame is always forced to be an anchor.

An intermediate cadence frame:

- still resolves its exact prompt/camera/generation schedules,
- still applies its 2D or depth-aware 3D camera transform,
- does not inject scheduled noise,
- does not run img2img diffusion,
- is saved as the next frame,
- reports `cadence-transform` in render telemetry.

An anchor frame performs the normal transform + noise + diffusion path.

Because anchors use absolute frame numbers, interrupted renders preserve cadence phase
when resumed.

### Important scope

This is the first useful Deforum-style diffusion-cadence implementation, not the final
Deforum turbo algorithm.

B4 carries transformed intermediate frames forward from the previous generated state.
It does not yet generate a future anchor and interpolate/tween optical state between two
diffused anchors.

That richer anchor interpolation can be added after physical performance and temporal
quality are measured.

## Suggested physical acceptance

### A. SDXL LoRA still-image gate

Use one of the SDXL LoRAs that previously showed no effect.

Keep identical:

- checkpoint,
- positive and negative prompts,
- seed,
- dimensions,
- steps,
- sampler,
- guidance.

Render A with no LoRA.

Render B with the LoRA at weight 1.0.

The B console should either show a normal successful SDXL payload or the compatibility
message followed by a nonzero payload audit.

The two output images must differ. Registry/active-adapter messages alone are not
acceptance.

### B. SDXL LoRA animation gate

After still generation passes, repeat a short 2D or 3D animation with a constant LoRA
weight. Verify the img2img pipeline also reports a real attached payload and the effect
persists after the txt2img/img2img task conversion.

### C. 1024 performance baseline

Run a short 1024x1024 animation with:

```text
Cadence:         0:(1)
Depth resolution: Auto
```

Compare the new stage timing with the earlier physical result where 1024 SDXL frames
took roughly a minute or more while CPU depth stayed near one second.

The key number is the new `diff` timing.

### D. Cadence speed test

Repeat the same project with:

```text
Cadence: 0:(2)
```

The console/UI should alternate transform frames and diffusion anchors.

For a sufficiently long render, cadence 2 should substantially reduce total diffusion
work. Exact wall-clock speedup will be less than 2x because transforms, depth, saving,
and checkpointing still occur.

Then try cadence 3 only after cadence 2 behaves correctly.

## Physical-test stop condition

Do not merge B4 solely because CI is green.

B4 requires:

- visible deterministic SDXL LoRA effect,
- LoRA-off restoration of the base result,
- successful img2img/animation LoRA continuation,
- useful 1024 stage timings,
- no 2D/3D regression at cadence 1,
- correct anchor/transform behavior at cadence 2,
- acceptable visual coherence for the initial cadence implementation.
