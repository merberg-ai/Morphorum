# Contributing to Morphorum

Thanks for helping improve Morphorum. Contributions that make installation, image generation, animation and documentation more reliable are welcome.

## Before opening a pull request

1. Search [existing issues](https://github.com/merberg-ai/Morphorum/issues) for similar work. For larger changes, open an issue describing the problem and proposed approach first.
2. Work from an up-to-date feature branch; do not force-push or rewrite the public `main` history.
3. Keep changes focused and explain which user workflow they affect.
4. Add or update tests and documentation when user-facing behavior changes.
5. Open a pull request against the active development/integration branch (normally `dev-ui`), rather than changing `main` directly.

## Local setup for contributors

Use the normal [installation instructions](docs/INSTALLATION.md) to prepare a working environment. A separate test installation is recommended if you also have valuable saved projects.

Tests and GitHub Actions are explained in [Testing](docs/TESTING.md). The repository includes Python backend tests, Node-based browser logic tests, shell/PowerShell checks and installer smoke checks. Node.js is a **development requirement only**, not a normal end-user installation requirement.

## Design principles

- Preserve the existing browser workflow and compatibility with saved projects.
- Keep backend-only client APIs versioned and avoid unsafe assumptions about network trust or local filesystem paths.
- Use model-specific capabilities: SDXL, FLUX and Z-Image do not share every sampler, guidance value or text-encoder behavior.
- Keep desktop and mobile-browser layouts usable and long-running operations observable.
- Prefer clear error messages with recovery steps. Never include tokens, personal paths or authentication files in reports.
- Add regression coverage for changes to model handling, rendering, project files, launchers or installation.

## Licensing and third-party code

Morphorum is distributed under [The Unlicense](LICENSE). Do not copy, mechanically translate or lightly rewrite GPL/AGPL-covered Deforum or other incompatible code into the Morphorum core. Independent implementations based on publicly documented behavior and permitted file formats are welcome.

Document new third-party requirements in [THIRD_PARTY.md](THIRD_PARTY.md), and confirm their licenses before opening a PR.

## Reporting an issue

At [GitHub Issues](https://github.com/merberg-ai/Morphorum/issues), describe expected vs. observed behavior, reproduction steps, Morphorum version/branch, OS, GPU/model where relevant, and the **first meaningful error** from the app or terminal. Redact secrets before attaching any log or screenshot.
