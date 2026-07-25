# Requirements — Phase 0: Stabilization

## Source

`specs/roadmap.md` Phase 0 (current phase, all items unchecked):

- 0a. Audit stopwatch mutual-exclusivity logic for edge cases (rapid switching, app restart mid-run, clock changes)
- 0b. Verify timer ring/acknowledge flow can't get stuck or double-fire
- 0c. Verify event countdown + acknowledgment behaves the same as timers where expected
- 0d. Confirm state restore on startup matches state at last shutdown (no drift/loss)
- 0e. Fix any bugs found above; add lightweight regression checks where practical

Per `specs/mission.md`, this device is trusted to run continuously and hold state across restarts with near-zero maintenance attention — Phase 0 exists to make that trustworthy before Phase 2 (new tracking categories) adds more surface area.

## Scope

All of Phase 0 (0a–0e) in this one branch/spec — decided over splitting into a stopwatch-only subset, since the roadmap groups these as one shippable unit and the confirmed bugs below touch timers, events, and shutdown/restore together.

## Decisions

- **Regression checks**: introduce `pytest` for the backend (currently no test framework anywhere in the repo). Add it to `backend/requirements.txt`. Tests exercise `TaskManager.process_command` and `Database` directly (no HTTP layer needed — `main.py` is a thin FastAPI wrapper). Frontend gets no new test tooling in this phase; audit findings there are covered by the manual walkthrough in `validation.md`.
- **Known-bug-driven, not blind audit**: the user reported "Python throws an error when a timer/stopwatch card or event rings." Investigation (see below) found the ring/stop_ring handlers are actually no-ops and can't throw — the real crashes live in two adjacent paths a user hits in the same session. Both are treated as confirmed, in-scope bugs, not hypothetical edge cases.
- No new features. Exercise/Shower stopwatches, Sheets sync, analytics, and voice are explicitly Phase 2+ and out of scope here.

## Confirmed findings (reproduced directly against `backend/classes.py`)

1. **Shutdown always crashes the backend.** `App.tsx` `handleShutdown` sends `{ command: "close", current_time: ... }` on every click of the header "X" button. `TaskManager.process_command`'s `match msg.command` has no `"close"` case, so it falls into `case _: raise NotImplementedError(...)`. This fires on effectively every session close — directly relevant to 0d (state restore) since the crash happens before/during the save-then-close sequence.
   - **Decision**: `"close"` should do more than just avoid crashing — it should actually terminate both the backend and the frontend, since the "X" button is the dashboard's real power-off, not just a card-clearing step. That means: the backend process exits, the frontend's browser window/tab closes (`window.close()`), and the frontend's own Vite dev server process also exits (via a small `configureServer` shutdown route, since nothing today lets one process kill the other). `docker-compose.yml` has no `restart` policy on either service, so both containers actually stop rather than relaunching. See `plan.md` Group 2 for the implementation approach (respond to in-flight requests before exiting).
2. **Editing a running or paused timer always crashes.** `Timer.edit()` (`classes.py:212`) references `self.self.total_elapsed` (typo — extra `self.`), raising `AttributeError: 'Timer' object has no attribute 'self'` on every timer edit-save. Directly relevant to 0b (a ringing timer is commonly edited/reused afterward) and 0e.
3. **`ring` / `stop_ring` are literal no-ops server-side** (`case "ring": pass`, `case "stop_ring": pass`, and `TaskManager.ring()` is dead code that's never called). Consequences:
   - The `alerting` flag is never persisted — `Task.__init__` sets `self.alerting = False` once and nothing ever updates it, so `Timer.get_ApiDuration()`'s `alerting=self.alerting` is always `False` regardless of frontend state.
   - The elapsed time captured at the moment of ringing (sent in the `ring` payload) is discarded — never written to the DB. If the backend restarts while a timer/event is mid-ring, that elapsed time and the ringing state are both lost on restore.
   - Directly relevant to 0b, 0c, and 0d.
4. **Day-rollover + shutdown interaction is unverified.** `Database.__init__` calls `deleteAll()` when `date_id.txt`'s stored date differs from today, wiping all tables (including the persistent Work/Misc/Waste stopwatches). Combined with finding #1 (shutdown crashes before the delete-then-close sequence in `App.tsx` completes), it's unconfirmed whether a normal end-of-day shutdown leaves the DB in the state the next startup expects. Needs explicit audit under 0a/0d.
5. **Leftover debug output**: `Duration.get_ApiDuration()` has a stray `print(started_at)` (`classes.py:151`); multiple other `print()` debug statements exist throughout `classes.py`/`database.py`. Not a bug, but noise to clean up while touched files are open (0e).

## Non-goals

- No changes to Phase 2+ features (Exercise/Shower, Sheets sync, analytics, voice).
- No frontend redesign or new UI framework work beyond what's needed to fix the confirmed bugs (e.g., the `close` payload shape, or sending an `edit` payload that doesn't trigger the `self.self` path).
- No ORM introduction — stay with hand-written `sqlite3` per `specs/tech-stack.md`.
- No CI/deployment pipeline changes; pytest is added for local/manual use only in this phase.
