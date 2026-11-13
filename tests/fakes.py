"""In-memory stand-in for Google Drive. No network, ever."""
import copy

FOLDER = "application/vnd.google-apps.folder"
SHORTCUT = "application/vnd.google-apps.shortcut"
DOC = "application/vnd.google-apps.document"


from google_client import NotFound


class FakeApiError(Exception):
    pass


class FakeDrive:
    def __init__(self):
        self.files = {"root": {"id": "root", "name": "My Drive", "mimeType": FOLDER}}
        self.text = {}          # file id -> exported/extracted text
        self.fail_ids = set()   # ids whose metadata fetch raises
        self.calls = []         # (op, id) log

    def add(self, id, name, parent="root", mime="text/plain", **extra):
        f = {"id": id, "name": name, "mimeType": mime, "parents": [parent],
             "modifiedTime": extra.pop("modifiedTime", "2026-01-01T00:00:00Z"),
             "ownedByMe": extra.pop("ownedByMe", True), "trashed": False}
        f.update(extra)
        self.files[id] = f
        return f

    def folder(self, id, name, parent="root"):
        return self.add(id, name, parent, FOLDER)

    def shortcut(self, id, name, target, parent="root"):
        return self.add(id, name, parent, SHORTCUT,
                        shortcutDetails={"targetId": target})

    def get_meta(self, id):
        self.calls.append(("get", id))
        if id in self.fail_ids:
            raise FakeApiError("boom")
        if id not in self.files:
            raise NotFound()
        return copy.deepcopy(self.files[id])

    # ---- adapter interface (same method names as tools/bridge.BridgeApi) ----
    def list_files(self, exclude_parents=(), modified_after=None):
        self.calls.append(("list", None))
        out = []
        for f in self.files.values():
            if f["id"] == "root" or f.get("trashed"):
                continue
            if any(p in exclude_parents for p in f.get("parents", [])):
                continue
            if modified_after and f["modifiedTime"] <= modified_after:
                continue
            out.append(copy.deepcopy(f))
        return out

    def export_text(self, id, mime=None):
        self.calls.append(("export", id))
        return self.text.get(id, "")

    def download(self, id):
        self.calls.append(("download", id))
        return self.text.get(id, "").encode()

    def update(self, id, add_parent=None, remove_parent=None, name=None):
        self.calls.append(("update", id))
        f = self.files[id]
        if add_parent:
            f["parents"] = [p for p in f["parents"] if p != remove_parent] + [add_parent]
        if name:
            f["name"] = name
        return copy.deepcopy(f)

    def create_folder(self, name, parent):
        self.calls.append(("create_folder", name))
        new_id = f"folder_{len(self.files)}"
        return self.folder(new_id, name, parent)

    def find_child_folder(self, name, parent):
        for f in self.files.values():
            if f["mimeType"] == FOLDER and f["name"] == name and parent in f.get("parents", []):
                return copy.deepcopy(f)
        return None

    def find_child_file(self, name, parent):
        for f in self.files.values():
            if f["name"] == name and parent in f.get("parents", []) and f["mimeType"] != FOLDER:
                return copy.deepcopy(f)
        return None

    def upload(self, name, parent, data, mime, file_id=None):
        self.calls.append(("upload", name))
        if file_id is None:
            file_id = f"up_{len(self.files)}"
            self.add(file_id, name, parent, mime)
        self.text[file_id] = data.decode() if isinstance(data, bytes) else data
        return copy.deepcopy(self.files[file_id])

    def create_file(self, name, parent, mime):
        self.calls.append(("create_file", name))
        return self.add(f"new_{len(self.files)}", name, parent, mime)
