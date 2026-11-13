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
   "target_folder": "Clients/Northbeam/Contracts", "new_name": "...", "keep_id": "...",
   "reason": "one line", "confidence": 0.0}
]}
```

## How to decide: act on your own judgement
The owner wants the agent to organise his Drive itself, with as few questions as possible.
Every move, rename and archive is logged and undoable, so you don't need permission for them.

- **Precedent first.** `rules.md` wins over your own judgement. `corrections.json` lists files
  you placed that the owner later moved ("agent put X in A, the owner moved it to B"): learn the pattern
  and apply it to similar files. `feedback.json` holds the owner's own words from `/drive-review`.
- **Folders.** Suggested top level: `Clients/<ClientName>/…`, `Business Operations`, `Content`,
  `Learning`, `Personal`, `Finance`. You may create new top-level folders and new subfolders
  when they fit better (e.g. a client, a project, `Claude Skills`). Never target `_DriveAgent`,
  and never `move` into `Archive` (use `archive`).
- **Gather clients.** If several files belong to one client or company, put them together in
  `Clients/<Client>` (with a subfolder if useful), even if they're scattered today.
- **Files you couldn't read** (zips, images, videos, PDFs or Word files with `kind: metadata`,
  and `unread: true` files the name screen flagged): decide from the name, the folder path and
  the files around them. A zip or poster sitting with a client's files, or named after a client,
  goes to that client's folder. A skill or template zip goes with the related project or Content.
  Low read-confidence is not a reason to ask.
- **Name-flagged files (`unread: true`)** may only be moved or renamed, from the name and folder.
  Never archive or ask about them, and don't guess at what's inside.
- **rename** only broken names: `Untitled*`, `Copy of *`, `* (1)`, numeric junk. No naming convention.
- **archive** only files that are clearly of no use (junk exports, blank copies, old temp files).
  Business-looking files (contracts, invoices, proposals, client work, finance) are kept or moved,
  not archived; an archive of one becomes a question.
- **dedupe_archive** every non-first id in a `duplicates.json` group (`keep_id` = first id). No need to ask.
- Staleness (`viewedByMeTime` older than `stale_days`) is never a reason by itself.
- A file already in the right place → `keep`.
- **ask** only when it's genuinely unclear **and** getting it wrong would matter. At most 5 a run;
  extra asks are dropped. Prefer making the best move and saying why.
- **Every item needs a one-line `reason`.** It's shown to the owner in the decision log and in
  `/drive-review` ("why is this here?"), so make it specific: "named after client X, next to
  their other proposals", not "seems right".

Also write `runs/current/context_proposals.md`: bullet suggestions for `business_context.md`
(new clients/projects you noticed). Do not edit `business_context.md` yourself.

```
python tools/validate_plan.py
```
The validator enforces the hard rules in code (forbidden folder, unsafe targets, broken-name
renames, unread files move/rename only, real-secret files untouched, max 5 questions).
