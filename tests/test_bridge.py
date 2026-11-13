import base64
import pytest
from bridge import BridgeApi, BridgeError
from google_client import NotFound
from guard import Blocked


class FakeTransport:
    def __init__(self, response):
        self.response, self.sent = response, []

    def __call__(self, payload):
        self.sent.append(payload)
        return self.response


def api(response):
    t = FakeTransport(response)
    return BridgeApi(t, secret="s3cret"), t


def test_calls_send_secret_action_and_args():
    a, t = api({"ok": True, "result": {"id": "x"}})
    assert a.get_meta("x") == {"id": "x"}
    assert t.sent == [{"secret": "s3cret", "action": "get_meta", "args": {"id": "x"}}]


def test_list_files_sends_sorted_exclusions():
    a, t = api({"ok": True, "result": []})
    a.list_files(exclude_parents={"b", "a"}, modified_after="2026-01-01")
    assert t.sent[0]["args"] == {"exclude_parents": ["a", "b"], "modified_after": "2026-01-01"}


@pytest.mark.parametrize("error,exc", [("not_found", NotFound), ("refused", Blocked),
                                       ("error", BridgeError), ("unauthorized", BridgeError)])
def test_errors_are_mapped(error, exc):
    a, _ = api({"ok": False, "error": error})
    with pytest.raises(exc):
        a.get_meta("x")


@pytest.mark.parametrize("bad", [None, "html error page", [], {"result": 1}])
def test_malformed_responses_fail(bad):
    a, _ = api(bad)
    with pytest.raises(BridgeError):
        a.get_meta("x")


def test_download_and_upload_use_base64():
    a, t = api({"ok": True, "result": base64.b64encode(b"\x00pdf").decode()})
    assert a.download("x") == b"\x00pdf"
    a.upload("state.json", "p", b"{}", "application/json")
    assert base64.b64decode(t.sent[-1]["args"]["data"]) == b"{}"


# ---- sheets + mail ----
from bridge import BridgeSheets


def test_sheet_calls_map_to_bridge_actions():
    a, t = api({"ok": True, "result": [["file_id"]]})
    sh = BridgeSheets(a)
    assert sh.get_rows("SID") == [["file_id"]]
    sh.append("SID", [["a", "b"]])
    sh.set_status("SID", 5, "done")
    sh.setup("SID")
    actions = [(p["action"], p["args"]) for p in t.sent]
    assert actions[0] == ("sheet_rows", {"sid": "SID"})
    assert actions[1] == ("sheet_append", {"sid": "SID", "rows": [["a", "b"]]})
    assert actions[2][0] == "sheet_set" and actions[2][1]["row"] == 5 and actions[2][1]["value"] == "done"
    assert actions[2][1]["col"] == 10  # 1-based column of "status"
    assert actions[3][0] == "sheet_setup" and actions[3][1]["choices"][0] == "Approve"


def test_send_mail_maps_to_bridge_action():
    a, t = api({"ok": True, "result": "sent"})
    a.send_mail("me@x.com", "Report", "body")
    assert t.sent[0]["action"] == "send_mail"
    assert t.sent[0]["args"] == {"to": "me@x.com", "subject": "Report", "body": "body"}


# ---- diagnosable errors: a fixed, name-free code on every BridgeError ----
@pytest.mark.parametrize("response,code", [
    ({"ok": False, "error": "error"}, "error"),
    ({"ok": False, "error": "unauthorized"}, "unauthorized"),
    ({"ok": False, "error": "unknown_action"}, "unknown_action"),
    ({"ok": False, "error": "guard_unavailable"}, "guard_unavailable"),
    ({"ok": False, "error": "bad_config"}, "bad_config"),
    ({"ok": False, "error": "incomplete_listing"}, "incomplete_listing"),
    ({"ok": False, "error": "Secret Invoice.pdf missing"}, "other"),  # never echo free text
    (None, "bad_response"),
    ({"result": 1}, "bad_response"),
])
def test_bridge_error_has_whitelisted_code(response, code):
    a, _ = api(response)
    with pytest.raises(BridgeError) as e:
        a.get_meta("x")
    assert e.value.code == code
    assert "Invoice" not in str(e.value)


def test_cli_prints_bridge_error_code_only(capsys, monkeypatch):
    import sys
    import common
    monkeypatch.setattr(sys, "argv", ["tool"])

    def main(argv):
        raise BridgeError("bad_response")
    with pytest.raises(SystemExit) as e:
        common.run(main)
    assert e.value.code == 1
    assert capsys.readouterr().err.strip() == "error: BridgeError(bad_response)"


def test_cli_still_prints_type_only_for_other_errors(capsys, monkeypatch):
    import sys
    import common
    monkeypatch.setattr(sys, "argv", ["tool"])

    def main(argv):
        raise ValueError("Secret Invoice.pdf")
    with pytest.raises(SystemExit):
        common.run(main)
    assert capsys.readouterr().err.strip() == "error: ValueError"
