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

- [x] A `Button` (the existing shadcn component, same as the sync button) in the header, between the sync button and the ✕, labelled with the text **"RST"** (changed 2026-11-15 from a `lucide-react` `RotateCcw` icon — the user wanted it to read as words; the in-flight state pulses the text instead of spinning an icon). Unlike the sync button it is **always shown**, including when `sheetSync.status === "disabled"` — reset still clears and zeroes without Sheets.
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

- [x] A single `Audio` instance (a `useRef` inside the new `useAlarmSound` hook in `frontend/src/app/alarmSound.ts`, created lazily on the first ring via the Group 2 `createAlarmAudio()`, so `loop = true` and the asset are still set in one place).
- [x] A derived boolean, computed in `App.tsx` just before the toggle handlers and passed to the hook: "at least one event in `events` has `alerting === true`, or at least one duration in `durations` has `subtype === "timer" && alerting === true`." **Stopwatches are deliberately excluded** even though `DurationCard.alerting` exists on them too — the check is written as `subtype === "timer"`, not "any duration," so a defensive/future stopwatch `alerting` flag can never trigger sound by accident.
- [x] A `useEffect` keyed on that derived boolean: boolean goes false→true starts the loop (`.play()`); goes true→false stops and rewinds it (`.pause()` + `currentTime = 0`, so the next ring starts from the top rather than mid-loop). No-op on any render where the boolean doesn't change, so a second alarm starting while one is already ringing does not restart or layer the sound.
- [x] **Verify in a browser first** (no Pi needed yet; headless Chromium here, see status below): start one timer, let it ring — sound starts. Start a second timer while the first is still ringing — sound doesn't restart or double up. Dismiss one, the other still rings — sound keeps playing. Dismiss the last one — sound stops.

**Status (2026-11-15)**: code written (`useAlarmSound` in `alarmSound.ts`, one call in `App.tsx`). The effect's cleanup does the stop (`pause()` + `currentTime = 0`), so "no-op when the boolean doesn't change" is React's own dependency check rather than hand-written logic. `play()` rejections (browser blocks it, or `AbortError` from a pause before it starts) are caught and logged with `console.warn`, so a blocked first ring leaves the card ringing visually and does not throw. Checked by machine, not by ear: a throwaway CDP script (kept in the session scratchpad, not committed) ran headless Chromium against the Vite dev server with the backend **faked at the network layer**, so the real `productivity.db` and spreadsheet were never touched (the real backend log showed 0 POSTs). 19/19 checks pass — results in `validation.md` § C. 136 backend tests pass; no backend change.

## 4. Wire it into the dashboard (4c, 4d)

By this point the engine from Group 3 is already reacting to real `alerting` state — this group is mostly verification that nothing needs changing, plus any small adjustment the dev-browser pass in Group 3 surfaced.

- [x] Confirm a timer reaching zero (the existing `App.tsx:306-310` detection) produces sound with no code change beyond Group 3 — if it doesn't, the derived boolean in Group 3 is checking the wrong field and needs fixing here.
- [x] Confirm an event reaching its ring time (`App.tsx:292-294`) produces sound the same way.
- [x] Confirm a stopwatch never produces sound, even if `Stopwatch.ring()` were somehow reached (defensive check — nothing in the frontend calls it today, so this is "confirm it stays impossible," not "exercise a real path").

**Status (2026-11-15)**: all three confirmed in the same headless run as Group 3 — a timer and an event each reached zero through the app's own detection code and started the one shared loop; a stopwatch arriving with `alerting: true` produced no `play()` and no audio element. **No change was needed beyond Group 3.** Not exercised: the real backend's `ring` persistence round trip (the faked backend just says 200), which Phase 0 Group 3 already covers in pytest.

## 5. Dismissal stops the sound (4e)

Also expected to already hold from Group 3's effect, verified explicitly against the multi-alarm case since that's the one 4e's wording ("stops on dismissal") doesn't spell out on its own.

- [x] One alerting card, dismissed via tap (`onDismiss`) → sound stops immediately.
- [x] Two alerting cards (a timer and an event, or two timers) → dismissing the first leaves the sound playing (the second is still undismissed); dismissing the second stops it.
- [x] A card dismissed via the event path (`dismissEvent`, `App.tsx` ~line 647, which also sets `completed = true`; the "task-complete path" wording in the first draft of this plan was stale — there is only this one event-dismiss function) stops the sound the same way a plain dismiss does.
- [x] Reload the page with a card still alerting (state restored from the backend) → sound resumes on load, since the derived boolean is computed from server-restored `alerting`, not from the moment `ring` was called.

**Status (2026-11-15)**: verified in the same headless run, with three cards ringing (two timers, one event) dismissed one at a time: the sound kept playing after the first and second dismissals and stopped, rewound to 0, after the third. A page load with a timer and an event already `alerting` from the server started one loop with no new `ring` POST. Steps 13–17 were then **heard on the Pi's speaker and passed (user, 2026-11-15)**.

