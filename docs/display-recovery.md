# Internal-panel recovery

An observed Intel/NVIDIA laptop incident left the Intel eDP panel physically black
after unlocking, while HDMI continued working. KScreen and DRM reported an enabled
panel, brightness was 100%, the lid was open and a screenshot contained a rendered
desktop. Changing only the internal panel from 2560×1600 at 240 Hz to the advertised
60 Hz mode restored the image, confirmed by the user. Earlier KWin EBUSY messages
were observed but do not establish the cause; PSR2 was enabled, which alone is not
evidence of a fault.

A second incident (24 November 2026) showed the same symptom with the panel **already
at 60 Hz**, so the refresh rate alone does not prevent it. The panel was lit, rewriting
its brightness changed nothing, and the kernel logged no error. Powering the outputs off
and on (DPMS) restored the image, confirmed by the user. The recovery of that day had
not run at all: the kernel had numbered the panel `eDP-1` instead of `eDP-2`.

## Authorization and trigger

`lili-crash display approve eDP-2` authorizes restoring that panel's current, visually
confirmed 60 Hz mode, and powering the screens off and on again after they were off. It requires an enabled Intel eDP panel, stores an
EDID hash, driver, connector, resolution and refresh rate. The panel is recognized by
EDID and driver, since the connector's number changes between boots. It does not authorize
arbitrary commands or give an AI unrestricted approval. Other installations remain
disabled. `display disable` revokes the authorization.

The existing user service polls every 10 seconds. It checks the lock state, lid
and DPMS. At watcher startup, unlock, panel wake or a sampling gap over 45 seconds,
it restores the registered mode if the panel is using more than 61 Hz at the same
resolution. This is a preventive rule for a known incident, **not optical detection
of a black LCD**.

A panel already at 60 Hz is **rewoken** when the screens were off (or the computer was
suspended) and the session is back, unlocked: DPMS off, up to three seconds, DPMS on.
KWin powers all outputs together, so external screens blink too. Moving the mouse ends
the pause early. A lock and unlock with the screens on does nothing. DPMS is sampled
every second so that a brief screen-off is not missed. `lili-crash display rewake` does
the same by hand, without the cooldown, for the approved panel only.

It also reacts to fresh display errors: three distinct KWin `Atomic commit failed:
EBUSY` timestamps, or an explicit pageflip timeout / Intel atomic update failure.
Queries are limited to 100 messages per journal source and the last 10 minutes,
after enrollment and after the last handled error. These are display error signals,
not proof that a screen is physically black. NVIDIA GPU resets, unrelated kernel
errors and a single EBUSY do not trigger the rule.

No action occurs for a locked/unknown session, closed/unknown lid, powered-off or
disabled panel, changed resolution, missing stable mode, or different EDID/driver.
Only one automatic attempt per five minutes is allowed, including across watcher restarts.
Every command has a timeout, and DPMS on is sent even when off failed. Lili does not
disable outputs, change layout, reset GPUs, restart KWin, log out or reboot.

## Verification and reporting

After applying the mode, Lili reads KScreen again and verifies the target mode,
panel enablement, layout and unchanged external outputs. Success means **mode
applied**, not proven visual recovery. If the panel is already at 60 Hz when errors
arrive, Lili reports that further diagnosis is needed instead of claiming repair.
Command failure, timeout and failed readback are recorded as unverified corrections.

A separate native Qt window is opened for each handled episode and remains until
closed, except after a rewake, when it closes by itself in 30 seconds. A KWin script
puts it on another screen when there is one, above other windows, because Wayland does
not let the window choose. Its button asks for another rewake. KDE's kdialog is used if PySide6 is unavailable. The report contains
the signal, before/after rate, result and scope of authorization. It can be reopened
with `lili-crash display show latest`.

`display approve eDP-2 --record-recovery-from 240` additionally records a historical
240→60 Hz recovery **already confirmed by the user** and opens its report; this
option does not invent or execute a recovery. Do not use it without that confirmation.

The policy, last attempt, handled timestamps and latest 50 events are stored in
`~/.local/state/lili/display.json` (0600), under a process lock with atomic writes.
Raw logs and raw EDID are not saved. `display status` shows this local history;
these events are not yet part of the general crash list or fleet export schema.

## Validation

`make check` covers authorization, panel identity, lock/lid/DPMS transitions,
timeouts, cooldown across restarts, journal deduplication, external-output
preservation, readback failure and the persistent translated report window.
Tests use simulated display responses. On the affected hardware the user confirmed the
240→60 Hz recovery and the DPMS recovery, and the watcher was seen rewaking the screens
after a real DPMS off/on. Whether it clears a *new* black screen by itself is only known
at the next occurrence.
