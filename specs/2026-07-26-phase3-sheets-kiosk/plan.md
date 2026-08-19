# Plan — Phase 3: Google Sheets sync (read path) + kiosk autostart

Numbered groups are the intended implementation order. Each group should be independently committable and leave the app in a working state (i.e. the dashboard still boots and works with Sheets disabled at every point in the sequence).

Branch: `phase3-sheets-sync-kiosk`.

**Dependency note**: Groups 1–7 and 8–8c are done. **Group 9 (the Chromium kiosk session) and Group 10 (the manual sync button) are both unblocked**, and Group 11 (docs) closes the phase out after them. Kiosk work (8–9) can be done in parallel or first if the Pi currently needs a manual start each boot. Groups 8b and 8c tune what Group 8 landed and should precede Group 11, so the docs close out against the final boot sequence and the final dependency lists.

---

## 1. Capture the cell format — **COMPLETE** (2026-08-01, at the start of Group 4 as intended)

Not code, and deliberately deferred: the user asked to be questioned about the sheet's format at the moment the parsing work begins, so the answers are fresh and concrete rather than guessed at up front.

Asked via `AskUserQuestion` before a line of Group 4 was written. The answers, and the one thing that changed the design:

- [x] Spreadsheet id — already known and verified in Group 3; not re-asked.
- [x] Real sample cells — the user chose "dump column A read-only now" over pasting samples, so the grammar was written against the **actual 24 rows**, not a description of them. The dump also pulled `effectiveFormat/textFormat/bold` in the same request, which is how the bold question below got settled with data.
- [x] **Event vs. task**: *"the rows always start with the events in order. They are always bold and they start with the time they should ring: `1pm sun lunch`."*
- [x] **A1**: *"just the time I should wake up. Ignore it for now at least."* (`645am` — skipped.)
- [x] **Other days**: today only, no date filtering.
- [x] Time format: no separator, meridiem forms — `1pm`, `10pm`, `645am`.

**Deliverable met**: `requirements.md` § Sheet shape now carries the confirmed grammar, a worked-example table, and the two design notes that came out of the answers (why bold is *not* the discriminator, and why a leading time must carry a meridiem or a colon).

## 2. Dependencies and configuration plumbing (3a) — **COMPLETE**

- [x] `gspread`, `google-api-python-client`, `google-auth-httplib2`, `google-auth-oauthlib` in `backend/requirements.txt` (superset of the planned `gspread` + `google-auth`; `google-auth` comes in transitively).
- [x] `backend/sheets_config.py`: reads `SHEETS_SYNC_ENABLED` (bool, default `false`), `SHEETS_KEY_FILE`, `SHEETS_SPREADSHEET_ID`, `SHEETS_TAB_NAME` (default `"Day"`, per the already-confirmed sheet shape) from the environment once at import time.
- [x] `docker-compose.yml`: `backend` service gets the four env vars (each with a safe default/empty string) and a read-only bind mount `${SHEETS_KEY_FILE_HOST:-/dev/null}:/run/secrets/sheets_key.json:ro` — the `/dev/null` default means `docker compose up` still boots with no `.env` present; an absent real key file surfaces later as the documented "key file missing/unreadable" failure path (Group 6), not a compose-level error.
- [x] `.gitignore`: already had the actual key filename (`backend/productivity-dashboard-503701-03b014c70abf.json`); added `.env` / `.env.*` (with `!.env.example` un-ignored).
- [x] `.env.example` at the repo root documents all four variables with placeholder values only.

**Verify**: `docker compose config` resolves cleanly with no `.env` present (confirmed). Existing 82 backend tests pass unmodified with `sheets_config` importable but unused by any running code yet (nothing calls into it until Group 3).

## 3. Authenticated Sheets client (3a) — **COMPLETE**

New `backend/sheets.py`:

- [x] `get_client(key_file=None)` — builds `google.oauth2.service_account.Credentials` from the key file with the **read-only** scope, authorizes `gspread`, returns the client. Typed errors throughout: `SheetsConfigError` (env var unset), `SheetsAuthError` (key missing / not JSON / not a service-account key / rejected by `google-auth`), `SheetsAccessError` (403), `SheetsNotFoundError` (404 spreadsheet or missing tab), `SheetsNetworkError` (DNS/route/timeout) — all under a `SheetsError` base so Group 6's guard can catch one class.
- [x] `open_worksheet(client, spreadsheet_id=None, tab_name=None)` — defaults both from `sheets_config`, opens the sheet and returns the worksheet. Note `gspread.open_by_key` is lazy, so this is the first call that touches the network and the one that raises 403/404. The 403 message names the service account's `client_email` and says to share the sheet with it; `get_service_account_email()` supplies that and never raises.
- [x] Explicit `REQUEST_TIMEOUT_SECONDS = 15` via `client.set_timeout()`, so a dead network cannot hang startup.
- [x] `python sheets.py --check` (flat modules, run from `/app` in the container): authenticates, prints the service-account email, spreadsheet title, and tab name/row count, exits 0; on any `SheetsError` it prints `Type: message` to stderr and exits 1. Bare `python sheets.py` runs the same check; anything else exits 2 with usage.

**Verified**: against the real key and the real spreadsheet, `--check` prints `service account: python-api@…`, `spreadsheet: IAN'S REQUIÉM`, `tab: Day (1000 rows)`, `OK`. Failure paths walked one at a time — unset `SHEETS_KEY_FILE`, wrong path, `/dev/null`, valid JSON that isn't a service-account key, unset `SHEETS_SPREADSHEET_ID`, wrong spreadsheet id (404), wrong tab name (404) — each printing its typed message and exiting 1. The 403/unshared case is left for the manual walkthrough (validation step 2), since it needs the user to un-share the sheet. Existing 82 backend tests still pass, unmodified.

