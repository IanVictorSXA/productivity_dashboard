# Requirements — Phase 3: Google Sheets sync (read path) + kiosk autostart

## Source

`specs/roadmap.md` Phase 3:

- **3a.** Service-account auth on the backend: key file stored on-device (never committed), sheet shared with the service account email, authenticated client available to the app
- **3b.** Start-of-day job: load the day's schedule from Sheets into the dashboard
- **3c.** Start-of-day job: load events from Sheets into the dashboard
- **3d.** Handle failure paths (no network, missing/invalid key, sheet unreachable or unshared) without losing local data
- **3e.** Kiosk mode starts automatically on every Pi 5 boot: backend and frontend services come up on their own, and the browser opens the dashboard full-screen with no chrome — no keyboard, mouse, or login step needed. Must survive a power cut, and recover if the browser or a service crashes.
- **3f.** Manual sync control on the dashboard: re-pull today's rows from the sheet on demand, for when the day's agenda is edited after the morning's automatic import. (Added to the roadmap during this spec, at the user's request.)

Mission alignment: Pillar 3 ("Sync runs unattended via a service account, so it never depends on the user being present to re-authorize a login") and the Success Criterion "The device requires near-zero maintenance attention — it restores its own state after power loss/restart and syncs to Sheets unattended."

## Scope

All six items (3a–3f) land on the single branch `phase3-sheets-sync-kiosk` under this one spec folder — confirmed with the user. 3e is host configuration rather than app code, so it touches no files that 3a–3d touch and can be committed independently. 3f is the only frontend change in the phase and comes last, since it is a thin trigger over the import path built in 3b–3d.

**Write path is out of scope.** The end-of-day stats upload is Phase 7 (7a). Everything here is read-only; the service-account credential is requested with a read-only scope so an implementation bug cannot damage the source spreadsheet.

## Sheet shape (user-confirmed)

The user has an **existing spreadsheet** whose layout the backend reads as-is — the schema is not ours to define.

- **One tab, named `Day`.**
- **One column, column A.** Every non-empty cell in it is a single item.
- **Each cell is either an event or a task.** Nothing else — **timers and stopwatches are never imported** from Sheets.
- The sheet is the **source of truth for the items it owns**: a cell removed from column A means the corresponding card is removed from the dashboard (see § Reconciliation).

### Cell grammar (Group 1 — asked and answered 2026-08-01, at the start of Group 4)

Answered by the user and then checked against a read-only dump of the live column A (user-approved), so the rules below describe real cells, not a described format.

- **A1 is the user's wake-up time** (`645am`), not an item. It is skipped unconditionally — `sheets_parse.HEADER_ROWS = 1`. User's words: *"A1 is just the time I should wake up. Ignore it for now at least."*
- **Events come first, in order, and start with the time they should ring** — *"1pm sun lunch"*. Everything after the time is the label; there is no separator character, just whitespace.
- **A cell with no leading time is a task.** That is the whole discriminator.
- **Blank cells appear mid-column** and are skipped without comment. Row numbers are preserved for logging, so a skip message names the sheet row the user can look at.
- **The `Day` tab is today only.** No date filtering.

Time forms, from the real cells plus the near neighbours the parser accepts:

| Cell | Reads as | Ring time |
| --- | --- | --- |
| `1pm sun lunch` | event | 13:00 local |
| `10pm plan, self check, reflect, read` | event | 22:00 local |
| `645am` (A1) | — | skipped as the header row |
| `6:45am gym` | event | 06:45 local |
| `1230pm lunch` | event | 12:30 local |
| `13:30 standup` | event | 13:30 local |
| `bath, bed, timers 8h` | task | — |
| `5, 10, 15 reps` | task | — |
| `check email` | task | — |
| `25pm broken` / `9:75am broken` / `3pm` | skipped | bad hour / bad minute / no label |

**Bold is not used as the discriminator, deliberately.** The user noted events are also always bold, and a `includeGridData` fetch confirms it (A1–A3 bold, A4 onward not). The leading time alone already separates the two types on every real cell, so the parser stays on the cell *text*: text survives a copy-paste that drops formatting, needs no second API call, and keeps the grammar something the user can reason about by reading the sheet. If a bold-but-untimed event ever shows up, that is the moment to revisit this.

