"""Simulates bridge/Code.gs over a FakeDrive, so GoogleClient tests can run through BridgeApi.
Argument names here must match bridge/Code.gs (also checked by bridge/code.test.js)."""
import base64
from google_client import NotFound


class BridgeSim:
    def __init__(self, drive, secret="s"):
        self.d, self.secret = drive, secret

    def __call__(self, p):
        if p.get("secret") != self.secret:
            return {"ok": False, "error": "unauthorized"}
        a, d = p["args"], self.d
        try:
            act = p["action"]
            if act == "get_meta":
                r = d.get_meta(a["id"])
            elif act == "list_files":
                r = d.list_files(set(a["exclude_parents"]), a["modified_after"])
            elif act == "export_text":
                r = d.export_text(a["id"], a["mime"])
            elif act == "download":
                r = base64.b64encode(d.download(a["id"])).decode()
            elif act == "update":
                r = d.update(a["id"], a["add_parent"], a["remove_parent"], a["name"])
            elif act in ("create_folder", "find_child_folder", "find_child_file"):
                r = getattr(d, act)(a["name"], a["parent"])
            elif act == "create_file":
                r = d.create_file(a["name"], a["parent"], a["mime"])
            elif act == "upload":
                r = d.upload(a["name"], a["parent"], base64.b64decode(a["data"]), a["mime"], a["file_id"])
            else:
                return {"ok": False, "error": "unknown_action"}
            return {"ok": True, "result": r}
        except NotFound:
            return {"ok": False, "error": "not_found"}
        except Exception:
            return {"ok": False, "error": "error"}
