"""Local, evidence-based early warnings. No AI, network, root, or automatic repairs."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time


RULES = {
    "disk-space": ("Disk space is running low", "Free space or move files before writes and updates fail."),
    "disk-inodes": ("The filesystem is running out of file entries", "Inspect directories with many small files before creating more files."),
    "disk-trend": ("The disk may fill within 24 hours", "Check growing logs and downloads; the estimate assumes the recent growth continues."),
    "memory-pressure": ("Memory pressure is persisting", "Save your work and inspect memory usage before opening more applications."),
    "kernel-storage": ("Storage errors are recurring", "Back up important files and inspect disk health and connections."),
    "kernel-gpu": ("Graphics driver timeouts are recurring", "Save your work and inspect driver errors before another graphics failure."),
    "kernel-hardware": ("Hardware errors are recurring", "Inspect hardware health; corrected errors can precede an uncorrectable failure."),
}
KERNEL_PATTERNS = {
    "kernel-storage": re.compile(r"I/O error|Buffer I/O|nvme.*(?:timeout|reset controller)|ata\d.*failed command", re.I),
    "kernel-gpu": re.compile(r"NVRM: Xid|amdgpu.*(?:ring .* timeout|GPU reset)|i915.*GPU HANG", re.I),
    "kernel-hardware": re.compile(r"EDAC.*(?:CE |corrected)|Hardware Error|Machine check", re.I),
}


def read_json(path, fallback):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return fallback


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix=path.name + "-")
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def disk_identity(path, fallback, mountinfo):
    matches = []
    for line in mountinfo.splitlines():
        try:
            left, right = line.split(" - ", 1)
            mount = re.sub(r"\\([0-7]{3})", lambda m: chr(int(m[1], 8)), left.split()[4])
            if str(path) == mount or str(path).startswith(mount.rstrip("/") + "/"):
                matches.append((len(mount), right.split()))
        except (ValueError, IndexError):
            continue
    if matches:
        fields = max(matches, key=lambda m: m[0])[1]
        if len(fields) >= 2 and fields[0] == "btrfs":
            # Subvolumes share one storage pool even when Linux exposes distinct device IDs.
            return "btrfs-" + hashlib.sha256(fields[1].encode()).hexdigest()[:16]
    return fallback


def collect(now=None):
    now = int(time.time() if now is None else now)
    sample = {"time": now, "disks": {}, "kernel": {}, "unavailable": []}
    devices = set()
    try:
        mountinfo = Path("/proc/self/mountinfo").read_text()
    except OSError:
        mountinfo = ""
    # Watch the filesystems used by the OS, logs/packages, and the current user.
    for label, path in (("root", Path("/")), ("var", Path("/var")), ("home", Path.home())):
        try:
            fs = os.statvfs(path)
            device = disk_identity(path, getattr(fs, "f_fsid", 0) or path.stat().st_dev, mountinfo)
            if device in devices:
                continue
            devices.add(device)
            sample["disks"][label] = {
                "free": fs.f_bavail * fs.f_frsize, "total": fs.f_blocks * fs.f_frsize,
                "inodes_free": fs.f_favail, "inodes_total": fs.f_files,
                "device": device,
            }
        except OSError:
            sample["unavailable"].append("disk:" + label)
    try:
        mem = dict(re.findall(r"^(\w+):\s+(\d+)", Path("/proc/meminfo").read_text(), re.M))
        psi = re.search(r"^some .*?avg60=([\d.]+)", Path("/proc/pressure/memory").read_text(), re.M)
        sample["memory"] = {"available_pct": 100 * int(mem["MemAvailable"]) / int(mem["MemTotal"]),
                            "stall_pct": float(psi.group(1))}
    except (OSError, KeyError, ValueError, ZeroDivisionError, AttributeError):
        sample["unavailable"].append("memory-pressure")
    try:
        result = subprocess.run(["journalctl", "-k", "-b", "--since", "10 minutes ago", "-n", "300",
                                 "-o", "json", "--output-fields=MESSAGE", "--no-pager"],
                                capture_output=True, text=True, timeout=10)
        if result.returncode or "not seeing messages" in result.stderr or "permission" in result.stderr.lower():
            sample["unavailable"].append("kernel-journal")
        else:
            for line in result.stdout.splitlines():
                try:
                    entry = json.loads(line)
                    message = entry.get("MESSAGE", "")
                    stamp = int(entry["__REALTIME_TIMESTAMP"]) // 1_000_000
                    if not isinstance(message, str) or not now - 600 <= stamp <= now:
                        continue
                    for code, pattern in KERNEL_PATTERNS.items():
                        if pattern.search(message):
                            sample["kernel"].setdefault(code, []).append(stamp)
                except (ValueError, KeyError, TypeError):
                    continue
    except (OSError, subprocess.TimeoutExpired):
        sample["unavailable"].append("kernel-journal")
    return sample


def candidates(sample, samples):
    found = {}

    def add(code, resource, evidence):
        found[code + ":" + resource] = {"code": code, "resource": resource, "evidence": evidence}

    for label, disk in sample["disks"].items():
        total, free = disk["total"], disk["free"]
        if total and free / total < .10 and free < 10 * 1024**3:
            add("disk-space", label, {"available_bytes": free, "available_pct": round(100 * free / total, 2)})
        if disk["inodes_total"] and disk["inodes_free"] / disk["inodes_total"] < .05:
            add("disk-inodes", label, {"available_inodes": disk["inodes_free"],
                                      "available_pct": round(100 * disk["inodes_free"] / disk["inodes_total"], 2)})
        points = [(s["time"], s["disks"][label]["free"]) for s in samples
                  if label in s["disks"] and s["disks"][label].get("device") == disk.get("device")
                  and s["disks"][label]["total"] == total]
        if len(points) >= 6 and points[-1][0] - points[0][0] >= 900:
            elapsed, consumed = points[-1][0] - points[0][0], points[0][1] - free
            falling = sum(b[1] < a[1] for a, b in zip(points, points[1:]))
            if consumed >= 100 * 1024**2 and falling / (len(points) - 1) >= .8:
                hours = free / (consumed / elapsed) / 3600
                if 0 < hours <= 24:
                    add("disk-trend", label, {"estimated_hours": round(hours, 2), "window_seconds": elapsed,
                                             "consumed_bytes": consumed, "assumption": "recent-growth-continues"})
    memory = sample.get("memory")
    if memory and memory["available_pct"] < 10 and memory["stall_pct"] >= 10:
        add("memory-pressure", "system", {k: round(v, 2) for k, v in memory.items()})
    for code, stamps in sample["kernel"].items():
        # Repeated sampling of one old message must not turn it into a pattern.
        unique = set(stamps)
        if code in RULES and len(unique) >= 3:
            add(code, "system", {"distinct_seconds": len(unique), "window_seconds": 600,
                                 "first_seen": min(unique), "last_seen": max(unique)})
    return found


def poll(state_dir, sample=None):
    """One writer at a time; require three samples spanning two minutes, persist episodes."""
    state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (state_dir / "health.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        path = state_dir / "health.json"
        data = read_json(path, {})
        if not isinstance(data, dict):
            data = {}
        sample = collect() if sample is None else sample
        now = sample["time"]
        samples = data.get("samples", [])
        if samples and 0 <= now - samples[-1]["time"] < 50:
            return []
        if samples and not 0 <= now - samples[-1]["time"] <= 180:
            samples = []  # Sleep/restart gaps don't establish persistence.
            data["streaks"] = {}
        samples = [s for s in samples if now - 3600 <= s["time"] < now] + [sample]
        found = candidates(sample, samples)
        streaks, events = data.get("streaks", {}), data.get("events", [])
        opened = []
        for key in set(streaks) | set(found) | {e["key"] for e in events if not e.get("ended")}:
            streak = streaks.setdefault(key, {"count": 0, "clear": 0, "start": now})
            active = next((e for e in reversed(events) if e["key"] == key and not e.get("ended")), None)
            if key in found:
                streak["count"] += 1
                streak["clear"] = 0
                if active:
                    active["evidence"] = found[key]["evidence"]
                    active["last_seen"] = now
                elif streak["count"] >= 3 and now - streak["start"] >= 120:
                    event = {**found[key], "key": key, "time": now, "last_seen": now,
                             "id": "health-" + hashlib.sha256(f"{key}:{now}".encode()).hexdigest()[:24]}
                    events.append(event)
                    opened.append(event)
            else:
                # Missing data is not evidence of recovery.
                code, resource = key.split(":", 1)
                unavailable = sample.get("unavailable", [])
                unknown = (code.startswith("disk-") and resource not in sample["disks"] or
                           code == "disk-trend" and samples[-1]["time"] - samples[0]["time"] < 900 or
                           code == "memory-pressure" and "memory" not in sample or
                           code.startswith("kernel-") and "kernel-journal" in unavailable)
                streak["count"], streak["start"] = 0, now
                if unknown:
                    streak["clear"] = 0
                    continue
                streak["clear"] += 1
                if active and streak["clear"] >= 3:
                    active["ended"] = now
        # Preserve active warnings; retain the most recent 100 closed episodes.
        closed = [e for e in events if e.get("ended")][-100:]
        active = [e for e in events if not e.get("ended")]
        write_json(path, {"samples": samples[-61:], "streaks": streaks, "events": closed + active,
                          "checked_at": now, "unavailable": sample.get("unavailable", [])})
        return opened


def history(state_dir):
    data = read_json(state_dir / "health.json", {})
    return data.get("events", []) if isinstance(data, dict) else []
