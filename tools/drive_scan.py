"""List new/changed files as candidates. Blocked files are counted, never named.

python tools/drive_scan.py [--since ISO|auto] [--limit N] [--dry] [--out PATH]
  --dry   smoke test: print up to N allowed names + blocked_count, write nothing
"""
import argparse
import os

from common import load_config, read_json, run, run_dir, write_json

FIELDS = ("id", "name", "mimeType", "size", "modifiedTime", "viewedByMeTime",
          "path", "md5Checksum", "webViewLink")


AGENT_FOLDER = "_DriveAgent"


def _agent_owned(f):
    p = f.get("path") or ""
    return p == AGENT_FOLDER or p.startswith(AGENT_FOLDER + "/")


def folder_map(files):
    """{folder path: file count} for the classifier to design a structure from. Paths only."""
    out = {}
    for f in files:
        if not _agent_owned(f):
            out[f.get("path") or ""] = out.get(f.get("path") or "", 0) + 1
    return out


def scan(client, state, since, cap):
    files, blocked = client.list_allowed(since=since)
    whole = files if not since else client.list_allowed()[0]  # the map always covers the whole Drive
    files = [f for f in files if not _agent_owned(f)]  # its own state, logs, sheets: never organised
    placed = state.get("placed", {})
    candidates, skipped = [], 0
    for f in files:
        if f.get("modifiedTime") in (placed.get(f["id"]), state.get("seen", {}).get(f["id"])) \
                and f.get("modifiedTime") is not None:
            skipped += 1
            continue
        candidates.append({k: f.get(k) for k in FIELDS})
    return {"candidates": candidates[:cap], "blocked_count": blocked, "folders": folder_map(whole),
            "skipped_unchanged": skipped, "truncated": len(candidates) > cap}


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="auto")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--out", default=os.path.join(run_dir(), "candidates.json"))
    a = ap.parse_args(argv)
    from google_client import from_env
    cfg = load_config()
    client = from_env()
    state = read_json(os.path.join(run_dir(), "state.json"), {}) or {}
    since = state.get("scan_since") if a.since == "auto" else a.since  # not legacy last_run
    out = scan(client, state, since, a.limit or cfg["max_files_per_run"])
    if a.dry:
        for c in out["candidates"][: a.limit or 5]:
            print(f"{c['mimeType']:<45} {c['path']}/{c['name']}")
        print(f"candidates={len(out['candidates'])} blocked_count={out['blocked_count']}")
        return 0
    write_json(os.path.join(os.path.dirname(a.out), "folders.json"), out.pop("folders"))
    write_json(a.out, out)
    print(f"candidates={len(out['candidates'])} blocked_count={out['blocked_count']} "
          f"skipped_unchanged={out['skipped_unchanged']} -> {a.out}")
    return 0


if __name__ == "__main__":
    run(main)
