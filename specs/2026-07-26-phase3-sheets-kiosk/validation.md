# Validation — Phase 3: Google Sheets sync (read path) + kiosk autostart

## Automated

None added — per `requirements.md` (standing guidance in CLAUDE.md §1; user confirmed manual-only validation for this spec, since the real credentials, the real spreadsheet, and the Pi hardware all live on the device).

- [ ] `python -m pytest backend/tests/ -q` — the existing 82 backend tests still pass, **unmodified**. Phase 3 adds a new startup step; this proves it didn't disturb the existing card/rollover behavior. With `SHEETS_SYNC_ENABLED` unset (the test default), the import path must not run at all during tests.

## Manual walkthrough — Sheets (run on the Pi, real service account, real spreadsheet)

Run against the actual app (backend + frontend via `docker compose up`), not a scratch script, except where a step says otherwise.

### Prerequisite — drop the old tables (one time, before section B)

There is **no migration code** by design (`requirements.md` § Schema changes). Before the first run of the Group 5 build, drop the old `events` and `tasks` tables on the Pi — or delete `productivity.db` outright — so `CREATE TABLE IF NOT EXISTS` rebuilds them with `source` and `sheet_key`. **Any cards in those tables are lost**, so do it on an empty board.

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

### B. Start-of-day sync (3b, 3c)

4. Set `date_id.txt`'s date line to yesterday and restart the backend. Confirm: yesterday's cards are wiped by the existing rollover, **and** the events and tasks from column A of the `Day` tab appear on the dashboard.
5. Compare card-by-card against column A: every non-empty cell is present, with the right label, the right type (**event vs. task only** — no timer or stopwatch was created from a cell), and the right time on events. Nothing missing, nothing extra.
6. Restart the backend again, same day. Confirm **no duplicates** and the log says the sync was skipped (already synced today).
7. Add a cell to column A, then restart the backend. Confirm it is **not** picked up (the day is already marked done) — intended: the automatic trigger is once-per-day, and mid-day edits are the manual button's job (section D).
8. Create a card by hand on the dashboard, then restart the backend. Confirm the hand-made card survives untouched.
9. Put a deliberately malformed cell in column A, clear today's `sheet_sync` marker, restart. Confirm the other cells still sync, the bad cell is logged with its row number, and — critically — **no card was deleted** because of it.
10. Confirm provenance survives a restart: after a sync, restart the backend and check that sheet-origin cards still carry `source = 'sheet'`, so a later sheet deletion can still remove them (section D exercises this).

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

## Manual walkthrough — kiosk autostart (3e)

**Group 8b changed the boot sequence (2026-08-01), so steps 20–22 and 25 must be re-run against the new unit.** The unit no longer builds on boot, and `ExecStop` is now `docker compose stop` rather than `down`. Already confirmed on the Pi without a reboot: `systemctl restart` brings both services up in **4s** with no build and no container recreation (was 156–176s), and a daemon-restart proxy for a power cut brings the containers back in **4s** via `unless-stopped` alone. What still needs the real hardware event: an actual `sudo reboot`, an actual power cut, and `docker kill` against the new unit. See plan.md § 8b "What the measurements changed".

20. `sudo reboot`, with no keyboard or mouse attached. Confirm the Pi reaches the full-screen dashboard unattended: the already-configured autologin still lands in the desktop session, both containers come up, and Chromium opens in kiosk mode with no address bar, tabs, cursor, or infobar.
21. **Power-cut test**: pull power mid-session, restore it, touch nothing. Confirm the same end state as 20, and that the cards from before the cut are still there (local state survived).
22. `docker kill` the backend container. Confirm it restarts on its own and the dashboard recovers without a manual page reload beyond what the frontend already does.
23. Kill Chromium. Confirm the wrapper relaunches it into kiosk mode.
24. Confirm the screen does not blank or sleep after idling (screensaver/DPMS disabled).
25. Confirm the boot ordering holds: the browser does not sit on a connection-error page because it raced the backend — repeat the reboot 2–3 times to catch a race.
26. Confirm no traceback in `docker compose logs backend` and no error in the browser console across steps 20–25.

## D. Manual walkthrough — manual sync button (3f)

Run these on the touchscreen, tapping — not with a mouse on a desktop browser.

