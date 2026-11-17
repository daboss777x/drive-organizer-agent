"""Enforce the action rules in code, so they never depend on the LLM following them.

python tools/validate_plan.py   # reads runs/current/{plan,candidates,state,duplicates}.json
                                # writes runs/current/validated_plan.json
"""
import math
import os
import re

from common import load_config, read_json, run, run_dir, write_json

ACTIONS = {"move", "rename", "archive", "dedupe_archive", "keep", "ask"}
BUSINESS_TYPES = {"contract", "invoice", "proposal", "quote", "receipt", "statement",
                  "report", "deliverable", "client_work", "finance", "agreement", "sow"}
BUSINESS_PATH_ROOTS = ("Clients", "Finance")
BROKEN_NAME = [
    re.compile(r"^untitled", re.I),
    re.compile(r"^copy of ", re.I),
    re.compile(r"\s\(\d+\)(\.\w+)?$"),
    re.compile(r"^[\d\s_\-.]+(\.\w+)?$"),  # numeric junk like 20240311_0932.pdf
]
# Names that say nothing about the file: camera, phone, screenshot and AI-generator defaults.
UNCLEAR_NAME = [
    re.compile(r"^(IMG|VID|PXL|DSC|DSCN|DCIM|MVIMG|PANO|MOV|GOPR)[-_ ]?\d", re.I),
    re.compile(r"^[A-Z0-9]{4}\d{4}(\.\w+)?$"),  # camera serials like 5K2A5533.JPG
    re.compile(r"^WhatsApp (Image|Video|Audio)", re.I),
    re.compile(r"^Screen ?(shot|recording)", re.I),
    re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I),  # UUIDs
]
FORBIDDEN_TARGETS = {"Archive", "_DriveAgent"}


def is_broken_name(name):
    return any(r.search(name or "") for r in BROKEN_NAME)


def is_renameable(name):
    """Broken (Untitled, Copy of, (1), numeric junk) or unclear (camera/phone/AI defaults).
    Meaningful names are left alone (the owner, 2026-11-17)."""
    return is_broken_name(name) or any(r.search(name or "") for r in UNCLEAR_NAME)


def _new_name_problem(old, new):
    new = (new or "").strip()
    if not is_renameable(old):
        return "only broken or unclear names may be renamed"
    if not new or "/" in new or is_renameable(new):
        return "new_name invalid"
    return None


def _is_business(cand, summary):
    if (summary or {}).get("doc_type", "").lower() in BUSINESS_TYPES:
        return True
    return (cand.get("path") or "").split("/")[0] in BUSINESS_PATH_ROOTS


def _confidence(it):
    try:
        c = float(it.get("confidence"))
    except (TypeError, ValueError):
        return 0.0
    return 0.0 if math.isnan(c) else c


def _target_ok(target, categories):
    from guard import NAME_PATTERNS
    parts = (target or "").split("/")
    if not target or any(p in ("", ".", "..") for p in parts):
        return False
    if any(re.search(pat, p, re.I) for pat in NAME_PATTERNS for p in parts):
        return False  # the guard would refuse this folder at execution time
    # Categories are suggestions: the agent may create new top-level folders (the owner, 2026-11-13).
    return parts[0] not in FORBIDDEN_TARGETS and all(p == p.strip() and p for p in parts)


def _check(it, cand, summary, config, dup_pairs):
    a = it["action"]
    if a == "move":
        if not _target_ok(it.get("target_folder"), config["categories"]):
            return "target_folder not allowed (forbidden, unsafe or sensitive-looking name)"
        if it["target_folder"] == cand.get("path"):
            return "already there"
        if it.get("new_name"):  # move + rename in one step: both must be allowed
            return _new_name_problem(cand["name"], it["new_name"])
    elif a == "rename":
        return _new_name_problem(cand["name"], it.get("new_name"))
    elif a == "archive":
        if it.get("source") != "owner" and _is_business(cand, summary):
            return "business doc: default keep, never archived"
    elif a == "dedupe_archive":
        if (it.get("keep_id"), it["id"]) not in dup_pairs:
            return "not an exact duplicate group"
    return None


UNREAD_OK = {"move", "rename"}  # decided from the name and folder alone, never from content


