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
