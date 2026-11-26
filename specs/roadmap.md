# Roadmap

Phases are kept intentionally small — each one should be shippable and testable on its own before moving to the next. Order within a phase group is the intended implementation order, not just a checklist.

## Phase 0 — Stabilization (done)

The core loop (timers, stopwatches, events, persistence) is functionally built, but known bugs remain. Do this before starting new feature work.

- [x] Audit stopwatch mutual-exclusivity logic for edge cases (rapid switching, app restart mid-run, clock changes) — no bugs found (Group 4)
- [x] Verify timer ring/acknowledge flow can't get stuck or double-fire — fixed `ring`/`stop_ring` no-ops (Group 3) and a rung timer resuming as "running" after reload (Group 5 addendum)
- [x] Verify event countdown + acknowledgment behaves the same as timers where expected — fixed dismissed events re-ringing after reload (Group 5 addendum)
- [x] Confirm state restore on startup matches state at last shutdown (no drift/loss) — fixed shutdown deleting all cards instead of only the day-rollover doing so (Group 5)
- [x] Fix any bugs found above; add lightweight regression checks where practical — 82 backend tests passing across Groups 1–5

- [x] Full `validation.md` manual browser walkthrough (10 steps) re-run and passing — user-verified 2026-07-26

See `specs/2026-07-25-phase0-stabilization/` for the detailed plan, requirements, and validation status per group. All groups (1–8) are complete and the manual walkthrough has been signed off, so Phase 0 is closed.

## Phase 1 — Core (done)

- [x] React frontend
- [x] FastAPI backend
- [x] SQLite persistence
- [x] Timers
- [x] Stopwatches
- [x] Events

## Phase 2 — Round out tracking + stats (done)

- [x] **2a.** Add "Exercise" stopwatch (mutually exclusive)
- [x] **2b.** Add "Shower" stopwatch (mutually exclusive)
- [x] **2c.** Add "Fun" stopwatch (mutually exclusive)

See `specs/2026-07-26-phase2-new-stopwatches/` for plan, requirements, and validation.

## Phase 3 — Google Sheets sync (read path, service account) + kiosk autostart (done)

Auth uses a **Google Cloud service account**, not an OAuth user-consent flow: the spreadsheet is shared with the service account's email, and the backend authenticates with a locally-stored key file. There is no interactive login step and no refresh-token dance, which is what makes the unattended start-of-day job viable on a headless Pi.

Kiosk autostart (**3e**) is unrelated to Sheets but shares the same theme — the station should come up ready to use with no human intervention.

- [x] **3a.** Service-account auth on the backend: key file stored on-device (never committed), sheet shared with the service account email, authenticated client available to the app
- [x] **3b.** Start-of-day job: load the day's tasks from Sheets into the dashboard
- [x] **3c.** Start-of-day job: load events from Sheets into the dashboard

  Source shape: a single tab named `Day`, column A only, where each non-empty cell is either an event or a task. Timers and stopwatches are never imported. The sheet is the source of truth for the cards it creates — a cell removed from column A removes the matching card from the dashboard.

- [x] **3d.** Handle failure paths (no network, missing/invalid key, sheet unreachable or unshared) without losing local data
- [x] **3e.** Kiosk mode starts automatically on every Pi 5 boot: backend and frontend services come up on their own, and the browser opens the dashboard full-screen with no chrome — no keyboard, mouse, or login step needed. Must survive a power cut, and recover if the browser or a service crashes.
- [x] **3f.** Manual sync button on the dashboard: re-run the reconciliation on demand, for when the day's agenda is edited in the sheet after the morning's automatic sync. Applies both additions and deletions; never touches cards the user created on the dashboard.

The end-of-day upload of stats to Sheets moved to Phase 8, where the stats it writes are actually defined.

See `specs/2026-07-26-phase3-sheets-kiosk/` for plan, requirements, and validation. Closed out 2026-11-08, user-verified on the real app and spreadsheet.

## Phase 4 — Alarm sound

- [x] **4a.** Reset button in the dashboard header (third button, top right, labelled "RST"): one tap-again-to-confirm action that removes the user-created timers and stopwatches, zeroes the six default stopwatches, deletes every event and task, then re-pulls the day from Google Sheets
- [x] **4b.** Standalone test script that just plays the alarm sound for a short period — proves the sound asset and playback path work on the real Pi hardware before wiring it into any app logic
- [x] **4c.** Play an audible ring when a timer's countdown reaches zero
- [x] **4d.** Play the same ring when an event reaches its ring time
- [x] **4e.** Sound keeps playing (or repeats) until the alert is dismissed, and stops on dismissal
- [x] **4f.** Sound asset bundled locally — no network fetch at ring time

Stopwatches count up and have no zero to reach, so they are out of scope here. See `specs/2026-11-08-phase4-alarm-sound/` for plan, requirements, and validation; the fresh-kiosk first ring was heard by the user (2026-11-15); a real reboot was also run and the next event rang (2026-11-15) — see `validation.md` § F. Per-card muting of the sound arrived in Phase 5 (**5d**).

## Phase 5 — Dashboard layout & ordering

Presentation-layer work on the existing cards: manual ordering by a grip handle, stable layout, muting, and order that survives a restart. No new tracking categories. Stopwatches and timers share one "Tasks Duration" list, so 5a/5b are one drag mechanism. **Cards never move by themselves** — the earlier "promotion" idea (old 5e) was dropped on 2026-11-25 in favour of a red pause button.

