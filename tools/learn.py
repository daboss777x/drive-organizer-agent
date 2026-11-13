"""Learn from the owner: files the agent placed that he later moved somewhere else are corrections.

state["placed_to"][id] = where the agent put the file. The classifier gets recent corrections as
examples, so next time it files similar things where the owner wants them.
"""
MAX_CORRECTIONS = 500


def corrections(state, metas):
    """metas: {id: {"name", "path"}} as Drive sees it now. Returns new corrections."""
    out = []
    for fid, agent_to in state.get("placed_to", {}).items():
        m = metas.get(fid)
        if m is None or m.get("path") == agent_to:
            continue
        out.append({"id": fid, "name": m.get("name", ""), "agent_to": agent_to, "owner_to": m.get("path", "")})
    return out


def record_corrections(state, new):
    known = state.setdefault("corrections", [])
    seen = {(c.get("id"), c.get("owner_to")) for c in known}
    for c in new:
        if (c["id"], c["owner_to"]) not in seen:
            known.append(c)
            seen.add((c["id"], c["owner_to"]))
        state.setdefault("placed_to", {})[c["id"]] = c["owner_to"]
    del known[:-MAX_CORRECTIONS]
    return state


def collect(client, state):
    """Look up where every agent-placed file is now (guarded), record corrections.
    Returns (new_corrections, skipped_count). Protected or vanished files are only counted."""
    cache = {}

    def lookup(i):
        if i not in cache:
            cache[i] = client.api.get_meta(i)
        return cache[i]

    metas, skipped = {}, 0
    for fid in list(state.get("placed_to", {})):
        try:
            m = client.get_meta(fid)  # guard re-check: Blocked if it's now protected
            metas[fid] = {"name": m.get("name", ""), "path": client._path(m, lookup)}
        except Exception:
            skipped += 1
            state["placed_to"].pop(fid, None)  # forget it: never name a protected or gone file
    new = corrections(state, metas)
    record_corrections(state, new)
    return new, skipped
