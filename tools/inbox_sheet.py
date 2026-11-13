"""The 'Drive Agent Inbox' Google Sheet: questions out, the owner's dropdown answers in.
Rows with proposed_action "review" are files the name screen refused to read.

python tools/inbox_sheet.py read    # answers -> runs/current/answers.json
python tools/inbox_sheet.py write   # validated_plan questions -> new Sheet rows
python tools/inbox_sheet.py close   # mark rows answered + executed as done
"""
import os

from common import read_json, run, run_dir, write_json

SHEET_NAME = "Drive Agent Inbox"
TAB = "Inbox"
HEADER = ["file_id", "file", "link", "summary", "proposed_action", "proposed_folder",
          "reason", "answer", "other_folder", "status", "asked_on"]
CHOICES = ["Approve", "Other folder", "Keep where is", "Archive"]


def _col(name):
    return HEADER.index(name)


def parse_answers(rows):
    out = []
    for n, r in enumerate(rows[1:], start=2):
        r = list(r) + [""] * (len(HEADER) - len(r))
        rec = dict(zip(HEADER, r))
        ans, status = rec["answer"].strip(), rec["status"].strip().lower()
        if not ans or status == "done" or not rec["file_id"]:
            continue
        item = {"id": rec["file_id"], "confidence": 1.0, "source": "owner",
                "sheet_row": n, "reason": f"the owner answered: {ans}"}
        review = rec["proposed_action"] == "review"
        if ans == "Approve" and review:
            item["action"] = "clear_read"
        elif ans == "Keep where is" and review:
            item["action"] = "never_read"
        elif ans == "Approve":
            item["action"] = rec["proposed_action"] or "keep"
            if rec["proposed_folder"]:
                item["target_folder"] = rec["proposed_folder"]
        elif ans == "Other folder":
            if not rec["other_folder"].strip():
                continue
            item.update(action="move", target_folder=rec["other_folder"].strip())
        elif ans == "Keep where is":
            item["action"] = "keep"
        elif ans == "Archive":
            item["action"] = "archive"
        else:
            continue
        out.append(item)
    return out


def apply_screen_answers(state, answers, names):
    """Record name-screen decisions in state. Returns (other answers, sheet rows to close)."""
    remaining, closed = [], []
    for a in answers:
        if a["action"] == "clear_read":
            state.setdefault("screen_cleared", {})[a["id"]] = names[a["id"]]
        elif a["action"] == "never_read":
            state.setdefault("screen_never", {})[a["id"]] = True
        else:
            remaining.append(a)
            continue
        closed.append(a["sheet_row"])
    return remaining, closed


def new_rows(existing, questions, meta, summaries, today):
    open_ids = {r[0] for r in existing[1:]
                if r and (len(r) <= _col("status") or r[_col("status")].lower() != "done")}
    rows = []
    for q in questions:
        if q["id"] in open_ids or q["id"] not in meta:
            continue
        m = meta[q["id"]]
        rows.append([q["id"], m.get("name", ""), m.get("webViewLink", ""),
                     (summaries.get(q["id"]) or {}).get("summary", ""),
                     q.get("action", ""), q.get("target_folder", ""), q.get("reason", ""),
                     "", "", "open", today])
        open_ids.add(q["id"])
    return rows


def _open(client, state, sheets):  # pragma: no cover
    sid = state.get("inbox_sheet_id")
    if sid:
        client.get_meta(sid)  # guard re-check
        return sid
    sid = client.find_or_create_agent_sheet(SHEET_NAME)  # reuse: never a second inbox
    sheets.setup(sid)  # idempotent: header + answer dropdowns
    state["inbox_sheet_id"] = sid
    return sid


def main(argv):  # pragma: no cover - exercised in the live dry run
    from datetime import date

    from bridge import BridgeSheets
    from google_client import from_env
    from guard import Blocked
    cmd = argv[0] if argv else ""
    rd = run_dir()
    state_path = os.path.join(rd, "state.json")
    state = read_json(state_path, {}) or {}
    client = from_env()
    sheets = BridgeSheets(client.api)
    sid = _open(client, state, sheets)
    write_json(state_path, state)
    rows = sheets.get_rows(sid)
    if cmd == "read":
        items, metas, blocked = [], [], 0
        for it in parse_answers(rows):
            try:
                m = client.get_meta(it["id"])
            except Blocked:
                blocked += 1
                continue
            items.append(it)
            metas.append({"id": m["id"], "name": m["name"], "path": "", "modifiedTime": m.get("modifiedTime"),
                          "md5Checksum": m.get("md5Checksum"), "mimeType": m.get("mimeType")})
        items, closed = apply_screen_answers(state, items, {m["id"]: m["name"] for m in metas})
        write_json(state_path, state)
        for n in closed:
            sheets.set_status(sid, n, "done")
        write_json(os.path.join(rd, "answers.json"), {"items": items, "candidates": metas})
        print(f"answers={len(items)} screen_decisions={len(closed)} refused={blocked} "
              f"open_rows={max(len(rows) - 1, 0)}")
    elif cmd == "write":
        plan = read_json(os.path.join(rd, "validated_plan.json"), {"questions": []})
        cands = {c["id"]: c for c in read_json(os.path.join(rd, "candidates.json"), {"candidates": []})["candidates"]}
        summaries = {k: v["summary"] for k, v in state.get("summaries", {}).items()}
        flagged = read_json(os.path.join(rd, "flagged.json"), [])
        reviews = [{"id": f["id"], "action": "review",
                    "reason": f"NOT READ: name looks sensitive ({f['reason']}). Approve = OK to read; "
                              "Keep where is = never read; Other folder/Archive = move unread"}
                   for f in flagged]
        out = new_rows(rows or [HEADER], reviews + plan["questions"], cands, summaries,
                       date.today().isoformat())
        if out:
            sheets.append(sid, out)
        print(f"new_questions={len(out)} sheet=https://docs.google.com/spreadsheets/d/{sid}")
    elif cmd == "close":
        done = read_json(os.path.join(rd, "executed.json"), [])
        rows_done = sorted({d["sheet_row"] for d in done if d.get("sheet_row") and d.get("ok")})
        for n in rows_done:
            sheets.set_status(sid, n, "done")
        print(f"closed={len(rows_done)}")
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    run(main)