**A leading time requires a meridiem or a colon** (`1pm`, `645am`, `13:30`) — a bare `1300` is not read as a time. This is what keeps a task like `bath, bed, timers 8h` or `5, 10, 15 reps` from being turned into an alarm, and it is the reason the discriminator is safe without the bold signal.

**Wall-clock text is resolved against the app's configured timezone** — line 1 of `date_id.txt` (`America/Chicago`), the same source the daily rollover uses — and stored as UTC. `classes.parse_time` is *not* reused for this: it resolves against the process timezone, and the backend container runs UTC, which would have made `1pm` ring at 08:00 local. Cards created in the browser never exposed this, because the frontend sends an already-absolute ISO timestamp.

## Current state (confirmed by reading the code)

- `backend/main.py` builds a single module-level `TaskManager` at import time; `TaskManager.__init__` constructs `Database()` and then `retrieve_data()`. That constructor is the only place the app has a "start of day" moment today.
- `Database.__init__` (`backend/database.py:28`) owns the rollover: it reads `date_id.txt` (line 1 IANA timezone, line 2 last-seen date, line 3 last-used id) and, if the stored date is not today, calls `deleteAll()` — which wipes all four tables and `VACUUM`s — then rewrites the date.
- **The rollover only runs at process startup.** There is no scheduler and no midnight tick; a backend left running across midnight keeps yesterday's cards until it restarts. This is pre-existing behavior, not something Phase 3 introduces.
- Cards are created exclusively through `TaskManager.create(Message)`; `retrieve_data()` reloads DB rows by round-tripping them through `Message.model_validate` and the same `create` path. **A Sheets import should therefore synthesize `Message` objects and call the existing command path — not write SQL directly.**
- Ids come from `db.last_id`, persisted to `date_id.txt` on every INSERT.
- `deleteAll()` deletes *rows*, not tables, so schema changes persist across the daily rollover — and `CREATE TABLE IF NOT EXISTS` will **not** add a new column to an already-existing `events`/`tasks` table. **The user will delete the old `events`/`tasks` tables (or the whole `productivity.db`) by hand before running the new code**, so the new columns are declared in the `CREATE TABLE IF NOT EXISTS` statements only — no migration code is written (user-directed, see § Schema changes).
- `Event.get_ApiEvent()` / `Task.get_ApiTask()` and the `get_tuple_to_save()` INSERTs enumerate columns explicitly, so a new column means touching both sides in `backend/classes.py`.
- The backend's declared dependencies are `fastapi`, `uvicorn`, `tzlocal`, `pytest`, `gspread`, `google-auth`, in `backend/requirements.in`; `backend/requirements.txt` is the pinned file generated from a verified build of that list and is what the image installs (Group 8c — Group 2's wider install of `google-api-python-client` / `google-auth-httplib2` / `google-auth-oauthlib` was trimmed back, the first two being unimported and the third arriving transitively through `gspread` anyway). The service-account key JSON has been downloaded and placed under `backend/` (gitignored). `backend/sheets_config.py` (Group 2, complete) reads the four env vars from environment; `docker-compose.yml` passes them through and mounts the key file read-only. `backend/sheets.py` (Group 3, complete) holds the authenticated read-only client — `get_client()`, `open_worksheet()`, the `SheetsError` exception family, a 15-second request timeout, and a `python sheets.py --check` diagnostic. It is the only consumer of `sheets_config` so far, and **nothing imports it at runtime yet**: `main.py`/`classes.py` are untouched, so with sync disabled (and in the tests) the module is never loaded. `backend/sheets_parse.py` (Group 4, complete) holds the cell grammar as a pure function over a list of strings, plus the `SheetItem`/`SheetRead` shapes the reconciliation diff consumes; `sheets.read_day()` is the one-request column-A read that feeds it, and `python sheets.py --dump` prints the parse for eyeballing against the sheet. Group 4 also added `database.get_timezone()` (line 1 of `date_id.txt`, never raises) so a sheet's wall-clock time resolves in the user's zone rather than the container's UTC.
- `docker-compose.yml` mounts `./backend:/app` and `./frontend:/app` and binds 5173/8080 to `127.0.0.1`. Both services now carry `restart: unless-stopped` (Group 8), and `deploy/productivity-dashboard.service` + `deploy/README.md` hold the systemd unit and its install instructions — **not yet installed on the Pi**; the user runs the install and the reboot/power-cut validation.

