#!/usr/bin/env python3
"""PreToolUse gate for Write/Edit/NotebookEdit. Protects the guard, settings and hooks."""
import os

PROTECTED_FILES = {"tools/guard.py", ".claude/settings.json", ".claude/settings.local.json"}
PROTECTED_DIRS = {".claude/hooks"}


def decide(hook_input, project_dir):
    ti = hook_input.get("tool_input", {})
    path = ti.get("file_path") or ti.get("notebook_path")
    if not path:
        return False, "no path"
    root = os.path.realpath(project_dir)
    full = os.path.realpath(os.path.join(hook_input.get("cwd", root), path))
    rel = os.path.relpath(full, root).lower()  # case-insensitive filesystems
    if rel in PROTECTED_FILES or any(rel == d or rel.startswith(d + os.sep) for d in PROTECTED_DIRS):
        return False, "protected file: only the owner edits this by hand"
    return True, "ok"


if __name__ == "__main__":
    import json
    import sys
    try:
        data = json.load(sys.stdin)
        ok, reason = decide(data, os.environ.get("CLAUDE_PROJECT_DIR") or data.get("cwd") or os.getcwd())
    except Exception:
        ok, reason = False, "gate error"
    if not ok:
        print(f"edit_gate: blocked ({reason})", file=sys.stderr)
        sys.exit(2)
