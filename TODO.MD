# Morphorum TODO

Deferred investigations and improvements. These entries are **not** release blockers unless a later test demonstrates a functional failure.

## Z-Image Turbo LoRA stability and animation coherence (reported 2026-10-19)

**Status:** ZL1 candidate fix on `dev-webui` awaiting physical Windows GPU verification; ZT1 remains open and untouched. A CPU-only PyTorch reproduction verified the inference-tensor failure mechanism, but this does **not** prove the production Z-Image failure has been resolved. **Priority:** ZL1 correctness first; ZT1 quality second.

### ZL1: Managed Z-Image + LoRA inference stability (bug)

**Observed:** Managed Z-Image Turbo animation completes when the `<lora:Horror Style ZIT:1>` directive is removed from an otherwise unchanged prompt, but fails after a few generated frames when that LoRA is active. The same error has also occurred intermittently during single-image generation with a LoRA:

```text
Setting requires_grad=True on inference tensor outside InferenceMode is not allowed.
```

**Candidate fix (2026-10-20):** Keep managed Z-Image group offloading, but run its still-image, animation-anchor, and blended-prompt conditioning calls under `torch.no_grad()` instead of `torch.inference_mode()`. When Diffusers offload replaces PEFT `Parameter.data` during inference mode, a later adapter `requires_grad_(True)` operation can raise exactly the reported error. SDXL and FLUX retain their previous inference contexts. Lightweight CPU regression tests cover parameter mutability and Z-Image prompt conditioning; GPU confirmation is outstanding.

**Investigation / proposed work:**
- Reproduce with single-image generations/batches and animation, with/without LoRA. Collect full Python tracebacks and record the exact stage (LoRA load, adapter enable/weight update, task conversion, prompt encoding, offload transfer, or inference).
- Audit `backend/morphorum/generation.py` shared `configure_loras()`, model reuse and txt2img/img2img conversion, and `backend/morphorum/animation_render.py` inference and conditioning contexts. The single-image failure means the task switch cannot be the only suspect.
- On 16 GB GPUs, inspect PEFT adapter parameter lifecycle with Diffusers Z-Image BF16 group offloading and `torch.inference_mode()`. Confirm the cause before changing behavior; evaluate `torch.no_grad()` selectively where inference tensors might later undergo parameter/adapter operations.
- Ensure loaded adapter identity, weight, enabled state and valid tensors survive subsequent generations and task changes without stale adapters or unintended LoRA effects. Preserve memory-safe offloading: do not solve by forcing the managed Z-Image model entirely into 16 GB VRAM.
- Add regression coverage for repeated Z-Image single-image/batch generations, txt2img-to-img2img animation, LoRA enable/disable/reweight, and generation without LoRA; run automated tests and Windows GPU physical verification.
- Keep SDXL, FLUX, managed model installation and existing project behavior unchanged unless a separately tested shared fix is necessary.

**Acceptance:** Same settings complete several consecutive single-image generations and a multi-anchor animation with the Z-Image LoRA; without-LoRA baseline still succeeds; no inference tensor exception, stale adapter influence, or new CUDA out-of-memory regression.

### ZT1: Z-Image animation temporal coherence (quality improvement)

**Observed:** Managed Z-Image animation renders successfully without LoRA but can look like a sequence of substantially reimagined stills instead of the smoother frame-to-frame progression seen with SDXL. This is a subjective quality report, not yet a proven renderer defect.

