# SDXL LoRA text-encoder compatibility investigation

**Date:** 2026-10-09  
**Baseline:** `checkpoint/sdxl-fp16-animation-gpu-verified-20261009`, commit `d22b385b4bf9ff67dd5d3419a6e6dfe1e009e8e1`  
**Status:** Root-cause hypothesis strongly corroborated by upstream source/issues; no renderer changes in this investigation. Needs Windows/RTX 4080 SUPER physical validation before accepted.

## User-observed problem

The GPU-validated SDXL animation run `anim-20261009-065914-994eaa` succeeds and stays memory-stable following the FP16 task-conversion fix. During LoRA loading, each of these examples triggers:

- `DonM0v3rC4ff31n4t3dXL.safetensors`
- `DonM5h0wM3XL.safetensors`
- `ChalkDustStyleSDXL.safetensors`

The console reports `SDXL LoRA ... hit the Diffusers/PEFT text-encoder rank compatibility bug`, followed by a verified **UNet-only** adapter with 722 injected modules, 1444 parameter tensors, 85,114,880 parameters and **528 text-encoder tensors skipped** per reported LoRA. Adapter registration, reweighting and 90-frame generation work. This proves the UNet component is attached, not that the text-encoder weights are being used. The LoRA's full trained behavior is therefore not guaranteed, especially for prompt/trigger learning.

## Morphorum source findings

- `pyproject.toml`: `diffusers==0.40.0`, `transformers>=5,<6`, `peft>=0.17,<1`. These constraints put Morphorum in the same Transformers 5 family as upstream reports. Confirm exact installed runtime versions in Windows before editing dependencies.
- `backend/morphorum/generation.py`, `configure_loras()` (~2170-2239): first calls `pipe.load_lora_weights(...)`; on **IndexError** with SDXL `.safetensors`, calls `_load_sdxl_unet_only_adapter()`.
- `_load_sdxl_unet_only_adapter()` (~1991-2089): calls `pipe.lora_state_dict(..., unet_config=..., return_lora_metadata=True)` to correctly remap Kohya/SGM blocks; deliberately removes keys beginning `text_encoder.` or `text_encoder_2.`; clears partially loaded adapters and loads only UNet tensors. Keeps network alphas relevant to UNet and verifies nonzero injection.
- `tests/test_generation.py`: `FakeSDXLRankBugPipe`, `test_sdxl_rank_bug_retries_with_unet_only_state_dict`, `test_sdxl_rank_bug_accepts_already_loaded_unet_adapter`, and a synthetic mixed SDXL safetensors fixture specifically document and protect the current fallback. The fixture contains `lora_te1_text_model_...` and `lora_te2_text_model_...` keys.

## Upstream mechanism

**Source, Diffusers 0.40.0:** `src/diffusers/loaders/lora_base.py::_load_lora_into_text_encoder` (~307-380). After converting the TE weights into PEFT format, Diffusers iterates `text_encoder.named_modules()`, constructs `f"{name}.lora_B.weight"` for supported linear layers, and collects a `rank` dictionary **only for exact matches in the converted state dict**. It passes `rank` to `_create_lora_config`.

`src/diffusers/utils/peft_utils.py::get_peft_kwargs` (~140-146) then uses `list(rank_dict.values())[0]` without checking for emptiness. If a checkpoint names `text_model.encoder.layers...` but the installed Transformers model exposes `encoder.layers...`, the match set is empty and the observed `IndexError: list index out of range` follows.

**Upstream corroboration:** [huggingface/peft#3238](https://github.com/huggingface/peft/issues/3238) explicitly reports an **SDXL** LoRA producing that exception with Transformers 5.8, and includes example `encoder...` UNEXPECTED vs `text_model.encoder...` MISSING diagnostics. [huggingface/diffusers#13984](https://github.com/huggingface/diffusers/issues/13984) isolates the prefix mismatch in **Flux** CLIP text-encoder LoRAs and shows the same Diffusers rank-building path. These reports are related evidence, **not proof** that all three local Morphorum files have identical key collisions, because neither the full runtime traceback nor the user's actual safetensors tensors were directly inspected.

Sources:
- https://raw.githubusercontent.com/huggingface/diffusers/v0.40.0/src/diffusers/loaders/lora_base.py
- https://raw.githubusercontent.com/huggingface/diffusers/v0.40.0/src/diffusers/utils/peft_utils.py
- https://raw.githubusercontent.com/huggingface/diffusers/v0.40.0/src/diffusers/loaders/lora_pipeline.py

## Recommended isolated repair

1. **Do not downgrade Transformers globally or remove the UNet-only safety fallback** until other families (Flux, Z-Image) and dependency compatibility have been checked. Do not install an untested new Diffusers or PEFT version on the known-good runtime.
2. Add a narrow SDXL diagnostic in an isolated work branch: for each text encoder, inspect module-name samples and the parsed `lora_state_dict` key prefixes and **count exact PEFT post-conversion matches**. Do not log tensor values or write large tensors to console. Capture original exception type and stack location. Never infer installed version solely from `pyproject.toml`.
3. In the fix path only when mismatches are actually detected, reconcile the TE keys **per text encoder** with its actual `named_modules()` namespace. In particular, remove stale `text_model.` only for encoders lacking that wrapper, not indiscriminately for `text_encoder_2` or UNet. Preserve network alpha mappings and per-layer ranks, optional metadata, and Kohya/SGM UNet remapping. Avoid globally monkey-patching Transformers, Diffusers or all LoRA loaders.
4. Clean up any partially attached adapters before retry, to prevent duplicate PEFT layers. Load UNet and each available TE adapter, verify **nonzero tensors in every component that has source TE weights**, confirm active adapters, and keep proper weight scheduling at runtime.
5. If full loading still fails, preserve today's verified UNet-only fallback **with an honest warning**; do not claim full loading or hide skipped tensors. Prefer a per-LoRA status `full` versus `unet-only` with source components/counts.
6. Test synthetic formats: Kohya SDXL with `lora_te1` and `lora_te2`, native Diffusers PEFT keys, UNet-only LoRAs, wrapped/unwrapped encoder models, nonuniform ranks and alphas, partial failure cleanup, multi-LoRA weight scheduling, txt2img→img2img reuse, with/without VAE tiling. Never regress the dtype-preserving FP16 conversion.
7. Physical test on Windows: two LoRAs from user's set, same seed/prompt/model, **A/B images with and without full TE weights**; compare behavior and quality. Run a short cadence-4 animation, verify per-frame LoRA weights, stable ~7 GiB CUDA allocation (plus TE injection overhead), no slow anchors, no fallbacks, and 90-frame run only after short render passes.

**Safe immediate outcome:** The known-good FP16 checkpoint remains untouched; investigation can proceed on `dev-ui` or a separate `fix/sdxl-lora-text-encoder` branch after diagnostics establish the exact offending keys.
