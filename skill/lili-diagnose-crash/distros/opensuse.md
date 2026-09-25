# openSUSE

Covers Tumbleweed and Leap (`ID` is `opensuse-tumbleweed` or `opensuse-leap`, both
list `opensuse` in `ID_LIKE`).

- **Debug symbols:** `DEBUGINFOD_URLS="https://debuginfod.opensuse.org/"`.
- **What changed recently:** `/var/log/zypp/history`.
- **Snapshots:** the root is usually btrfs with snapper; `snapper list` shows the
  snapshots taken around each `zypper` run. Rolling back is the user's call.
- **Where a package came from:** `rpm -qf <file>`, and `zypper info <pkg>` for the repo.
