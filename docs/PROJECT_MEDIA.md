# Saved project media and editor restoration

Morphorum keeps project JSON and project-owned media in the host's `projects/<id>/`
directory. Browser-selected paths do not survive reload; **uploaded copies do**.

## Project-open workflow

1. Open the saved `project.json` through the regular project API.
2. Read `GET /api/animation/projects/<id>/media-inventory`. The response includes
   checksummed, server-owned asset descriptors and independently collected
   `warnings` for damaged/missing files. One corrupt asset does not hide other
   good files. No host filesystem paths are returned.
3. Restore the start-image preview through its project API URL. If the project
   still refers to an absent/undecodable source, warn, disable source-start
   rendering and allow Clear Image or a new upload. Do **not** silently clear
   the saved reference.
4. For an attached soundtrack, restore filename, offset and native playback
   through the saved audio download endpoint. Save offset changes through the
   pre-existing soundtrack-offset API.
5. Restore Motion Lab WAV playback from a saved asset. Prefer the WAV currently
   being edited, then the last saved audio layer's SHA-256; otherwise use the
   first available WAV. The dropdown allows selecting a different saved WAV.
   `GET /api/animation/projects/<id>/motion-lab/audio/<sha256>/analysis`
   verifies its checksum and analyzes it using the **saved project's** FPS
   and frame count without uploading from the browser.
6. Match the latest saved layer's beat controls to its WAV where available.
   Generated camera tracks, saved layers and unrelated project fields are
   not rewritten by media restoration.

The new **Saved Project Media** section belongs to the Project Editor and
works in phone, tablet and desktop layouts. The existing start-frame card
still owns uploading and previewing the source image. The Deforum import
page still owns attaching or replacing a soundtrack.

## Media layout

```text
projects/<project-id>/
  project.json
  assets/source.png                   (optional)
  imported_soundtrack/
    attachment.json                   (optional)
    <sha256>.<wav|mp3|ogg|flac>         (optional)
  motion_lab_audio/
    <sha256>.wav                       (optional, multiple supported)
```

These are **separate files**, not embedded into `project.json`. Backups and
manual transfers must include the complete project directory.

## Failure and concurrency behavior

- Missing/bad files appear in the media panel without rewriting JSON, deleting
  unrelated media or making project opening fail.
- Both inventory responses and saved WAV analysis responses are guarded
  against switching projects while a request is running. Manual WAV selection
  supersedes an automatic restore still in progress.
- Stored WAV analysis validates current project FPS and frame count. Editing
  frame count does not silently rewrite existing audio motion layers.
- The start image and audio files are only available while the Morphorum host
  still has the project directory. **An export of project.json alone is not a
  portable media backup.**
- Save/attach operations keep their original explicit behavior; simply
  opening a project never creates another render or changes its camera tracks.

## Validation

Run `node --test tests/frontend_project_media_restore.test.cjs` and
`python -m pytest tests/test_project_media_restore.py -q`, plus existing
frontend and backend regressions. In an actual browser, test projects with
no media, source only, attached soundtrack, saved Motion Lab WAV, all three,
several WAVs, and missing/corrupt assets. Verify that switching projects
does not show the previous project's audio or image.

Work is on `dev-webui`; keep `main` unchanged pending physical acceptance.

## W2 checkpoint — 2026-10-15

Project media restoration is implemented on `dev-webui` as one integration
batch. The project editor now has persistent media playback and offset controls,
verified inventory diagnostics and restored Motion Lab WAV analysis, including
saved audio-layer editing parameters. The server uses per-asset inventory
recovery and a checksum-verified WAV reanalysis endpoint.

Source-level validation: 5 new Node project-media tests + 10 existing
`frontend_dev_ui` tests pass in an in-memory test harness; JavaScript syntax
parses, and five additional integration checks pass. Four new Python tests
were added for valid and damaged assets, but the **full Python test suite and
GitHub Actions results have not been verified** from this remote session.
Physical Windows + Android/browser acceptance remains pending.

The W2 checkpoint commit is the rollback point for this batch. Do not
promote this implementation to `main` until it has been physically accepted.
