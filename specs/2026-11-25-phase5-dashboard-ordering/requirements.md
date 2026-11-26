# Requirements — Phase 5: Dashboard layout & ordering

Branch: `phase5-dashboard-ordering`. Written 2026-11-25 after two rounds of questions with the user; the answers are recorded below as decisions, in the user's words where the wording matters.

## Goal

Make the existing cards **stay where the user puts them**, look the same size at every second of the day, show at a glance which ones are running, and show when each event will ring — and let the user silence a single timer or event without losing its visual alert. No new tracking categories, no new card types.

This is presentation-layer work on cards that already exist (`mission.md` pillar 2: minimal taps, glanceable). Goals, limits, the exclusive checkbox and importing timers/stopwatches from the sheet are **Phase 6**, deliberately not here — see § Handed to later phases.

## Scope

Roadmap items 5a–5j (see `specs/roadmap.md`):

| ID | What |
|---|---|
| 5a | Drag-to-reorder stopwatches, with a grip handle, by mouse or finger |
| 5b | Drag-to-reorder timers, same mechanism |
| 5c | Cards keep a fixed size |
| 5d | Mute toggle on timers and events |
| 5e | A running card's pause button is **red** (replaces the earlier "promotion" idea — see § Decisions) |
| 5f | Events are sorted by ring time (derived, not draggable) |
| 5g | Completed tasks sit at the end of the task list |
| 5h | Order is persisted: reload and backend restart both restore it |
| 5i | Each event shows, below its countdown, the clock time it will ring |
| 5j | Task reorder works by finger on the touchscreen (it only works with a mouse today) |

## Current state (confirmed by reading the code, 2026-11-25)

- **Stopwatches and timers are one flat list, not two sections.** `App.tsx` renders a single "Tasks Duration" section: `durations.map(...)` into one wrapping `flex-wrap` row. The roadmap's "within the stopwatch section / within the timer section" described a layout that does not exist; see Decision 1.
- **Tasks already have a drag handle, but it works only with a mouse** (user-reported 2026-11-25; the cause is native HTML5 drag not firing from touch) — — a `GripVertical` icon (the "six little squares") on the left of each task row, using **native HTML5 drag events** (`draggable`, `onDragStart/Over/Drop`, `App.tsx:463-466`). `react-dnd` is in `package.json` but nothing imports it, so `tech-stack.md`'s "already installed and used for the task list" was inaccurate (corrected in this phase).
- **Task reorder is not persisted today, and the backend rejects it.** The frontend sends `{type: "task", command: "reorder", order: [...]}` but `TaskManager.process_command` has no `reorder` case: it hits `raise NotImplementedError`, FastAPI returns a 500, and `sendMessage` swallows the failure. On reload, `retrieve_data` sorts lists by `id`, so the manual order is lost. This is a real existing bug that 5h fixes.
- **Every card table already has a `pos INTEGER` column**, but nothing reads or sets it meaningfully (`Message.pos` defaults to 0, so every card is 0). Internally `tasks`, `events` and `durations` are kept sorted by `id` because `sorted_find_index` does a binary search on `id` — they must stay that way; display order has to be produced separately (Decision 6).
- **Cards currently never move by themselves** — new ones are appended, and nothing re-sorts. Phase 5 must keep it that way for stopwatches and timers (Decision 2).
- **Running state**: `DurationCardView` shows a pause icon on a dark blue circle (`#1a2d6e`) when running and a play icon on bright blue (`#2250c4`) when not. Ringing shows a red (`#e03555`) blinking outline and hides the button.
- **Card width varies** with content: `min-w-[160px]` only, and the digits use a proportional font, so `09:59` → `10:00` or `59:59` → `1:00:00` reflows the card.
- **Sound** (Phase 4): `useAlarmSound(ringing)` plays one shared looping `Audio` while *any* event or timer is alerting. There is no mute concept.
- **Events** show a countdown only; the ring time is not displayed. Events are rendered in array (id) order.

## Decisions

### 1. One drag list for stopwatches and timers together

The "Tasks Duration" list stays one list, and every card in it — stopwatch or timer — can be dragged past any other. The roadmap items 5a/5b are both satisfied by the one mechanism. Splitting it into two sections is a layout change nobody asked for (CLAUDE.md principle 2). *Chosen by Claude as the least invasive reading; the user can overrule.*

### 2. Cards never move by themselves (user, 2026-11-25)

> "task duration cards will not move by themselves whatsoever. It does not matter the action. They should only remember the order I manually placed them…"

