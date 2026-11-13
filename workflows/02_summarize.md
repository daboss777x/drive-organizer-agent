# 02 Screen names, then summarize

```
python tools/state.py todo
```
- Writes `runs/current/to_summarize.json` (files not cached by id + modifiedTime) and
  `runs/current/screen_input.json` (NAMES + paths only, for files the word list didn't already flag).
- If `to_screen` > 0: spawn ONE `screener` subagent with the prompt
  `Screen runs/current/screen_input.json`. Wait for it.
  (If it fails, carry on anyway: every unscreened file is treated as flagged.)
```
python tools/state.py screen
```
- Word-list matches always flag. The AI can only add flags. Flagged files go to
  `runs/current/flagged.json`: they are NOT read, NOT summarized and NOT classified. They
  become "review" rows in the inbox Sheet (05, End of run) and appear in the report.
- Batches in `runs/current/batches/` contain only cleared files. Spawn one `summarizer`
  subagent per batch file, **all in parallel** (one message, many Agent calls). Prompt each
  with just `Summarize runs/current/batches/batch_N.json`.
- When all have replied:
```
python tools/state.py merge
```
- Never read file contents yourself, and never pass a flagged file to a summarizer.
