# Productivity Dashboard

A modern productivity dashboard designed for a dedicated Raspberry Pi touchscreen. The dashboard helps users track how they spend their time using timers, stopwatches, and scheduled events while automatically recording productivity statistics. The long-term goal is to create a distraction-free productivity assistant that can be controlled entirely through voice.

---

# Features

## Time Tracking

The dashboard supports two types of trackers:

### Timers

Timers count down toward zero and are used for scheduled work sessions or events.

Example:

- work session
- Meeting
- Lunch Break

When a timer reaches zero, it begins ringing until acknowledged.

---

### Stopwatches

Stopwatches count upward and are used for tracking the amount of time spent on activities.

Default stopwatches include:

- Work
- Misc
- Waste

to be added:
- exercise
- shower

These three trackers are mutually exclusive (there will be 5 total in the future):

- Starting one automatically pauses the other two.
- Only one productivity category can be active at a time.

This prevents overlapping tracked time and produces more accurate productivity metrics.

---

## Events

The Events section contains countdown timers for upcoming events.

Features:

- Countdown to scheduled time
- Audible notification when completed
- User acknowledgment stops the alarm
- Editable labels
- Add and remove events

---

## Daily Statistics

The dashboard automatically tracks:

- Time spent working
- Time spent on miscellaneous activities
- Time wasted
- Time on shower (in the future)
- Time on workout (in the future)
- Total tracked time

Future versions will provide:

- Daily productivity score
- Weekly summaries
- Monthly trends
- Historical charts

All in google sheets
---

## Google Sheets Integration

At the end of each day, the dashboard automatically uploads productivity statistics to Google Sheets.

This provides:

- Long-term history
- Graphs
- Trend analysis
- Backup of productivity data

At the start of each day, the dashboards automatically loads current day schedule, as well as events, from google sheets.

---

## Local Database

The application stores its state using SQLite.

Saved information includes:

- Timers
- Stopwatches
- Events
- Labels
- Settings

When the dashboard starts, it restores the previous state from the database.

---

# Voice Assistant (Planned)

The dashboard is being designed to become completely hands-free.

Example workflow:

```
Hey Dashboard...

Start work timer.

Pause waste tracking.

Create a meeting in 30 minutes.
```
The AI may also list today's todo list.


### Planned Architecture

```
Microphone
      │
Wake Word Detection
      │
Speech-to-Text
      │
Intent Detection
      │
Dashboard Actions
```

The assistant will initially support predefined commands before eventually expanding to a local AI assistant capable of understanding natural language.

---

# Technology Stack

## Frontend

- React
- TypeScript
- Vite

## Backend

- FastAPI
- Python

## Database

- SQLite

## Future AI

- Whisper (Speech-to-Text)
- Wake-word detection
- Local LLM for natural language commands (running on the AI hat+2)

---

# Hardware

Designed primarily for:

- Raspberry Pi 5 + AI hat+2
- 10-inch touchscreen display

The dashboard is intended to run continuously as a dedicated productivity station.

---

# Project Goals

The project aims to create a simple, distraction-free productivity system that:

- Tracks how time is spent
- Encourages focused work
- Provides long-term productivity analytics
- Requires minimal user interaction
- Can eventually be operated entirely through voice

Unlike traditional task managers, this project focuses on measuring actual time usage rather than managing to-do lists.

---

# Future Roadmap

## Phase 1

- [x] React frontend
- [x] FastAPI backend
- [x] SQLite persistence
- [x] Timers
- [x] Stopwatches
- [x] Events

## Phase 2

- [ ] Google Sheets synchronization
- [ ] Daily summaries
- [ ] Historical statistics
- [ ] Charts and analytics

## Phase 3

- [ ] Wake-word detection
- [ ] Speech-to-text
- [ ] Voice commands
- [ ] Natural language intent detection

## Phase 4

- [ ] Local AI assistant
- [ ] Conversational productivity assistant
- [ ] Daily AI-generated productivity reports
- [ ] Smart productivity recommendations

---

# License

This project is currently under active development.