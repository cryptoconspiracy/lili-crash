# Ubuntu

- **Core dumps:** Ubuntu hands crashes to Apport, not systemd-coredump. If
  `coredumpctl list` is empty, look in `/var/crash/` for `.crash` files
  (`apport-unpack` extracts them), or install `systemd-coredump` so Lili Crash sees
  future crashes.
- **Debug symbols:** `DEBUGINFOD_URLS="https://debuginfod.ubuntu.com"`.
- **What changed recently:** `/var/log/apt/history.log` and `/var/log/dpkg.log`. Snap
  apps update on their own: `snap changes` lists when.
- **Where a package came from:** `apt policy <pkg>`, `dpkg -S <file>`, and for a binary
  under `/snap/` it's a snap, with its own runtime.
