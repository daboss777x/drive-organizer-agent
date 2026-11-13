import pytest
from inbox_sheet import parse_answers, new_rows, HEADER
from rules import append as add_rule


def row(id, answer="", other="", status="open", action="move", folder="Content"):
    r = dict.fromkeys(HEADER, "")
    r.update({"file_id": id, "answer": answer, "other_folder": other, "status": status,
              "proposed_action": action, "proposed_folder": folder})
    return [r[h] for h in HEADER]


def test_answers_become_plan_items_from_owner():
    rows = [HEADER, row("a", "Approve"), row("b", "Other folder", other="Learning/University"),
            row("c", "Keep where is"), row("d", "Archive")]
    got = {x["id"]: x for x in parse_answers(rows)}
    assert got["a"]["action"] == "move" and got["a"]["target_folder"] == "Content"
    assert got["b"]["action"] == "move" and got["b"]["target_folder"] == "Learning/University"
    assert got["c"]["action"] == "keep"
    assert got["d"]["action"] == "archive"
    assert all(x["source"] == "owner" and x["confidence"] == 1.0 for x in got.values())


def test_unanswered_done_and_incomplete_rows_are_ignored():
    rows = [HEADER, row("a"), row("b", "Approve", status="done"), row("c", "Other folder", other="")]
    assert parse_answers(rows) == []


def test_answer_rows_remember_their_sheet_row_number():
    rows = [HEADER, row("a"), row("b", "Approve")]
    assert parse_answers(rows)[0]["sheet_row"] == 3


def test_new_rows_skip_files_already_waiting_for_an_answer():
    existing = [HEADER, row("a")]
    qs = [{"id": "a", "action": "move", "target_folder": "Content", "reason": "r"},
          {"id": "z", "action": "archive", "reason": "looks stale"}]
    meta = {"z": {"name": "z.txt", "webViewLink": "https://drive/z"}, "a": {"name": "a", "webViewLink": ""}}
    out = new_rows(existing, qs, meta, summaries={"z": {"summary": "an old note"}}, today="2026-11-13")
    assert len(out) == 1 and out[0][HEADER.index("file_id")] == "z"
    assert out[0][HEADER.index("summary")] == "an old note"


def test_rules_append_once_and_reject_junk(tmp_path):
    p = tmp_path / "rules.md"
    p.write_text("# Rules\n")
    assert add_rule(str(p), "Files mentioning Northbeam -> Clients/Northbeam") is True
    assert add_rule(str(p), "files mentioning northbeam -> clients/northbeam") is False
    assert add_rule(str(p), "") is False
    assert add_rule(str(p), "line one\nline two") is False
    assert p.read_text().count("\n- ") == 1


# ---- review rows from the name screen ----
from inbox_sheet import apply_screen_answers


def test_review_answers_map_to_screen_decisions():
    rows = [HEADER, row("a", "Approve", action="review", folder=""),
            row("b", "Keep where is", action="review", folder=""),
            row("c", "Other folder", other="Personal", action="review", folder=""),
            row("d", "Archive", action="review", folder="")]
    got = {x["id"]: x["action"] for x in parse_answers(rows)}
    assert got == {"a": "clear_read", "b": "never_read", "c": "move", "d": "archive"}


def test_screen_answers_update_state_and_are_removed_from_the_plan():
    state = {}
    answers = [{"id": "a", "action": "clear_read", "sheet_row": 2},
               {"id": "b", "action": "never_read", "sheet_row": 3},
               {"id": "c", "action": "move", "target_folder": "Personal", "sheet_row": 4}]
    names = {"a": "Payslip March.pdf", "b": "diary.docx", "c": "x"}
    remaining, closed = apply_screen_answers(state, answers, names)
    assert state["screen_cleared"] == {"a": "Payslip March.pdf"}
    assert "b" in state["screen_never"]
    assert [x["id"] for x in remaining] == ["c"] and closed == [2, 3]
