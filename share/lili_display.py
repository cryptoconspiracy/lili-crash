"""Opt-in recovery for a known internal panel. Never restarts a desktop or GPU."""
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
import re
from pathlib import Path
import subprocess
import tempfile
import time
import uuid

from lili_health import read_json, write_json


POLL_SECONDS = 10
COOLDOWN = 300
OFF_SECONDS = 3  # The interval that brought the image back on the affected hardware.


def run(argv):
    # The user service may inherit a locale that is not generated on this host.
    # Qt otherwise emits a journal warning on every polling iteration.
    result = subprocess.run(argv, capture_output=True, text=True, timeout=10,
                            env={**os.environ, "LC_ALL": "C.UTF-8"})
    if result.returncode:
        raise RuntimeError(f"{argv[0]} failed ({result.returncode})")
    return result.stdout


def outputs():
    value = json.loads(run(["kscreen-doctor", "-j"]))
    if not isinstance(value, dict) or not isinstance(value.get("outputs"), list):
        raise ValueError("Invalid KScreen response")
    return value["outputs"]


def mode(output):
    return next((m for m in output.get("modes", [])
                 if str(m["id"]) == str(output.get("currentModeId"))), None)


def panel_identity(name, drm=Path("/sys/class/drm")):
    if not re.fullmatch(r"eDP-\d+", name):
        return None
    for connector in drm.glob("card*-" + name):
        try:
            edid = (connector / "edid").read_bytes()
            if len(edid) < 128 or (connector / "status").read_text().strip() != "connected":
                continue
            return {"connector": str(connector), "edid": hashlib.sha256(edid).hexdigest(),
                    "driver": (connector / "device/device/driver").resolve().name,
                    "dpms": (connector / "dpms").read_text().strip()}
        except OSError:
            continue
    return None


def find_panel(policy, drm=Path("/sys/class/drm")):
    """The kernel may number the same panel eDP-1 on one boot and eDP-2 on the next."""
    names = [policy["output"]] + sorted({c.name.split("-", 1)[1] for c in drm.glob("card*-eDP-*")})
    for name in dict.fromkeys(names):
        identity = panel_identity(name, drm)
        if identity and all(identity[k] == policy[k] for k in ("edid", "driver")):
            return name, identity
    return None, None


def wait(tracker):
    """Sleep until the next poll, noticing a screen-off too short for the poll itself to see."""
    for _ in range(2 if tracker.get("ready") is False else POLL_SECONDS):
        time.sleep(1)
        try:
            if tracker.get("dpms") and Path(tracker["dpms"]).read_text().strip() == "Off":
                tracker["slept"] = True
        except OSError:
            pass


def session_ready(lid_root=Path("/proc/acpi/button/lid")):
    # Unknown/locked/closed is not permission to turn on a deliberately dark panel.
    try:
        lid = [p.read_text().strip().split()[-1] for p in lid_root.glob("*/state")]
        unlocked = run(["qdbus6", "org.freedesktop.ScreenSaver", "/ScreenSaver",
                        "org.freedesktop.ScreenSaver.GetActive"]).strip() == "false"
        return bool(lid) and all(value == "open" for value in lid) and unlocked
    except (OSError, RuntimeError, subprocess.TimeoutExpired):
        return False


def video_errors(since, now):
    """Only fresh, bounded signals; an EBUSY is not proof of a physically black LCD."""
    stamps = set()
    for scope in (["--user", "_COMM=kwin_wayland"], ["-k"]):
        try:
            text = run(["journalctl", "-b", *scope, "--since", f"@{since:.6f}",
                        "-n", "100", "-o", "json", "--no-pager"])
        except (OSError, RuntimeError, subprocess.TimeoutExpired):
            continue
        busy = set()
        for line in text.splitlines():
            try:
                entry = json.loads(line)
                stamp = int(entry["__REALTIME_TIMESTAMP"]) / 1_000_000
                message = entry.get("MESSAGE", "")
                if not isinstance(message, str) or not since < stamp <= now:
                    continue
                if scope[0] == "--user" and "Atomic commit failed: EBUSY" in message:
                    busy.add(stamp)
                if re.search(r"(?:i915.*(?:flip_done timed out|flip_done timeout|Atomic update failure)|"
                             r"Pageflip timed out)", message, re.I):
                    stamps.add(stamp)
            except (ValueError, KeyError, TypeError):
                continue
        if len(busy) >= 3:
            stamps.update(busy)
    return max(stamps, default=0)


