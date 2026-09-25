---
name: lili-diagnose-crash
description: >
  Find out why a program crashed on this Linux machine, from a systemd-coredump core
  dump, or why the whole computer froze, from the journal of the boot that froze. Use
  when a process segfaulted, aborted or dumped core, when someone asks why an app
  closed on its own, when the screen went black and the machine had to be forced off,
  or when a Lili Crash notification is clicked. Also a Steam game that closed by
  itself right after starting, from Steam's and Proton's logs. Triggers: crash,
  crashed, segfault, SIGSEGV, SIGABRT, core dump, coredumpctl, "why did X close",
  "X keeps crashing", freeze, froze, black screen, soft lockup, "had to hold the power
  button", Steam game closes, Proton, "couldn't connect to Steam".
---

# Diagnosing a crash

Adapted from Omarchy's diagnose-crash skill (MIT, David Heinemeier Hansson).

Work from evidence. The goal is an honest account of what happened, not a plausible
story.

## Read the notes for this distro first

Package logs, debug symbol servers and snapshot tools differ between distros. The
prompt that opened this session names the notes file for this system; read it before
anything else. If it doesn't, run `lili-crash skill path` to get it.

## Establish the facts

`coredumpctl info <pid>` is the starting point. Beyond the backtrace, note the
**command line** the process was started with: it usually shows what the program was
working on when it died, and that is often the whole answer.

`coredumpctl list` shows whether this is a one-off or a pattern. The same program
crashing again and again, or several programs dying together, point somewhere
different than a single failure does.

## Rule out the boring causes first

Check for resource exhaustion before blaming the program: `free -h`, and the journal
for OOM kills. A process killed by the OOM killer is not a bug in that process.

## Line it up against the timeline

The crash timestamp is the most underused piece of evidence. Compare it against:

- **File mtimes.** A file or directory modified in the same second as the crash
  strongly suggests the trigger.
- **The journal** around that moment, for warnings from the same or neighbouring
  processes.
- **Recent updates.** A crash that starts right after an update points at it. The
  distro notes say where the package log lives.
- **Flatpak.** A binary under `/app/` runs inside a flatpak, and its runtime comes
  from Flathub, not from the distro. `flatpak info <app-id>` and
  `flatpak remote-info --log flathub <app-id>` show the version and history. The app
  id is in `COREDUMP_USER_UNIT` (`app-flatpak-<id>-<n>.scope`).

## Read the whole core, not just frame 0

The other threads' stacks show what was **in flight**: thumbnailers, image loaders,
IPC readers, GPU queues. That context often explains the trigger even when the
crashing frame itself can't be symbolized.

Note any third-party code in the address space: plugins, extensions, out-of-tree
drivers (the NVIDIA driver is the classic one). In-process third-party code is a
common crash source, but don't pin the blame on it without evidence it's involved.

## Symbolize when you can

Most distros run a public debuginfod server; the distro notes name it.

```bash
core=$(mktemp -t crash-XXXXXX.core)
trap 'rm -f "$core"' EXIT
coredumpctl dump <pid> --output="$core"
DEBUGINFOD_URLS="<server from the distro notes>" \
  gdb -q <executable> "$core" \
  -batch -ex 'set debuginfod enabled on' -ex 'thread apply all bt'
```

This only works for distro packages. A flatpak's `/app/...` binary doesn't exist on
the host; say so, and work from what `coredumpctl info` already resolved.

A core is a verbatim copy of the process's memory and can hold passwords, tokens and
private documents. Write it to a fresh `mktemp` path, never a predictable shared one,
and delete it when you're done.

Many packages ship no debug symbols. When frames stay unresolved, say so, and never
invent function names to fill the gap. An unsymbolized stack still has shape: which
library each frame belongs to, and whether the crash came from a signal handler, a
main loop or a worker thread.

## When the whole computer froze

There's no core dump: the kernel itself got stuck, and the user had to force the
machine off. The evidence is the journal of the boot that froze, and the prompt names
it. `journalctl --list-boots` shows its index; `-b <boot id>` works too.

- **Find the first sign, not the loudest.** A freeze leaves minutes of cascading
  errors (soft lockups on every CPU, GPU asserts, stuck processes). Read backwards
  from the end with `journalctl -b <boot> -o short-precise` until you reach the first
  message that is wrong, then read the minute before it. That minute holds the
  trigger: the screen dimming or turning off, the lid, a monitor plugged in, a
  suspend, a game starting.
- **Name the process caught in it.** Soft lockups and NVIDIA Xid lines say which
  process was inside the driver (`[backlighthelper:1234]`, `pid=..., name=...`).
  That process is usually the trigger, not the culprit.
