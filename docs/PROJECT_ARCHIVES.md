# Portable project archives and Save Project As

Morphorum can transfer or duplicate animation projects without including rendered outputs.

## Project Manager actions

In **Project → Project Manager**, select a project, then:

- **Export ZIP:** Download the saved project configuration and verified project-owned input files. Save pending Editor changes first.
- **Import Project ZIP:** Select a ZIP. Morphorum validates its format, manifest, paths, lengths, SHA-256 digests, and attached media. Confirm import, then choose whether to load the imported project.
- **Save Project As:** Enter a new name in Morphorum's modal. Create a new project ID with the full configuration and all attached inputs; the original is unchanged. If it is open in Editor, current unsaved Editor settings are included in the new copy only. Morphorum asks whether to load it.

**Project Editor** also has a **Save Project As** button beside **Save Project**.

## Included and excluded media

| Included | Excluded |
| --- | --- |
| Entire project.json: model settings, prompts/keyframes, motion, schedules, audio offsets | Generated images and animation frames |
| Uploaded start image (assets/source.png) | Rendered videos and exports |
| Soundtrack attachment.json and its verified audio (WAV, MP3, OGG, FLAC) | Depth caches and temporary analysis |
| Project-owned Motion Lab WAV inputs | Checkpoint models, LoRAs, and external libraries |

Model IDs remain references. Configure compatible model and LoRA libraries on the destination installation.

## Archive format and safety

A Morphorum project archive contains a manifest.json with the magic value morphorum.project.archive, version 1, project ID/name, and a SHA-256 hash and size for each payload. Only the expected project.json and input-media paths are accepted. Import rejects missing or unexpected members, duplicate paths, symlinks, traversal, corrupt digests, invalid media formats, inconsistent identity and unsupported project schema.

The size limits are **256 MiB compressed**, **512 MiB expanded**, **128 entries** and **40 MiB per input file**. These prevent unbounded uploads and ZIP-bomb extraction. Archive hashes detect corruption and tampering but do not authenticate the publisher of a file.

If an import encounters the same project ID, Morphorum requires typing the exact project name before overwrite. The previous folder is moved to managed project Trash with an archive-backup suffix; existing generated outputs outside the project are untouched. Validation failure must leave existing projects intact.

## Windows and mobile acceptance

1. Save a project with prompts, source image, soundtrack and Motion Lab WAV. Export ZIP and confirm no rendered outputs are present.
2. Import on an installation without that ID. Confirm all project settings and media restore correctly; accept or decline the **Load Project** prompt.
3. Import again and test overwrite confirmation and the Trash backup.
4. Use **Save Project As** from both Manager and Editor, including with unsaved prompt edits. Check the original is unchanged and the new project has the expected media.
5. Attempt a generic ZIP and a tampered archive. Both should fail without altering projects.

Automated coverage: tests/test_project_archive.py and frontend Project Manager regression tests. Physical Windows and mobile acceptance remain pending before merging to main.
