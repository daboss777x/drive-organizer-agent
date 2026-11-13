# 06 Report

```
python tools/report.py
python tools/audit.py
```
- `audit.py` prints `ok` or `SECURITY ABORT`.
- Either way, run `python tools/send_email.py runs/current/report.md`. It re-runs the audit
  and, on failure, sends only a fixed SECURITY ABORT notice.
- If the audit passed: `python tools/state.py finish` (moves `scan_since` only after a live, uncapped scan; saves state to Drive).
- If it failed: do NOT run `state.py finish` or `push`. End the session with one line:
  "Security audit failed; report withheld."