**Correction (2026-11-15, same day): the "reload with a card still alerting" item above only held for a page reload, not a backend restart.** Run against the real backend code, a restart mid-ring dropped the ringing flag: `alerting` was written to the database but `Message` had no such field and `Task.__init__` hard-coded `False`, so it was never read back. A ringing timer came back silent and undismissable; a ringing event re-rang only because the page's own countdown check re-sent `ring`. Fixed with 2 lines in `backend/classes.py` and 4 regression tests (`test_phase0_group3.py::TestAlertingSurvivesRestart`); with the fix, the real-backend run passes 14/14 (`validation.md` § C). 140 backend tests pass. This is the one backend change the sound work needed, contrary to the first draft of `requirements.md`.

## 6. Bundling + kiosk autoplay verification (4f)

- [x] Confirm the asset is bundled by Vite into the production build (`npm run build` / the Docker frontend build), not fetched at runtime — check the built output references the asset as a local, hashed file, not a URL, and that nothing in Groups 3–5 constructs an `Audio` URL from a network source.
- [x] **On the real Pi**, with the kiosk running fresh (fresh boot or fresh Chromium launch, no prior tap on the screen that day): trigger a real alarm (a short timer) and confirm it's audible — this is the check that `--autoplay-policy=no-user-gesture-required`, already present in `deploy/kiosk.sh` from Phase 3, actually does its job now that there's a real sound to test against. If the first ring is silent, that's a bug to fix in this phase (the flag may need adjusting, or something else in Chromium's policy is blocking it), not a pre-existing issue to defer.
- [x] Re-confirm the Group 2 standalone tools (`alarm_test.py`, the dev route) still work after any asset-path changes made along the way — they're the fast way to re-check audio without going through the full dashboard flow.

**Status (2026-11-15)**: build check done — `vite build` emits `assets/alarm-CaaFxJjI.wav` as a hashed local file, referenced by filename, no network audio URL anywhere. Autoplay check done with a stand-in for a fresh boot: a second Chromium with exactly the flags `deploy/kiosk.sh --check` prints, a brand-new profile and no tap; the timer rang by itself, `play()` was allowed, and PipeWire showed a Chromium stream active on the USB card. **Not done:** a real `sudo reboot` (so the autologin → `kiosk.sh` chain was not re-run). The user then heard that first ring and it passed (2026-11-15). The Group 2 tools were re-run the same day: `alarm_test.py -D plughw:CARD=UACDemoV10,DEV=0` exits 0 (and with no `-D` still fails with `Unknown error 524`, as documented); `/?test=alarm` in a fresh kiosk-flag Chromium with no tap showed "Playing for 5s (loop on)" then "Finished — the browser allowed playback", `hasBeenActive = false`. Both are **machine-checked; audibility of this re-run is for the user to confirm by ear** (both were heard in Group 2 and the code path is unchanged).

## 7. Docs and spec updates

- [x] Check off 4a–4f in `specs/roadmap.md`.
- [x] Update `CLAUDE.md`: Phase 4 status, and the next phase pointer (Phase 5 — voice: predefined commands). (`CLAUDE.md` is gitignored/untracked, so this doesn't show up in the diff or the commit — it's local-only, per the Phase 3 precedent.)
- [x] README: one line on the header reset button (what it clears, that it re-pulls from Sheets, that already-passed sheet events are not brought back), plus a short note on the alarm sound (where the asset lives, that it's a placeholder tone and how to swap it, and the `aplay`/dev-route test tools from Group 2 — including that on this Pi the default ALSA device fails, so the documented command is `python backend/experiments/alarm_test.py -D plughw:CARD=UACDemoV10,DEV=0`, with `aplay -L` for finding the device name), plus a note alongside the existing kiosk section that the autoplay flag is what makes the first ring of the day audible.
- [x] Fold the manual walkthrough results into `validation.md`.

---

## Commit strategy

One commit per group, per CLAUDE.md §6 (`Co-Authored-By` footer, group referenced in the message). No amends. Groups 3–5 are tightly coupled (the engine is useless without being wired in and verified against dismissal) and may reasonably land as one commit if, in practice, nothing needs changing between them — but call that out explicitly in the pre-commit summary rather than silently merging groups.

**Status (2026-11-15)**: Group 7 done (roadmap boxes, README sections "Reset button" and "Alarm sound" plus the `reset` API entry, `validation.md` merge bar, local `CLAUDE.md`). The walkthrough results were already recorded in `validation.md` as each group ran, so "folding them in" was ticking the merge bar. The user heard the fresh-kiosk first ring and it passed (step 22, 2026-11-15). The one open item is a real `sudo reboot`, which was not run.
