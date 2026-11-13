"""Shared CLI plumbing. Errors never print file names, IDs or API messages."""
import json
import os
import sys

from guard import REFUSAL, Blocked

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run(main):
    try:
        code = main(sys.argv[1:])
    except Blocked:
        print(REFUSAL, file=sys.stderr)
        sys.exit(3)
    except Exception as e:
        if type(e).__name__ != "Flagged":
            _fail(e)
        from screen import SKIP_MESSAGE
        print(SKIP_MESSAGE, file=sys.stderr)
        sys.exit(5)
    sys.exit(code or 0)


def _fail(e):  # the message may contain IDs/names from the API: print the type only
    name = type(e).__name__
    if name == "BridgeError":  # its .code is whitelisted in bridge.py, safe to show
        name += f"({e.code})"
    print(f"error: {name}", file=sys.stderr)
    sys.exit(1)


def load_config(path=None):
    import yaml
    with open(path or os.path.join(ROOT, "config.yaml")) as fh:
        return yaml.safe_load(fh)


def write_json(path, data):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)


def read_json(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path) as fh:
        return json.load(fh)


def run_dir(run_id=None):
    run_id = run_id or os.environ.get("DRIVE_AGENT_RUN") or "current"
    return os.path.join(ROOT, "runs", run_id)
