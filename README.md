# Productivity Dashboard

A distraction-free productivity station for a dedicated Raspberry Pi touchscreen. Instead of managing a to-do list, it measures how time is actually spent — via timers, mutually-exclusive stopwatches, and scheduled events — and turns that raw activity into daily/weekly/monthly insight. See `specs/mission.md` for the full mission statement and non-goals, and `specs/roadmap.md` for the phased build-out (Phases 0–3 are complete; Phase 4, an audible alarm, is next).

## Features

- **Timers** — count down toward zero for scheduled sessions (work blocks, meetings, breaks); ring and blink until dismissed when they hit zero.
- **Stopwatches** — count up for open-ended activity tracking. **Work**, **Misc**, **Waste**, **Exercise**, **Shower**, and **Fun** are mutually exclusive: starting one automatically pauses the others, so recorded time never overlaps.
- **Events** — one-shot alarms for a specific clock time (e.g. "Lunch 12pm"); ring and stay dismissed once acknowledged, even across a page refresh.
- **Tasks** — a lightweight, drag-to-reorder checklist alongside the trackers, for quick day-of to-dos (not the project's focus — see "Not a task manager" in `specs/mission.md`).
- **Persistent state** — all cards are backed by SQLite and restored on every backend restart. A same-day restart (e.g. a Pi reboot) preserves everything exactly as it was; state only resets once the calendar date rolls over (see `backend/date_id.txt` below).
- **Google Sheets sync** — the day's events and tasks can be loaded automatically from a Google Sheet at startup, and re-pulled on demand with the sync button in the header. See "Google Sheets sync" below.
- **Kiosk autostart** — on the Pi, the dashboard comes up full-screen with no keyboard, mouse, or login step after a reboot or power cut. See `deploy/README.md`.
- **Planned**: an audible alarm when a timer or event hits zero (Phase 4); full voice control — wake word → speech-to-text → intent → action (Phases 5–6); historical analytics plus the end-of-day upload to Sheets (Phase 7); and dashboard ordering/muting improvements — drag-to-reorder cards, fixed-size cards, mutable timers and events (Phase 8).

## Tech Stack

- **Frontend**: React 18 + TypeScript, built with Vite, styled with Tailwind CSS v4 (Radix/shadcn components going forward). Package manager: `pnpm`.
- **Backend**: FastAPI (Python 3.11) + `uvicorn`, using `tzlocal` for timezone detection.
- **Database**: SQLite via the stdlib `sqlite3` module directly (no ORM) — `tasks`, `events`, `stopwatches`, `timers`, `sheet_sync` tables. The database is the source of truth; in-memory state is rebuilt from it on every boot.
- **Google Sheets**: `gspread` + a service-account credential (no OAuth consent flow), read-only scope.
- **Deployment target**: Raspberry Pi 5 + AI HAT+2 driving a 10-inch touchscreen in kiosk mode.

Full details, including the planned voice-assistant stack, are in `specs/tech-stack.md`.

## Setup & Running

Note: rename date_id_example.txt to date_id.txt

### Option A: Docker Compose (recommended)

```bash
docker compose up
```

This builds and runs both services from `docker-compose.yml`: frontend on `http://localhost:5173`, backend API on `http://localhost:8080`, both bound to `127.0.0.1`.

### Option B: Run manually

**Backend** (from `backend/`):

```bash
pip install -r requirements.txt

# First run only: create date_id.txt with your IANA timezone as the only line.
# `python get_local_timezone.py` prints your local timezone name; see date_id_example.txt for the file format.
echo "America/Chicago" > date_id.txt

uvicorn main:app --reload --port 8080
```

`date_id.txt` is how the backend knows what day it currently is: on every boot, if the stored date doesn't match today, all tables are wiped for a fresh day; if it matches, existing cards are restored untouched.

**Frontend** (from `frontend/`):

```bash
pnpm install
pnpm dev
```

The frontend expects the API at `http://localhost:8080/api` (see `API_ENDPOINT` in `frontend/src/app/App.tsx`); the backend's CORS config expects the frontend at `http://localhost:5173`. Change both together if you need different ports.

### One-time upgrade step (existing installs only)

If you're updating a checkout that already has a `productivity.db` from before Phase 3, **drop the old `events` and `tasks` tables, or delete `productivity.db` outright, before the first run of this version.** There is no migration code by design (see `specs/2026-07-26-phase3-sheets-kiosk/requirements.md` § Schema changes) — the two tables gain `source`/`sheet_key` columns, declared only in `CREATE TABLE IF NOT EXISTS`, so they're created with the new shape only if they don't already exist. Skipping this isn't a sync-only problem: with the old table shape, creating *any* card — including one you make by hand on the dashboard — fails with `sqlite3.OperationalError: table tasks has no column named source`. Do the drop on an empty board, since any cards in those tables at that moment are lost. A fresh checkout with no existing `productivity.db` needs no action.

## Google Sheets sync

The dashboard can load the day's events and tasks from a Google Sheet — once automatically at startup, and again on demand from a button in the header. It's read-only: the dashboard never writes to, or deletes from, the spreadsheet.

### How the sheet is read

- **One tab, named `Day`** (configurable — see `SHEETS_TAB_NAME` below). **One column, column A.** Every non-empty cell is one item.
- **A1 is skipped unconditionally** (reserved for the user's own notes, e.g. a wake-up time).
- **A cell starting with a time is an event** — the time it should ring, then the label, no separator (`1pm sun lunch`, `10pm reflect`, `645am wake up`). **Everything else is a task.**
- **Blank cells are skipped.** A cell that can't be parsed is skipped too (logged with its row number) — it does **not** delete the card from a previous sync.
- **The sheet owns the cards it creates.** Deleting a cell removes the matching card from the dashboard on the next sync; deleting a sheet-created card on the dashboard doesn't stick — the next sync (automatic or manual) recreates it, because the sheet is the source of truth. The fix is always to edit the sheet, not the dashboard. Cards you create by hand on the dashboard are never touched by a sync, no matter what the sheet contains.
- **Timers and stopwatches are never imported or deleted by a sync** — column A only ever produces events and tasks.
- **An event whose time has already passed today is skipped, not created** — editing the time in the sheet to something still upcoming brings it back on the next sync.

### Setting it up

1. Create a Google Cloud service account and download its JSON key. Keep the key file **outside the repo** — it must never be committed.
2. Share the Google Sheet with the service account's email (Viewer access is enough) — find the email with `docker compose run --rm backend python sheets.py --check` once `SHEETS_KEY_FILE_HOST` below is set, or by opening the key JSON directly (`client_email` field).
3. Copy `.env.example` to `.env` and fill in:

   ```
   SHEETS_SYNC_ENABLED=true
   SHEETS_KEY_FILE_HOST=/absolute/path/on/this/host/to/service-account-key.json
   SHEETS_SPREADSHEET_ID=<the long id in the sheet's URL, between /d/ and /edit>
   SHEETS_TAB_NAME=Day
   ```

   `.env` is read by `docker-compose.yml`, which mounts the key file read-only into the backend container; leaving `SHEETS_SYNC_ENABLED` unset or `false` (the default) disables sync entirely and is what every dev machine should run with.
4. `docker compose up` (rebuild first with `docker compose build backend` if you changed `backend/requirements.txt`). Check it's wired up:

   ```bash
   docker compose exec backend python sheets.py --check   # prints the service-account email + spreadsheet title
   docker compose exec backend python sheets.py --dump    # prints every parsed item in column A
   ```

### Using it

The day's events and tasks load automatically once per day, the first time the backend starts that day. To pick up a sheet edit made later the same day — without restarting — tap the sync button in the dashboard's header (hidden when sync is disabled). It's disabled while a sync is in flight, and its color reflects the last attempt's result (also available as its tooltip): green for success, grey for "already synced, nothing to do", red for a failure. A failure (network down, sheet unshared, wrong id/tab) never deletes anything — the dashboard keeps working with local data and logs the problem for the next attempt to retry.

## Running the tests

```bash
cd backend
pip install -r requirements.txt   # includes pytest
python -m pytest tests/ -q
```

Tests run against temporary, isolated SQLite/`date_id.txt` fixtures — they never touch the real `productivity.db`.

## API Reference

All messages are `POST`ed as JSON to `/api` (default `http://localhost:8080/api`); the frontend also logs every outgoing message to the browser console. Every request body is a `Message` (see `backend/classes.py`) — only the fields relevant to `command`/`type` need to be set. Note the label field is **`label`**, not `task`.

### Create

Duration – Timer:
```json
{ "id": 1, "type": "duration", "type_duration": "timer", "label": "AI Project", "current_time": "02:30:00 PM", "total_time": "01:51:00", "command": "create" }
```

Duration – Stopwatch:
```json
{ "id": 2, "type": "duration", "type_duration": "stopwatch", "label": "Work", "current_time": "02:30:00 PM", "command": "create" }
```

Event:
```json
{ "id": 3, "type": "event", "label": "Lunch 12pm", "ring_time": "2026-06-16T17:00:00.000Z", "command": "create" }
```

Task:
```json
{ "id": 4, "type": "task", "label": "Buy milk", "completed": false, "pos": 0, "command": "create" }
```

### Pause / resume (durations only)

```json
{ "id": 1, "type": "duration", "elapsed": "00:10:00", "remaining_time": "01:41:00", "command": "pause" }
```
```json
{ "id": 1, "type": "duration", "current_time": "02:41:00 PM", "command": "resume" }
```

### Edit

```json
{ "id": 1, "type": "duration", "type_duration": "timer", "label": "AI Project", "current_time": "02:45:00 PM", "total_time": "01:00:00", "remaining_time": "01:00:00", "command": "edit" }
```
```json
{ "id": 3, "type": "event", "label": "Lunch", "ring_time": "2026-06-16T18:00:00.000Z", "command": "edit" }
```

Editing an event or a rung timer/stopwatch clears any stale `alerting`/`completed` state — the card starts fresh from the new schedule.

### Complete (tasks and timers)

```json
{ "id": 4, "type": "task", "completed": true, "command": "complete" }
```

### Delete

```json
{ "id": 1, "type": "duration", "elapsed": "01:51:00", "command": "delete" }
```

### Ring / stop_ring

Sent by the frontend when a timer/event's countdown hits zero, and when the user dismisses the resulting alert:

```json
{ "id": 1, "type": "duration", "elapsed": "01:51:00", "command": "ring" }
```
```json
{ "id": 1, "type": "duration", "command": "stop_ring" }
```

`ring` freezes the card (sets `alerting = true` and, for timers/stopwatches, `paused = true`) and persists the frozen elapsed time, so a reload can't silently resume it as still running. `stop_ring` clears `alerting`; for events it also sets `completed = true`, since an event's `ring_time` never moves back into the future — dismissal is the only durable record that the ring was acknowledged.

### Close (shutdown)

```json
{ "command": "close", "current_time": "05:00:00 PM" }
```

Sent once when the app shuts down. It's a no-op on the backend — no cards are deleted on close. Clearing the board for a new day is handled exclusively by the `date_id.txt`-based rollover on the next backend startup, not by shutdown.

### Sync sheets (manual)

```json
{ "command": "sync_sheets" }
```

Sent by the header sync button (see "Google Sheets sync" above). Re-runs the same reconciliation as the automatic startup sync, but bypasses the once-per-day marker. A no-op with `SHEETS_SYNC_ENABLED` unset. Never returns an error status to the HTTP caller — check `sheet_sync` on the next `GET /api` for the outcome.

### GET /api response shape

```json
{
  "last_id": 1007,
  "durations": [
    {
      "id": 1007,
      "label": "Work",
      "subtype": "stopwatch",
      "total_ms": 0,
      "accumulated_ms": 45000,
      "started_at": null,
      "alerting": false
    }
  ],
  "events": [],
  "tasks": [],
  "sheet_sync": { "date": "2026-11-08", "status": "ok", "detail": "created 2, deleted 0, past 1, unparsed 0" }
}
```

Field notes:
- **`id`** — unique numeric identifier; the frontend uses this to track and update the card.
- **`label`** — the name shown on the card, e.g. `"Work"`.
- **`subtype`** (durations only) — `"stopwatch"` or `"timer"`; the frontend treats the two differently.
- **`total_ms`** — countdown target for timers; ignored (always `0`) for stopwatches.
- **`accumulated_ms`** — elapsed time recorded before the current run. If paused, this is the full elapsed time; if running, it's the elapsed time before the current start.
- **`started_at`** — epoch milliseconds when the card was last started/resumed, or `null` if paused. When set, the frontend computes live elapsed time as `accumulated_ms + (now - started_at)`.
- **`alerting`** — whether the card is currently ringing/unacknowledged.
- **`sheet_sync`** — the most recent Sheets sync attempt (startup or manual button), not per-card: `status` is one of `disabled` (sync off), `ok`, `skipped` (already synced today), or `error`; `detail` is a human-readable summary or error message. Drives the sync button's color/tooltip — see "Google Sheets sync" above.
- Every event/task also carries `source` (`"local"` for hand-made cards, `"sheet"` for ones loaded from the spreadsheet) and `sheet_key` (the raw cell text, `null` for local cards). The frontend doesn't currently read either field; they're what a sync diffs against to decide what to create or delete.
