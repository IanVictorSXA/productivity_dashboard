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
- [x] **Group 3 regression tests**: `pytest` (Group 3 tests) pass, covering:
  - [x] `ring` persists frozen elapsed time + `alerting=True` to the DB for both timers and events; `stop_ring` clears `alerting` (8 tests)
  - [x] Sending `ring` twice for the same card does not double-process or corrupt state
  - Total: 67 tests passing
- [x] **Group 4 regression tests**: `pytest` (Group 4 tests) pass, covering:
  - [x] Out-of-order rapid `resume`/`pause` on the same stopwatch leaves DB in consistent state (3 tests)
  - [x] App restart with stopwatch mid-run restores correct state (3 tests)
  - [x] Clock change behavior verified (DST/manual adjustments handled correctly) (2 tests)
  - Total: 75 tests passing (up from 67), all Group 4 tests pass, no bugs found
- [x] **Group 5 regression tests**: `pytest` (Group 5 tests) pass, covering:
  - [x] Simulated "shutdown mid-run, same-day reboot" restores running/paused state as it was (4 tests)
  - [x] Simulated "reboot after date rollover" starts clean via `date_id.txt`, independent of shutdown handling
  - [x] (Addendum) Dismissed events stay dismissed after reload; editing a ringing/dismissed event resets its alerting/completed state — 2 additional tests in `test_phase0_group3.py`
  - [x] (Addendum) A rung timer/stopwatch no longer reloads as "still running" and re-fires ring — 1 additional test in `test_phase0_group3.py`
  - Total: 82 tests passing
- [x] No new test touches the real `productivity.db` or `date_id.txt` — all use temp fixtures.

## Manual walkthrough (run the actual app — frontend + backend — via the normal dev flow)

1. Start backend + frontend. Confirm no traceback on boot.
2. Create a timer for a few seconds, let it ring. Confirm: card shows "DONE!", no traceback appears in the backend terminal. Refresh the page while it's still ringing — confirm it still shows "DONE!" and does not silently reset to a running countdown.
3. Dismiss the rung timer. Confirm: no traceback, card returns to normal (non-alerting), paused state. Refresh the page — confirm it stays dismissed (does not ring again).
4. Edit that same timer's remaining time and save. Confirm: no `AttributeError`, backend terminal is clean, new time reflected on the card.
5. Create an event a few seconds out, let it ring, dismiss it. Confirm the same as steps 2–3 for events, including that a refresh after dismissal does not re-ring it.
6. Start a Work stopwatch, then start Misc — confirm Work auto-pauses (mutex behavior unchanged from before this phase).
7. Rapidly tap pause/resume on a running stopwatch several times in a row. Confirm the displayed time and the DB (`sqlite3 productivity.db "SELECT * FROM stopwatches"`) end up consistent — no negative/stuck elapsed values.
8. With a stopwatch running and a timer mid-countdown, click the header "X" (shutdown). Confirm: no `NotImplementedError` in the backend terminal, and the `close` request completes successfully without throwing.
9. Restart the backend process (simulating a same-day Pi reboot, `date_id.txt` unchanged). Confirm the dashboard on reload shows the same cards/state as right before shutdown — Group 5 settled on a full restore: shutdown no longer deletes any cards, so a same-day restart must show exactly what was running/paused before.
10. Manually edit `date_id.txt`'s date line to yesterday's date, restart the backend. Confirm tables are cleared and Work/Misc/Waste stopwatches are recreated fresh on next frontend load.

## Merge bar

- [x] All automated tests pass (82 tests, `python -m pytest backend/tests/ -q`).
- [ ] All 10 manual walkthrough steps pass with no unhandled exceptions in either terminal. (Not re-run since Group 5; Groups 6–7 changed no frontend/card-logic behavior. Recommend a full re-run before final Phase 0 sign-off.)
- [x] The confirmed crash bug (`Timer.edit` typo) is fixed and covered by regression tests, not just manually patched. The `close` command no-op is implemented and covered by a regression test that it does not raise.
- [x] `ring`/`stop_ring` are no longer no-ops — `alerting` state is visibly correct after a backend restart mid-ring.
- [x] Decisions made in Plan Group 5 (what shutdown should actually delete, if anything) are written back into `requirements.md` or `plan.md` as the final decision, so the roadmap reflects intent, not just the fix. **Decision**: shutdown deletes nothing; card clearing is exclusively the day-rollover's responsibility.
- [x] Every Python file in `backend/` has a module-level docstring, and every function/method has a docstring, per Plan Group 6.
- [x] `specs/roadmap.md` Phase 0 items (0a–0e) are checked off.
- [x] `README.md` has a real project overview + setup instructions, its API examples are corrected (no stale `"task"` field, `close`/`ring`/`stop_ring` documented), and `readme_claude.md` is folded in and removed per Plan Group 8.
