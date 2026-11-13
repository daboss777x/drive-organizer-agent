"""SECURITY CORE. DO NOT MOVE THESE SETTINGS TO CONFIG.
Editable only by the owner, by hand. Claude is blocked from editing this file by a hook.
"""
import re

# ---- the owner edits these by hand. Paste the forbidden folder ID in place of PLACEHOLDER.
PLACEHOLDER = "<FORBIDDEN_FOLDER_ID>"
FORBIDDEN_FOLDER_IDS = {PLACEHOLDER}   # replace PLACEHOLDER with your folder ID: {"1AbC..."}
FORBIDDEN_FILE_IDS = set()          # optional extra individual files
# ----

REFUSAL = "refused: protected file"
SHORTCUT_MIME = "application/vnd.google-apps.shortcut"
MAX_DEPTH = 50

NAME_PATTERNS = [
    r"forbidden", r"private", r"passport", r"\bid\b", r"bank", r"password",
]


class Blocked(Exception):
    def __init__(self):
        super().__init__(REFUSAL)  # never carries a name or an ID


def default_guard():
    """The guard every tool uses. Blocks everything until the real ID is pasted in."""
    if not FORBIDDEN_FOLDER_IDS or PLACEHOLDER in FORBIDDEN_FOLDER_IDS:
        return _BlockAll()
    return Guard(FORBIDDEN_FOLDER_IDS, FORBIDDEN_FILE_IDS)


class Guard:
    def __init__(self, folder_ids, file_ids=(), name_patterns=NAME_PATTERNS):
        self.folder_ids = set(folder_ids)
        self.file_ids = set(file_ids)
        self.name_res = [re.compile(p, re.IGNORECASE) for p in name_patterns]
        self._folder_cache = {}  # folder id -> blocked?

    def is_blocked(self, file, get_meta):
        try:
            if self._self_blocked(file):
                return True
            if not file["parents"]:
                return True
            if file["mimeType"] == SHORTCUT_MIME:
                target = get_meta(file["shortcutDetails"]["targetId"])
                if self.is_blocked(target, get_meta):
                    return True
            return any(self._folder_blocked(p, get_meta, 0) for p in file["parents"])
        except Exception:
            return True  # fail closed

    def _self_blocked(self, f):
        return (f["id"] in self.folder_ids or f["id"] in self.file_ids
                or any(r.search(f["name"]) for r in self.name_res))

    def _folder_blocked(self, folder_id, get_meta, depth):
        if folder_id in self.folder_ids:
            return True
        if folder_id in self._folder_cache:
            return self._folder_cache[folder_id]
        if depth > MAX_DEPTH:
            raise RecursionError("parent chain too deep")
        folder = get_meta(folder_id)
        blocked = self._self_blocked(folder) or any(
            self._folder_blocked(p, get_meta, depth + 1)
            for p in folder.get("parents", []))  # no parents = top of My Drive
        self._folder_cache[folder_id] = blocked
        return blocked

    def assert_allowed(self, file_id, get_meta):
        """Fetch fresh metadata and refuse if blocked. Returns the metadata."""
        try:
            meta = get_meta(file_id)
        except Exception:
            raise Blocked() from None
        if self.is_blocked(meta, get_meta):
            raise Blocked()
        return meta


class _BlockAll(Guard):
    def __init__(self):
        super().__init__(set())

    def is_blocked(self, file, get_meta):
        return True
