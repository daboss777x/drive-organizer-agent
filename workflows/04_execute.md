# 04 Execute

```
python tools/execute.py runs/current/validated_plan.json --answers runs/current/validated_answers.json
```
- With `dry_run: true` (config.yaml) nothing changes; actions are marked `proposed`.
- Otherwise applies up to `max_actions_per_run`, re-checking the guard before each action,
  and writes the undo log to `runs/current/undo_log.json` and `_DriveAgent/logs/`.
- Exit 3 (`refused: protected file`) → stop. Go straight to 06; the audit will decide what to send.
- Never edit `config.yaml` to change `dry_run`. Only the owner flips it.
- Every decision (done, or proposed in a dry run) is written to the **decision log**:
  `state.json` → `history` (from → to, action, reason, confidence) and `_DriveAgent/logs/decisions_<stamp>.json`.
  `/drive-review` uses it to answer "where is X / why is it there". Refused files never appear in it.
- Done moves are remembered in `placed_to`. Next run, `python tools/state.py learn` spots files the owner
  moved somewhere else and writes `runs/current/corrections.json` (examples for classify).
