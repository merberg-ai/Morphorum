# Morphorum TODO

Deferred investigations and improvements. These entries are **not** release blockers unless a later test demonstrates a functional failure.

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
