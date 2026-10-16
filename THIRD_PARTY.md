# Third-party software

Morphorum is intentionally starting with a clean-room core. This file will track runtime/build dependencies and any bundled third-party material as those dependencies are introduced.

## Compatibility references

The project may study public behavior, documentation, formats, and interfaces from projects including Deforum, Stable Diffusion WebUI, Forge, Diffusers, and related model ecosystems. Reference does not mean source code is incorporated.

## Optional managed FFmpeg and FFprobe

Morphorum's **FFmpeg Manager** can fetch an optional upstream static **GPL** build containing FFmpeg and FFprobe for Windows/Linux. The binaries are downloaded only after a user requests installation; they are **not included in this source repository**, and the original Morphorum code remains separately distributed under the Unlicense.

- **Provider:** [BtbN FFmpeg-Builds](https://github.com/BtbN/FFmpeg-Builds), managed FFmpeg 8.1-family GPL static build
- **Source:** [FFmpeg](https://github.com/FFmpeg/FFmpeg)
- **Licensing:** [FFmpeg legal / LGPL and GPL details](https://ffmpeg.org/legal.html); the downloaded build and any linked GPL components retain their own obligations
- **Installation location:** `tools/ffmpeg/current/bin`, with `installation.json` for the resolved artifact URL, SHA-256 and package provenance, and a local `LICENSE-NOTICE.txt`
- **Distribution:** No third-party FFmpeg binary is bundled in Morphorum's Git tree. The download is user-initiated and verified against GitHub's published SHA-256 release digest. Redistribution of FFmpeg builds by others must satisfy the applicable licenses.

See [FFmpeg Manager](docs/FFMPEG_MANAGER.md) for supported hosts and instructions.

## Rule for contributors

Before adding vendored code, copied code, patched third-party source, model files, binaries, fonts, or other redistributable assets, document:

- upstream project and source URL
- exact version/commit
- license
- what is redistributed or modified
- required notices/source-offer obligations

If the license is incompatible with Morphorum's current Unlicense strategy, do not merge the code into the core repository without an explicit project-level licensing decision.
