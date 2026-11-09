"""FastAPI app exposing the productivity dashboard's single `/api` endpoint.

A single `TaskManager` instance (`tm`) is created at import time and lives
for the lifetime of the process, holding all in-memory card state; every
request just calls into it and either mutates it (`POST`) or serializes it
(`GET`).
"""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from classes import TaskManager, Timer, Duration, Event, Task, parse_time, parse_datetime, parse_iso_datetime, Message

# Uvicorn configures its own loggers but leaves the root logger empty at
# WARNING, so without this every `logger.info` in the sheet sync is dropped and
# its warnings print bare, with no timestamp or level. Set before the
# `TaskManager()` below, which is what runs the startup sync.
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = FastAPI()
tm = TaskManager()

app.add_middleware(
    CORSMiddleware,
    # Browsers treat localhost and 127.0.0.1 as different origins even though
    # they're the same host; an SSH-tunneled or hand-typed 127.0.0.1 tab got a
    # 400 "Disallowed CORS origin" on every POST (pause/play/edit/close/sync)
    # while GET still worked, since only POST triggers a preflight.
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/api")
def update_time_card(msg: Message):
    """Apply a single command (create/edit/pause/.../close) to the task manager."""
    tm.process_command(msg)

    return {"success": True}

@app.get("/api")
def get_time_cards():
    """Return the full current board state (tasks, events, durations, last_id)."""
    return tm.get_ApiState()