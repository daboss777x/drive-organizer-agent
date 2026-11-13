"""Decision log: what the agent did (or proposed), to which file, from where to where, and why.

Lives in state["history"] (pulled/pushed with state.json) and in _DriveAgent/logs/decisions_*.json.
Refused files never appear here: they're only ever a count.
"""
MAX_ENTRIES = 5000
ARCHIVE = "Archive"


def _to(result, item, cand):
    action = result.get("action") or item.get("action")
    if action in ("archive", "dedupe_archive"):
        return ARCHIVE
    if action == "move":
        return result.get("target_folder") or item.get("target_folder") or ""
    return cand.get("path", "")  # rename/keep: stays where it is


def record(state, run_date, results, items, cands):
    """Append one entry per result that has an id and wasn't refused. Returns the new entries."""
    by_id = {it.get("id"): it for it in items if it.get("id")}
    new = []
    for r in results:
        fid = r.get("id")
        if not fid or r.get("status") == "refused":
            continue
        it, cand = by_id.get(fid, {}), cands.get(fid, {})
        conf = it.get("confidence")
        new.append({
            "run": run_date, "id": fid, "name": cand.get("name", ""), "from": cand.get("path", ""),
            "to": _to(r, it, cand), "action": r.get("action") or it.get("action"),
            "new_name": r.get("new_name") or it.get("new_name"), "reason": it.get("reason", ""),
            "confidence": float(conf) if isinstance(conf, (int, float)) else None,
            "status": r.get("status"),
        })
    hist = state.setdefault("history", [])
    hist.extend(new)
    del hist[:-MAX_ENTRIES]
    return new


def find(state, text):
    """Entries whose name or from/to folder contains text (case-insensitive), newest first."""
    t = (text or "").lower()
    hits = [e for e in state.get("history", [])
            if t in " ".join(str(e.get(k) or "") for k in ("name", "from", "to", "new_name")).lower()]
    return list(reversed(hits))
