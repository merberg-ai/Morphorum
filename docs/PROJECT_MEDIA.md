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

These are **separate files**, not embedded into `project.json`. For a manual filesystem backup, copy the entire project directory. For **portable settings plus attached inputs**, use **Project Manager → Export ZIP**, which includes these owned files with a verified manifest while intentionally excluding renders and caches. The reverse **Import Project ZIP** restores them into the managed project library. See [Project archives & Save As](PROJECT_ARCHIVES.md).

## Failure and concurrency behavior

- Missing/bad files appear in the media panel without rewriting JSON, deleting
  unrelated media or making project opening fail.
- Both inventory responses and saved WAV analysis responses are guarded
  against switching projects while a request is running. Manual WAV selection
  supersedes an automatic restore still in progress.
- Stored WAV analysis validates current project FPS and frame count. Editing
  frame count does not silently rewrite existing audio motion layers.
- The start image and audio files are only available while the Morphorum host
  still has the project directory or a complete portable project archive. **An export of project.json alone is not a portable media backup.**
- **Save Project As** duplicates project settings and attached inputs under a new project ID. It does not duplicate generated renders and does not change the original project.
- Importing a conflicting project ID requires confirmation and moves the replaced project folder into managed Trash for recovery; render output remains separate.
- Save/attach operations keep their original explicit behavior; simply
  opening a project never creates another render or changes its camera tracks.

## Validation

Run `node --test tests/frontend_project_media_restore.test.cjs` and
`python -m pytest tests/test_project_media_restore.py -q`, plus existing
frontend and backend regressions. In an actual browser, test projects with
no media, source only, attached soundtrack, saved Motion Lab WAV, all three,
several WAVs, and missing/corrupt assets. Verify that switching projects
does not show the previous project's audio or image.

For full test-suite instructions, see [Testing and validation](TESTING.md). For end-user media recovery and backup guidance, see [Troubleshooting](TROUBLESHOOTING.md) and [Installation](INSTALLATION.md).
