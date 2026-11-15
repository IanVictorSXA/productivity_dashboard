# Validation — Phase 4: Alarm sound

## Automated

The sound work is almost entirely frontend audio behavior and real-hardware playback, which `pytest` cannot touch, and the 4a `reset` command is verified by hand in § A. The one exception is the restart-persistence bug found in step 18, which got four backend regression tests (CLAUDE.md §3).

- [x] `python -m pytest backend/tests/ -q` — **140 pass** (2026-11-15): the 136 that existed after the Phase 3 post-close tests, unmodified, plus 4 new regression tests in `test_phase0_group3.py::TestAlertingSurvivesRestart` (see § C, step 18 — the sound work did need one small backend fix after all). The other backend change in this phase is the 4a `reset` command (`requirements.md` § Reset button).

## Manual walkthrough

Run against the actual app (backend + frontend), and — for the hardware-dependent steps — on the real Pi with its real speaker, not a scratch script.

### A. Reset button (4a)

Run against the real app with the backend's database in a state worth wiping. Steps 1–7 can use a dev machine; use a throwaway or backed-up `productivity.db`, since this deletes cards for real.

1. **Placement.** With sync enabled the header's right side reads: sync button, reset button (labelled "RST", text not an icon — confirmed fitting the 36px circle in a 1024×600 screenshot, 2026-11-15), ✕ (✕ rightmost). With `SHEETS_SYNC_ENABLED` false the sync button is gone and reset and ✕ remain.
2. **Set up a messy board**: two timers (one running, one left to ring), a user-created stopwatch with an arbitrary label, two of the six defaults with time on them (one running), a hand-made event in the future, a hand-made task, and whatever the sheet imported.
3. **Tap once, then wait.** The button turns into the "Confirm?" state; after ~4 seconds it reverts and **nothing changed** — no card was touched.
4. **Tap twice inside the window.** Afterwards: both timers and the custom stopwatch are gone; all six defaults are present, at 0:00, paused (the running one stopped); the hand-made event and task are gone; the sheet's tasks and still-future events are back, not completed, not alerting.
5. **Reload the page, then restart the backend.** The board is identical both times — the reset was persisted, not just shown.
6. **No Sheets available** (disable sync, or break the network and tap the sync button's retry afterwards): reset still deletes and zeroes, the sync button/`sheet_sync` shows the failure, and tapping sync once the problem is fixed brings the sheet's cards back without another reset.
7. **Past events**: an event whose sheet time has already passed today is deleted by the reset and is *not* re-created (expected — `requirements.md` § Reset button, accepted consequences).
8. No error in the browser console and no traceback in `docker compose logs backend` across steps 1–7.

**Results — run 2026-11-09 on the real stack (Docker backend + Vite, real `productivity.db`, real spreadsheet), driven through headless Chromium over the DevTools protocol with real mouse clicks.** Run on the live board by the user's choice (not a throwaway DB); a copy of the pre-walkthrough DB was kept aside but the board was not restored, so the day's ticked-off tasks and one past event were lost, as predicted.

| Step | Result |
|---|---|
| 1 Placement | **Pass.** Sync on: sync (x=876), reset (x=924), ✕ (x=972). Sync off (`SHEETS_SYNC_ENABLED=false`): reset (924), ✕ (972). |
| 2 Messy board | **Pass.** Built through the same API payloads the frontend sends: running + ringing timer, custom stopwatch `Reading`, `Eat` running, `Misc` at 12:00, hand-made event and task, plus the sheet's cards. |
| 3 Tap once, wait | **Pass.** Button turns amber "Confirm?" (93px wide vs 36px); reverts on its own within 5s; server state byte-identical before/after; no `reset` reached the backend. |
| 4 Tap twice | **Pass.** Timers and `Reading` gone; six defaults at 0, paused (`Eat` stopped); hand-made event/task gone; the sheet's 4 tasks + 1 future event back, unticked. Real read: 7 items, 5 created, 2 skipped as already passed. Screen matches DB. |
| 5 Reload + backend restart | **Pass.** DB state after reset == after page reload == after `docker restart` of the backend. |
| 6 No Sheets | **Pass, disabled variant only.** With sync disabled the reset still deletes and zeroes. After re-enabling, the startup sync said "skipped" (marker already `ok` today), and **one tap of the sync button** brought the cards back with no second reset. The `status: "error"` variant (bad key / no network) was **not** exercised live; that path is Phase 3 code, unchanged here. |
| 7 Past events | **Covered by evidence, not by the exact scenario.** The two events already past (`1pm sun lunch`, `6pm exercise`) were logged "skipped, has already passed today" on the re-pull and never recreated. The literal case — a sheet event that existed on the board, then passed, then was reset — was not run (the only sheet event rings at 8:30 PM local, after the walkthrough). Deletion itself is the generic `delete` path used by every other card. |
| 8 Logs | **Pass.** No browser console errors or exceptions in any page session; no traceback, no 4xx/5xx in the backend log. Caveat: the backend container was recreated twice (for step 6), which discards the earlier container's log, so the clean log was read on the original container during steps 3–5 and on the current one afterwards, not as one continuous capture. |

### B. Asset + standalone test tools (4b)

9. `python backend/experiments/alarm_test.py` on the dev machine: exits 0, plays audibly if the dev machine has audio output.
10. The frontend dev test route/button plays the same tone in a desktop browser.
11. **On the Pi**: `python backend/experiments/alarm_test.py` plays audibly through the Pi's speaker.
12. **On the Pi**: the frontend dev test route plays audibly in the kiosk Chromium.

**Results (2026-11-09; steps 9–10 checked by machine from the Pi, steps 11–12 confirmed audibly by the user)**

| Step | Result |
|---|---|
| 9 | **Exit status only.** `-D plughw:CARD=UACDemoV10,DEV=0` exits 0. With no `-D`, exits 1 (`Unknown error 524`): the default ALSA device is not the speaker on this Pi (HDMI cards have no sink). Audibility **not confirmed**. |
| 10 | **Logic only.** Headless Chromium on `/?test=alarm`: "Playing for 5s (loop on)" with `--autoplay-policy=no-user-gesture-required`; `NotAllowedError` without it. No sound was heard. |
| 11 | **Pass** (user, 2026-11-09): `python backend/experiments/alarm_test.py -D plughw:CARD=UACDemoV10,DEV=0` heard through the Pi's speaker. |
| 12 | **Pass** (user, 2026-11-09): `/?test=alarm` heard in the kiosk Chromium. |

### C. The shared alarm engine (4c, 4d, 4e)

Can be run in a desktop browser for steps 13–17; step 18 needs the Pi.

13. Start a short timer, let it reach zero. Confirm sound starts the moment the card turns to "RING!" (alerting) — no delay, no need to interact with the page first.
14. Create an event with a near-future ring time, let it ring. Confirm the same sound plays the same way.
15. With one card already ringing, let a second card (timer or event) start ringing too. Confirm the sound does **not** restart, double up, or layer — it keeps playing exactly as it was.
16. Dismiss the first of two simultaneously-ringing cards (tap it). Confirm the sound **keeps playing** (the second card is still alerting).
17. Dismiss the second (last) ringing card. Confirm the sound **stops immediately**.
18. **On the Pi**, reload the dashboard while a card is still alerting (e.g. restart the backend with an un-dismissed alerting card persisted). Confirm the sound resumes on load without needing a fresh ring event.

**Steps 13–17 heard on the Pi's speaker (user-confirmed 2026-11-15):** timer rings, event rings, a second alarm does not layer, dismissing one of two keeps it playing, dismissing the last stops it. All pass.

**Machine check (2026-11-15), before the above.** Headless Chromium (`--autoplay-policy=no-user-gesture-required`) against the Vite dev server, backend faked at the network layer (real DB and spreadsheet untouched; the real backend logged 0 POSTs). Every `play()`/`pause()` on any audio element was counted. Because headless Chromium makes no audible sound here, "playing" means the element's `paused` flag is false.

| Step | Result |
|---|---|
| 13 | **Pass (logic).** One timer reaching zero → one `play()`, element playing, `loop = true`, no tap beforehand. |
| 14 | **Pass (logic).** An event reaching its ring time joined the loop already running: still 1 `play()`, 1 element. |
| 15 | **Pass (logic).** Second timer ringing while the first rang: still 1 `play()`, 1 element, no `pause()`. |
| 16 | **Pass (logic).** Three cards ringing (2 timers + 1 event); dismissed the first, then the second: still playing, 0 `pause()` calls. |
| 17 | **Pass (logic).** Dismissed the last: `pause()` once, `currentTime` 0. |
| 18 | **Superseded by the real-backend run below.** (The faked-backend version passed, but a faked backend cannot show what a real restart does — which is how the bug below was missed.) |
| extra | A later timer ringing after everything was dismissed played again (2nd `play()`, same single element) and stopped again. A `play()` that the browser rejects (`NotAllowedError`) left the card ringing and raised no unhandled rejection. |

**Steps 18–20 and 23 against the real backend code (2026-11-15) — and a bug they found.** Same headless Chromium, but the page talked to a copy of `backend/*.py` (own empty SQLite file, Sheets disabled, `TZ=UTC` like the Docker container) on port 8081, reached by redirecting the page's `localhost:8080` calls. The live backend on 8080, the real `productivity.db` and the real spreadsheet were never touched.

- **Bug found by step 18's first real run.** After restarting the backend with a card mid-ring, the card was no longer alerting: `Message` had no `alerting` field and `Task.__init__` hard-coded `self.alerting = False`, so the `alerting` column was written but never read back. A ringing **event** came back un-alerting and only re-rang because the page's own countdown check noticed its time had passed and sent `ring` again. A ringing **timer** came back paused at 00:00:00 with no alert at all (the page only rings *running* timers), so its alarm was silently lost and nothing would ever dismiss it. A page reload *without* a backend restart was always fine, because the backend's memory kept the flag.
- **Fix** (`backend/classes.py`, 2 lines): `Message.alerting: bool = False`, and `Task.__init__` uses `msg.alerting`. The frontend never sends `alerting`, so new cards still start at `False`; only rows loaded from the database carry it. Four regression tests: a ringing timer and a ringing event are still alerting after a simulated restart, dismissed cards stay dismissed, and a frontend-style create starts un-alerting.
- **After the fix, 14/14 checks pass:** timer and event ring through the real backend (`alerting` persisted); backend killed and restarted mid-ring, page reloaded → both cards still ringing, sound resumes with one `play()`, and the page sends no new `ring`; dismiss one → still playing, dismiss the last → stops and rewinds; the backend shows the timer `alerting = false` and the event `completed = true, alerting = false`; a reload afterwards is silent and shows nothing ringing (step 20, both halves); and no browser console error and no traceback or 4xx/5xx in the backend log (step 23, for this run). One benign line excluded: Vite's dev server returns 404 for `/favicon.ico`, which this app has never had.

### D. Stopwatches stay silent (scope guard)

19. Run all six mutex stopwatches through a normal start/pause/switch cycle. *(2026-11-15, machine check, real backend: clicked Play/Pause through Work → Misc → Eat → Exercise → Shower → Fun, then paused Fun, started and paused Work. Exactly one was running after each switch, and there was no `play()`, no audio element, no ringing card and no `alerting` in the backend. Separately, a stopwatch loaded with `alerting: true` made no sound. Done through the real UI buttons by script, not by a finger.)* Confirm none of them ever produce sound, blink red, or set `alerting` — unaffected by this phase, as expected.

### E. Dismissal via task-complete path

20. Let an event ring, then dismiss it via whatever path marks it completed (`onDismiss` / `dismissEvent` — the only event-dismiss path). *(2026-11-15, machine check, real backend: the event was dismissed last, the sound stopped, the backend showed `completed = true, alerting = false`, and after a reload the card was not ringing and the page was silent.)* Confirm the sound stops the same way a plain dismiss does, and the card shows completed rather than still alerting.

### F. Bundling + kiosk autoplay (4f)

21. Build the frontend for production (`npm run build`, or let the Docker frontend build run it) and confirm the built output references the alarm asset as a local bundled file (hashed filename under the build's assets directory), not a URL — confirm by inspecting the build output or network tab, not by assumption.
22. **On the Pi**, with the kiosk freshly launched (fresh `sudo reboot` or a fresh Chromium relaunch) and **no prior tap anywhere on the screen that session**, trigger a real alarm. Confirm it is audible — this is the check that `--autoplay-policy=no-user-gesture-required` (already in `deploy/kiosk.sh` since Phase 3) actually prevents a silent first ring, now that there's a real sound to test it against.
23. Confirm no error in the browser console and no traceback in `docker compose logs backend` across steps 13–22.

**Results (2026-11-15).**

| Step | Result |
|---|---|
| 21 | **Pass.** `vite build` (run inside the frontend container, output to `/tmp` there) emitted `assets/alarm-CaaFxJjI.wav` (264.68 kB) as a hashed local file; the built JS refers to it by that filename, with no `http(s)` audio URL anywhere. Note: the compose stack serves the Vite **dev** server on :5173, not this build, so the kiosk loads the asset from `/src/assets/alarm.wav` on localhost. Either way nothing comes from the network. |
| 22 | **Pass, on the Pi, with a stand-in for a fresh boot.** A second Chromium was started with the exact flag list printed by `deploy/kiosk.sh --check` (including `--autoplay-policy=no-user-gesture-required`), a brand-new empty profile, and no tap. `navigator.userActivation.hasBeenActive` stayed `false`; the timer reached zero by itself, `play()` resolved ("allowed") and PipeWire listed a **Chromium** stream, both channels `[active]`, on the USB audio card `UACDemoV1.0`. Tapping the card stopped it. **Heard by the user (2026-11-15): the fresh-kiosk first ring passes.** **Not done:** a real `sudo reboot`, so the autologin → labwc → `kiosk.sh` start-up chain was not re-run; this tested the Chromium flags and policy, which is what step 22 exists to check. |
| 23 | **Pass for the runs above** (see the real-backend run in § C, and no console error or exception in the step 22 run). **Not covered:** the Docker backend's own log across a hand-driven session, since these runs used a separate backend on :8081 on purpose. |


## Merge bar

**Real reboot, done (user, 2026-11-15):** after a real `sudo reboot` (autologin → labwc → `kiosk.sh`) the user created an event and its alarm rang. No open items.

- [x] All of 4a–4f checked off in `specs/roadmap.md`.
- [x] Steps 1–23 above pass (machine-checked or user-heard; the real-reboot run is recorded under Merge bar), with any intentional deviation documented in this file rather than silently accepted.
- [x] Existing backend tests pass unmodified (136 before this work, 140 now with the 4 new restart tests).
- [x] The reset button works as specified (steps 1–8): confirm-by-second-tap, user-created timers/stopwatches gone, the six defaults at 0 and paused, events and tasks replaced by the sheet's, persisted across reload and backend restart.
- [x] **Deviation, documented:** 4c–4e needed a 2-line backend fix, because `alerting` was persisted but never restored on startup (see § C, step 18). Detection (`msUntil`, the timer elapsed check) is unchanged.
- [x] Sound is global and single-instance: two simultaneous alarms never produce two overlapping/layered sounds (step 15).
- [x] Sound stops exactly when the *last* alerting card is dismissed, not before (steps 16–17).
- [x] Stopwatches never produce sound (step 19) — confirms the scope boundary in `requirements.md` § Non-goals held in practice, not just in the code's intent.
- [x] The alarm asset is bundled, not fetched over the network, in the production build (step 21).
- [x] The kiosk's first ring of the day is audible with no prior screen interaction (step 22, user-heard 2026-11-15, first on a fresh Chromium with the kiosk flags, then after a real reboot) — the one finding this phase owes back to Phase 3's forward-compat flag.
- [x] No scope creep beyond `requirements.md` — no per-card mute (Phase 8), no volume control, no stopwatch sound, no backend schema/API changes (the 4a `reset` command adds a command, not a column or response field).
- [x] `CLAUDE.md` updated with Phase 4 status and Phase 5 as next.
- [x] README documents the reset button, the alarm asset, the standalone test tools, and the kiosk autoplay dependency.
