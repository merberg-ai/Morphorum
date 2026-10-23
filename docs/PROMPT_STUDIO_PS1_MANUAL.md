# Prompt Studio PS1.3: Manual Keyframe Editing (dev-webui)

**Status:** PS1.3 manual editing Windows-accepted. PS1.4 persistent drafts available on `dev-webui` for Windows/mobile acceptance. Not an AI prompt generator yet and not part of `main`.

## Workflow

1. Open or create an animation project in **Project → Project Editor**. Save normally or make unsaved prompt-text edits.
2. Select **Project → Prompt Studio**, or **Prompt Studio** from the Project Editor's **Prompt Keyframes** card.
3. Select **Import Existing Prompts**. Studio reads a revision-checked snapshot of the active Editor draft, including unsaved positive/negative text. Project, checkpoint/family, FPS and frame count appear in the context bar. Import does not change or save the Editor.
4. Edit the two prompt lanes independently. Each lane has its own **Hold/Blend** selector and keyframes. You may edit prompt text without normalization, including existing literal LoRA tags and trigger words; change a keyframe frame number; add one at an explicit frame; or remove a nonzero keyframe. Frame 0 is required and cannot be moved or removed; duplicate/out-of-bounds positions are rejected.
5. Select **Preview Changes** to inspect a text diff of all changes (first 50 visible when large). Review the counts and before/after contents. **Apply to Animation** is disabled until the preview is current.
6. Select **Apply to Animation** and confirm the prompt-only transfer. The Project Editor opens with changed prompts staged as **unsaved**. Verify them and use **Save Project**. Camera schedules, generation settings, image/audio attachments and model selection are outside this transfer.

**Reset Draft** restores the imported track values without touching the Editor. **Unsaved Studio edits** exist only in browser memory. Use **Save Draft** to persist them before reloading. **Save As New Draft** makes a separate named copy. **Load Draft** resumes a saved copy, and **Delete Draft** removes the selected saved copy after confirmation. Saving a draft never modifies the animation's `project.json` or triggers rendering. Reimporting with unsaved Studio changes requires confirmation. Importing again after an applied transfer refreshes the snapshot. If the Editor's state, selected model, FPS, frame count or saved revision changes while a Studio draft is open, its Preview/Apply fails closed and asks for a fresh import. A save from a second tab is intentionally treated as a conflict.

## Acceptance tests (Windows plus narrow-screen mobile)

- With no project open, Import shows an explanatory error and does not make one.
- In the Editor, edit text without saving; import and confirm the draft sees the unsaved text.
- Import separate positive and negative tracks with different keyframe positions and modes; ensure no new phantom negative frames appear after **Apply → Save Project → reload**.
- Verify multiple LoRA directives and spacing survive exactly. Edit one lane without changing the other.
- Add and move keyframes using explicit frames; confirm collisions, frame 0 moves/removes and out-of-range frames are blocked.
- After Preview, edit another prompt; Apply must require a new Preview.
- Switch projects or edit the saved project in another tab while Studio remains open; Preview/Apply must reject the old snapshot without altering Editor data.
- Verify **Reset Draft**, explicit confirmation, and the main Editor's normal Save Project; manually confirm untouched camera/generation/media settings.
- Edit prompts, Save Draft, reload the browser, select the saved draft and Load Draft. Save again, Save As New Draft, then delete a selected copy. Two browsers changing one draft should refuse stale overwrite/delete.
- Change the active project's positive or negative keyframes or model/FPS, then load an older saved draft. It should remain editable and saveable, but **Apply** should remain blocked. Reimport current Editor prompts to start a new safe baseline.
- Export the project ZIP and import on a clean test install: drafts should be included. Use Save Project As, open the copy, and confirm the drafts belong to the new project ID. Generated outputs should remain excluded.
- On a phone, verify lane fields, frame numbers, Hold/Blend and action buttons remain usable without horizontal overflow.

## Not yet implemented

Visual drag/snap/undo timeline (PS2), LoRA block organizer (PS3), local Ollama AI authoring (PS4), model-specific prompt profiles (PS5), **audio-to-storyboard synchronization (PS6)**, transition refinement and Parseq coexistence. Existing rendering and native frame resolution remain unchanged.

