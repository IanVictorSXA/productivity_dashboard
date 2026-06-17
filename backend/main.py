from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI()

class Message(BaseModel):
    id: int
    command: str
    task: str | None = None # label
    type: str | None = None # event, duration, or task
    type_duration: str | None = None # timer or stopwatch
    total_time: str | None = None # total time for the timer
    current_time: str | None = None # current clock time
    remaining_time: str | None = None
    ring_time: str | None = None # time the event should ring
    completed: bool | None = None # is type task object completed?


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
    return {"success": True}

@app.get("/api")
def get_time_card():
    return []