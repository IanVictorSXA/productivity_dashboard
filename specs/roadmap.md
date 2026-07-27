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

See `specs/2026-07-25-phase0-stabilization/` for the detailed plan, requirements, and validation status per group. All groups (1–8) are complete and the manual walkthrough has been signed off, so Phase 0 is closed. **Phase 3 is the next phase to start.**

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

## Phase 3 — Google Sheets sync (read path, service account) + kiosk autostart

Auth uses a **Google Cloud service account**, not an OAuth user-consent flow: the spreadsheet is shared with the service account's email, and the backend authenticates with a locally-stored key file. There is no interactive login step and no refresh-token dance, which is what makes the unattended start-of-day job viable on a headless Pi.

Kiosk autostart (**3e**) is unrelated to Sheets but shares the same theme — the station should come up ready to use with no human intervention.

- [ ] **3a.** Service-account auth on the backend: key file stored on-device (never committed), sheet shared with the service account email, authenticated client available to the app
- [ ] **3b.** Start-of-day job: load the day's schedule from Sheets into the dashboard
- [ ] **3c.** Start-of-day job: load events from Sheets into the dashboard
- [ ] **3d.** Handle failure paths (no network, missing/invalid key, sheet unreachable or unshared) without losing local data
- [ ] **3e.** Kiosk mode starts automatically on every Pi 5 boot: backend and frontend services come up on their own, and the browser opens the dashboard full-screen with no chrome — no keyboard, mouse, or login step needed. Must survive a power cut, and recover if the browser or a service crashes.

The end-of-day upload of stats to Sheets moved to Phase 7, where the stats it writes are actually defined.

## Phase 4 — Alarm sound

- [ ] **4a.** Play an audible ring when a timer's countdown reaches zero
- [ ] **4b.** Play the same ring when an event reaches its ring time
- [ ] **4c.** Sound keeps playing (or repeats) until the alert is dismissed, and stops on dismissal
- [ ] **4d.** Sound asset bundled locally — no network fetch at ring time

Stopwatches count up and have no zero to reach, so they are out of scope here. Per-card muting of the sound is Phase 8 (**8d**).

## Phase 5 — Voice: predefined commands

- [ ] **5a.** Wake-word detection running locally on the Pi
- [ ] **5b.** Speech-to-text pipeline (Whisper) wired to the wake word trigger
- [ ] **5c.** Predefined command set: start/pause/resume a stopwatch by name
- [ ] **5d.** Predefined command set: create a timer/event ("create a meeting in 30 minutes")
- [ ] **5e.** Audible/visual confirmation of recognized commands

## Phase 6 — Voice: natural language + local AI

- [ ] **6a.** Local LLM running on the AI HAT+2
- [ ] **6b.** Natural-language intent detection replacing/extending the predefined command set
- [ ] **6c.** Voice query support (e.g. "how much have I worked today?", "what's on my schedule?")
- [ ] **6d.** Daily AI-generated productivity report
- [ ] **6e.** Smart productivity recommendations based on historical trends

## Phase 7 — Historical analytics

Includes the end-of-day Sheets upload (which lived in Phase 3 before it was renumbered) — writing history is grouped with the analytics that consume it, so the schema is designed once.

- [ ] **7a.** End-of-day job: upload that day's stats to a Google Sheet
- [ ] **7b.** Daily stats: include exercise/shower/fun time and total tracked time in the existing stats view
- [ ] **7c.** Daily stats: compute and display a simple per-category breakdown (no scoring yet)
- [ ] **7d.** Daily productivity score (simple formula: e.g. work vs. waste ratio)
- [ ] **7e.** Weekly summary view
- [ ] **7f.** Monthly trend view
- [ ] **7g.** Historical charts (recharts) sourced from Sheets history

## Phase 8 — Dashboard interaction & ordering

Presentation-layer work on the existing cards: manual ordering, stable layout, muting, and order that survives a restart. No new tracking categories.

- [ ] **8a.** Drag-to-reorder stopwatches within the stopwatch section
- [ ] **8b.** Drag-to-reorder timers within the timer section
- [ ] **8c.** Cards keep a fixed size — a card must not grow or shrink as the numbers inside it change (e.g. `09:59` → `10:00`, or crossing into hours)
- [ ] **8d.** Mute toggle on timers and events: a clickable mute icon on the card. Muted cards make no sound but still blink/alert visually and still require dismissal
- [ ] **8e.** Play/resume promotion: starting or resuming a stopwatch or timer moves it toward the front of its section — placed immediately after the last card that is already running, or first if nothing is running
- [ ] **8f.** Events are always sorted by increasing ring time (soonest first). Events are **not** manually reorderable; their order is derived from their times
- [ ] **8g.** Tasks marked complete move to the end of the task list
- [ ] **8h.** Order is persisted, so stopwatches, timers, and tasks come back in the same order after a reload or backend restart
