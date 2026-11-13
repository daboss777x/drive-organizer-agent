"""Build the weekly report markdown from run artifacts.

python tools/report.py      # writes runs/current/report.md (send_email.py sends it)
Only counts are ever reported for protected files.
"""
import os

from common import load_config, read_json, run, run_dir

VERB = {"move": "Move", "rename": "Rename", "archive": "Archive", "dedupe_archive": "Archive duplicate"}


def _line(r, cands):
    c = cands.get(r.get("id"), {})
    name = c.get("name", r.get("id"))
    if r.get("action") == "rename":
        dest = f"→ \"{r.get('new_name')}\""
    elif r.get("action") in ("archive", "dedupe_archive"):
        dest = "→ Archive"
    else:
        dest = f"→ {r.get('target_folder')}"
    return f"- {VERB.get(r.get('action'), r.get('action'))} **{name}** (in /{c.get('path', '')}) {dest}"


def _dest(r):
    a = r.get("action")
    if a == "rename":
        return "Renamed"
    if a in ("archive", "dedupe_archive"):
        return "Archive"
    return r.get("target_folder") or "(unknown)"


def build(dry_run, scan, results, cands, questions, rejected, context_proposals, usage,
          undo_link, flagged=(), sheet_url=None):
    """questions: the few `ask` items (dicts with id + reason). sheet_url is unused (Sheet retired)."""
    title = "Drive agent report" + (" — DRY RUN (nothing was changed)" if dry_run else "")
    shown = "proposed" if dry_run else "done"
    acted = [r for r in results if r.get("status") == shown]
    refused = sum(r.get("status") == "refused" for r in results)
    other = [r for r in results if r.get("status") not in (shown, "refused")]
    questions = list(questions or [])
    out = [f"# {title}", "",
           "## Summary",
           f"- Files checked: {scan.get('candidates', 0)} "
           f"(unchanged since last run: {scan.get('skipped_unchanged', 0)})",
           f"- Protected files skipped: {scan.get('blocked_count', 0)}",
           f"- Actions {shown}: {len(acted)}",
           f"- Refused (protected): {refused}",
           f"- Not applied (cap / error): {len(other)}",
           f"- Plan items rejected by the rule checker: {rejected}",
           f"- Not read (name looks sensitive): {len(flagged)}",
           f"- Files summarized: {usage.get('summarized', 0)}, from cache: {usage.get('cached', 0)}",
           "", "## Here's what I " + ("would do" if dry_run else "did")]
    if not acted:
        out.append("- nothing this time")
    groups = {}
    for r in acted:
        groups.setdefault(_dest(r), []).append(r)
    for dest in sorted(groups):
        out += ["", f"### {dest} ({len(groups[dest])})"]
        for r in groups[dest]:
            c = cands.get(r.get("id"), {})
            name = c.get("name", "a file")
            extra = f" → \"{r.get('new_name')}\"" if r.get("action") == "rename" else ""
            why = f": {r['reason']}" if r.get("reason") else ""
            out.append(f"- **{name}**{extra} (from /{c.get('path', '')}){why}")
    if flagged:
        out += ["", "## Not read (sorted by name only)"]
        out += [f"- **{f['name']}** (in /{f.get('path', '')})" for f in flagged]
    out += ["", "## Questions for you"]
    if questions:
        for i, q in enumerate(questions, 1):
            name = cands.get(q.get("id"), {}).get("name", "a file")
            out.append(f"{i}. **{name}**: {q.get('reason', '')}")
    else:
        out.append("None this week.")
    out += ["", "Answer questions, ask why something moved, or correct me: run **/drive-review** in "
            "Claude Code. Everything here can be undone."]
    if context_proposals.strip():
        out += ["", "## Things I noticed (suggestions for business_context.md)", context_proposals.strip()]
    if undo_link:
        out += ["", f"Undo log: {undo_link}"]
    return "\n".join(out) + "\n"


def usage_counts(candidates, todo, flagged):
    """summarized = needed a summary and wasn't flagged (flagged files are never read)."""
    flagged_ids = {f["id"] for f in flagged}
    return {"summarized": sum(1 for t in todo if t["id"] not in flagged_ids),
            "cached": candidates - len(todo)}


def main(argv):
    rd = run_dir()
    cfg = load_config()
    scan = read_json(os.path.join(rd, "candidates.json"), {"candidates": []})
    cands = {c["id"]: c for c in scan["candidates"]}
    cands.update({c["id"]: c for c in read_json(os.path.join(rd, "answers.json"), {}).get("candidates", [])})
    plan = read_json(os.path.join(rd, "validated_plan.json"), {"questions": [], "rejected": []})
    state = read_json(os.path.join(rd, "state.json"), {}) or {}
    todo = read_json(os.path.join(rd, "to_summarize.json"), [])
    flagged = read_json(os.path.join(rd, "flagged.json"), [])
    proposals_path = os.path.join(rd, "context_proposals.md")
    md = build(
        dry_run=cfg.get("dry_run", True),
        scan={"candidates": len(scan["candidates"]), "blocked_count": scan.get("blocked_count", 0),
              "skipped_unchanged": scan.get("skipped_unchanged", 0)},
        results=read_json(os.path.join(rd, "executed.json"), []), cands=cands,
        questions=plan["questions"],
        rejected=len(plan["rejected"]),
        context_proposals=open(proposals_path).read() if os.path.exists(proposals_path) else "",
        usage=usage_counts(len(scan["candidates"]), todo, flagged),
        flagged=flagged,
        undo_link="_DriveAgent/logs/ in Drive" if os.path.exists(os.path.join(rd, "undo_log.json")) else "",
    )
    with open(os.path.join(rd, "report.md"), "w") as fh:
        fh.write(md)
    print(f"report -> {os.path.join(rd, 'report.md')}")
    return 0


if __name__ == "__main__":
    run(main)
