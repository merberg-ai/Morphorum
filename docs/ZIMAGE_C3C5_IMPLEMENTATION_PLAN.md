# Z2.20c3c5: first tiny standalone diagnostic PNG, implementation plan

**Plan approved for documentation/checkpoint only, 2026-10-18. No implementation or generation has been performed.**

**Baseline:** `dev-webui`, Z2.20c3c4 Windows acceptance PASS. The existing `backend/morphorum/zimage_vae_decode_probe.py` yields a finite CPU float32 RGB tensor of shape `[1,3,32,32]` after two native-caption scheduler updates with a zero-initialized latent. Converted external BF16 scratch encoder/transformer, managed tokenizer/scheduler/VAE, and all original weights remain unchanged. `main` must not be modified.

## Objective and non-goals

Create **exactly one explicitly authorized, 32×32 diagnostic PNG** from the c3c4 decoder output in a user-selected isolated output directory. Record verifiable output metadata while keeping normal Z-Image model loading disabled. This is **not proof of faithful image generation**: the present integration uses a zero initial latent, two steps, and a tiny spatial extent. The resulting picture may be solid, noise-like or meaningless.

Out of scope: replacing managed Z-Image, enabling standalone selection in the app UI, altering Civitai paths, changing managed checkpoints, normal batch render, video/animation, CUDA model offload automation, arbitrary prompt injection, full resolution, inference benchmarking, and merges to `main`.

## Files to add or change

1. New `backend/morphorum/zimage_png_smoke_probe.py`: the experiment entrypoint and simple `main(argv=None)`. Reuse existing c3c4 computational sequence, preferably through a small extracted **private** helper that returns the verified CPU decoder tensor without ever writing it. Keep the existing c3c4 CLI output and acceptance behavior unchanged. Avoid copy-pasting a third full ~12 GiB inference loader if possible; any refactor must retain c3c4 JSON and tests.
2. New `backend/morphorum/zimage_png_postprocess.py`: pure function, e.g. `rgb_tensor_to_png_bytes(decoded: torch.Tensor) -> (bytes, metadata)`, with no filesystem, model, CUDA or network effects. Use the installed Diffusers VaeImageProcessor equivalent semantics: `image = (decoded / 2 + 0.5).clamp(0,1)`; convert NCHW [1,3,32,32] to HWC, scale to 0–255, convert to uint8, then encode PNG via Pillow. Validate finite CPU float tensor, exact batch/channels/dimensions and cap output bytes. Do **not** independently min-max normalize each image; that would conceal decoder range/quality issues.
3. New `tests/test_zimage_png_postprocess.py`: pure synthetic tensor tests, deterministic channel orientation and pixel tests for values -1, 0, +1, clamp cases, NaN/inf rejection, wrong shape/dtype rejection, reproducibility and PNG re-open/size/mode verification.
4. New `tests/test_zimage_png_smoke_probe.py`: opt-in, reserved directory, overwrite prevention, exact byte/hash report, runtime/loadable flags, no side effects before guard success and injected simulated decoded tensors to run without model weights/CUDA.
5. Update `docs/ZIMAGE_SINGLE_FILE_ROADMAP.md`, this plan and `docs/TESTING.md` with implementation, tests and physical acceptance result after it actually passes. Keep `docs/CURRENT_STATUS.md` describing production limitations.

## CLI and isolation contract

Proposed command (no execution before implementation):

```powershell
cd D:\Morphorum-test
git pull
.\.venv\Scripts\python.exe -m morphorum.zimage_png_smoke_probe --transformer "D:\Morphorum-z219-test\transformer" --encoder "D:\Morphorum-z219-test\encoder" --execute-png-smoke --steps 2 --reserve-gib 3 --headroom-gib 1.5 --output-dir "D:\Morphorum-z219-test\png-smoke"
```

