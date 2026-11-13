from report import build

CANDS = {"a": {"name": "notes.txt", "path": "Downloads"}, "b": {"name": "meme.png", "path": ""}}
BASE = dict(scan={"candidates": 2, "blocked_count": 7, "skipped_unchanged": 1},
            questions=[{"id": "b", "action": "ask", "reason": "Archive?"}], rejected=1,
            context_proposals="- Add client Northbeam", usage={"summarized": 2, "cached": 0},
            undo_link="")


def test_dry_run_report_lists_proposed_actions_with_names():
    results = [{"id": "a", "action": "move", "target_folder": "Learning", "status": "proposed"}]
    md = build(dry_run=True, results=results, cands=CANDS, **BASE)
    assert "DRY RUN" in md
    assert "notes.txt" in md and "Learning" in md
    assert "Protected files skipped: 7" in md
    assert "meme.png" in md and "Archive?" in md  # questions are in the email now (Sheet retired)
    assert "Add client Northbeam" in md


def test_live_report_counts_done_and_shows_refusals_only_as_a_count():
    results = [{"id": "b", "action": "archive", "status": "done"},
               {"status": "refused"}, {"id": "a", "status": "not_run"}]
    md = build(dry_run=False, results=results, cands=CANDS, **BASE)
    assert "DRY RUN" not in md
    assert "meme.png" in md and "Archive" in md
    assert "Refused (protected): 1" in md


def test_report_lists_files_flagged_by_the_name_screen():
    flagged = [{"name": "Payslip March.pdf", "path": "Downloads", "by": "words"},
               {"name": "Mum's things", "path": "", "by": "ai"}]
    md = build(dry_run=True, results=[], cands=CANDS, flagged=flagged, **BASE)
    assert "Not read" in md and "Payslip March.pdf" in md and "Mum's things" in md
    assert "Not read (name looks sensitive): 2" in md


def test_usage_counts_exclude_flagged_files_from_summarized():
    from report import usage_counts
    todo = [{"id": i} for i in ("a", "b", "c", "d")]
    flagged = [{"id": "c"}, {"id": "d"}]
    assert usage_counts(candidates=6, todo=todo, flagged=flagged) == {"summarized": 2, "cached": 2}


def test_report_groups_what_it_did_by_folder_with_reasons_and_points_to_drive_review():
    cands = {"a": {"name": "brief.docx", "path": ""}, "b": {"name": "logo.zip", "path": "Downloads"},
             "c": {"name": "Untitled document", "path": ""}, "q": {"name": "old deck.pptx", "path": ""}}
    results = [
        {"id": "a", "action": "move", "target_folder": "Clients/Acme", "status": "done", "reason": "Acme brief"},
        {"id": "b", "action": "move", "target_folder": "Clients/Acme", "status": "done", "reason": "Acme assets"},
        {"id": "c", "action": "rename", "new_name": "Kickoff notes", "status": "done", "reason": "broken name"},
    ]
    questions = [{"id": "q", "action": "ask", "reason": "Archive this 2019 deck?"}]
    md = build(dry_run=False, results=results, cands=cands, **{**BASE, "questions": questions})
    assert "Here's what I did" in md
    assert "### Clients/Acme (2)" in md
    assert "brief.docx" in md and "Acme brief" in md
    assert "Kickoff notes" in md
    assert "old deck.pptx" in md and "Archive this 2019 deck?" in md
    assert "/drive-review" in md
    assert "spreadsheets" not in md
