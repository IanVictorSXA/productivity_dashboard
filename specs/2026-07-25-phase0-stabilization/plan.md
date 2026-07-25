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

## 2. Fix confirmed crash bugs (0e)

- **`close` command (backend)**: add a `case "close":` branch to `TaskManager.process_command` in `classes.py`, and have it terminate the entire backend process — this is the dashboard's actual shutdown, not just an acknowledgment. Since `App.tsx` already sends explicit `delete` for every card and awaits all of those requests before sending `close` (see `handleShutdown`), by the time `close` arrives the DB writes are already done, so the handler's only remaining job is to end the process cleanly: respond `{"success": true}` to the in-flight request first (e.g. schedule the exit via `os.kill(os.getpid(), signal.SIGTERM)` or `asyncio` callback right after responding, not a synchronous `sys.exit()` inside the handler, which would kill the response before the client sees it). `docker-compose.yml`'s backend service has no `restart` policy, so killing the process will actually stop the container rather than auto-relaunching it.
- **`close` command (frontend)**: closing the app must also terminate the frontend, in two parts — no existing mechanism does either yet:
  - *Window/tab*: after `handleShutdown` gets a successful response from the backend's `close`, call `window.close()`. Only takes effect if the kiosk browser is launched in a mode that permits script-closing a page it opened itself (e.g. Chromium `--app=... --kiosk`); note this constraint for whoever sets up the actual kiosk launcher, since it's not yet in this repo.
  - *Dev server process*: add a small custom middleware route in `frontend/vite.config.ts` (via the `configureServer` hook) — e.g. `/__shutdown` — that responds then calls `process.exit()`, so the Vite process (and its container) actually stops rather than idling forever. `handleShutdown` calls this endpoint alongside the backend `close` call. `docker-compose.yml`'s frontend service also has no `restart` policy, so this stops the container the same way the backend fix does.
- Update `requirements.md`'s finding #1 and `validation.md` step 8 to match this behavior (both processes must actually exit, not just avoid throwing) once this group lands.
- **`Timer.edit()` typo**: fix `self.self.total_elapsed` → `self.total_elapsed` at `classes.py:212`.
- Add regression tests for both: a `close` command must not raise, and editing a timer (paused and while running) must not raise and must persist the expected `total_elapsed`/`elapsed`/`remaining_time`.

## 3. Make ring/stop_ring persist real state (0b, 0c)

- Replace the `pass` no-ops in `process_command` for `"ring"` / `"stop_ring"` with real handling: set `alerting` on the matching `Task`/`Duration`/`Event`, persist the elapsed time delivered in the ring payload (timers) to the DB, and persist `alerting` so `get_ApiState()` reflects it accurately after a restart.
- Remove or wire up the dead `TaskManager.ring()` method (currently unused and a no-op) — either delete it or make `process_command`'s `"ring"` case call it with real logic, whichever reads cleaner once the above is implemented.
- Verify events behave the same as timers for this flow (roadmap 0c) — same alerting/persistence treatment, no divergent behavior unless there's a deliberate reason.
- Add regression tests: ring a timer → assert DB row shows the frozen elapsed time; ring an event → assert its alerting state persists; dismiss (`stop_ring`) → assert alerting clears in both the in-memory object and the DB.
- Double-fire check: confirm the frontend's existing `alerting` guard (`if (!e.alerting && ...)` / `if (d.subtype !== "timer" || d.alerting ...)`) is sufficient once the backend actually tracks `alerting` — add a test that sends `ring` twice for the same card and asserts no double-processing/corruption.

## 4. Audit stopwatch mutual-exclusivity edge cases (0a)

- **Rapid switching**: trace what happens if `pause`/`resume` requests arrive out of order (frontend fires-and-forgets via `sendMessage`, no request sequencing). Write a test that sends `resume` then immediately `pause` (and the reverse) for the same stopwatch and confirms the DB ends in a consistent state.
- **App restart mid-run**: a stopwatch left running (`startedAt` set, no `pause` sent) when the backend process dies — confirm `retrieve_data()` on the next boot restores a sane state (currently it replays DB rows verbatim via `create`, which doesn't reconstruct "still running" state — `current_time`/`paused` come straight from the last saved row). Document actual behavior and fix if it leaves a stopwatch either stuck running with a stale timestamp or silently frozen.
- **Clock changes**: `parse_time`/`Duration.resume()` build timestamps from `datetime.now().date()` combined with a wall-clock string — check behavior around DST transitions or a manually-adjusted system clock. This is Raspberry Pi hardware without guaranteed NTP at boot, so document the realistic risk rather than solving generalized clock-skew handling.
- Fix any bugs found; add regression tests per scenario above.

## 5. Confirm startup/shutdown state parity (0d)

- Using the fix from Group 2 (`close` no longer crashes), manually and then via test trace the full shutdown sequence in `App.tsx`'s `handleShutdown`: does it intentionally delete all cards (including the persistent Work/Misc/Waste stopwatches) on every shutdown, or is that a bug? Cross-reference against `Database`'s day-rollover `deleteAll()` — decide whether card deletion belongs in the frontend shutdown handler at all, or should only happen via the backend's date-based rollover.
- Fix whichever side is wrong so that: (a) a same-day restart (e.g. Pi reboot without a date change) restores exactly what was running/paused before, and (b) a next-day boot correctly starts fresh via the existing `date_id.txt` rollover — not via the shutdown handler nuking data early.
- Add a regression test simulating "shutdown mid-run, reboot same day" and "reboot after a date rollover" and assert the resulting DB/`get_ApiState()` output matches expectations for each.

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
