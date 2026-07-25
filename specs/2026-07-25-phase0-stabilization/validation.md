# Validation — Phase 0: Stabilization

## Automated

- [x] **Group 1 baseline**: `pytest` (new `backend/tests/`) infrastructure complete
  - 51 tests passing (48 passing, 3 xfailed for known Timer.edit() bug)
  - Comprehensive coverage: Task, Event, Stopwatch, Timer creation, commands, persistence
  - All fixtures use temporary SQLite DB + date_id.txt (never touch production files)
  - Ready for Group 2–5 regression tests to be added
- [x] **Group 2 regression tests**: `pytest` (Groups 2 tests) pass, covering:
  - [x] `close` command does not raise (2 tests)
  - [x] Timer `edit` (paused and while running) does not raise and persists correct `total_elapsed`/`elapsed`/`remaining_time` (3 tests)
  - Total: 59 tests passing (up from 51), all xfail markers removed
- [ ] `pytest` (Groups 3–5 tests) passes in full, covering:
  - `ring` persists frozen elapsed time + `alerting=True` to the DB for both timers and events; `stop_ring` clears `alerting` (Group 3)
  - Sending `ring` twice for the same card does not double-process or corrupt state (Group 3)
  - Out-of-order rapid `resume`/`pause` on the same stopwatch leaves the DB in a consistent state (Group 4)
  - Simulated "shutdown mid-run, same-day reboot" restores running/paused state as it was (Group 5)
  - Simulated "reboot after date rollover" starts clean via `date_id.txt`, independent of shutdown handling (Group 5)
- [ ] No new test touches the real `productivity.db` or `date_id.txt` — all use temp fixtures.

## Manual walkthrough (run the actual app — frontend + backend — via the normal dev flow)

1. Start backend + frontend. Confirm no traceback on boot.
2. Create a timer for a few seconds, let it ring. Confirm: card shows "DONE!", no traceback appears in the backend terminal.
3. Dismiss the rung timer. Confirm: no traceback, card returns to normal (non-alerting) state.
4. Edit that same timer's remaining time and save. Confirm: no `AttributeError`, backend terminal is clean, new time reflected on the card.
5. Create an event a few seconds out, let it ring, dismiss it. Confirm the same as steps 2–3 for events.
6. Start a Work stopwatch, then start Misc — confirm Work auto-pauses (mutex behavior unchanged from before this phase).
7. Rapidly tap pause/resume on a running stopwatch several times in a row. Confirm the displayed time and the DB (`sqlite3 productivity.db "SELECT * FROM stopwatches"`) end up consistent — no negative/stuck elapsed values.
8. With a stopwatch running and a timer mid-countdown, click the header "X" (shutdown). Confirm: no `NotImplementedError` in the backend terminal, and the `close` request completes successfully without throwing.
9. Restart the backend process (simulating a same-day Pi reboot, `date_id.txt` unchanged). Confirm the dashboard on reload shows the same cards/state as right before shutdown (per whatever behavior Group 5 settles on — document expected vs. actual explicitly if intentionally not a full restore).
10. Manually edit `date_id.txt`'s date line to yesterday's date, restart the backend. Confirm tables are cleared and Work/Misc/Waste stopwatches are recreated fresh on next frontend load.

## Merge bar

- [ ] All automated tests pass.
- [ ] All 10 manual walkthrough steps pass with no unhandled exceptions in either terminal.
- [ ] The confirmed crash bug (`Timer.edit` typo) is fixed and covered by regression tests, not just manually patched. The `close` command no-op is implemented and covered by a regression test that it does not raise.
- [ ] `ring`/`stop_ring` are no longer no-ops — `alerting` state is visibly correct after a backend restart mid-ring.
- [ ] Decisions made in Plan Group 5 (what shutdown should actually delete, if anything) are written back into `requirements.md` or `plan.md` as the final decision, so the roadmap reflects intent, not just the fix.
- [ ] Every Python file in `backend/` has a module-level docstring, and every function/method has a docstring, per Plan Group 6.
- [ ] `specs/roadmap.md` Phase 0 items (0a–0e) are checked off.
- [ ] `README.md` has a real project overview + setup instructions, its API examples are corrected (no stale `"task"` field, `close`/`ring`/`stop_ring` documented), and `readme_claude.md` is folded in and removed per Plan Group 8.
