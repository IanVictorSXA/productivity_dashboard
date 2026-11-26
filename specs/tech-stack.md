# Tech Stack

## Frontend

- **React 18** + **TypeScript**, built with **Vite**
- **Tailwind CSS v4** for styling
- **Radix UI + shadcn-style components** are the standard component library going forward (`default_shadcn_theme.css` is the theme source of truth).
  - MUI (`@mui/material`, `@mui/icons-material`, `@emotion/*`) is currently installed and in use in places, but is legacy — do not add new MUI usage. Migrate existing MUI components to Radix/shadcn opportunistically as they're touched, rather than in a dedicated rewrite phase.
- **recharts** for charts/graphs (historical stats, Phase 8)
- Package manager: **pnpm** (`pnpm-workspace.yaml` present)

## Backend

- **FastAPI** + **Python**
- **uvicorn** as the ASGI server
- **tzlocal** for local timezone handling

## Database

- **SQLite**, accessed via the stdlib **`sqlite3`** module directly (no ORM). Queries are hand-written in `database.py`; the `dict_factory` row factory returns plain dicts to the API layer.
- Tables: `tasks`, `events`, `stopwatches`, `timers`.
- State is restored from the database on startup — the database is the source of truth, not in-memory state.

## Google Sheets Integration (Phase 3 read path, Phase 8 write path)

- Auth: **Google Cloud service account** (not an OAuth user-consent flow). This means:
  - No interactive login/consent step and no refresh-token lifecycle — the key file is the only credential, which is what makes unattended jobs on a headless Pi reliable.
  - The target spreadsheet must be shared with the service account's email address, or every request 403s.
  - Store the JSON key file on-device outside version control (never commit it); the backend reads its path from configuration.
- Direction of sync:
  - Start of day: load the day's schedule and events from Sheets (**Phase 3**).
  - End of day: upload productivity stats (time per category, totals) to Sheets (**Phase 8**, alongside the analytics that consume that history).

## Alarm Audio (Phase 4)

- Ring sound played in the browser via the standard `Audio`/HTML5 audio API; the sound file is bundled with the frontend so nothing is fetched at ring time.
- Applies to timers hitting zero and events reaching their ring time. Per-card muting arrived in Phase 5 (5d).
- Kiosk-mode caveat: browsers gate autoplay behind a prior user gesture — the dashboard's first interaction of the day generally satisfies this, but it needs verifying on the Pi.

## Dashboard Ordering (Phase 5)

- Stopwatches and timers are **one list** ("Tasks Duration"); a grip handle on each card (lucide `GripVertical`, as on the task rows) starts a drag.
- **Drag mechanism: hand-written pointer events** (`frontend/src/app/dragReorder.tsx`, `useDragReorder`), chosen by a probe on the real touchscreen (Group 1, 2026-11-25): native HTML5 drag works with a mouse but not with a finger on this Chromium, which was the cause of the task-reorder bug (5j). The handle uses `touch-action: none` and pointer capture, and the drop target is found with `document.elementFromPoint`. Tasks and duration cards share this one implementation. `react-dnd` is in `package.json` but is **not used** anywhere — it is HTML5-drag based and would fail on touch the same way.
- **The backend owns order.** The persisted `pos` integer column (on every card table) is set by a `reorder` command that carries the full id list, written in one transaction (`Database.execute_many`); `get_ApiState` returns each list sorted by `(pos, id)`. In-memory lists stay sorted by `id` (binary search depends on it). A new card gets `pos = max + 1` in its list.
- Event order is derived from `ring_time` (ascending), not stored — events are not manually reorderable. Task display order is incomplete-then-completed, derived at render (`frontend/src/app/cardOrder.ts`); `pos` stores the manual order, and a drag on the visible list is mapped back onto the full list so completed tasks keep their slots.
- Cards are a fixed size (224×88 stopwatch/timer, 224×100 event at 1024×600). The display font (Jockey One) has no tabular digits, so `FixedTime` draws each character in its own fixed-width cell.
- A per-card `muted` flag on timers and events is persisted in SQLite (a new column; no migration code, so an existing DB needs a one-time table drop — see the README). The `mute` command sets the flag (never toggles); the alarm plays only while an alerting timer/event is **not** muted.

## Deployment

- **Docker Compose** (`docker-compose.yml`) with separate `frontend` and `backend` services, each with its own `dockerfile`.
- Frontend served on `5173`, backend API on `8080`, both bound to `127.0.0.1` (not exposed beyond the Pi itself).
- Target hardware: **Raspberry Pi 5 + AI HAT+2**, driving a **10-inch touchscreen** running the dashboard in kiosk mode continuously.
- Kiosk autostart (**Phase 3e**): the Pi boots straight into the dashboard unattended. Compose services start on boot via `restart: unless-stopped` plus a systemd unit enabled at the system level; the browser is launched full-screen with no chrome by the desktop session's autostart (Chromium `--kiosk`). Auto-login must be enabled or the session never starts. Since Phase 4 adds alarm audio, the kiosk browser flags are also where an autoplay exemption (e.g. `--autoplay-policy=no-user-gesture-required`) belongs — otherwise the first ring of the day is silent until someone taps the screen.

## Future AI Stack (Phase 9 local AI; voice parked)

- **hailo-ollama** to serve the local LLM on the AI HAT+2 (Ollama-compatible API backed by the Hailo NPU) — Phase 9. Later it is also meant for natural-language intent detection and the eventual conversational assistant, once voice is picked up again.
- **Voice is parked** (retired from the numbered roadmap 2026-11-25). The choices made for it are kept on branch `phase5-voice-commands` (`specs/tech-stack.md` there): **Whisper (tiny)** on the Hailo-10H NPU for speech-to-text, **openWakeWord** with `hey_jarvis` on the CPU for the wake word, `arecord` for mic capture.
- When voice resumes: predefined/rule-based commands come first; natural-language understanding via the local LLM comes after — don't reach for the LLM before the simple command path is solid.
