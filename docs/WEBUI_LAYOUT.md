# Browser WebUI layout architecture

The Morphorum browser UI is a **single application** for phone, tablet and desktop.
FastAPI serves the same `frontend/dist/index.html` and the same scripts to every
browser. Device characteristics affect CSS presentation, not the API contract or
project/generation behavior.

## Stylesheet responsibilities

| File | Responsibility |
| --- | --- |
| `assets/app.css` | Shared themes, tokens, controls, and base page structure |
| `assets/mobile.css` | Global phone navigation, compact header, dialogs and keyboard clearance |
| `assets/tablet.css` | Intermediate, touch-friendly navigation and panel sizing |
| `assets/desktop.css` | Wide-screen, fine-pointer sidebar and editor workspaces |
| `assets/models.css`, `image.css`, `animation.css` | Feature-owned styles, including their local responsive breakpoints |

The conditional stylesheets have mutually exclusive intended ranges:
- **Phone**: up to 640 CSS px; phone-specific CSS is requested via media.
- **Tablet/intermediate**: 641–1180 CSS px, plus extra-wide coarse-pointer
  devices. Primary destinations wrap into full-size touch targets.
- **Desktop**: at least 1181 CSS px with `hover: hover` and `pointer: fine`.
  The desktop-only stylesheet adds the sidebar and spacious editor layouts.

A wide touch screen without a fine pointer uses tablet presentation, not a forced
desktop sidebar. The shared and feature-owned CSS still applies at every width;
feature rules may have additional breakpoints appropriate to their controls.

## Maintenance rules

1. Keep API requests, navigation state, form validation and generation logic in
   the shared JavaScript. Do not create independent desktop/mobile code paths.
2. Put global phone navigation/header/keyboard changes in `mobile.css`; put
   tablet-specific layout in `tablet.css`; put wide-pointer layout in `desktop.css`.
3. Keep responsive styles for individual features beside the feature in its own
   stylesheet, especially timeline and Motion Lab grids.
4. Preserve accessible touch targets, keyboard navigation, scroll reachability,
   persisted UI state and no duplicate DOM controls.
5. After layout changes, run the Node browser regressions and manually inspect
   approximately 360px, 390px, 640px, 700px, 820px, 1024px, 1180px and 1440px
   at 100% and 125–150% browser/OS scaling. Also test landscape phones and wide
   touch-only screens when available.

## Regression expectations

Use the [Testing guide](TESTING.md) to run current frontend and backend checks. The same shared browser code and API contracts must work at phone, tablet, and desktop widths; avoid fixing one layout by creating a second application pathway.



## Responsive WebUI usability improvements (October 2026)

The published WebUI includes `assets/ux-polish.css` after the responsive breakpoint styles. The narrow Project and Motion Lab dropdowns are bounded and appear in a positioned overlay above the phone bottom-navigation bar instead of expanding its flex row. The desktop sidebar still uses its original layout. Help is in the left desktop navigation and in the phone More menu. Verify 320, 375, 390, 640, 768, and desktop widths with both menu groups expanded; no horizontal page scroll or hidden controls.

The Image Generation pane now includes **Apply Image Settings to Project**, which copies model, width/height, steps, sampler, schedule type, seed, seed mode and seed increment into the **already open Project Editor draft**. It deliberately does **not** copy positive/negative prompts or CFG/guidance. The user must still press **Save Project** in Project Editor; the Image action does not write to disk. The Image generation progress component has been moved without changing its DOM IDs into the Results card, directly above preview content. Both in-progress and history/empty preview must remain readable.

Help is a normal application view, backed by read-only `/api/help/docs` and `/api/help/docs/{name}`, exposing only regular top-level `docs/*.md` files from the installed repository. The client fetches pages in-place and renders a constrained/sanitized subset of Markdown. It makes no remote network request or navigation away from the WebUI; the FastAPI interactive API documentation route at `/docs` remains reserved for its preexisting purpose. This Help browser is a local documentation reader, not a GitHub live sync. Back-end only mode does not expose it.

Tests: `tests/frontend_webui_quick_tweaks.test.cjs`; run alongside existing `frontend_responsive_styles.test.cjs`, `frontend_project_navigation.test.cjs`, and project editor tests. These frontend changes were promoted to `main` in [PR #51](https://github.com/merberg-ai/Morphorum/pull/51), with Syntax, Backend and Installer CI passing. Owner accepted the relevant Windows WebUI interactions; dedicated physical phone/zoom acceptance remains deferred. The experimental standalone Z-Image c3c4 research remains non-production.


## Prompt keyframe distribution (owner-accepted)

Project Editor → **Prompt Keyframes** offers **+ Keyframe** and **Evenly Space**. Adding a prompt automatically reassigns the existing prompt rows and the new blank row across frames 0 through `max_frames - 1` in their existing order. Evenly Space reassigns only frame numbers, without inserting a row. For `max_frames=543`: 4 prompts → `0, 181, 361, 542`; 5 prompts → `0, 136, 271, 407, 542`. Uses rounded `index*(max_frames-1)/(count-1)`, first frame always zero. If there are more prompts than frames, the action refuses to introduce duplicate keyframes.

Positive prompt text, negative prompt text, LoRA insertion controls, and row order remain unchanged. Manual frame edits are still allowed after redistribution. Both actions mark the **Project Editor draft as unsaved**; users must press **Save Project**. No animation schema or backend rendering behavior changed. Unit regression: `tests/frontend_prompt_even_spacing.test.cjs`. Verify manually on Windows with unsaved prompt text and after saving/reloading the project.

### Motion Lab popup styling on touch layouts (2026-10-19)

Motion Lab's `#motion-lab-sidebar` buttons previously received their custom styling from `desktop.css` alone. On mobile, the `ux-polish.css` popup layout made the buttons visible without those rules, leaving the browser's default gray button backgrounds. A responsive, theme-token-based style now applies to narrow and coarse-pointer popups: transparent buttons, muted/active accent text, selection/hover/focus states, and preserved scroll limits. The fine-pointer desktop sidebar remains untouched. Verify on phone with all available UI themes and confirm the adjacent Project popup still behaves normally. Regression: `tests/frontend_webui_quick_tweaks.test.cjs`.


### Touch submenu dismissal

On compact and coarse-pointer layouts, selecting a **Project** or **Motion Lab** submenu destination now navigates to the requested workspace and then closes both nav popups. The menu toggles' `aria-expanded` attributes return to `false`, keeping the underlying editor unobstructed. On wide fine-pointer desktops the sidebar remains open as before. Both behaviors are covered by the WebUI regression suite.

## Civitai artwork in local model managers (published main)

The installed **Models** library uses an auto-fitting card grid in place of
dense rows. Each card keeps its selection checkbox, thumbnail or NO PREVIEW
placeholder, filename, family, type, file size, collapsible full path and
original generation/Civitai actions. **Sync Civitai Info (N)** is an explicit
bulk action; opening the manager loads only existing local cached data.

The **LoRAs** manager retains its two-column desktop selector/detail layout,
with miniature images in the selector and a larger fitted preview above Quick
Use. On tablet/phone the detail stack remains single-column. Cache images are
loaded with native lazy loading and use only the local preview endpoint.
The selected adapter, prompt snippets and runtime diagnostics remain unchanged.
The owner confirmed cached thumbnails appearing after sync; this does not
certify every phone-width, maturity-filter or CDN-failure edge case. Continue
testing mobile click targets, disabled Civitai Hub behavior, 320px layouts and
long filenames. Regression: `tests/frontend_cached_art.test.cjs`.
