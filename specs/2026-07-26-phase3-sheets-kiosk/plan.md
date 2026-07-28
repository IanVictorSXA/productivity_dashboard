# Plan — Phase 3: Google Sheets sync (read path) + kiosk autostart

Numbered groups are the intended implementation order. Each group should be independently committable and leave the app in a working state (i.e. the dashboard still boots and works with Sheets disabled at every point in the sequence).

Branch: `phase3-sheets-sync-kiosk`.

**Dependency note**: Groups 1–3 and 8–9 are unblocked. Groups 4–7 are blocked on the sheet layout being supplied (Group 1), and Group 10 is blocked on 5–7. Kiosk work (8–9) can be done in parallel or first if the Pi currently needs a manual start each boot.

---

## 1. Capture the cell format — **ask the user when Group 4 starts, not before** (blocks 4–5)

Not code, and deliberately deferred: the user asked to be questioned about the sheet's format at the moment the parsing work begins, so the answers are fresh and concrete rather than guessed at up front.

Already confirmed (in `requirements.md` § Sheet shape): one tab named `Day`, one column (A), every non-empty cell is either an **event** or a **task**, and the sheet owns those cards (deletes propagate). Still to ask, via `AskUserQuestion` at the start of Group 4:

- Spreadsheet id/URL.
- 5–10 real sample cells covering both types and any edge case.
- **How a cell declares event vs. task** — prefix, keyword, presence of a time?
- Event time format inside the cell, and how label and time are separated.
- Whether A1 is a header/title to skip.
- Whether the `Day` tab ever holds days other than today.

**Deliverable**: `requirements.md` § Sheet shape updated with the confirmed cell grammar and worked examples, replacing the open-input checklist. Nothing in Groups 4–5 gets written before this exists.

## 2. Dependencies and configuration plumbing (3a) — **COMPLETE**

- [x] `gspread`, `google-api-python-client`, `google-auth-httplib2`, `google-auth-oauthlib` in `backend/requirements.txt` (superset of the planned `gspread` + `google-auth`; `google-auth` comes in transitively).
- [x] `backend/sheets_config.py`: reads `SHEETS_SYNC_ENABLED` (bool, default `false`), `SHEETS_KEY_FILE`, `SHEETS_SPREADSHEET_ID`, `SHEETS_TAB_NAME` (default `"Day"`, per the already-confirmed sheet shape) from the environment once at import time.
- [x] `docker-compose.yml`: `backend` service gets the four env vars (each with a safe default/empty string) and a read-only bind mount `${SHEETS_KEY_FILE_HOST:-/dev/null}:/run/secrets/sheets_key.json:ro` — the `/dev/null` default means `docker compose up` still boots with no `.env` present; an absent real key file surfaces later as the documented "key file missing/unreadable" failure path (Group 6), not a compose-level error.
- [x] `.gitignore`: already had the actual key filename (`backend/productivity-dashboard-503701-03b014c70abf.json`); added `.env` / `.env.*` (with `!.env.example` un-ignored).
- [x] `.env.example` at the repo root documents all four variables with placeholder values only.

**Verify**: `docker compose config` resolves cleanly with no `.env` present (confirmed). Existing 82 backend tests pass unmodified with `sheets_config` importable but unused by any running code yet (nothing calls into it until Group 3).

## 3. Authenticated Sheets client (3a)

New `backend/sheets.py`:

- `get_client()` — build `google.oauth2.service_account.Credentials` from the key file with the **read-only** scope, authorize `gspread`, return the client. Raises a typed error (not a bare exception) for missing/malformed key.
- `open_worksheet(client, spreadsheet_id, tab_name)` — open the sheet and return the worksheet, with the 403/404 cases distinguished.
- Explicit request timeout so a dead network cannot hang startup.
- A `python -m sheets --check` style entry point (or equivalent function) that authenticates, prints the service-account email and the sheet title, and exits — the quickest way to prove sharing works on the Pi without booting the whole app.

**Verify**: on the Pi with real credentials, the check prints the sheet title; with the sheet unshared, it prints the 403 message naming the service-account email.

## 4. Cell parsing (3b, 3c) — *blocked on Group 1*

Start by running the Group 1 questions. Then, in `backend/sheets.py` (or `sheets_parse.py`):

