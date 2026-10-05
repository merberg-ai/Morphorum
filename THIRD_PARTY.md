# Third-party software

Morphorum is intentionally starting with a clean-room core. This file will track runtime/build dependencies and any bundled third-party material as those dependencies are introduced.

## Compatibility references

The project may study public behavior, documentation, formats, and interfaces from projects including Deforum, Stable Diffusion WebUI, Forge, Diffusers, and related model ecosystems. Reference does not mean source code is incorporated.

## Rule for contributors

Before adding vendored code, copied code, patched third-party source, model files, binaries, fonts, or other redistributable assets, document:

- upstream project and source URL
- exact version/commit
- license
- what is redistributed or modified
- required notices/source-offer obligations

If the license is incompatible with Morphorum's current Unlicense strategy, do not merge the code into the core repository without an explicit project-level licensing decision.