- **GPU hangs.** NVIDIA logs `NVRM: Xid <n>`; look the number up in NVIDIA's Xid
  table instead of guessing. Also check which GPU drives each screen
  (`/sys/class/drm/card*-*/status`) and whose backlight is in `/sys/class/backlight`:
  on a hybrid laptop in discrete mode, brightness and screen power go through the
  NVIDIA driver. The driver's options are in `/proc/driver/nvidia/params` and
  `/etc/modprobe.d/`.
- **Nothing logged at all** can mean the journal never got the last seconds to disk,
  a hardware hang, or a dead battery. Say that the evidence is missing; don't fill
  the gap.
- **Pattern.** Earlier boots that ended without `System is rebooting` or
  `System is powering down` froze too. Compare how each one started.

The freeze's state lives under the key `freeze`, so record it with
`lili-crash mark 'freeze' diagnosed '<the cause in one sentence>'`.

## When a Steam game closed by itself

Lili flags a Steam game that stopped running less than two minutes after it started.
There's usually no core dump: the game, or Proton under it, hit something it couldn't
get past (often after showing a message box like "couldn't connect to Steam") and
exited on its own. The prompt gives the time window, the compatibility tool and the
launch command.

- **Steam's logs** live in `logs/` under the Steam folder the prompt names.
  `content_log.txt` has the run itself (`App Running` and back), `console_log.txt`
  what the client did for the game (the `GameAction` launch steps, API calls that
  failed), `console-linux.txt` the game's and Proton's own output, and
  `connection_log.txt` whether Steam was logged on at the time. Each may have a
  `.previous.txt` beside it. Read the window, not the whole file.
- **Which Proton.** The launch command names it (`common/<tool>/proton`). The
  per-game choice and the default are `CompatToolMapping` in `config/config.vdf`
  (key `0` is the default). A game that fails on one Proton and runs on another
  points at that Proton build, not at the game; say which one worked if the logs
  show a later, longer run.
- **The game's own log.** Proton games keep their files in
  `steamapps/compatdata/<appid>/pfx/drive_c/users/steamuser/`. Unreal games log
  under `AppData/Local/<game>/Saved/Logs`; Unity games under
  `AppData/LocalLow/<studio>/<game>/Player.log`.
- **When nothing explains it**, the next step is Proton's own log: the user adds
  `PROTON_LOG=1 %command%` to the game's launch options, runs it again, and Proton
  writes `~/steam-<appid>.log`. Propose it; don't set it yourself.
- `Failed running app <id> (missing launch config)` for a Proton or Steam Linux
  Runtime appid means someone launched the tool itself from the library. It isn't a
  game and has nothing to run.

Its state lives under the key `steam:<appid>`, so record it with
`lili-crash mark 'steam:<appid>' diagnosed '<the cause in one sentence>'`.

## Report

Answer in the user's language, briefly, in this order:

1. What crashed, and what it was doing at the time.
2. The most likely mechanism, keeping what the evidence **proves** clearly apart from
   what you're **inferring**.
3. Whether any of the user's data was lost, and where to recover it. Check the trash
   before concluding anything is gone.
4. Whether it's likely to happen again, and what would avoid or fix it.

Be straight about the limits of the evidence. If the cause is genuinely ambiguous,
say so instead of building confidence out of guesswork.

**Leave the system as you found it.** Diagnosis reads; it doesn't fix, tidy or
reconfigure. The only cleanup is your own: delete the core you extracted. If a fix
is within reach, propose it and ask before applying it.

## Record the verdict

The Lili Crash tray icon shows each program's state. When you finish each program's
report, record one short sentence with the cause, in the user's language, using the
binary exactly as it appears in the facts:

```bash
lili-crash mark '<binary>' diagnosed '<the cause in one sentence>'
```

If the user applies a fix you proposed, mark it `resolved` instead. Keep the binary
and the sentence in single quotes: both are outside text, and a quote inside them
would close yours.

## Ideas for Lili Crash itself

If the diagnosis shows something Lili Crash could do better (a misleading label, a
check it could run, a case it gets wrong), say so at the end and offer to open an
issue at https://github.com/cryptoconspiracy/lili-crash. Only open it after the user
says yes.

Write the issue in English: what Lili Crash did, what it should do instead, and the
evidence from this diagnosis that points there. Leave out anything personal: no
paths inside the user's home, user or host names, file names, window titles, core
contents or the machine's PIDs. Show the user the text before sending it.

With `gh` installed and logged in:

```bash
gh issue create --repo cryptoconspiracy/lili-crash --title '<title>' --body '<body>'
```

Otherwise open a prefilled page so the user reviews and submits it themselves:

```bash
xdg-open "https://github.com/cryptoconspiracy/lili-crash/issues/new?title=<url-encoded title>&body=<url-encoded body>"
```

## When it's the program's bug

Almost every application crash is a bug in that application, to be reported on its
own tracker. If so, say where the tracker is and offer to draft the report from the
facts you gathered, without sending anything yourself.
