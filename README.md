# Drive Organizer Agent

An AI agent that tidies your Google Drive once a week, on its own, in the cloud. It reads your
files, decides where each one belongs, and moves, renames or archives it (it never deletes),
then emails you "Here's what I did". One folder you choose is **never** read, moved or named,
and that rule is enforced in code, twice, not just in a prompt.

Built with Claude Code (cloud routines, Sonnet and Haiku), a small Google Apps Script bridge and
plain Python tools, with 327 tests.

## Who it's for

| Who | What it takes off your plate |
|---|---|
| Solo consultants and small agencies | Client files scattered across Drive get gathered into `Clients/<name>` |
| Freelancers and creators | Scripts, thumbnails, exports and "Copy of ..." files sorted and renamed |
| Small business owners | Duplicates archived, loose files filed, without handing an AI your private papers |
| Anyone with a messy Drive | A weekly tidy-up that happens without you, with a log of every change |

## How it creates value

- **Time:** the weekly sort happens without you. You only read a short email and answer at most 5 questions.
- **Fewer mistakes:** every change has a one-line reason and can be undone, one file or a whole run.
- **Privacy you can check:** a forbidden folder blocked in two places, a name screen before any
  file is opened, and an audit after every run before the email goes out.
- **It gets better:** when you move a file it placed, or correct it in `/drive-review`, the next
  run learns from that.

## Features

- Weekly Claude Code cloud routine (or run it by hand), dry-run mode first.
- Name screen before reading: real secrets (IDs, passwords, medical) are never opened or moved;
  other sensitive-looking names are filed by name only, unread.
- Parallel Haiku readers summarise files; Sonnet decides moves, renames, new folders and archives.
- Rule checker in code: no delete, no sharing changes, no moves into unsafe or agent folders, max 5 questions.
- Exact-duplicate detection (checksums / identical text) with automatic archiving of extra copies.
- Decision log and undo log in your Drive (`_DriveAgent/logs/`); undo one file or a whole run.
- `/drive-review` in Claude Code: "where is X?", "why is Y there?", "undo the last run", "zips go in the client folder".
- Learns from your corrections, including files you simply move yourself.
- "Here's what I did" email, grouped by folder, with the reasons.

## How it works

```
 Friday (cron) --> Claude Code routine (cloud) --> clones your private repo
                         |
   1 Learn --> 2 Scan --> 3 Name screen --> 4 Read (Haiku) + decide (Sonnet) --> 5 Rule check
                 |                                                                   |
                 v                                                                   v
        +----------------------+   only via Python tools   +------------------------------+
        |  Apps Script bridge  | <------------------------ | 6 Act (move/rename/archive)  |
        |  ("the hands", runs  |                           | 7 Audit  8 Email  9 Save     |
        |   as you in Google)  |                           +------------------------------+
        +----------+-----------+
                   v
              Your Drive        [ forbidden folder: blocked by the bridge AND by tools/guard.py ]

 You --> /drive-review (Claude Code) --> corrections + rules --> next run learns
```
A hand-drawn version: [`docs/architecture.html`](docs/architecture.html) (open it in a browser).

## Project structure

```
bridge/            Apps Script bridge (Code.gs + appsscript.json) and its Node tests
tools/             Every action the agent can take (the agent may only run these)
workflows/         The recipe the cloud agent follows each run
.claude/           Hooks (bash gate, edit lock), settings (denied connectors), subagents, /drive-review
tests/             Pytest suite against an in-memory fake Drive
config.yaml        Tunables: dry_run, caps, report email
business_context.md, rules.md   Optional guidance; rules are learned from your corrections
docs/              Architecture drawing
```

## Setup

Follow **[SETUP.md](SETUP.md)** step by step (about 45 minutes). In short:
1. Make a **private** copy of this repo, install, run the tests.
2. Put your forbidden folder's ID in `tools/guard.py` and your email in `config.yaml`.
3. Create the Apps Script bridge from `bridge/Code.gs`, set its 3 script properties, run `selfTest`, deploy it as a web app.
4. Smoke test locally, then give Claude access to the repo and create a cloud environment.
5. Create the weekly routine with **no connectors**, do dry runs, review with `/drive-review`, then go live.

Accounts, tools and costs: **[REQUIREMENTS.md](REQUIREMENTS.md)**.

## Customise it

| What | Where |
|---|---|
| The folder that must never be touched | `tools/guard.py` (+ `FORBIDDEN_FOLDER_IDS` in Apps Script) |
| Report address | `config.yaml` `report_email` (+ `REPORT_EMAIL` in Apps Script) |
| Files, actions and questions per run | `config.yaml` (`max_files_per_run`, `max_actions_per_run`, `max_questions_per_run`) |
| Suggested top-level folders | `config.yaml` `categories`, `workflows/03_classify.md` |
| Your clients and projects (optional) | `business_context.md` |
| Standing rules ("zips go to the client folder") | `/drive-review` (saved to `rules.md`) |
| What counts as a sensitive name | `tools/screen.py` (word list), `.claude/agents/screener.md` |
| Schedule | your routine at claude.ai/code/routines |

## Security notes before real use

- **Keep your copy private.** `tools/guard.py` holds your forbidden folder's ID.
- **The bridge URL + secret together give full access to your Drive**, like a login token. Keep
  them only in `.env` (git-ignored) and the cloud environment. If in doubt, make a new secret and
  update both places.
- **Keep sensitive files inside the forbidden folder.** A sensitive file elsewhere with an
  innocent name can't be detected by name.
- **Don't attach Google Drive or Gmail connectors** to the routine. They'd bypass every guard.
- **Start with `dry_run: true`** and read a few reports before going live. Only you should flip it.
- The agent writes its own state, logs and reports in a `_DriveAgent` folder in your Drive.
- Files over about 45 MB can't pass through the bridge; they're filed by name and folder only.
- The classifier can be cautious on some runs and plan fewer moves than expected; check the
  "Here's what I did" email and correct it in `/drive-review`.
- No license is included: you can read the code, but there's no grant to reuse it.

## Credits

- Built with [Claude Code](https://claude.com/claude-code) by Anthropic (cloud routines, subagents, hooks).
- Google [Apps Script](https://developers.google.com/apps-script) and the Drive API v3 advanced service.
- Architecture drawing uses [rough.js](https://roughjs.com).
