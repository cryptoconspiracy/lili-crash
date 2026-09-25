#!/usr/bin/python3
"""Prints the usage limits of the installed coding agents as JSON.

Claude Code: the endpoint behind its /usage command, with the OAuth token Claude
Code stores. The token only ever goes to api.anthropic.com.
Codex: its own app-server, asked over stdin the same way the Codex UI asks.

Errors come back as codes; the widget turns them into text in the user's language.
When a request fails, the last good result is returned marked as stale.
"""

import json
import os
import re
import select
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HOME = Path.home()
CLAUDE_DIR = Path(os.environ.get("CLAUDE_CONFIG_DIR") or HOME / ".claude")
CODEX_DIR = Path(os.environ.get("CODEX_HOME") or HOME / ".codex")
CACHE = Path(os.environ.get("XDG_CACHE_HOME") or HOME / ".cache") / "lili" / "usage.json"


def which(name):
    return shutil.which(name, path=os.pathsep.join([str(HOME / ".local/bin"), os.environ.get("PATH", "")]))


def claude():
    if not which("claude"):
        return {"error": "not_installed"}
    try:
        settings = json.loads((CLAUDE_DIR / "settings.json").read_text())
    except (OSError, ValueError):
        settings = {}
    result = {"model": settings.get("model") or ""}
    try:
        login = json.loads((CLAUDE_DIR / ".credentials.json").read_text())["claudeAiOauth"]
    except (OSError, KeyError, ValueError):
        return {**result, "error": "no_login"}
    result["plan"] = login.get("subscriptionType") or ""

    # Claude Code refreshes the token whenever it runs. Refreshing it here would
    # rotate the refresh token out from under it.
    if login.get("expiresAt", 0) / 1000 < time.time():
        return {**result, "error": "expired"}

    request = urllib.request.Request("https://api.anthropic.com/api/oauth/usage", headers={
        "Authorization": "Bearer " + login["accessToken"],
        "anthropic-beta": "oauth-2025-04-20",
        "User-Agent": "lili/0.2",
    })
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            data = json.load(response)
    except urllib.error.HTTPError as e:
        return {**result, "error": "expired" if e.code == 401 else "http", "status": e.code}
    except (urllib.error.URLError, TimeoutError, ValueError):
        return {**result, "error": "offline"}

    def window(bucket):
        if not bucket or bucket.get("utilization") is None:
            return None
        return {"percent": round(float(bucket["utilization"])), "resets": bucket.get("resets_at")}

    return {**result, "session": window(data.get("five_hour")), "week": window(data.get("seven_day"))}


def rpc(proc, request_id, method, params=None, timeout=6):
    proc.stdin.write(json.dumps({"id": request_id, "method": method, "params": params or {}}) + "\n")
    proc.stdin.flush()
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not select.select([proc.stdout], [], [], 0.25)[0]:
            continue
        line = proc.stdout.readline()
        if not line:
            break
        try:
            message = json.loads(line)
        except ValueError:
            continue
        if message.get("id") == request_id:
            return message.get("result") or {}
    raise TimeoutError(method)


def codex():
    binary = which("codex")
    if not binary:
        return {"error": "not_installed"}
    try:
        model = re.search(r'^model\s*=\s*"([^"]+)"', (CODEX_DIR / "config.toml").read_text(), re.M).group(1)
    except (OSError, AttributeError):
        model = ""
    result = {"model": model}
    try:
        proc = subprocess.Popen([binary, "-s", "read-only", "-a", "on-request", "app-server"], stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    except OSError:
        return {**result, "error": "offline"}
    try:
        rpc(proc, 1, "initialize", {"clientInfo": {"name": "lili", "version": "0.2"}})
        proc.stdin.write(json.dumps({"method": "initialized", "params": {}}) + "\n")
        proc.stdin.flush()
        limits = rpc(proc, 2, "account/rateLimits/read").get("rateLimits") or {}
    except (TimeoutError, OSError, ValueError):
        return {**result, "error": "no_login"}
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=1)
        except subprocess.TimeoutExpired:
            proc.kill()

    def window(w):
        if not isinstance(w, dict) or w.get("usedPercent") is None:
            return None
        resets = w.get("resetsAt")
        return {"percent": round(float(w["usedPercent"])),
                "resets": datetime.fromtimestamp(float(resets), timezone.utc).isoformat() if resets else None}

    return {**result, "plan": limits.get("planType") or "",
            "session": window(limits.get("primary")), "week": window(limits.get("secondary"))}


def main():
    try:
        previous = json.loads(CACHE.read_text())
    except (OSError, ValueError):
        previous = {}
    agents = {"claude": claude(), "codex": codex()}
    for name, fresh in agents.items():
        old = previous.get(name) or {}
        if fresh.get("error") in ("offline", "http", "expired") and old.get("session"):
            agents[name] = {**old, "error": fresh["error"], "stale": True}
    agents["updated"] = int(time.time())
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(agents))
    print(json.dumps(agents))


if __name__ == "__main__":
    main()
