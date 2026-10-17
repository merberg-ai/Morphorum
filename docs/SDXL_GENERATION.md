# SDXL image and animation generation

Morphorum supports SDXL image generation and animation with several sampler choices, noise schedules, longer prompts, and model-aware LoRA loading. This guide covers **SDXL only**. FLUX and Z-Image use their own sampler, prompt, guidance, and LoRA handling.

> This documentation describes the features on the development branch while final Windows acceptance is in progress. Use the public `main` branch for a normal installation until the changes are released.

## Choose a sampler and schedule

Choose an **SDXL** checkpoint in **Image Generation** or your animation project's **Generation Settings**.

Available samplers:

- Euler, Euler a, DPM++ 2M, DPM++ 2M SDE
- DDIM, LMS, Heun, UniPC
- DPM2, DPM2 a, DEIS, DPM++ Single Step

Available SDXL schedule types are **Normal**, **Karras**, **Exponential**, **Beta**, and **Trailing (Diffusers)**. Not every combination is supported. The UI restricts incompatible choices, and backend validation rejects unsupported combinations rather than silently switching algorithms.

- **Normal:** supported by every listed SDXL sampler.
- **Karras:** available where its selected Diffusers scheduler supports Karras sigma spacing.
- **Exponential** and **Beta:** supported for Euler, DPM++ 2M, DPM++ 2M SDE, and UniPC.
- **Trailing:** supported for Euler, Euler a, DPM++ 2M, DPM++ 2M SDE, LMS, Heun, and UniPC.
- **DDIM:** Normal only.

Sampler choice can alter image appearance and reproducibility. For repeatable comparisons, keep the checkpoint, prompt, negative prompt, seed, resolution, steps, CFG, and LoRA settings fixed while changing just one sampler or schedule.

## Long prompts and negative prompts

Both SDXL text encoders (CLIP-L and CLIP-G) ordinarily accept 77 tokens per sequence. Morphorum uses **chunked conditioning** for prompts that exceed either encoder's sequence limit. Positive and negative prompts are encoded with both towers and aligned to a common embedding length for classifier-free guidance.

- An ordinary short prompt stays on the native Diffusers prompt path.
- An overflowing SDXL prompt uses several CLIP chunks; there is a safety limit on chunk count.
- Long negative prompts are also supported where classifier-free guidance is enabled.
- In animations, blended prompt endpoints are aligned before interpolation. An unchanged long prompt can reuse cached conditioning on later diffusion anchors.
- **CLIP chunking is not unlimited context.** Very large prompts can exceed the configured safety limit. More tokens also require more conditioning work and memory.

The **Image Generation** progress panel shows the *actual* conditioning mode (`STANDARD`, `CHUNKED`, or `EMBEDDED`), token/chunk counts when available, and embedding dimensions. **Animation Rendering** shows its confirmed conditioning mode at diffusion anchors. `CHUNKED / BLENDED` means the renderer is interpolating precomputed chunked embeddings.

A character-length advisory shown while editing is only an estimate. It is **not** proof that your prompt was truncated or chunked. Check the actual conditioning diagnostic during the render. Successful chunking is informational, not an error.

## LoRA adapters and verification

Add SDXL LoRA directories through **Settings**, scan **Models**, and use the LoRA picker to insert a prompt tag. Animation prompt keyframes can specify different LoRA strengths.

Morphorum verifies adapter registration, activation, and loaded parameter presence. For the **normalized SDXL full text-encoder compatibility loader**, it also verifies the CLIP-L and CLIP-G LoRA A/B tensor counts and values against the checkpoint.

The render diagnostics distinguish:

| Display | Interpretation |
| --- | --- |
| **CLIP weights matched checkpoint** | The compatibility loader compared expected CLIP LoRA parameters to the injected values successfully. |
| **Active; source weight comparison unavailable** | The adapter is active, but a source-value comparison was **not** performed on that loading path. This is not a failure or proof of full matching. |
| **UNet-only fallback; CLIP LoRA weights not applied** | The compatibility loader could not retain a full text-encoder adapter and applied verified denoiser weights only; text-encoder style influence may differ. |

A `MISSING` report from Transformers or a message about deleting an old active PEFT adapter can occur during module initialization/replacement. These messages alone do not prove that final weights are missing. Read the **subsequent Morphorum verification result**. An explicit checkpoint mismatch or incomplete adapter error **must be investigated**; it must not be ignored because the render still produced an image.

## Animation performance and stability

Morphorum caches a bounded number of SDXL conditioning results for animation prompt transitions and unchanged long prompts. The cache key includes the relevant LoRA strength signature, so changing LoRA strengths requires a new conditioning result.

**Animation Rendering → Performance** includes:

- Diffusion-anchor timings and CUDA memory allocation/reservation when reported by the backend.
- Cumulative SDXL conditioning-cache **hits** and **misses**; successful reuse should produce hits on later diffusion anchors when the prompt and LoRA strengths remain unchanged.
- Existing pipeline task, optimization, active LoRA, and stability data.
- A downloadable performance report and individual `performance.jsonl` frame records.

A cache hit does not by itself prove a faster whole render; performance depends on the checkpoint, device, image size, scheduler, and denoising work. Compare otherwise identical runs on your actual GPU.

## Common checks

**Conditioning shows STANDARD for a long-looking prompt:** character length is not token length. Look at the encoder-specific token counts. If encoding resources were unavailable, the console may warn about truncation.

**Animation changes appearance at a prompt transition:** inspect the positive and negative prompt keyframes and their interpolation weights; the UI reports the resolved prompt for each frame.

**A LoRA is present but seems ineffective:** check its indexed model family, strength, tag, adapter diagnostic, and whether it fell back to UNet-only. A verification message about a *normal* adapter does not mean its values were compared.

**Memory usage grows or rendering slows:** inspect the render performance report. Reduce output size/frames, number of active LoRAs, or long-prompt length as appropriate. Performance data is observational; it does not automatically switch to CPU or change your model.

See [G5 Windows acceptance checklist](G5_RELEASE_ACCEPTANCE.md), [Testing](TESTING.md), and [Troubleshooting](TROUBLESHOOTING.md).
