# Import Deforum Motion Settings

Morphorum can import **3D six-axis camera schedules** from a Deforum Motion Studio **Export to Deforum** `.txt` file or compatible Deforum `.json` settings into an **existing** Morphorum animation project. Import is optional and never changes the model, prompts, seeds, resolution, FPS, frame count or cadence.

## Import into an existing project

1. Open **Motion Lab → Project Manager**, select or create a **3D** project, and save any unsaved editor changes.
2. Open **Motion Lab → Import Motion Settings** on desktop or in the Motion Lab workspace navigation.
3. Choose the Deforum `.txt` or `.json` export. Review the source FPS, frame count, cadence, duration, six-axis graphs and any compatibility warnings. This preview **does not modify** the project.
4. Select **Deforum compatible** camera conversion (default), or **Raw source values** for comparison. Adjust the separate **Translation strength** and **Rotation strength** sliders/percentage inputs from **0% to 400%**. **Reset 100%** restores the initial conversion baseline; **Tested 200%** recalls a working experimental setting, not a universal optimum.
5. Expand **Review original vs converted schedules** to inspect the actual source keyframes and converted Morphorum schedules. Select **Review safe import**.
6. If the review succeeds, select **Apply camera motion** and confirm. Only the six camera tracks are replaced. You must review again if the source file, project or conversion settings change.
7. Use **Motion Curves**, **Camera Preview**, then **Render Animation**. Export completed MP4/WebM videos under **Outputs**.

**Compatibility requirements:** The project must already use 3D mode and match the source **FPS, number of frames and constant diffusion cadence**. All six numeric camera schedules must be present; expressions and unsupported formulas are rejected. The import does not automatically retime, change cadence, or merge with existing Motion Lab layers/applied motion. Sources over **3,000 frames** cannot be applied unchanged. Prefer a fresh or backed-up project: there is **no single-click undo** for an applied import.

### Camera units and strength

Deforum and Morphorum use different camera/depth projections. In Deforum-compatible mode the importer initially maps **X = −source X / 200**, **Y = source Y / 200**, **Z = −source Z / 200**. The imported rotation angles remain in degrees. A strength of **100%** multiplies these mapped values by 1, **200%** by 2, and **400%** by 4. In **Raw** mode the unconverted Deforum camera values are multiplied by the chosen strengths. The renderer itself is not modified.

This is a practical conversion, **not pixel-for-pixel Deforum compatibility**; image depth, FOV and rotational behavior can differ. Review a short preview or test render before committing to long animations.

## Optional soundtrack

The source export may include `soundtrack_path`. It is displayed **only as reference text**, with **Copy path** and **Copy folder** buttons. Morphorum never reads that computer path automatically. Browser security prevents opening the file chooser at an arbitrary imported path, so choose the file manually.

The optional browser picker supports **WAV, MP3, OGG and FLAC** when your browser can decode them. The audio playhead and waveform allow you to check synchronization and adjust an offset in seconds.

To keep the audio for rendering, explicitly select **Attach selected audio to project**. Files are limited to **40 MiB** and validated by file signature. **Save audio offset** persists the offset independently of camera motion; accepted offsets are **−30 to +30 seconds**. Merely selecting audio for browser preview does not upload it.

An attached soundtrack is **frozen into each new animation render** at render submission, including its file content and saved offset. MP4/WebM exports use that frozen soundtrack at the **original render FPS**. A positive offset skips ahead in the soundtrack at video time zero; a negative offset delays its start. Playback is trimmed/padded to video duration. Replacing an attachment or offset later affects **new renders only**, not old render exports. A render with both imported audio and a Motion Lab audio source cannot be exported with ambiguous dual audio; the exporter rejects it.

Animation frame previews and GIF-like previews may be silent. Check the **exported MP4/WebM** for audible sound. FFmpeg must be available.

## Supported format and limitations

- Use **Export to Deforum** in [Deforum Motion Studio](https://github.com/chicodog530/Deforum-Motion-Studio). Its separate `.dms.json` session format is not supported here.
- The importer accepts literal numeric `frame:(value)` schedules only. It never runs user-supplied expressions or loads embedded host paths, external models or video files.
- Import into an existing project **replaces** the six camera schedules after guarded review. It does not offer additive-layer import, timing adoption, automatic resampling, one-click rollback or complete Deforum engine emulation.
- **200% / 200%** translation and rotation strengths were tested successfully on Windows during development, but different projects may require other values. The sliders allow safe experimentation through 400%.
- The existing, separate legacy Deforum **create new project** import is not this workflow.

## More help

For a first animation, follow [Getting started](GETTING_STARTED.md) or the [New Project Wizard](NEW_PROJECT_WIZARD.md). If the import fails, verify the project uses the same FPS, frame count and cadence as the source file. Test a short camera preview before rendering a full animation.

Morphorum uses compatible export settings, not copied implementation source. Credit to [Deforum Motion Studio](https://github.com/chicodog530/Deforum-Motion-Studio) for the useful workflow and export format.
