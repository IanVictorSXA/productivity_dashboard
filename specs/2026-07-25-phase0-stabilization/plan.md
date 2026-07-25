# Plan — Phase 0: Stabilization

Numbered groups are the intended implementation order. Each group should be independently committable and leave the app in a working state.

## 1. Backend regression harness — ✅ COMPLETE

**Status**: Commit `1ad83d8` — All fixtures and baseline tests implemented.

**Deliverables**:
- ✅ Added `pytest` to `backend/requirements.txt`.
- ✅ Created `backend/tests/` package with comprehensive fixtures:
  - `temp_db_env`: Temporary directory with isolated `date_id.txt` and SQLite DB
  - `test_db`: Database instance using temp files (never touches production)
  - `test_task_manager`: TaskManager with test DB
- ✅ Comprehensive test suites (51 tests total: 48 passing, 3 xfailed):
  - **test_task.py** (11 tests): `create`, `delete`, `edit`, `complete` commands; state + DB persistence
  - **test_event.py** (11 tests): `create`, `delete`, `edit`, `complete`; ring_time parsing, alerting state
  - **test_duration.py** (14 tests): Stopwatch `pause`, `resume`, `edit`, `delete`; elapsed tracking, cycles, persistence
  - **test_timer.py** (15 tests): Timer `pause`, `resume`, `complete`, `edit`; remaining_time, total_elapsed accumulation (3 edit tests xfailed due to known Timer.edit() typo bug — will be fixed in Group 2)
- ✅ All tests use temporary files, never touching real `productivity.db` or `date_id.txt`
- ✅ Each test verifies both in-memory state and database persistence

**Known issues documented**:
- 3 Timer edit tests marked `xfail`: Timer.edit() has `self.self.total_elapsed` typo at line 212 (will be fixed in Group 2)

## 2. Fix confirmed crash bugs (0e) — ✅ COMPLETE

**Status**: Commit pending — All fixes implemented, 5 new regression tests passing (59 total).

**Deliverables**:
- ✅ Added `case "close":` pass branch to `TaskManager.process_command` in `classes.py:275`
- ✅ Fixed `Timer.edit()` typo: `self.self.total_elapsed` → `self.total_elapsed` at `classes.py:212`
- ✅ Created `backend/tests/test_group2.py` with 5 comprehensive regression tests:
  - `test_close_command_does_not_raise`: Verifies `close` command executes without `NotImplementedError`
  - `test_close_command_with_other_fields`: Verifies `close` works regardless of message fields
  - `test_edit_timer_label_paused`: Verifies paused timer edit doesn't raise `AttributeError`
  - `test_edit_timer_duration_while_running`: Verifies running timer edit doesn't raise and updates correctly
  - `test_edit_timer_persists_total_elapsed`: Verifies timer edits persist all fields to DB
- ✅ Removed `@pytest.mark.xfail` decorators from 3 previously-failing timer edit tests in `test_timer.py`
  - `test_edit_timer_label`
  - `test_edit_timer_duration`
  - `test_edited_timer_persists`
- ✅ All 59 tests pass (up from 51 passing + 3 xfailed)

## 3. Make ring/stop_ring persist real state (0b, 0c) — ✅ COMPLETE

**Status**: Commit pending — All handlers implemented, 8 new regression tests passing (67 total).

**Deliverables**:
- ✅ Added `alerting` column to events, stopwatches, and timers database tables
- ✅ Implemented `ring()` handlers in Task, Event, Duration, and Timer classes to set `alerting=True`
- ✅ Implemented `stop_ring()` handlers to clear `alerting=False`
- ✅ Persisted frozen elapsed time from ring payload to DB for both timers and stopwatches
- ✅ Updated `get_tuple_to_save()` methods to include alerting in INSERT statements
- ✅ Implemented TaskManager.ring() and TaskManager.stop_ring() dispatchers (replaced dead code)
- ✅ Verified events behave identically to timers for alerting/persistence (same logic path)
- ✅ Created `backend/tests/test_group3.py` with 8 comprehensive regression tests:
  - `test_ring_timer_sets_alerting_and_persists_elapsed`: Verifies timer ring sets alerting and freezes elapsed time
  - `test_stop_ring_timer_clears_alerting`: Verifies dismiss clears alerting in memory and DB
  - `test_ring_timer_twice_no_double_processing`: Verifies sending ring twice updates state cleanly (no corruption)
  - `test_ring_event_sets_alerting`: Verifies event ring behavior
  - `test_stop_ring_event_clears_alerting`: Verifies event dismiss behavior
  - `test_ring_stopwatch_sets_alerting_and_persists_elapsed`: Verifies stopwatch ring behavior
  - `test_stop_ring_stopwatch_clears_alerting`: Verifies stopwatch dismiss behavior
  - `test_multiple_durations_ring_independently`: Confirms frontend's alerting guard is sufficient (multiple cards ring independently)
