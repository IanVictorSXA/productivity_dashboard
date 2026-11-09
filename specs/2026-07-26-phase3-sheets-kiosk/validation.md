# Validation — Phase 3: Google Sheets sync (read path) + kiosk autostart

## Automated

None added — per `requirements.md` (standing guidance in CLAUDE.md §1; user confirmed manual-only validation for this spec, since the real credentials, the real spreadsheet, and the Pi hardware all live on the device).

- [x] `python -m pytest backend/tests/ -q` — the existing 82 backend tests still pass, **unmodified**.
  - **Confirmed again after Group 7 (2026-08-18)**: 82 passed, unmodified. Group 7 changes the `GET /api` response shape, so this is the check that no existing test asserted on its exact key set.
  - **Confirmed again after Group 6 (2026-08-18)**: 82 passed, unmodified, in the container. Group 6 touches `main.py` (a `logging.basicConfig` call) and `classes.py` (the outer sync guard), so this is the check that the guard did not change any card behavior.
  - **Confirmed after Group 5 (2026-08-18)**: 82 passed, run in the container. Group 5 is the change this check exists for — it adds a startup step and two columns to `events`/`tasks` — and it disturbed nothing. `SHEETS_SYNC_ENABLED` is unset in the test environment, and `TaskManager.sync_sheets()` checks that flag *before* importing `sheets`, so the suite never loads `gspread` or reaches the network. Phase 3 adds a new startup step; this proves it didn't disturb the existing card/rollover behavior. With `SHEETS_SYNC_ENABLED` unset (the test default), the import path must not run at all during tests.

## Manual walkthrough — Sheets (run on the Pi, real service account, real spreadsheet)

Run against the actual app (backend + frontend via `docker compose up`), not a scratch script, except where a step says otherwise.

### Prerequisite — drop the old tables (one time, before section B)

There is **no migration code** by design (`requirements.md` § Schema changes). Before the first run of the Group 5 build, drop the old `events` and `tasks` tables on the Pi — or delete `productivity.db` outright — so `CREATE TABLE IF NOT EXISTS` rebuilds them with `source` and `sheet_key`. **Any cards in those tables are lost**, so do it on an empty board.

**This is a prerequisite of the build, not just of enabling sync** (measured 2026-08-18). With old-shape tables, *any* card creation raises `sqlite3.OperationalError: table tasks has no column named source` — including a card the user makes by hand, since `get_tuple_to_save()` names the new columns unconditionally. Group 6's guard wraps the sync only, so it does not cover that. At the time Group 5 landed, the Pi's `events` and `tasks` were both **empty (0 rows)**, so the drop cost nothing.

Then confirm two things before continuing:

- The recreated tables have both columns (`PRAGMA table_info(events)` / `(tasks)`), and the dashboard boots and creates a card by hand normally.
- **The un-dropped case degrades safely**: on a *copy* of the old database, start the backend with sync enabled and confirm the missing-column error is logged and swallowed — the app still boots, local cards are intact, and nothing was deleted. Restore the correct database afterward. This is the check that the prerequisite being skipped can't cost data.

### A. Auth and sharing (3a)

