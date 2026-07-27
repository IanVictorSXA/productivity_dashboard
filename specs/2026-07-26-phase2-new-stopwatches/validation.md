# Validation — Phase 2: New Stopwatches

## Automated

None — per `requirements.md`, no automated tests are added for this feature (standing project guidance: tests only added when explicitly requested; user confirmed skipping tests for this spec). The existing 82 backend tests must still pass unmodified, since no backend code changes:

- [ ] `python -m pytest backend/tests/ -q` still shows all existing tests passing (proves this change is frontend-only and made no backend regression).

## Manual walkthrough (run the actual app — frontend + backend — via the normal dev flow)

1. Stop any running frontend/backend. Delete or rename the local `productivity.db` (or start from a fresh `date_id.txt` day) so boot-time auto-creation runs from empty state. Start backend + frontend.
2. On first load, confirm all 6 mutex stopwatches appear: **Work, Misc, Waste, Exercise, Shower, Fun** — in that left-to-right order — each starting at 0:00, not running.
3. Start **Exercise**. Confirm it begins counting up and no other stopwatch starts.
4. Start **Shower**. Confirm Exercise auto-pauses (freezes its elapsed time) and Shower begins counting up — mutex behavior extends correctly to the new categories, not just the original 3.
5. Start **Work** (one of the original 3). Confirm Shower auto-pauses. Confirms the mutex group is a single set of 6, not two separate groups of 3.
6. Start **Fun**, then rapidly tap pause/resume a few times. Confirm the displayed time stays consistent (no negative/stuck values) — same check as the Phase 0 stopwatch audit, now exercised against a new label.
7. With Fun running, refresh the page (same-day restart). Confirm Fun reloads still running with correct accumulated elapsed time, and the other 5 stopwatches reload in their prior state (paused, with correct frozen elapsed times).
8. Confirm the card layout: with 6 stopwatch cards plus any active timers/events, cards wrap onto additional rows cleanly with no overlap or horizontal scroll cutoff on the touchscreen viewport (or browser window sized to the target 10" touchscreen resolution).
9. Confirm no traceback appears in the backend terminal and no console error appears in the browser dev tools throughout steps 1–8.

## Merge bar

- [ ] `specs/roadmap.md` Phase 2 items 2a, 2b, 2c are checked off.
- [ ] `MUTEX_LABELS` in `frontend/src/app/App.tsx` includes all 6 labels: Work, Misc, Waste, Exercise, Shower, Fun.
- [ ] All 9 manual walkthrough steps above pass with no unhandled exceptions in either terminal.
- [ ] Existing backend test suite (82 tests) still passes unmodified, confirming no backend regression from a frontend-only change.
- [ ] No stats/UI-layout scope creep beyond what's described in `requirements.md` (no per-category breakdown, no Sheets sync, no card-grid redesign).