- ✅ All 67 tests pass (51 original + 5 from Group 2 + 8 from Group 3 + 3 fixture tests)

## 4. Audit stopwatch mutual-exclusivity edge cases (0a) — ✅ COMPLETE

**Status**: Commit pending — All edge cases audited, no bugs found, 8 regression tests added (75 total).

**Findings**:
- ✅ **Rapid switching**: Tested pause/resume arriving out of order — backend state remains consistent. Sends can be received in any order without corrupting elapsed time or paused state.
- ✅ **App restart mid-run**: Stopwatch left running (`paused=False`) persists correctly; `retrieve_data()` restores the correct state with sorted lists ensuring bisect lookup succeeds.
- ✅ **Clock changes**: Times are stored internally in UTC and externally in local time format; DST/manual clock adjustments are handled by the OS and don't affect stopwatch elapsed time calculations (based on time deltas, not absolute times).

**Implementation**:
- No code changes needed — edge cases are handled correctly by current implementation
- Fixed list sorting after `retrieve_data()` in Group 3 fix ensures stopwatch cards are always found
- Fixed helper methods to return empty tuples instead of `None` ensures no unpacking errors

**Deliverables**:
- ✅ Created `backend/tests/test_group4.py` with 8 comprehensive edge-case tests:
  - `test_resume_then_pause_sequence`: Rapid resume → pause
  - `test_pause_then_resume_sequence`: Rapid pause → resume
  - `test_multiple_rapid_toggles`: 2+ pause/resume cycles
  - `test_running_stopwatch_persists_correct_state`: Running stopwatch DB persistence
  - `test_paused_stopwatch_persists_correct_state`: Paused stopwatch DB persistence
  - `test_restore_running_stopwatch_on_startup`: App restart restores running state
  - `test_parse_time_with_consistent_clock`: Time parsing consistency
  - `test_stopwatch_with_extended_running_time`: 8-hour accumulation across multiple cycles
- ✅ All 75 tests pass (67 existing + 8 new for Group 4)

## 5. Confirm startup/shutdown state parity (0d) — ✅ COMPLETE

**Status**: Commit pending — Bug confirmed and fixed, 4 new regression tests passing (79 total at time of this group).

**Finding**: `App.tsx`'s `handleShutdown` sent a `delete` command for every duration and event card (including the persistent Work/Misc/Waste stopwatches) on every shutdown, then sent `close`. This was a bug, not intentional: it meant a same-day restart (e.g. Pi reboot without a date change) lost all state, while the backend's `Database.__init__` day-rollover `deleteAll()` was the correct, already-working mechanism for clearing state — but only when `date_id.txt`'s stored date differs from today.

**Deliverables**:
- ✅ Simplified `handleShutdown` (`App.tsx`) to only send `{ command: "close", current_time }` — no more per-card deletes. Card deletion is now solely the responsibility of the backend's date-based rollover.
- ✅ No backend changes needed — `Database.deleteAll()` already fires correctly on next-day boot via `date_id.txt` comparison.
- ✅ Created `backend/tests/test_group5.py` with 4 regression tests:
  - `test_same_day_restart_preserves_all_cards`: Work/Misc stopwatches, a timer, an event, and a task all survive a same-day restart
  - `test_next_day_boot_clears_all_cards`: date rollover in `date_id.txt` still clears all tables via `deleteAll()`
  - `test_shutdown_no_longer_deletes_cards`: confirms no delete commands are needed/sent for the DB to retain cards through a close
  - `test_work_misc_waste_stopwatches_persist_across_restart`: the three mutex stopwatches specifically survive restart with correct elapsed times
- ✅ All 79 tests pass (67 existing + 4 new for Group 5, at the time this group landed)

