# Debian

- **Core dumps:** systemd-coredump isn't installed by default. If `coredumpctl list` is
  empty, `sudo apt install systemd-coredump` is needed first (and only catches future
  crashes).
- **Debug symbols:** `DEBUGINFOD_URLS="https://debuginfod.debian.net"`.
- **What changed recently:** `/var/log/apt/history.log` (whole transactions) and
  `/var/log/dpkg.log` (per package).
- **Where a package came from:** `apt policy <pkg>` and `dpkg -S <file>` for the owner of
  a library in the backtrace.
