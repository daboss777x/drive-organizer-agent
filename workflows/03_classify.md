# 03 Classify (you, Sonnet: the decision maker)

```
python tools/dedupe.py
python tools/state.py digest
```
Read `runs/current/classify_input.json`, `runs/current/duplicates.json`, `rules.md`,
`business_context.md` (may be a bare template: that's fine) and, if they exist,
`runs/current/corrections.json` and `runs/current/feedback.json`. Write `runs/current/plan.json`:

```json
{"items": [
  {"id": "...", "action": "move|rename|archive|dedupe_archive|keep|ask",
   "target_folder": "Acme Studio/Clients/Kenya/Northbeam Events/Photos", "new_name": "optional, see Renames",
   "keep_id": "...", "reason": "one line", "confidence": 0.0}
]}
```

The owner's verdict on earlier runs: **"it isn't moving enough files."** Keeping 90% of files where they
are is a failure, not caution. Your job is to make the Drive *well organised*, not to leave it as
you found it. Every move and rename is logged and undoable, so act.

## Step A: design the target structure (before any file decision)
Read `runs/current/folders.json` (every folder path in the Drive with its file count: the whole
Drive, not just this run's files) and `runs/current/structure.md` (the map earlier runs designed;
may be empty on the first run).

Write `runs/current/structure.md`: the target folder tree for the WHOLE Drive, one path per line
with a short note, e.g.
```
Acme Studio/Clients/<Country>/<Client>/            one folder per client
Acme Studio/Clients/<Country>/<Client>/Photos/      shoots and raw photos for that client
Acme Studio/Marketing/Ad Designs/<Campaign or month>/
Personal/
```
- **Build on the owner's existing main folders** (e.g. a business folder that already holds most
  client work). Don't invent a parallel tree next to it.
- **Merge near-duplicates**: folders that mean the same thing (`Acme Studio` vs `Acme Operations`,
  `Scripts` in two places, `Clients` at two levels) become ONE folder in the map; move the files from
  the other into it.
- **Split dumping grounds**: a folder with more than ~25 loose files of mixed kinds gets subfolders
  (by client, campaign, project, type or year). Numbered series (Ad1…Ad71) stay together but go in
  their own subfolder.
- **Nothing important lives loose in My Drive's root** or in vague folders (`New folder`, `Misc`,
  `Stuff`, `Downloads`, `Untitled folder`).
- If `structure.md` already has a map, **keep to it** and only extend it (new clients/projects);
  don't redesign it every week.

Then run:
```
python tools/state.py save-structure
```

## Step B: decide EVERY file against the map
- Read ALL of `classify_input.json` in chunks (offset/limit) until the end, and write one item for
  **every** id: move, rename, archive, dedupe_archive, keep or ask.
- **`keep` only if the file is already where `structure.md` says it belongs AND its name is fine.**
  "It's in a sensible-ish place" is not enough. Root-level files are never kept.
- Never fall back to "be conservative". An empty `business_context.md` is not a reason to skip files.

### How to place files
- **Precedent first.** `rules.md` wins over your own judgement. `corrections.json` lists files you
  placed that the owner moved afterwards ("agent put X in A, the owner moved it to B"): learn the pattern and
  apply it to similar files. `feedback.json` holds the owner's own words from `/drive-review`.
- **Gather by client/project.** Anything that belongs to one client, company or project goes into
  that client's folder (with a subfolder if useful), wherever it sits today. Use the name, the path,
  the summary and the neighbouring files.
- **Files you couldn't read** (images, videos, zips, `kind: metadata`, and `unread: true` files the
  name screen flagged): decide from name, folder and neighbours. Low read-confidence is not a reason
  to keep or to ask.
- Never target `_DriveAgent`, and never `move` into `Archive` (use `archive`).

### Renames
- Rename **broken** names (`Untitled*`, `Copy of *`, `* (1)`, numeric junk) and **unclear** names
  (camera/phone/AI defaults: `IMG-20240814-WA0009.jpg`, `DSC_2038.jpg`, `5K2A5533.JPG`,
  `WhatsApp Image …`, `Screenshot …`, anything with a UUID like `Generate a shot 3f73…png`).
- New name: `<Client or topic> - <what it is> - <date or number>.<same extension>`, e.g.
  `Northbeam Events - event photo - 2024-08-14 - 03.jpg`. Use the modified date if nothing better.
  Keep the extension. Never reuse a camera/UUID pattern in the new name.
- Leave meaningful names alone (the validator rejects renaming them).
- **Moving AND renaming one file:** use `"action": "move"` with both `target_folder` and `new_name`.
  It's one action and undoes as one.
- `unread: true` files may be renamed only from their name, folder and neighbours: say what they
  are by where they sit ("Northbeam Events - photo - 2024-08-14"), never guess at content.

### Archive, duplicates, questions
- **archive** files that are clearly of no use (junk exports, blank copies, empty templates, old temp
  files). Business-looking files (contracts, invoices, proposals, client work, finance) are moved,
  not archived; an archive of one becomes a question.
- **dedupe_archive** every non-first id in a `duplicates.json` group (`keep_id` = first id).
- Staleness alone is never a reason to archive.
- **ask** only when genuinely unclear **and** getting it wrong would matter. At most 5 a run; extra
  asks are dropped. Prefer the best move and say why.
- **Every item needs a specific one-line `reason`** ("Northbeam Events shoot photo, joins the client's
  Photos folder"). It's shown in the decision log and in `/drive-review`.

### Check yourself before validating
Count your actions. If fewer than half of the files get a move or rename, re-read the map and the
`keep` items: most of those should move or get a clear name. Then validate.

Also write `runs/current/context_proposals.md`: bullet suggestions for `business_context.md`
(new clients/projects you noticed). Do not edit `business_context.md` yourself.

```
python tools/validate_plan.py
```
If it prints `missing=N` with N > 0, add a decision for each missing id (listed in
`runs/current/validated_plan.json` under `missing`) to `plan.json` and run it again. Only go on
to 04 Execute when `missing=0`.
If it prints `rejected=N` with N > 0, read each item's `rejected_because` in `validated_plan.json`
and fix it (e.g. a move whose `new_name` was refused: drop the `new_name` and keep the move), then
validate again. Don't let a good move be lost to a bad rename.
The validator enforces the hard rules in code (forbidden folder, unsafe targets, broken-name
or unclear-name renames, unread files move/rename only, real-secret files untouched, max 5 questions).
