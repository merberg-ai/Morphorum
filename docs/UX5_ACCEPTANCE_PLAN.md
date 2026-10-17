# UX5 combined WebUI acceptance (dev-webui)

This is a development-only checklist. Do not merge to main before user acceptance and green CI.

## Current automated gate
- Syntax checks: FAIL, 12 of 236 frontend Node tests failing as of UX4.2 head e591825. Some assertions still expect Project Manager, Wizard and Editor inside Motion Lab, despite UX2.4 moving them to primary navigation. Other WAV/media tests need behavioral triage, not blanket assertion removal.
- Backend tests: FAIL, 1 of 791 (789 passed, 1 skipped). Exact keyframe 0.09 was clipped to 0.08 by the generated camera safety patch; a follow-up patch preserves explicitly authored keyframe and recording axes. Re-run required.
- Installer checks: PASS at UX4.2 head.
- No full browser or GPU CI confirmation; pending.

## UX5 CI cleanup checkpoint (2026-10-16)

- Updated previously stale frontend navigation assertions to reflect three project destinations in the primary menu, not the Motion Lab sidebar.
- Updated the WAV analyzer and project media restoration test harnesses to include new soundtrack/selection state.
- At commit `25eafd2`, GitHub **Syntax checks PASS** (including all frontend Node regressions) and **Installer checks PASS**.
- Backend tests are still running at the time of this checkpoint; consult GitHub Actions before signoff.
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
- Keep main unchanged until explicit authorization.