27. With today already auto-synced, add a cell to column A, then tap the sync button. Confirm the new card appears **without restarting the backend** — this is the whole point of the control.
28. **Deletion propagates**: delete a cell from column A, tap sync. Confirm the corresponding card disappears from the dashboard. This is the core of the user's requirement.
29. **Local cards are safe**: create a card by hand on the dashboard, then tap sync (with that item absent from column A, which it is). Confirm the hand-made card is **not** deleted — only `source = 'sheet'` cards are eligible.
30. **Timers and stopwatches are safe**: with the six mutex stopwatches present and a local timer running, tap sync. Confirm none of them are created, deleted, paused, or reset, and the running stopwatch keeps its elapsed time.
31. Tap the button again with the sheet unchanged. Confirm **nothing changes at all** — no new cards, no deletions. The marker is bypassed on this path, so the diff is the only guard; this step is what proves it.
32. Double-tap the button quickly. Confirm only one sync runs (the control disables itself while the request is in flight) and no duplicates or spurious deletions result.
33. **State is preserved**: complete an imported task and dismiss a rung imported event, then tap sync with those cells still in column A. Confirm the task stays completed and the event stays dismissed — a matched card must not be rewritten or resurrected.
34. **Edit reads as delete + create**: change the text of a cell, tap sync. Confirm the old card is gone and a new one appears with the new text — expected per `requirements.md`, not a bug.
35. **Locally deleting a sheet card does not stick**: delete a sheet-origin card on the dashboard, then tap sync with its cell still in column A. Confirm it comes back — the sheet is the source of truth; the documented fix is to delete the cell. Confirm this is what the README says.
36. Disconnect the network and tap sync. Confirm the button reports a failure, the UI does not hang, and **every card is still present** — no deletions. Reconnect, tap again, confirm it succeeds.
37. Clear column A entirely, tap sync. Confirm all sheet-origin cards are removed and local cards/timers/stopwatches remain — the deliberate "nothing scheduled today" case. Restore the sheet contents and sync again to confirm they come back.
38. With `SHEETS_SYNC_ENABLED` false, confirm the button is hidden or disabled — no dead control on a dev machine.

## Merge bar

- [ ] Cell grammar captured in `requirements.md` § Sheet shape (Group 1, asked at the start of Group 4) — the spec no longer contains the open-input checklist.
- [ ] All of 3a–3f checked off in `specs/roadmap.md`.
- [ ] Steps 1–38 above pass, with any intentional deviation documented in this file rather than silently accepted.
- [ ] Existing 82 backend tests pass unmodified.
- [x] **Both dependency trees are pinned and reproducible** (Groups 8b/8c): `frontend/package-lock.json` and `backend/requirements.txt` are committed and generated, `backend/requirements.in` holds the declared list, and a rebuild reproduces the pinned set exactly. Confirmed 2026-08-01.
- [ ] **No credential material committed**: no JSON key, no `.env`, no spreadsheet id hardcoded in tracked source. Verify with `git log -p` over the branch before merging.
- [ ] Read-only scope confirmed in code — nothing in this branch can write to the spreadsheet (Phase 7 owns the write path).
- [ ] **No failure path can delete a card** (step 18 — the highest-risk check in the phase).
- [ ] Only `source = 'sheet'` events and tasks are ever deleted by a sync; local cards, timers, and stopwatches are untouchable by it (steps 29–30).
- [ ] A Sheets failure never blocks startup or loses local cards (steps 11–19 all pass).
- [ ] `source`/`sheet_key` are declared in `CREATE TABLE IF NOT EXISTS` only — **no `ALTER TABLE` or `PRAGMA` migration code anywhere in the branch** — and the required table drop is documented in the README and the Group 5 commit message (§ Prerequisite).
- [ ] Provenance survives a backend restart (step 10).
- [ ] `CLAUDE.md` updated with Phase 3 status and Phase 4 as next.
- [ ] README documents credential setup, the `Day`/column-A contract, the sheet-owns-its-cards rule, and points to `deploy/README.md` for kiosk install.
- [ ] Manual sync is idempotent (step 31) and never rewrites a matched card's state (step 33).
- [ ] The sync button is the only new UI in the phase, built with Radix/shadcn — no new MUI usage introduced (tech-stack rule).
- [ ] No scope creep beyond `requirements.md` — no write-back to the spreadsheet, no stats, no alarm sound (beyond the Chromium autoplay flag), no automatic mid-day polling.
