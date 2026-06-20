python 3.11.15
Edit date_id to local timezone see get_local_timezone.py

Database is cleaned at the end of the day

```bash
git pull https://github.com/IanVictorSXA/productivity_dashboard.git
```

API Messages

All messages are POST'd to API_ENDPOINT (default http://localhost:8080/api). Change this constant at the top of App.tsx. Messages are also logged to the browser console for easy debugging.

Duration – Timer created:

```Json
{ "id": 1, "type": "duration", "type_duration": "timer", "task": "AI Project", "current_time": "02:30:00 PM", "total_time": "01:51:00", "command": "create" }
```

Duration – Timer completed:
```Json
{ "id": 1, "command": "complete" }
```

Duration – Timer paused:
```Json
{ "id": 1, "remaining_time": "01:20:35", "command": "pause" }
```

Duration – Timer/Stopwatch resumed:
```Json
{ "id": 1, "current_time": "02:30:00 PM", "command": "resume" }
```

Duration – Deleted:
```Json
{ "id": 1, "remaining_time": "01:20:35", "command": "delete" }
```

Stopwatch created:
```Json
{ "id": 2, "type": "duration", "type_duration": "stopwatch", "task": "Work", "current_time": "02:30:00 PM", "command": "create" }
```

Event created:
```Json
{ "id": 3, "type": "event", "task": "Lunch 12pm", "ring_time": "2026-06-16T17:00:00.000Z", "command": "create" }
```

Event rings:
```Json
{ "id": 3, "type": "event", "command": "ring", "task": "Lunch 12pm" }
```

get stopwatch json
```Json
{
  "durations": [
    {
      "id": 1007,
      "label": "Work",
      "subtype": "stopwatch",
      "total_ms": 0,
      "accumulated_ms": 45000,
      "started_at": null,
      "alerting": false
    }
  ],
  "events": [],
  "tasks": []
}
```
What each field means
id

Unique numeric identifier for the duration card.
Used by the frontend to track and update the card.
label

The name shown on the card, e.g. "Work".
subtype

Must be "stopwatch" for a stopwatch card.
The frontend treats "timer" differently.
total_ms

For stopwatches, this is effectively ignored.
It can safely be 0 for stopwatch cards.
accumulated_ms

Total elapsed time already recorded before the current run.
If the stopwatch is paused, this is the full elapsed time.
If the stopwatch is running, it is prior elapsed time before the current start.
started_at

Epoch milliseconds when the stopwatch last started/resumed.
If null, the stopwatch is paused/stopped.
If set to a number, the frontend computes current elapsed time as accumulated_ms + (now - started_at).
alerting

Boolean for alert state.
For normal stopwatches this should be false.