"""Find EXACT duplicates only. Same md5Checksum, or identical exported text for Google Docs.

python tools/dedupe.py    # reads runs/current/candidates.json, writes runs/current/duplicates.json
Each group is [keep_id, *duplicate_ids], newest first. Content is never combined.
"""
import hashlib
import os
import re
from collections import defaultdict

from common import read_json, run, run_dir, write_json
from google_client import EXPORT_MIME
from guard import Blocked

NATIVE_PREFIX = "application/vnd.google-apps."  # kept for callers; comparison uses EXPORT_MIME
_NOISE = [re.compile(r"^copy of\s+", re.I), re.compile(r"\s\(\d+\)$")]


def _norm(name):
    n = os.path.splitext(name or "")[0].strip()
    for r in _NOISE:
        n = r.sub("", n)
    return n.lower().strip()


def _ordered(files):
    return [x["id"] for x in sorted(files, key=lambda x: x.get("modifiedTime") or "", reverse=True)]


def groups(files, text_of, may_read=lambda f: True):
    """md5 groups need no reading. Text comparison only for files that may_read() allows."""
    out = []
    by_md5 = defaultdict(list)
    native_by_name = defaultdict(list)
    for x in files:
        if x.get("md5Checksum"):
            by_md5[x["md5Checksum"]].append(x)
        elif x.get("mimeType") in EXPORT_MIME and may_read(x):  # Forms, Drawings etc. can't export
            native_by_name[(x["mimeType"], _norm(x["name"]))].append(x)
    out += [_ordered(g) for g in by_md5.values() if len(g) > 1]
    for cluster in native_by_name.values():
        if len(cluster) < 2:
            continue
        by_text = defaultdict(list)
        for x in cluster:
            try:
                text = text_of(x["id"])
            except Blocked:
                raise  # a protected file still stops the run
            except Exception:
                continue  # can't compare this one: treat it as unique, don't sink the run
            by_text[hashlib.sha256(text.encode()).hexdigest()].append(x)
        out += [_ordered(g) for g in by_text.values() if len(g) > 1]
    return out


def main(argv):
    from google_client import from_env
    client = from_env()
    rd = run_dir()
    import screen
    cands = read_json(os.path.join(rd, "candidates.json"))["candidates"]
    state = read_json(os.path.join(rd, "state.json"), {}) or {}
    out = groups(cands, text_of=client.export_text,
                 may_read=lambda f: not screen.is_unread(state, f))
    write_json(os.path.join(rd, "duplicates.json"), out)
    print(f"duplicate_groups={len(out)}")
    return 0


if __name__ == "__main__":
    run(main)
