import history

CANDS = {"a": {"id": "a", "name": "notes.txt", "path": "Downloads"},
         "b": {"id": "b", "name": "Untitled document", "path": "Downloads"}}
ITEMS = [{"id": "a", "action": "move", "target_folder": "Learning/University", "reason": "course notes", "confidence": 0.9},
         {"id": "b", "action": "rename", "new_name": "Kickoff notes", "reason": "broken name", "confidence": 0.8}]


def test_record_adds_one_entry_per_result_with_reason_and_paths():
    state = {}
    results = [{"id": "a", "action": "move", "target_folder": "Learning/University", "status": "done"},
               {"id": "b", "action": "rename", "new_name": "Kickoff notes", "status": "proposed"}]
    history.record(state, "2026-11-13", results, ITEMS, CANDS)
    a, b = state["history"]
    assert a == {"run": "2026-11-13", "id": "a", "name": "notes.txt", "from": "Downloads",
                 "to": "Learning/University", "action": "move", "new_name": None,
                 "reason": "course notes", "confidence": 0.9, "status": "done"}
    assert b["to"] == "Downloads" and b["new_name"] == "Kickoff notes" and b["status"] == "proposed"


def test_refused_results_leave_no_trace():
    state = {}
    history.record(state, "2026-11-13", [{"status": "refused", "ok": False}], ITEMS, CANDS)
    assert state.get("history", []) == []


def test_history_keeps_only_the_newest_5000():
    state = {"history": [{"name": f"old{i}"} for i in range(5000)]}
    history.record(state, "2026-11-13", [{"id": "a", "action": "move", "target_folder": "X", "status": "done"}],
                   ITEMS, CANDS)
    assert len(state["history"]) == 5000 and state["history"][-1]["name"] == "notes.txt"
    assert state["history"][0]["name"] == "old1"


def test_find_matches_name_or_folders_newest_first():
    state = {"history": [{"name": "notes.txt", "from": "Downloads", "to": "Learning", "run": "1"},
                         {"name": "plan.pdf", "from": "", "to": "Clients/Northbeam", "run": "2"},
                         {"name": "notes v2.txt", "from": "Downloads", "to": "Content", "run": "3"}]}
    assert [e["run"] for e in history.find(state, "NOTES")] == ["3", "1"]
    assert [e["run"] for e in history.find(state, "northbeam")] == ["2"]
