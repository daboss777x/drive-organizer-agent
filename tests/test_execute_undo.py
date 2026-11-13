import json
import pytest
from fakes import FakeDrive
from guard import Guard
from google_client import GoogleClient
from execute import run as execute
from undo import run as undo

CFG = {"max_actions_per_run": 100, "dry_run": False}


@pytest.fixture
def drive():
    d = FakeDrive()
    d.folder("VAULT", "Vault")
    d.add("secret", "s.txt", parent="VAULT")
    d.folder("inbox", "Downloads")
    d.add("a", "notes.txt", parent="inbox")
    d.add("b", "Untitled document", parent="inbox")
    d.add("c", "meme.png", parent="inbox")
    return d


@pytest.fixture
def client(drive):
    return GoogleClient(drive, Guard({"VAULT"}))


ITEMS = [
    {"id": "a", "action": "move", "target_folder": "Learning/University"},
    {"id": "b", "action": "rename", "new_name": "Kickoff notes"},
    {"id": "c", "action": "archive"},
]


def mutations(drive):
    return [c for c in drive.calls if c[0] in ("update", "create_folder", "upload")]


def path_of(drive, id):
    names, cur = [], drive.files[id]
    while cur.get("parents"):
        cur = drive.files[cur["parents"][0]]
        if cur.get("parents"):
            names.append(cur["name"])
    return "/".join(reversed(names))


def test_dry_run_changes_nothing(client, drive):
    results, log = execute(client, ITEMS, {**CFG, "dry_run": True})
    assert mutations(drive) == [] and log == []
    assert all(r["status"] == "proposed" for r in results)


def test_actions_are_applied_and_logged(client, drive):
    results, log = execute(client, ITEMS, CFG)
    assert all(r["status"] == "done" for r in results)
    assert path_of(drive, "a") == "Learning/University"
    assert drive.files["b"]["name"] == "Kickoff notes"
    assert path_of(drive, "c") == "Archive"
    assert {e["id"] for e in log} == {"a", "b", "c"}
    assert all(e["old_parent"] == "inbox" and "old_name" in e for e in log)


def test_cap_limits_actions(client, drive):
    results, _ = execute(client, ITEMS, {**CFG, "max_actions_per_run": 1})
    assert [r["status"] for r in results] == ["done", "skipped_cap", "skipped_cap"]


def test_blocked_item_halts_the_run_without_leaking(client, drive):
    items = ITEMS[:1] + [{"id": "secret", "action": "move", "target_folder": "Content"}] + ITEMS[1:2]
    results, log = execute(client, items, CFG)
    assert [r["status"] for r in results] == ["done", "refused", "not_run"]
    assert "secret" not in json.dumps(results) and "secret" not in json.dumps(log)
    assert [e["id"] for e in log] == ["a"]  # earlier work stays undoable


def test_unknown_action_is_never_executed(client, drive):
    results, _ = execute(client, [{"id": "a", "action": "delete"}], CFG)
    assert results[0]["status"] == "invalid" and mutations(drive) == []


def test_undo_reverses_moves_and_renames(client, drive):
    _, log = execute(client, ITEMS, CFG)
    undo(client, log)
    assert all(path_of(drive, i) == "Downloads" for i in "abc")
    assert drive.files["b"]["name"] == "Untitled document"


# ---- decision log ----
from execute import log_decisions

CANDS = {"a": {"id": "a", "name": "notes.txt", "path": "Downloads"},
         "b": {"id": "b", "name": "Untitled document", "path": "Downloads"},
         "c": {"id": "c", "name": "meme.png", "path": "Downloads"}}


def test_live_run_logs_every_decision_and_remembers_where_moves_went(client, drive):
    results, _ = execute(client, ITEMS, CFG)
    state = {}
    log_decisions(client, state, results, ITEMS, CANDS, "2026-11-13", "20261113T000000Z")
    assert [e["action"] for e in state["history"]] == ["move", "rename", "archive"]
    assert state["placed_to"] == {"a": "Learning/University", "c": "Archive"}
    logs = [f for f in drive.files.values() if f["name"] == "decisions_20261113T000000Z.json"]
    assert len(logs) == 1


def test_dry_run_logs_proposals_but_places_nothing(client, drive):
    results, _ = execute(client, ITEMS, {**CFG, "dry_run": True})
    state = {}
    log_decisions(client, state, results, ITEMS, CANDS, "2026-11-13", "20261113T000000Z")
    assert {e["status"] for e in state["history"]} == {"proposed"}
    assert state.get("placed_to", {}) == {}
    assert any(f["name"] == "decisions_20261113T000000Z.json" for f in drive.files.values())


def test_a_refusal_leaves_no_name_or_id_in_the_decision_log(client, drive):
    items = [{"id": "secret", "action": "move", "target_folder": "Learning"}]
    results, _ = execute(client, items, CFG)
    state = {}
    log_decisions(client, state, results, items, {"secret": {"name": "s.txt", "path": "Vault"}},
                  "2026-11-13", "20261113T000000Z")
    assert state["history"] == []
    assert "s.txt" not in json.dumps(state) and "secret" not in json.dumps(state)


def test_live_run_saves_its_undo_log_in_drive_and_remembers_it(client, drive):
    from execute import save_undo_log
    state = {}
    log = [{"id": "x", "old_parent": "p", "new_parent": "q", "old_name": "n"}]
    save_undo_log(client, state, log, stamp="20261120T154000Z", run_date="2026-11-20")
    assert state["undo_logs"] == [{"run": "2026-11-20", "file": "undo_20261120T154000Z.json", "count": 1}]
    assert any(f["name"] == "undo_20261120T154000Z.json" for f in drive.files.values())