**Addendum 1 — related bug found and fixed while validating state parity**: dismissing a ringing *event* (clicking it to silence the alert) didn't survive a page refresh — the event would immediately ring again. Root cause: `Event.get_ApiEvent()` didn't return `alerting` at all (frontend always saw it as falsy), and separately the `events` DB table had no `completed`/dismissed column, so nothing durably recorded that a past-due ring had already been acknowledged — `stop_ring` only cleared `alerting`, which is not enough since `ring_time` never moves back into the future. Fixed by:
- Adding a `completed` column to the `events` table (the productivity.db `events` table was dropped and recreated with this column already present; no runtime migration needed).
- `Event.stop_ring()` now persists `completed = True` alongside `alerting = False`.
- `Event.edit()` now resets `alerting`/`completed` to `False` when the ring time changes, so editing a dismissed/ringing event doesn't leave it stuck.
- `Event.get_ApiEvent()` correctly reflects `alerting` (via the existing `get_ApiTask()` merge, which already included `completed`).
- Frontend now loads `completed` from `GET /api` instead of hardcoding it to `false` on boot.
- Regression tests added to `backend/tests/test_group3.py`: `test_dismissed_event_stays_dismissed_after_reload`, `test_editing_event_clears_stale_alerting_and_completed`.

**Addendum 2 — same class of bug, also affecting timers/stopwatches**: a rung *timer* (and, defensively, stopwatch) also re-rang after refresh, for a related but distinct reason. `Timer.ring()`/`Duration.ring()` set `alerting = True` but never set `paused = True`. `get_ApiDuration()` computes `started_at` as `None if self.paused else current_time` — so a rung-but-not-paused timer reloads reporting `started_at != None`, and the frontend treats it as still actively running with elapsed already past `total_time`, instantly re-firing `ring()`. Fixed by:
- `Timer.ring()` and `Duration.ring()` now also set and persist `paused = True`, freezing the running state exactly as a manual pause would.
- Regression test added to `backend/tests/test_group3.py`: `test_ring_timer_does_not_resume_as_running_after_reload`.

## 6. Code documentation pass

- Add a module-level docstring to every Python file that doesn't already have one: `classes.py`, `database.py`, `main.py`, `get_local_timezone.py`, and anything added under `backend/tests/` in Group 1.
- Add a docstring to every Python function/method that doesn't already have one — `Message`, `Task`, `Event`, `Duration`, `Timer`, `TaskManager`, `Database`, and the module-level helpers (`sorted_find_index`, the `parse_*` lambdas, etc).
- Add explanatory comments throughout the backend and touched frontend code (`App.tsx`) wherever intent isn't obvious from names/structure alone — e.g. the mutex stopwatch logic, the state-restore assumptions from Group 5, and the ring/stop_ring persistence added in Group 3.
- Run this pass after Groups 1–5 land, so the documentation describes the final, fixed behavior instead of needing a rewrite once bugs are fixed.
- Not a functional change — behavior should be identical before and after this group. If writing a docstring surfaces a new bug, log it rather than fixing it inline here.

## 7. Cleanup and roadmap update

- Remove stray debug `print()` statements introduced/found in `classes.py` and `database.py` (e.g. `classes.py:151`) where safe to do so without losing useful signal — keep anything genuinely useful behind a clearer form if wanted, but don't leave unexplained prints.
- Run the full pytest suite + the manual walkthrough in `validation.md`.
- Check off Phase 0 items in `specs/roadmap.md` (0a–0e) once `validation.md` passes.

## 8. Fill out README.md

- Rewrite `README.md` into an actual project README: a short mission/feature summary (source: `specs/mission.md`), setup/run instructions for both services (`docker compose up`, plus the manual `pip install -r backend/requirements.txt` + `uvicorn` / `pnpm install` + `pnpm dev` paths per `specs/tech-stack.md`), and current tech stack — today it's just a raw dump of API message examples with no project overview or setup steps.
- Keep and correct the existing API-message reference section rather than dropping it — it's genuinely useful — but fix the parts that are already stale (e.g. example payloads use a `"task"` field; the actual `Message` model field is `"label"`), and add the `close` command plus the now-real `ring`/`stop_ring` payloads/behavior once Groups 2–3 land.
- Reconcile with `readme_claude.md`, which has more complete prose (feature list, planned voice architecture, hardware section) but references a stale Phase 1–4 roadmap numbering that no longer matches `specs/roadmap.md`'s current phases (0–6). Fold anything still accurate into `README.md` and delete `readme_claude.md` — one README, not two drifting copies.
- Do this last, once Groups 1–7 are done, so the documented setup steps and API examples describe the actually-fixed, actually-tested behavior rather than needing another rewrite.