@contextmanager
def locked(state_dir):
    state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (state_dir / "display.lock").open("a") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        data = read_json(state_dir / "display.json", {})
        if not isinstance(data, dict):
            raise ValueError("Invalid display recovery state")
        yield data
        write_json(state_dir / "display.json", data)


def event(data, output, before, after, trigger, status, now):
    item = {"id": uuid.uuid4().hex, "time": now, "output": output,
            "before_hz": before, "after_hz": after, "trigger": trigger, "status": status}
    data["events"] = (data.get("events", []) + [item])[-50:]
    return item


def approve(state_dir, name, previous_hz=None):
    """Enroll only the currently working 60 Hz mode, bound to panel EDID and driver."""
    found = next((o for o in outputs() if o.get("name") == name), None)
    identity = panel_identity(name)
    current = mode(found) if found else None
    if (not found or not found.get("enabled") or not found.get("connected") or
            not identity or identity["driver"] != "i915" or not current or
            not 59 <= current["refreshRate"] <= 61):
        raise ValueError("Approval needs an enabled Intel eDP panel already working at 60 Hz")
    if previous_hz is not None and not 61 < previous_hz <= 1000:
        raise ValueError("Previous refresh rate must be above 61 Hz and at most 1000 Hz")
    now = time.time()
    with locked(state_dir) as data:
        data["policy"] = {"enabled": True, "output": name, "edid": identity["edid"],
                          "driver": identity["driver"], "size": current["size"],
                          "refresh": current["refreshRate"], "approved_at": now}
        data["errors_until"] = now
        if previous_hz is not None:
            return event(data, name, previous_hz, current["refreshRate"],
                         "user-confirmed", "confirmed", now)


def signature(items, excluded):
    return [{k: o.get(k) for k in ("name", "connected", "enabled", "currentModeId",
                                  "pos", "scale", "rotation", "priority")}
            for o in sorted(items, key=lambda o: o["name"]) if o["name"] != excluded]


def rewake(data, trigger, now, state_dir, output, dpms):
    """Power the screens off and on again: the panel can light up without an image.

    KWin's DPMS is all outputs or none, so the external screens blink as well.
    """
    data["last_attempt"] = now
    write_json(state_dir / "display.json", data)
    hz = (mode(output) or {}).get("refreshRate")
    item = event(data, output["name"], hz, hz, trigger, "failed", now)
    read = lambda: Path(dpms).read_text().strip()
    went_off = False
    try:
        before = outputs()
        try:
            run(["kscreen-doctor", "--dpms", "off"])
            deadline = time.monotonic() + OFF_SECONDS + 2
            while time.monotonic() < deadline:
                if read() == "Off" and not went_off:
                    went_off, deadline = True, time.monotonic() + OFF_SECONDS
                elif went_off and read() == "On":
                    break  # The mouse or keyboard already woke it.
                time.sleep(.1)
        finally:
            # Never leave the person in the dark: insist once if the first call fails.
            for _ in range(2):
                try:
                    run(["kscreen-doctor", "--dpms", "on"])
                    break
                except (RuntimeError, subprocess.TimeoutExpired):
                    continue
        deadline = time.monotonic() + 5
        while read() != "On" and time.monotonic() < deadline:
            time.sleep(.1)
        if went_off and read() == "On" and signature(before, None) == signature(outputs(), None):
            item["status"] = "rewoken"
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired):
        pass
    return item


def rewake_now(state_dir):
    """The person says the screen is black: no cooldown, but only for the approved panel."""
    with locked(state_dir) as data:
        policy = data.get("policy", {})
        name, identity = find_panel(policy) if policy.get("enabled") else (None, None)
        output = next((o for o in outputs() if o.get("name") == name), None) if name else None
        if not output or not output.get("enabled"):
            raise ValueError("No approved internal panel is enabled; see lili-crash display approve")
        return rewake(data, "user-request", time.time(), state_dir, output,
                      Path(identity["connector"]) / "dpms")


