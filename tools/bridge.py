"""Python side of the Apps Script bridge (bridge/Code.gs runs inside Google as the owner).

BridgeApi has the same methods as tests/fakes.FakeDrive, so GoogleClient (and its guard)
sits on top of it unchanged. Every request carries the shared secret.
Errors never carry names or IDs: not_found -> NotFound, refused -> Blocked, else BridgeError.
"""
import base64
import json

from google_client import NotFound
from guard import Blocked


SAFE_CODES = {"bad_response", "error", "unauthorized", "unknown_action", "bad_recipient",
              "guard_unavailable", "bad_config", "incomplete_listing"}


class BridgeError(Exception):
    """`code` is always one of SAFE_CODES or "other", so it can be printed (no names/IDs)."""
    def __init__(self, code):
        self.code = code if code in SAFE_CODES else "other"
        super().__init__(self.code)


class BridgeApi:
    def __init__(self, transport, secret):
        self.transport = transport
        self.secret = secret

    def _call(self, action, **args):
        resp = self.transport({"secret": self.secret, "action": action, "args": args})
        if not isinstance(resp, dict) or "ok" not in resp:
            raise BridgeError("bad_response")
        if resp["ok"]:
            return resp.get("result")
        err = resp.get("error")
        if err == "not_found":
            raise NotFound()
        if err == "refused":
            raise Blocked()
        raise BridgeError(err)

    # ---- Drive (same interface as FakeDrive) ----
    def get_meta(self, id):
        return self._call("get_meta", id=id)

    def list_files(self, exclude_parents=(), modified_after=None):
        return self._call("list_files", exclude_parents=sorted(exclude_parents),
                          modified_after=modified_after)

    def export_text(self, id, mime=None):
        return self._call("export_text", id=id, mime=mime or "text/plain")

    def download(self, id):
        return base64.b64decode(self._call("download", id=id) or "")

    def update(self, id, add_parent=None, remove_parent=None, name=None):
        return self._call("update", id=id, add_parent=add_parent, remove_parent=remove_parent, name=name)

    def create_folder(self, name, parent):
        return self._call("create_folder", name=name, parent=parent)

    def create_file(self, name, parent, mime):
        return self._call("create_file", name=name, parent=parent, mime=mime)

    def find_child_folder(self, name, parent):
        return self._call("find_child_folder", name=name, parent=parent)

    def find_child_file(self, name, parent):
        return self._call("find_child_file", name=name, parent=parent)

    def upload(self, name, parent, data, mime, file_id=None):
        data = data.encode() if isinstance(data, str) else data
        return self._call("upload", name=name, parent=parent, mime=mime, file_id=file_id,
                          data=base64.b64encode(data).decode())

    # ---- Gmail (send only; the script refuses any recipient but REPORT_EMAIL) ----
    def send_mail(self, to, subject, body):
        return self._call("send_mail", to=to, subject=subject, body=body)


def http_transport(url, timeout=300):  # pragma: no cover - exercised by the live smoke test
    import urllib.request

    def send(payload):
        req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                     headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as r:  # follows Apps Script's redirect
            try:
                return json.loads(r.read().decode("utf-8"))
            except ValueError:
                return None
    return send


class BridgeSheets:
    """Inbox Sheet operations: get_rows / append / set_status / setup."""
    def __init__(self, api):
        self.api = api

    def get_rows(self, sid):
        return self.api._call("sheet_rows", sid=sid) or []

    def append(self, sid, rows):
        return self.api._call("sheet_append", sid=sid, rows=rows)

    def set_status(self, sid, row_num, status):
        from inbox_sheet import HEADER
        return self.api._call("sheet_set", sid=sid, row=row_num,
                              col=HEADER.index("status") + 1, value=status)

    def setup(self, sid):
        from inbox_sheet import CHOICES, HEADER
        return self.api._call("sheet_setup", sid=sid, header=HEADER, choices=CHOICES,
                              answer_col=HEADER.index("answer") + 1)
