"""Append a learned rule to rules.md (one line, no duplicates).

python tools/rules.py add "Files mentioning Northbeam -> Clients/Northbeam"
"""
import os

from common import ROOT, run


def append(path, rule):
    rule = (rule or "").strip()
    if not rule or "\n" in rule or len(rule) > 300:
        return False
    text = open(path).read() if os.path.exists(path) else "# Learned rules\n"
    existing = {l[2:].strip().lower() for l in text.splitlines() if l.startswith("- ")}
    if rule.lower() in existing:
        return False
    with open(path, "w") as fh:
        fh.write(text.rstrip("\n") + f"\n- {rule}\n")
    return True


def main(argv):
    if len(argv) != 2 or argv[0] != "add":
        print(__doc__)
        return 2
    print("added" if append(os.path.join(ROOT, "rules.md"), argv[1]) else "skipped")
    return 0


if __name__ == "__main__":
    run(main)
