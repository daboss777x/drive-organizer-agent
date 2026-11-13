"""End-to-end dry run through every CLI, in workflow order, against FakeDrive."""
import json
import sys
import pytest
from fakes import FakeDrive, DOC
from guard import Guard
import google_client
import common


@pytest.fixture
def env(monkeypatch, tmp_path):
    d = FakeDrive()
    d.folder("VAULT0000000000000000000000000", "Vault")
    d.add("SECRET00000000000000000000000", "tax return.pdf", parent="VAULT0000000000000000000000000")
    d.folder("DL", "Downloads")
    d.add("A" * 28, "Untitled document", parent="DL", mime=DOC)
    d.text["A" * 28] = "Kickoff notes for Northbeam"
    d.add("B" * 28, "meme.png", parent="DL", mime="image/png")
    d.add("C" * 28, "Payslip March.pdf", parent="DL", mime="application/pdf")
    d.add("D" * 28, "Mum's things", parent="DL", mime=DOC)
    client = google_client.GoogleClient(d, Guard({"VAULT0000000000000000000000000"}))
    monkeypatch.setattr(google_client, "from_env", lambda: client)
    monkeypatch.setenv("DRIVE_AGENT_RUN", "current")
    monkeypatch.setattr(common, "ROOT", str(tmp_path))
    import re
    cfg = re.sub(r"(?m)^dry_run:.*$", "dry_run: true", open("config.yaml").read())  # never the live setting
    (tmp_path / "config.yaml").write_text(cfg)
    (tmp_path / "rules.md").write_text("# Learned rules\n")
    (tmp_path / "business_context.md").write_text("# Context\n")
    return d, tmp_path


def cli(module, *argv):
    mod = __import__(module)
    sys.argv = [module, *argv]
    with pytest.raises(SystemExit) as e:
        common.run(mod.main)
    return e.value.code


def test_full_dry_run_changes_nothing_and_leaks_nothing(env):
    d, root = env
    rd = root / "runs" / "current"
    assert cli("state", "begin") == 0
    assert cli("drive_scan") == 0
    assert cli("state", "todo") == 0
    todo = json.loads((rd / "to_summarize.json").read_text())
    assert len(todo) == 4
    screen_input = json.loads((rd / "screen_input.json").read_text())
    assert sorted(x["name"] for x in screen_input) == ["Mum's things", "Untitled document", "meme.png"]
    assert all(set(x) == {"id", "name", "path", "mimeType"} for x in screen_input)  # no content
    (rd / "screen_ai.json").write_text(json.dumps([
        {"id": "A" * 28, "sensitive": False}, {"id": "B" * 28, "sensitive": False},
        {"id": "D" * 28, "sensitive": True, "reason": "family"}]))
    assert cli("state", "screen") == 0
    flagged = json.loads((rd / "flagged.json").read_text())
    assert sorted(f["name"] for f in flagged) == ["Mum's things", "Payslip March.pdf"]
    batches = sorted((rd / "batches").glob("batch_*.json"))
    assert len(batches) == 1 and len(json.loads(batches[0].read_text())) == 2
    (rd / "summaries").mkdir()
    (rd / "summaries" / "batch_1.json").write_text(json.dumps(
        [{"id": "A" * 28, "summary": "Northbeam kickoff", "doc_type": "notes"},
         {"id": "B" * 28, "summary": "a meme", "doc_type": "image"}]))
    assert cli("state", "merge") == 0
    assert cli("dedupe") == 0
    assert cli("state", "digest") == 0
    digest = json.loads((rd / "classify_input.json").read_text())
    read = [r for r in digest if not r.get("unread")]
    assert {r["summary"]["summary"] for r in read} == {"Northbeam kickoff", "a meme"}
    unread = {r["name"]: r for r in digest if r.get("unread")}
    assert set(unread) == {"Payslip March.pdf", "Mum's things"}  # by name only, to file them unread
    assert all(r["summary"] is None for r in unread.values())
    (rd / "plan.json").write_text(json.dumps({"items": [
        {"id": "A" * 28, "action": "move", "target_folder": "Clients/Northbeam/Notes", "confidence": 0.9, "reason": "r"},
        {"id": "B" * 28, "action": "archive", "confidence": 0.5, "reason": "r"},
    ]}))
    assert cli("validate_plan") == 0
    before = len(d.calls)
    assert cli("execute", str(rd / "validated_plan.json")) == 0
    during = d.calls[before:]
    assert not [c for c in during if c[0] == "update"]  # a dry run moves/renames nothing
    # the only things created are the agent's own decision log and its folders
    assert {c[1] for c in during if c[0] == "create_folder"} <= {"_DriveAgent", "logs"}
    assert all(c[1].startswith("decisions_") for c in during if c[0] in ("upload", "create_file"))
    assert cli("report") == 0
    report = (rd / "report.md").read_text()
    assert "DRY RUN" in report and "Untitled document" in report
    assert cli("audit") == 0
    for f in rd.rglob("*.json"):
        text = f.read_text()
        assert "SECRET" not in text and "VAULT" not in text and "tax return" not in text


def test_scan_ignores_a_legacy_last_run_set_by_a_dry_run(env):
    """Run 4 (a dry run) stored last_run; the scan must not treat the backlog as already seen."""
    d, root = env
    rd = root / "runs" / "current"
    rd.mkdir(parents=True)
    (rd / "state.json").write_text(json.dumps({"last_run": "2099-01-01T00:00:00Z"}))
    assert cli("drive_scan") == 0
    assert len(json.loads((rd / "candidates.json").read_text())["candidates"]) == 4
