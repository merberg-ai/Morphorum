# Backend integration into dev-ui and main — 2026-10-14

## Outcome

**PASS — integrated.** Morphorum DB1 and DB2.1–DB2.5 remote/backend-only support is included in `main`, preserving normal browser-mode launch and the separate native Morphorum Studio API contract.

- Original `dev-ui`: `661d029a267bc8c9b6fb01995f46a7ab4b323711`
- Original `main`: `5a14fb52141000ce0316aa7372ffa3e1610a86b1`
- Accepted `dev-backend`: `2046d36ff6e084d801a14e2024d14665c207d884`
- Post-integration `dev-ui` head before `main` promotion: `2046d36ff6e084d801a14e2024d14665c207d884`
- `main` backend merge (PR #32): `0cb5d489e27b5193fac8dd075d418b8e324beddd`
- Verified identical source trees between accepted DB2.5 feature checkpoint `51e1ecf33d1b617d32f48252765bf2272c8e7335`, integrated backend `2046d36f`, and `main` merge `0cb5d489`: Git tree `8830d9ce9be3541787f28015dc2ad8d4d69fcaf1`. The integration merge commits changed commit ancestry, **not the checked-out files**.

## Release sequence

1. Created recovery refs for pre-integration `main`, `dev-ui` and `dev-backend` without changing those branches.
2. Draft [PR #33](https://github.com/merberg-ai/Morphorum/pull/33) staged the accepted backend commit onto `dev-ui`. Candidate CI passed, then `dev-ui` advanced **non-force / fast-forward-only** from `661d029a` to `2046d36f`. PR #33 was automatically marked merged by GitHub.
3. All fresh push workflows on promoted `dev-ui` succeeded: [backend](https://github.com/merberg-ai/Morphorum/actions/runs/38565651899), [syntax/browser](https://github.com/merberg-ai/Morphorum/actions/runs/38565651852), [installer](https://github.com/merberg-ai/Morphorum/actions/runs/38565651835).
4. The user reported physical **PASS** on 2026-10-14 testing the integrated `dev-ui` checkout: Morphorum Studio connection, normal/browser mode, and backend-only mode worked as expected.
5. Marked [PR #32](https://github.com/merberg-ai/Morphorum/pull/32) ready for review and merged it normally into `main` with GitHub merge commit `0cb5d489` (parents `5a14fb52` and `2046d36f`).
6. Post-merge documentation is maintained in a separate documentation-only commit/PR to avoid changing the accepted source tree during code promotion.

## Prior acceptance and test limitations

The original Windows RTX GPU / Ubuntu Mini remote test matrix for DB1–DB2.5 passed: remote still generation, animation preview/output, disconnect/reattach, completed output after backend restart, idempotent lost-response replay, SHA-256 transfers, FFmpeg MP4 and WebM exports with audio, and normal Windows browser GPU functions. DB2.5 scripted physical tests recorded **41/41 PASS** and the separately user-accepted browser-mode Gate F. Combined backend integration CI had **536 passed, 1 skipped** prior to promotion.

The 2026-10-14 repeat was a focused **connection and two-startup-mode smoke test**, not a fresh rerun of every image/animation/export case. The exact tree identity carries forward the prior tested backend code, not untested claims about every Studio feature.

Limits remain: a real server restart interrupts active GPU work; keyed submission is single-host scoped, not distributed exactly-once; historical SSE event replay is not durable; bearer credentials over untrusted plaintext HTTP are exposed; the ordinary web-LAN mode is unauthenticated. Never internet-expose either service unprotected. The native Studio repository is independent and must maintain its own application acceptance.

## Recovery checkpoints (do not delete)

| Checkpoint branch | SHA |
| --- | --- |
| `checkpoint/main-before-backend-promotion-20261014` | `5a14fb52141000ce0316aa7372ffa3e1610a86b1` |
| `checkpoint/dev-ui-before-backend-promotion-20261014` | `661d029a267bc8c9b6fb01995f46a7ab4b323711` |
| `checkpoint/dev-backend-pre-integration-20261014` | `2046d36ff6e084d801a14e2024d14665c207d884` |
| `checkpoint/dev-ui-backend-integration-ci-verified-20261014` | `2046d36ff6e084d801a14e2024d14665c207d884` |

Rollback should use a separate recovery branch/worktree, project/data backups, and a reviewed revert PR when necessary. **Do not hard-reset, force-push `main`, or discard user projects/outputs** to recover an installation.

## Integration policy going forward

- Treat `main` as the approved baseline; keep `dev-ui` synchronized after all closeout changes.
- Preserve `dev-backend` and milestone/checkpoint refs for diagnosis. Avoid silent deletion.
- Keep unrelated `dev-audio` / PR #25 isolated.
- Studio API compatibility checks should use `api_contract_version=1` and feature advertisement, never branch-name assumptions.
- Development continuation belongs in [Morphorum-Studio](https://github.com/merberg-ai/Morphorum-Studio) for native client work, and `dev-ui` / feature PRs for new Morphorum web/backend changes.
