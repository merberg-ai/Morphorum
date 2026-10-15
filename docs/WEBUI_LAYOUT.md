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

## Development branch and checkpointing

Browser WebUI changes are integrated directly on `dev-webui`. Each accepted
batch gets a descriptive checkpoint commit on that branch; `main` remains
unchanged until deliberate promotion.
