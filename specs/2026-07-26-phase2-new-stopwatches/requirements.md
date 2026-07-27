# Requirements — Phase 2: New Stopwatches

## Source

`specs/roadmap.md` Phase 2 — Round out tracking + stats:

- 2a. Add "Exercise" stopwatch (mutually exclusive)
- 2b. Add "Shower" stopwatch (mutually exclusive)
- 2c. Add "Fun" stopwatch (mutually exclusive)

Stats work that was originally bundled into Phase 2 (2c/2d in the prior roadmap revision) has since moved to Phase 4 (4e/4f) and is explicitly out of scope here.

Per `specs/mission.md` Pillar 1: "mutually-exclusive stopwatches for open-ended activity categories (Work, Misc, Waste, and eventually Exercise, Shower)" — this phase delivers that "eventually," plus "Fun" which the current roadmap revision adds as a fourth new category.

## Scope

All three stopwatches (Exercise, Shower, Fun) in this one branch/spec — decided over splitting into per-stopwatch specs, since they are mechanically identical additions to the same mutex group (same pattern already proven by Work/Misc/Waste).

## Current state (confirmed by reading the code)

- The backend (`backend/classes.py`, `backend/database.py`) has **no hardcoded stopwatch category names**. Stopwatches are generic label-based rows created via the `duration`/`create` message — the backend requires zero changes to support new categories.
- The frontend (`frontend/src/app/App.tsx`) is the only place category names are hardcoded:
  - `MUTEX_LABELS = ["Work", "Misc", "Waste"]` (line 20) — defines which stopwatch labels participate in mutual exclusivity.
  - The boot effect (lines 214–256) iterates `MUTEX_LABELS` and auto-creates any stopwatch that doesn't already exist in the loaded state, so the three (soon six) mutex stopwatches are always present without user action.
  - The mutex-pause logic (line 324) is generic: `if (willRun && MUTEX_LABELS.includes(card.label) && MUTEX_LABELS.includes(d.label) && d.startedAt !== null)` — pausing every other running mutex-labeled stopwatch when one starts. It already works for any list length, not just 3.
  - Duration cards render in a `flex flex-wrap` container (line 644/665), so additional cards wrap onto new rows automatically — no layout code depends on there being exactly 3.

## Decisions

- **Implementation is additive to `MUTEX_LABELS` only.** Add `"Exercise"`, `"Shower"`, `"Fun"` to the existing array. No new component, no new message type, no new DB column — reuses the exact mechanism Work/Misc/Waste already use.
- **UI layout**: keep the current layout as-is (flex-wrap grid). No redesign for 6 cards — confirmed with the user that minimal-scope, mission-aligned change is preferred over a touchscreen layout overhaul. If 6 cards visibly crowd the touchscreen during manual validation, that's a follow-up, not blocking this phase.
- **Testing**: no automated tests added for this feature, per standing project guidance (AGENTS.md §1, §3: tests are only added when explicitly requested) and explicit user confirmation for this spec. Validation is manual only (see `validation.md`).
- **Naming**: use exactly "Exercise", "Shower", "Fun" (roadmap's current wording) as the stopwatch labels — matching the capitalization convention of "Work", "Misc", "Waste".
- **Order**: new stopwatches are appended after the existing three in `MUTEX_LABELS`, so Work/Misc/Waste keep their existing left-to-right card order and Exercise/Shower/Fun appear after them (in that order) both in the boot-creation loop and in card layout (cards render in `durations` state order, which follows creation order).

## Non-goals

- No stats/analytics changes (per-category breakdown, totals) — that's Phase 4 (4e/4f).
- No Google Sheets sync (Phase 3).
- No UI redesign of the duration-card grid/layout.
- No backend schema changes — the `stopwatches` table already supports arbitrary labels.
- No changes to non-mutex stopwatch behavior or to timers/events.