Implementation details: [PS0 native contract](PROMPT_STUDIO_PS0_CONTRACT.md) and [PS0–PS9 roadmap](PROMPT_STUDIO_ROADMAP.md).

## PS2 visual timeline acceptance (dev-webui, Windows/mobile)

1. Import an existing or stored Studio draft. A horizontally scrollable time ruler and separate positive/negative diamond keyframes appear above the text editors. Scrub the range/Frame input to inspect both tracks' **native backend Hold/Blend prompt transitions**, including from/to weights and raw prompt text.
2. Drag a nonzero positive keyframe on desktop and by touch on phone. Try Snap 1, 5, 10 and zoom levels. Check a diamond's resulting frame number matches its text editor. Move negative keyframes independently; frame 0 cannot move.
3. Shift/Ctrl-click two diamonds then drag to move them together. A positive-lane scene strip shows scene durations; clicking a block scrubs to its starting keyframe. Occupied destinations, out-of-bounds moves and anchored frame-zero selections must not partially modify the draft.
4. Select nonzero keyframes and use **Duplicate**, **Delete Selected** and **Evenly Space**. Verify raw text and LoRA tags stay byte-for-byte intact.
5. Use **Lock** for a lane; verify its diamonds and matching frame/text inputs cannot be edited. Unlock and try again. Locks are temporary editor controls, not rendering or stored draft metadata.
6. Use **Undo/Redo**, including text edits followed by drag. Editing after Undo must clear redo. Save Draft, refresh/reload it and verify the edited tracks persisted; Undo/Redo history is session-only.
7. Preview Changes, Apply to Animation, Save Project and reload. Verify the native timeline and prompt resolution matches the Studio tracks and unrelated camera/generation/media settings remain unchanged.
8. On mobile, check horizontal scroll, diamond dragging without accidental page movement, accessible zoom/snap buttons, and no viewport overflow. No rendering or backend project write should occur just by scrubbing or editing Studio.

## PS3 structured prompt composer: physical acceptance

PS3 adds **Structured Prompt Composer** above the PS2 timeline on `dev-webui`.

1. Import a project, add a global Positive text block at Beginning, then a scene-local block at End at an existing positive keyframe. Preview the exact prompt string, including untouched literal text already in the frame.
2. Reorder blocks with ↑/↓, toggle Active, edit the block text or placement, and preview the new result. Verify the negative lane remains unchanged unless a negative text block was deliberately added.
3. Refresh the local LoRA catalog with an SDXL/FLUX/Z-Image project active. The list must be filtered to that project's model family. Choose a LoRA, adjust its weight, and optionally use cached Civitai trained words/thumbnail metadata. No automatic Civitai sync or internet fetch should occur.
4. Check that negative LoRA directives are disallowed, other-family LoRAs cannot be committed, and duplicates of a native existing LoRA tag produce a warning/confirmation.
5. **Commit Preview to Studio Draft** should update only the Studio draft tracks, including PS2's text/timeline editor. Then use Preview Changes → Apply to Animation → Save Project to persist into the animation. Verify the actual keyframes and raw LoRA directives survive reload.
6. Save a draft with composer blocks, reload it, and verify label, scope, frame, order, weight, triggers, placement and enabled state. An old draft without composer data should still load with an empty composer.
7. Verify project ZIP export/import and Save Project As keep block metadata. On a phone, ensure text editors, LoRA picker and actions fit the viewport.
8. Check SDXL/FLUX/Z-Image generation separately if testing actual LoRA behavior. An indexed-family label and Civitai trigger metadata are informative, not proof the LoRA applies correctly in the renderer.

No AI provider is part of PS3. That remains the separate PS4 work.

## PS4 AI Director visibility hotfix (2026-10-21)

PS4 initial UI integration left the **outer** AI panel hidden while toggling only its inner child. Even after a successful `dev-webui` update and prompt import, the AI controls could remain invisible. The fix in `frontend/dist/assets/prompt-studio-ai.js` explicitly reveals the outer section. A new **AI Story Director ↓** shortcut is in Prompt Studio's top action row. Before import, the section displays guidance; after **Import Existing Prompts** or **Load Draft**, the Ollama form should be visible. Reload the browser after updating the branch, and check the new shortcut to confirm the patched frontend assets are loaded.

