# Plan — Phase 5: Dashboard layout & ordering

Numbered groups are the intended implementation order. Each group should be independently committable and leave the app working. Scope, decisions and reasons are in `requirements.md`; this file is the work list. Group 1 done 2026-11-25 (pointer events chosen); Group 2 (backend order) done 2026-11-25, committed `f8441ce`; Group 3 (frontend drag) built 2026-11-25, finger-verified by the user 2026-11-25; Group 4 (derived order) built 2026-11-25; Groups 5–7 not started.

Branch: `phase5-dashboard-ordering`.

Convention (CLAUDE.md): tests are added when behaviour changes, the full `python -m pytest backend/tests/ -v` suite must pass before a group is called done (140 tests at the start), every new file gets a header and docstrings, and nothing is committed without the user reviewing the summary first.

---

## 1. Drag probe on the real touchscreen (decides the mechanism for 5a, 5b)

Prove how a card can be dragged by **mouse and by finger** on this Pi before any real feature code depends on it. Nothing here touches the running app's cards.

- [x] (2026-11-25) Dev page `/?test=drag` (same pattern as `/?test=alarm`: chosen in `frontend/src/main.tsx` before `App` renders), showing a short wrapping list of dummy cards, each with a `GripVertical` handle.
- [x] (2026-11-25) Variants side by side — built as **three** (C added: a replica of today's task rows, so the 5j failure is recorded without touching the real app): **(A)** native HTML5 drag from the handle (what tasks use today), **(B)** hand-written pointer events on the handle (`touch-action: none`, pointer capture, drop target found by position). Each variant logs the events it receives and shows the resulting order.
- [x] *Scripted pre-check done 2026-11-25 (headless Chromium, **emulated** touch — not the real digitizer): mouse drag works in A, B and C; emulated touch works only in B. In A and C the browser fires `pointercancel` right after `touchstart`/`touchmove`, then no `dragstart` — the same shape as the user-reported 5j bug. This is a hint, not the result.* **Run on the touchscreen with a finger** (user) and with the mouse: does each variant lift, follow, and drop correctly? Does the page scroll instead of dragging? Does a stray tap on the card body start anything?
- [x] Also try the **existing task rows** by finger — the user has already reported they fail (5j); the probe records *how* (no events at all, or the page scrolls instead) so the fix targets the real cause.
- [x] (2026-11-25: finger run — only B works; A and C fail and open the context menu) Write the result into `requirements.md` Decision 4 (chosen mechanism, and why the other lost).

## 2. Backend: order, persisted (5h — backend half)

- [x] (2026-11-25) `Message` gains `order: list[int] | None` (the full desired id list for a `reorder`) and `muted: bool = False` (used in Group 6). `Message.pos` stays but is no longer trusted from the client on create.
- [x] (2026-11-25) `TaskManager.create` (the build step is split out as `_instantiate`, which `retrieve_data` uses so a restored row keeps its saved `pos`): assign `pos = (largest pos in that list) + 1` for tasks, events and durations (durations = stopwatches and timers share one counter).
- [x] (2026-11-25) New `reorder` command in `process_command`: validates that every id in `order` is a live card of the right kind, sets `pos = index`, persists all rows in **one transaction** (add a small multi-statement helper to `Database` if `execute` only takes one), tolerates ids deleted in the meantime. A malformed list is rejected without changing anything.
- [x] (2026-11-25) `get_ApiState` returns each list **sorted by `(pos, id)`**; the in-memory lists stay sorted by id (`sorted_find_index` depends on it). Document that split in a comment at the sort sites.
- [x] (2026-11-25) `retrieve_data` restores `pos` from the DB (check the `Message.model_validate` round-trip carries it).
- [x] (2026-11-25) Tests (`backend/tests/test_ordering.py`, temp DB fixtures): create order is append order; `reorder` changes `get_ApiState` order for tasks and for mixed stopwatch+timer lists; order survives a fresh `TaskManager` on the same DB; delete then reorder; a stale id in the list; a malformed list changes nothing; new card after a reorder lands last; `pos` stays gap-free enough that appending still works after deletes.
- [x] (2026-11-25) Add a regression test for the existing bug: a `reorder` command no longer raises `NotImplementedError`.

*Done 2026-11-25: 24 tests in `backend/tests/test_ordering.py`, suite 164 passing. Design notes: a malformed `reorder` raises `ValueError` (the API returns a 500, like other bad commands) before anything is written; a card the client did not list keeps its place after the listed ones; `Database.execute_many` is the new one-transaction helper; each card class has a `table` attribute that `set_pos` writes to. Not exercised over HTTP — `main.py` builds a `TaskManager()` at import, which would run the live sheet sync, so the check is at `process_command` level.*

## 3. Frontend: drag handle on duration cards; tasks fixed onto the same mechanism (5a, 5b, 5j, 5h — frontend half)

- [x] (2026-11-25) A `GripVertical` handle on the left of `DurationCardView` (matching the task rows' icon and colour). Only the handle starts a drag. Implemented with the mechanism chosen in Group 1.
- [x] (2026-11-25) Dropping sends `{ type: "duration", command: "reorder", order: [...] }` with the full id list in the new order; the local list is reordered optimistically and **the backend's order is what loads next time** (already applied via Group 2).
- [x] (2026-11-25) Visible drag feedback (dragged card dimmed or lifted, drop position highlighted), sized for a finger.
- [x] (2026-11-25) **5j — fix task reorder by finger.** Move the task list's drag onto the same mechanism as the duration cards (the reported bug: it works with a mouse only). Keep the grip handle as the drag start, keep the task text's double-click-to-edit and the complete/delete buttons working, and make sure a finger drag inside the scrolling task list reorders instead of scrolling it. Remove the old native `draggable`/`onDrag*` handlers once replaced, so there is a single implementation.
- [x] (2026-11-25, code read; the live walkthrough § A is still to do) No automatic movement anywhere: confirm `toggleRunning`, pause, ring, dismiss, reset and sheet sync never reorder `durations` (Decision 2) — read the code paths and test them in the walkthrough.
- [x] (2026-11-25, throwaway backend copy on :8082) The existing task `reorder` call now succeeds against the backend (Group 2); check the network log shows 200, not 500.

*Built 2026-11-25: `frontend/src/app/dragReorder.tsx` is the single drag implementation (`useDragReorder(group, ids, onReorder)` + the pure `moveId`); `App.tsx` uses it for tasks and durations and the old native `draggable`/`onDrag*` code is gone. Handle = ~32px wide, full card height (finger-sized; a task row's grip is 28px wide, min 32px tall). While dragging: source dimmed to 40%, hovered target outlined blue, a floating label follows the pointer. Dropping on the same card, on empty space, or on a card of the other list does nothing and sends nothing. The handle's click/pointerdown do not bubble, so grabbing a ringing card does not dismiss it. Not done: auto-scroll of the task list when dragging near its edge — a drag only reaches rows currently visible.*

*Checked by machine (headless Chromium over CDP, `/api` faked so no real DB is touched; script `drag_check.mjs`, 14/14): mouse and **emulated** touch drags reorder durations and tasks and send the right `reorder` body; drop on empty space / other list is ignored; play button still sends `resume` and does not reorder; mid-drag feedback present; no console errors. Over HTTP, a throwaway copy of the backend returned 200 for task and duration `reorder` and returned the new order. The **real finger** check is the user's (validation § B).*

## 4. Derived order: events by time, completed tasks last (5f, 5g)

- [x] (2026-11-25) Events render sorted by `ring_time` ascending — in the render, from state (`sortEventsByRingTime`), so a new or edited event lands in the right place without a reload. Ties break by id.
- [x] (2026-11-25) Tasks render as incomplete-in-`pos`-order then completed-in-`pos`-order (`incompleteFirst`, a stable partition at render). Completing moves a task to the end; un-completing returns it to its slot. A drag rewrites `pos` for the full list so the saved order is consistent.
- [x] (2026-11-25, scripted) Verify: dragging while some tasks are completed does not scramble the hidden order; a sheet sync that adds a task puts it last among the incompletes (by construction: the backend gives it `pos = max + 1`, and the partition keeps it after the other incompletes).

*Built 2026-11-25: new `frontend/src/app/cardOrder.ts` (three pure helpers) used by `App.tsx`; `tasks`/`events` state still hold the backend's saved order and nothing is stored for the derived order. No backend change (suite still 164). **The one subtle part:** a task drag happens on the *visible* list, so `mergeVisibleOrder(full, visible, isDone)` maps it back — incomplete ids take the slots incomplete tasks held in the saved list, completed ids the slots completed ones held. Example: saved `21,22,23,24,25` with 22 and 24 done, drag 25 to the top → sends `[25,22,21,24,23]`; the completed pair keeps slots 1 and 3. Dropping an incomplete task on a completed one leaves it as the last incomplete (it can't enter the completed block); the reverse likewise.*

*Checked by machine (headless Chromium over CDP, `/api` faked, script `order_check.mjs` in the session scratchpad, 9/9): events shown Soon/Mid/Late from ids out of order; tasks 21,23,25,22,24; completing/un-completing sends only `complete`, never `reorder`, and the task returns to its slot; the drag cases above send the expected body. Not checked: a real finger (same mechanism as Group 3), and the event-edit path in a live browser (it uses the same `setEvents`, so the derived sort covers it, but I didn't click it). The manual steps are `validation.md` § C2.*

## 5. Card visuals: fixed size, red pause, event ring-time line (5c, 5e, 5i)

- [ ] **5e** — `DurationCardView`: running → pause button red (new colour token chosen to be clearly different from the blue play button and distinct from the `#e03555` alert outline); not running → blue play button as today.
- [ ] **5i** — `EventCardView`: small gray `h:mm AM/PM` line under the countdown, from `card.ringTime`, shown in all states.
- [ ] **5c** — tabular numerals on all countdown/stopwatch digits, explicit fixed width and height on duration cards and event cards, content that can overflow (long label, `DONE!`, `HH:MM:SS`, the ring-time line) clipped or truncated rather than allowed to resize. Pick the pixel size against a screenshot at 1024×600 and record it here.
- [ ] Scripted measurement (headless Chromium over CDP, as in Phase 4, on a faked network layer so the real DB is untouched): card width/height identical at `09:59`→`10:00`, `59:59`→`1:00:00`, in `DONE!`, and for the longest allowed label. Results recorded in `validation.md`.

## 6. Mute on timers and events (5d)

- [ ] `muted` column on `timers` and `events` (`CREATE TABLE IF NOT EXISTS` only — no migration code, by design). `Task`/`Event`/`Timer` classes carry the field; `get_tuple_to_save` and `get_Api*` enumerate it; `retrieve_data` restores it.
- [ ] New `mute` command carrying the desired `muted` boolean (a set, not a toggle); persisted immediately.
- [ ] Frontend: `Volume2` / `VolumeX` icon button on timer and event cards (never on stopwatches, in this phase), sized for a finger, not starting a drag. Optimistic local update plus the command.
- [ ] Alarm engine: `App.tsx`'s "ringing" boolean becomes "at least one alerting timer/event that is **not muted**" and is passed to `useAlarmSound` as before; muted cards still blink and still need dismissal. No change inside `alarmSound.ts` unless the verification shows one is needed.
- [ ] Tests: `mute` persists and restores after a fresh `TaskManager`; a restored ringing card keeps its mute state; muting does not change `alerting`.
- [ ] The one-time table drop for an existing `productivity.db` (`timers`, `events`) is written into the README and `requirements.md`, as Phase 3 did.

## 7. Docs, walkthrough and close-out

- [ ] `specs/roadmap.md`: tick 5a–5i with dates; `specs/tech-stack.md` § Dashboard Ordering rewritten to match what was built (backend-owned `pos`, `reorder`/`mute` commands, the mechanism chosen in Group 1, the corrected `react-dnd` note); README gets the ordering/mute behaviour and the table-drop note; `CLAUDE.md` status updated.
- [ ] Run `validation.md` in full on the real app and the real touchscreen; record results there, with honest gaps.
- [ ] Full backend suite green; no traceback in the backend log and no console errors during the walkthrough.
- [ ] Commit per group, user reviews each summary first; merge only when the `validation.md` merge bar is met.
