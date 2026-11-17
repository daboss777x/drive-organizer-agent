"""Agent state: summary cache (keyed by id + modifiedTime), placed files, scan_since (the scan bookmark).

Lives in Drive at _DriveAgent/state.json; a working copy sits in runs/<run>/state.json.
  python tools/state.py begin                     # fresh runs/current, then pull
  python tools/state.py pull                      # Drive -> runs/current/state.json
  python tools/state.py push                      # runs/current/state.json -> Drive
  python tools/state.py merge                     # runs/current/summaries/*.json -> cache
  python tools/state.py todo                      # to_summarize.json + screen_input.json (names only)
  python tools/state.py screen                    # screen_ai.json + word catalog -> batches/, flagged.json
  python tools/state.py digest                    # candidates + summaries -> classify_input.json
  python tools/state.py learn                     # files the owner moved after the agent placed them -> corrections.json
  python tools/state.py finish                    # move scan_since (live + uncapped scans only), then push
  python tools/state.py save-structure            # runs/current/structure.md -> state (the target map)
  python tools/state.py reorganise                # forget decisions so the next runs re-sort the WHOLE Drive
"""
import glob
import json
import os
from datetime import datetime, timezone

from common import read_json, run, run_dir, write_json

STATE_NAME = "state.json"


def needs_summary(state, f):
    hit = state.get("summaries", {}).get(f["id"])
    return not hit or hit.get("modifiedTime") != f.get("modifiedTime")


def put_summary(state, f, summary):
    state.setdefault("summaries", {})[f["id"]] = {
        "modifiedTime": f.get("modifiedTime"), "summary": summary}


def get_summary(state, file_id):
    hit = state.get("summaries", {}).get(file_id)
    return hit["summary"] if hit else None


def merge(state, candidates, batches):
    known = {c["id"]: c for c in candidates}
    added = 0
    for batch in batches:
        for s in batch:
            if isinstance(s, dict) and s.get("id") in known:
                put_summary(state, known[s["id"]], s)
                added += 1
    return added


def mark_seen(state, ids, cands):
    """Files with a decision (incl. keep) aren't scanned again until their modifiedTime changes,
    so each live run works through the NEXT batch of the Drive instead of the same newest 150."""
    seen = state.setdefault("seen", {})
    for i in ids:
        if i in cands:
            seen[i] = cands[i].get("modifiedTime")


def mark_placed(state, file_id, modified_time):
    state.setdefault("placed", {})[file_id] = modified_time


def finish_state(state, scan, dry_run, now):
    """Move the scan bookmark only after a LIVE run whose scan wasn't capped. Otherwise the next
    scan would only see files changed since now, and the unscanned backlog would be skipped forever.
    (The old `last_run` key is ignored: a dry run once set it.)"""
    if not dry_run and not scan.get("truncated"):
        state["scan_since"] = now
    return state


def reorganise(state):
    """Re-sort the whole Drive with the current rules: forget which files were decided and where the
    scan got to. What was learned (summaries, screen, the owner's corrections/feedback, the map) stays."""
    for k in ("seen", "placed"):
        state[k] = {}
    state.pop("scan_since", None)
    return state


def save_structure(state, text):
    if (text or "").strip():
        state["structure"] = text.strip() + "\n"


def structure_text(state):
    return state.get("structure", "")


DIGEST_KEYS = ("id", "name", "path", "mimeType", "modifiedTime", "viewedByMeTime")


def digest_rows(state, cands):
    """Classifier input. Read files come with their summary. Name-flagged files come by NAME ONLY
    (unread: true, no summary) so they can be filed unread. Real-secret names (identity,
    credentials, health) and the owner's "keep where it is" are left out entirely."""
    import screen
    rows = []
    for c in cands:
        if c["id"] in state.get("screen_never", {}) or screen.strict_flag(c.get("name"), c.get("path")):
            continue
        row = {k: c.get(k) for k in DIGEST_KEYS}
        if screen.is_unread(state, c):
            rows.append({**row, "summary": None, "unread": True})
        else:
            rows.append({**row, "summary": get_summary(state, c["id"])})
    return rows


ID_DICTS = ("screen", "summaries", "seen", "placed", "placed_to", "screen_cleared", "screen_never")
ID_LISTS = ("history", "corrections", "feedback", "open_questions")


def prune_protected(state, allowed):
    """Forget every file the guard no longer allows (moved into the forbidden folder, or gone):
    no ID and no name of it may stay in memory. Returns how many files were dropped (count only)."""
    ids = set()
    for k in ID_DICTS:
        ids |= set(state.get(k, {}))
    for k in ID_LISTS:
        ids |= {e.get("id") for e in state.get(k, []) if isinstance(e, dict) and e.get("id")}
    gone = {i for i in ids if not allowed(i)}
    for k in ID_DICTS:
        if k in state:
            state[k] = {i: v for i, v in state[k].items() if i not in gone}
    for k in ID_LISTS:
        if k in state:
            state[k] = [e for e in state[k] if not (isinstance(e, dict) and e.get("id") in gone)]
    return len(gone)


