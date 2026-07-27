# Tech Stack

## Frontend

- **React 18** + **TypeScript**, built with **Vite**
- **Tailwind CSS v4** for styling
- **Radix UI + shadcn-style components** are the standard component library going forward (`default_shadcn_theme.css` is the theme source of truth).
  - MUI (`@mui/material`, `@mui/icons-material`, `@emotion/*`) is currently installed and in use in places, but is legacy — do not add new MUI usage. Migrate existing MUI components to Radix/shadcn opportunistically as they're touched, rather than in a dedicated rewrite phase.
- **recharts** for charts/graphs (historical stats, Phase 7)
- Package manager: **pnpm** (`pnpm-workspace.yaml` present)

## Backend

- **FastAPI** + **Python**
- **uvicorn** as the ASGI server
- **tzlocal** for local timezone handling

## Database

- **SQLite**, accessed via the stdlib **`sqlite3`** module directly (no ORM). Queries are hand-written in `database.py`; the `dict_factory` row factory returns plain dicts to the API layer.
- Tables: `tasks`, `events`, `stopwatches`, `timers`.
- State is restored from the database on startup — the database is the source of truth, not in-memory state.

## Google Sheets Integration (Phase 3 read path, Phase 7 write path)

- Auth: **Google Cloud service account** (not an OAuth user-consent flow). This means:
  - No interactive login/consent step and no refresh-token lifecycle — the key file is the only credential, which is what makes unattended jobs on a headless Pi reliable.
  - The target spreadsheet must be shared with the service account's email address, or every request 403s.
  - Store the JSON key file on-device outside version control (never commit it); the backend reads its path from configuration.
- Direction of sync:
  - Start of day: load the day's schedule and events from Sheets (**Phase 3**).
  - End of day: upload productivity stats (time per category, totals) to Sheets (**Phase 7**, alongside the analytics that consume that history).

## Alarm Audio (Phase 4)

- Ring sound played in the browser via the standard `Audio`/HTML5 audio API; the sound file is bundled with the frontend so nothing is fetched at ring time.
- Applies to timers hitting zero and events reaching their ring time. Per-card muting is Phase 8.
- Kiosk-mode caveat: browsers gate autoplay behind a prior user gesture — the dashboard's first interaction of the day generally satisfies this, but it needs verifying on the Pi.

## Dashboard Ordering (Phase 8)

- **react-dnd** + **react-dnd-html5-backend** (already installed and used for the task list) is the drag-and-drop layer for reordering stopwatch and timer cards; don't add a second DnD library.
- Order is persisted in SQLite as an integer position column per card type, following the existing `pos` pattern on `tasks`.
- Event order is derived from `ring_time` (ascending), not stored — events are not manually reorderable.

## Deployment

- **Docker Compose** (`docker-compose.yml`) with separate `frontend` and `backend` services, each with its own `dockerfile`.
- Frontend served on `5173`, backend API on `8080`, both bound to `127.0.0.1` (not exposed beyond the Pi itself).
- Target hardware: **Raspberry Pi 5 + AI HAT+2**, driving a **10-inch touchscreen** running the dashboard in kiosk mode continuously.
- Kiosk autostart (**Phase 3e**): the Pi boots straight into the dashboard unattended. Compose services start on boot via `restart: unless-stopped` plus a systemd unit enabled at the system level; the browser is launched full-screen with no chrome by the desktop session's autostart (Chromium `--kiosk`). Auto-login must be enabled or the session never starts. Since Phase 4 adds alarm audio, the kiosk browser flags are also where an autoplay exemption (e.g. `--autoplay-policy=no-user-gesture-required`) belongs — otherwise the first ring of the day is silent until someone taps the screen.

## Future AI Stack (Phase 5–6)

- **Whisper** for speech-to-text
- A wake-word detection engine (TBD which one — evaluate options for accuracy/CPU cost on Pi 5 when Phase 5 starts)
- **hailo-ollama** to serve the local LLM on the AI HAT+2 (Ollama-compatible API backed by the Hailo NPU), for natural-language intent detection and the eventual conversational assistant
- Predefined/rule-based commands come first (Phase 5); natural-language understanding via the local LLM comes later (Phase 6) — don't reach for the LLM before the simple command path is solid.
