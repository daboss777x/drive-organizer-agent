"""/drive-review engine: The owner asks about, corrects and teaches the Drive agent, in plain words.

python tools/review.py summary                     # last run: what changed, by folder; open questions
python tools/review.py find "<text>"               # where did a file go, and why
python tools/review.py undo "<file name>"          # put it back where it was
python tools/review.py undo-run [YYYY-MM-DD]       # undo a whole live run (default: the latest)
python tools/review.py move "<file name>" "<Folder/Sub>"   # the owner's correction
python tools/review.py feedback "<rule>"           # a general rule, e.g. "zips go to the client folder"
python tools/review.py answer <n> "<reply>"        # answer open question n

Reads and writes the agent's state in Drive (_DriveAgent/state.json). Every Drive action goes
through GoogleClient, so the forbidden-folder guard applies. Corrections and answers are stored as
feedback the next run's classifier uses as precedent. Locally, the bridge settings are read from
.env by this script itself; they are never printed.
"""
import os
import sys

from common import ROOT, run


class NothingToUndo(Exception):
    """The entry was only proposed (dry run) or isn't a move/rename."""


class Ambiguous(Exception):
    def __init__(self, matches):
        super().__init__("ambiguous")
        self.matches = matches


def _hist(state):
    return list(reversed(state.get("history", [])))  # newest first


def _line(e):
    if e.get("action") == "rename":
        what = f"renamed to \"{e.get('new_name')}\""
    elif e.get("action") in ("archive", "dedupe_archive"):
        what = "archived"
    else:
        what = f"/{e.get('from', '')} → /{e.get('to', '')}"
    state = "" if e.get("status") == "done" else f" [{e.get('status')}]"
    return f"{e.get('run')}: **{e.get('name')}** {what}{state}. Why: {e.get('reason') or '(no reason given)'}"


def find(state, text):
    t = (text or "").lower()
    return [_line(e) for e in _hist(state)
            if t and any(t in str(e.get(k) or "").lower() for k in ("name", "from", "to", "new_name"))]


def resolve(state, text):
    """The newest history entry for the one file `text` names. Exact name first, then substring."""
    t = (text or "").strip().lower()
    latest = {}
    for e in _hist(state):
        if e.get("id") and e["id"] not in latest:
            latest[e["id"]] = e
    exact = [e for e in latest.values() if (e.get("name") or "").lower() == t]
    hits = exact or [e for e in latest.values() if t and t in (e.get("name") or "").lower()]
    if len(hits) != 1:
        raise Ambiguous(hits)
    return hits[0]


def _today():
    from datetime import date
    return date.today().isoformat()


def _record(state, e, to, note):
    state.setdefault("feedback", []).append(
        {"name": e["name"], "agent_to": e.get("to", ""), "owner_to": to, "note": note})
    state["feedback"] = state["feedback"][-500:]
    state.setdefault("history", []).append(
        {"run": _today(), "id": e["id"], "name": e["name"], "from": e.get("to", ""), "to": to,
         "action": "move", "new_name": None, "reason": note, "confidence": None,
         "status": "done", "source": "owner"})
    state.setdefault("placed_to", {})[e["id"]] = to


def move(client, state, text, folder):
    e = resolve(state, text)
    target = client.ensure_folder(folder)   # guard-checked; a forbidden folder raises Blocked
    client.move(e["id"], target)            # guard-checked again for the file itself
    _record(state, e, folder, "moved by the owner")
    return e


def undo(client, state, text):
    e = resolve(state, text)
    if e.get("status") != "done" or e.get("action") not in ("move", "rename", "archive", "dedupe_archive"):
        raise NothingToUndo()
    if e.get("action") == "rename" and e.get("new_name"):
        client.rename(e["id"], e["name"])
    else:
        client.move(e["id"], client.ensure_folder(e.get("from", "")))
    _record(state, e, e.get("from", ""), "undone by the owner")
    return e


def undo_run(client, state, log):
    """Reverse one run's undo log, newest first, through the guard. Files the owner has moved or
    renamed since are skipped (his change wins). A protected file stops the undo; it's only counted."""
    from guard import Blocked
    names = {e.get("id"): e.get("name") for e in state.get("history", [])}
    out = {"undone": [], "skipped": [], "refused": 0, "folders_left": []}
    for e in reversed(log):
        try:
            meta = client.get_meta(e["id"])
            name = names.get(e["id"]) or e.get("old_name")
            expected_name = e.get("new_name") or e["old_name"]
            if meta["parents"][0] != e["new_parent"] or meta["name"] != expected_name:
                out["skipped"].append(name)
                continue
            if e["new_parent"] != e["old_parent"]:
                client.move(e["id"], e["old_parent"])
                out["folders_left"].append(e["new_parent"])
            if meta["name"] != e["old_name"]:
                client.rename(e["id"], e["old_name"])
        except Blocked:
            out["refused"] += 1
            break
        out["undone"].append(name)
        state.setdefault("feedback", []).append(
            {"name": name, "agent_to": "(that run)", "owner_to": "(back where it was)",
             "note": "whole run undone by the owner"})
        state.setdefault("history", []).append(
            {"run": _today(), "id": e["id"], "name": name, "from": "", "to": "", "action": "undo",
             "new_name": None, "reason": "whole run undone by the owner", "confidence": None,
             "status": "done", "source": "owner"})
        state.get("placed_to", {}).pop(e["id"], None)
    out["folders_left"] = sorted(set(out["folders_left"]))
    return out


def pick_log(state, run_date=None):
    """The undo log of the latest live run, or of the run on run_date."""
    logs = [l for l in state.get("undo_logs", []) if run_date in (None, l.get("run"))]
    return logs[-1] if logs else None


