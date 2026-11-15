# Plan — Phase 4: Alarm sound

Numbered groups are the intended implementation order. Each group should be independently committable and leave the app in a working state.

Branch: `phase4-alarm-sound`.

---

## 1. Dashboard reset button (4a)

A third header button — after the sheet-sync button and before the close (✕) button — that returns the dashboard to a clean start-of-day state in one confirmed action. Independent of the sound work: it touches no audio code, and the groups after it do not depend on it. Full behavior is specified in `requirements.md` § Reset button; this is the work list.

**Backend** (`backend/classes.py`) — a new `reset` case in `TaskManager.process_command`, following the `sync_sheets` precedent (the command does its own persisting, so there is no `(command, arguments)` tuple to execute afterwards):

- [x] Every event and task: soft-deleted through the existing `delete` path, so the `deleted = 1` UPDATE is persisted per card. This includes cards whose `source` is `'sheet'` — they are meant to be re-created in the last step, not preserved.
- [x] Every timer, and every stopwatch whose label is not one of the six defaults: soft-deleted the same way.
- [x] The six default stopwatches (`Work`, `Misc`, `Eat`, `Exercise`, `Shower`, `Fun`): kept, set to paused with `elapsed = 0`, persisted. The backend has no list of the defaults today (`MUTEX_LABELS` lives only in `frontend/src/app/App.tsx:22`), so add a matching constant beside the other backend constants with a one-line comment pointing at the frontend one — two places to keep in step, deliberately, rather than inventing an API field for it.
- [x] Then `self.sync_sheets(force=True)`, the same call the manual sync button makes. It never raises (`_run_sheet_sync` catches everything), so a Sheets failure cannot leave the reset half-applied; the outcome lands in `sheet_sync` like any other sync.

**Frontend** (`frontend/src/app/App.tsx`):

- [x] A `Button` (the existing shadcn component, same as the sync button) in the header, between the sync button and the ✕, with a `lucide-react` reset icon (e.g. `RotateCcw`). Unlike the sync button it is **always shown**, including when `sheetSync.status === "disabled"` — reset still clears and zeroes without Sheets.
- [x] Tap-again confirm: first tap puts the button in a visibly different "Confirm?" state (colour change plus text, sized for a finger); it drops back to normal by itself after ~4 seconds. Second tap inside that window sends `{ command: "reset" }`. Timer cleaned up on unmount and on confirm.
- [x] After the command returns, refetch with `fetchState()` and replace `durations`, `events`, `tasks`, `sheetSync` and `_nextId` from the result — the same shape `handleSyncSheets` already uses, but also replacing `durations`, since reset changes those too. Disabled while in flight (reuse a `resetting` flag, like `syncing`).
- [x] No card state is edited locally before the refetch — the backend is the source of truth for what survived — so the screen never shows a state the database does not have.

**Status (2026-11-09)**: code written. Done and checked: the 82 existing backend tests pass unmodified, and a throwaway script against a temp DB confirmed `reset` leaves only the six defaults (paused, 0), no events/tasks, and that a fresh `TaskManager` reload from disk matches. A user-created stopwatch and a timer labelled `Work` were both deleted (timers are matched on type, not label). The walkthrough was then run on the real app (2026-11-09) — results, including two honest gaps (step 6's error variant, step 7's exact scenario), are in `validation.md` § A.

- [x] **Verify**: `validation.md` § A (steps 1–8) on the real app.

## 2. Sound asset + standalone test script (4b)

Nothing here touches the running app — this group only proves the asset and the two playback paths work, before anything depends on them.

- [x] A 3-second synthesized placeholder tone (two 880 Hz beeps in a 1-second pattern, 3 repeats, 44.1 kHz mono 16-bit) generated with `ffmpeg` `aevalsrc`, saved as `frontend/src/assets/alarm.wav` (264 KB). WAV chosen over MP3: `aplay` plays it natively and Chromium plays it with no codec question. Committed; no network fetch.
- [x] `backend/experiments/alarm_test.py`: standalone, imported by nothing. Plays the asset with `aplay -q -d 5`; optional `-D <alsa device>`; exit code is aplay's. Prints a hint to try `-D` if the default device fails.
- [x] Frontend dev page at `/?test=alarm` (`frontend/src/app/AlarmTest.tsx`, chosen in `frontend/src/main.tsx` before `App` renders, so the dashboard and its polling are untouched). It calls `createAlarmAudio()` from the new `frontend/src/app/alarmSound.ts` — the single place the `Audio` settings (asset, `loop = true`) live, which Group 3 will import too. It tries to play **on load with no tap** (the same condition as a real ring on a fresh kiosk) and shows either "Playing…" or the browser's block reason, plus a "Play again" button.
- [x] **Verify on the dev machine**: done (this machine *is* the Pi — see below).
- [x] **Verify on the real Pi**: both tools heard through the Pi's actual speaker (user-confirmed 2026-11-09).

**Status (2026-11-09)**: code written; the 82 backend tests still pass. Checked by machine: the asset plays with `aplay` exit 0 on the USB audio card; the production build emits it as a hashed local file (`assets/alarm-CaaFxJjI.wav`); headless Chromium on the dev page reports "Playing…" with `--autoplay-policy=no-user-gesture-required` and `NotAllowedError` without it. The user then confirmed by ear that both the script and the dev page are audible. Finding: on this Pi, `aplay`'s *default* ALSA device fails (`audio open error: Unknown error 524`, as do both HDMI cards, which have no sink); only `-D plughw:CARD=UACDemoV10,DEV=0` (the USB card, which is also PipeWire's default sink, the path Chromium uses) opens. So `python backend/experiments/alarm_test.py` with no flag fails here by design of the Pi's ALSA setup, not of the script.

