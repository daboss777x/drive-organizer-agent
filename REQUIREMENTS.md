# Requirements

## Accounts and platforms

| Platform | What it's for | Plan needed | Sign up |
|---|---|---|---|
| Google account | The Drive being organised; runs the Apps Script bridge; sends the report email | Free personal account works (Workspace too) | [accounts.google.com](https://accounts.google.com) |
| Claude (Anthropic) | Claude Code on the web: the weekly cloud routine, Sonnet and Haiku, `/drive-review` | A plan that includes Claude Code on the web and routines (check current plans) | [claude.ai](https://claude.ai) |
| GitHub | Holds your **private** copy; the routine clones it each run | Free | [github.com](https://github.com) |
| Claude GitHub app | Lets claude.ai/code see your private repo | Free | [github.com/settings/installations](https://github.com/settings/installations) |

No Google Cloud project, OAuth consent screen or server is needed.

## Local tools

| Tool | Version | Why |
|---|---|---|
| Python | 3.11 or newer (built on 3.13) | The tools, tests, local smoke test and `/drive-review` |
| git | any recent | Your private copy |
| Node.js | 18 or newer (optional) | Runs the Apps Script bridge's tests (`bridge/code.test.js`), also run by pytest |
| Claude Code (CLI, desktop or VS Code) | current | `/schedule` to create the routine, `/drive-review` |

## Languages

- **Python** for every action the agent can take (`tools/`).
- **Google Apps Script** (JavaScript, V8 runtime) for the bridge (`bridge/Code.gs`).

## Python packages (`requirements.txt`)

| Package | Version | Purpose |
|---|---|---|
| pypdf | >= 5.0 | Extract text from PDFs before summarising |
| python-docx | >= 1.1 | Extract text from Word files |
| pyyaml | >= 6.0 | Read `config.yaml` |
| pytest | >= 8.0 | Test suite |

The cloud environment's setup script installs the same list (see SETUP.md step 9).

## Apps Script services

| Service | Purpose |
|---|---|
| Drive API v3 (advanced service) | List, read, move, rename files (declared in `bridge/appsscript.json`) |
| MailApp | Send the report, only to `REPORT_EMAIL` |
| UrlFetchApp | Export Google Docs/Sheets/Slides as text, download small files |
| PropertiesService | Reads `SECRET`, `FORBIDDEN_FOLDER_IDS`, `REPORT_EMAIL` |

## Environment variables and settings

| Name | Where | Used by | Where to get it |
|---|---|---|---|
| `DRIVE_BRIDGE_URL` | `.env` (local) and the cloud environment | `tools/bridge.py` | Apps Script → Deploy → Web app URL (ends in `/exec`) |
| `DRIVE_BRIDGE_SECRET` | `.env` and the cloud environment | `tools/bridge.py`; also switches on the bash gate | You make it (SETUP.md step 5) |
| `SECRET` | Apps Script script property | `bridge/Code.gs` | Same value as `DRIVE_BRIDGE_SECRET` |
| `FORBIDDEN_FOLDER_IDS` | Apps Script script property | Bridge's own guard | Your forbidden folder's ID (bare ID only) |
| `REPORT_EMAIL` | Apps Script script property | Bridge's mail guard | Same as `report_email` in `config.yaml` |
| `SSL_CERT_FILE` | local, optional | Python on macOS | `/etc/ssl/cert.pem` if you get `URLError` |

## Running costs (rough, check current pricing)

- **Google Apps Script:** free, within Google's daily quotas (a weekly run uses a small fraction).
- **Claude:** each run is a Claude Code cloud session (Sonnet decides, Haiku screens and
  summarises). It counts toward your Claude plan's usage. The first runs read the most files;
  later runs mostly use cached summaries and only read new or changed files.
- **GitHub:** free for a private repo.
