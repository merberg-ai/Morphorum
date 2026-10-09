# Output Resolution Presets

**Branch:** `dev-ui` | **Status:** Implemented; Windows/Android acceptance required

Image Generation and Animation now use a shared resolution menu:
- **Recommended for model:** default plus presets supplied by the selected model family's generation capabilities, including any variant-specific overrides.
- **Square & previews:** 512, 768 and 1024 square.
- **Landscape (video formats):** 480p, 720p, 1080p and 1440p.
- **Portrait (video formats):** matching 9:16 choices for 480p through 1440p.
- **Custom:** width and height remain directly editable. Typing a supported preset size reselects it; other values display Custom.

The image generator accepts widths/heights divisible by **8 for SDXL** or **16 for Flux / Z-Image**. This is a model constraint, not a stylistic preference. The common 854×480 frame isn't divisible by 8, so 480p uses **848×480** (or 480×848). For Flux/Z-Image, 1080p uses **1920×1088** (or 1088×1920) to remain divisible by 16; SDXL supports exact 1920×1080. The UI labels model-aligned variants and warns that large outputs demand more VRAM. Higher resolutions are options, not promises of memory availability or successful rendering.

The dropdown does not change the model itself, the Image draft key, Animation project schema, rendering code, or saved project dimensions. Switching models refreshes recommendations without destroying a custom animation size.

## Physical acceptance
1. Windows Image tab: SDXL selected; choose 480p landscape, 720p portrait, 1080p landscape and verify numeric fields. Try rendering a small preset. Enter an arbitrary multiple-of-8 custom size, refresh, and confirm the Image form draft restores both dimensions.
2. Flux/Z-Image Image tab: confirm aligned 1080p dimensions, custom warnings for non-16-aligned dimensions, and existing model-specific samplers/default steps remain correct.
3. Animation Editor: open an existing project with custom dimensions. The dropdown should say Custom and **must not** replace the saved dimensions. Choose a preset, verify project dirty state, Save, Reload and verify persistence. Change selected model: the presets adapt without silently changing the dimensions. Test a short animation at a small preset.
4. Android browser over LAN: landscape/portrait labels remain readable, the numeric fields and Model selection are accessible, and there is no horizontal overflow. Check the existing Monitor progress and outputs.
5. Confirm high-res animation warning still appears before attempting untested large renders. The new 1080p/1440p choices can exceed physical GPU capacity. Begin with low resolutions before attempting large jobs.

Do not create a new checkpoint or merge into paused B6 until physical acceptance.
