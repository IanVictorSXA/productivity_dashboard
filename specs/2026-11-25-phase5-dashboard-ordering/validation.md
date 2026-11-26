# Validation — Phase 5: Dashboard layout & ordering

How we know this phase works and can merge. Nothing is run yet (spec written 2026-11-25). Run it against the real app, and for anything involving a finger, on the **real Pi touchscreen** — not a mouse standing in for one.

## Merge bar

The user chose these as blockers (2026-11-25). All must pass before merging:

1. **Finger drag on the touchscreen** — stopwatches, timers **and tasks** can be reordered by finger from the grip handle (§ B). The task part is the user-reported bug (5j).
2. **Order survives reload AND a real backend restart** — stopwatches, timers and tasks come back in the same order (§ C).
3. **A muted card is silent but still blinks and needs dismissal** — and an un-muted card ringing at the same time still plays sound (§ F).
4. **The two items the user added to this phase:** each event shows its ring time (§ E), and a running card's pause button is red (§ D).

Fixed-size cards (§ G) were not ticked as a blocker; they are verified anyway because it is a roadmap item, and a failure is reported rather than hidden — but it does not by itself block the merge unless the user says so.

## Automated

- [ ] `python -m pytest backend/tests/ -v` — the 140 existing tests pass unmodified, plus the new ones: `reorder` (tasks; mixed stopwatch+timer lists; survives a fresh `TaskManager`; stale ids; malformed list changes nothing; new card appended last; no `NotImplementedError`), `pos` assignment on create, `get_ApiState` order, and `mute` (persists, restores, does not change `alerting`). Record the final count here.
- [ ] Tests use only temp DB fixtures — the production `productivity.db` is untouched.
- [ ] `pnpm`/`npm run build` for the frontend succeeds with no type errors. *(Group 3: `vite build` succeeds in the frontend container; the repo has no `tsc`/tsconfig, so there is no separate type check — Vite only strips types.)*

## Manual walkthrough

Set up first: start the app on a **backed-up or throwaway** `productivity.db` (the `timers` and `events` tables must have been dropped once so they pick up the `muted` column — see § H). Create at least: three stopwatches/timers in a known order, three tasks, three events at different times.

### A. Cards never move by themselves (Decision 2)

1. Note the order of the duration cards. **Start, pause, resume** several of them in a different order: nothing moves.
2. Let a timer **ring**, then **dismiss** it: nothing moves. Start a mutually exclusive stopwatch so another auto-pauses: nothing moves.
3. Tap the **sync** button and the **RST** button's cancel path (tap once, wait for it to revert): nothing moves. (After a confirmed reset the board is rebuilt — expected.)
4. Create a new timer: it appears **last**.

### B. Drag by mouse and by finger (5a, 5b) — finger part is a merge blocker

1. Each stopwatch and timer card shows a grip handle (six dots) on its left, like the task rows.
2. **Mouse:** drag a card by its handle to the front, the middle, the end — it lands where dropped, with visible feedback while dragging.
3. **Finger, on the touchscreen:** repeat step 2. The card follows the finger, the page does not scroll instead, and it drops where released. Do this for a stopwatch and for a timer, and for a drag across a row boundary (the cards wrap).
4. **Tapping the body of a card** (not the handle) never starts a drag; tapping a *ringing* card still dismisses it.
5. A card that is running keeps running while it is dragged, and its time is not disturbed by the move.
6. **Tasks (5j, user-reported bug — merge blocker):** drag a task by finger from its grip: it follows the finger, the task list does not scroll instead, and it drops where released. Repeat with a mouse. Then check nothing else regressed: double-click-to-edit a task label, the complete tick and the delete button all still work, with finger and mouse. Before the fix, record that the finger drag fails (so the fix is shown to change something).

### C. Order persists (5h) — merge blocker

