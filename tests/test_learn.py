import learn


def test_files_owner_moved_after_the_agent_placed_them_become_corrections():
    state = {"placed_to": {"a": "Content", "b": "Learning"}}
    metas = {"a": {"name": "deck.zip", "path": "Clients/Northbeam"}, "b": {"name": "n.txt", "path": "Learning"}}
    assert learn.corrections(state, metas) == [
        {"id": "a", "name": "deck.zip", "agent_to": "Content", "owner_to": "Clients/Northbeam"}]


def test_files_not_seen_now_are_ignored():
    assert learn.corrections({"placed_to": {"a": "Content"}}, {}) == []


def test_record_dedupes_caps_and_updates_placed_to():
    state = {"placed_to": {"a": "Content"},
             "corrections": [{"id": f"x{i}", "owner_to": "Y"} for i in range(500)]}
    c = [{"id": "a", "name": "deck.zip", "agent_to": "Content", "owner_to": "Clients/Northbeam"}]
    learn.record_corrections(state, c)
    learn.record_corrections(state, c)  # same correction again: not duplicated
    assert len(state["corrections"]) == 500
    assert state["corrections"][-1]["id"] == "a"
    assert sum(1 for x in state["corrections"] if x["id"] == "a") == 1
    assert state["placed_to"]["a"] == "Clients/Northbeam"
    assert learn.corrections(state, {"a": {"name": "deck.zip", "path": "Clients/Northbeam"}}) == []


# ---- reading the current Drive (through the guarded client) ----
from fakes import FakeDrive
from guard import Guard
from google_client import GoogleClient


def test_collect_reads_current_paths_through_the_guard_and_skips_protected_files():
    d = FakeDrive()
    d.folder("VAULT", "Vault")
    d.folder("cl", "Clients")
    d.folder("nb", "Northbeam", parent="cl")
    d.folder("ct", "Content")
    d.add("a", "deck.zip", parent="nb")        # the owner moved it from Content to Clients/Northbeam
    d.add("b", "script.docx", parent="ct")     # still where the agent put it
    d.add("s", "x.txt", parent="VAULT")        # now inside the forbidden folder
    client = GoogleClient(d, Guard({"VAULT"}))
    state = {"placed_to": {"a": "Content", "b": "Content", "s": "Content", "gone": "Content"}}
    new, skipped = learn.collect(client, state)
    assert new == [{"id": "a", "name": "deck.zip", "agent_to": "Content", "owner_to": "Clients/Northbeam"}]
    assert skipped == 2  # protected + deleted: counted, never named
    assert "x.txt" not in str(state)


def test_learn_command_writes_name_only_corrections(monkeypatch, tmp_path):
    import json, sys, pytest, common, google_client, state as st
    d = FakeDrive()
    d.folder("cl", "Clients")
    d.add("a", "deck.zip", parent="cl")
    client = GoogleClient(d, Guard({"VAULT"}))
    monkeypatch.setattr(google_client, "from_env", lambda: client)
    monkeypatch.setattr(common, "ROOT", str(tmp_path))
    monkeypatch.setenv("DRIVE_AGENT_RUN", "current")
    rd = tmp_path / "runs" / "current"
    rd.mkdir(parents=True)
    (rd / "state.json").write_text(json.dumps({"placed_to": {"a": "Content"}}))
    monkeypatch.setattr(sys, "argv", ["state", "learn"])
    with pytest.raises(SystemExit) as e:
        common.run(st.main)
    assert e.value.code == 0
    assert json.loads((rd / "corrections.json").read_text()) == [
        {"name": "deck.zip", "agent_to": "Content", "owner_to": "Clients"}]
