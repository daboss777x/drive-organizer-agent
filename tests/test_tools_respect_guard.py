"""Every CLI tool, given a protected ID, refuses with exit 3 and prints nothing identifying."""
import json
import sys
import pytest
from fakes import FakeDrive
from guard import Guard, REFUSAL
import google_client
import common

SECRET_ID, SECRET_NAME, SECRET_TEXT = "SECRETID123", "my diary.txt", "very private words"


@pytest.fixture
def fake(monkeypatch, tmp_path):
    d = FakeDrive()
    d.folder("VAULT", "Vault")
    d.add(SECRET_ID, SECRET_NAME, parent="VAULT")
    d.text[SECRET_ID] = SECRET_TEXT
    d.folder("work", "Work")
    client = google_client.GoogleClient(d, Guard({"VAULT"}))
    monkeypatch.setattr(google_client, "from_env", lambda: client)
    monkeypatch.setenv("DRIVE_AGENT_RUN", "test")
    monkeypatch.setattr(common, "ROOT", str(tmp_path))
    (tmp_path / "config.yaml").write_text(
        "dry_run: false\nmax_actions_per_run: 10\nmax_chars_per_file: 100\n")
    return d


def run_tool(module, argv, monkeypatch, capsys):
    mod = __import__(module)
    monkeypatch.setattr(sys, "argv", [module] + argv)
    with pytest.raises(SystemExit) as e:
        common.run(mod.main)
    out = capsys.readouterr()
    return e.value.code, out.out + out.err


def assert_silent_refusal(code, output):
    assert code == 3
    assert REFUSAL in output
    for leak in (SECRET_ID, SECRET_NAME, SECRET_TEXT, "Vault", "VAULT"):
        assert leak not in output


def test_read_file_refuses_blocked_id(fake, monkeypatch, capsys):
    assert_silent_refusal(*run_tool("read_file", [SECRET_ID, "--max-chars", "100"], monkeypatch, capsys))


def test_execute_refuses_blocked_id(fake, monkeypatch, capsys, tmp_path):
    plan = tmp_path / "plan.json"
    plan.write_text(json.dumps({"actions": [{"id": SECRET_ID, "action": "archive"}]}))
    assert_silent_refusal(*run_tool("execute", [str(plan)], monkeypatch, capsys))
    executed = (tmp_path / "runs" / "test" / "executed.json").read_text()
    assert SECRET_ID not in executed


def test_undo_refuses_blocked_id(fake, monkeypatch, capsys, tmp_path):
    log = tmp_path / "undo.json"
    log.write_text(json.dumps([{"id": SECRET_ID, "old_parent": "work", "old_name": "x"}]))
    assert_silent_refusal(*run_tool("undo", [str(log)], monkeypatch, capsys))


def test_read_file_cli_skips_flagged_file_silently(fake, monkeypatch, capsys):
    fake.add("TAXID", "tax return.txt", parent="work")
    fake.text["TAXID"] = "TIN 998877"
    code, output = run_tool("read_file", ["TAXID"], monkeypatch, capsys)
    assert code == 5 and "flagged for review" in output and "998877" not in output