1. After rearranging stopwatches/timers and tasks, **reload the page**: identical order.
2. **Stop and restart the backend** (`docker compose restart backend`, or the real service restart), then reload: identical order. Check the backend log shows the `reorder` POSTs as 200, not 500.
3. Reorder, then immediately cut the page without waiting (close tab): the order was saved at drop time, so it is still there.
4. After a restart, **create a card**: it is last. Delete a card in the middle and reload: the remaining order is unchanged.

### C2. Derived order: events by time, completed tasks last (5f, 5g)

1. Create three events out of time order (e.g. 3 PM, then 1 PM, then 2 PM): they show **1 PM, 2 PM, 3 PM**, with no reload. Edit one event's time: it moves to its new place at once. Events have no grip handle.
2. Create tasks A, B, C, D, E; tick **B** and **D**. The list reads **A, C, E, B, D** (completed last, each group in its saved order). Untick B: it returns to its slot (**A, B, C, E, D**).
3. With B and D still ticked, drag **E** to the top: **E, A, C, B, D** — and after untick-ing D then B and reloading, the order is E, A, B, C, D (the hidden slots were not scrambled).
4. Tap **sync** (or add a task by hand): the new task lands **after the last incomplete task** and before the completed ones.
5. Reload and restart the backend: the same display order.

### D. Red pause button (5e) — user-added item

1. A paused/idle card shows a **blue play** button; starting it turns the button **red pause**; pausing turns it blue again — for a stopwatch and for a timer.
2. Start several; the running ones are identifiable at a glance by red, the others by blue. Confirm by screenshot at 1024×600.
3. A ringing card hides the button (no red button inside a red alert outline).

### E. Event ring time (5i) — user-added item

1. Each event shows, below its countdown, small gray `h:mm AM/PM` text equal to its ring time (compare against the time you entered, including a PM time and a time with a non-zero minute).
2. Edit an event's time: the line updates. A sheet-imported event shows its time too.
3. The line is still visible while the event rings.

### F. Mute (5d) — merge blocker

1. Every timer and event card has a speaker icon; stopwatches do not.
2. Mute a timer, let it ring: **no sound**, the card **blinks red**, and it **still needs a tap to dismiss**. (Real speaker, heard by the user.)
3. Un-muted timer ringing: sound plays as in Phase 4.
4. **Both together:** one muted, one un-muted ringing at once — sound plays; dismiss the un-muted one — sound stops, the muted one keeps blinking; dismiss it too.
5. Mute a card **while it is ringing** (sound stops if nothing else un-muted is ringing); un-mute it (sound starts again).
6. Same for an **event**.
7. **Mute survives a reload and a backend restart**; a ringing muted card restored after a restart is still muted.
8. Muting does not move, resize or otherwise change the card.

### G. Fixed size (5c) — not a blocker

1. Watch a stopwatch cross `00:09:59` → `00:10:00` and `00:59:59` → `01:00:00`; a timer count down across the same (`00:59:59` → `01:00:00` — the display is always `HH:MM:SS`): the card's width and height do not change by a pixel (scripted measurement, results below).
2. `DONE!`, a very long label, and an event with the ring-time line are all the same size as an ordinary card.
3. The wrapped layout does not jump around as numbers tick.

### H. Setup / upgrade note

1. On a database from before this phase, the app fails or ignores `muted` until `timers` and `events` are dropped once; the README documents the exact step, and after following it the app starts clean.

### I. Hygiene

1. No error in the browser console and no traceback in the backend log across A–H.
2. No stray files outside `backend/experiments/` for the Group 1 probe.

## Results

*Not run yet.* Record, per step: pass/fail, how it was checked (by eye on the touchscreen, by scripted CDP run on a faked backend, by pytest), and any honest gaps — the same format Phase 4 used.

## Deviations

*None yet.* Known up front: the roadmap's "within the stopwatch section / within the timer section" is implemented as one shared list because that is how the dashboard is laid out (`requirements.md` Decision 1).