def validate(plan, candidates, summaries, config, dup_groups=(), unread=frozenset(),
             untouchable=frozenset()):
    """unread: ids the name screen flagged (not read): the agent may only move/rename them.
    untouchable: real-secret word-list hits and the owner's "keep where it is": no action at all."""
    known = {c["id"]: c for c in candidates}
    dup_pairs = {(g[0], other) for g in dup_groups for other in g[1:]}
    out = {"actions": [], "questions": [], "rejected": [], "deferred": []}
    kept = []
    max_q = int(config.get("max_questions_per_run", 5))

    def reject(it, why):
        out["rejected"].append({**it, "rejected_because": why})

    for it in plan:
        action = it.get("action")
        if it.get("id") not in known:
            reject(it, "unknown file id")
            continue
        if action not in ACTIONS:
            reject(it, f"action not allowed: {action}")
            continue
        if action == "keep":
            kept.append(it["id"])
            continue
        if action == "move" and it.get("new_name") and it.get("target_folder") == known[it["id"]].get("path"):
            it = {**it, "action": "rename"}  # already in the right folder: only the name changes
            action = "rename"
        path = known[it["id"]].get("path") or ""
        if path == "_DriveAgent" or path.startswith("_DriveAgent/"):
            reject(it, "the agent's own folder is never organised")
            continue
        if it["id"] in untouchable:
            reject(it, "untouchable: real-secret name or the owner said keep where it is")
            continue
        if it["id"] in unread and it.get("source") != "owner" and action not in UNREAD_OK:
            reject(it, "not read: only move/rename allowed")
            continue
        risky_archive = action == "archive" and it.get("source") != "owner" and (
            _confidence(it) < config["ask_threshold"]
            or _is_business(known[it["id"]], summaries.get(it["id"])))
        if action == "ask" or risky_archive:  # only archives need confidence; moves/renames are undoable
            (out["questions"] if len(out["questions"]) < max_q else out["deferred"]).append(it)
            continue
        if action == "keep":
            continue
        why = _check(it, known[it["id"]], summaries.get(it["id"]), config, dup_pairs)
        if why:
            reject(it, why)
        else:
            out["actions"].append(it)
    planned = {it.get("id") for it in plan}
    # every file needs a decision; decided ones are skipped by later scans unless they change
    out["missing"] = [c["id"] for c in candidates if c["id"] not in planned and c["id"] not in untouchable]
    out["seen"] = sorted(set(kept) | {a["id"] for a in out["actions"]} | (set(known) & set(untouchable)))
    return out


def split_flagged(flagged, state):
    """(unread, untouchable). Real-secret names and the owner's "keep where it is" are untouchable;
    every other name-flagged file may be moved/renamed unread."""
    from screen import strict_flag
    untouchable = set(state.get("screen_never", {}))
    untouchable |= {f["id"] for f in flagged if strict_flag(f.get("name"), f.get("path"))}
    unread = {f["id"] for f in flagged} - untouchable
    return unread, untouchable


def main(argv):
    """--answers: validate the owner's inbox answers (answers.json -> validated_answers.json)."""
    rd = run_dir()
    state = read_json(os.path.join(rd, "state.json"), {}) or {}
    summaries = {k: v["summary"] for k, v in state.get("summaries", {}).items()}
    groups = read_json(os.path.join(rd, "duplicates.json"), [])
    if argv[:1] == ["--answers"]:
        src = read_json(os.path.join(rd, "answers.json"), {"items": [], "candidates": []})
        plan, cands, dest = src["items"], src["candidates"], "validated_answers.json"
    else:
        cands = read_json(os.path.join(rd, "candidates.json"))["candidates"]
        plan = read_json(os.path.join(rd, "plan.json"))
        plan = plan["items"] if isinstance(plan, dict) else plan
        dest = "validated_plan.json"
    unread, untouchable = split_flagged(read_json(os.path.join(rd, "flagged.json"), []), state)
    out = validate(plan, cands, summaries, load_config(), groups, unread, untouchable)
    write_json(os.path.join(rd, dest), out)
    print(f"actions={len(out['actions'])} questions={len(out['questions'])} "
          f"rejected={len(out['rejected'])} deferred={len(out['deferred'])} missing={len(out['missing'])}")
    return 0


if __name__ == "__main__":
    run(main)
