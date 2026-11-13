# Setup guide

Set up your own weekly Drive organizer from scratch. It takes about 45 minutes the first time.
Do the steps in order. Every command is run from the project folder unless it says otherwise.

You'll need: a Google account (the Drive you want organised), a Claude account with Claude Code
on the web (claude.ai/code) and routines, a GitHub account, Python 3.11+ and git on your computer.
Details and costs: [REQUIREMENTS.md](REQUIREMENTS.md).

---

## 1. Get your own private copy of the code

Your copy will hold your forbidden folder's ID, so keep it **private**.

```bash
git clone https://github.com/daboss777x/drive-organizer-agent.git
cd drive-organizer-agent
rm -rf .git && git init -b main      # start your own history
```
Create an empty **private** repository on GitHub (for example `my-drive-agent`), then:
```bash
git add -A && git commit -m "My Drive organizer"
git remote add origin https://github.com/<you>/my-drive-agent.git
git push -u origin main
```

## 2. Install and run the tests locally

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/pytest            # all tests should pass (the Apps Script tests also need Node 18+)
```
The tests use a fake, in-memory Drive. Nothing touches Google yet.

## 3. Choose your forbidden folder

This is the one folder the agent must **never** read, move or even name (IDs, tax papers,
anything private). Put everything sensitive inside it.

1. Open the folder in Google Drive. The URL looks like `https://drive.google.com/drive/folders/1AbCdEf...`
2. Copy the ID: the part after `/folders/`, up to any `?`. Only letters, digits, `-` and `_`.
3. In `tools/guard.py`, replace the placeholder:
   ```python
   FORBIDDEN_FOLDER_IDS = {"1AbCdEf..."}     # your ID, in quotes, inside { }
   ```
   (Claude Code is blocked from editing this file by a hook. Edit it yourself.)

## 4. Set your report email

In `config.yaml`, set `report_email` to the address that should get the weekly report.
Leave `dry_run: true` for now.

## 5. Make a secret

In your own terminal (not in a Claude session):
```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```
Keep it somewhere safe. You'll paste it twice: into Apps Script (step 6) and into the cloud
environment (step 9). Never paste it into a chat.

## 6. Create the Apps Script bridge (the "hands" inside your Drive)

Claude never talks to your Drive directly. A small Google Apps Script, running as you inside
Google, does the work and refuses anything inside the forbidden folder on its own. The code is in
[`bridge/Code.gs`](bridge/Code.gs) and its settings file is [`bridge/appsscript.json`](bridge/appsscript.json).