def recover(data, trigger, now, state_dir):
    policy = data["policy"]
    before = outputs()
    output = next((o for o in before if o.get("name") == policy["output"]), None)
    identity = panel_identity(policy["output"])
    if (not output or not output.get("enabled") or not output.get("connected") or not identity or
            identity["dpms"] != "On" or identity["edid"] != policy["edid"] or
            identity["driver"] != policy["driver"]):
        return None
    current = mode(output)
    if not current or current["size"] != policy["size"]:
        return None  # Do not replace a user's deliberate resolution/layout choice.
    safe = next((m for m in output["modes"] if m["size"] == policy["size"] and
                 abs(m["refreshRate"] - policy["refresh"]) < .1), None)
    if not safe:
        return None
    if current["refreshRate"] <= 61:
        if trigger == "display-wake":
            return rewake(data, trigger, now, state_dir, output, Path(identity["connector"]) / "dpms")
        if trigger != "video-errors":
            return None
        return event(data, output["name"], current["refreshRate"], current["refreshRate"],
                     trigger, "needs-attention", now)
    data["last_attempt"] = now
    # Save before starting the command: a timeout or watcher crash must not cause a loop.
    write_json(state_dir / "display.json", data)
    item = event(data, output["name"], current["refreshRate"], None, trigger, "failed", now)
    try:
        if not re.fullmatch(r"\d+", str(safe["id"])):
            raise ValueError("Invalid KScreen mode ID")
        run(["kscreen-doctor", f"output.{output['name']}.mode.{safe['id']}"])
        after = outputs()
        actual = next((o for o in after if o.get("name") == output["name"]), None)
        actual_mode = mode(actual) if actual else None
        if actual_mode:
            item["after_hz"] = actual_mode["refreshRate"]
        if (actual and actual.get("enabled") and actual.get("connected") and actual_mode and
                actual_mode["size"] == safe["size"] and
                abs(actual_mode["refreshRate"] - safe["refreshRate"]) < .1 and
                all(actual.get(k) == output.get(k) for k in ("pos", "scale", "rotation", "priority")) and
                signature(before, output["name"]) == signature(after, output["name"])):
            item["status"] = "applied"
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired):
        pass
    return item


def poll(state_dir, tracker, now=None):
    now = time.time() if now is None else now
    with locked(state_dir) as data:
        policy = data.get("policy", {})
        if not policy.get("enabled"):
            tracker.clear()
            return None
        name, identity = find_panel(policy)
        if name:
            policy["output"] = name
            tracker["dpms"] = identity.get("connector") and identity["connector"] + "/dpms"
        ready = bool(identity and identity["dpms"] == "On") and session_ready()
        data["checked_at"] = now
        data["panel_found"] = bool(name)
        data["session_ready"] = ready
        suspended = now - tracker.get("time", now) > 45
        if suspended or (identity and identity["dpms"] == "Off"):
            tracker["slept"] = True
        resumed = ready and (tracker.get("ready") is not True or tracker.get("slept", False))
        tracker.update(ready=ready, time=now)
        if not ready:
            return None
        woke = tracker.pop("slept", False)
        since = max(policy["approved_at"], now - 600, data.get("errors_until", 0))
        try:
            error_time = video_errors(since, now)
        except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired):
            error_time = 0
        if error_time:
            data["errors_until"] = error_time
        if now - data.get("last_attempt", 0) < COOLDOWN or not (error_time or resumed):
            return None
        trigger = "display-wake" if woke else "video-errors" if error_time else "session-return"
        result = recover(data, trigger, now, state_dir)
        if result:
            data["last_attempt"] = now
        return result


