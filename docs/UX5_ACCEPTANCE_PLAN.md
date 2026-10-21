# UX5 combined WebUI acceptance (historical checklist)

> **Release reconciliation (2026-10-21):** UX5 Windows acceptance was reported on October 16, and the affected WebUI changes were subsequently promoted to published `main`, including the [PR #51](https://github.com/merberg-ai/Morphorum/pull/51) consolidation. Current release checks passed; physical mobile checks remain deferred. Failures and "do not merge" wording below describe **earlier checkpoints**, not current published code. Do not convert unrecorded device, audio alignment or edge-case tests into PASS.

## Original automated gate (historical pre-fix failures)
- Syntax checks: FAIL, 12 of 236 frontend Node tests failing as of UX4.2 head e591825. Some assertions still expect Project Manager, Wizard and Editor inside Motion Lab, despite UX2.4 moving them to primary navigation. Other WAV/media tests need behavioral triage, not blanket assertion removal.
- Backend tests: FAIL, 1 of 791 (789 passed, 1 skipped). Exact keyframe 0.09 was clipped to 0.08 by the generated camera safety patch; a follow-up patch preserves explicitly authored keyframe and recording axes. Re-run required.
- Installer checks: PASS at UX4.2 head.
- No full browser or GPU CI confirmation; pending.

## UX5 CI cleanup checkpoint (2026-10-16)

- Updated previously stale frontend navigation assertions to reflect three project destinations in the primary menu, not the Motion Lab sidebar.
- Updated the WAV analyzer and project media restoration test harnesses to include new soundtrack/selection state.
- At commit `25eafd2`, GitHub **Syntax checks PASS** (including all frontend Node regressions) and **Installer checks PASS**.
- **Backend tests PASS** at commit `25eafd2`, alongside Syntax checks and Installer checks. All three required CI workflows completed successfully.
- The prior backend regression from clipping a manually authored camera keyframe was fixed and had a confirmed passing backend workflow at commit `51294fc`.

## Windows and mobile owner acceptance
- Primary project destinations each open correct workspace and contextual heading, Motion Lab opens Overview, Motion Studio appears immediately after Overview. Test 360px phone, 720px tablet, desktop, 200% zoom.
- Project Manager search/sort, Select All Visible, Clear Selection, one selected project triggers exact-name verification, two selected trigger one batch confirmation, failure reports remain distinct. Use disposable projects; confirm trash is recoverable without erasing outputs.
- Project Editor five sections fit content width, save state stays accurate across switching, keyboard Left/Right/Home/End works, compact picker appears on phone. Confirm unsaved fields survive each navigation and save/reload correctly.
- Motion Studio loads stored soundtrack, analyzes waveform, lets users assign beats and remove multiple camera cues with Undo, then save/preview/apply; verify next render/export includes attached soundtrack. Existing completed render snapshots are unchanged.
- Check Render with applied Motion Studio cues; ensure generated camera translations remain within safety safeguards without changing explicitly hand-authored camera keyframes. Confirm actual short animation render and video export.
- Test stale media/project switching and pending async analysis; ensure old requests do not overwrite the newly selected project.

## Release gate
- Repair and rerun frontend and backend CI; tests must reflect intended new navigation rather than the old sidebar.
- Record actual Windows, mobile and GPU smoke outcomes. Don't mark unchecked cases passed.
- Update public user-facing docs only after final behavior is verified.
- At that milestone, main promotion still required explicit authorization; the eventual release was approved and merged.

## Mobile acceptance disposition (owner decision, 2026-10-16)

**DEFERRED:** Owner explicitly postponed physical mobile verification to a later milestone. This is not a PASS and is no longer a blocker to starting P5 development on `dev-webui`. The remaining mobile acceptance checklist stays open for a future session. UX5 Windows/GPU acceptance and CI results stand independently; `main` promotion was still pending at this historical checkpoint; it has since occurred.

## Owner Windows acceptance (2026-10-16)

**PASS:** Owner reports the combined UX5 Windows test successful and supplied a rendered/exported MP4. The uploaded export was independently inspected: H.264 video, 832×1216 at 24 fps, duration 9.875 seconds, plus an AAC audio stream. This verifies an audio track exists, not subjective A/V synchronization. Earlier checks include Project Manager bulk trash, contextual navigation, Editor layout, cue bulk delete, and soundtrack attachment. Automated Syntax, Backend, and Installer workflows all passed at source commit `25eafd2`.

**Remaining nonblocking release review:** a dedicated physical phone/mobile check and final public documentation review have not been independently reported as complete. Do not treat mobile or frame-accurate audio sync as tested. This was the remaining release gate at the historical checkpoint; the later owner-approved main promotion is complete.
