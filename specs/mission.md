# Mission

## Purpose

Build a distraction-free productivity station, running on a dedicated Raspberry Pi touchscreen, that measures how time is actually spent — rather than managing what should be done. The dashboard replaces a to-do list with timers, stopwatches, and events, and turns that raw activity into daily, weekly, and monthly productivity insight.

## Who it's for

A single user (the owner of the Pi station) who wants an always-on, glanceable device on their desk — not a phone app, not a browser tab. The device is trusted to run continuously and to hold state across restarts.

## Core Pillars

1. **Accurate time tracking** — Timers for scheduled sessions, mutually-exclusive stopwatches for open-ended activity categories (Work, Misc, Waste, Exercise, Shower, and Fun). Only one productivity category runs at a time, so recorded time reflects reality, not overlapping guesses.
2. **Distraction-free interaction** — The touchscreen UI should require minimal taps to start/stop/acknowledge. No feeds, no notifications beyond timer/event alarms, no unrelated apps.
3. **Long-term insight, not just logging** — Daily stats are meaningless in isolation. Google Sheets sync exists so trends, graphs, and history persist beyond the device and beyond what SQLite alone is good at surfacing. Sync runs unattended via a service account, so it never depends on the user being present to re-authorize a login.
4. **Hands-free control as a defining long-term goal** — This is not a stretch feature bolted on later; the project is explicitly working toward full voice control (wake word → speech-to-text → intent → action), and the assistant should eventually be able to answer questions about the day (e.g. today's schedule) as well as execute commands. Voice is built last, but it is core to what "done" looks like.

## Non-Goals

- **Not a task manager.** No arbitrary to-do lists, projects, priorities, or kanban boards. If a feature primarily helps someone decide *what* to do next rather than *measure what they did*, it's out of scope.
- **Not multi-user.** No accounts, no auth beyond what's needed for Google Sheets, no per-user data isolation.
- **Not phone/web-first.** The touchscreen kiosk is the primary surface; anything that pulls design attention toward a generic responsive web app works against the mission.

## Success Criteria

- The user can start their day, and the dashboard alone (eventually just their voice) tells them how they're spending their time without them opening a spreadsheet.
- Daily/weekly/monthly time-in-category numbers are trustworthy enough to act on.
- The device requires near-zero maintenance attention — it restores its own state after power loss/restart and syncs to Sheets unattended.
- Voice can reliably perform the example workflow from the readme (start/pause a tracker, create an event) without falling back to touch.