def feedback(state, rule, rules_path=None):
    import rules as rules_mod
    rules_mod.append(rules_path or os.path.join(ROOT, "rules.md"), rule)
    state.setdefault("feedback", []).append({"rule": rule.strip()})
    state["feedback"] = state["feedback"][-500:]


def save_questions(state, questions, cands):
    """The run's few `ask` items, kept in state so /drive-review can show and answer them."""
    state["open_questions"] = [{"id": q.get("id"), "name": cands.get(q.get("id"), {}).get("name", "a file"),
                                "question": q.get("reason", "")} for q in questions][:5]


def answer(state, n, reply):
    qs = state.get("open_questions", [])
    q = qs.pop(n - 1)
    state.setdefault("feedback", []).append(
        {"name": q["name"], "id": q.get("id"), "question": q["question"], "answer": reply.strip()})


def summary(state):
    hist = state.get("history", [])
    last = max((e.get("run", "") for e in hist), default="")
    groups = {}
    for e in hist:
        if e.get("run") == last and e.get("source") != "owner":
            dest = "Renamed" if e.get("action") == "rename" else (
                "Archive" if e.get("action") in ("archive", "dedupe_archive") else e.get("to") or "?")
            groups.setdefault(dest, []).append(e)
    out = [f"Last run: {last or 'none yet'}"]
    for dest in sorted(groups):
        out.append(f"\n{dest} ({len(groups[dest])})")
        out += [f"- {_line(e)}" for e in groups[dest]]
    qs = state.get("open_questions", [])
    out.append("\nOpen questions:" if qs else "\nNo open questions.")
    out += [f"{i}. {q['name']}: {q['question']}" for i, q in enumerate(qs, 1)]
    return "\n".join(out)


def _load_env_file():  # pragma: no cover - local convenience
    """Local use: read the two bridge settings from .env if they aren't set. Never printed."""
    if not os.environ.get("SSL_CERT_FILE") and os.path.exists("/etc/ssl/cert.pem"):
        os.environ["SSL_CERT_FILE"] = "/etc/ssl/cert.pem"  # macOS venv Python lacks a CA bundle
    p = os.path.join(ROOT, ".env")
    if os.environ.get("DRIVE_BRIDGE_SECRET") or not os.path.exists(p):
        return
    for line in open(p, encoding="utf-8"):
        k, _, v = line.strip().partition("=")
        k = k.replace("export ", "").strip()
        if k in ("DRIVE_BRIDGE_URL", "DRIVE_BRIDGE_SECRET") and v:
            os.environ.setdefault(k, v.strip().strip("'\""))


def main(argv):  # pragma: no cover - thin CLI over the tested functions above
    from common import read_json, run_dir, write_json
    if not argv:
        print(__doc__)
        return 2
    cmd, args = argv[0], argv[1:]
    rd = run_dir()
    if cmd in ("save-questions", "export-feedback"):  # used inside the weekly run (local state file)
        path = os.path.join(rd, "state.json")
        s = read_json(path, {}) or {}
        if cmd == "save-questions":
            plan = read_json(os.path.join(rd, "validated_plan.json"), {"questions": []})
            cands = {c["id"]: c for c in read_json(os.path.join(rd, "candidates.json"), {"candidates": []})["candidates"]}
            save_questions(s, plan["questions"], cands)
            write_json(path, s)
            print(f"open_questions={len(s['open_questions'])}")
        else:
            fb = [{k: v for k, v in f.items() if k != "id"} for f in s.get("feedback", [])[-100:]]
            write_json(os.path.join(rd, "feedback.json"), fb)
            print(f"feedback={len(fb)}")
        return 0
    _load_env_file()
    import state as st
    from google_client import from_env
    client = from_env()
    s = st.pull(client)
    changed = True
    try:
        if cmd == "summary":
            print(summary(s)); changed = False
        elif cmd == "find" and len(args) == 1:
            print("\n".join(find(s, args[0])) or "No file like that in the decision log."); changed = False
        elif cmd == "undo-run" and len(args) <= 1:
            import json
            entry = pick_log(s, args[0] if args else None)
            if not entry:
                print("No live run to undo" + (f" on {args[0]}." if args else " yet (dry runs change nothing)."))
                return 2
            raw = client.read_agent_file(entry["file"], sub="logs")
            res = undo_run(client, s, json.loads(raw) if raw else [])
            st.push(client, s)
            print(f"Run {entry['run']}: undone {len(res['undone'])} of {entry['count']}.")
            if res["skipped"]:
                print("Left alone (you changed them since): " + ", ".join(res["skipped"]))
            if res["folders_left"]:
                print(f"{len(res['folders_left'])} folder(s) it created may now be empty; nothing was deleted.")
            if res["refused"]:
                print("Stopped at a protected file (not named). Files after it in the log were not undone.")
                return 3
            return 0
        elif cmd == "undo" and len(args) == 1:
            e = undo(client, s, args[0]); print(f"undone: {e['name']} is back in /{e.get('from', '')}")
        elif cmd == "move" and len(args) == 2:
            e = move(client, s, args[0], args[1]); print(f"moved: {e['name']} -> /{args[1]}")
        elif cmd == "feedback" and len(args) == 1:
            feedback(s, args[0]); print("rule saved")
        elif cmd == "answer" and len(args) == 2:
            answer(s, int(args[0]), args[1]); print("answer saved; the next run will act on it")
        else:
            print(__doc__); return 2
    except Ambiguous as e:
        print("Which one? " + "; ".join(f"{m['name']} (/{m.get('to', '')})" for m in e.matches[:10])
              if e.matches else "No file like that in the decision log.")
        return 2
    except NothingToUndo:
        print("Nothing to undo: that change was only proposed (dry run).")
        return 2
    if changed:
        st.push(client, s)
    return 0


if __name__ == "__main__":
    run(main)
