# Validation — Phase 0: Stabilization

## Automated

- [ ] `pytest` (new `backend/tests/`) passes in full, covering:
  - `close` command does not raise (Group 2)
  - Timer `edit` (paused and while running) does not raise and persists correct `total_elapsed`/`elapsed`/`remaining_time` (Group 2)
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
8. With a stopwatch running and a timer mid-countdown, click the header "X" (shutdown). Confirm: no `NotImplementedError` in the backend terminal, the frontend's `close` request completes successfully, the browser window/tab closes, and `docker compose ps` shows **both** the backend and frontend containers stopped (not just idling).
9. Restart the backend process (simulating a same-day Pi reboot, `date_id.txt` unchanged). Confirm the dashboard on reload shows the same cards/state as right before shutdown (per whatever behavior Group 5 settles on — document expected vs. actual explicitly if intentionally not a full restore).
10. Manually edit `date_id.txt`'s date line to yesterday's date, restart the backend. Confirm tables are cleared and Work/Misc/Waste stopwatches are recreated fresh on next frontend load.

## Merge bar

- [ ] All automated tests pass.
- [ ] All 10 manual walkthrough steps pass with no unhandled exceptions in either terminal.
- [ ] The two confirmed crash bugs (`close` command, `Timer.edit` typo) are fixed and covered by regression tests, not just manually patched.
- [ ] `ring`/`stop_ring` are no longer no-ops — `alerting` state is visibly correct after a backend restart mid-ring.
- [ ] Decisions made in Plan Group 5 (what shutdown should actually delete, if anything) are written back into `requirements.md` or `plan.md` as the final decision, so the roadmap reflects intent, not just the fix.
- [ ] Every Python file in `backend/` has a module-level docstring, and every function/method has a docstring, per Plan Group 6.
- [ ] `specs/roadmap.md` Phase 0 items (0a–0e) are checked off.
