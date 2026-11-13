"""The ONLY module the tools use to reach Google Drive. Every file-level call is guarded.

GoogleClient  - guarded operations, on top of any adapter with FakeDrive's method names
                (tests/fakes.FakeDrive, or tools/bridge.BridgeApi in real runs)
from_env()    - real client over the Apps Script bridge, from DRIVE_BRIDGE_* env vars only
"""
import os

from guard import Blocked, default_guard

FOLDER_MIME = "application/vnd.google-apps.folder"
AGENT_FOLDER = "_DriveAgent"
EXPORT_MIME = {
    "application/vnd.google-apps.document": "text/plain",
    "application/vnd.google-apps.spreadsheet": "text/csv",
    "application/vnd.google-apps.presentation": "text/plain",
}


class NotFound(Exception):
    """The ID is not a file we can see (HTTP 404)."""


class GoogleClient:
    def __init__(self, api, guard):
        self.api = api
        self.guard = guard

    def _check(self, file_id):
        return self.guard.assert_allowed(file_id, self.api.get_meta)

    def get_meta(self, file_id):
        return self._check(file_id)

    def export_text(self, file_id):
        meta = self._check(file_id)
        return self.api.export_text(file_id, EXPORT_MIME.get(meta["mimeType"], "text/plain"))

    def download(self, file_id):
        self._check(file_id)
        return self.api.download(file_id)

    def move(self, file_id, new_parent_id):
        meta = self._check(file_id)
        self._check(new_parent_id)
        old = meta["parents"][0]
        self.api.update(file_id, add_parent=new_parent_id, remove_parent=old)
        return old

    def list_allowed(self, since=None, cap=None):
        """All My Drive files I own, minus blocked ones. Returns (files, blocked_count).
        Blocked files are dropped here, in memory, before anything is returned."""
        raw = self.api.list_files(exclude_parents=self.guard.folder_ids, modified_after=since)
        index = {f["id"]: f for f in raw}

        def lookup(i):  # cached: My Drive itself (top of every path) is never in `raw`
            if i not in index:
                index[i] = self.api.get_meta(i)
            return index[i]
        allowed, blocked = [], 0
        for f in raw:
            if f.get("mimeType") == FOLDER_MIME or not f.get("ownedByMe", False):
                continue
            if self.guard.is_blocked(f, lookup):
                blocked += 1
                continue
            f["path"] = self._path(f, lookup)
            allowed.append(f)
        allowed.sort(key=lambda f: f.get("modifiedTime", ""), reverse=True)
        return (allowed[:cap] if cap else allowed), blocked

    def _path(self, f, lookup):
        names, cur = [], f
        for _ in range(50):
            parents = cur.get("parents") or []
            if not parents:
                break
            cur = lookup(parents[0])
            if cur.get("parents"):  # the top folder (My Drive) has none and is left out
                names.append(cur["name"])
        return "/".join(reversed(names))

    def ensure_folder(self, path, root="root"):
        """Find or create a folder path like 'Clients/Northbeam'. Returns its ID."""
        parent = root
        for name in [p for p in path.split("/") if p]:
            if parent != root:
                self._check(parent)
            found = self.api.find_child_folder(name, parent)
            parent = found["id"] if found else self.api.create_folder(name, parent)["id"]
        self._check(parent)
        return parent

    def read_agent_file(self, name, sub=""):
        folder = self.ensure_folder(f"{AGENT_FOLDER}/{sub}".rstrip("/"))
        f = self.api.find_child_file(name, folder)
        if not f:
            return None
        data = self.download(f["id"])
        return data.decode("utf-8") if isinstance(data, bytes) else data

    def write_agent_file(self, name, data, mime="application/json", sub=""):
        folder = self.ensure_folder(f"{AGENT_FOLDER}/{sub}".rstrip("/"))
        f = self.api.find_child_file(name, folder)
        if f:
            self._check(f["id"])
        meta = self.api.upload(name, folder, data.encode() if isinstance(data, str) else data,
                               mime, file_id=f["id"] if f else None)
        return meta["id"]

    def find_or_create_agent_sheet(self, name):
        """Reuse the sheet in _DriveAgent if one exists (a run that stopped early never saved its ID)."""
        folder = self.ensure_folder(AGENT_FOLDER)
        found = self.api.find_child_file(name, folder)
        if found and found.get("mimeType") == "application/vnd.google-apps.spreadsheet":
            self._check(found["id"])
            return found["id"]
        return self.api.create_file(name, folder, "application/vnd.google-apps.spreadsheet")["id"]

    def create_agent_sheet(self, name):
        folder = self.ensure_folder(AGENT_FOLDER)
        return self.api.create_file(name, folder, "application/vnd.google-apps.spreadsheet")["id"]

    def rename(self, file_id, new_name):
        meta = self._check(file_id)
        if self.guard.is_blocked({**meta, "name": new_name}, self.api.get_meta):
            raise Blocked()
        self.api.update(file_id, name=new_name)
        return meta["name"]


def from_env():  # pragma: no cover - exercised by the live smoke test
    """Real client: Drive via the Apps Script bridge (bridge/Code.gs). Env vars only, never a file."""
    from bridge import BridgeApi, http_transport
    api = BridgeApi(http_transport(os.environ["DRIVE_BRIDGE_URL"]), os.environ["DRIVE_BRIDGE_SECRET"])
    return GoogleClient(api, default_guard())
