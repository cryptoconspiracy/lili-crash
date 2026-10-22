#!/usr/bin/env python3
"""Check the complete release set, payload integrity and installed CLI entry points."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
TARGETS = {
    "arch": "any.pkg.tar.zst", "debian12": "all.deb", "debian13": "all.deb",
    "ubuntu22.04": "all.deb", "ubuntu24.04": "all.deb", "ubuntu25.10": "all.deb", "ubuntu26.04": "all.deb",
    "fedora43": "noarch.rpm", "fedora44": "noarch.rpm",
    "opensuse-leap16.0": "noarch.rpm", "opensuse-tumbleweed": "noarch.rpm",
}
FILES = {
    "bin/lili-crash": "usr/bin/lili-crash",
    **{f"share/{name}.py": f"usr/share/lili-crash/{name}.py"
       for name in ("lili_health", "lili_reports", "lili_privacy", "package_window")},
    "skill/lili-diagnose-crash/SKILL.md": "usr/share/lili-crash/skill/lili-diagnose-crash/SKILL.md",
    "skill/lili-install-package/SKILL.md": "usr/share/lili-crash/skill/lili-install-package/SKILL.md",
    "plasma/lili/contents/ui/main.qml": "usr/share/plasma/plasmoids/lili/contents/ui/main.qml",
}


def run(*args, **kwargs):
    return subprocess.check_output(args, timeout=60, **kwargs)


def verify(version):
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("Invalid version")
    directory = ROOT / "packages" / version
    names = {f"lili-crash-{version}-{target}.{suffix}" for target, suffix in TARGETS.items()}
    sums = {}
    for line in (directory / "SHA256SUMS").read_text().splitlines():
        checksum, name = line.split(maxsplit=1)
        if name in sums:
            raise ValueError("Duplicate checksum entry")
        sums[name] = checksum
    if set(sums) != names:
        raise ValueError(f"Incomplete package set: missing={names - sums.keys()}, extra={sums.keys() - names}")
    for name in sorted(names):
        package = directory / name
        if hashlib.sha256(package.read_bytes()).hexdigest() != sums[name]:
            raise ValueError(f"Checksum mismatch: {name}")
        with tempfile.TemporaryDirectory(prefix="lili-package-check-") as temporary:
            work = Path(temporary)
            payload = package
            if name.endswith(".deb"):
                members = run("bsdtar", "-tf", str(package), text=True).splitlines()
                data = [entry for entry in members if entry.startswith("data.tar")]
                if len(data) != 1:
                    raise ValueError("Debian package must contain one data archive")
                payload = work / data[0]
                payload.write_bytes(run("bsdtar", "-xOf", str(package), data[0]))
            members = run("bsdtar", "-tf", str(payload), text=True).splitlines()
            if any(PurePosixPath(entry).is_absolute() or ".." in PurePosixPath(entry).parts for entry in members):
                raise ValueError("Unsafe archive path")
            installed = work / "installed"
            installed.mkdir()
            run("bsdtar", "-xf", str(payload), "-C", str(installed), "--no-same-owner", "--no-same-permissions")
            for source, destination in FILES.items():
                if (installed / destination).read_bytes() != (ROOT / source).read_bytes():
                    raise ValueError(f"Payload mismatch: {name}: {destination}")
            metadata = json.loads((installed / "usr/share/plasma/plasmoids/lili/metadata.json").read_text())
            if metadata["KPlugin"]["Version"] != version:
                raise ValueError(f"Incorrect embedded version: {name}")
            command = str(installed / "usr/bin/lili-crash")
            if not os.access(command, os.X_OK):
                raise ValueError("Installed entry point is not executable")
            env = {**os.environ, "XDG_STATE_HOME": str(work / "state"), "XDG_CONFIG_HOME": str(work / "config")}
            measurement = json.loads(run(command, "health", env=env, text=True))
            if "sample" not in measurement or "candidates" not in measurement:
                raise ValueError("Installed health command failed")
            report = work / "report.json"
            run(command, "report", "export", str(report), env=env)
            exported = json.loads(report.read_text())
            combined = json.loads(run(command, "report", "aggregate", str(report), str(report), env=env))
            if combined["incident_count"] != len(exported["events"]) or combined["machine_count"] != 1:
                raise ValueError("Installed report aggregation failed")
        print(f"PASS {name}: checksum, payload, version, health and reports", flush=True)


if __name__ == "__main__":
    verify(sys.argv[1])
