"""Runs the Apps Script bridge's own tests (bridge/code.test.js) so one `pytest` covers both."""
import shutil
import subprocess
import pytest


@pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
def test_apps_script_bridge_tests_pass():
    r = subprocess.run(["node", "--test", "bridge/code.test.js"], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout[-2000:]
