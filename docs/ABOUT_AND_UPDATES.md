# About Morphorum and Git updates

Open **About** in the desktop sidebar or **More → About** on a phone.
The page shows an overview of Morphorum, upstream acknowledgments, repository
links, the installed version, the checked-out Git branch and the local commit.

## Update behavior

1. Select **Check for updates**. This fetches **only the current local branch**
   from `origin`, without switching branches, merging or installing files.
2. The page reports whether the branch is current, behind, ahead or diverged.
   A dirty tracked worktree blocks updates. A missing Git checkout or detached
   HEAD also blocks updates.
3. To install an available fast-forward, use **Update current branch** in a
   browser **on the Morphorum host itself** and accept the confirmation.
   Morphorum checks the branch/commit again before starting the existing
   Windows or Linux updater, which independently refuses dirty tracked files,
   makes a recovery backup, and can roll back after an error.
4. Allow the updater to finish, inspect the logged result, then **stop and
   restart Morphorum** to use the updated server. An in-progress generation or
   animation blocks starting an update. Do not begin renders while updating.

The update does not silently follow `main`, switch branches, or downgrade to a
different commit. A locally ahead/diverged branch requires manual Git review.
No updater is started automatically when this page is opened.

### Remote browser limitation

The regular LAN WebUI is deliberately unauthenticated, so accepting software
update commands from remote LAN clients would be unsafe. Remote browsers may
**check** the installed branch for updates, but **cannot apply** them. Run the
manual updater from the computer running Morphorum after stopping the server:

| Windows (in the install folder) | Linux (in the install folder) |
| --- | --- |
| `.\\update.bat` | `./update.sh` |

These commands update whichever branch is **currently checked out**, with no
branch argument. Do not use the optional explicit-branch arguments from
`README.md` if you intend to remain on the current branch.

## Credits and branding

Morphorum is an independent implementation inspired by work across the
Deforum, Stable Diffusion WebUI Forge, and broader open-source AI art
communities. The About page includes a special acknowledgment for
`chicodog530`; these acknowledgments are **not** endorsement claims and do
not imply that upstream source code was copied into Morphorum.

The approved, user-provided Morphorum artwork is installed as an optimized
**960 × 640 WebP** image at
`frontend/dist/assets/morphorum-about-logo.webp`. The original supplied
1536 × 1024 design was resized and encoded for the WebUI without cropping or
removing visual elements. The About page displays the complete 3:2 image in a
responsive hero, alongside project details on desktop and stacked on narrow
screens. The letter **M** remains a graceful fallback if the asset fails to load.

The logo is project-specific artwork; these credits do not grant permission to
reuse unrelated third-party artwork.
