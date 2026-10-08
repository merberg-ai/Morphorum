# LoRA support

Morphorum accepts Deforum-style LoRA directives in positive prompts:

```text
<lora:lora_name:weight>
```

Examples:

```text
a cinematic portrait <lora:detail-style:0.8>
a ruined city <lora:cyberpunk:0.65> <lora:film-grain:0.25>
```

The directive is Morphorum control syntax. It is removed before the prompt text reaches
the model's text encoder.

## Supported model families

LoRA resolution is model-family aware:

- SDXL prompts resolve only against indexed SDXL LoRAs.
- Flux prompts resolve only against indexed Flux LoRAs.
- Z-Image prompts resolve only against indexed Z-Image LoRAs.

A same-named LoRA from another family is not silently substituted. Morphorum reports a
family mismatch instead.

Checkpoint source and LoRA source are independent. Z-Image checkpoints remain managed
by Morphorum while Z-Image LoRAs are scanned from user-configured external directories.

## LoRA directories and indexing

Settings exposes LoRA directories for SDXL, Flux, and Z-Image. After adding or changing
a directory, run the normal Models scan.

Indexed LoRAs retain:

- stable Morphorum model-index id,
- family,
- name,
- filename,
- absolute path,
- file size,
- optional preview path.

Prompt tags resolve by exact filename, exact filename stem, or exact indexed name.
Case-insensitive exact matching is allowed. Morphorum does not use fuzzy matching for
generation because choosing the wrong adapter is considerably worse than asking the
user to spell its name correctly.

## Still-image generation

For image generation Morphorum:

1. parses LoRA directives from the positive prompt,
2. resolves every directive against the active model family,
3. strips the directives from prompt text,
4. loads each required Diffusers adapter once on the currently loaded pipeline,
5. activates the requested adapters and weights with `set_adapters()`,
6. runs inference,
7. records resolved LoRA state in image/job metadata.

LoRA directives in the negative prompt are rejected. Diffusers adapters are global
pipeline controls rather than negative-conditioning tokens.

Morphorum does not fuse LoRA weights into the base checkpoint. Keeping adapters
separate permits fast weight changes, animation scheduling, and predictable unload
behavior.

## Animation behavior

LoRA directives can appear independently in positive prompt keyframes:

```text
Frame 0:
forest at dusk <lora:horror:0.0>

Frame 30:
the trees begin twisting <lora:horror:0.5>

Frame 60:
nightmarish corrupted forest <lora:horror:1.0>
```

When prompt interpolation is `blend`, Morphorum interpolates LoRA weights alongside
the prompt transition. A LoRA omitted from one endpoint is treated as weight zero for
that endpoint.

At each resolved frame the renderer receives first-class state:

```json
{
  "loras": [
    {
      "id": "indexed-lora-id",
      "family": "sdxl",
      "name": "horror",
      "weight": 0.5,
      "adapter_name": "morphorum_indexed-lora-id"
    }
  ]
}
```

The human-readable prompt shown to the diffusion text encoder no longer contains the
`<lora:...>` directive.

Loaded adapters are cached on the active pipeline. Weight changes call
`set_adapters()` rather than reloading the LoRA file. A frame that needs no active
LoRA disables adapters while leaving them available for later frames.

Animation render preflight validates LoRA names and model-family compatibility before
diffusion starts. The render also uses one LoRA index snapshot instead of repeatedly
querying the model index for each frame.

Resolved LoRA state is written into frame metadata through the existing resolved-frame
manifest data.

## Picker UI

The image-generation prompt has a family-filtered LoRA picker. Selecting an adapter and
weight inserts the Deforum directive at the current prompt cursor.

Each animation prompt keyframe also exposes a family-filtered picker. It inserts the
same directive into that keyframe's positive prompt.

The resolved-frame inspector displays the active LoRA names and weights at the current
frame.

Typing directives manually remains fully supported.

## LoRA Manager (B4 diagnostic laboratory)

The dedicated **LoRAs** tab sits next to Models and shares its indexed file database.
It can rescan configured SDXL/Flux/Z-Image LoRA directories, filter a family,
inspect an individual file, and insert a family-checked Deforum tag into the
Image prompt. A user may also include *recorded* trigger words automatically.
The selected image checkpoint must belong to the same family.

The static inspector opens safetensors headers on CPU and reports:
- embedded metadata and training fields (including `ss_*` values),
- local `.civitai.info`, `.civitai.json`, `.json` and bounded `.html` sidecars,
- explicit trigger words with provenance,
- model-family hints and mismatches,
- tensor counts by UNet/transformer/text encoder,
- representative keys and rank/shape patterns,
- frequently occurring training tags (NOT treated as verified triggers).

Unsafe pickle-based `.ckpt` and `.pt` files are not deserialized for inspection.
Inspection doesn't load any weights onto CUDA. It also cannot by itself prove
that the LoRA actually changes inference output.

### Optional Civitai metadata lookup

**Fetch from Civitai** is a deliberate per-LoRA online action. Morphorum
hashes the selected indexed file with SHA-256 and queries the documented
`GET https://civitai.com/api/v1/model-versions/by-hash/{SHA256}` endpoint.
If no hash match is found and a local JSON sidecar supplies an exact
`modelVersionId`, it attempts that version ID as a fallback, clearly labeled
*not hash-verified*. There is no fuzzy filename match, HTML scraping, automatic
whole-library upload, or remote model download.

It displays Civitai's stated base model, model and version names,
explicit `trainedWords`, description converted to plain text, and a link
to the version page. All remote text is rendered as untrusted text, not HTML.
The hash is cached locally using file size/mtime to avoid unnecessary repeated
hashing. The outbound query reveals the file hash to Civitai, **not** prompts,
local file paths, or file contents. Browsing the manager stays offline.

If no triggers exist in the local file or sidecar, the prompt insertion
control may use explicit Civitai trained words after a successful lookup.
Metadata and source provenance are kept distinct.

## Runtime implementation

Morphorum uses the current Diffusers LoRA APIs exposed by its supported pipelines:

- `load_lora_weights()`
- `set_adapters()`
- `enable_lora()`
- `disable_lora()`

The pipeline cache is reset when the base model is unloaded or replaced. Adapter state
therefore cannot leak from one checkpoint to another.

No LoRA fusion is performed in A3.

## Timeline schema

Schema 2 already reserves `tracks.loras` for future explicit LoRA tracks. A3 derives
LoRA state from prompt directives and publishes it in resolved-frame state.

This deliberately keeps the familiar Deforum syntax as the authoring format while
avoiding a second competing schedule representation. A later timeline UI can promote
derived LoRA state to explicit visual tracks without changing the renderer contract.

## Physical verification boundary

Automated tests cover:

- directive parsing and stripping,
- positive/negative prompt rules,
- exact family-aware resolution,
- family mismatch errors,
- Z-Image external LoRA indexing,
- Diffusers LoRA API availability for SDXL, Flux, and Z-Image,
- load-once adapter caching,
- adapter reweighting,
- adapter disabling,
- animation weight interpolation,
- pre-render validation,
- frontend control presence,
- existing backend/self-test regressions.

A real GPU test is still required to establish that actual third-party LoRA weights are
compatible with the selected real checkpoints and with Morphorum's low-VRAM/offload
configuration. Mock pipelines cannot prove that adapters materially change generated
pixels or that a particular LoRA file was trained for the selected base architecture.