## PS4 AI Story Director acceptance (dev-webui, Windows + Android)

**Prerequisite:** A local Ollama server with at least one installed text-capable model. `http://127.0.0.1:11434` is the default Ollama endpoint **on the Morphorum host**, not on the Android phone. For a different LAN computer, enter its numeric private IP address (for example `http://192.168.1.20:11434`) and explicitly tick **Allow my trusted private LAN IP**. Ollama must be configured by its owner to listen on that interface; do not expose Ollama to the public internet. The connection accepts no credentials and never fetches model weights.

1. Open a project, import prompts into Studio, then **Test Connection / Models** in the AI Story Director. Select an installed Ollama model. If it has poor JSON-format support, choose a model that follows strict structured-output instructions reliably.
2. In **Create storyboard**, enter a story, select 3–5 scenes and Generate. Frame positions must be deterministic, starting at 0, within `max_frames`. The proposed scene text must appear in a before/after panel. Studio timeline and Project Editor must still be unchanged.
3. **Discard Proposal** and verify nothing changed. Generate again, **Accept into Studio Draft**, confirm, then inspect the timeline and Undo/Redo. Save Draft and reload to verify the accepted AI prompts and model/time provenance survived.
4. Try **Refine existing positive keyframes**. Native frame positions must remain identical; existing literal LoRA tags should survive exactly, although the generated refinement reports their placement at the beginning of each revised prompt. Check that unrelated negative prompts/keyframes remain unchanged.
5. Enable **Also generate negative prompts** only when you intend to replace the negative track. Review the negative-lane diff carefully before accepting.
6. Test a wrong Ollama port, offline host, uninstalled model and a model returning invalid JSON; errors should be visible, with no changes to the Studio draft. Cancel a long request, then edit the draft: the old response must never be accepted.
7. Check LAN restrictions: private host without the opt-in should be rejected. Public/DNS endpoints, `https://`, credentials, URL paths and redirects must fail.
8. Verify ordinary Studio **Preview Changes → Apply to Animation → Save Project**, followed by project reload and a small SDXL/Z-Image test render. PS3 composer, PS2 undo/redo, and persistent ZIP/Save As should continue to work.
9. On Android, verify connection fields, story editor, proposal diff, cancel and confirmation buttons work without horizontal overflow. No image/audio assets are transmitted to the LLM in PS4.

**Important:** AI authoring can consume your local Ollama computer's GPU/VRAM. With an RTX 4080 SUPER 16 GB, avoid concurrent large Ollama models and diffusion renders. The Ollama request sends `keep_alive:0` to encourage model unloading after inference, but this does not forcibly evict all Ollama resources. Model-family prompt optimization and optional vision description come in PS5; audio-to-storyboard synchronization is still planned for PS6.

## PS4.1 Ollama progress and console visibility hotfix (2026-10-21)

The original PS4 `/api/prompt-studio/ollama/generate` endpoint waited until Ollama produced an entire structured response. A large or cold-loaded model therefore appeared stalled, and Prompt Studio backend log events were absent from the Console's source filter.

**PS4.1** changes only the WebUI generation path to **`POST /api/prompt-studio/ollama/generate-stream`** with streaming newline-delimited JSON. Morphorum now sends a *connecting/model-load* event immediately, regular heartbeat events while Ollama is quiet, actual response stages and character counts as the model outputs text, validation, and either a fully validated proposal or an actionable error. The WebUI shows an indeterminate progress bar, **elapsed seconds** and **received character count** (not a fake percentage or ETA). The request is bounded to 240 seconds and can be cancelled; browser cancellation closes the stream and the backend cancels its producer when the disconnect is observed. The existing nonstreaming endpoint remains for backward compatibility.

**Console:** In the Morphorum Console, **Source filters → Prompt Studio** is now checked by default. Events include model, mode, requested scene count, waiting/progress updates, completion, cancellation and errors. Raw story ideas, AI-generated scene text, connection credentials and prompt LoRA content are deliberately **not logged**. These messages belong to the WebUI Console; they are not a guaranteed printout in the separate process terminal.