## Decisions

### Auth and configuration (3a)

- **Library**: `gspread` + `google-auth`. Rationale: read-only tabular access is a one-liner per worksheet, versus hand-rolling `google-api-python-client` requests. Both are pure-Python wheels and install cleanly on arm64. Declared in `backend/requirements.in`. Since `google-api-python-client` is not used, it is not installed either (Group 8c) — it was carrying 100MB of API discovery documents for nothing.
- **Scope**: `https://www.googleapis.com/auth/spreadsheets.readonly` only. Phase 7 widens it when the write path arrives.
- **Key file**: JSON service-account key lives on the Pi outside the repo, mounted read-only into the backend container. Path comes from the `SHEETS_KEY_FILE` env var. The path is **never** hardcoded to a repo-relative location and the file is added to `.gitignore` defensively.
- **Config surface** — all env vars, read once at startup:
  - `SHEETS_SYNC_ENABLED` (default `false`) — master switch, so a dev machine without a key file behaves exactly as it does today.
  - `SHEETS_KEY_FILE` — absolute path to the mounted JSON key.
  - `SHEETS_SPREADSHEET_ID` — the spreadsheet's id.
  - Tab names — final var names deferred until the layout is supplied.
- **Sharing**: the spreadsheet must be shared with the service account's `client_email` (Viewer is sufficient given the read-only scope). Unshared ⇒ every request 403s; this is called out in the failure matrix rather than worked around.

### Import behavior (3b, 3c)

Roadmap wording predates the confirmed sheet shape: **3b ("the day's schedule") is the tasks in column A, and 3c is the events in the same column.** They are one parsing pass over one column, split into two groups only by which card type each cell produces.

- **Automatic trigger**: day rollover + backend startup (user-confirmed). Concretely: the sync runs during `TaskManager.__init__`, after `retrieve_data()`, whenever today's sync has not already been recorded as done. That covers a normal boot, a power cut at 09:00 followed by a restart, and a same-day restart (which is a no-op). The manual control (3f, below) is the second entry point into the same code.
- **Cards are created through `Message` + `TaskManager.create`**, and removed through the existing `delete` command path — reusing id allocation, persistence, and validation as-is. No new insert or delete SQL.
- **Sync marker**: a `sheet_sync` table (`date TEXT PRIMARY KEY`, `status TEXT`, `detail TEXT`, `synced_at TEXT`), deliberately **not** added to `Database.tables`, so the daily `deleteAll()` does not wipe it — the marker for a given date must outlive the card wipe that happens on the next rollover. A successful sync writes the row for today; startup checks for it before syncing.
- **Failed syncs do not mark the day done**, so the next restart retries. A day that fails all day stays retryable all day.
- **Malformed cells are skipped individually**, not fatal: one unparseable cell does not abort the other 20. Skipped cells are logged with their row number, and — importantly — an unparseable cell is **not** treated as a deletion (see below).

### Reconciliation: the sheet owns the cards it created

The user's requirement: *"If I delete an event or task in Google Sheet, it should be deleted here on the dashboard as well."* So a sync is a **diff against column A**, not an append.

- **Provenance is tracked.** Cards get a `source` column (`'local'` default, `'sheet'` for imported ones) plus the raw cell text as the match key. Only `source = 'sheet'` cards are eligible for sync-driven deletion — **a card the user created by hand on the dashboard is never touched by a sync**, no matter what column A says.
- **The diff, per sync run:**
  - Cell present in column A, no matching sheet-origin card ⇒ **create** the card.
  - Cell present, matching sheet-origin card exists ⇒ **leave it completely alone** (see next bullet).
  - Sheet-origin card whose cell is **no longer in column A** ⇒ **delete** the card (existing `delete` command, which sets `deleted = 1`).
