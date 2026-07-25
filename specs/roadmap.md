# Roadmap

Phases are kept intentionally small — each one should be shippable and testable on its own before moving to the next. Order within a phase group is the intended implementation order, not just a checklist.

## Phase 0 — Stabilization (current)

The core loop (timers, stopwatches, events, persistence) is functionally built, but known bugs remain. Do this before starting new feature work.

- [x] Audit stopwatch mutual-exclusivity logic for edge cases (rapid switching, app restart mid-run, clock changes) — no bugs found (Group 4)
- [x] Verify timer ring/acknowledge flow can't get stuck or double-fire — fixed `ring`/`stop_ring` no-ops (Group 3) and a rung timer resuming as "running" after reload (Group 5 addendum)
- [x] Verify event countdown + acknowledgment behaves the same as timers where expected — fixed dismissed events re-ringing after reload (Group 5 addendum)
- [x] Confirm state restore on startup matches state at last shutdown (no drift/loss) — fixed shutdown deleting all cards instead of only the day-rollover doing so (Group 5)
- [x] Fix any bugs found above; add lightweight regression checks where practical — 82 backend tests passing across Groups 1–5

See `specs/2026-07-25-phase0-stabilization/` for the detailed plan, requirements, and validation status per group. Groups 6 (docstrings), 7 (debug-print cleanup), and 8 (README rewrite) are documentation/quality passes still in progress before Phase 0 is fully closed out and the full `validation.md` manual walkthrough is signed off.

## Phase 1 — Core (done)

- [x] React frontend
- [x] FastAPI backend
- [x] SQLite persistence
- [x] Timers
- [x] Stopwatches
- [x] Events

## Phase 2 — Round out tracking + stats

- [ ] **2a.** Add "Exercise" stopwatch (5th mutually-exclusive category)
- [ ] **2b.** Add "Shower" stopwatch
- [ ] **2c.** Daily stats: include exercise/shower time and total tracked time in the existing stats view
- [ ] **2d.** Daily stats: compute and display a simple per-category breakdown (no scoring yet)

## Phase 3 — Google Sheets sync

- [ ] **3a.** Implement OAuth consent flow + token storage/refresh on the backend
- [ ] **3b.** End-of-day job: upload that day's stats to a Google Sheet
- [ ] **3c.** Start-of-day job: load the day's schedule from Sheets into the dashboard
- [ ] **3d.** Start-of-day job: load events from Sheets into the dashboard
- [ ] **3e.** Handle failure paths (no network, expired token, sheet unreachable) without losing local data

## Phase 4 — Historical analytics

- [ ] **4a.** Daily productivity score (simple formula: e.g. work vs. waste ratio)
- [ ] **4b.** Weekly summary view
- [ ] **4c.** Monthly trend view
- [ ] **4d.** Historical charts (recharts) sourced from Sheets history

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