def allowed_now(client):
    """allowed(id) for prune_protected: one fresh listing, then single lookups for the rest."""
    import audit
    from google_client import NotFound
    ok = audit.known_ok_ids(client)

    def allowed(i):
        if i in ok:
            return True
        try:
            meta = client.api.get_meta(i)
            return not client.guard.is_blocked(meta, client.api.get_meta)
        except NotFound:
            return False
        except Exception:
            return False  # can't prove it's allowed: forget it (it's only a cache)
    return allowed


def pull(client):
    raw = client.read_agent_file(STATE_NAME)
    return json.loads(raw) if raw else {}


def push(client, state):
    client.write_agent_file(STATE_NAME, json.dumps(state, indent=1))


def main(argv):
    cmd = argv[0] if argv else ""
    rd = run_dir()
    path = os.path.join(rd, "state.json")
    if cmd == "begin" and os.path.isdir(rd):
        import shutil
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        shutil.move(rd, rd + f"_prev_{stamp}")
    if cmd in ("begin", "pull", "push", "finish", "learn", "reorganise"):
        from google_client import from_env
        client = from_env()
    if cmd in ("begin", "pull"):
        s = pull(client)
        if cmd == "begin":
            n = prune_protected(s, allowed_now(client))
            if n:
                print(f"forgot {n} file(s) that are now protected or gone")
        write_json(path, s)
    elif cmd == "push":
        push(client, read_json(path, {}))
    elif cmd == "finish":
        from common import load_config
        s = read_json(path, {})
        scan = read_json(os.path.join(rd, "candidates.json"), {}) or {}
        finish_state(s, scan, load_config().get("dry_run", True),
                     datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
        write_json(path, s)
        push(client, s)
    elif cmd == "todo":
        import screen
        s = read_json(path, {})
        cands = read_json(os.path.join(rd, "candidates.json"), {})["candidates"]
        todo = [c for c in cands if needs_summary(s, c)]
        write_json(os.path.join(rd, "to_summarize.json"), todo)
        ask = [{k: c.get(k) for k in ("id", "name", "path", "mimeType")} for c in screen.needs_ai(todo, s)]
        write_json(os.path.join(rd, "screen_input.json"), ask)
        print(f"to_summarize={len(todo)} cached={len(cands) - len(todo)} to_screen={len(ask)}")
    elif cmd == "screen":
        import screen
        from common import load_config
        s = read_json(path, {})
        todo = read_json(os.path.join(rd, "to_summarize.json"), [])
        out = screen.apply(todo, read_json(os.path.join(rd, "screen_ai.json"), []) or [], s)
        write_json(path, s)
        write_json(os.path.join(rd, "flagged.json"),
                   [{k: f.get(k) for k in ("id", "name", "path", "mimeType", "webViewLink", "by", "reason")}
                    for f in out["flagged"]])
        size = load_config().get("summarizer_batch_size", 10)
        read = out["read"]
        for n, i in enumerate(range(0, len(read), size), start=1):
            write_json(os.path.join(rd, "batches", f"batch_{n}.json"),
                       [{"id": c["id"], "name": c["name"], "path": c["path"],
                         "mimeType": c["mimeType"]} for c in read[i:i + size]])
        print(f"to_read={len(read)} flagged_for_review={len(out['flagged'])}")
    elif cmd == "merge":
        s = read_json(path, {})
        cands = read_json(os.path.join(rd, "candidates.json"), {})["candidates"]
        batches = [read_json(p, []) for p in sorted(glob.glob(os.path.join(rd, "summaries", "*.json")))]
        n = merge(s, cands, batches)
        write_json(path, s)
        print(f"merged={n}")
    elif cmd == "learn":
        import learn
        s = read_json(path, {})
        new, skipped = learn.collect(client, s)
        write_json(path, s)
        recent = [{k: c.get(k) for k in ("name", "agent_to", "owner_to")} for c in s.get("corrections", [])[-50:]]
        write_json(os.path.join(rd, "corrections.json"), recent)
        print(f"new_corrections={len(new)} known={len(s.get('corrections', []))} skipped={skipped}")
    elif cmd == "digest":
        s = read_json(path, {})
        rows = digest_rows(s, read_json(os.path.join(rd, "candidates.json"), {})["candidates"])
        write_json(os.path.join(rd, "classify_input.json"), rows)
        with open(os.path.join(rd, "structure.md"), "w") as fh:
            fh.write(structure_text(s))
        print(f"classify_input={len(rows)} structure={'saved' if structure_text(s) else 'none yet'}")
    elif cmd == "save-structure":
        s = read_json(path, {})
        sp = os.path.join(rd, "structure.md")
        save_structure(s, open(sp).read() if os.path.exists(sp) else "")
        write_json(path, s)
        print(f"structure_lines={len(structure_text(s).splitlines())}")
    elif cmd == "reorganise":
        s = reorganise(pull(client))
        push(client, s)
        print("reorganise: the next runs re-sort the whole Drive")
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    run(main)
