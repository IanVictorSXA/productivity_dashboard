# Tech Stack

## Frontend

- **React 18** + **TypeScript**, built with **Vite**
- **Tailwind CSS v4** for styling
- **Radix UI + shadcn-style components** are the standard component library going forward (`default_shadcn_theme.css` is the theme source of truth).
  - MUI (`@mui/material`, `@mui/icons-material`, `@emotion/*`) is currently installed and in use in places, but is legacy — do not add new MUI usage. Migrate existing MUI components to Radix/shadcn opportunistically as they're touched, rather than in a dedicated rewrite phase.
- **recharts** for charts/graphs (historical stats, Phase 2+)
- Package manager: **pnpm** (`pnpm-workspace.yaml` present)

## Backend

- **FastAPI** + **Python**
- **uvicorn** as the ASGI server
- **tzlocal** for local timezone handling

## Database

- **SQLite**, accessed via the stdlib **`sqlite3`** module directly (no ORM). Queries are hand-written in `database.py`; the `dict_factory` row factory returns plain dicts to the API layer.
- Tables: `tasks`, `events`, `stopwatches`, `timers`.
- State is restored from the database on startup — the database is the source of truth, not in-memory state.

## Google Sheets Integration (Phase 2)

- Auth: **OAuth user consent flow** (the user's own Google account, not a service account). This means:
  - An initial interactive login/consent step is required (one-time, or whenever the token needs re-authorization).
  - Token refresh must be handled so the daily unattended upload/download jobs don't silently fail after the access token expires.
  - Store refresh tokens securely on-device; do not commit credentials to the repo.
- Direction of sync:
  - End of day: upload productivity stats (time per category, totals) to Sheets.
  - Start of day: load the day's schedule and events from Sheets.

## Deployment

- **Docker Compose** (`docker-compose.yml`) with separate `frontend` and `backend` services, each with its own `dockerfile`.
- Frontend served on `5173`, backend API on `8080`, both bound to `127.0.0.1` (not exposed beyond the Pi itself).
- Target hardware: **Raspberry Pi 5 + AI HAT+2**, driving a **10-inch touchscreen** running the dashboard in kiosk mode continuously.

## Future AI Stack (Phase 3–4)

- **Whisper** for speech-to-text
- A wake-word detection engine (TBD which one — evaluate options for accuracy/CPU cost on Pi 5 when Phase 3 starts)
- **hailo-ollama** to serve the local LLM on the AI HAT+2 (Ollama-compatible API backed by the Hailo NPU), for natural-language intent detection and the eventual conversational assistant
- Predefined/rule-based commands come first (Phase 3); natural-language understanding via the local LLM comes later (Phase 4) — don't reach for the LLM before the simple command path is solid.