## 4. Cell parsing (3b, 3c) — **COMPLETE**

Ran the Group 1 questions first, as specified. New `backend/sheets_parse.py` (separate module, not inside `sheets.py`: the grammar is then testable with no network, no key file, and no Google import, and it keeps Group 5's `sync_day` from having to share a file with the regex).

- [x] `sheets.read_day(worksheet=None)` reads column A in **one** `col_values(1)` call, so the items are a snapshot of a single moment rather than a walk down a sheet that may be edited mid-read. Row numbers are the list index, preserved into every item and every skip message.
- [x] Blanks skipped silently; A1 skipped via `HEADER_ROWS = 1`.
- [x] Classification by the Group 1 grammar: a leading clock time ⇒ **event** (label is the remainder), anything else non-empty ⇒ **task**. **No timer or stopwatch can be produced** — `SheetItem.type` is only ever `"event"` or `"task"`, and a cell like `bath, bed, timers 8h` parses as a task.
- [x] Returns `SheetRead(ok, items, skipped, error)` — `ok` is exactly the "could the sheet be read at all" flag Group 5's diff needs, and **every** failure path returns `ok=False` with an empty `items`, so a failure can never be mistaken for an empty column.
- [x] Per-cell failures collected into `skipped` with the row number and a reason, logged at WARNING, never raised.
- [x] `python sheets.py --dump` prints the parse for reading against the sheet, alongside Group 3's `--check`.

**Deviation from the plan, and the bug it caught**: the plan said to reuse `parse_time`/`parse_datetime`/`parse_iso_datetime` from `classes.py` "where the formats line up". They don't. `parse_time` resolves a wall-clock string against the **process** timezone, and the backend container runs **UTC** while the app's configured zone is **`America/Chicago`** — so reusing it would have made `1pm sun lunch` ring at 08:00 local, five hours early. This never surfaced before because every card the frontend creates carries an already-absolute ISO timestamp computed in the browser; a spreadsheet is the first source of bare wall-clock text. Fixed by adding `database.get_timezone()` (line 1 of `date_id.txt` — the same source the daily rollover already reads, refactored to one `_zone_from` helper so there is still exactly one place that knows what line 1 means) and resolving against that. `get_timezone()` deliberately **never raises**, falling back to the system zone with a printed note, since Group 6 requires that no sync failure can take startup down.

**Verified 2026-08-01**:

- `python sheets.py --dump` against the real spreadsheet ⇒ **15 items, 0 skipped**, matching a human read of column A row for row: `A2 event 'sun lunch' @ 18:00Z` (13:00 CDT), `A3 event 'plan, self check, reflect, read' @ 03:00Z next day` (22:00 CDT), 13 tasks at A4–A24, A1 and every blank skipped.
- Timezone correctness checked explicitly by converting each parsed `ring_time` back to `America/Chicago` — every event lands on the wall-clock time written in its cell.
- Malformed cells and the failed-read paths were exercised **without editing the user's live sheet**: the grammar over synthetic cells (`25pm broken` ⇒ bad hour, `9:75am broken` ⇒ bad minute, `3pm` ⇒ no label, each skipped with its row logged and the surrounding cells still parsed), and `read_day` against a stub worksheet raising a network error and APIError 403/404/500 — all four return `ok=False`, `items=[]`, and a typed message.
- Boundary forms confirmed: `12am` ⇒ 00:00, `12pm` ⇒ 12:00, `645am` ⇒ 06:45, `1230pm` ⇒ 12:30, `13:30` ⇒ 13:30. Non-times confirmed to stay tasks: `bath, bed, timers 8h`, `5, 10, 15 reps`, a cell starting with a URL.
- **82 backend tests pass, unmodified** (`database.py` was touched, so this is the check that mattered), `sheets.py --check` still passes against the real sheet, and the backend restarts clean with `GET /api` ⇒ 200 and no tracebacks.

**Raised here, decided for Group 5 (2026-08-01)**: an event whose ring time has already passed when the sync runs (a 06:45 event synced at 09:00) would be created in the past and ring immediately. The user's call is to **skip it** — see Group 5's diff bullet and `requirements.md` § Import behavior. Group 4 needs no change for this: the parser keeps turning the cell into a timestamp and saying nothing about whether that moment has passed, which is what makes `--dump` give the same answer at any hour of the day.
## 5. Reconcile into the dashboard (3b, 3c) — **COMPLETE** (2026-08-18)

This is the diff described in `requirements.md` § Reconciliation. **Schema first, then the diff.**

- [x] **Schema**: `source TEXT DEFAULT 'local'` and `sheet_key TEXT` added to the `events` and `tasks` `CREATE TABLE IF NOT EXISTS` statements in `Database.__init__`. **No migration code** — no `ALTER TABLE`, no `PRAGMA table_info`. The user drops the old tables on the Pi by hand, so `CREATE TABLE IF NOT EXISTS` builds them fresh with the new shape. Flag in the commit message and in the README that this upgrade requires dropping `events` and `tasks` (or deleting `productivity.db`) first. Both fields carried through `Message`, the `Task` constructor (inherited by `Event`), `get_tuple_to_save()` on both classes, and `get_ApiTask()` (inherited by `get_ApiEvent()`), so provenance survives a restart.
- [x] `sheet_sync` table (`date TEXT PRIMARY KEY`, `status`, `detail`, `synced_at`), **left out of `Database.tables`** so the daily `deleteAll()` does not wipe it, plus `Database.get_sheet_sync()` / `set_sheet_sync()` and `get_date()`.
- [x] New `sync_day(task_manager, force=False)` in `backend/sheets.py`:
  - [x] Bails before any mutation if the read failed (per Group 4's success flag) — **a failed read never deletes anything**, and writes no marker, so the next restart retries.
  - [x] Builds the set of cell keys from column A, and the set of loaded cards with `source = 'sheet'` (`_sheet_cards`).
  - [x] **Creates** cards for keys with no matching sheet-origin card, via `Message` + `process_command("create")`. Ids come from `db.last_id + 1` per card, so the existing `date_id.txt` id allocation is reused rather than duplicated.
  - [x] **Skips events whose ring time has already passed** (user decision, 2026-08-01 — see `requirements.md` § Import behavior for the full rule). `_has_passed()` compares the parsed UTC `ring_time` against now in UTC; at-or-before now counts as past. The check lives **here, at creation**, not in Group 4's parser, which stays time-independent. It applies to creation only — a matched card that has since rung is left alone by the rule above, or the manual button would wipe the day's events every evening. Tasks are unaffected. Counted separately from malformed cells in the summary log, since a past event is a normal outcome rather than a failure.
  - [x] **Deletes** sheet-origin cards whose key is absent from column A, via the existing `delete` command.
  - [x] **Leaves matched cards untouched** — no state rewrite, so a completed task stays completed and a dismissed event stays dismissed.
  - [x] Never touches `source = 'local'` cards, and never touches timers or stopwatches (`_sheet_cards` only ever looks at `tasks` + `events`).
- [x] Called from `TaskManager.__init__` after `retrieve_data()`, via a new `TaskManager.sync_sheets(force=False)` — that method is the seam Group 10's `sync_sheets` command hooks into. Guarded by: sync enabled (checked at the call site), and today's marker absent (checked inside `sync_day`, which is why `force` lives there rather than at the call site).
- [x] Marker written only on a successful run; one-line summary logged as `created N, deleted M, past K, unparsed J`.

**Deviation from the plan, and why**: the plan put both guards at the call site. The enabled-check stayed there but the marker-check moved into `sync_day`, because Group 10 needs to bypass exactly one of them — a manual tap ignores the marker but must still respect the master switch. Keeping them in two places is what lets `force` be a single boolean instead of a duplicated code path.

**Import is lazy, deliberately.** `TaskManager.sync_sheets()` imports `sheets_config` first and returns immediately if sync is off; `import sheets` happens only after that. So with `SHEETS_SYNC_ENABLED` false — every dev machine and the whole test suite — `gspread` is never loaded and no network call is reachable, which is what validation's "the import path must not run at all during tests" asks for. It also means there is no import cycle: `classes` reaches `sheets` only at call time, so `sheets` can import `Message` from `classes` at module level.

**Verified 2026-08-18** (33-check scratch harness in a temp directory, `read_day` stubbed — **no credentials, no network, and the live spreadsheet never touched**; production `productivity.db` never opened):

- Schema: `events` and `tasks` both carry `source`/`sheet_key`; `sheet_sync` is `(date, status, detail, synced_at)` and is absent from `Database.tables`.
- First sync of a synthetic column A (2 events, 2 tasks, 1 unparseable) ⇒ `created 3, deleted 0, past 1, unparsed 1`. The future event and both tasks appear; the past event does not; the duration-looking cell `bath, bed, timers 8h` became a task and **no stopwatch or timer was created**.
- Second run same day ⇒ skipped by the marker, no duplicates. A restart (`TaskManager()`) reloads the same three cards with `source = 'sheet'` and their `sheet_key` intact, and `get_ApiTask()` exposes both.
- Completing an imported task and dismissing an imported event, then re-syncing with `force=True` ⇒ `created 0, deleted 0` and **both states preserved**; a hand-made local card sitting alongside is untouched.
- Removing one cell ⇒ exactly that card deleted, the local card and the event untouched.
- **Failed read (`ok=False`) ⇒ nothing deleted, board byte-identical, and the existing `ok` marker not overwritten.** This is the phase's highest-risk property.
- Successfully-read **empty** column A ⇒ both remaining sheet cards deleted, local card survives — the deliberate "nothing scheduled today" case, and the one path that distinguishes an empty read from a failed one.
- Rolling `date_id.txt` to an old date and restarting ⇒ cards wiped by the existing rollover, **and the `sheet_sync` marker survived `deleteAll()`**.
- **82 backend tests pass, unmodified.** The backend restarts clean with `GET /api` ⇒ 200 and no traceback.

**Confirmed cost of skipping the table drop** (measured, not predicted): with old-shape tables, creating a card raises `sqlite3.OperationalError: table tasks has no column named source`. That is not limited to the sync path — **hand-made cards fail too**, because the INSERT names the new columns unconditionally. Group 6's guard covers the sync half; the card-creation half is fixed only by doing the drop. The Pi's `events`/`tasks` were empty (0 rows) at the time of this work, so the drop costs nothing if done now.

**Verify on the Pi (still owed, needs the real sheet)**: fresh day + real sheet ⇒ cards match column A exactly. Restart ⇒ no duplicates. Delete a cell in the sheet and re-sync ⇒ that card disappears; a hand-made card next to it does not. Roll `date_id.txt` to a new date and restart ⇒ yesterday wiped, today synced. These are validation steps 4–10.

## 6. Failure paths (3d) — **COMPLETE** (2026-08-18)

- [x] **Two guards, not one.** `sheets.sync_day()` is now a wrapper whose whole body is `try: _reconcile(...) except Exception:` — it logs with a traceback, records the failure, and returns an error status. `TaskManager.sync_sheets()` wraps the layer above it, because two things happen *before* `sync_day` exists and so cannot guard themselves: reading `sheets_config`, and `import sheets` — the latter being the real Group 3 failure (`ModuleNotFoundError: No module named 'gspread'` from a stale image). Either way startup completes and local state is untouched.
- [x] Anticipated failures were already typed and message-carrying from Groups 3–4; Group 6 is what makes them *land somewhere*. Each of the six matrix causes (config, key missing, key malformed, network, 403 unshared, 404 wrong id/tab) now reaches both the log and the `sheet_sync` row with the fix named in the text.
- [x] **The deletion half is structural, not asserted.** The diff moved into `_apply_diff()`, called from exactly one place — the line after the `read.ok` check. There is no path from a failed read to that function, and the single call site is what makes that inspectable rather than a claim.
- [x] **The unparseable-cell promise made real.** `SheetRead` gained `cells`: every non-empty cell text, parsed or not. Deletion now diffs against that instead of against `items`, so a cell that *stops* parsing keeps its card rather than reading as a deleted row. Before, the matrix's "treat the cell's existing card as still present" held only because parsing is deterministic — true today, and quietly dependent on nobody ever editing the grammar.
- [x] Failures record `status = 'error'` in `sheet_sync` **without** marking the day done. The automatic trigger gates on `status == 'ok'`, so an error row leaves the day retryable on the next restart, and the row is what Group 7 exposes on `GET /api`.
- [x] `_record()` swallows a failure of the marker write itself: if the database is what broke, failing to record *that* must not be what finally takes startup down.

**Deviation from Group 5, deliberate**: Group 5 verified that a failed read *does not overwrite* an existing `ok` marker. It now does — the row means "the last attempt for this date, and how it went", which is what makes it usable as the manual button's feedback (3f) instead of a stale success. The cost is that a failed evening sync re-opens the automatic trigger for that date, so a restart later the same day re-syncs. That is idempotent by construction (matched cards are left alone) and its only visible effect is the already-documented one: a sheet card the user deleted by hand on the dashboard comes back.

**One thing the plan did not contain, and it was load-bearing**: none of this logging was reaching the container log. Uvicorn configures its own loggers and leaves the **root logger empty at WARNING**, so every `logger.info` in `sheets.py`/`sheets_parse.py` was dropped and the warnings printed bare — no timestamp, no level, no logger name. Measured in the container, not assumed. A `logging.basicConfig(level=INFO, ...)` in `main.py` before `TaskManager()` fixes it, plus the same line in `sheets.py`'s `__main__` block for `--check`/`--dump`. Without it, this group's verification criterion ("the log names the cause") could not be met — the log named nothing.

**Verified 2026-08-18** (33-check harness in a temp directory, `sheets.read_day` stubbed — **no credentials, no network, the live spreadsheet never touched**, production `productivity.db` never opened; see validation § C0):

- All six matrix causes ⇒ error status, **nothing created or deleted**, marker records the cause with the fix in the text, day not marked done.
- `import sheets` failing ⇒ error status, `TaskManager()` still constructs.
- `RuntimeError` and `sqlite3.OperationalError: table tasks has no column named source` from inside the sync ⇒ both caught by the same guard, board unchanged.
- The marker write itself failing, and `db.get_date()` itself failing ⇒ still no exception escapes; the latter returns `date: None`.
- An error marker does **not** count as "already synced" (the retry property); an `ok` marker still does.
- An unparseable cell keeps its card (`created 0, deleted 0, past 0, unparsed 1`); a successfully-read **empty** column A still deletes sheet cards and keeps local ones — the one path to mass deletion, still open, still the only one.
- **82 backend tests pass, unmodified.** Backend restarts clean, `GET /api` ⇒ 200, no traceback. `sheets.py --check`/`--dump` still print their typed message and exit 1 with the credential unreachable.

**Still owed on the Pi** (validation steps 11–18): the matrix walked against the real sheet by breaking one thing at a time — rename the key file, wrong spreadsheet id, unshare the sheet, pull the network — confirming each time that the dashboard boots with local cards intact, **nothing was deleted**, and the log names the cause.

## 7. Sync status on the API (3d) — **COMPLETE** (2026-08-18)

- [x] `TaskManager.get_ApiState()` returns a `sheet_sync` object — `{date, status, detail}` — alongside `last_id`/`events`/`durations`/`tasks`.
- [x] **The source is the last attempt, held in memory** (`self.sheet_sync`), not a read of the marker table. The two differ in exactly the cases that matter: a failure the marker never received (`import sheets` failing, `get_date()` failing, the marker write itself failing) still reaches the API, and so does the "sync is switched off" case, which was never going to have a row.
- [x] **One recorder, so no caller can forget.** `sync_sheets()` is now a thin wrapper that stores what `_run_sheet_sync()` returns; startup and Group 10's manual command both go through it, so the published status is always the most recent attempt without either call site remembering to update anything.
- [x] Four statuses: `disabled`, `ok`, `skipped` (already synced today), `error`.
- [x] **`disabled` is reported rather than left blank** — a small addition beyond the plan's wording, and the reason is Group 10: the button has to be hidden when `SHEETS_SYNC_ENABLED` is false, and this field is the only channel that tells the frontend so. `_run_sheet_sync()` now returns that status where it previously returned `None`.
- [x] **The `skipped` detail carries the earlier run's counts through** (`already synced today — created 1, deleted 1, past 0, unparsed 0`). Without this, every same-day restart would replace the day's real outcome with the word "skipped", which is the state the Pi is in for most of any given day.
- [x] No frontend change, per the plan. `App.tsx` types the response structurally and never validates it at runtime, so the extra key is ignored; `ApiState` gains the field in Group 10, when something reads it.

**Verified 2026-08-18**:

- **Live**: the running backend restarts clean and `GET /api` ⇒ 200 with `"sheet_sync": {"date": null, "status": "disabled", "detail": "SHEETS_SYNC_ENABLED is false"}` — the real dev-machine state — and the other four keys unchanged.
- **Off-device harness, now 43 checks**: the field is present and correct for `disabled`, for all six failure causes (`error`, with the typed message), for a successful run, and for a same-day restart, which still reports today's counts. The response's key set is exactly the four originals plus `sheet_sync`.
- **82 backend tests pass, unmodified.**

**Still owed on the Pi** (validation step 19): confirm the field over the real sheet in a success *and* a failure case, and that the dashboard renders normally with the browser console clean.

## 8. Services start on boot (3e) — **COMPLETE**

- [x] `docker-compose.yml`: `restart: unless-stopped` on `frontend` and `backend`.
- [x] New `deploy/productivity-dashboard.service` systemd unit: `Requires=docker.service`, `After=docker.service network-online.target`, `WorkingDirectory` at the repo root (so compose finds `docker-compose.yml` and `.env`), `ExecStart=docker compose up`, `ExecStop=docker compose down`, `Restart=on-failure` with `RestartSec=10`, `TimeoutStartSec=0` for the first cold build.
- [x] `ExecStartPre=-/usr/bin/docker compose build` — added beyond the plan, from the Group 3 finding that the bind mounts carry source but not site-packages, so the unit must not run a stale image after a dependency change. The leading `-` makes a failed build non-fatal: the kiosk comes up on the last good image rather than not at all.
- [x] Install/enable instructions in `deploy/README.md`, plus status/log commands, the stop-via-systemctl-not-compose note, and the `.env` and 127.0.0.1-binding notes. The user runs these on the Pi; **nothing was installed into systemd from here**.

**Verify**: `docker compose config` resolves with both restart policies present, and `systemd-analyze verify` on the unit reports no warnings (both confirmed). The reboot / power-cut / `docker kill` checks are validation steps 20–22 and 25, run on the Pi by the user after installing the unit.

## 8b. Get the build off the boot path; make the frontend build smaller and reproducible (3e follow-up) — **COMPLETE**

Numbered `8b` rather than `12` so Groups 9–11, the validation step numbers, and the existing commit messages keep meaning what they say. Unblocked; do it before Group 11 so the docs close out against the final shape.

**Outcome (2026-08-01)**: all four planned changes landed, plus one the plan did not anticipate and which turned out to be the larger half of the boot-time win. Measured on the Pi: **boot 156–176s → 4s**, frontend image **2.49GB → 906MB**, cold build **~3min → 1m19s**, and 6.0GB of Docker garbage reclaimed. Details in "What the measurements changed" below.

Three changes, from what the first real run of the unit showed (4m51s to reach a listening container, and a 2.49GB frontend image built from no lockfile):

- [x] **Drop `ExecStartPre` from `deploy/productivity-dashboard.service`.** The unit is the only reason the Pi ever rebuilds: BuildKit's cache is swept on a 60-day keep duration and a 5.588GiB reserved floor regardless of whether anything changed, and `docker compose build` re-runs a step whenever the cache record is missing — it does not treat the existing image as a cache source. So an untouched repo can still pay a full `FROM node:22` + `npm install` on a boot. ~~Without the build, the Pi runs the image it has and boots in seconds, forever.~~ **This last claim was wrong** — see "What the measurements changed". Removing the build was necessary but nowhere near sufficient; with a warm cache the build cost ~1s, and boot still took 156–176s.
- [x] **Replace the stale-image guard the build was providing** — that failure (Group 3's `ModuleNotFoundError: No module named 'gspread'`) is real and must not come back silently:
  - `deploy/README.md`: the documented step after **any** change to `backend/requirements.txt` or `frontend/package.json` is now `docker compose build && docker compose down -v && sudo systemctl restart …`, stated as a rule rather than a footnote. The `down -v` is not decoration — see the anonymous-volume finding below.
  - Rewrite the cold-cache note added in `75108e6` — with the build gone from boot, the cache only matters to a build the user is already sitting in front of.
- [x] **`frontend/dockerfile`: `FROM node:22` → `node:22-slim`.** The full base is most of the 2.49GB. **Landed: 906MB final image** (better than the 1.22GB prototype, since `npm ci` also prunes what `npm install` had left behind).
  - **Prototyped 2026-08-01 and it works**: built clean with no `node-gyp` step, **1.22GB vs 2.49GB**, Vite 6.3.5 ready in 486ms, `/src/app/App.tsx` and the Tailwind CSS both transform and serve, no errors in the container log. The test image was removed afterward; the Dockerfile edit itself is still to do.
  - The three native binaries in the tree (`@rollup/rollup-linux-arm64-gnu`, `@tailwindcss/oxide-linux-arm64-gnu`, `lightningcss-linux-arm64-gnu`) are **prebuilt platform packages, downloaded not compiled**, which is why slim's missing toolchain doesn't matter. They are all `-gnu` builds, so **`node:22-alpine` is the base to avoid** — musl would break all three. Slim is Debian/glibc, same as the full image.
  - Note that switching bases is itself a one-time full rebuild, so do it at a keyboard, not before a reboot.
- [x] **Commit a lockfile and build from it.** `frontend/` has **no `package-lock.json` and no `pnpm-lock.yaml`**, so every build re-resolves the whole transitive tree from the registry. Direct dependencies are pinned to exact versions, but nothing beneath them is — which is both why builds are slow and why the image the Pi builds in October need not match the one it builds today. With the build leaving the boot path, an unpinned rebuild is no longer something to discover at 3am, but it is still the difference between a reproducible kiosk and a hopeful one.
  - **Stay on `npm`** — the decision, not a default. `pnpm` (which `specs/tech-stack.md`, the README, `frontend/pnpm-workspace.yaml`, and the `pnpm.overrides` block in `package.json` all point at) is a real migration with a specific trap: `react` and `react-dom` are declared as **optional `peerDependencies`**, which npm installs anyway (18.3.1 is in the running container, confirmed) and pnpm does not install by default. That migration needs its own group and its own verification; it is not this one.
  - Generate the lockfile **from the tree that currently works**, not a fresh resolution: `docker compose run --rm frontend npm install --package-lock-only` writes it straight to `frontend/` through the bind mount. Commit it.
    - **What actually happened**: the planned command is self-contradictory — `run --rm` gets a *fresh* anonymous `node_modules`, so it is a fresh resolution, not the working tree. Generating from the working tree instead (`compose exec`, which has the populated volume) produced a lockfile with **no `resolved` or `integrity` fields at all** — npm cannot recover that metadata from an installed tree — which is useless for reproducibility, the entire point of the exercise. Resolved by generating fresh (full metadata, 356 entries) and then **diffing it against the working tree**: nothing present in the working tree was missing from the fresh resolve, the 77 extra entries are other platforms' optional binaries that npm skips at install, and 10 packages differed by a patch version (`rollup` 4.62.3→4.62.4, four `@babel/*` 7.29.7→7.29.8, `@types/react`, `enhanced-resolve`, `electron-to-chromium`, `baseline-browser-mapping`). Committed the fresh one; the diff *is* the "from a tree that works" guarantee the plan was reaching for.
  - `frontend/dockerfile`: `RUN npm install` → `RUN npm ci`. The existing `COPY package*.json ./` already picks the lockfile up, and `frontend/.dockerignore` does not exclude it. `npm ci` fails loudly when the lockfile and `package.json` disagree — that is the point of it, and it is also the one way this change can bite, so the first build after the switch is the one to watch.
  - **Verify React survived**: after the first `npm ci` image, confirm `react@18.3.1` is actually in `node_modules`. The optional-peer declaration means "npm installed it last time" is an observation, not a guarantee.
  - Two known-inert oddities in `package.json`, deliberately **left alone** so a later reader doesn't think they were missed: the `pnpm.overrides` block (npm ignores it, so the `vite` override it declares does nothing today) and `"tsx": "^4.0.0"` sitting in `scripts` rather than `devDependencies`. Neither breaks anything; both belong to the pnpm decision above.
  - Out of scope: multi-stage builds.

### What the measurements changed (2026-08-01)

The plan blamed boot time on the build. With the build removed, a restart still took **156–176s**, so the diagnosis was wrong. The real cause, and a fifth change that the plan did not contain:

- **`ExecStop=docker compose down` was the expensive half.** `down` *removes* the containers, which orphans the anonymous `/app/node_modules` volume. Docker fills a volume from the image only when the volume is empty, so the next `up` builds a new one and copies the image's `node_modules` in: **405MB across 64,888 files**, measured at 156–176s. It is file-count bound, not bandwidth bound — the same 405MB written sequentially on this Pi takes 0.15s (2.8GB/s), i.e. ~415 files/sec. Nothing about this depends on anything having changed; the copy is unconditional on an empty volume.
- **Fix: `ExecStop=/usr/bin/docker compose stop`.** Containers persist, the volume is reused, and boot is **4s**. User-approved deviation from the plan.
- **The trap that makes it non-trivial**, proven with a throwaway busybox project rather than assumed: compose **carries an anonymous volume forward when it recreates a container**, so after `docker compose build` the container runs the new image with the *old* volume mounted over `node_modules`. A frontend dependency change would silently not take effect — precisely the `ModuleNotFoundError` class of bug this group exists to prevent. That is why the documented rebuild rule is `build && down -v && restart`; `-v` deletes the volume with the containers so the next start repopulates it. **Do not simplify that command back.**
- **Docker never garbage-collects anonymous volumes**, so the old unit leaked one ~180MB volume per restart, permanently. The Pi had reached 9 dead volumes / 1.486GB. Cleaned up during this group: **6.0GB reclaimed** (1.486GB volumes + 4.518GB build cache), disk 32G→24G used.
- **Log rotation, added as a direct consequence.** Keeping containers alive removed the incidental log cap that `down` had been providing (destroying a container destroys its json log). Docker's `json-file` driver has **no rotation by default**, so both services now declare `max-size: 10m` / `max-file: 3` in `docker-compose.yml` — a 30MB ceiling each, permanently. Growth is interaction-driven rather than continuous: the frontend has no polling loop (the 1s intervals in `App.tsx` are local ticks that only reach the backend when a timer or event fires), and an idle 60s sample grew 0 bytes. Applied and confirmed live via a 3s `systemctl restart`.
- **Storage growth audit, for the record**: dangling images do **not** accumulate on this device — the containerd snapshotter releases the untagged image when a rebuild retags, verified with `docker images -a --filter dangling=true` returning empty after the 2.49GB→906MB switch. The journal self-rotates (~4GB cap, 8MB in use) and the build cache is BuildKit-GC'd. After this group the only category that grows without a bound is container logs, which is what the `logging:` block closes.
- **A power cut was never the slow path.** With power pulled, `ExecStop` never runs, the containers survive, and the daemon's own `unless-stopped` restore brings them back in **4s** without the unit. So before this change, yanking the cord recovered *faster* than a clean `sudo reboot` — the only path that ran `down`.

**Verified 2026-08-01** (on the Pi, unit installed to `/etc/systemd/system/` and `daemon-reload`ed):

- `systemd-analyze verify` clean; installed unit confirmed identical to the repo copy, with no `ExecStartPre` and `ExecStop=docker compose stop`.
- `sudo systemctl restart productivity-dashboard.service` ⇒ **both services answering in 4s**, no build in the journal (the only `npm` lines are Vite's SIGTERM noise on stop), no container recreation, volume count unchanged at 1.
- Frontend from `npm ci`: image **906MB** (was 2.49GB), Vite 6.3.5 ready in 385ms, `index.html` and `/src/main.tsx` serve 200, react resolves through Vite's dep cache, no errors in the container log. **`react@18.3.1` and `react-dom@18.3.1` confirmed present** in both the image and the running container — the optional-peer risk did not materialise.
- Genuine cold build (new base + fresh `npm ci`): **1m19s**. Two consecutive rebuilds after that: 2s and 1s. Note `docker builder prune` without `-a` keeps cache still referenced by an existing image, so a prune does not by itself produce a cold build.
- 82 backend tests pass, unmodified.
- **Not verified here, left for the user**: kiosk validation steps 20–22 and 25 need a real `sudo reboot` and a power cut, and steps 20/23–25 additionally need Group 9's Chromium kiosk, which does not exist yet. The container half of step 22 (`docker kill` ⇒ auto-restart) is also still to run against the new unit.

## 8c. Backend dependencies — trim, then pin — **COMPLETE**

The backend half of what Group 8b does for the frontend. Separate group because it is a different language, a different failure mode, and it wants its own verification pass against the real spreadsheet. **Order matters: trim first, then pin** — pinning first would carefully lock the versions of packages that are about to be deleted.

**Outcome (2026-08-01)**: both halves landed as planned, with no surprises of 8b's magnitude. Measured on the Pi: site-packages **185MB → 78MB**, backend image **436MB → 308MB** (a 128MB drop, ahead of the ~100MB estimate, since the estimate counted only `google-api-python-client` itself and not the six transitives that left with it). 9 packages went, all traceable to the dropped API client. One thing the plan did not anticipate: **the unpinned trim silently upgraded three packages**, which is the case for pinning making itself in the middle of the exercise — see below.

### Trim (measured, not guessed)

`backend/requirements.txt` declares eight packages. Grepping every import in `backend/*.py` and `backend/tests/*.py` shows three of them are never imported, and `pip show` confirms `gspread` does not require two of them:

- [x] **Drop `google-api-python-client`.** Nothing imports `googleapiclient`, and `gspread` requires only `google-auth` and `google-auth-oauthlib`. It is **100MB of the 185MB site-packages** — the bundled API discovery documents — so the backend image should drop from 436MB to roughly 335MB. This is the whole win; the rest is tidiness.
- [x] **Drop `google-auth-httplib2`.** It exists only to bridge `google-auth` to the API client above. Nothing imports it. Takes `httplib2`, `uritemplate`, `protobuf` and `googleapis-common-protos` (~2.6MB) with it.
- [x] **Drop `google-auth-oauthlib` from the declared list.** It is the OAuth user-consent path this phase explicitly rejects in favour of a service account (`requirements.md` § Non-goals). `gspread` requires it, so it stays installed transitively either way — removing the declaration is about the list telling the truth, not about size.
- [x] **Add `google-auth`.** `backend/sheets.py` imports `google.oauth2.service_account` and `google.auth.exceptions` directly, so it is a real direct dependency that today is only present because `gspread` happens to pull it in.

Net declared list: `fastapi`, `uvicorn`, `tzlocal`, `pytest`, `gspread`, `google-auth`. That is exactly the "`gspread` + `google-auth`" that Group 2 planned before the install went wide — see the "superset of the planned" wording in Group 2 above, which this restores.

**What actually left** (`pip freeze` diffed before and after, 42 packages → 33): the four the plan named — `google-api-python-client`, `google-auth-httplib2`, `httplib2`, `uritemplate` — plus `protobuf` and `googleapis-common-protos` as predicted, plus three the plan did not list but which belong to the same subtree: `google-api-core` (required by the API client), `proto-plus` (required by `google-api-core`), and `pyparsing` (required by `httplib2`). Nothing outside that subtree was touched: `google-auth-oauthlib`, `oauthlib`, `requests-oauthlib` and `requests` all remain, arriving transitively through `gspread` exactly as the plan expected.

### Pin

- [x] Split `backend/requirements.in` (the six names above, hand-edited) from `backend/requirements.txt` (fully pinned, generated, committed). `backend/dockerfile` keeps `pip install --no-cache-dir -r requirements.txt` unchanged — **no new tool in the image**, and the README's host instructions keep working verbatim. Both files carry a header saying which is which and how to regenerate; `deploy/README.md`'s rebuild rule now names `requirements.in` too and says never to hand-edit the generated file.
- [x] Generate the pinned file **after** the trim and **from a tree that works**: rebuild the backend against the trimmed `.in`, run the test suite and `sheets.py --check`, then freeze that environment. `uv pip compile requirements.in -o requirements.txt` is the better generator if you want it (it resolves from the declared list and annotates which dependency pulled what, rather than snapshotting whatever drifted into the container) — but it runs on your machine, never in the image, so it is a preference, not part of the deliverable.
  - **Done by freezing the container, not by `uv`** — deliberately, even though `uv` is installed on this host. The pin has to describe `python:3.11-slim`/linux-arm64 as the image actually resolves it; a host-side compile describes the host's interpreter and would have to be trusted rather than observed. The verification sequence ran in that order: build against the trimmed `.in` → 82 tests → live `--check` → `pip freeze | sort -f` → paste → rebuild → confirm the freeze reproduces byte-identically.
- [x] **The unpinned window upgraded three packages, and that is the argument for this half of the group.** Re-resolving the trimmed list — same `.in` intent, four weeks later — moved `fastapi` 0.140.13→**0.141.1**, `uvicorn` 0.51.0→**0.52.1**, and `cryptography` 49.0.0→**50.0.0**, none of which the trim asked for. They were caught only because the before/after `pip freeze` diff was being read for removals. Pinned at the new versions, since those are the ones that passed the 82 tests and the live `--check`; the older set below is now history rather than the running state.
- Versions as of Group 3 (2026-07-28), kept for reference: Python 3.11.15, `fastapi==0.140.13`, `starlette==1.3.1`, `pydantic==2.13.4`, `uvicorn==0.51.0`, `tzlocal==5.4.4`, `gspread==6.2.1`, `google-auth==2.56.2`, `pytest==9.1.1` — 47 packages resolved from 8 declared names. **Now pinned at 33 packages from 6 declared names**, with the three upgrades above; `starlette`, `pydantic`, `tzlocal`, `gspread`, `google-auth` and `pytest` all came back at the same versions.
- [x] **`pytest` stays in the runtime image** for now. It is a test dependency shipping to production, but `README.md` and CLAUDE.md §3 both document `pip install -r requirements.txt` as the way to get a test environment, and splitting `requirements-dev.txt` changes a documented workflow for a few MB. Noted here as a deliberate choice, not an oversight.
- `pydantic` is imported directly in `backend/classes.py` but left undeclared, as `fastapi` guarantees it. Called out so the omission reads as intentional.

**Verify**: the trimmed image builds; the 82 backend tests pass; **`python sheets.py --check` still authenticates and reads the real spreadsheet** — the google stack has no other consumer, so this is the check that the trim went too far or didn't; the dashboard boots and cards work. `docker images` shows the backend image ~100MB smaller. Diff `pip freeze` before and after and confirm every removed package is one of the four expected (`google-api-python-client`, `google-auth-httplib2`, `httplib2`, `uritemplate`, plus `protobuf`/`googleapis-common-protos`) and nothing else went with them. Build twice; the second should be cache-fast.

**Verified 2026-08-01** (on the Pi, against the running compose stack):

- Trimmed image builds clean in **27s**; the pinned rebuild after it in **25s**, and a second consecutive build in **2s** (cache-fast, as expected).
- **The pin reproduces exactly**: `pip freeze | sort -f` from the container built off the pinned file is byte-identical to the file's contents.
- **82 backend tests pass, unmodified** — run in the trimmed image before pinning and again in the pinned one.
- **`python sheets.py --check` succeeds against the real spreadsheet** (user-approved, read-only scope): service account `python-api@…`, `IAN'S REQUIÉM`, `Day (1000 rows)`, `OK`. Same output as Group 3's, from an image with 9 fewer packages — the trim did not cut into the live path.
- `GET /api` returns 200 and the frontend serves 200; the dashboard boots and cards work.
- site-packages **185MB → 78MB**, backend image **436MB → 308MB**, `pip freeze` **42 → 33** packages.
- **Not verified here**: nothing outstanding for this group. The kiosk-hardware steps still owed from Group 8b (validation 20–22, 25) are unaffected by it — no boot-path file changed.

## 9. Browser kiosk session (3e) — *blocked on Group 8*

- Desktop autologin is **already enabled** on the Pi (user-confirmed) — nothing to configure. Note the dependency in `deploy/README.md` so a future re-image doesn't silently break the kiosk, and confirm it still holds during validation.
- `deploy/kiosk.sh`: wait for the dashboard URL to answer, then exec Chromium with `--kiosk`, `--noerrdialogs`, `--disable-infobars`, `--disable-session-crashed-bubble`, `--autoplay-policy=no-user-gesture-required` (Phase 4 forward-compat, per `requirements.md`), wrapped in a relaunch loop for browser-crash recovery.
- `deploy/kiosk.desktop` autostart entry pointing at the script; blank the screensaver/DPMS so the display stays on.
- Install instructions in `deploy/README.md`.

**Verify**: pull the power, plug it back in, touch nothing ⇒ the Pi lands on the full-screen dashboard with no cursor, no chrome, no login prompt. Kill Chromium ⇒ it relaunches.

## 10. Manual sync button (3f) — *unblocked (5–7 are done)*

The only frontend work in the phase. Backend first, then UI.

- **Backend**: add a `sync_sheets` case to `TaskManager.process_command` that calls `sync_day()` with the "already synced today" marker **bypassed** (see `requirements.md` § Manual sync for why the marker only gates the automatic trigger). Reuse the same guard from Group 6 so a failure returns a status instead of raising; record the attempt in `sheet_sync`. No new route — it rides the existing `POST /api`.
- **Sync path**: confirm `sync_day()` takes a flag (or equivalent) for marker-bypass rather than being duplicated. Both halves of the diff apply — this button is how a mid-day sheet deletion reaches the dashboard.
- **Frontend** (`frontend/src/app/App.tsx`): a single sync control in the header area, Radix/shadcn per tech-stack — **no new MUI**. Behavior: disabled while the request is in flight (a double-tap must not fire two imports); on completion, refresh board state the same way other commands do; show last-result feedback from the `sheet_sync` field added in Group 7. Hidden/disabled when sync is not enabled, so a dev machine shows no dead button.
- Touch-friendly hit target — this is tapped on a 10" touchscreen, not clicked with a mouse.

**Verify**: add a cell to column A, tap the button ⇒ the new card appears without a restart. Delete a cell, tap ⇒ that card disappears. Tap with the sheet unchanged ⇒ nothing changes at all. Tap with the network down ⇒ error feedback and **nothing deleted**.

## 11. Docs and spec updates

- Check off 3a–3f in `specs/roadmap.md`.
- Update `CLAUDE.md`: Phase 3 status, and the next phase pointer (Phase 4 — alarm sound).
- README: the Sheets configuration section (env vars, sharing the sheet with the service-account email, key file placement), **the one-time upgrade step — drop the old `events` and `tasks` tables (or delete `productivity.db`) before first run, since there is no migration and any cards in them are lost**, **the `Day`-tab/column-A contract and the fact that the sheet owns the cards it creates** (deleting a cell deletes the card; deleting a sheet card on the dashboard won't stick), and a pointer to `deploy/README.md` for kiosk install.
- Fold the manual walkthrough results into `validation.md`, including any intentional deviations.

**Verify**: a reader who has never seen the project can set up credentials and the kiosk from the README alone.

---

## Commit strategy

One commit per group, per CLAUDE.md §6 (`Co-Authored-By: AI` footer, group referenced in the message). Groups 2–3 may reasonably land together (config + client are useless apart); Groups 8–9 may land together as the kiosk commit; Group 10's backend command and its UI may land together since neither is useful alone. No amends.
