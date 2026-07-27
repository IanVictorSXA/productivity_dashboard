"""FastAPI app exposing the productivity dashboard's single `/api` endpoint.

A single `TaskManager` instance (`tm`) is created at import time and lives
for the lifetime of the process, holding all in-memory card state; every
request just calls into it and either mutates it (`POST`) or serializes it
(`GET`).
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from classes import TaskManager, Timer, Duration, Event, Task, parse_time, parse_datetime, parse_iso_datetime, Message

app = FastAPI()
tm = TaskManager()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
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