# 05 Feedback (no Sheet: The owner reviews in /drive-review)

The Google Sheet inbox is retired. The owner answers questions and corrects the agent in Claude Code
with `/drive-review`; that writes feedback and rules into the agent's state and `rules.md`.

## Start of run
```
python tools/state.py learn              # files the owner moved after the agent placed them -> corrections.json
python tools/review.py export-feedback   # his /drive-review corrections, answers and rules -> feedback.json
```
- `corrections.json` and `feedback.json` are precedent for 03 Classify: learn from them.
- An answered question in `feedback.json` (e.g. "yes, archive it") is the owner's decision: plan it
  with `"source": "owner"`.
- If a correction shows a general pattern, add ONE rule: `python tools/rules.py add "<pattern -> folder>"`.
  Rules describe patterns (client names, file types); never paste file IDs.

## End of run (after 04 Execute)
```
python tools/review.py save-questions    # the few `ask` items (max 5) -> state, shown in /drive-review
```