1. Go to [script.google.com](https://script.google.com) → **New project**. Name it, e.g. "Drive Agent Bridge".
2. Delete the sample code in `Code.gs` and paste in **all** of `bridge/Code.gs`. Save (Cmd/Ctrl+S).
3. Turn on the Drive API, either way:
   - **Project Settings (⚙)** → tick **Show "appsscript.json" manifest file in editor**, open
     `appsscript.json` in the editor and replace its content with `bridge/appsscript.json`; or
   - **Services (+)** in the left sidebar → **Drive API** → version **v3** → **Add**.
4. **Project Settings (⚙) → Script properties → Add script property**, three times:

   | Property | Value |
   |---|---|
   | `SECRET` | the secret from step 5 |
   | `FORBIDDEN_FOLDER_IDS` | your folder ID from step 3: **just the ID**, no quotes, no `{ }`, no URL (several: comma-separated) |
   | `REPORT_EMAIL` | the same address as `report_email` in `config.yaml` |

5. In the editor, pick **`selfTest`** in the function menu → **Run**. Google asks for permission:
   **Advanced → Go to Drive Agent Bridge (unsafe) → Allow**. It's your own script.
   The execution log must show **five `true` lines**, including `forbidden IDs well-formed: true`.
6. **Deploy → New deployment → ⚙ Web app**: Execute as **Me**, Who has access **Anyone** → **Deploy**.
   Copy the **Web app URL** (ends in `/exec`). "Anyone" is fine: every request needs the secret.

> **Updating the code later:** always use **Deploy → Manage deployments → ✏️ Edit → Version:
> New version → Deploy**. "New deployment" creates a *new* URL, and your old URL keeps running
> the old code.

## 7. Smoke test from your computer

Create `.env` in the project folder (it's git-ignored; never commit it):
```bash
DRIVE_BRIDGE_URL=https://script.google.com/macros/s/.../exec
DRIVE_BRIDGE_SECRET=the-secret-from-step-5
```
Then:
```bash
set -a && . ./.env && set +a
.venv/bin/python tools/drive_scan.py --dry --limit 5
```
Expected: up to 5 file names and a line like `candidates=5 blocked_count=N`. Nothing from the
forbidden folder may appear. `--dry` writes nothing.

On macOS, if you see `error: URLError`, your Python can't find certificates. Add
`export SSL_CERT_FILE=/etc/ssl/cert.pem` and try again.

## 8. Give Claude access to your repository

1. Go to [github.com/settings/installations](https://github.com/settings/installations) → **Claude** → **Configure**.
2. Under repository access, add your private repo → **Save**.
3. Refresh [claude.ai/code](https://claude.ai/code). Your repo should now be selectable.

## 9. Create the cloud environment

On claude.ai/code, select your repo, open the environment selector next to it → **Add environment**:

| Field | Value |
|---|---|
| Name | e.g. `Drive Agent` |
| Network access | **Custom**, only: `script.google.com`, `script.googleusercontent.com`, `pypi.org`, `files.pythonhosted.org` |
| Environment variables | the two lines from your `.env` (`DRIVE_BRIDGE_URL=...`, `DRIVE_BRIDGE_SECRET=...`) |
| Setup script | `pip install "pypdf>=5.0" "python-docx>=1.1" "pyyaml>=6.0" "pytest>=8.0"` |

Save it. (The setup script lists packages directly because it doesn't run inside the repo folder,
so `-r requirements.txt` would fail. Keep it in step with `requirements.txt`.)

## 10. Create the weekly routine

In Claude Code (in this project), type `/schedule` and ask for:
- **Schedule:** weekly, e.g. Fridays 18:00 in your time zone (it converts to UTC cron).
- **Repository:** your private repo. **Environment:** the one from step 9.
- **Model:** Sonnet.
- **Prompt:** `Run the weekly Drive organizer per CLAUDE.md.`
- **Connectors: none.** Ask for no connectors, so Google Drive/Gmail connectors are not attached
  (they would bypass every guard; they're also denied in `.claude/settings.json`).
- **Tools:** Bash, Read, Write, Edit, Glob, Grep, Agent.

You can also create it at [claude.ai/code/routines](https://claude.ai/code/routines).
Tip: pause the schedule until you've reviewed a few dry runs, and start runs by hand.

## 11. Dry runs

Start the routine by hand ("run now"). With `dry_run: true` it scans up to 150 files, plans, and
emails you **"Here's what I would do"**, without changing anything. Read the email.

Review and correct it in Claude Code, in this project:
```
/drive-review
```
Ask "where did X go?", "why is Y in Content?", say "zip files go in the client folder", answer its
questions. That becomes feedback the next run learns from. (`/drive-review` reads your `.env`
itself; the values are never printed.)

## 12. Go live

1. In `config.yaml`, set `dry_run: false` **yourself**, then commit and push (the cloud reads the
   config from GitHub).
2. Start a run. You'll get **"Here's what I did"**.
3. Prove undo works: in `/drive-review`, undo one file, or say **"undo the last run"**.
4. Happy? Turn the weekly schedule on.

---

## Troubleshooting

| You see | It means | Fix |
|---|---|---|
| `BridgeError(unauthorized)` | Secret mismatch | `SECRET` (Apps Script) and `DRIVE_BRIDGE_SECRET` must be identical |
| `BridgeError(bad_config)` | `FORBIDDEN_FOLDER_IDS` isn't a bare ID | Remove quotes, `{ }`, URLs, spaces |
| `BridgeError(bad_response)` | The URL isn't returning the bridge's JSON | Use the `/exec` URL of the deployment, not `/dev` |
| `BridgeError(guard_unavailable)` | A Drive lookup failed mid-check | Usually temporary; run again |
| `BridgeError(incomplete_listing)` | Drive cut a search short | Run again |
| New code "doesn't take effect" | You made a new deployment | Manage deployments → Edit → New version on the original one |
| `refused: protected file` (exit 3) | Something touched the forbidden folder | Working as designed: the run stops and only a count is reported |
| `URLError` locally on macOS | Python can't find certificates | `export SSL_CERT_FILE=/etc/ssl/cert.pem` |
| Setup script fails: `requirements.txt` not found | Setup script runs outside the repo | Use the package list from step 9 |