def report_text(item, _):
    labels = {
        "user-confirmed": _("Internal screen stayed black after unlocking; the user confirmed recovery."),
        "session-return": _("On session return, the approved panel was using a refresh rate above its known stable mode."),
        "display-wake": _("The screens came back from being off. This panel is known to light up without an image then."),
        "user-request": _("You asked Lili to wake the internal screen again."),
        "video-errors": _("Recent display update errors were detected in the graphics journal."),
    }
    outcomes = {
        "confirmed": _("Image recovery confirmed by the user."),
        "applied": _("The system confirmed the stable mode. Physical image recovery still needs visual confirmation."),
        "rewoken": _("The screens were powered off and on again. If the internal screen is still black, use the button below."),
        "failed": _("The correction could not be verified. Automatic retries are limited; further diagnosis is needed."),
        "needs-attention": _("The panel is already in its stable mode. No display settings were changed; further diagnosis is needed."),
    }
    rate = lambda value: "?" if value is None else f"{value:g}"
    return "\n\n".join([
        _("Detected: {detail}").format(detail=labels[item["trigger"]]),
        _("Panel: {output}\nRefresh rate: {before} → {after} Hz").format(
            output=item["output"], before=rate(item["before_hz"]), after=rate(item["after_hz"])),
        outcomes[item["status"]],
        _("No restart, logout or application termination was performed."),
        _("Automatic authorization covers only restoring this registered panel to its known stable 60 Hz mode and waking it again after the screens were off."),
    ])


def create_dialog(item, _, logo, retry=lambda: None):
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QTextBrowser, QVBoxLayout
    dialog = QDialog()
    dialog.setWindowTitle(_("Lili Crash — Display recovery"))
    dialog.setWindowIcon(QIcon(str(logo)))
    dialog.resize(620, 440)
    layout = QVBoxLayout(dialog)
    heading = QLabel(_("Display recovery report"))
    font = heading.font()
    font.setPointSize(font.pointSize() + 4)
    font.setBold(True)
    heading.setFont(font)
    layout.addWidget(heading)
    body = QTextBrowser()
    body.setPlainText(report_text(item, _))
    layout.addWidget(body)
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
    buttons.rejected.connect(dialog.reject)
    again = buttons.addButton(_("Screen is black: wake it again"), QDialogButtonBox.ButtonRole.ActionRole)
    again.clicked.connect(lambda: (dialog.accept(), retry()))
    layout.addWidget(buttons)
    dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
    return dialog


def move_off_panel(output):
    """A report about a black screen must not open on it. Wayland lets only KWin place windows."""
    script = f"""
for (const w of workspace.windowList()) {{
    if (w.pid !== {os.getpid()}) continue;
    w.keepAbove = true;  // Not behind a maximized window, and without taking the focus.
    const other = workspace.screens.find(s => s.name !== {json.dumps(output)});
    if (other) workspace.sendClientToScreen(w, other);
}}
"""
    name = f"lili-display-{os.getpid()}"
    bus = ["qdbus6", "org.kde.KWin", "/Scripting"]
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".js") as stream:
            stream.write(script)
            stream.flush()
            number = run([*bus, "org.kde.kwin.Scripting.loadScript", stream.name, name]).strip()
            run([*bus[:2], f"/Scripting/Script{number}", "org.kde.kwin.Script.run"])
            run([*bus, "org.kde.kwin.Scripting.unloadScript", name])
    except (OSError, RuntimeError, subprocess.TimeoutExpired):
        pass  # The report still opened, wherever the desktop put it.


def show(state_dir, event_id, _, logo, retry=lambda: None):
    data = read_json(state_dir / "display.json", {})
    item = next((e for e in data.get("events", []) if e["id"] == event_id), None)
    if not item:
        raise ValueError("Display recovery report not found")
    try:
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QApplication
    except ImportError:
        import html
        subprocess.run(["kdialog", "--title", _("Lili Crash — Display recovery"),
                        "--msgbox", "<p>" + html.escape(report_text(item, _)).replace("\n", "<br>") + "</p>"],
                       check=True)
        return
    app = QApplication.instance() or QApplication([])
    dialog = create_dialog(item, _, logo, retry)
    QTimer.singleShot(500, lambda: move_off_panel(item["output"]))
    if item["status"] == "rewoken":
        QTimer.singleShot(30_000, dialog.reject)  # Runs at every wake: it must not pile up.
    dialog.exec()
