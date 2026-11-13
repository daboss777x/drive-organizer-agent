# 01 Scan

```
python tools/drive_scan.py
```
- Lists files changed since `scan_since` (until a live, uncapped scan has covered the whole Drive: every file, newest first, capped at `max_files_per_run`).
- Writes `runs/current/candidates.json`. Protected files appear only as `blocked_count`.
- Skips files already placed by the agent and unchanged since.
- If it prints `refused: protected file` or any `error:` → stop the run and go to 06 (report).
