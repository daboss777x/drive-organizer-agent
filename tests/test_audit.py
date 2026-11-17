import json
import pytest
from fakes import FakeDrive
from guard import Guard
from audit import check

VAULT = "VAULTFOLDERID0000000000000000"
SECRET = "SECRETFILEID00000000000000000"
NORMAL = "NORMALFILEID00000000000000000"


@pytest.fixture
def drive():
    d = FakeDrive()
    d.folder(VAULT, "Vault")
    d.add(SECRET, "x.txt", parent=VAULT)
    d.add(NORMAL, "y.txt")
    return d


def write(tmp_path, name, data):
    p = tmp_path / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data) if not isinstance(data, str) else data)


def run_check(tmp_path, drive):
    return check([str(tmp_path)], Guard({VAULT}), drive.get_meta)


def test_clean_run_passes(tmp_path, drive):
    write(tmp_path, "candidates.json", {"candidates": [{"id": NORMAL}]})
    assert run_check(tmp_path, drive) is True


@pytest.mark.parametrize("leak", [SECRET, VAULT])
def test_protected_id_anywhere_in_artifacts_aborts(tmp_path, drive, leak):
    write(tmp_path, "summaries/batch_1.json", [{"id": NORMAL}])
    write(tmp_path, "logs/run.log", f"moved {leak} somewhere")
    assert run_check(tmp_path, drive) is False


def test_id_shaped_tokens_that_are_not_files_are_ignored(tmp_path, drive):
    write(tmp_path, "plan.json", {"hash": "a" * 64})
    assert run_check(tmp_path, drive) is True


def test_api_error_during_audit_aborts(tmp_path, drive):
    write(tmp_path, "plan.json", {"id": NORMAL})
    drive.fail_ids.add(NORMAL)
    assert run_check(tmp_path, drive) is False


def test_ids_already_checked_this_run_are_not_fetched_again(tmp_path, drive):
    write(tmp_path, "a.json", {"ids": [NORMAL]})
    drive.calls.clear()
    assert check([str(tmp_path)], Guard({VAULT}), drive.get_meta, known_ok={NORMAL}) is True
    assert ("get", NORMAL) not in drive.calls


def test_forbidden_ids_still_fail_even_if_listed_as_known_ok(tmp_path, drive):
    write(tmp_path, "a.json", {"ids": [VAULT]})
    assert check([str(tmp_path)], Guard({VAULT}), drive.get_meta, known_ok={VAULT}) is False


def test_checksums_are_not_looked_up_as_if_they_were_file_ids(tmp_path, drive):
    md5 = "9e107d9d372bb6826bd81d3542a419d6"
    write(tmp_path, "c.json", {"md5Checksum": md5})
    drive.calls.clear()
    assert check([str(tmp_path)], Guard({VAULT}), drive.get_meta, not_ids={md5}) is True
    assert ("get", md5) not in drive.calls


def test_known_ok_ids_include_allowed_folders_but_never_the_forbidden_one(drive):
    from audit import known_ok_ids
    from google_client import GoogleClient
    drive.folder("WORKFOLDER0000000000000000000", "Work")
    client = GoogleClient(drive, Guard({VAULT}))
    ok = known_ok_ids(client)
    assert "WORKFOLDER0000000000000000000" in ok and NORMAL in ok
    assert VAULT not in ok and SECRET not in ok
