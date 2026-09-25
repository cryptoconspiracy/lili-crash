# Arch Linux

- **Debug symbols:** `DEBUGINFOD_URLS="https://debuginfod.archlinux.org"`. Official
  repo packages have them; AUR packages usually don't.
- **What changed recently:** `grep -E 'upgraded|installed|removed' /var/log/pacman.log | tail -50`.
  Match the timestamps against the crash.
- **Downgrading to test a regression:** older packages stay in `/var/cache/pacman/pkg/`,
  so `pacman -U` on the previous version is a cheap experiment. Propose it, don't run it.
- **Where a package came from:** `pacman -Qi <pkg>` (Packager, Build Date) and
  `pacman -Qo <file>` for the owner of a library in the backtrace.