1. **[x]** With the key file mounted and `SHEETS_SYNC_ENABLED=true`, run the standalone check from Group 3 (`python sheets.py --check`). Confirm it prints the service-account email and the spreadsheet's title.
   - **Done (Group 3, 2026-07-28)**, by the user via `docker compose run --rm backend python sheets.py --check` — the in-container run, so the compose mount and env wiring are proven, not just the credential. Printed the service-account email, `IAN'S REQUIÉM`, and `Day`.
   - Prerequisite discovered here: the backend image predated the Group 2 `requirements.txt` change, so the first run failed with `ModuleNotFoundError: No module named 'gspread'`. **`docker compose build backend` is required after any backend dependency change** — the `./backend:/app` bind mount carries source, not site-packages. Noted for the Group 8 systemd unit, which must not run a stale image.
   - **Re-run 2026-08-01 after Group 8c's dependency trim** and passed identically (same service account, `IAN'S REQUIÉM`, `Day (1000 rows)`), from an image with `google-api-python-client` and its subtree removed — 9 fewer packages, 436MB → 308MB. `sheets.py` is the google stack's only consumer, so this run is what proves the trim stopped in the right place.
   - Also confirmed (config/auth failure half of section C, standalone rather than via app startup): unset `SHEETS_KEY_FILE`, wrong key path, `/dev/null` key, valid-JSON-but-not-a-service-account key, unset `SHEETS_SPREADSHEET_ID`, wrong spreadsheet id, and wrong tab name each print their own typed message and exit 1. Steps 11–18 still have to be re-run through the real app once the sync path exists.
2. **[x]** Un-share the spreadsheet from the service account, re-run the check. Confirm it reports a 403 and names the service-account email to share with — not a raw traceback. Re-share before continuing.
   - **Done (Group 3, 2026-07-28)**: un-shared ⇒ `SheetsAccessError` with the "share it with `python-api@…`" hint, no traceback; re-shared ⇒ the check succeeds again. This was the last unexercised branch in `sheets.py`.
3. **[x]** Confirm `git status` shows no key file and no `.env` as untracked-but-addable content — i.e. `.gitignore` covers them.
   - **Done (2026-07-28)**: `.env.example` is the only credential-adjacent tracked file; neither the key JSON nor `.env` appears as untracked-addable.

### A2. Cell parsing (3b, 3c) — Group 4, before any card is created

These run through `python sheets.py --dump` rather than the dashboard, because nothing imports the parser at runtime until Group 5. They are the evidence that the cards section B is about to compare are being *read* correctly in the first place.

3a. **[x]** `docker compose exec backend python sheets.py --dump` against the real spreadsheet ⇒ the printed items match a human read of column A, row for row.
   - **Done (Group 4, 2026-08-01)**: **15 items, 0 skipped** from 24 rows. Two events — `A2 event 'sun lunch'`, `A3 event 'plan, self check, reflect, read'` — and 13 tasks at A4–A24. A1 (`645am`, the wake-up time) and all seven blank cells skipped. Row numbers in the output line up with the sheet.
3b. **[x]** Event ring times land on the wall-clock time written in the cell, in the **user's** timezone.
   - **Done (2026-08-01)**, and this is the check that caught a real bug: the container runs UTC while `date_id.txt` says `America/Chicago`, so the obvious reuse of `classes.parse_time` would have rung `1pm sun lunch` at 08:00 local. Converting each parsed `ring_time` back to `America/Chicago` now gives 13:00 and 22:00 CDT — the times in the cells. See plan.md Group 4 for the fix (`database.get_timezone()`).
3c. **[x]** A malformed cell is skipped with its row number logged, and its neighbours still parse.
   - **Done (2026-08-01)** against **synthetic** cells, not the live sheet — deliberately, so the user's real spreadsheet was never edited to manufacture a failure: `25pm broken` (bad hour), `9:75am broken` (bad minute), `3pm` (time with no label) each skipped with `A<row>` and a reason at WARNING, with the cells above and below still parsed. Step 9 below re-runs this end-to-end through the app once Group 5 exists.
3d. **[x]** A failed read returns "could not read", never "the column is empty".
   - **Done (2026-08-01)** with a stub worksheet raising a network error and `APIError` 403/404/500 — all four give `ok=False`, `items=[]`, and a typed message naming the fix. This is the Group 4 half of the phase's highest-risk property (merge bar: "no failure path can delete a card"); the other half is step 18, once the diff exists.
3e. **[x]** No cell can produce a timer or a stopwatch.
   - **Done (2026-08-01)**: `SheetItem.type` is only ever `"event"` or `"task"`. Confirmed against the duration-looking real cell `bath, bed, timers 8h` and the digit-leading `5, 10, 15 reps`, both of which parse as plain tasks.

### A3. Reconciliation logic (3b, 3c) — Group 5, off-device

Steps 4–10 below need the real sheet and the Pi. These are what was provable without either: a 33-check harness run in a temp directory with `sheets.read_day` stubbed to return synthetic `SheetRead` objects — **no credentials, no network, the live spreadsheet never touched, and production `productivity.db` never opened**. They are not a substitute for section B; they are the reason section B is expected to pass on the first run.

3f. **[x]** Schema is as specified: `events`/`tasks` carry `source` and `sheet_key`; `sheet_sync` is `(date, status, detail, synced_at)` and is **not** in `Database.tables`. Rolling `date_id.txt` to an old date and restarting wipes the cards and **leaves the marker**, which is the property that whole exclusion exists for.
3g. **[x]** A synthetic column A (2 events, 2 tasks, 1 unparseable cell) syncs to `created 3, deleted 0, past 1, unparsed 1`: the future event and both tasks created, the past event skipped, `bath, bed, timers 8h` created as a **task** — no stopwatch, no timer.
3h. **[x]** Re-running the same day is blocked by the marker (no duplicates); a restart reloads the cards with `source = 'sheet'` and `sheet_key` intact, and `get_ApiTask()` exposes both. This is the off-device half of step 10.
3i. **[x]** A completed imported task and a dismissed imported event both survive a `force=True` re-sync unchanged, alongside an untouched hand-made local card — the off-device half of steps 29 and 33.
3j. **[x]** Removing one cell deletes exactly that card and nothing else; a successfully-read **empty** column A deletes both remaining sheet cards while the local card survives.
3k. **[x]** **A failed read (`ok=False`) deletes nothing** — the board comes back byte-identical and the existing `ok` marker is not overwritten. Group 4's step 3d proved the read reports failure honestly; this proves the diff acts on it. Step 18 is still the real-hardware version of this check.

### B. Start-of-day sync (3b, 3c)

4. Set `date_id.txt`'s date line to yesterday and restart the backend. Confirm: yesterday's cards are wiped by the existing rollover, **and** the events and tasks from column A of the `Day` tab appear on the dashboard.
5. Compare card-by-card against column A: every non-empty cell is present, with the right label, the right type (**event vs. task only** — no timer or stopwatch was created from a cell), and the right time on events. Nothing missing, nothing extra.
5a. **Past events are skipped, not created** (user decision, 2026-08-01 — `requirements.md` § Import behavior). With a cell whose event time is earlier *today* (the real `645am`-style case: clear today's `sheet_sync` marker and restart in the afternoon), confirm **no card is created for it**, no alarm fires, the log names it as skipped-because-past *separately from malformed cells*, and every other cell in column A still syncs normally.
5b. **Future events on the same run are unaffected.** In the same run as 5a, confirm an event later today (e.g. the `10pm` cell) **is** created with the right time — the skip must be per-event, not a switch that turns off event creation once one is past.
5c. **A task is never skipped for being "late."** Confirm the tasks in column A all appear regardless of the hour the sync runs — the rule applies to ring times only, and tasks have none.
6. Restart the backend again, same day. Confirm **no duplicates** and the log says the sync was skipped (already synced today).
7. Add a cell to column A, then restart the backend. Confirm it is **not** picked up (the day is already marked done) — intended: the automatic trigger is once-per-day, and mid-day edits are the manual button's job (section D).
8. Create a card by hand on the dashboard, then restart the backend. Confirm the hand-made card survives untouched.
9. Put a deliberately malformed cell in column A, clear today's `sheet_sync` marker, restart. Confirm the other cells still sync, the bad cell is logged with its row number, and — critically — **no card was deleted** because of it.
10. Confirm provenance survives a restart: after a sync, restart the backend and check that sheet-origin cards still carry `source = 'sheet'`, so a later sheet deletion can still remove them (section D exercises this).

### C0. Failure paths (3d) — Group 6, off-device

Same shape as A3, and for the same reason: steps 11–18 need the Pi and the real credentials, and these are what was provable without either. A 33-check harness in a temp directory with `sheets.read_day` stubbed — **no credentials, no network, the live spreadsheet never touched, and production `productivity.db` never opened**.

11a. **[x]** All six matrix causes (config unset, key file missing, key malformed, network, 403 unshared, 404 wrong id/tab) ⇒ error status, **nothing created or deleted**, and the `sheet_sync` row carries the cause *with the fix named in the text* ("share it (Viewer is enough) with python-api@…", "check SHEETS_SPREADSHEET_ID"), not a traceback.
11b. **[x]** The day is **not** marked done by a failure, and an `error` row does not gate the next automatic run — while an `ok` row still does. This is the retryability property; step 15 is its real-hardware version.
11c. **[x]** `import sheets` failing (the stale-image `ModuleNotFoundError` from step 1's prerequisite) ⇒ error status, `TaskManager()` still constructs. This is the failure the inner guard structurally cannot catch.
11d. **[x]** An unanticipated exception from inside the sync — a bare `RuntimeError`, and `sqlite3.OperationalError: table tasks has no column named source` — is caught by the same guard, logged with a traceback, and leaves the board unchanged. The second is the un-dropped-tables case from the prerequisite above, confirmed to degrade safely rather than needing the old database on hand.
11e. **[x]** The marker write itself failing, and `db.get_date()` itself failing, both stay swallowed: no exception escapes, and the latter reports `date: None`.
11f. **[x]** An unparseable cell keeps its card (`created 0, deleted 0, past 0, unparsed 1`) — now structural, since the delete pass diffs against every non-empty cell rather than the parsed ones. A successfully-read **empty** column A still deletes sheet cards and keeps local ones: the only path to mass deletion, and still the only one.
11g. **[x]** Log visibility, measured in the container: under uvicorn's config the root logger has no handler and sits at WARNING, so every `logger.info` in the sync path was being dropped and its warnings printed with no level or timestamp. After the `basicConfig` in `main.py`, the sync's INFO and WARNING lines both appear with timestamp, level, and logger name, and uvicorn's own lines still appear exactly once.

### C. Failure paths (3d) — after every step here, the dashboard must still boot, local cards must be intact, and **nothing may have been deleted**

11. `SHEETS_SYNC_ENABLED` unset ⇒ no sync, no errors, behavior identical to pre-Phase-3.
12. Key file path wrong / file removed ⇒ logged, app starts normally.
13. Key file corrupted (truncate the JSON) ⇒ logged, app starts normally.
14. Pi's network disconnected ⇒ logged, app starts normally, startup is not noticeably delayed (the timeout holds), and the day is **not** marked synced.
15. After 14, reconnect the network and restart ⇒ the sync now runs and succeeds (proving failures stay retryable).
16. Wrong `SHEETS_SPREADSHEET_ID` ⇒ 404 logged naming the id, app starts normally.
17. `Day` tab renamed/missing ⇒ logged naming the tab, app starts normally.
18. **The deletion guard**: with sheet-origin cards on the dashboard, re-run steps 12–17 one at a time and confirm after each that **every sheet-origin card is still present**. A failed read must never be mistaken for an emptied column A. This is the single most important check in the phase — a bug here silently destroys the day's agenda.
19. `GET /api` returns the `sheet_sync` object with a sensible status in both a success case and one failure case; the frontend renders normally and the browser console shows no error from the extra field.
    - **Off-device half done (Group 7, 2026-08-18)**, in the same harness: the field is present and correct for `disabled`, for all six failure causes (`error`, carrying the typed message), for a successful run, and for a same-day restart — which still reports today's counts rather than just the word "skipped". The response's key set is exactly the four originals plus `sheet_sync`. On the **live** backend, `GET /api` ⇒ 200 with `"sheet_sync": {"date": null, "status": "disabled", "detail": "SHEETS_SYNC_ENABLED is false"}`, which is the correct dev-machine state. `App.tsx` types the response structurally and never validates it at runtime, so the extra key cannot throw — but the console half still wants a real browser, which is what remains of this step alongside the success/failure cases over the real sheet.

## Manual walkthrough — kiosk autostart (3e)

**Group 8b changed the boot sequence (2026-08-01), so steps 20–22 and 25 must be re-run against the new unit.** The unit no longer builds on boot, and `ExecStop` is now `docker compose stop` rather than `down`. Already confirmed on the Pi without a reboot: `systemctl restart` brings both services up in **4s** with no build and no container recreation (was 156–176s), and a daemon-restart proxy for a power cut brings the containers back in **4s** via `unless-stopped` alone. What still needs the real hardware event: an actual `sudo reboot`, an actual power cut, and `docker kill` against the new unit. See plan.md § 8b "What the measurements changed".

20. `sudo reboot`, with no keyboard or mouse attached. Confirm the Pi reaches the full-screen dashboard unattended: the already-configured autologin still lands in the desktop session, both containers come up, and Chromium opens in kiosk mode with no address bar, tabs, cursor, or infobar.
21. **Power-cut test**: pull power mid-session, restore it, touch nothing. Confirm the same end state as 20, and that the cards from before the cut are still there (local state survived).
22. `docker kill` the backend container. Confirm it restarts on its own and the dashboard recovers without a manual page reload beyond what the frontend already does.
23. Kill Chromium (`pkill -f dashboard-kiosk`). Confirm the wrapper relaunches it into kiosk mode within ~5s.
24. Confirm the screen does not blank or sleep after idling (screensaver/DPMS disabled).
25. Confirm the boot ordering holds: the browser does not sit on a connection-error page because it raced the backend — repeat the reboot 2–3 times to catch a race.
26. Confirm no traceback in `docker compose logs backend` and no error in the browser console across steps 20–25.

**Group 9 (2026-08-18) — what was provable without taking over the screen.** Launching a full-screen browser would have hijacked the display the user was sitting in front of, so the kiosk itself was not started from here; `kiosk.sh --check` exists precisely so the rest could be checked:

26a. **[x]** `bash -n` clean; `--check` against the running stack prints `browser: /usr/bin/chromium`, both URLs answering, the exact command line, and exits 0.
26b. **[x]** `--check` with the backend pointed at a dead port names that URL as not ready and exits 1; a bad argument exits 2 with usage.
26c. **[x]** **It waits rather than launching.** With the backend URL pointed at a dead port the script blocked for 70s, logged its once-a-minute "still waiting" line at exactly 60s, and **no Chromium process ever started** — the readiness gate is real, not decorative.
26d. **[x]** Host facts confirmed on the device rather than assumed: the session is **labwc on Wayland** (`labwc -m`, so the user autostart is additive), the binary is `/usr/bin/chromium` (no `chromium-browser` on trixie), autologin is `--autologin team` on `getty@tty1` with `graphical.target` default, and **screen blanking is already off** — no `swayidle` line in `~/.config/labwc/autostart`, no `swayidle` process.

**Found on real-hardware reboot (2026-11-08), step 20 above**: autologin never unlocks the system keyring (no login password is entered), so Chromium's first touch of `libsecret` — its password manager / cookie-encryption key — blocked step 20 on an "unlock default keyring" dialog with no keyboard to answer it. Fixed by adding `--password-store=basic` to `chromium_arguments()` in `kiosk.sh`, which keeps that state in the kiosk's own profile dir instead of asking the OS keyring. `--check` confirms the flag reaches the command line; re-running step 20 from a cold `sudo reboot` is the only way to confirm the dialog itself is gone. See `deploy/README.md` § "Unlock default keyring" prompt.

## D. Manual walkthrough — manual sync button (3f)

**Confirmed by the user (2026-11-08)**, against the real app and the real spreadsheet: reported as tested and working, as one overall "works just fine" rather than broken out against the 12 cases below. Also confirmed separately: the 82-test backend suite still passes unmodified after Group 10's change.

**Code-level walkthrough (2026-11-08), done in response to the user asking for it directly, against `backend/sheets.py`/`classes.py` and `frontend/src/app/App.tsx` as committed in Group 10.** This is a *different kind of check* than the live walkthrough above — tracing each numbered case against the actual branches in the code, not tapping the button — and is reported as that, not conflated with it (CLAUDE.md §8). It cannot catch what only shows up at runtime (gspread's real network behavior, React re-render timing, browser quirks); the user's live pass above is still what covers that. No live sheet or credentials were used for this pass.

Run these on the touchscreen, tapping — not with a mouse on a desktop browser.

27. **[x]** With today already auto-synced, add a cell to column A, then tap the sync button. Confirm the new card appears **without restarting the backend** — this is the whole point of the control.
    - The button's `onClick` (`App.tsx`) posts `{command: "sync_sheets"}`, which `process_command` (`classes.py`) routes to `self.sync_sheets(force=True)` → `sheets.sync_day(force=True)`. With `force=True`, `_reconcile` (`sheets.py:337-348`) skips the "already synced today" marker check entirely, so it re-reads column A regardless of today's status. `_apply_diff` (`sheets.py:294-319`) creates a card for any `read.items` entry whose key isn't already in `owned` — a new cell is exactly that. The handler then re-`GET`s `/api` and replaces `events`/`tasks` from the response, so the new card renders without a page reload or backend restart.
28. **[x]** **Deletion propagates**: delete a cell from column A, tap sync. Confirm the corresponding card disappears from the dashboard. This is the core of the user's requirement.
    - `_apply_diff`'s delete loop (`sheets.py:281-292`): for every sheet-owned card whose `sheet_key` is no longer in `read.cells`, it sends a `delete` command, which removes it from `task_manager.events`/`tasks` in memory (`classes.py:618-628`, `del sorted_ids[index]`) and sets `deleted = 1` in the DB. The next `GET /api` the frontend fetches after the sync no longer lists it.
29. **[x]** **Local cards are safe**: create a card by hand on the dashboard, then tap sync (with that item absent from column A, which it is). Confirm the hand-made card is **not** deleted — only `source = 'sheet'` cards are eligible.
    - `_sheet_cards` (`sheets.py:243-256`) builds `owned` by filtering to `card.source == "sheet"` only. A hand-made card defaults to `source = "local"` (`Message.source` default, `classes.py:69`), so it's never in `owned` and the delete loop never iterates over it — structurally invisible to the diff, not just untouched by luck.
30. **[x]** **Timers and stopwatches are safe**: with the six mutex stopwatches present and a local timer running, tap sync. Confirm none of them are created, deleted, paused, or reset, and the running stopwatch keeps its elapsed time.
    - `_sheet_cards` only reads `task_manager.tasks` and `task_manager.events` (`sheets.py:252`) — `task_manager.durations` (which holds both timers and stopwatches) is never referenced anywhere in `sheets.py`. `SheetItem.type` is also only ever `"event"` or `"task"` (`sheets_parse.py`, confirmed in Group 4). Two independent reasons the diff can't touch a duration. On the frontend, the manual-sync handler only calls `setEvents`/`setTasks` after a sync — `setDurations` isn't called, so a running stopwatch's local state (and its live elapsed-time computation, which never depends on a re-fetch) is untouched by the sync round-trip itself.
31. **[x]** Tap the button again with the sheet unchanged. Confirm **nothing changes at all** — no new cards, no deletions. The marker is bypassed on this path, so the diff is the only guard; this step is what proves it.
    - Every cell's key is already in `owned` (`sheets.py:298`, `if item.key in owned: continue` — no create) and every owned card's key is still in `read.cells` (`sheets.py:286`, `if key in read.cells: continue` — no delete). `created, deleted, past` all come out `0`.
32. **[x]** Double-tap the button quickly. Confirm only one sync runs (the control disables itself while the request is in flight) and no duplicates or spurious deletions result.
    - `handleSyncSheets` sets `syncing = true` as its first statement, before any `await`; the shadcn `Button` forwards `disabled={syncing}` straight onto the native `<button>` element (`button.tsx`, `{...props}`), and a browser does not dispatch `click` to a `disabled` button at all — this is enforced by the DOM, not just app logic. Belt-and-suspenders: even without that guard, the diff itself is idempotent per step 31, so two overlapping sync requests can't produce duplicates or spurious deletes — at worst, two network round-trips to Google for one user action.
33. **[x]** **State is preserved**: complete an imported task and dismiss a rung imported event, then tap sync with those cells still in column A. Confirm the task stays completed and the event stays dismissed — a matched card must not be rewritten or resurrected.
    - The creation loop's only check for a matched key is `if item.key in owned: continue` (`sheets.py:298`) — it skips straight past matched items with no further read or write. Nothing in `_apply_diff` ever calls `edit`/`complete`/`stop_ring` on an existing card, so `completed`/`alerting` set by the user earlier are never touched by a sync.
33a. **[x]** **The past-event rule must never delete.** Late in the day, with events that have already rung still on the board and their cells still in column A, tap sync. Confirm those cards are **still there** — the skip rule governs creation only.
    - `_has_passed` (`sheets.py:259-265`) is only called inside the *creation* loop (`sheets.py:301`), gating whether a new card gets created. The *deletion* loop (`sheets.py:281-292`) never calls it and deletes purely on "is this card's key still in `read.cells`" — a rung event's cell is still there, so it's never a deletion candidate regardless of what time it is.
34. **[x]** **Edit reads as delete + create**: change the text of a cell, tap sync. Confirm the old card is gone and a new one appears with the new text — expected per `requirements.md`, not a bug.
    - The cell text is the only key (`item.key`/`card.sheet_key`). Editing it means the old text is no longer in `read.cells` (old card deleted, step 28's path) and the new text isn't yet in `owned` (new card created, step 27's path) — both halves of the same diff, run in the same pass, so both legs necessarily fire together.
35. **[x]** **Locally deleting a sheet card does not stick**: delete a sheet-origin card on the dashboard, then tap sync with its cell still in column A. Confirm it comes back.
    - Deleting it removes it from `task_manager.events`/`tasks` (`classes.py:618-628`), so `_sheet_cards` no longer sees it in `owned` on the next sync. Its cell is still in `read.cells`, so the creation loop's `if item.key in owned` is false — it gets created again, as a new card with a new id. README documents this as the expected fix-is-in-the-sheet behavior (§ "Google Sheets sync").
36. **[x]** Disconnect the network and tap sync. Confirm the button reports a failure, the UI does not hang, and **every card is still present**.
    - A network failure surfaces as `read.ok = False` from `read_day()`; `_reconcile` (`sheets.py:351-360`) returns the `error` status *before* calling `_apply_diff` at all — there is no code path from a failed read to a deletion. `handleSyncSheets`'s `try/finally` always runs `setSyncing(false)` even if `sendMessage`/`fetchState` throw, so the button always re-enables (never hangs), and the failure shows up as `sheet_sync.status === "error"` (red button, detail in the tooltip) on the next fetch.
37. **[x]** Clear column A entirely, tap sync. Confirm all sheet-origin cards are removed and local cards/timers/stopwatches remain.
    - With `read.cells` empty, every owned card's key is absent from it, so the deletion loop (`sheets.py:286-292`) removes all of them; the creation loop has no items to create. Local cards were already shown unreachable in step 29, durations in step 30 — this is the same code path, just with `owned` fully emptied rather than partially.
38. **[x]** With `SHEETS_SYNC_ENABLED` false, confirm the button is hidden — no dead control on a dev machine.
    - `_run_sheet_sync` returns `status: "disabled"` immediately when the flag is false (`classes.py:459-463`), before `sheets` is even imported. The header button's render guard is `{sheetSync && sheetSync.status !== "disabled" && (...)}` (`App.tsx`) — `disabled` is the one status value that unconditionally hides it, matching every dev machine's default.

## Merge bar

- [x] Cell grammar captured in `requirements.md` § Sheet shape (Group 1, asked at the start of Group 4) — the spec no longer contains the open-input checklist. **Done 2026-08-01**: questions asked before any Group 4 code, answers written up as a grammar plus a worked-example table, both checked against a read-only dump of the real column A.
- [x] All of 3a–3f checked off in `specs/roadmap.md`. **Done 2026-11-08.**
- [ ] Steps 1–38 above pass, with any intentional deviation documented in this file rather than silently accepted. **Partially**: the off-device sub-checks (3a–3k, 11a–11g, 26a–26d) are individually verified; the on-hardware numbered steps 4–26 were run across earlier groups but most aren't individually checked off in this file (a pre-existing gap, not introduced by Group 10). **Steps 27–38 are now itemized** against both the user's live 2026-11-08 run and a 2026-11-08 code-level trace of each case — see section D.
- [x] Existing 82 backend tests pass unmodified. **Re-confirmed after Group 10, 2026-11-08.**
- [x] **Both dependency trees are pinned and reproducible** (Groups 8b/8c): `frontend/package-lock.json` and `backend/requirements.txt` are committed and generated, `backend/requirements.in` holds the declared list, and a rebuild reproduces the pinned set exactly. Confirmed 2026-08-01.
- [x] **No credential material committed**: no JSON key, no `.env`, no spreadsheet id hardcoded in tracked source. **Verified 2026-11-08** — `git ls-files` has no `.env`/key-shaped filename, and no tracked diff contains `private_key`/`client_email`.
- [x] Read-only scope confirmed in code — nothing in this branch can write to the spreadsheet (Phase 7 owns the write path). `sheets.py` only ever calls read methods (`get_all_values`); no `gspread` write call appears anywhere in the backend.
- [x] **No failure path can delete a card** (step 18 — the highest-risk check in the phase). Off-device equivalent (11f, 11d) passed; the manual-sync half is covered by step 36's code trace (`_reconcile` returns before `_apply_diff` on any failed read); step 18 itself (the automatic-sync path on real hardware) still isn't individually itemized here.
- [x] Only `source = 'sheet'` events and tasks are ever deleted by a sync; local cards, timers, and stopwatches are untouchable by it (steps 29–30). Code-traced 2026-11-08 — see section D.
- [x] **Events whose ring time has passed are skipped at creation and never deleted for it** (steps 5a–5c and 33a). Off-device equivalent passed (A3); the manual-sync half code-traced 2026-11-08 (step 33a).
- [ ] A Sheets failure never blocks startup or loses local cards (steps 11–19 all pass). Off-device equivalent (C0) passed; the manual-sync half is covered by step 36; steps 11–19 (the automatic/startup path on real hardware) still aren't individually itemized here.
- [x] `source`/`sheet_key` are declared in `CREATE TABLE IF NOT EXISTS` only — **no `ALTER TABLE` or `PRAGMA` migration code anywhere in the branch** — and the required table drop is documented in the README (§ "One-time upgrade step") and the Group 5 commit message.
- [x] Provenance survives a backend restart (step 10 off-device equivalent, 3h/3i, passed).
- [x] `CLAUDE.md` updated with Phase 3 status and Phase 4 as next. **Done 2026-11-08 (Group 11).**
- [x] README documents credential setup, the `Day`/column-A contract, the sheet-owns-its-cards rule, and points to `deploy/README.md` for kiosk install. **Done 2026-11-08 (Group 11).**
- [x] Manual sync is idempotent (step 31) and never rewrites a matched card's state (step 33). Code-traced 2026-11-08 — see section D.
- [x] The sync button is the only new UI in the phase, built with Radix/shadcn — no new MUI usage introduced (tech-stack rule). The Group 10 button uses the existing shadcn `Button` (`@/app/components/ui/button`); no `@mui/*` import was added.
- [x] No scope creep beyond `requirements.md` — no write-back to the spreadsheet, no stats, no alarm sound (beyond the Chromium autoplay flag), no automatic mid-day polling.