## 3. Shared alarm engine (4c, 4d, 4e — the mechanism)

One piece of frontend logic that turns "is anything alerting" into "is the sound playing," independent of what set `alerting` or which card it is. Timers and events already set `alerting` correctly (confirmed in `requirements.md` § Current state) — this group adds the one new side effect, not new detection logic.

- [ ] A single `Audio` instance (module-level or a `useRef`, not per-card), `loop = true`, pointed at the Group 2 asset.
- [ ] A derived boolean, recomputed each render/tick: "at least one event in `events` has `alerting === true`, or at least one duration in `durations` has `subtype === "timer" && alerting === true`." **Stopwatches are deliberately excluded** even though `DurationCard.alerting` exists on them too — the check is written as `subtype === "timer"`, not "any duration," so a defensive/future stopwatch `alerting` flag can never trigger sound by accident.
- [ ] A `useEffect` keyed on that derived boolean: boolean goes false→true starts the loop (`.play()`); goes true→false stops and rewinds it (`.pause()` + `currentTime = 0`, so the next ring starts from the top rather than mid-loop). No-op on any render where the boolean doesn't change, so a second alarm starting while one is already ringing does not restart or layer the sound.
- [ ] **Verify in a desktop browser first** (no Pi needed yet): start one timer, let it ring — sound starts. Start a second timer while the first is still ringing — sound doesn't restart or double up. Dismiss one, the other still rings — sound keeps playing. Dismiss the last one — sound stops.

## 4. Wire it into the dashboard (4c, 4d)

By this point the engine from Group 3 is already reacting to real `alerting` state — this group is mostly verification that nothing needs changing, plus any small adjustment the dev-browser pass in Group 3 surfaced.

- [ ] Confirm a timer reaching zero (the existing `App.tsx:306-310` detection) produces sound with no code change beyond Group 3 — if it doesn't, the derived boolean in Group 3 is checking the wrong field and needs fixing here.
- [ ] Confirm an event reaching its ring time (`App.tsx:292-294`) produces sound the same way.
- [ ] Confirm a stopwatch never produces sound, even if `Stopwatch.ring()` were somehow reached (defensive check — nothing in the frontend calls it today, so this is "confirm it stays impossible," not "exercise a real path").

## 5. Dismissal stops the sound (4e)

Also expected to already hold from Group 3's effect, verified explicitly against the multi-alarm case since that's the one 4e's wording ("stops on dismissal") doesn't spell out on its own.

- [ ] One alerting card, dismissed via tap (`onDismiss`) → sound stops immediately.
- [ ] Two alerting cards (a timer and an event, or two timers) → dismissing the first leaves the sound playing (the second is still undismissed); dismissing the second stops it.
- [ ] A card dismissed via the task-complete path for events (`App.tsx:598-603`, which also sets `completed = true`) stops the sound the same way a plain dismiss does.
- [ ] Reload the page with a card still alerting (state restored from the backend) → sound resumes on load, since the derived boolean is computed from server-restored `alerting`, not from the moment `ring` was called.

## 6. Bundling + kiosk autoplay verification (4f)

- [ ] Confirm the asset is bundled by Vite into the production build (`npm run build` / the Docker frontend build), not fetched at runtime — check the built output references the asset as a local, hashed file, not a URL, and that nothing in Groups 3–5 constructs an `Audio` URL from a network source.
- [ ] **On the real Pi**, with the kiosk running fresh (fresh boot or fresh Chromium launch, no prior tap on the screen that day): trigger a real alarm (a short timer) and confirm it's audible — this is the check that `--autoplay-policy=no-user-gesture-required`, already present in `deploy/kiosk.sh` from Phase 3, actually does its job now that there's a real sound to test against. If the first ring is silent, that's a bug to fix in this phase (the flag may need adjusting, or something else in Chromium's policy is blocking it), not a pre-existing issue to defer.
- [ ] Re-confirm the Group 2 standalone tools (`alarm_test.py`, the dev route) still work after any asset-path changes made along the way — they're the fast way to re-check audio without going through the full dashboard flow.

## 7. Docs and spec updates

- [ ] Check off 4a–4f in `specs/roadmap.md`.
- [ ] Update `CLAUDE.md`: Phase 4 status, and the next phase pointer (Phase 5 — voice: predefined commands). (`CLAUDE.md` is gitignored/untracked, so this doesn't show up in the diff or the commit — it's local-only, per the Phase 3 precedent.)
- [ ] README: one line on the header reset button (what it clears, that it re-pulls from Sheets, that already-passed sheet events are not brought back), plus a short note on the alarm sound (where the asset lives, that it's a placeholder tone and how to swap it, and the `aplay`/dev-route test tools from Group 2 — including that on this Pi the default ALSA device fails, so the documented command is `python backend/experiments/alarm_test.py -D plughw:CARD=UACDemoV10,DEV=0`, with `aplay -L` for finding the device name), plus a note alongside the existing kiosk section that the autoplay flag is what makes the first ring of the day audible.
- [ ] Fold the manual walkthrough results into `validation.md`.

---

## Commit strategy

One commit per group, per CLAUDE.md §6 (`Co-Authored-By` footer, group referenced in the message). No amends. Groups 3–5 are tightly coupled (the engine is useless without being wired in and verified against dismissal) and may reasonably land as one commit if, in practice, nothing needs changing between them — but call that out explicitly in the pre-commit summary rather than silently merging groups.
