# Requirements — Phase 4: Alarm sound

## Source

`specs/roadmap.md` Phase 4 (4a and 4b were each added to the roadmap at the user's request as the first task item — 4b immediately before this spec was written, 4a afterwards, which is why the sound items are 4b–4f):

- **4a.** Reset button in the dashboard header (third button, top right): one tap-again-to-confirm action that removes the user-created timers and stopwatches, zeroes the six default stopwatches, deletes every event and task, then re-pulls the day from Google Sheets
- **4b.** Standalone test script that just plays the alarm sound for a short period — proves the sound asset and playback path work on the real Pi hardware before wiring it into any app logic
- **4c.** Play an audible ring when a timer's countdown reaches zero
- **4d.** Play the same ring when an event reaches its ring time
- **4e.** Sound keeps playing (or repeats) until the alert is dismissed, and stops on dismissal
- **4f.** Sound asset bundled locally — no network fetch at ring time

Mission alignment: Pillar 2 ("No feeds, no notifications beyond timer/event alarms") — the alarm is the one notification this kiosk is allowed to make. Tech-stack.md § "Alarm Audio (Phase 4)" already commits to the browser's `Audio`/HTML5 audio API and a bundled asset; this spec fills in the decisions tech-stack.md left open.

## Scope

All six items (4a–4f) land on the single branch `phase4-alarm-sound` under this one spec folder. **4a (the reset button) is unrelated to sound** — it was added as the first group at the user's request, and nothing in 4b–4f depends on it. 4b is deliberately the first *sound* item and separately committable: it proves the sound asset and the playback mechanism work on the real Pi speaker *before* any app logic depends on them, so a failure is a hardware/asset problem, not a "did I wire it up right" problem.

**Stopwatches are explicitly out of scope** (they count up, never reaching zero — per roadmap). `backend/classes.py` already has a defensive `Stopwatch.ring()`/`stop_ring()` (comment: "stopwatches don't ring today"), but nothing in the frontend ever calls it, so stopwatches never set `alerting = true` in practice. The alarm-sound trigger is written to only ever look at events and timers, not "any card with `alerting`", so this stays true even if that changes later.

**Per-card mute is Phase 8 (8d), not here.** This phase ships one global sound with no mute control.

## Current state (confirmed by reading the code)

- `alerting` is already a real, persisted boolean on both timers and events (*correction, 2026-11-15: persisted, but not restored after a backend restart until the fix described under Non-goals*):
  - **Events**: detected client-side every tick — `frontend/src/app/App.tsx:292` (`if (!e.alerting && !e.completed && msUntil(e.ringTime) <= 0)`), which sends `{command: "ring"}` and the backend's `Event.ring()` (`backend/classes.py:181-184`) persists `alerting = 1`.
  - **Timers**: detected client-side every tick — `App.tsx:306-310` (`d.subtype !== "timer" || d.alerting || d.startedAt === null`, then elapsed-vs-total check), sends `{command: "ring"}`, and `Timer`'s inherited/overridden `ring()` persists `alerting = 1` and freezes the running state.
  - **Dismissal**: both go through `stop_ring`, called from `onDismiss`/the task-complete handlers (`App.tsx:598-613`), which clears `alerting` (and, for events, also sets `completed = 1`).
- **Rendering already reacts to `alerting`**: `App.tsx:853-874` — a card's background, border, and blink animation all key off `card.alerting`, and clicking an alerting card calls `onDismiss()`. Sound is a new side effect of a flag that already drives the UI; **no new backend command, no new column, no new API field** is needed for 4c–4e.
- **No audio code exists anywhere in the repo today.** No `<audio>` element, no `Audio()` call, no sound asset, no `frontend/public` directory (there is a Vite `figma:asset/` resolver pointing at `src/assets`, used for images — nothing audio-related lives there yet).
- **`deploy/kiosk.sh` already carries `--autoplay-policy=no-user-gesture-required`** (`kiosk.sh:86`, with a comment at `kiosk.sh:67` naming it as "Phase 4 forward-compat", added during Phase 3 Group 9). **This phase does not add that flag — it verifies it actually does what it's there for**, on the real device, as part of validation. If the flag turns out not to be enough (e.g. a newer Chromium build tightens the policy), that's a finding for this phase to fix, not assume.
- `ffmpeg` is available on this machine and can synthesize a sine-wave tone with no network fetch and no licensing question, which settles how the placeholder asset gets made (see § Decisions).

## Decisions

Answered via `AskUserQuestion` before any file in this spec was written.

### 4b — what the test script exercises

**Both a Python script and a frontend dev route**, not just one:

- **Python script** (`backend/experiments/alarm_test.py` or similar, run manually — not part of the app, not imported by anything): plays the bundled sound file through the Pi's system audio (ALSA, via `aplay`, invoked with `subprocess` — no new Python audio dependency) for a short, fixed duration. This is the check that the Pi's speaker/audio output actually works at all, independent of the browser.
- **Frontend dev route**: a hidden/dev-only button or route that calls the exact same `Audio()`/HTML5 API call the real alarm will use (same asset, same loop/volume settings), playing for a short period. This is the check that the browser-based playback path — including the kiosk autoplay flag — works, since that's the path 4c–4e actually depend on, and a working speaker proves nothing about whether Chromium will let the page make noise.
- Both are throwaway/manual-trigger tools, not part of the dashboard's normal UI. Neither is deleted after use — they stay as a fast way to re-check the audio path if it ever goes silent again (e.g. after a Chromium or OS update on the Pi).

### Sound asset

**A synthesized placeholder tone**, generated with `ffmpeg` (already installed, confirmed) rather than sourced from the network — no licensing question, no fetch, trivially reproducible. One short `.wav` (or `.mp3`, whichever `ffmpeg` produces more simply and both `aplay` and the browser play cleanly), committed to `frontend/src/assets/`. The user can swap it for a real sound file later without any code change beyond the file itself, since the sound is referenced by a single import path.

### Overlapping alarms

**A single shared alarm loop.** One `Audio` element, driven by "is at least one timer or event currently alerting" (a boolean derived each render from the existing card lists), not one `Audio` instance per card:

- The loop starts the moment the derived boolean goes from false to true (the first card starts alerting) and stops the moment it goes back to false (the last alerting card is dismissed).
- If a second card starts alerting while the first is still ringing, nothing changes audibly — the loop that's already playing keeps playing; it does not restart, double up, or layer a second copy of the sound.
- This avoids a cacophony when a timer and an event (or two timers) ring close together, and it means the "stops on dismissal" requirement (4e) is really "stops when the *last* alerting card is dismissed," which is the correct reading of 4e given 4c/4d cover more than one alarm source.

### Kiosk autoplay (4f-adjacent, not a new 4-item)

The autoplay-policy flag needed for the first ring of the day not to be silent **already exists** in `deploy/kiosk.sh` (added during Phase 3 as deliberate forward-compat — see § Current state). This phase's job is to **verify it on the real device** once there's an actual sound to test with: confirm that, on a fresh kiosk launch with no prior tap on the screen, the very first alarm of the day is audible. This is a validation step (see `validation.md`), not new code. If it fails, fixing it is in scope for this phase even though adding the original flag was not.

## Reset button (4a)

Added after the rest of this spec was written, so it sits outside the "current state" reading above. Decisions were answered via `AskUserQuestion` before this section was written.

### What one confirmed reset does

In this order, as one `reset` command handled by the backend:

1. **Events and tasks: deleted, all of them** — hand-made and sheet-sourced alike. (Sheet-sourced ones are deleted on purpose; step 4 brings back what the sheet still lists.)
2. **Timers: deleted, all of them.** Timers are always user-created; the dashboard never auto-creates one.
3. **Stopwatches: the six defaults are kept and zeroed; any other stopwatch is deleted.** "Default" means the six labels the frontend auto-creates at boot: `Work`, `Misc`, `Eat`, `Exercise`, `Shower`, `Fun` (`MUTEX_LABELS`, `App.tsx:22`). Zeroed means paused with `elapsed = 0`; a running one stops. A user-created stopwatch (the create modal allows an arbitrary label) is deleted like a timer.
4. **Sheets is re-pulled**, using the same forced sync the header sync button runs (`sync_sheets(force=True)`), so the "already synced today" marker does not skip it.

Any ringing card is cleared by this: ringing timers and events are deleted, so `alerting` goes with them.

### The button

- **Label**: the text "RST" (small, bold, inside the same 36px circle as the other header buttons) — not an icon. Chosen by the user on 2026-11-15 over the original `RotateCcw` icon. While the reset is in flight the text pulses.
- **Position**: third button in the header's right-hand group, left to right: sheet-sync, **reset**, close (✕). The close button stays rightmost. When sync is disabled (`sheetSync.status === "disabled"`) the sync button is hidden as it is today, so the header shows two buttons — reset is always present.
- **Confirmation: tap again.** The first tap changes the button into an obviously different "Confirm?" state; it reverts on its own after ~4 seconds with nothing done. A second tap inside the window performs the reset. Chosen over a modal so a stray touch on the kiosk can't wipe the day, without adding a dialog to a distraction-free screen.
- **After the reset** the frontend refetches `GET /api` and replaces all its card lists from the response — it does not predict the outcome locally.

### Accepted consequences (not bugs)

- **Past events do not come back.** The sheet import deliberately skips events whose time has already passed today (Phase 3 § Reconciliation). So an event that rang this morning is deleted by reset and is *not* restored by the re-pull. Tasks, and events still in the future, are.
- **A failed or disabled sheet read leaves nothing in place of the deleted events and tasks.** Reset deletes first and pulls second; if the pull fails (network, auth) or sync is disabled, the events and tasks stay gone until a sync succeeds. The failure is visible the usual way — the sync button's colour and tooltip, and `sheet_sync` on `GET /api` — and tapping that button retries without another reset. Deleting before knowing the read will work is what was asked for; reading first would avoid it at the cost of a second code path, so it is not done here.
- **Hand-made events and tasks are lost for good** — they have no sheet to come back from.
- **The six defaults' history is lost**: zeroing discards the accumulated time. Nothing is exported first (analytics is Phase 7).

### Out of scope for 4a

No undo, no per-section reset, no change to how stopwatches mutually exclude, no new Sheets behavior (it calls the existing sync as-is), no change to the daily rollover wipe.

## Non-goals

- **No stopwatch sound** — stopwatches count up and never reach a terminal "ring" state (roadmap-stated, confirmed by code: no frontend path ever triggers `Stopwatch.ring()`).
- **No per-card mute toggle** — Phase 8 (8d).
- **No volume control, no different sounds per card type, no snooze.** One sound, one volume, plays until dismissed.
- **No backend changes for the sound work (4b–4f) — as first written; one turned out to be needed (2026-11-15).** `alerting` already existed and was persisted, but it was never *restored* when the backend started (`Message` had no such field; `Task.__init__` hard-coded `False`), so a card ringing across a backend restart lost its alert. Fixed in `backend/classes.py` (2 lines, 4 tests); see `validation.md` § C. Everything else here still holds: no new column, no new command, no new API field — the sound is a side effect of state that's already there. The one backend change in this phase is the `reset` command for 4a, below.
- **No new Python audio dependency** (`pygame`, `simpleaudio`, etc.) for the 4b test script — `aplay` via `subprocess` is already present on Raspberry Pi OS and is the standalone/system-level check 4b calls for.
- **No change to how/when `ring`/`stop_ring` are triggered.** The detection logic (`msUntil(...) <= 0`, the timer elapsed-vs-total check) is unchanged; sound hooks onto the existing `alerting` flags, it doesn't change what sets them.
- **No automated tests for the audio itself or the 4a `reset` command** — they need real hardware or a browser; validation is manual (`aplay` test + browser + real device). The one exception is the restart-persistence fix above, which is backend logic and has four `pytest` regression tests.