- **Hard gate:** `--execute-png-smoke` required; no write, CUDA import/initialization, checkpoint binding or directory creation without it.
- The user supplies `--output-dir`; no implicit app `outputs/`, `ckpts/`, managed model directory or arbitrary app configuration path. Resolve paths, disallow model checkpoint directories/managed root as targets and refuse symlink escapes. Do not accept a full user-defined filename, just output directory.
- Fixed one-file basename `z2_20c3c5_diagnostic_32x32.png` (or a fixed unique run suffix clearly described in CLI). **Never overwrite existing files**, including via race: use exclusive creation (`xb`) and delete partial file if encoding/writing fails. No writes until numerical and postprocess validation complete; directory-creation behavior and cleanup must be covered in tests.
- Retain c3c4 guards: full SHA-256 of both scratch artifacts, schema, available RAM greater than both BF16 checkpoint files plus 18 GiB, measured VRAM transformer file + minimum 3 GiB reserve, minimum 1.5 GiB forward headroom, two or three steps only, independent components and native prompt encoding. Start with exactly 2 steps for first physical acceptance; no general production prompt overrides or image size flags.
- Keep VAE **on CPU**. Do not save raw tensors, original prompts in sidecars, credentials or EXIF metadata. Only the PNG is persisted; report its path and checksum to console.
- Fail-closed errors return JSON `status=blocked` plus short exception details and a nonzero exit code; no image saved. Treat an existing PNG as a refusal, not success.
- Ensure executable path stays separate from all production Z-Image model discovery and app model-loading APIs.

## JSON contract and acceptance

On success, return `milestone=z2.20c3c5`, `mode=isolated_tiny_png_diagnostic`, `status=diagnostic_png_saved_nonloadable`, `generation_attempted=true` (an actual output attempt was made), `image_file_saved=true`, `loadable=false`, `runtime_verified=false` (not approved for production). Include `output_path` (absolute), `png_sha256` (64 lowercase hex chars), `png_bytes` (>0), `image_dimensions=[32,32]`, `image_mode=RGB`, `decoded_tensor_shape=[1,3,32,32]`, `steps_completed=2`, `decoder_output_min/max`, `postprocess=clamp(decoded/2+0.5,0,1) -> RGB uint8`, `cuda_peak_allocated_gib` and available/free VRAM telemetry. Record whether PNG bytes re-open cleanly in Pillow and dimensions/mode match.

Acceptance on owner's physical Windows RTX 4080 SUPER:
- import/compilation and unit regression tests pass without model weights;
- exactly one file under the **explicitly selected scratch output directory**, nothing under managed model folders or Morphorum normal output paths;
- PNG signature valid, Pillow reads RGB 32×32; checksum and byte count independently match; output deterministic for the postprocess unit fixture;
- two native-caption denoising steps and a finite VAE decode completed; no out-of-memory; peak GPU memory and available RAM recorded;
- `image_file_saved=true`, `loadable=false`, `runtime_verified=false`, no production loader/UI change.
- Report any unexpected image appearance as observation, **not** a model quality PASS. Retain failed/error logs and never re-label `blocked` as success.

## Step-by-step implementation sequence for next chat

1. Inspect current `zimage_vae_decode_probe.py` and existing Z-Image tests, and verify Diffusers/Pillow postprocess API exact output semantics against the installed pipeline.
2. Refactor only as needed to reuse the final CPU decoded tensor, protecting c3c4 console JSON and error contracts with tests.
3. Implement pure CPU postprocessor and isolated one-file exclusive-output saver.
4. Implement guarded c3c5 CLI and test invalid paths, missing flag, bad schema, nonfinite tensors, file collision and fake successful decoded data.
5. Run available Python compilation/tests and check actual CI results; correct issues on `dev-webui`, do not claim physical Windows tests from CI.
6. Update docs with new code status, provide owner's precise PowerShell command and **stop for physical Windows acceptance**.
7. On successful owner JSON + PNG observation, record hashes/memory/acceptance in roadmap, then consider c3d1 (larger tiny image) separately.

## Recovery and checkpoint boundary

Return to the owner-approved c3c4 checkpoint before implementing c3c5 if new changes affect managed generation or UI. Experimental outputs may be deleted without touching sources. Source originals and converted scratch files must not be rewritten. Never merge into `main` absent explicit approval.
