# FFmpeg Manager

Morphorum uses **FFmpeg** to encode animation videos (MP4/WebM), extract frames from source videos and convert audio. **FFprobe** reads media duration, streams and technical details. Both tools run on the computer hosting Morphorum, not in the browser.

Morphorum does **not** require a global FFmpeg installation. You can choose between an existing system installation, a custom executable or Morphorum's optional managed installation.

## Select your installation

1. Open **Settings → Storage → FFmpeg Manager** in the WebUI.
2. Choose one of the following options.

| Source | Use when | What Morphorum does |
| --- | --- | --- |
| **Auto-detect** | FFmpeg is already installed | Finds FFmpeg on the host PATH, or uses the legacy `MORPHORUM_FFMPEG` environment override when configured |
| **Custom executable** | You have an existing standalone installation | Uses the **absolute path** to `ffmpeg.exe` (Windows) or `ffmpeg` (Linux), with **FFprobe alongside it** |
| **Morphorum-managed local FFmpeg** | You want Morphorum to handle the download | Installs FFmpeg **and FFprobe** below `tools/ffmpeg/current/bin` in your Morphorum folder |

3. Click **Test FFmpeg / FFprobe** to validate the selection. The test checks executable versions on the **host**.
4. Click **Save Settings** to activate the chosen source. **Testing alone does not save** your selection.

If you explicitly choose Custom or Managed and the selected binaries are absent or invalid, Morphorum **does not silently switch** to another installation. Fix your selection or choose Auto-detect.

## Install Morphorum-managed FFmpeg

Managed installation is supported for **Windows x64/ARM64** and compatible **Linux x64/ARM64** systems. For Linux, the selected upstream binaries require **glibc 2.28+ and Linux kernel 4.18+**. Unsupported systems can use an externally installed Auto or Custom pair.

1. Open **Settings → Storage → FFmpeg Manager**.
2. Select **Morphorum-managed local FFmpeg**.
3. Click **Install managed FFmpeg**. This is always a **manual opt-in**: opening the WebUI or selecting Managed never starts a download.
4. Follow the progress in Settings. The Runtime **Console** reports the download, SHA-256 verification, extraction, executable checks and failures.
5. Once installation completes, click **Test FFmpeg / FFprobe** and **Save Settings**.

The installer downloads an upstream **BtbN FFmpeg-Builds** static GPL package directly from GitHub. It checks the published archive size and **SHA-256 digest**, safely extracts the FFmpeg/FFprobe executables, verifies both `-version` responses and confirms that FFmpeg contains the **libx264, libvpx-vp9, AAC and libopus encoders** Morphorum uses for MP4/WebM. Only then does it activate the new installation. The upstream release package may be large, so allow disk space for the download and temporary extraction as well as the final binaries.

A managed install never modifies the system PATH, installs FFmpeg for other applications or requires a system-level package manager. You can keep an external FFmpeg installation alongside it.

### Maintenance, updates and removal

The FFmpeg Manager also provides **Update / Reinstall**, **Cancel download** and **Remove managed FFmpeg**. These actions apply only to Morphorum's managed files, not to your models, projects or rendered videos.

- **Update / Reinstall:** Downloads and validates a new upstream build before switching the managed installation. A failed download or verification normally leaves the previous installation unchanged.
- **Cancel:** Requests cancellation of an in-progress download or installation. The operation may take until the current network read finishes.
- **Remove:** After confirmation, removes Morphorum's managed binaries; it does **not** remove a separately installed FFmpeg or existing videos.

Install/removal is blocked while tracked video exports or hybrid extractions are active. When an update reports files in use, finish the job and retry.

**Restart behavior:** The selected source is stored in Morphorum's Settings. The managed installation remains on disk when Morphorum restarts. The download progress itself is tied to the current running backend; an interrupted download may need to be retried.

## Verify a managed installation

To run **CPU-only** encoding, probing and conversion tests on your host, from the Morphorum installation folder:

**Windows PowerShell**

~~~powershell
.\.venv\Scripts\python.exe scripts\ffmpeg_acceptance.py --mode managed
~~~

**Linux**

~~~bash
./.venv/bin/python scripts/ffmpeg_acceptance.py --mode managed
~~~

The script creates temporary synthetic PNG frames and audio, checks **MP4/H.264 + AAC**, **WebM/VP9 + Opus**, media probing, source-video frame extraction and MP3/OGG/FLAC-to-WAV conversion, then cleans up. It does **not** access your GPU, modify projects or move existing outputs.

You can also use `--mode auto`, or `--mode custom --custom-path "C:\full\path\to\ffmpeg.exe"` (adjust for your host).

These tests do not replace a full GPU-driven animation and export test. The Windows managed installer and media acceptance script passed a user-operated test on October 16, 2026. Linux managed-install testing and certain interrupted-operation edge cases still require coverage.

## Troubleshooting

**FFmpeg found but FFprobe missing:** Ensure `ffprobe` is available beside the explicitly chosen custom executable. For Auto-detect, check both programs on PATH. Some video exports may work without FFprobe, but source media inspection needs it.

**Download or install failed:** Expand **Console → Runtime** to see the stage and error. Verify that GitHub is reachable, you have adequate free disk space and write permission, then retry **Install**. A SHA-256 or archive safety error means Morphorum refused the package; do not bypass that check.

**Wrong source after installation:** Choose Managed, test it, and **Save Settings**. The managed download does not automatically overwrite a saved Auto/Custom selection.

**Update/remove blocked:** Stop ongoing video encoding or frame extraction before retrying. Avoid manually deleting a managed installation while an export is running.

**Linux says unsupported:** Check CPU architecture, glibc and kernel compatibility; install FFmpeg/FFprobe through your distribution and choose Auto or Custom.

Additional guidance: [Troubleshooting](TROUBLESHOOTING.md#video-export-fails-or-ffmpeg-is-missing) and [Testing](TESTING.md).

## License and source

**Morphorum's Unlicense does not change FFmpeg's license.** Managed binaries are **third-party, GPL-licensed FFmpeg builds**, downloaded separately at your request. The executable and its dependencies retain their own license requirements. The app writes a local provenance record and license notice alongside the managed installation.

- [BtbN FFmpeg-Builds](https://github.com/BtbN/FFmpeg-Builds)
- [FFmpeg source](https://github.com/FFmpeg/FFmpeg)
- [FFmpeg licensing](https://ffmpeg.org/legal.html)

See the repository's [Third-party software](../THIRD_PARTY.md) and [Notices](../NOTICE.md). Morphorum does not ship these third-party executables in its Git repository.
