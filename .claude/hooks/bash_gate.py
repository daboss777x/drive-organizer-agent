#!/usr/bin/env python3
"""PreToolUse gate for Bash. Allows only `python tools/<name>.py ...` and pytest."""
import re
import shlex

PYTHONS = {"python", "python3"}
TOOL_SCRIPT = re.compile(r"^tools/[a-z_]+\.py$")
LOCAL_ONLY = {"tools/get_refresh_token.py"}   # never run where credentials exist
METACHARS = re.compile(r"[;&|<>$`\\(){}\n\r]")


def decide(hook_input, env):
    # Enforced whenever Google credentials are reachable (always in the cloud).
    if not (env.get("GOOGLE_REFRESH_TOKEN") or env.get("DRIVE_BRIDGE_SECRET")):
        return True, "gate off: no Google credentials in this environment"
    cmd = hook_input.get("tool_input", {}).get("command", "")
    if METACHARS.search(cmd):
        return False, "shell metacharacters are not allowed"
    try:
        argv = shlex.split(cmd)
    except ValueError:
        return False, "unparseable command"
    if not argv:
        return False, "empty command"
    if argv[0] == "pytest":
        return True, "ok"
    if argv[0] in PYTHONS and len(argv) >= 2:
        if argv[1:3] == ["-m", "pytest"]:
            return True, "ok"
        if TOOL_SCRIPT.match(argv[1]) and argv[1] not in LOCAL_ONLY:
            return True, "ok"
    return False, "only `python tools/<name>.py ...` and `pytest` are allowed"


if __name__ == "__main__":
    import json
    import os
    import sys
    try:
        ok, reason = decide(json.load(sys.stdin), os.environ)
    except Exception:
        ok, reason = False, "gate error"
    if not ok:
        print(f"bash_gate: blocked ({reason})", file=sys.stderr)
        sys.exit(2)