- **Existing cards are never mutated in place.** A matched card keeps its completed/alerting/dismissed state — a sync must not un-complete a task the user ticked off or resurrect a dismissed event alarm.
- **An edited cell reads as delete + create**, since the cell text is the match key. The old card goes away and a new one appears. This is the accepted consequence of keying on cell text; it is correct for the events/tasks case because neither type accumulates tracked time.
- **Local deletion of a sheet-origin card does not stick.** Delete a sheet card on the dashboard and the next sync recreates it, because column A still lists it. The fix is to delete the row in the sheet. This follows directly from "the sheet is the source of truth" and is called out here so it isn't reported as a bug. (The once-per-day automatic trigger limits the surprise: within a day, only a manual tap re-creates it.)
- **Deletion only ever happens after a successful, complete read of column A.** Any failure — network, auth, 403/404, timeout — skips the entire diff. A sync that cannot see the sheet must never conclude "everything was deleted."
- **A successfully-read empty column A does delete all sheet-origin cards**, since that is a legitimate "nothing scheduled today." Accepted deliberately; the safeguard is the previous bullet — an empty *read* is distinguished from a *failed* read, and only the former counts.
- **No timers or stopwatches are ever created or deleted by a sync**, regardless of cell content. The six mutex stopwatches and any local timers are entirely outside the sheet's authority.

### Manual sync (3f)

Purpose: the user edits today's agenda in the spreadsheet *after* the morning's automatic sync, and wants those changes on the dashboard without restarting the backend or waiting for tomorrow.

