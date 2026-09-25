# Fedora Atomic (Bazzite, Silverblue, Kinoite, Aurora, Bluefin)

The system is an image that updates as a whole; there is no per-package history.

- **Debug symbols:** Fedora sets `DEBUGINFOD_URLS` to
  `https://debuginfod.fedoraproject.org/` out of the box, so gdb fetches them on its own.
- **What changed recently:** `rpm-ostree status` lists the booted deployment and the
  previous one with their dates; `rpm-ostree db diff` shows which packages changed
  between them. A crash that started with the new deployment points at that update.
- **Layered packages:** `rpm-ostree status` also lists what the user layered on top of
  the image; those are the first suspects when only this machine crashes.
- **Rolling back:** `rpm-ostree rollback` boots the previous image. It's the user's call;
  suggest it, never run it.
- **Apps:** most GUI apps here are flatpaks (binary under `/app/`); see the main skill.
