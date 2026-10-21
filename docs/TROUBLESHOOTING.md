# Troubleshooting Morphorum

This guide covers common installation, startup, model, rendering, and network problems. Start with the fix that matches the **exact error or symptom**.

If you are brand new, see [Getting started](GETTING_STARTED.md). For commands, paths, and maintenance details, see [Installation & maintenance](INSTALLATION.md).

## The installer does not start

**Windows:**

1. Download a fresh copy of [bootstrap.bat](https://raw.githubusercontent.com/merberg-ai/Morphorum/main/bootstrap.bat). An old file may contain bugs that have already been fixed.
2. Run it from a terminal so the error remains visible:

   ```powershell
   .\bootstrap.bat
   ```

3. Check internet access and that PowerShell can access GitHub.
4. If the installer says Git is missing, install [Git for Windows](https://git-scm.com/downloads/win) or use the installer-supported Windows Package Manager (`winget`).
5. If permissions or disk space are insufficient, try another folder with plenty of free space, such as `D:\Morphorum`.

**Linux:** ensure you have a functioning shell, Git, internet access, and write permission to the installation folder. Missing system packages may require `sudo`.

> [!TIP]
> The first install can take a long time because it downloads Python, GPU-aware PyTorch, and other dependencies. The optional AI checkpoint is a separate download.

## The browser says "This site can't be reached"

Check that the Morphorum launch window is still open and reports a running server.

- **Default address:** http://127.0.0.1:7865
- **Windows custom port:** the installer saves it in `data\server-port.txt`. The `run.bat` output also shows the current address.
- **Linux override:** `MORPHORUM_PORT_OVERRIDE=8080 ./run.sh`
- If you see a "port already in use" error, stop the other process or try another port. Windows: `.\run.bat -Port 8080`.
- Use **`http://`** rather than `https://` for a default local launch.

If the window closes immediately, run the command from PowerShell or another terminal to read the error:

```powershell
cd C:\Morphorum
.\run.bat
```

If your folder is not `C:\Morphorum`, substitute the actual install location.

## A phone or another computer cannot connect

Starting with `run.bat` or `./run.sh` permits local host access only. To use another device:

1. Make sure both devices are connected to the **same trusted LAN**.
2. Start **LAN mode**: `.\run-lan.bat` on Windows or `./run-lan.sh` on Linux.
3. Find the host computer's local IPv4 address (the Windows launcher attempts to list it).
4. On the other device, browse to `http://HOST_IP:7865`, replacing the address and port.
5. Check the host firewall if needed. Do **not** create a public router port-forward rule.

> [!WARNING]
> Morphorum's LAN service does **not** currently provide authentication. Do not expose it to public networks or the internet.

## First-run setup wizard does not appear, resume, or finish

- **Existing installation?** Onboarding does not automatically appear because models are absent. Use **Settings → Setup Wizard**, or restart the WebUI with `run.bat --setup-wizard` (Windows) or `./run.sh --setup-wizard` (Linux).
- **Installation unfinished:** Complete or repair the installation. The new installer marks setup ready only after its installation checks.
- **Setup revision conflict:** Another browser/tab updated setup state. Close and reopen the wizard to retrieve the current server-owned state. Do not manually reset `data/setup-state.json`.
- **Folder validation issue:** Enter an existing readable directory on the computer hosting Morphorum, check it, then **Save Folders & Scan**. A readable folder does not guarantee the right model family or that model weights can load.
- **Z-Image transfer still active:** **Not Now** continues onboarding; interrupted files are incomplete, not a usable model. Resume/retry when space and network are available. The full package is about 33 GB plus a disk reserve.
- **Example Animations cannot advance:** The catalog and model index may still be loading or unavailable. Refresh/reopen setup and inspect **Console**. If your selected checkpoint disappeared, choose another or **No model yet**.
- **Project saved but the Editor did not open:** Resolve any unsaved-editor prompt or ongoing render/recording, then retry. The same project ID is reused without overwriting your changes.
- **Finish Without Example:** Finishes onboarding with no model or render required. Create a normal project later through **Motion Lab → New Project Wizard**.
- **Backend-only:** Has no browser wizard. Do not combine `--setup-wizard` and `--backend-only`.

If the saved setup-state JSON is corrupted, preserve a backup for diagnostics rather than deleting it or user projects.

## Models are missing from the dropdown

- Open **Settings** and confirm your checkpoint and LoRA directories point to real locations.
- Open **Models** and refresh the model index. File scanning does not automatically download third-party checkpoints.
- Only supported model families can be loaded. The current runtime supports **SDXL**, **FLUX**, and **Z-Image**, not SD 1.x/2.x.
- If you downloaded managed Z-Image-Turbo, wait for it to show **Installed** and **Use Model**.
- Check that the model matches the intended family and file format.

## Civitai model or LoRA thumbnail still says NO PREVIEW

1. Confirm **Settings → Civitai Hub** is enabled, and **Load Previews** is on. Preview downloads are explicit, not background jobs.
2. Use **Identify on Civitai** if necessary, then **Sync Civitai Info** for the installed checkpoint or LoRA. Metadata success alone does not mean an image was downloaded.
3. Reopen **Models** or **LoRAs**. Their thumbnail cards use the local cache; they do not fetch images merely because the panel was opened.
4. Check the displayed state: **PREVIEWS OFF** means the preference is disabled, **PREVIEW HIDDEN** means mature-content filtering, **CACHE MISSING / IMAGE LOAD FAILED** means missing or unreadable cached artwork, and **NO IMAGE AVAILABLE** means there was no eligible still or an upstream/CDN fetch failed.
5. If the installed version has no example still, a clearly labeled representative preview from another version of the same SHA-verified Civitai model may be used. Never assume its example image was generated with your exact checkpoint version.

See the [Civitai synchronization and diagnostics guide](CIVITAI_MODEL_HUB.md#c51-no-preview-after-successful-metadata-sync). If you still see older behavior after the October 21 release, stop Morphorum, update your **current branch**, restart it and retry. Do not delete checkpoints or LoRA files to fix a missing preview.

## "No generation models available" banner stays visible

The translucent warning appears only after Morphorum successfully checks the model index and finds **no usable checkpoint**.

1. Select **Configure Models / Help** in the banner.
2. For the fastest setup, open **Models**, download managed **Z-Image-Turbo**, wait for the package to be verified, and click **Use Model**.
3. For existing SDXL/FLUX files, open **Settings**, add checkpoint directories on the **host computer**, save settings, return to **Models**, and select **Scan Models**.
4. LoRAs are optional additions to a compatible checkpoint. A LoRA-only directory does not clear the banner.
5. If models exist but the banner is still visible, rescan and check the **Console** for model-index errors. Refresh the browser after the scan if necessary.

The warning automatically disappears once the model index contains a usable checkpoint. See [New Project Wizard](NEW_PROJECT_WIZARD.md#before-you-start).

## New Project Wizard will not advance or save

Open **Motion Lab → New Project Wizard** and check the message on the current step.

- **Step 1:** The project must have a nonempty name (up to 120 characters).
- **Step 2:** Select an available generation checkpoint. Use **Refresh Models** after scanning, or open **Models / Download** or **Settings** from the wizard.
- **Step 3:** Choose valid frame count/FPS and dimensions divisible by eight. Large dimensions may still exceed your GPU's VRAM.
- **Step 4:** Enter an opening prompt. A second prompt, when supplied, needs a valid later frame inside the project.
- **Step 6 / Save:** Invalid generation schedules are rejected by Morphorum's existing backend validator. Review the field named in the error.
- A running preview, render, or recording can block switching to a newly created project. Finish the operation and retry.
- If your existing project has unsaved **Project Editor** changes, the wizard asks whether you want to discard them before creating and opening a new project.

**Save Project & Open Editor** creates the project only after validation. **Back** and **Next** don't create files. An unfinished wizard is only a browser-session draft, not a project saved in Project Manager. **Start Over** clears the draft after confirmation. See [New Project Wizard](NEW_PROJECT_WIZARD.md) for a full walkthrough.

## Z-Image-Turbo download is slow, incomplete, or unexpectedly large

- The full package is **about 33 GB**, not a tiny model file. Check your disk space and internet connection.
- Morphorum downloads the **complete** official `Tongyi-MAI/Z-Image-Turbo` Diffusers model. Text-to-image and image-to-image share it.
- The runtime now checks required model configurations and weight shards. A missing shard can make a partly downloaded package show as unavailable even if a completion marker exists.
- Let any active download finish. If the interface reports an error, check the **Models** status and **Console** details, then retry or repair as appropriate.
- Never delete or replace your entire `projects/` or `outputs/` directory while fixing a model download.

The source package is published at [Tongyi-MAI/Z-Image-Turbo on Hugging Face](https://huggingface.co/Tongyi-MAI/Z-Image-Turbo).

## Managed Z-Image Turbo generation with a LoRA fails with an inference-tensor error

On builds before the October 21, 2026 promotion, repeated Z-Image Turbo generations or animation with a LoRA could raise `Setting requires_grad=True on inference tensor outside InferenceMode is not allowed.` The fix now shipped on `main` uses the corrected managed Z-Image inference context while retaining model offloading. **Stop the server, update the checked-out branch and restart** before retrying with the same settings. The owner verified multiple still generations and an animation; this does not prove every LoRA setup is covered. If the exception still occurs, record the first complete traceback, model, LoRA name/weight and whether the same render succeeds without the LoRA, while excluding private paths and tokens. Do not solve it by forcing all managed model weights into limited GPU VRAM. See [TODO.MD](../TODO.MD) for the separate still-open ZT1 temporal-continuity investigation.

## CUDA is unavailable, or generation runs on the CPU

On a Windows machine with an NVIDIA GPU:

1. Make sure the NVIDIA driver is installed and current enough for the configured PyTorch CUDA build.
2. Open PowerShell and run `nvidia-smi`. If it fails, check the driver installation.
3. From the Morphorum installation directory, run `.\repair.bat`. The installer checks CUDA availability and runs a GPU tensor smoke test when it detects NVIDIA.
4. Close other GPU-heavy programs and retry.

The installer manages Python/PyTorch; mixing it with a different system Python environment usually makes troubleshooting harder. Avoid manually changing the packages in `.venv` unless you are deliberately debugging.

**CPU fallback may work for certain operations, but full AI generation can be extremely slow without an appropriate accelerator.**

## Out-of-memory or extremely slow generation

These issues depend on **model size, image dimensions, number of diffusion steps, precision/offload settings, and other GPU loads**.

Try these in order:

1. Reduce image or animation resolution to a recommended preset.
2. Reduce batch size or simultaneous GPU work.
3. Close programs using GPU memory (other AI runtimes, games, or 3D software).
4. Test a **single image** before starting a long animation.
5. Check the app's Console and memory telemetry for the actual failure.

Avoid assuming that a 1024 × 1024 still-image generation speed will match a multi-hundred-frame animation: animation can also involve depth estimation, warping, frame blending, and repeated img2img inference.

## SDXL long prompts, chunking and LoRA initialization reports

For SDXL, a long-looking prompt is not automatically truncated. Check the **actual conditioning status** during image/animation rendering. `CHUNKED` confirms the encoder produced multiple CLIP chunks; `STANDARD` means the native short-prompt path was used. The editor character-length notice is only a heuristic. A genuinely unavailable SDXL text encoder/tokenizer or an exceeded safety limit should be investigated rather than ignored.

A Transformers `MISSING` adapter report or a PEFT warning that an active adapter was deleted can occur during initial LoRA injection or a compatibility retry. Check the **subsequent Morphorum LoRA verification** in the render view and Console. `CLIP weights matched checkpoint` confirms the compatibility loader's tensor-value comparison; `Active; source weight comparison unavailable` does **not** mean a source-value check occurred. `UNet-only fallback` means CLIP LoRA weights were not applied. Explicit checkpoint mismatch, incomplete payload, or failed activation messages require action; reduce LoRA complexity and inspect checkpoint compatibility.

For more, see the [SDXL generation guide](SDXL_GENERATION.md) and [release acceptance checklist](G5_RELEASE_ACCEPTANCE.md).

## A Motion Lab preview or render button is disabled

Morphorum prevents incompatible actions from running simultaneously. A busy button may be intentionally disabled while recording, updating curves, previewing camera motion, applying layers, or rendering animation.

- Wait for the current action to finish.
- Confirm the project is open and the model is selected.
- Ensure the project has valid prompts, resolution, and other required inputs.
- Read any error shown in **Render Monitor**, **Models**, or **Console**.
- If the operation has finished but the control appears stuck, refresh the UI and check whether the job is still running server-side.

**Camera Preview is not the same as AI rendering.** It helps validate motion but does not replace a real diffusion run.

## Video export fails or FFmpeg is missing

For source-selection screenshots-free instructions, local-managed download troubleshooting, license notes and the CPU-only acceptance command, see [FFmpeg Manager](FFMPEG_MANAGER.md).


Open **Settings → Storage → FFmpeg Manager**. Set **Auto-detect** to use
the FFmpeg available in the host's `PATH`, optionally overridden by the
legacy `MORPHORUM_FFMPEG` environment variable. Select **Custom executable**
to point to the complete `ffmpeg.exe` (Windows) or `ffmpeg` (Linux)
executable path. Choose **Test FFmpeg / FFprobe**, then **Save Settings**
to activate a tested selection. Testing alone does not change your settings.

You can also check from a terminal:

```text
ffmpeg -version
ffprobe -version
```

If `ffmpeg` is missing, install it or provide a custom path. The Windows
installer may offer a `winget` setup; Linux distributions generally provide
both binaries through their package manager. If **FFmpeg ready / FFprobe
missing** appears, ordinary video exports may still work, but hybrid video
inspection requires FFprobe from the same installation. For explicit Custom
or Managed modes Morphorum will not silently switch to another FFmpeg.

Choose **Morphorum-managed local FFmpeg**, then click **Install managed
FFmpeg**. Morphorum downloads the static FFmpeg and FFprobe pair directly from
the BtbN GitHub release, validates its published SHA-256 digest, checks both
executable versions, and installs it under `tools/ffmpeg/current/bin`. The
package is approximately 100–200 MB depending on host architecture. Downloads
are never automatic. After installation, click **Save Settings** to activate
Managed mode. **Cancel download**, **Update / Reinstall**, and **Remove** are
available in the same card. These operations do not delete any video output
or externally installed FFmpeg binaries.

Managed downloads currently support Windows x64/ARM64 and Linux x64/ARM64 with
a compatible runtime (BtbN Linux builds require recent glibc). Other hosts
can use Auto or Custom. Downloading requires GitHub access; running already
installed binaries does not. The static **GPL build** includes encoders used
by Morphorum's MP4 pipeline, so review the BtbN licensing and
[FFmpeg licensing information](https://ffmpeg.org/legal.html). Installation
records, a license notice and upstream source links are saved with the files.

If an update or removal fails because files are in use, finish active
video exports or extractions and retry. Existing verified installations are
preserved on package checksum or extraction failure. If a download fails,
check network access to GitHub and try Install again; a failed attempt does
not replace a previously functioning managed copy.

Also check available disk space, that the render actually completed, and whether the chosen export format is supported by the current pipeline.

### FFmpeg acceptance checks (no GPU needed)

Run the temporary-media smoke test after installing and saving the selected
FFmpeg mode. It creates and removes test PNGs/WAVs/videos in a temporary
directory; it does **not** edit project media or download models.

Windows PowerShell:

```powershell
.\.venv\Scripts\python.exe scripts\ffmpeg_acceptance.py --mode managed
```

Linux:

```bash
./.venv/bin/python scripts/ffmpeg_acceptance.py --mode managed
```

For a system installation, use `--mode auto`. For a custom installation,
use `--mode custom --custom-path "/full/path/to/ffmpeg"`.
Omit `--mode` to use your saved Morphorum Settings.

The script checks MP4 (libx264/AAC), WebM (libvpx-vp9/Opus), FFprobe metadata,
hybrid frame extraction, and MP3/OGG/FLAC-to-PCM WAV conversions. If it reports
a missing codec, install a package with all necessary codecs or select
another FFmpeg installation. A working `ffmpeg -version` by itself is not
enough to confirm compatibility.

BtbN Linux static builds require glibc 2.28+ and kernel 4.18+; Alpine/musl
systems should use a compatible system/custom binary. FFmpeg managed install
does not ask for administrator privileges.

## Project is missing or was moved to Trash

Look under **Motion Lab → Project Manager**. The manager lists projects from the application-managed `projects/` directory.

- Moving a project to Trash relocates its managed files to the project's `.trash` area; it is **not** an automatic restore-button workflow.
- Separately stored completed renders and exports are not removed by moving a project to Trash.
- Check that you launched the **correct Morphorum installation folder**: a second installation has its own independent `projects/` and `data/` directories.
- Do not modify project files manually while a render or preview is active.

For accidental data loss, use your own backup rather than assuming the updater copied the entire project library.

## Updater refuses to run because of local changes

The guarded updater stops if Git-tracked application files have uncommitted changes. This is intentional.

- If you edited source code, commit it to your own branch or save a copy outside the repo.
- If you only want to update, check what changed before taking action: `git status`.
- **Do not blindly run `git reset --hard` or delete your installation**, because tracked edits and important work may be lost.
- The updater also records previous commit/branch information in the `backups/` directory.

Windows updates: `.\update.bat` or `.\update.bat main`. Linux: `./update.sh` or `./update.sh main`.

## Backend-only mode returns 401, 404 or cannot connect

Backend-only mode is a **token-protected API**, not the browser interface. Opening its root URL returns **404** by design. An API request with no or invalid bearer token returns **401**.

- Start it using `.\run.bat --backend-only` (Windows) or `./run.sh --backend-only` (Linux), normally on port **7866**.
- Add `--lan` if another computer on your trusted private network needs to connect, and enter the host's actual LAN IP, not `0.0.0.0`.
- Use an issued per-client token, not a password. Reissue or revoke credentials locally on the backend computer if needed.
- Check your firewall and verify the backend server remains running.
- Never post `data/backend-access-token`, exported client tokens, or raw Authorization headers in a bug report.

See [Backend-only setup and security](BACKEND_ONLY.md) for correct commands, an authenticated health check and supported remote client behavior.

## Where to find logs

Inside your installation folder, check:

- `logs/install.log` for initial setup
- `logs/update.log` for updates
- `logs/repair.log` for diagnostics/repair
- **Console** inside the Morphorum UI for application/runtime messages
- The terminal running `run.bat` or `run.sh` for startup errors

When reporting a problem, include the **first meaningful error**, operating system, GPU, Morphorum branch/version, and what you clicked or ran. Remove any private file paths, tokens, or personal information before posting public logs.

[**Open a GitHub issue**](https://github.com/merberg-ai/Morphorum/issues/new) · [Return to the README](../README.md)
