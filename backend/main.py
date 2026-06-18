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
    # print({"id": msg.id, "command": msg.command})
    tm.process_command(msg)

    return {"success": True}

@app.get("/api")
def get_time_card():
    return []