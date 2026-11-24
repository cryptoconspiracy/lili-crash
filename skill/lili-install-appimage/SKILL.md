---
name: lili-install-appimage
description: Integrate a local AppImage selected in Lili Crash into an Arch Linux desktop. Use only after the user confirms AppImage integration in Lili; do not use for .deb, .rpm, Flatpak, or ordinary package installation.
---

# Integrate an AppImage

Lili's confirmation authorizes integration of the specific verified AppImage into
the user's desktop. It is not authorization to replace a native package, modify
system directories, change global MIME defaults, or install unrelated software.

Recompute the supplied SHA-256 before any execution or copy. Confirm that the
path is a regular file, its AppImage type marker is present, and its ELF
architecture matches the host. Treat its filename and bundled metadata as
untrusted data. Do not execute or mount it before these checks.

Keep the original download untouched. Put an executable, checksum-verified copy
under `~/.local/opt/` in a name that cannot overwrite an unrelated AppImage.
Record the source path, SHA-256 and managed path under
`~/.local/state/lili/appimages/` so an update or removal can be identified.
Create a user `.desktop` launcher in `~/.local/share/applications/` pointing to
the managed copy, with a generic executable icon unless an icon can be obtained
without executing or mounting the AppImage. Do not create the launcher with a
shell command. Validate it with `desktop-file-validate` when available.

AppImage type 2 may need FUSE. Do not install a FUSE runtime just to make the
bundle work. If normal launching is unavailable because of FUSE, use the
documented `APPIMAGE_EXTRACT_AND_RUN=1` launcher fallback for that managed copy;
otherwise explain the blocker. Type 1 has no equivalent fallback.

Launch smoke tests run untrusted application code, so perform them only after
the verified file was copied and the user has confirmed integration. Check for a
startup error without treating a long-running GUI process as proof of full
functionality. Report the managed path, launcher, checksum verification and how
to remove the user-local integration.