**Quick Windows acceptance:** Update `dev-webui` and hard-reload the browser, open Prompt Studio → AI Story Director, connect and request a storyboard. Observe elapsed time advance even if Ollama has not started output. Once Ollama streams text, the received-character count should climb. Open Morphorum Console and verify checked *Prompt Studio* events (including successful completion or timeout). Test Cancel, an invalid/offline port, and a second request; neither cancelled nor failed output should reach the prompt editor. If Ollama never sends a completion, the request errors instead of silently applying partial text. For final scene review and Apply → Save, continue using the normal PS4 safety workflow. Live generation performance on the owner's Ollama installation has not yet been measured.

## PS5.1 model-family profiles and continuity: Windows/mobile acceptance

**Status:** PS4/PS5.1/PS5.2 passed owner Windows testing. PS5.3 model comparisons are implemented on `dev-webui` for owner physical acceptance; not merged into `main`.

1. Open **Project → Prompt Studio → AI Story Director**. Import or load a saved Studio draft. The new **Model-aware authoring** section should show the selected project's **SDXL**, **FLUX** or **Z-Image** family profile. Verify the profile description and negative-conditioning caveat match the selected family; no generator settings are changed.
2. Enter a recurring subject identity, e.g. `the same orange cat with a torn left ear`, and a locked style, e.g. `grainy 1990s VHS footage`. Create a three-scene storyboard and inspect the AI proposal. Missing lock phrases must be repeated literally on each generated positive frame; no new LoRA tags should be invented.
3. Switch **Mode → Refine existing positive keyframes**. Choose a specific entry in **Refine selection → Only frame N**; generate and review. Only that selected positive prompt should change. All other positive keyframes retain frame positions and exact prompt text, including preexisting LoRA directives and whitespace in unselected frames.
4. Keep **Also generate negative prompts** unchecked: the negative lane must remain byte-for-byte unchanged. If checked during a selected-frame refinement, only the selected frame is updated/inserted while unrelated negative keyframes remain intact. The tool should warn that negative conditioning may not be supported by all FLUX/Z-Image pipelines.
5. Examine the **Prompt lengths** review section. Counts are approximated words, **not model tokenizer counts**, and warnings must not imply a universal 77-token truncation threshold.
6. Verify SDXL → FLUX → managed Z-Image project switching shows the correct family guidance and rejects mismatched profiles; cancel in-flight Ollama requests and verify no stale proposal is accepted. Check narrow-screen mobile layout.
7. Accept a proposal into Studio, Save Draft, reload, and verify the versioned profile provenance survives project ZIP and Save As. Complete **Preview Changes → Apply to Animation → Save Project** and reload. Confirm the normal renderer remains untouched.

## PS5.2 optional local start-image vision: Windows acceptance (2026-10-22)

**Status:** owner Windows-accepted (2026-10-23); automated provider/privacy test coverage retained. PS5.1 was accepted. This is an *image-to-editable-description* assist, **not** a generated storyboard and not another renderer.

1. Attach a **start image** in the Project Editor and save/verify the attachment. Import prompts (or load a valid saved Studio draft), open **AI Story Director → PS5.2 Analyze attached start image**, and confirm its preview is the correct project image. Use **Refresh Start Image** after replacing it.
2. Run local Ollama **on the Morphorum host**. Select an installed **vision-capable** model from Test Connection / Models. The chosen model must return `capabilities` containing `vision` from Ollama's `/api/show`; model name/family/size alone does not qualify. The normal text Story Director can target a trusted private LAN Ollama server, but **PS5.2 image analysis is restricted to loopback** (`localhost`, `127.0.0.1`, `::1`).
3. Review the thumbnail, check **I authorize sending this previewed attached image** for this specific request, and click **Analyze Start Image**. The checkbox resets immediately. The backend checks the image's exact SHA-256 against the preview, rejects symlink/traversal paths, validates PNG format/size/dimensions and sends a bounded downscaled JPEG only after confirming the selected model is vision capable. No other file is eligible; no image is sent by opening Prompt Studio.
4. Edit the returned description, then click **Add Description to Story**. This only appends text to the editable Story idea field. It **does not** generate a storyboard, touch positive/negative keyframes, persist the description as project metadata or render. Generate Storyboard separately, review the proposal and explicitly Accept → Preview/Apply → Save Project as usual.
5. Negative-path tests: no image, unchecked consent, image replaced after preview (SHA conflict), corrupt image, offline Ollama, a text-only model or absent `vision` capability, invalid returned JSON, Cancel while analyzing, then switch projects. Confirm no stale results appear and no project/Studio edits or image request are silently applied. Test responsive image preview and checkbox/button controls on Android.

