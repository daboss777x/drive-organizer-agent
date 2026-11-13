"""Gate 8: post-run audit. Every Drive-ID-shaped token in the run artifacts is re-checked
with the guard. Any protected hit, or any error, fails the audit.

python tools/audit.py        # prints only "ok" or "SECURITY ABORT"; writes runs/current/audit.json
It never lists the forbidden folder and never prints which token failed.
"""
import os
import re

from common import ROOT, run, run_dir, write_json

ID_TOKEN = re.compile(r"[A-Za-z0-9_-]{25,}")
TEXT_EXT = (".json", ".md", ".log", ".txt", ".csv", ".html")


def _files(paths):
    for p in paths:
        if os.path.isfile(p):
            yield p
        for dirpath, _, names in os.walk(p):
            for n in names:
                if n.endswith(TEXT_EXT):
                    yield os.path.join(dirpath, n)


def known_ok_ids(client):
    """IDs that passed both guards in one fresh full listing: one call instead of one per ID."""
    try:
        files, _ = client.list_allowed()
    except Exception:
        return set()  # no shortcut: every ID gets checked one by one (slow but safe)
    return {f["id"] for f in files}


def check(paths, guard, get_meta, known_ok=()):
    from google_client import NotFound
    try:
        tokens = set()
        for f in _files(paths):
            with open(f, encoding="utf-8", errors="replace") as fh:
                tokens |= set(ID_TOKEN.findall(fh.read()))
        literal = guard.folder_ids | guard.file_ids
        for t in tokens:
            if t in literal:
                return False
            if t in known_ok:  # guard-checked moments ago in a fresh listing
                continue
            try:
                meta = get_meta(t)
            except NotFound:
                continue  # not a Drive file (a hash, a URL fragment...)
            if guard.is_blocked(meta, get_meta):
                return False
        return True
    except Exception:
        return False


def main(argv):
    from google_client import from_env
    client = from_env()
    rd = run_dir()
    paths = [rd, os.path.join(ROOT, "rules.md"), os.path.join(ROOT, "business_context.md")]
    ok = check(paths, client.guard, client.api.get_meta, known_ok=known_ok_ids(client))
    write_json(os.path.join(rd, "audit.json"), {"ok": ok})
    print("ok" if ok else "SECURITY ABORT")
    return 0 if ok else 4


if __name__ == "__main__":
    run(main)
