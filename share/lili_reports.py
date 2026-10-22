"""Portable incident reports: allowlisted metadata, local aggregation, no log text."""
import hashlib
import fcntl
import json
import os
from pathlib import Path
import re
import time
import uuid


SCHEMA = "lili.incidents/v1"
KINDS = {"crash", "freeze", "steam", "launch", "update", "health"}


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def token(value):
    value = str(value or "unknown")
    return value if re.fullmatch(r"[A-Za-z0-9_.:+-]{1,128}", value) else "private-" + digest(value)[:16]


def machine_id(state_dir):
    state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = state_dir / "report-machine-id"
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    with os.fdopen(fd, "r+") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        value = stream.read().strip()
        if value:
            return str(uuid.UUID(value))
        value = str(uuid.uuid4())
        stream.write(value + "\n")
        stream.flush()
        return value


def classify(program, event):
    key = program["exe"]
    if key.startswith("health:"):
        return "health", token(event["resource"]), token(event["code"])
    if key == "freeze":
        return "freeze", token(event.get("tag") or "system"), token(event.get("kind"))
    for kind in ("steam", "launch", "update"):
        if key.startswith(kind + ":"):
            component = key.split(":", 1)[1]
            if "/" in component:
                component = "private-" + digest(component)[:16]
            category = (event.get("kind", "error") if kind == "update" else
                        "early-exit" if kind == "steam" else "exit-" + str(event.get("status", "unknown")))
            return kind, token(component), token(category)
    # Standard binary names are useful for fleet correlation. Custom paths remain pseudonymous.
    component = Path(key).name if key.startswith(("/usr/", "/bin/", "/sbin/")) else "private-" + digest(key)[:16]
    return "crash", token(component), token(event.get("signal"))


def build(programs, state_dir, days=30, now=None):
    now = int(time.time() if now is None else now)
    since = now - days * 86400
    events = {}
    for program in programs:
        for event in program["crashes"]:
            stamp = event["time"]
            if not since <= stamp <= now:
                continue
            kind, component, category = classify(program, event)
            signature = f"{kind}:{component}:{category}"
            source_id = event.get("id") or event.get("boot") or event.get("pid") or event.get("start", stamp)
            event_id = digest(f"{program['exe']}:{source_id}:{stamp}")
            events[event_id] = {"id": event_id, "time": stamp, "kind": kind,
                                "component": component, "category": category,
                                "fingerprint": digest(signature),
                                "status": "resolved" if event.get("ended") else program["state"]}
    return {"schema": SCHEMA, "machine_id": machine_id(state_dir), "generated_at": now,
            "window": {"since": since, "until": now},
            "privacy": "No raw logs, hostnames, usernames, paths, or diagnosis text. Application identifiers remain.",
            "events": sorted(events.values(), key=lambda e: (e["time"], e["id"]))}


def validate(report):
    if not isinstance(report, dict) or report.get("schema") != SCHEMA:
        raise ValueError("Unsupported report schema (expected lili.incidents/v1)")
    try:
        uuid.UUID(report["machine_id"])
        window = report["window"]
        if (type(window["since"]) is not int or type(window["until"]) is not int or
                not 0 <= window["since"] <= window["until"] or
                type(report["generated_at"]) is not int):
            raise ValueError("Invalid report time window")
        events = report["events"]
        if not isinstance(events, list) or len(events) > 100000:
            raise ValueError("Invalid or oversized event list")
        for event in events:
            if (event["kind"] not in KINDS or
                    event["status"] not in ("new", "diagnosed", "resolved", "ignored") or
                    type(event["time"]) is not int or not window["since"] <= event["time"] <= window["until"] or
                    any(not re.fullmatch(r"[0-9a-f]{64}", event[k]) for k in ("id", "fingerprint")) or
                    any(not re.fullmatch(r"[A-Za-z0-9_.:+-]{1,128}", event[k]) for k in ("component", "category")) or
                    event["fingerprint"] != digest(f"{event['kind']}:{event['component']}:{event['category']}")):
                raise ValueError("Invalid incident record")
    except (KeyError, TypeError, AttributeError) as error:
        raise ValueError("Malformed incident report") from error


def aggregate(reports):
    """Newest export wins; count an incident once even with overlapping exports."""
    unique, machines, windows = {}, set(), []
    for report in reports:
        validate(report)
    for report in sorted(reports, key=lambda r: r["generated_at"]):
        machine = report["machine_id"]
        machines.add(machine)
        windows.append(report["window"])
        for event in report["events"]:
            unique[(machine, event["id"])] = event
    grouped = {}
    for (machine, _event_id), event in unique.items():
        key = event["fingerprint"]
        group = grouped.setdefault(key, {"fingerprint": key, "kind": event["kind"],
                                        "component": event["component"], "category": event["category"],
                                        "occurrences": 0, "machines": set(), "first_seen": event["time"],
                                        "last_seen": event["time"], "status_counts": {}})
        group["occurrences"] += 1
        group["machines"].add(machine)
        group["status_counts"][event["status"]] = group["status_counts"].get(event["status"], 0) + 1
        group["first_seen"] = min(group["first_seen"], event["time"])
        group["last_seen"] = max(group["last_seen"], event["time"])
    for group in grouped.values():
        group["machines"] = sorted(group["machines"])
        group["machine_count"] = len(group["machines"])
        group["recurring"] = group["occurrences"] > 1
    return {"schema": "lili.fleet/v1", "machine_count": len(machines), "incident_count": len(unique),
            "windows": windows, "note": "Matching symptoms are not proof of a shared root cause. Coverage depends on retained logs.",
            "patterns": sorted(grouped.values(), key=lambda g: (-g["machine_count"], -g["occurrences"], g["fingerprint"]))}


def read(path):
    with Path(path).open("rb") as stream:
        raw = stream.read(20 * 1024**2 + 1)
    if len(raw) > 20 * 1024**2:
        raise ValueError("Report exceeds 20 MiB")
    return json.loads(raw)


def save(path, report):
    # An export must not overwrite an existing report or follow a destination symlink.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
