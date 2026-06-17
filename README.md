python 3.11.15

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