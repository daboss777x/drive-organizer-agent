"""/drive-review engine: The owner asks, corrects and teaches; everything goes through the guard."""
import pytest
from fakes import FakeDrive
from guard import Guard, Blocked
from google_client import GoogleClient
import review

F = "FORBIDDEN_FOLDER"


def entry(id, name, frm, to, action="move", status="done", run="2026-11-20", reason="r", new_name=None):
    return {"run": run, "id": id, "name": name, "from": frm, "to": to, "action": action,
            "new_name": new_name, "reason": reason, "confidence": 0.9, "status": status}


@pytest.fixture
def setup():
    d = FakeDrive()
    d.folder(F, "Vault")
    d.folder("acme", "Acme", parent="root")
    d.add("z", "logo.zip", parent="acme")
    c = GoogleClient(d, Guard({F}))
    state = {"history": [entry("z", "logo.zip", "Downloads", "Acme", reason="Acme brand assets"),
                         entry("n", "notes.txt", "", "Learning", run="2026-11-13")]}
    return d, c, state


def test_find_says_where_a_file_went_and_why(setup):
    _, _, state = setup
    out = review.find(state, "logo")
    assert len(out) == 1
    assert "logo.zip" in out[0] and "Acme" in out[0] and "Acme brand assets" in out[0]
    assert review.find(state, "nothing-like-this") == []


def test_owner_move_goes_through_the_guard_and_becomes_feedback(setup):
    d, c, state = setup
    review.move(c, state, "logo.zip", "Clients/Acme/Assets")
    folder = [f for f in d.files.values() if f["name"] == "Assets"][0]
    assert d.files["z"]["parents"] == [folder["id"]]
    fb = state["feedback"][-1]
    assert fb["name"] == "logo.zip" and fb["agent_to"] == "Acme" and fb["owner_to"] == "Clients/Acme/Assets"
    assert state["history"][-1]["action"] == "move" and state["history"][-1]["source"] == "owner"


def test_move_into_the_forbidden_folder_is_refused(setup):
    d, c, state = setup
    with pytest.raises(Blocked):
        review.move(c, state, "logo.zip", "Vault")
    assert d.files["z"]["parents"] == ["acme"]


def test_undo_puts_the_file_back_and_records_why(setup):
    d, c, state = setup
    review.undo(c, state, "logo.zip")
    dl = [f for f in d.files.values() if f["name"] == "Downloads"][0]
    assert d.files["z"]["parents"] == [dl["id"]]
    assert state["feedback"][-1]["owner_to"] == "Downloads"
    assert state["feedback"][-1]["note"] == "undone by the owner"


def test_ambiguous_names_list_the_choices_instead_of_guessing(setup):
    _, c, state = setup
    state["history"].append(entry("z2", "logo (2).zip", "", "Content"))
    with pytest.raises(review.Ambiguous) as e:
        review.move(c, state, "logo", "Content")
    assert len(e.value.matches) == 2


def test_undo_of_a_dry_run_entry_is_refused_because_nothing_moved(setup):
    _, c, state = setup
    state["history"].append(entry("p", "plan.pdf", "", "Content", status="proposed"))
    with pytest.raises(review.NothingToUndo):
        review.undo(c, state, "plan.pdf")


def test_feedback_rule_goes_to_rules_md_and_feedback(setup, tmp_path):
    _, _, state = setup
    rules = tmp_path / "rules.md"
    review.feedback(state, "Zip files go to the client folder they belong to", str(rules))
    assert "Zip files go to the client folder" in rules.read_text()
    assert state["feedback"][-1]["rule"].startswith("Zip files")


def test_answers_close_the_question_and_become_feedback(setup):
    _, _, state = setup
    review.save_questions(state, [{"id": "q", "reason": "Archive this 2019 deck?"}], {"q": {"name": "old deck.pptx"}})
    assert "old deck.pptx" in review.summary(state)
    review.answer(state, 1, "yes, archive it")
    assert state["open_questions"] == []
    fb = state["feedback"][-1]
    assert fb["name"] == "old deck.pptx" and fb["question"].startswith("Archive") and fb["answer"] == "yes, archive it"


def test_summary_groups_the_latest_run_by_folder(setup):
    _, _, state = setup
    s = review.summary(state)
    assert "2026-11-20" in s and "Acme (1)" in s and "logo.zip" in s
    assert "notes.txt" not in s   # older run


# ---- undo a whole run ----
from execute import run_items

CFG = {"dry_run": False, "max_actions_per_run": 100}


@pytest.fixture
def live_run():
    d = FakeDrive()
    d.folder(F, "Vault")
    d.folder("dl", "Downloads")
    for i in ("a", "b", "c"):
        d.add(i, f"{i}.pdf", parent="dl")
    d.add("u", "Untitled document", parent="dl")
    c = GoogleClient(d, Guard({F}))
    items = [{"id": "a", "action": "move", "target_folder": "Clients/Acme"},
             {"id": "b", "action": "archive"},
             {"id": "c", "action": "move", "target_folder": "Content"},
             {"id": "u", "action": "rename", "new_name": "Kickoff notes"}]
    _, log = run_items(c, items, CFG)
    state = {"history": [entry(i, f"{i}.pdf", "Downloads", "x") for i in ("a", "b", "c")]
             + [entry("u", "Untitled document", "Downloads", "Downloads", action="rename")]}
    return d, c, state, log


def test_undo_run_puts_every_file_back_and_teaches_the_next_run(live_run):
    d, c, state, log = live_run
    out = review.undo_run(c, state, log)
    assert all(d.files[i]["parents"] == ["dl"] for i in ("a", "b", "c", "u"))
    assert d.files["u"]["name"] == "Untitled document"
    assert sorted(out["undone"]) == ["Untitled document", "a.pdf", "b.pdf", "c.pdf"]
    assert out["skipped"] == [] and out["refused"] == 0
    assert sum(f.get("note") == "whole run undone by the owner" for f in state["feedback"]) == 4


def test_undo_run_skips_files_owner_moved_since(live_run):
    d, c, state, log = live_run
    c.move("c", c.ensure_folder("Learning"))      # the owner moved it himself after the run
    out = review.undo_run(c, state, log)
    assert out["skipped"] == ["c.pdf"]
    assert d.files["c"]["parents"] != ["dl"]      # his move is respected
    assert d.files["a"]["parents"] == ["dl"]


def test_undo_run_stops_at_a_protected_file_and_names_nothing(live_run):
    d, c, state, log = live_run
    d.files["a"]["parents"] = [F]                 # ended up in the forbidden folder somehow
    out = review.undo_run(c, state, log)
    assert out["refused"] == 1
    assert "a.pdf" not in out["undone"] + out["skipped"]


def test_pick_log_defaults_to_the_latest_run_or_a_given_date():
    state = {"undo_logs": [{"run": "2026-11-20", "file": "undo_A.json", "count": 3},
                           {"run": "2026-11-27", "file": "undo_B.json", "count": 5}]}
    assert review.pick_log(state)["file"] == "undo_B.json"
    assert review.pick_log(state, "2026-11-20")["file"] == "undo_A.json"
    assert review.pick_log(state, "2026-12-01") is None
    assert review.pick_log({}) is None
