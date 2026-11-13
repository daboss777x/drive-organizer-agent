"""Apply validated actions. Guard re-checked before every action (inside GoogleClient).

python tools/execute.py runs/current/validated_plan.json [--answers runs/current/validated_answers.json]
Does nothing (status=proposed) while config.yaml has dry_run: true.
Writes runs/current/executed.json and the undo log (locally + _DriveAgent/logs/).
"""
import json
import os
from datetime import datetime, timezone

from common import load_config, read_json, run_dir, write_json
from guard import REFUSAL, Blocked

EXECUTABLE = {"move", "rename", "archive", "dedupe_archive"}
ARCHIVE = "Archive"


def _apply(client, it):
    meta = client.get_meta(it["id"])
    entry = {"id": it["id"], "old_parent": meta["parents"][0], "old_name": meta["name"]}
    if it["action"] == "rename":
        client.rename(it["id"], it["new_name"])
        entry["new_name"] = it["new_name"]
        entry["new_parent"] = entry["old_parent"]
    else:
        target = ARCHIVE if it["action"] in ("archive", "dedupe_archive") else it["target_folder"]
        dest = client.ensure_folder(target)
        client.move(it["id"], dest)
        entry["new_parent"] = dest
    entry["modifiedTime"] = meta.get("modifiedTime")
    return entry


def run_items(client, items, config):
    """Returns (results, undo_log). A refusal halts the run; later items are 'not_run'."""
    results, log, done = [], [], 0
    for i, it in enumerate(items):
        base = {k: it.get(k) for k in ("id", "action", "target_folder", "new_name", "sheet_row")}
        if it.get("action") not in EXECUTABLE:
            results.append({**base, "status": "invalid", "ok": False})
            continue
        if config.get("dry_run", True):
            results.append({**base, "status": "proposed", "ok": False})
            continue
        if done >= config["max_actions_per_run"]:
            results.append({**base, "status": "skipped_cap", "ok": False})
            continue
        try:
            log.append(_apply(client, it))
            results.append({**base, "status": "done", "ok": True})
            done += 1
        except Blocked:
            results.append({"status": "refused", "ok": False})  # no id, no name
            results += [{"id": x.get("id"), "status": "not_run", "ok": False} for x in items[i + 1:]]
            break
        except Exception as e:
            results.append({**base, "status": f"error: {type(e).__name__}", "ok": False})
    return results, log


run = run_items  # public seam name used by tests: execute.run(client, items, config)


def save_undo_log(client, state, log, stamp, run_date):
    """The run's undo log goes to _DriveAgent/logs/ (the cloud run's folder disappears after the
    run); state remembers which file belongs to which run, so /drive-review can undo a whole run."""
    name = f"undo_{stamp}.json"
    client.write_agent_file(name, json.dumps(log, indent=1), sub="logs")
    state.setdefault("undo_logs", []).append({"run": run_date, "file": name, "count": len(log)})
    state["undo_logs"] = state["undo_logs"][-200:]


def log_decisions(client, state, results, items, cands, run_date, stamp):
    """Decision log (dry run too): history in state, the run's entries in _DriveAgent/logs/,
    and placed_to for moves that were done (used to learn from the owner's own corrections)."""
    import history
    entries = history.record(state, run_date, results, items, cands)
    placed = state.setdefault("placed_to", {})
    for e in entries:
        if e["status"] == "done" and e["action"] in ("move", "archive", "dedupe_archive"):
            placed[e["id"]] = e["to"]
    client.write_agent_file(f"decisions_{stamp}.json", json.dumps(entries, indent=1), sub="logs")
    return entries


def main(argv):
    import sys
    from google_client import from_env
    import argparse
    import state as st
    ap = argparse.ArgumentParser()
    ap.add_argument("plan")
    ap.add_argument("--answers")
    a = ap.parse_args(argv)
    cfg = load_config()
    client = from_env()
    rd = run_dir()
    items = []
    if a.answers:
        items += read_json(a.answers, {"actions": []})["actions"]
    items += read_json(a.plan)["actions"]
    results, log = run_items(client, items, cfg)
    write_json(os.path.join(rd, "executed.json"), results)
    now = datetime.now(timezone.utc)
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    state_path = os.path.join(rd, "state.json")
    s = read_json(state_path, {}) or {}
    if log:
        write_json(os.path.join(rd, "undo_log.json"), log)
        save_undo_log(client, s, log, stamp, now.date().isoformat())
        for e in log:
            st.mark_placed(s, e["id"], client.get_meta(e["id"]).get("modifiedTime"))
    cands = {c["id"]: c for c in read_json(os.path.join(rd, "candidates.json"), {"candidates": []})["candidates"]}
    cands.update({c["id"]: c for c in read_json(os.path.join(rd, "answers.json"), {}).get("candidates", [])})
    log_decisions(client, s, results, items, cands, now.strftime("%Y-%m-%d"), stamp)
    write_json(state_path, s)
    counts = {}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    if counts.get("refused"):
        print(REFUSAL, file=sys.stderr)
        return 3
    print(" ".join(f"{k}={v}" for k, v in sorted(counts.items())) or "nothing to do",
          "(dry run)" if cfg.get("dry_run", True) else "")
    return 0


if __name__ == "__main__":
    from common import run as _cli
    _cli(main)