- **Same code, different entry point.** The button calls the exact `sync_day()` built for 3b/3c — one reconciliation implementation, not a second path. The only difference is that the manual call **ignores the "already synced today" marker** (that marker exists to stop the *automatic* trigger from re-running, not to stop the user).
- **Additions and deletions both apply**, per § Reconciliation — that is precisely what the user wants the button for.
- **Transport**: a new command on the existing `POST /api` endpoint (e.g. `command: "sync_sheets"`) handled in `TaskManager.process_command`, rather than a new route — matching the single-endpoint shape the app already has. It returns after the sync so the frontend can refresh state.
- **Failure behavior is identical to the automatic path**: any failure is caught and reported, never crashes the request, and never adds or deletes anything. A failed manual sync returns a non-success status the button can reflect.
- **UI**: one control in the dashboard header area, Radix/shadcn per tech-stack (no new MUI). Minimum states: idle, in-progress (disabled while the request is out, so a double-tap can't fire two imports), and last-result feedback drawn from the `sheet_sync` status. Hidden or disabled when `SHEETS_SYNC_ENABLED` is false, so a dev machine doesn't show a dead button.

### Schema changes

- **`events` and `tasks`** each gain: `source TEXT DEFAULT 'local'` and `sheet_key TEXT` (the raw cell text used as the diff key). `stopwatches` and `timers` are untouched — they are never sheet-owned.
- Declared **only** in the `CREATE TABLE IF NOT EXISTS` statements in `Database.__init__`. **No migration code** — no `ALTER TABLE`, no `PRAGMA table_info` check. User-directed decision: the user drops the old `events`/`tasks` tables on the Pi themselves, so the tables are recreated with the new shape on the next start. The trade-off, accepted knowingly: **any cards in those tables at that moment are lost**, and a stale `productivity.db` that was *not* dropped fails at the first sync rather than silently working (see § Failure paths). Do the drop while the board is empty — e.g. right after a daily rollover — so nothing of value is discarded.
- `Message`, the `Task`/`Event` constructors, `get_tuple_to_save()`, and `get_ApiTask()`/`get_ApiEvent()` all carry the two fields through, so a reloaded card keeps its provenance across a restart — otherwise sheet-origin cards become undeletable-by-sync after every reboot.
- A new `sheet_sync` table, excluded from `Database.tables` (see § Import behavior).

### Failure paths (3d)

The controlling rule: **a Sheets failure must never degrade the local dashboard.** The app boots, restores local state, and serves normally whether or not Sheets is reachable. Every failure below is caught, logged once with a clear message, and leaves local data untouched — in particular **no failure may delete a card**, since deletion is now part of a successful sync:

| Failure | Behavior |
|---|---|
| `SHEETS_SYNC_ENABLED` false / unset | Sync skipped silently. Today's default on any dev machine. |
| Key file missing or unreadable | Log, skip sync, app starts normally. |
| Key file present but malformed/not a service account | Log, skip sync, app starts normally. |
| No network / DNS failure / timeout | Log, skip sync (no creates, **no deletes**), day not marked done (retry on next restart). |
| Sheet not shared with the service account (403) | Log with the service-account email and the "share the sheet with this address" hint, skip sync. |
| Spreadsheet wrong / `Day` tab missing (404) | Log the id or tab name that failed, skip sync. |
| Partial or truncated read of column A | Treat as failure, skip the whole diff — a partial read would look like mass deletion. |
| Individual cell unparseable | Skip that cell, sync the rest, log the row number — and treat the cell's existing card as **still present**, never as deleted. |
| Old `events`/`tasks` tables not dropped before the upgrade (no `source`/`sheet_key` columns) | Not a runtime failure path to design around — the drop is a manual prerequisite. It surfaces as a plain `sqlite3.OperationalError: no such column`, caught by the same guard as any other sync failure: logged, sync skipped, **nothing deleted**, app starts normally. The fix is to drop the tables. |

- **Network calls get an explicit timeout** so a black-holed connection cannot hang backend startup indefinitely. The import is wrapped so that, worst case, startup proceeds without it.
- **Status is exposed on `GET /api`** as a small `sheet_sync` object (date, status, detail) so the failure is diagnosable without SSH-ing into the Pi to read logs. The manual sync button (3f) is the only consumer of this field in this phase — it uses it for last-result feedback. No other UI rendering of sync state is in scope.

### Kiosk autostart (3e)

- **Services**: `restart: unless-stopped` on both compose services, plus a system-level systemd unit running `docker compose up` at boot with `Restart=on-failure` and a dependency on `docker.service`. Two layers because compose's restart policy handles a crashed container while the systemd unit handles the machine coming up cold after a power cut.
- **Browser**: Chromium in `--kiosk` launched by the desktop session's autostart. **Autologin is already enabled on the Pi** (user-confirmed), so it is a precondition to verify during validation, not a setup step this phase performs. Chromium is launched via a small wrapper script that relaunches it if it exits, giving browser-crash recovery.
- **Phase 4 forward-compat**: `--autoplay-policy=no-user-gesture-required` goes on the Chromium command line now, while the flags are being written, so the alarm sound phase doesn't have to revisit host config. This is the one deliberate look-ahead in the phase.
- **Backend readiness**: the browser must not load before the backend is serving; the wrapper waits for the dashboard URL to respond rather than racing it.
- **Host config is documented, not committed as live system files.** Unit files and the autostart entry go into a `deploy/` directory in the repo with exact install commands in the README; the agent cannot install them into a running Pi's systemd from here, and the user runs the install steps.

### Testing

- **No automated tests are added** — per standing guidance (CLAUDE.md §1) and user confirmation for this spec. The existing backend test suite must still pass unmodified; validation is the manual walkthrough in `validation.md`, run on the Pi against the real sheet.

## Non-goals

- No end-of-day / write path to Sheets (Phase 7, 7a).
- No OAuth user-consent flow, no refresh-token handling, no interactive login.
- No stats, analytics, or charts (Phase 7).
- No alarm sound (Phase 4) — only the Chromium autoplay flag is set in advance.
- No UI redesign and no new dashboard controls **other than the single manual sync button** (3f); no other visual rendering of sync status.
- No automatic mid-day polling or background re-sync — mid-day updates are user-initiated via the 3f button only.
- No **write-back**: the dashboard never edits, appends to, or deletes from the spreadsheet. Reconciliation is one-way (sheet → dashboard); completing a task on the dashboard does not tick anything in the sheet.
- No sheet authority over timers or stopwatches — column A only ever produces events and tasks.
- No sync-driven mutation of an existing card's state (label, time, completed, alerting); the diff only creates and deletes.
- No local tombstones: deleting a sheet-origin card on the dashboard does not prevent the next sync from recreating it (documented in § Reconciliation).
- No ORM; no change to the `sqlite3` + hand-written SQL approach.
- **No schema-migration code** — no `ALTER TABLE`, no `PRAGMA table_info` check, no version table. The user drops the old `events`/`tasks` tables manually (user-directed); the new columns live only in the `CREATE TABLE IF NOT EXISTS` statements.
- No fix for the pre-existing "rollover only happens at process startup" gap — noted above, out of scope here.
- No autologin setup work — already enabled on the Pi; validation only confirms it still holds.