**Investigation / proposed work:**
- Inspect per-frame img2img handoff, transformed frame feedback, fixed/incremented seeds, added pixel noise, cadence, step count, and prompt/LoRA transitions. Compare short renders with controlled settings and identical camera motion.
- Explicitly expose/document Morphorum's **retention** Strength convention: Diffusers `img2img strength = 1 - Morphorum retention strength`. Higher Morphorum Strength retains more of the preceding frame.
- Establish an empirical Z-Image Turbo baseline: try retention Strength `0.75` (denoise `0.25`), 9 steps, guidance 0, noise 0, cadence 1, fixed seed; compare to retention `0.65` and other values. These are *test settings*, not validated defaults. Check effective step counts at low denoise strengths.
- Investigate model-aware Smooth / Balanced / Creative animation presets and appropriate Z-Image-specific defaults. Apply only to newly chosen presets/new projects; never silently overwrite saved projects or other model-family settings.
- Consider bounded per-frame visual-change diagnostics; evaluate motion-aware temporal methods (including optional optical-flow interpolation or depth-aligned blending) only if strength/noise/step tuning does not provide acceptable continuity.
- Compare visual continuity, subject identity, motion smoothness, output detail, and render time against SDXL on the same short animation; retain existing SDXL/FLUX paths.

**Acceptance:** A short Z-Image test animation shows visibly steadier frame-to-frame subject/scene continuity without collapsing motion or detail; settings are explicit, reproducible, and documented. Complete ZL1 before reintroducing LoRAs to these quality tests.

## SDXL LoRA diagnostics and console warnings (deferred, 2026-10-18)

**Status:** Current SDXL single-image generation appears to work. Investigate later; do not suppress warnings without understanding them. Findings came from a Windows console capture plus the Image section's SDXL LoRA verification card on `dev-webui`.

- **Adapter teardown warnings:** PEFT warns that an active `morphorum_…` adapter was deleted and automatically switches to another adapter. Inspect the cleanup/retry path, ensure no unintended active-adapter switching or stale LoRA effects, and consider lower-noise diagnostics only after proving correctness.
- **Transformers CLIP `MISSING` load reports:** Large reports include adapter parameters newly initialized during intermediate loading/retries. The later checkpoint comparison verified the CLIP weights for five adapters, so do not equate intermediate reports with a final loading failure. Confirm expected loader behavior and whether any unexpected key initialization survives in final active adapters.
- **Unmatched `alpha_pattern` keys:** PEFT says several `*.processor.to_*_lora.down.weight` entries do not match target modules and are ignored. Trace the source checkpoint(s), key conversion, and per-module network alpha handling. Determine whether the effective UNet scaling differs from the source and add precise warnings/tests if necessary.
- **Unverified LoRA:** `BloodPunkAIp` at strength `0.400` reports **Active; source weight comparison unavailable**. Determine whether it uses the normal load path, UNet-only structure, or unsupported source comparison; improve verification honestly without relabeling as verified.
- **Long SDXL prompt:** Transformers warned about `121 > 77` CLIP tokens. Check whether Morphorum's chunked prompt conditioning handled the actual render, and confirm that the warning is not hiding truncation or indexing errors.
- **Zero-strength LoRA:** `ral-melting-sdxl_217057` was verified as loaded at strength `0.000`; exclude it from claims about visible stylistic contribution even if listed as active.

### Physical verification snapshot

| LoRA | CLIP result | Strength |
| --- | --- | ---: |
| DonM1ns0mn14XL | CLIP-L 144/144, CLIP-G 384/384 matched | 0.600 |
| DonMCr33pyD0115XL_529922 | CLIP-L 144/144, CLIP-G 384/384 matched | 0.200 |
| aidmaPsychadelicChaosWorldMorphXL-V0.1 | CLIP-L 144/144, CLIP-G 384/384 matched | 0.600 |
| BloodPunkAIp | Active; source comparison unavailable | 0.400 |
| zkeleton-sdxl | CLIP-L 144/144, CLIP-G 384/384 matched | 0.200 |
| ral-melting-sdxl_217057 | CLIP-L 144/144, CLIP-G 384/384 matched | 0.000 |

**Proposed later work:** An isolated `G5.6` diagnostics milestone with source-aligned alpha/key checks and actionable summaries. Keep actual inference, verified-LoRA behavior, and managed Z-Image unchanged. Run tests on `dev-webui` before any future merge.

## Project Editor prompt/keyframe UX

Next discussion topic: review prompt entry, keyframe editing, scheduling, and navigation workflows before defining implementation milestones. No design or changes have been approved yet.
