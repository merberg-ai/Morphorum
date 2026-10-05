# Morphorum

Standalone, modern Deforum-style AI animation studio with legacy project compatibility, multi-model support for Stable Diffusion, SDXL, Flux, and Z-Image, LoRAs, keyframed motion, live previews, and a mobile-friendly web UI.

> **Status:** very early development. The repository is being initialized now; rendering code will land in staged milestones.

## Goals

Morphorum is intended to be a standalone, browser-based animation environment inspired by the workflow that made Deforum useful, while removing the dependency on Stable Diffusion WebUI/Forge.

Core goals:

- Import and preserve classic Deforum JSON/TXT projects.
- Preserve familiar prompt syntax such as `<lora:name:weight>`.
- Support SD 1.x/2.x, SDXL, Flux, Z-Image, and compatible LoRAs through model-specific adapters.
- Scan checkpoints, LoRAs, VAEs, embeddings, and ControlNet assets from configurable directories without copying them into Morphorum.
- Provide capability-driven model settings instead of pretending every architecture uses the same CFG/sampler/scheduler controls.
- Provide 2D/3D keyframed camera motion, cadence, depth, masks, hybrid/video workflows, and a modern timeline.
- Show live preview frames, progress bars, per-frame progress, ETA, GPU/VRAM telemetry, logs, queue state, pause/resume, and crash recovery.
- Be mobile-browser friendly from the beginning.
- Use a themeable responsive UI with a dark `Midnight Glass` theme by default, translucent/collapsible cards, touch-friendly controls, and simple/advanced modes.
- Make installation, updates, diagnostics, repair, and normal launching as close to one-click/one-command as practical.

## Quick install

### Windows PowerShell

Default install location (`$HOME\Morphorum`):

```powershell
irm https://raw.githubusercontent.com/merberg-ai/Morphorum/main/scripts/bootstrap.ps1 | iex
```

Custom install location, for example `D:\Morphorum`:

```powershell
& ([scriptblock]::Create((irm 'https://raw.githubusercontent.com/merberg-ai/Morphorum/main/scripts/bootstrap.ps1'))) -InstallDir 'D:\Morphorum'
```

You can also set `MORPHORUM_HOME` before running the normal one-line installer:

```powershell
$env:MORPHORUM_HOME='D:\Morphorum'; irm https://raw.githubusercontent.com/merberg-ai/Morphorum/main/scripts/bootstrap.ps1 | iex
```

### Linux

Default install location (`$HOME/Morphorum`):

```bash
curl -fsSL https://raw.githubusercontent.com/merberg-ai/Morphorum/main/scripts/bootstrap.sh | bash
```

Custom install location, for example `/home/foo/bar`:

```bash
curl -fsSL https://raw.githubusercontent.com/merberg-ai/Morphorum/main/scripts/bootstrap.sh | bash -s -- /home/foo/bar
```

You can also use `MORPHORUM_HOME`:

```bash
curl -fsSL https://raw.githubusercontent.com/merberg-ai/Morphorum/main/scripts/bootstrap.sh | MORPHORUM_HOME=/home/foo/bar bash
```

Install-location precedence is: explicit command-line path, then `MORPHORUM_HOME`, then the platform default.

The bootstrap scripts install or update Morphorum in the selected folder, then hand off to the platform installer. During this early scaffold phase they may report that application components have not landed yet instead of pretending there is a finished renderer hiding somewhere.

## Normal usage

After installation:

### Windows

```text
run.bat
```

LAN-accessible mode:

```text
run-lan.bat
```

Maintenance:

```text
update.bat
repair.bat
```

### Linux

```text
./run.sh
./update.sh
./repair.sh
```

## Project philosophy

Morphorum keeps the old Deforum project vocabulary where compatibility matters, but separates animation/orchestration from model inference. The Deforum-style engine owns schedules, prompts, transforms, cadence, depth, frame state, and rendering flow. Model adapters own architecture-specific inference details such as CFG/guidance behavior, compatible samplers/schedulers, text encoders, precision, LoRA application, and VRAM strategy.

The selected model should therefore drive its own configuration UI. SD, SDXL, Flux, and Z-Image are not the same architecture wearing different filenames, despite software occasionally behaving as though they are.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) and [docs/ROADMAP.md](docs/ROADMAP.md) for the current design baseline.

## Licensing

Original Morphorum code is dedicated to the public domain under the [Unlicense](LICENSE).

Morphorum is being developed as a clean-room implementation of compatible behavior. Code from projects with incompatible/copyleft licenses must **not** be copied into Morphorum's Unlicensed core. Third-party libraries and optional integrations retain their own licenses; see [THIRD_PARTY.md](THIRD_PARTY.md) and [NOTICE.md](NOTICE.md).

This distinction matters because several Deforum implementations and related projects are GPL/AGPL licensed. We can study documented behavior, formats, interfaces, and externally observable results while independently implementing compatible behavior, but directly incorporating their covered source would change the licensing obligations of the resulting work.

## Contributing

Contributions are welcome. Please read [CONTRIBUTING.md](CONTRIBUTING.md) before submitting code, particularly the clean-room/licensing rules.

## Repository

https://github.com/merberg-ai/Morphorum
