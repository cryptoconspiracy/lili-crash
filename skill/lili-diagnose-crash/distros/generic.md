# Other distros

There are no notes for this distro yet, so find out what it uses:

- `cat /etc/os-release` for the family (`ID_LIKE`); the notes for that family in this
  folder mostly apply.
- **Debug symbols:** check whether `DEBUGINFOD_URLS` is already set; many distros set
  it for you.
- **What changed recently:** find the package manager's log (`/var/log/pacman.log`,
  `/var/log/apt/`, `dnf history`, `/var/log/zypp/history`, `xbps`, `emerge.log`...).
- Say plainly when a step isn't available on this system instead of guessing.
