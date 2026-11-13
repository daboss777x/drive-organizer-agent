"""Read one file's text for summarizing. Re-checks the guard first.

python tools/read_file.py <file_id> [--max-chars N]
Prints JSON: {id, name, mimeType, path?, kind: text|metadata, text?, truncated?}
"""
import io
import json

from common import load_config, run
from google_client import EXPORT_MIME

DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
MEDIA_PREFIXES = ("video/", "audio/", "image/")


def _pdf_text(data):
    from pypdf import PdfReader
    return "\n".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(data)).pages)


def _docx_text(data):
    import docx
    return "\n".join(p.text for p in docx.Document(io.BytesIO(data)).paragraphs)


def extract(client, file_id, max_chars, screen_state=None):
    """screen_state: the agent state. When given, files the name screen hasn't cleared are refused."""
    meta = client.get_meta(file_id)  # guard re-check
    if screen_state is not None:
        from screen import Flagged, is_unread
        if is_unread(screen_state, meta):
            raise Flagged()
    mime = meta.get("mimeType", "")
    base = {"id": meta["id"], "name": meta["name"], "mimeType": mime,
            "modifiedTime": meta.get("modifiedTime")}
    text = None
    try:
        if mime in EXPORT_MIME:
            text = client.export_text(file_id)
        elif mime == "application/pdf":
            text = _pdf_text(client.download(file_id))
        elif mime == DOCX:
            text = _docx_text(client.download(file_id))
        elif mime.startswith("text/") or mime in ("application/json", "text/csv"):
            text = client.download(file_id).decode("utf-8", "replace")
    except Exception as e:
        if type(e).__name__ == "Blocked":
            raise
        text = None
    if not text or not text.strip() or mime.startswith(MEDIA_PREFIXES):
        return {**base, "kind": "metadata"}
    return {**base, "kind": "text", "text": text[:max_chars], "truncated": len(text) > max_chars}


def main(argv):
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("file_id")
    ap.add_argument("--max-chars", type=int)
    a = ap.parse_args(argv)
    import os
    from common import read_json, run_dir
    from google_client import from_env
    state = read_json(os.path.join(run_dir(), "state.json"), {}) or {}  # missing -> nothing cleared
    out = extract(from_env(), a.file_id, a.max_chars or load_config()["max_chars_per_file"],
                  screen_state=state)
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    run(main)