- [x] **5a.** Drag-to-reorder stopwatches by a grip handle (the six-dot icon the task rows already have), with a mouse **or a finger** on the touchscreen
- [x] **5b.** Drag-to-reorder timers, same handle and mechanism
- [x] **5c.** Cards keep a fixed size — a card must not grow or shrink as the numbers inside it change (e.g. `09:59` → `10:00`, or crossing into hours)
- [x] **5d.** Mute toggle on timers and events: a clickable mute icon on the card, persisted. Muted cards make no sound but still blink/alert visually and still require dismissal. (Stopwatches get theirs in Phase 6.)
- [x] **5e.** A running stopwatch or timer shows a **red** pause button, so what is running is visible at a glance. Replaces "play/resume promotion": no card ever moves by itself, only by the user's drag
- [x] **5f.** Events are always sorted by increasing ring time (soonest first). Events are **not** manually reorderable; their order is derived from their times
- [x] **5g.** Tasks marked complete move to the end of the task list
- [x] **5h.** Order is persisted, so stopwatches, timers, and tasks come back in the same order after a reload or backend restart (this also fixes the task `reorder` command, which the backend never implemented)
- [x] **5i.** Each event shows, below its countdown, the hour and minute it will ring, in small gray print
- [x] **5j.** Fix: task reorder works by finger on the touchscreen (today it only works with a mouse); tasks use the same drag mechanism as the duration cards

See `specs/2026-11-25-phase5-dashboard-ordering/` for plan, requirements, and validation (branch `phase5-dashboard-ordering`).

## Phase 6 — Goals, limits & sheet cards

Timers and stopwatches gain optional targets, a choice of exclusivity, and a second source: the Google Sheet. Decisions already made are recorded in `specs/2026-11-25-phase5-dashboard-ordering/requirements.md` § Handed to later phases; the **timer-goal display** and the **sheet-cell disambiguation** still need to be asked when this phase starts.

- [ ] **6a.** "Mutually exclusive" checkbox on timer and stopwatch creation, ticked by default: one pool — starting any exclusive card pauses every other running exclusive card
- [ ] **6b.** Optional **maximum** on a stopwatch (less is better): time left and the maximum shown below the time in small gray print; reaching it plays one short negative chime, no dismissal, and turns the outline red while the stopwatch keeps running
- [ ] **6c.** Optional **goal** on a timer (more is better): time elapsed and the goal shown below the time in small gray print; reaching it plays one short positive chime, no dismissal, and turns the outline green (exact display behaviour to be settled)
- [ ] **6d.** Mute button on stopwatches that have a maximum
- [ ] **6e.** Load timers and stopwatches from the Google Sheet alongside tasks and events: a cell ending in a duration is a timer (`work 2h`), one ending in a duration plus `max` is a stopwatch (`shower 30m max`), anything else is a task

## Phase 7 — Custom alert sounds

- [ ] **7a.** Replace the placeholder negative and positive chimes (Phase 6) with chosen sounds
- [ ] **7b.** Decide whether the main alarm sound is also customizable, and per what (to be scoped when the phase starts)

## Phase 8 — Historical analytics

Includes the end-of-day Sheets upload (which lived in Phase 3 before it was renumbered) — writing history is grouped with the analytics that consume it, so the schema is designed once.

- [ ] **8a.** End-of-day job: upload that day's stats to a Google Sheet
- [ ] **8b.** Daily stats: include exercise/shower/fun time and total tracked time in the existing stats view
- [ ] **8c.** Daily stats: compute and display a simple per-category breakdown (no scoring yet)
- [ ] **8d.** Daily productivity score (simple formula: e.g. work vs. waste ratio)
- [ ] **8e.** Weekly summary view
- [ ] **8f.** Monthly trend view
- [ ] **8g.** Historical charts (recharts) sourced from Sheets history

## Phase 9 — Local AI

- [ ] **9a.** Local LLM running on the AI HAT+2
- [ ] **9b.** Daily AI-generated productivity report
- [ ] **9c.** Smart productivity recommendations based on historical trends

## Parked — Voice (no phase number yet)

Voice control is still the mission's long-term goal (`mission.md`, pillar 4), but it was retired from the numbered plan on 2026-11-25 to make room for dashboard polish, analytics and local AI first. Nothing below is scheduled; a number will be assigned when it is picked up again, most likely after Phase 9, since natural-language voice builds on the local LLM.

- [ ] **Wake-word detection** running locally on the Pi
- [ ] **Speech-to-text pipeline** (Whisper) wired to the wake-word trigger
- [ ] **Predefined command set:** start/pause/resume a stopwatch by name
- [ ] **Predefined command set:** create a timer/event ("create a meeting in 30 minutes") — needs its own decisions on naming an event and speaking a time
- [ ] **Audible/visual confirmation** of recognized commands
- [ ] **Natural-language intent detection** replacing/extending the predefined command set (needs 9a)
- [ ] **Voice query support** (e.g. "how much have I worked today?", "what's on my schedule?") (needs 9a)

The predefined-command half already has a written spec (`specs/2026-11-15-phase5-voice-commands/`, formerly Phase 5) and mic/wake-word/Whisper probe scripts, committed on branch `phase5-voice-commands` and not merged. Phase 9 (Local AI) does not depend on any of it.
