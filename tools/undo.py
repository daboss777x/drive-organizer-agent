"""Reverse an undo log (moves back to the old folder, renames back to the old name).

python tools/undo.py runs/current/undo_log.json [--only FILE_ID]
"""
from common import read_json
from guard import Blocked


def run(client, log, only=None):
    results = []
    for e in reversed(log):
        if only and e["id"] != only:
            continue
        try:
            meta = client.get_meta(e["id"])
            if meta["parents"][0] != e["old_parent"]:
                client.move(e["id"], e["old_parent"])
            if meta["name"] != e["old_name"]:
                client.rename(e["id"], e["old_name"])
            results.append({"id": e["id"], "status": "undone"})
        except Blocked:
            results.append({"status": "refused"})  # no id: halt the undo here
            break
        except Exception as ex:
            results.append({"id": e["id"], "status": f"error: {type(ex).__name__}"})
    return results


def main(argv):
    import argparse
    from google_client import from_env
    ap = argparse.ArgumentParser()
    ap.add_argument("log")
    ap.add_argument("--only")
    a = ap.parse_args(argv)
    res = run(from_env(), read_json(a.log, []), a.only)
    if any(r["status"] == "refused" for r in res):
        raise Blocked()
    print(f"undone={sum(r['status'] == 'undone' for r in res)} total={len(res)}")
    return 0


if __name__ == "__main__":
    from common import run as _cli
    _cli(main)