So: **no promotion on play/resume** (the roadmap's old 5e is dropped), no re-sorting on pause, ring, dismiss, completion, sheet sync or reset. The only thing that moves a stopwatch or timer is the user's own drag. New cards are appended at the end.

*Consequence the user should know about:* with no automatic ordering, the way to see what is running is purely visual — hence 5e (red pause button).

### 3. Red pause button replaces promotion (5e, user)

> "the pause button (for the ones that are running) should be of a different color (Red) so it is easy to see what is running and what is not"

A running card's pause button is red; a paused/idle card's play button stays blue. This applies to stopwatches and timers. While a card is ringing the button is hidden (existing behaviour), so the red button and the red alert outline never appear together.

### 4. Drag handle on each duration card — mouse **and** finger (5a, 5b, user)

> "the 6 squares on the left of the card … available to be dragged around and reordered with either a mouse pointer or touchscreen."

- A `GripVertical` handle on the left of every stopwatch and timer card, matching the task rows. **Only the handle starts a drag**, so tapping the rest of the card (e.g. to dismiss a ringing alert) never starts one by accident.
- It must work with a mouse and with a finger on the Pi's touchscreen.
- **Mechanism is decided by a probe, not assumed** (Group 1): Chromium's native HTML5 drag may not fire from touch, which is exactly the risk for the existing task rows. Candidates: native HTML5 drag (what tasks use now), or hand-written pointer events on the handle. No new dependency unless the probe shows the need, and then it is asked about first. The result is written back into this section.
- **Probe result (Group 1, 2026-11-25, real touchscreen, user + scripted pre-check): hand-written pointer events on the handle win.** Tried on `/?test=drag`: (A) native HTML5 drag from a handle, (B) pointer events on the handle with `touch-action: none` and pointer capture, (C) a replica of today's task rows. **Mouse: all three work. Finger: only B works.** In A and C the finger cannot drag at all and a press-and-hold opens the browser's context ("right-click") menu instead; the headless pre-check showed the same cause — the browser fires `pointercancel` right after `touchstart`/`touchmove` and never `dragstart`, i.e. Chromium on touch does not start native HTML5 drag from this gesture. That is the 5j bug's root cause: the task rows use native drag. **Chosen: B for stopwatches, timers and tasks, no new dependency** (`react-dnd-html5-backend` is also native HTML5 drag, so it would fail the same way). Implementation notes carried into Group 3: the handle needs `touch-action: none`, `setPointerCapture`, drop target found with `document.elementFromPoint` (the captured handle stays `e.target`), a floating ghost under the finger, and an `onContextMenu` preventDefault on the handle so a long press cannot open the menu mid-drag.
- **Task rows must also drag by finger (5j) — confirmed broken by the user, 2026-11-25:** "task reorder only works with mouse pointer, it does not work with touchscreen." This is no longer conditional on the probe: the task list moves onto the **same mechanism** as the duration cards, so one drag implementation serves both and they cannot drift apart. It is a bug fix to existing behaviour, not a new feature.

### 5. Mute (5d): timers and events only, persisted

- A clickable speaker icon on each timer and each event card (lucide `Volume2` / `VolumeX`). Stopwatches get a mute button in Phase 6, when they gain a sound.
- A muted card **makes no sound but still blinks red and still needs dismissal** (roadmap wording, user-confirmed).
- **Persisted in SQLite** (user chose this): a new `muted` column on `timers` and `events`. The project has no migration code by design (CLAUDE.md, Phase 3 precedent), so an existing `productivity.db` needs a **one-time drop of the `timers` and `events` tables** before first run; documented in the README, same as Phase 3. Mute survives reload and backend restart.
- Alarm engine rule becomes: the sound plays while **at least one alerting timer/event is not muted**. If a muted and an un-muted card ring together, the sound plays; dismiss the un-muted one and the sound stops while the muted one keeps blinking. Toggling mute on a ringing card takes effect immediately (mute stops the sound if nothing else un-muted rings; un-mute starts it).
- The mute icon works on a card in any state, not only while ringing, so a timer can be muted before it rings.
- Backend: a new `mute` command carrying the desired `muted` boolean (set, not toggle, so a repeated or retried request cannot flip the wrong way). A restored ringing card comes back with its saved mute state.

### 6. Order storage and who owns it (5h)

- The **backend owns order.** `pos` is the persisted position of a card among its own kind: tasks among tasks, events among events (unused for display — see below), and stopwatches+timers together among durations.
- A new `reorder` command carries the full desired list of ids; the backend sets `pos` = index for each and persists them in one transaction. Sending the whole list (as the frontend already does for tasks) keeps it idempotent and gap-free, and makes the existing frontend call finally valid.
- Creating any card assigns `pos = (largest pos in its list) + 1`, regardless of what the client sent, so new cards land at the end and sheet-imported tasks keep a stable position.
- `tasks`/`events`/`durations` stay **sorted by id in memory** (binary search depends on it). `get_ApiState` returns each list **sorted by `(pos, id)`**; the frontend renders what it receives. The frontend never invents order.
- Order is saved when the drop happens, not at shutdown, so a power cut loses nothing.

### 7. Events and tasks: derived order (5f, 5g)

- **Events** are displayed sorted by `ring_time` ascending (soonest first), recomputed on render and after an event edit. Events are not draggable and `pos` is not used for them.
- **Tasks**: displayed order = incomplete tasks in `pos` order, then completed tasks in `pos` order (a stable partition done when rendering, not a stored change). Completing a task sends it to the end; un-completing returns it to its saved slot among the incompletes. Dragging happens within the visible list and rewrites `pos` for the full list.

### 8. Fixed card size (5c)

A card must not change width or height as its numbers change. Technique: digits in a tabular-figures font setting (`font-variant-numeric: tabular-nums`) so every digit has the same width, plus **explicit fixed width and height** for duration and event cards, sized for the widest content they can show: `HH:MM:SS`, the word `DONE!`, a long label (truncated with ellipsis, as today), and the 5i ring-time line. The same size applies in every state (idle, running, ringing, muted). The exact pixel size is chosen against a 1024×600 screenshot in Group 5 and recorded in the plan.

### 9. Ring time on events (5i, user)

> "events should [show] at what time they are going to ring: below their timer, a small size print (in gray color) showing the hour and minute"

- Below the countdown, small gray text: the **ring time as hour and minute** — `h:mm AM/PM`, 12-hour, to match the AM/PM inputs in the creation modal.
- Rendered in the browser's local timezone (the same `Date` the countdown uses). Updates when the event is edited. Shown in every state, including while ringing.
- Part of the fixed-size budget in Decision 8.

## Out of scope

- Everything in § Handed to later phases.
- Splitting stopwatches and timers into separate sections.
- Manual reordering of events (derived order only).
- Any change to which stopwatches are mutually exclusive — that is Phase 6's checkbox.
- Sound changes, volume, custom sounds (Phase 7).
- Voice (parked).
- Re-enabling or inventing "promotion"; it is dropped, not deferred.

## Handed to later phases (recorded now so nothing the user said is lost)

**Phase 6 — Goals, limits & sheet cards.** User's decisions, 2026-11-25:

- **Exclusive checkbox** on timer *and* stopwatch creation, default **ticked**. Semantics chosen: **one pool** — starting any exclusive card pauses every other running exclusive card, timers and stopwatches alike. Consequence to remember: with the default ticked, starting a new timer pauses a running Work stopwatch. Today only the six default stopwatches are exclusive and timers never pause anything.
- **Stopwatch max** (optional, creation field): small gray text below the time, the **time left** on the left and the **maximum** on the right ("less is better"). When the max is reached: **one short, negative-sounding chime, no dismissal**; the stopwatch keeps running and its **outline turns red**.
- **Timer goal** (optional, creation field): small gray text below the time, the **time elapsed** on the left and the **goal** on the right ("more is better"). When the goal is reached: **one short, positive-sounding chime, no dismissal**, outline turns **green**. The user also said the timer "is set to 0 and swaps places with the little stopwatch below it" — the exact meaning (does the big number become a count-up of time past the goal? what is the goal relative to the timer's total?) is **not settled and must be asked at the start of Phase 6**.
- **Mute button on stopwatches that have a max.**
- **Sheet import of timers and stopwatches**, in column A, by the end of the cell: a cell ending in a duration is a **timer** (`work 2h` → timer "work", 2 hours); a cell ending in a duration followed by `max` is a **stopwatch** (`shower 30m max`, `eat 1h30 max`); anything else stays a task (`buy pineapple juice`). Flag for Phase 6: the existing sheet has a real task `bath, bed, timers 8h`, which ends in a duration and would turn into a timer under this rule — decide how to disambiguate (or edit that cell) before building. How a sheet cell would carry a goal or the exclusive flag was not specified.

**Phase 7 — Custom alert sounds** (new, user-requested): replace the placeholder negative/positive chimes (and later the main alarm) with chosen sounds.

## Context

- `specs/mission.md` — pillar 2 (minimal taps, glanceable) is the reason for 5c, 5e and 5i. Nothing here is a task-manager feature.
- `specs/tech-stack.md` § Dashboard Ordering — updated by this phase: the persistence design above, and the correction about `react-dnd`.
- The Phase 4 alarm engine (`useAlarmSound`, `frontend/src/app/alarmSound.ts`) is changed only by Decision 5's "at least one un-muted alerting card" rule.
- Real-hardware rule (memory: Claude runs on the Pi 5): the finger-drag probe and the finger checks run on the actual touchscreen, not a desktop approximation.
