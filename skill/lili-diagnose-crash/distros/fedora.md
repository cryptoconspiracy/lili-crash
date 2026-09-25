# Fedora

- **Debug symbols:** Fedora sets `DEBUGINFOD_URLS` to
  `https://debuginfod.fedoraproject.org/` out of the box, so gdb fetches them on its own.
- **What changed recently:** `dnf history list`, then `dnf history info <id>` for a
  transaction near the crash time.
- **Crash reports:** ABRT may already have caught it; `abrt-cli list` (if installed)
  shows what it has.
- **Where a package came from:** `rpm -qf <file>` for the owner of a library in the
  backtrace, `rpm -qi <pkg>` for its build.