- Read **column A of the `Day` tab** in one call (`col_values(1)` or equivalent), keeping each cell's row number for logging.
- Skip blanks (and A1, if Group 1 says it's a header).
- Classify each cell as **event** or **task** by the grammar Group 1 establishes, and parse out label + (for events) ring time. **Timers and stopwatches are never produced** — a cell that looks like a duration is still one of the two types or is skipped.
- Reuse `parse_time` / `parse_datetime` / `parse_iso_datetime` from `backend/classes.py` where the formats line up; add conversion only for formats the sheet uses that those don't handle.
- Return both the parsed items **and** whether the read itself succeeded — Group 5's diff must be able to tell "no items today" from "couldn't read the sheet."
- Per-cell failures are collected and skipped, never raised.

**Verify**: parsing runs against the real sheet and the printed items match what a human reads down column A, including a deliberately malformed cell being skipped with its row number logged.

## 5. Reconcile into the dashboard (3b, 3c) — *blocked on Group 4*

This is the diff described in `requirements.md` § Reconciliation. **Schema first, then the diff.**

- **Schema**: add `source TEXT DEFAULT 'local'` and `sheet_key TEXT` to the `events` and `tasks` `CREATE TABLE IF NOT EXISTS` statements in `Database.__init__` (`backend/database.py:43` and `:53`). **No migration code** — no `ALTER TABLE`, no `PRAGMA table_info`. The user drops the old tables on the Pi by hand, so `CREATE TABLE IF NOT EXISTS` builds them fresh with the new shape. Flag in the commit message and in the README that this upgrade requires dropping `events` and `tasks` (or deleting `productivity.db`) first. Carry both fields through `Message`, the `Task`/`Event` constructors, `get_tuple_to_save()`, and `get_ApiTask()`/`get_ApiEvent()`, so provenance survives a restart.
- Add the `sheet_sync` table (`date TEXT PRIMARY KEY`, `status`, `detail`, `synced_at`), **left out of `Database.tables`** so the daily `deleteAll()` does not wipe it, plus `Database` helpers to read/write today's marker.
- New `sync_day(task_manager)` in `backend/sheets.py`:
  - Bail before any mutation if the read failed (per Group 4's success flag) — **a failed read must never delete anything**.
  - Build the set of cell keys from column A, and the set of loaded cards with `source = 'sheet'`.
  - **Create** cards for keys with no matching sheet-origin card, via `Message` + the existing create path.
  - **Delete** sheet-origin cards whose key is absent from column A, via the existing `delete` command.
  - **Leave matched cards untouched** — no state rewrite, so a completed task stays completed and a dismissed event stays dismissed.
  - Never touch `source = 'local'` cards, and never touch timers or stopwatches.
- Call it from `TaskManager.__init__` after `retrieve_data()`, guarded by: sync enabled, and today's marker absent.
- Write the marker only on a successful run; log a one-line summary (created N, deleted M, skipped K).

**Verify**: fresh day + real sheet ⇒ cards match column A exactly. Restart ⇒ no duplicates. Delete a cell in the sheet and re-sync ⇒ that card disappears; a hand-made card next to it does not. Roll `date_id.txt` to a new date and restart ⇒ yesterday wiped, today synced.

## 6. Failure paths (3d) — *blocked on Group 5*

- Wrap the whole sync in a guard so **any** exception is logged and swallowed: startup always completes and local state is always intact.
- Distinguish and log the cases from the failure matrix in `requirements.md` (disabled, key missing, key malformed, network, 403 unshared, 404 wrong id/tab, partial read, bad cell) with messages that name the fix, not just the traceback.
- **The deletion half is the dangerous half**: assert that every failure path exits before the diff runs, so no failure mode can be mistaken for "column A is empty, delete everything." A successfully-read-but-empty column A is the *only* way mass deletion happens.
- Failures record status in `sheet_sync` **without** marking the day done, so the next restart retries.

**Verify**: walk the matrix by breaking one thing at a time (rename the key file, wrong spreadsheet id, unshare the sheet, disconnect the Pi's network) and confirm each time that the dashboard still boots with local cards intact, **nothing was deleted**, and the log names the cause.

## 7. Sync status on the API (3d) — *blocked on Group 6*

- Add a `sheet_sync` object (`date`, `status`, `detail`) to `TaskManager.get_ApiState()`'s response.
- No frontend change — the field exists for a later phase to render.

**Verify**: `GET /api` returns the field in both the success and failure cases; the frontend ignores the extra key without error.

## 8. Services start on boot (3e)

- `docker-compose.yml`: add `restart: unless-stopped` to `frontend` and `backend`.
- New `deploy/productivity-dashboard.service` systemd unit: `After=docker.service`, `Requires=docker.service`, `ExecStart=docker compose -f <path> up`, `ExecStop=docker compose down`, `Restart=on-failure`, `WorkingDirectory` at the repo root.
- Install/enable instructions in `deploy/README.md` (the user runs these on the Pi; the agent does not install into systemd).

**Verify**: `sudo reboot` with no keyboard attached ⇒ both containers come up and `127.0.0.1:8080/api` answers. `docker kill` the backend ⇒ it comes back on its own.

## 9. Browser kiosk session (3e) — *blocked on Group 8*

- Desktop autologin is **already enabled** on the Pi (user-confirmed) — nothing to configure. Note the dependency in `deploy/README.md` so a future re-image doesn't silently break the kiosk, and confirm it still holds during validation.
- `deploy/kiosk.sh`: wait for the dashboard URL to answer, then exec Chromium with `--kiosk`, `--noerrdialogs`, `--disable-infobars`, `--disable-session-crashed-bubble`, `--autoplay-policy=no-user-gesture-required` (Phase 4 forward-compat, per `requirements.md`), wrapped in a relaunch loop for browser-crash recovery.
- `deploy/kiosk.desktop` autostart entry pointing at the script; blank the screensaver/DPMS so the display stays on.
- Install instructions in `deploy/README.md`.

**Verify**: pull the power, plug it back in, touch nothing ⇒ the Pi lands on the full-screen dashboard with no cursor, no chrome, no login prompt. Kill Chromium ⇒ it relaunches.

## 10. Manual sync button (3f) — *blocked on Groups 5–7*

The only frontend work in the phase. Backend first, then UI.

- **Backend**: add a `sync_sheets` case to `TaskManager.process_command` that calls `sync_day()` with the "already synced today" marker **bypassed** (see `requirements.md` § Manual sync for why the marker only gates the automatic trigger). Reuse the same guard from Group 6 so a failure returns a status instead of raising; record the attempt in `sheet_sync`. No new route — it rides the existing `POST /api`.
- **Sync path**: confirm `sync_day()` takes a flag (or equivalent) for marker-bypass rather than being duplicated. Both halves of the diff apply — this button is how a mid-day sheet deletion reaches the dashboard.
- **Frontend** (`frontend/src/app/App.tsx`): a single sync control in the header area, Radix/shadcn per tech-stack — **no new MUI**. Behavior: disabled while the request is in flight (a double-tap must not fire two imports); on completion, refresh board state the same way other commands do; show last-result feedback from the `sheet_sync` field added in Group 7. Hidden/disabled when sync is not enabled, so a dev machine shows no dead button.
- Touch-friendly hit target — this is tapped on a 10" touchscreen, not clicked with a mouse.

**Verify**: add a cell to column A, tap the button ⇒ the new card appears without a restart. Delete a cell, tap ⇒ that card disappears. Tap with the sheet unchanged ⇒ nothing changes at all. Tap with the network down ⇒ error feedback and **nothing deleted**.

## 11. Docs and spec updates

- Check off 3a–3f in `specs/roadmap.md`.
- Update `AGENTS.md`: Phase 3 status, and the next phase pointer (Phase 4 — alarm sound).
- README: the Sheets configuration section (env vars, sharing the sheet with the service-account email, key file placement), **the one-time upgrade step — drop the old `events` and `tasks` tables (or delete `productivity.db`) before first run, since there is no migration and any cards in them are lost**, **the `Day`-tab/column-A contract and the fact that the sheet owns the cards it creates** (deleting a cell deletes the card; deleting a sheet card on the dashboard won't stick), and a pointer to `deploy/README.md` for kiosk install.
- Fold the manual walkthrough results into `validation.md`, including any intentional deviations.

**Verify**: a reader who has never seen the project can set up credentials and the kiosk from the README alone.

---

## Commit strategy

One commit per group, per AGENTS.md §6 (`Co-Authored-By: AI` footer, group referenced in the message). Groups 2–3 may reasonably land together (config + client are useless apart); Groups 8–9 may land together as the kiosk commit; Group 10's backend command and its UI may land together since neither is useful alone. No amends.