**Privacy:** The WebUI is intended for a trusted host/LAN; keep Ollama private. The endpoint sends a resized project image only after affirmative user consent. Image contents, model output and absolute paths are excluded from Morphorum Console messages. The backend sends no image to a user-entered remote IP, domain, URL or third-party provider. Image description quality and GPU behavior still need real Windows testing. PS5.3 compares models after this gate. PS6 remains the required audio-to-storyboard sync milestone.



## PS5.3 two-model comparison: owner Windows acceptance (2026-10-23)

**Status:** model evaluation tools implemented on `dev-webui`; automated browser tests pass, but physical model-quality and render checks remain pending. PS5.2 image analysis is already owner-accepted.

1. Open **Project → Prompt Studio → AI Story Director** and import or load an editable Studio draft. Choose a project with the family to evaluate (**SDXL**, **FLUX** or **managed Z-Image**). This family selects the appropriate authoring profile; comparison does not change the checkpoint or render anything.
2. Test Connection / Models with local or explicitly opted-in private-LAN Ollama. Under **PS5.3 Compare local Ollama models**, select a fixed case and **two different installed Ollama models** as candidates A and B. For example, a smaller 4B and larger 9B candidate *if installed*; names and parameters are informational, not evidence of quality.
3. Press **Compare Models**. Morphorum runs exactly the same built-in case for A then B using PS4.1 streamed generation and strict server frame assignment. Compare happens sequentially to reduce deliberate concurrent VRAM load. Watch progress and elapsed seconds. Each candidate may take up to the existing 240-second generation cap. Cancel discards partial comparison results. An invalid model/response should produce a recorded error without modifying the Studio draft.
4. Expand each candidate scene to inspect its exact generated positive prompt. Score **Instruction fidelity**, **Scene continuity**, and **Prompt clarity** manually. Ollama-reported evaluation time and token count are *provider metrics*, not render speed or image-quality measures. Cold-model loading, caching, sampling variability and local resources complicate speed comparisons; repeat runs before drawing conclusions.
5. For **mixed-LoRA**, the case uses synthetic `<lora:EvalInkStyle:0.65>` / `<lora:EvalAtmosphere:0.35>` placeholders. These are *not installed adapters*, and their exact preservation is handled by Morphorum's LoRA refinement logic. Replace these with your own compatible LoRAs if you manually use the prompts in a render. Do not label model correctness or live LoRA effects as verified by this test.
6. Click **Copy Prompts for Render Spot-check**, then render samples through the normal Morphorum generation workflow. For fair candidate comparisons, hold image checkpoint, seed, resolution, steps, CFG, sampler, LoRA weights and other rendering settings constant per family. Test SDXL, FLUX and managed Z-Image independently where supported. Record whether each actual render passed or had visible errors using **Physical render spot-check** on the evaluation card.
7. Select **Export JSON Report** to download cases, prompts, metrics, manual ratings and render outcomes. The report is generated only when requested; the comparison panel neither saves it to the server nor applies prompts to Studio. Reports are only comparable when benchmark case, family, model versions and generation settings match.
8. Negative-path checks: only one model connected, same model A/B, offline Ollama, malformed model JSON, cancelled first/second model, switching projects mid-comparison, mobile responsive cards, return to normal Generate Storyboard, and PS5.2 explicit image consent. Verify no project renders, files or prompt tracks are changed as a side effect.

**Acceptance boundary:** PS5.3 is the tooling for evaluating models, **not an automatic declaration of the best model**. Record real Windows tests and short physical renders before selecting a recommended local model. PS6 remains the separately gated, required Motion Studio audio-to-storyboard synchronization phase.
