---
name: drive-review
description: Talk through the Drive agent's latest run with the owner. Show what it did, answer "where is X / why is Y there", apply his corrections and answers, and save rules so the next run decides better. Use when the owner types /drive-review or asks about, corrects or gives feedback on the Drive organizer.
---

# /drive-review

The weekly run acts on its own and logs every decision. This is where the owner reviews it, in plain
words, without a spreadsheet. Everything goes through `tools/review.py`, which uses the guard; never
touch Drive any other way, and never read `.env` (the script loads it itself).

## Start
Run `.venv/bin/python tools/review.py summary` and show it briefly: the last run's changes grouped
by folder (counts first, then the files), then the open questions, numbered.

## Then follow the owner's lead
| He says | You run |
|---|---|
| "where is X?" / "why is X in Y?" | `review.py find "X"`, then answer from the log's reason |
| "put X back" / "undo X" | `review.py undo "X"` |
| "undo the last run" / "undo the run on <date>" | confirm once ("this puts N files back"), then `review.py undo-run [YYYY-MM-DD]` |
| "X belongs in Clients/Acme" | `review.py move "X" "Clients/Acme"` |
| a general preference ("zips go to the client folder", "never archive scripts") | `review.py feedback "<the rule, one line, no file IDs>"` |
| an answer to question n | `review.py answer n "<his words>"` |

- If `review.py` says "Which one?", show the choices and ask. Don't guess.
- After two or three corrections that share a pattern, propose one general rule and save it with
  `feedback` once he agrees. Rules and corrections are what the next run's classifier learns from.
- `undo` / `move` change his real Drive right away (even while the weekly run is in dry-run mode).
  They're what he asked for, so just do them and confirm in one line.
- `undo-run` leaves alone any file the owner moved or renamed since the run, and lists them. Folders the
  run created stay (nothing is ever deleted); mention how many may now be empty.
- Moves into the forbidden folder are refused by the guard. Say so plainly; don't retry.
- Never print file IDs. Names and folders only.

## Finish
One line: what changed and which rules were saved. The next run picks it all up automatically.
