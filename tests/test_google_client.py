import pytest
from fakes import FakeDrive
from guard import Guard, Blocked
from google_client import GoogleClient

F = "FORBIDDEN_FOLDER"


@pytest.fixture
def drive():
    d = FakeDrive()
    d.folder(F, "Vault")
    d.folder("work", "Work")
    d.add("ok", "plan.txt", parent="work")
    d.text["ok"] = "hello"
    d.add("hidden", "notes.txt", parent=F)
    d.text["hidden"] = "SECRET"
    return d


@pytest.fixture(params=["direct", "bridge"])
def client(drive, request):
    """Every test runs twice: straight on FakeDrive, and through BridgeApi + the Apps Script simulator."""
    if request.param == "direct":
        return GoogleClient(drive, Guard({F}))
    from bridge import BridgeApi
    from bridge_sim import BridgeSim
    return GoogleClient(BridgeApi(BridgeSim(drive), secret="s"), Guard({F}))


def acted_on(drive, id):
    return [c for c in drive.calls if c[1] == id and c[0] != "get"]


@pytest.mark.parametrize("op", [
    lambda c: c.export_text("hidden"),
    lambda c: c.download("hidden"),
    lambda c: c.move("hidden", "work"),
    lambda c: c.rename("hidden", "x.txt"),
])
def test_actions_on_blocked_file_are_refused_before_any_api_call(client, drive, op):
    with pytest.raises(Blocked):
        op(client)
    assert acted_on(drive, "hidden") == []


def test_cannot_move_a_file_into_the_forbidden_folder(client, drive):
    with pytest.raises(Blocked):
        client.move("ok", F)
    assert acted_on(drive, "ok") == []


def test_allowed_file_can_be_read_moved_and_renamed(client, drive):
    drive.folder("dest", "Clients", parent="root")
    assert client.export_text("ok") == "hello"
    client.move("ok", "dest")
    client.rename("ok", "plan v2.txt")
    assert drive.files["ok"]["parents"] == ["dest"]
    assert drive.files["ok"]["name"] == "plan v2.txt"


def test_list_allowed_filters_and_counts_blocked_files(client, drive):
    drive.folder("sub", "sub", parent=F)
    drive.add("deep", "deep.txt", parent="sub")
    drive.add("named", "passport.jpg", parent="work")
    drive.add("theirs", "shared.txt", parent="work", ownedByMe=False)
    files, blocked = client.list_allowed()
    assert [f["id"] for f in files] == ["ok"]
    assert blocked == 2  # deep + named; direct children never even returned (query exclusion)


def test_list_allowed_passes_forbidden_folders_to_the_query(client, drive):
    files, _ = client.list_allowed()
    assert "hidden" not in [f["id"] for f in files]
    assert not any(c == ("get", "hidden") for c in drive.calls)


def test_list_allowed_respects_cap_and_since(client, drive):
    for i in range(5):
        drive.add(f"n{i}", f"n{i}.txt", parent="work", modifiedTime=f"2026-06-0{i+1}T00:00:00Z")
    files, _ = client.list_allowed(since="2026-06-02T00:00:00Z", cap=2)
    assert len(files) == 2
    assert all(f["modifiedTime"] > "2026-06-02T00:00:00Z" for f in files)


def test_ensure_folder_creates_missing_path_once(client, drive):
    a = client.ensure_folder("Clients/Northbeam/Contracts")
    b = client.ensure_folder("Clients/Northbeam/Contracts")
    assert a == b
    assert len([c for c in drive.calls if c[0] == "create_folder"]) == 3


def test_agent_sheet_is_created_inside_drive_agent_folder(client, drive):
    sid = client.create_agent_sheet("Drive Agent Inbox")
    f = drive.files[sid]
    assert f["mimeType"] == "application/vnd.google-apps.spreadsheet"
    assert drive.files[f["parents"][0]]["name"] == "_DriveAgent"


def test_cannot_rename_a_file_to_a_sensitive_name(client, drive):
    with pytest.raises(Blocked):
        client.rename("ok", "passport scan.pdf")
    assert acted_on(drive, "ok") == []


def test_list_allowed_fetches_each_missing_folder_at_most_once(drive):
    """Every path walk ends at My Drive, which list_files never returns. Without a cache that is
    one bridge round-trip per file: hours on a real Drive."""
    client = GoogleClient(drive, Guard({F}))
    for i in range(30):
        drive.add(f"w{i}", f"w{i}.txt", parent="work")
        drive.add(f"r{i}", f"r{i}.txt")  # top level
    files, _ = client.list_allowed()
    assert len(files) == 61
    gets = [c[1] for c in drive.calls if c[0] == "get"]
    assert len(gets) == len(set(gets)), f"repeated fetches: {len(gets)} for {len(set(gets))} ids"


def test_agent_sheet_is_reused_instead_of_created_again(client, drive):
    """Runs that stop before `finish` lose the saved sheet ID; the next run must find the sheet."""
    first = client.find_or_create_agent_sheet("Drive Agent Inbox")
    second = client.find_or_create_agent_sheet("Drive Agent Inbox")
    assert first == second
    sheets = [f for f in drive.files.values() if f["name"] == "Drive Agent Inbox"]
    assert len(sheets) == 1


def test_folders_found_once_are_remembered_for_the_rest_of_the_run(drive):
    client = GoogleClient(drive, Guard({F}))
    first = client.ensure_folder("Clients/Acme/Notes")
    before = len(drive.calls)
    assert client.ensure_folder("Clients/Acme/Notes") == first
    assert client.ensure_folder("Clients/Acme") is not None
    assert drive.calls[before:] == []                       # no more lookups at all


def test_remembered_folders_never_skip_the_guard_for_the_forbidden_folder(drive):
    client = GoogleClient(drive, Guard({F}))
    with pytest.raises(Blocked):
        client.ensure_folder("Vault")
    with pytest.raises(Blocked):
        client.ensure_folder("Vault")


# ---- fewer round trips: the bridge sends the folder chain with each file ----
def _counted(drive):
    import collections
    from bridge import BridgeApi
    from bridge_sim import BridgeSim
    calls, sim = collections.Counter(), BridgeSim(drive)

    def send(p):
        calls[p["action"]] += 1
        return sim(p)
    return GoogleClient(BridgeApi(send, secret="s"), Guard({F})), calls


def test_reading_a_file_deep_in_folders_takes_two_calls(drive):
    drive.folder("x", "Ivy", parent="work"); drive.folder("y", "Acme", parent="x")
    drive.add("deepok", "brief.txt", parent="y"); drive.text["deepok"] = "hi"
    client, calls = _counted(drive)
    assert client.export_text("deepok") == "hi"
    assert sum(calls.values()) <= 2, dict(calls)


def test_one_move_takes_at_most_four_calls(drive):
    from execute import run_items
    client, calls = _counted(drive)
    run_items(client, [{"id": "ok", "action": "move", "target_folder": "Content"}],
              {"dry_run": False, "max_actions_per_run": 9})
    assert sum(calls.values()) <= 4, dict(calls)


def test_the_python_guard_still_blocks_using_the_chain(drive):
    drive.folder("sub", "sub", parent=F); drive.add("hid2", "x.txt", parent="sub")
    client, _ = _counted(drive)
    with pytest.raises(Blocked):
        client.export_text("hid2")
