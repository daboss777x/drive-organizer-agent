"""Send the run report to the owner through the Apps Script bridge (MailApp; send only, and the
script refuses any recipient except its REPORT_EMAIL property).

python tools/send_email.py runs/current/report.md
Re-runs the Gate 8 audit itself; if it fails, only a fixed SECURITY ABORT notice is sent.
"""
import os
from email.message import EmailMessage

from common import ROOT, load_config, run, run_dir

ABORT_BODY = ("The Drive agent's post-run security audit failed, so this week's report "
              "contents were withheld and nothing further was sent.\n"
              "Check the routine's session log in Claude Code before the next run.\n")


def build_message(to, subject, body, audit_ok):
    if not to or "@" not in to or to.startswith("<"):
        raise ValueError("report_email not configured")
    m = EmailMessage()
    m["To"] = to
    if audit_ok:
        m["Subject"] = subject
        m.set_content(body)
    else:
        m["Subject"] = "Drive agent: SECURITY ABORT"
        m.set_content(ABORT_BODY)
    return m


def main(argv):  # pragma: no cover - exercised in the live dry run
    import audit
    from google_client import from_env
    if len(argv) != 1:
        print(__doc__)
        return 2
    cfg = load_config()
    client = from_env()
    rd = run_dir()
    ok = audit.check([rd, os.path.join(ROOT, "rules.md"), os.path.join(ROOT, "business_context.md")],
                     client.guard, client.api.get_meta, known_ok=audit.known_ok_ids(client))
    body = open(argv[0], encoding="utf-8").read() if ok else ""
    first = body.splitlines()[0].lstrip("# ").strip() if body else "Drive agent report"
    msg = build_message(cfg["report_email"], first, body, ok)
    client.api.send_mail(msg["To"], msg["Subject"], msg.get_content())
    print("sent" if ok else "sent SECURITY ABORT notice")
    return 0 if ok else 4


if __name__ == "__main__":
    run(main)
