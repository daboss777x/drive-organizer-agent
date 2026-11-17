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
    """IDs (files AND folders) that pass both guards in one fresh listing: one call, not hundreds."""
    try:
        raw = client.api.list_files(exclude_parents=client.guard.folder_ids)
        index = {f["id"]: f for f in raw}

        def lookup(i):
            if i not in index:
                index[i] = client.api.get_meta(i)
            return index[i]
        return {f["id"] for f in raw if not client.guard.is_blocked(f, lookup)}
    except Exception:
        return set()  # no shortcut: every ID gets checked one by one (slow but safe)


def run_checksums(rd):
    """md5 checksums in this run's candidates look like IDs but aren't: don't look them up."""
    from common import read_json
    cands = (read_json(os.path.join(rd, "candidates.json"), {}) or {}).get("candidates", [])
    return {c["md5Checksum"] for c in cands if c.get("md5Checksum")}


def check(paths, guard, get_meta, known_ok=(), not_ids=()):
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
            if t in known_ok or t in not_ids:  # guard-checked moments ago / a checksum, not an ID
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
    ok = check(paths, client.guard, client.api.get_meta, known_ok=known_ok_ids(client),
               not_ids=run_checksums(rd))
    write_json(os.path.join(rd, "audit.json"), {"ok": ok})
    print("ok" if ok else "SECURITY ABORT")
    return 0 if ok else 4


if __name__ == "__main__":
    run(main)
