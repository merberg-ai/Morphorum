# Contributing to Morphorum

Morphorum is intended to be community-built, approachable, and technically serious.

## Before contributing

1. Keep the core standalone and browser-based.
2. Preserve classic Deforum project/prompt compatibility where practical.
3. Do not hard-code assumptions that all model families share SD-style CFG, samplers, schedulers, or text encoders.
4. Mobile-browser usability is a requirement, not an optional responsive pass at the end.
5. Long-running work must expose meaningful state/progress to the render job system.
6. New model support belongs behind the model-adapter/capability interfaces.

## Licensing / clean-room rule

Original Morphorum code is Unlicensed. Do not copy, paste, mechanically translate, or lightly rewrite GPL/AGPL-covered source into Morphorum's core. Implement compatible behavior independently from public documentation, permitted test data, file formats, and observable behavior.

If a contribution needs third-party source or vendoring, document it in `THIRD_PARTY.md` and verify compatibility before submitting it.

## Development style

- Prefer small, testable modules over UI-coupled inference code.
- Treat project schemas and capability manifests as versioned APIs.
- Add tests for legacy settings/schedule compatibility.
- Error messages shown to users should explain the recovery action; technical tracebacks belong behind an expandable detail view/log.
- Do not silently reinterpret model-specific parameters when switching architectures.
