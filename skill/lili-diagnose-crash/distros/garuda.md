# Garuda Linux

Garuda is Arch underneath: everything in the Arch notes applies. On top of that:

- **Debug symbols:** `DEBUGINFOD_URLS="https://debuginfod.archlinux.org"` covers the Arch
  repos. Packages from `chaotic-aur` are built without them.
- **What changed recently:** updates go through `garuda-update`, which still logs to
  `/var/log/pacman.log`. `grep -E 'upgraded|installed|removed' /var/log/pacman.log | tail -50`.
- **Snapshots:** the root is btrfs with snapper, and every update takes a pre/post
  snapshot. `snapper list` shows them with dates; if a crash started after an update,
  that pair is the before and after. Rolling back is the user's call; suggest it, never
  run it.
- **Where a package came from:** `pacman -Qi <pkg>`; the Repository line tells Arch
  from `chaotic-aur` or `garuda`.
