# Validation — Phase 5: Dashboard layout & ordering

How we know this phase works and can merge. Spec written 2026-11-25; the automated part and the scripted checks are recorded in Results below, the on-device walkthrough is still the user's. Run it against the real app, and for anything involving a finger, on the **real Pi touchscreen** — not a mouse standing in for one.

## Merge bar

The user chose these as blockers (2026-11-25). All must pass before merging:

1. **Finger drag on the touchscreen** — stopwatches, timers **and tasks** can be reordered by finger from the grip handle (§ B). The task part is the user-reported bug (5j).
2. **Order survives reload AND a real backend restart** — stopwatches, timers and tasks come back in the same order (§ C).
3. **A muted card is silent but still blinks and needs dismissal** — and an un-muted card ringing at the same time still plays sound (§ F).
4. **The two items the user added to this phase:** each event shows its ring time (§ E), and a running card's pause button is red (§ D).

Fixed-size cards (§ G) were not ticked as a blocker; they are verified anyway because it is a roadmap item, and a failure is reported rather than hidden — but it does not by itself block the merge unless the user says so.

## Automated

- [x] (2026-11-25: **178 passed**, 0.8 s; 140 original + 24 in `test_ordering.py` + 14 in `test_mute.py`) `python -m pytest backend/tests/ -v` — the 140 existing tests pass unmodified, plus the new ones: `reorder` (tasks; mixed stopwatch+timer lists; survives a fresh `TaskManager`; stale ids; malformed list changes nothing; new card appended last; no `NotImplementedError`), `pos` assignment on create, `get_ApiState` order, and `mute` (persists, restores, does not change `alerting`). Record the final count here.
- [x] (temp-DB fixtures only; the live DB was not opened by any test) Tests use only temp DB fixtures — the production `productivity.db` is untouched.
- [x] (2026-11-25, Group 7: `npx vite build` in the frontend container, built in ~4 s; the generated `frontend/dist/` was removed afterwards) `pnpm`/`npm run build` for the frontend succeeds with no type errors. *(Group 3: `vite build` succeeds in the frontend container; the repo has no `tsc`/tsconfig, so there is no separate type check — Vite only strips types.)*

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

Recorded 2026-11-25 (Group 7). **"Scripted" = headless Chromium over CDP against a faked `/api` or a throwaway copy of the backend with its own empty DB — the live backend, DB and sheet were not touched, and no sound was heard. It is not a real finger or a real speaker.**

| § | Item | Status | How checked / honest gap |
|---|---|---|---|
| Automated | pytest 178, build | **pass** | pytest and `vite build`, above |
| A | Cards never move by themselves | **partly** | Code read (Group 3) and scripted: play/pause sends only `resume`/`pause`, no `reorder`; completing/un-completing sends only `complete`. Not done on the live board: ring + dismiss, mutually-exclusive auto-pause, sync/RST cancel by hand |
| B | Drag by mouse and finger (5a, 5b, 5j) | **finger: pass (user, 2026-11-25, on the touchscreen); mouse + scripted: pass** | Probe (Group 1) and the Group 3 finger check by the user; scripted `drag_check.mjs` 14/14 (mouse + **emulated** touch). Double-click-to-edit / tick / delete by finger after the move to pointer events: scripted only |
| C | Order persists (5h) — blocker | **backend pass; live not done** | pytest: order survives a fresh `TaskManager`, deletes, stale ids; a throwaway backend returned 200 for task and duration `reorder` and the new order; the scripted mute run survived a real backend restart. **Not done on the live app** (needs the table drop below) |
| C2 | Events by time, completed tasks last | **scripted pass** | `order_check.mjs` 9/9. Event-edit path in a live browser not clicked |
| D | Red pause button | **scripted pass** | colours and 1024x600 screenshots read by eye. Not looked at on the touchscreen |
| E | Event ring time | **scripted pass** | PM time, non-zero minute, ringing state in a screenshot. Sheet-imported event on the live board not looked at |
| F | Mute — blocker | **scripted pass; speaker not heard** | `mute_check.mjs`, 21 checks on a real backend copy with `play()`/`pause()` hooked and counted. **The real speaker and a real finger on the mute button are the user's** (steps 2-5, 7). The button was shrunk to 20x20 after the user tried it by finger |
| G | Fixed size | **scripted pass** | `size_check.mjs`: 18 duration + 5 event cards in every state listed, exactly two distinct sizes (224x88, 224x100). Live tick across `00:09:59` to `00:10:00` not timed (layout depends only on the text) |
| H | Upgrade note | **documented, not executed live** | README "One-time upgrade step" |
| I | Hygiene | **scripted: no console errors; backend traces clean** | Live walkthrough hygiene still to watch |

### Closed out 2026-11-25 by the user

The user ran the on-device walkthrough (§ A-I) on the real app, touchscreen and speaker, after the one-time `timers`/`events` table drop, and reported that everything works. The merge bar is met. The per-step table above records how each item was machine-checked beforehand; the user's pass is a summary report, not a step-by-step log.

### Was open before that (kept for the record)

1. **The one-time `timers`/`events` table drop on the live `productivity.db`** (README). Until it is done the live app loads fine but creating a timer/event or pressing mute fails (`no column named muted`). It deletes the day's timers and events, so it was not run from here.
2. **The on-device walkthrough** (§ A-G above) on the real touchscreen and speaker: in particular § F steps 2-5 and 7 (sound/silence heard), § C steps 2-4 (live backend restart), and § A on the live board.
3. **The merge bar** (4 blockers at the top) is therefore **not yet met**; merge only after 1 and 2.

## Deviations

*Two, both small.* (1) The roadmap's 59:59 to 1:00:00 is really `00:59:59` to `01:00:00`, because `fmtMs` always prints `HH:MM:SS`. (2) Card heights moved after first sizing (event card 108 to 100 px) and the mute button went from 28x28 to 20x20, both at the user's request. Known up front: the roadmap's "within the stopwatch section / within the timer section" is implemented as one shared list because that is how the dashboard is laid out (`requirements.md` Decision 1).
