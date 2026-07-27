# Plan — Phase 2: New Stopwatches

Numbered groups are the intended implementation order. Each group should be independently committable and leave the app in a working state. Given the small, mechanical scope (see `requirements.md`), this may reasonably land as a single commit — groups are still separated below so each is independently verifiable.

## 1. Add Exercise, Shower, Fun to `MUTEX_LABELS` (2a, 2b, 2c) — ✅ COMPLETE

**Change**: `frontend/src/app/App.tsx` line 20:

```ts
const MUTEX_LABELS = ["Work", "Misc", "Waste"];
```
becomes
```ts
const MUTEX_LABELS = ["Work", "Misc", "Waste", "Exercise", "Shower", "Fun"];
```

**Why this is sufficient**: every behavior that needs to exist for a mutex stopwatch already keys off this array —
- Boot-time auto-creation (lines 238–249) creates any missing `MUTEX_LABELS` entry as a fresh stopwatch on first load.
- Mutex pause-on-start logic (line 324) already checks `MUTEX_LABELS.includes(...)` for both the card being started and every other card, generically, for any array length.
- Card rendering (`durations.map(...)`, flex-wrap layout) has no dependency on category count.

No other file needs to change. No backend change — stopwatch rows are generic label/elapsed/paused records with no hardcoded category logic.

**Deliverable**: one-line array edit; new stopwatches appear on next app load (existing browser session needs a refresh, or the app needs a restart, to pick up the new boot-creation list — same as any `MUTEX_LABELS` change).

## 2. Manual verification (no automated tests, per requirements.md) — ✅ COMPLETE

Full manual walkthrough in `validation.md` signed off by the user directly. Note: this sandbox's frontend `node_modules` were not installed, so the agent could not itself run `pnpm build`/`pnpm dev` to exercise the walkthrough — verification was performed outside this session.

## 3. Update specs and roadmap — ✅ COMPLETE

- Checked off 2a, 2b, 2c in `specs/roadmap.md`.
- `specs/mission.md` already updated (by the user) to list Fun alongside Exercise/Shower under Pillar 1.
