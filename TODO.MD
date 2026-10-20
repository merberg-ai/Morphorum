# Morphorum TODO

Deferred investigations and improvements. These entries are **not** release blockers unless a later test demonstrates a functional failure.

## Z-Image Turbo LoRA stability and animation coherence (reported 2026-10-19)

**Status:** **ZL1 passed / resolved on `dev-webui`** (user physical Windows GPU verification reported 2026-10-20): repeated managed Z-Image single-image generations with and without LoRAs, plus a Z-Image animation, no longer raise the inference-tensor exception. **ZT1 remains open** for animation temporal coherence and has not been modified. No merge to `main` yet.

### ZL1: Managed Z-Image + LoRA inference stability (bug)

**Observed:** Managed Z-Image Turbo animation completes when the `<lora:Horror Style ZIT:1>` directive is removed from an otherwise unchanged prompt, but fails after a few generated frames when that LoRA is active. The same error has also occurred intermittently during single-image generation with a LoRA:

```text
Setting requires_grad=True on inference tensor outside InferenceMode is not allowed.
```

**Fix and verification (2026-10-20):** Managed Z-Image keeps group offloading, but its still-image inference, animation-anchor inference, and blended prompt encoding use `torch.no_grad()` instead of `torch.inference_mode()`. The inferred failure mechanism is that Diffusers offloading can create inference tensors in PEFT adapter parameters, conflicting with a later `requires_grad_(True)` operation. SDXL and FLUX retain their previous inference contexts. CPU regression coverage exercises repeated adapter activation/disable/reweight cycles and blended Z-Image conditioning. GitHub Actions backend tests passed (run 39421028500, commit e0c88ee). User verified on physical Windows GPU: multiple managed Z-Image generations both with and without LoRAs, and an animation, without recurrence of the reported error.

**Acceptance:** **Passed by user report** for repeated physical Windows GPU still-image generation with and without LoRAs, and an animation without recurrence of the reported error. Automated CPU tests passed. The exact animation length, number of diffusion anchors, and LoRA scheduling variations were not separately recorded, so this is not a claim of exhaustive coverage. Keep the regression tests in place and reopen if the exception recurs.

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
