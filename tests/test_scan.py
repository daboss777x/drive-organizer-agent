import json
import pytest
from fakes import FakeDrive
from guard import Guard
from google_client import GoogleClient
from drive_scan import scan

F = "FORBIDDEN_FOLDER"


@pytest.fixture
def client():
    d = FakeDrive()
    d.folder(F, "Vault")
    d.folder("sub", "Deep", parent=F)
    d.add("deep", "deep.txt", parent="sub")
    d.folder("work", "Work")
    d.folder("proj", "Projects", parent="work")
    d.add("a", "proposal.docx", parent="proj", md5Checksum="m1", size="10")
    d.add("b", "notes.txt", parent="root", modifiedTime="2026-02-01T00:00:00Z")
    return GoogleClient(d, Guard({F}))


def test_scan_outputs_candidates_with_path_and_only_a_blocked_count(client):
    out = scan(client, state={}, since=None, cap=100)
    by_id = {c["id"]: c for c in out["candidates"]}
    assert set(by_id) == {"a", "b"}
    assert by_id["a"]["path"] == "Work/Projects"
    assert by_id["b"]["path"] == ""
    assert by_id["a"]["md5Checksum"] == "m1"
    assert out["blocked_count"] == 1
    text = json.dumps(out)
    assert "deep" not in text and "Deep" not in text and F not in text


def test_scan_skips_files_already_placed_and_unchanged(client):
    state = {"placed": {"b": "2026-02-01T00:00:00Z"}}
    out = scan(client, state=state, since=None, cap=100)
    assert [c["id"] for c in out["candidates"]] == ["a"]
    assert out["skipped_unchanged"] == 1


def test_the_agents_own_folder_is_never_a_candidate():
    from drive_scan import scan

    class C:
        def list_allowed(self, since=None):
            return ([{"id": "s", "name": "state.json", "path": "_DriveAgent", "modifiedTime": "1"},
                     {"id": "l", "name": "undo_x.json", "path": "_DriveAgent/logs", "modifiedTime": "1"},
                     {"id": "k", "name": "brief.docx", "path": "", "modifiedTime": "1"}], 0)
    out = scan(C(), {}, None, 150)
    assert [c["id"] for c in out["candidates"]] == ["k"]
