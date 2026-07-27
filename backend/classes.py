"""Domain model for the productivity dashboard backend.

Defines the `Message` envelope used for every frontend <-> backend API call,
the card classes that hold in-memory state (`Task`, `Event`, `Duration`,
`Timer`), and `TaskManager`, which dispatches incoming `Message`s to the
right card and keeps the SQLite-backed `Database` in sync with memory.

Card classes each expose the same small protocol: a constructor that builds
the object from a `Message`, `get_tuple_to_save()` for the initial INSERT,
one method per supported command (`edit`, `pause`, `ring`, ...) that mutates
in-memory state and returns an `(sql, params)` tuple for `Database.execute`,
and a `get_Api*()` method that serializes the object for the `GET /api`
response.
"""

from datetime import datetime, timedelta, timezone
from pydantic import BaseModel
import bisect
from database import Database

total_time_format = "%H:%M:%S"
time_format = "%I:%M:%S %p" # datetime.strptime("12:00:00 PM", time_format)
datetime_format = "%Y-%m-%d %I:%M:%S %p" # datetime.strptime("2023-01-01 12:00:00 PM", datetime_format)
# parse ISO 8601: date_string = "2023-01-01T12:00:00Z" -
# dt_object = datetime.fromisoformat(date_string.replace('Z', '+00:00'))
zero_timedelta = timedelta()
zero_datetime = datetime.strptime("00:00:00", total_time_format)

# Converts an "HH:MM:SS" duration string (e.g. elapsed/remaining/total_time) into a timedelta.
parse_total_timedelta = lambda total_time_string: datetime.strptime(total_time_string, total_time_format) - zero_datetime

# Converts a "HH:MM:SS AM/PM" clock string into today's date at that time, in UTC.
# Used for current_time fields, which only ever carry a time-of-day, not a date.
parse_time = lambda time_string: datetime.combine(
    datetime.now().date(),
    datetime.strptime(time_string, time_format).time()).astimezone(timezone.utc)

# Parses a "YYYY-MM-DD HH:MM:SS AM/PM" string (unused by current callers, kept for datetime_format).
parse_datetime = lambda datetime_string: datetime.strptime(datetime_string, datetime_format)

# Parses an ISO 8601 datetime string (event ring_time payloads), tolerating a trailing "Z".
parse_iso_datetime = lambda iso_string: datetime.fromisoformat(iso_string.replace('Z', '+00:00'))

class Message(BaseModel):
    """Single request/response envelope shared by every card type and command.

    The frontend POSTs one of these to `/api` for every user action; only the
    fields relevant to `command`/`type` are populated, the rest stay `None`.
    Field names intentionally match what `TaskManager` and the card classes
    read directly off `msg`.
    """
    id: int | None = None
    command: str | None = "create"
    label: str | None = None # label
    type: str | None = None # event, duration, or task
    type_duration: str | None = None # timer or stopwatch
    total_time: str | None = None # total time for the timer
    current_time: str | None = None # current clock time
    remaining_time: str | None = None
    total_elapsed: str | None = None
    elapsed: str | None = None
    ring_time: str | None = None # time the event should ring
    completed: bool | None = None # is type task object completed?
    paused: bool = True # is type task object completed?
    pos: int = 0 # position of task

class Task:
    """A plain to-do item: base class for `Event` and `Duration`/`Timer` too.

    `Event` and `Duration` subclass `Task` purely for the shared id/label/
    completed/pos/deleted/alerting bookkeeping and the default `ring`/
    `stop_ring`/`complete` behavior; each overrides what needs card-specific
    handling (e.g. `Event` and `Duration` override `get_tuple_to_save`,
    `edit`, `ring`, `stop_ring` for their own table/columns).
    """
    def __init__(self, msg : Message):
        """Build a Task from a `create` Message (or a row loaded from the DB)."""
        self.id = msg.id
        self.type = msg.type
        self.label = msg.label
        self.completed = msg.completed
        self.pos = msg.pos

        self.deleted = False
        self.alerting = False


    def get_tuple_to_save(self):
        """SQL + params to INSERT this task's initial row into the `tasks` table."""
        return "INSERT OR IGNORE INTO tasks (id, label, completed, deleted, pos) VALUES(?, ?, ?, ?, ?)", \
                (self.id, self.label, self.completed, self.deleted, self.pos)

    def delete(self, msg : Message = None):
        """Soft-delete: mark deleted so it's excluded from future `retrieveAll()` reads."""
        self.deleted = True

        return "UPDATE tasks SET deleted = 1 WHERE id = ?", \
                (self.id,)

    def complete(self, msg : Message):
        """Toggle completed state (checkbox click)."""
        self.completed = not self.completed

        return "UPDATE tasks SET completed = ? WHERE id = ?", \
                (self.completed, self.id)

    def edit(self, msg : Message):
        """Rename the task's label."""
        self.label = msg.label

        return "UPDATE tasks SET label = ? WHERE id = ?", \
                (self.label, self.id)

    def ring(self, msg: Message):
        """Mark as alerting (tasks don't currently ring in the UI, but the dispatcher supports it uniformly)."""
        self.alerting = True
        return "UPDATE tasks SET alerting = 1 WHERE id = ?", (self.id,)

    def stop_ring(self, msg: Message):
        """Clear the alerting flag (dismiss)."""
        self.alerting = False
        return "UPDATE tasks SET alerting = 0 WHERE id = ?", (self.id,)

    def get_ApiTask(self):
        """Serialize for the `GET /api` response's `tasks` list."""
        task = dict(id=self.id, label=self.label, completed=self.completed)
        return task

    def __str__(self):
        return self.label + " id: "  + str(self.id)

class Event(Task):
    """A one-shot alarm: rings once `ring_time` passes, then stays dismissed.

    Unlike a `Task`, `completed` here doesn't mean "done" in the checkbox
    sense — it means "this ring has been acknowledged" (see `stop_ring`).
    """
    def __init__(self, msg : Message):
        """Build an Event from a `create` Message (or a row loaded from the DB)."""
        super().__init__(msg)
        self.ring_time = parse_iso_datetime(msg.ring_time)
        # Message.completed defaults to None; normalize so it stores/compares as a real bool
        self.completed = bool(self.completed)


    def get_tuple_to_save(self):
        """SQL + params to INSERT this event's initial row into the `events` table."""
        return "INSERT OR IGNORE INTO events (id, label, ring_time, alerting, completed, deleted, pos) VALUES(?, ?, ?, ?, ?, ?, ?)", \
            (self.id, self.label, self.ring_time.isoformat(), self.alerting, self.completed, self.deleted, self.pos)

    def edit(self, msg : Message):
        """Rename and/or reschedule the ring time."""
        self.label = msg.label
        self.ring_time = parse_iso_datetime(msg.ring_time)
        # Editing the ring time supersedes any past ring/dismissal — start fresh
        self.alerting = False
        self.completed = False

        return "UPDATE events SET label = ?, ring_time = ?, alerting = 0, completed = 0 WHERE id = ?", \
                (self.label, msg.ring_time, self.id)

    def delete(self, msg : Message = None):
        """Soft-delete: mark deleted so it's excluded from future `retrieveAll()` reads."""
        self.deleted = True

        return "UPDATE events SET deleted = 1 WHERE id = ?", \
                (self.id,)

    def ring(self, msg: Message):
        """Called when the frontend detects `ring_time` has passed."""
        self.alerting = True
        return "UPDATE events SET alerting = 1 WHERE id = ?", (self.id,)

    def stop_ring(self, msg: Message):
        """Dismiss a ringing event (user clicked it to silence the alert)."""
        # Dismissing a ringing event is the only way an event gets "completed" today —
        # without persisting this, a page refresh re-evaluates msUntil(ring_time) <= 0
        # and immediately re-rings, since ring_time never moves back into the future.
        self.alerting = False
        self.completed = True
        return "UPDATE events SET alerting = 0, completed = 1 WHERE id = ?", (self.id,)

    def get_ApiEvent(self):
        """Serialize for the `GET /api` response's `events` list."""
        return self.get_ApiTask() | dict(ring_time=str(self.ring_time), alerting=self.alerting)

class Duration(Task):
    """A stopwatch: counts up from `elapsed` while running, freezes while paused.

    The frontend does all live-elapsed-time math itself (from `started_at` +
    `accumulated_ms`, see `get_ApiDuration`); the backend only needs to know
    the elapsed time as of the last pause/resume/ring, not track a live clock.
    `Timer` subclasses this and adds a countdown target plus cross-edit
    accumulation (`total_elapsed`).
    """
    def __init__(self, msg):
        """Build a Duration from a `create` Message (or a row loaded from the DB)."""
        super().__init__(msg)
        self.type_duration = msg.type_duration
        self.current_time = parse_time(msg.current_time)
        self.elapsed : timedelta = parse_total_timedelta(msg.elapsed) if msg.elapsed is not None else zero_timedelta
        self.paused = msg.paused

    def get_tuple_to_save(self):
        """SQL + params to INSERT this stopwatch's initial row into the `stopwatches` table."""
        return "INSERT OR IGNORE INTO stopwatches (id, label, current_time, elapsed, alerting, paused, deleted, pos) VALUES(?, ?, ?, ?, ?, ?, ?, ?)", \
            (self.id, self.label, self.current_time.strftime(time_format),
             self.get_elapsed_str(self.elapsed), self.alerting, self.paused, self.deleted, self.pos)

    def get_elapsed_str(self, elapsed : timedelta):
        """Format a timedelta as `HH:MM:SS`, truncating to whole seconds, for storage/display."""
        total_seconds = int(elapsed.total_seconds())
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)

        hhmmss = f"{hours:02}:{minutes:02}:{seconds:02}"

        return hhmmss

    def edit(self, msg : Message):
        """Rename the stopwatch. Timing state is never touched by a stopwatch edit."""
        self.label = msg.label

        return "UPDATE stopwatches SET label = ? WHERE id = ?", \
                (self.label, self.id)

    def pause(self, msg : Message):
        """Freeze the stopwatch; `msg.elapsed` is the frontend's just-computed elapsed time."""
        self.paused = True
        self.elapsed = parse_total_timedelta(msg.elapsed)

        return "UPDATE stopwatches SET paused = 1, elapsed = ? WHERE id = ?", \
                (msg.elapsed, self.id)

    def resume(self, msg: Message):
        """Start (or restart) counting from `msg.current_time`."""
        self.paused = False
        self.current_time = parse_time(msg.current_time)

        return "UPDATE stopwatches SET paused = 0, current_time = ? WHERE id = ?", \
                (msg.current_time, self.id)

    def delete(self, msg: Message):
        """Soft-delete, recording the final elapsed time at time of deletion."""
        self.deleted = True
        self.elapsed = parse_total_timedelta(msg.elapsed)

        return "UPDATE stopwatches SET deleted = 1, elapsed = ? WHERE id = ?", \
                (msg.elapsed, self.id)

    def ring(self, msg: Message):
        """Freeze the stopwatch and mark it alerting (defensive: stopwatches don't ring today, but
        share the same persistence path as timers so a future stopwatch alert would behave correctly)."""
        self.alerting = True
        # Mirrors Timer.ring(): freeze the running state so get_ApiDuration()
        # reports started_at = None on reload instead of "still running".
        self.paused = True
        self.elapsed = parse_total_timedelta(msg.elapsed) if msg.elapsed else self.elapsed
        return "UPDATE stopwatches SET alerting = 1, paused = 1, elapsed = ? WHERE id = ?", \
                (self.get_elapsed_str(self.elapsed), self.id)

    def stop_ring(self, msg: Message):
        """Clear the alerting flag (dismiss)."""
        self.alerting = False
        return "UPDATE stopwatches SET alerting = 0 WHERE id = ?", (self.id,)

    def get_ApiDuration(self):
        """Serialize for the `GET /api` response's `durations` list.

        `started_at` is the epoch-ms timestamp the frontend should measure
        "now minus started_at" from; `None` means paused (frontend adds
        nothing to `accumulated_ms`).
        """
        elapsed_ms = self.elapsed.total_seconds() * 1000
        started_at = self.current_time.timestamp() * 1000 if not self.paused else None
        stopwatch = dict(id=self.id, label=self.label, subtype="stopwatch",
                         total_ms=0, accumulated_ms=elapsed_ms, started_at=started_at,
                         alerting=False)
        return stopwatch

class Timer(Duration):
    """A countdown timer: like `Duration` but counts down to zero and rings.

    Adds `total_time` (the countdown target), `remaining_time`, and
    `total_elapsed` — the sum of elapsed time across all past edits, kept
    separate from `self.elapsed` (the elapsed time since the *current* edit's
    countdown started) so an edit can reset the countdown without losing the
    cumulative time already spent on this timer.
    """
    def __init__(self, msg : Message):
        """Build a Timer from a `create` Message (or a row loaded from the DB)."""
        super().__init__(msg)
        self.total_time = parse_total_timedelta(msg.total_time)
        # Total time elapsed accross all edits, self.elapsed is time elapsed without for current time card (no edits)
        self.total_elapsed = parse_total_timedelta(msg.total_elapsed) if msg.total_elapsed is not None else zero_timedelta
        self.remaining_time = parse_total_timedelta(msg.remaining_time) if msg.remaining_time is not None else self.total_time

    def get_tuple_to_save(self):
        """SQL + params to INSERT this timer's initial row into the `timers` table."""
        return "INSERT OR IGNORE INTO timers (id, label, current_time, total_time, remaining_time, elapsed, total_elapsed, alerting, completed, paused, deleted, pos) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", \
            (self.id, self.label, self.current_time.strftime(time_format), self.get_elapsed_str(self.total_time),
             self.get_elapsed_str(self.remaining_time), self.get_elapsed_str(self.elapsed),
             self.get_elapsed_str(self.total_elapsed), self.alerting, self.completed, self.paused,
             self.deleted, self.pos)

    def pause(self, msg: Message):
        """Freeze the countdown; `msg` carries the frontend's just-computed elapsed/remaining time."""
        self.paused = True
        self.set_elapsed_remaining(msg)

        return "UPDATE timers SET paused = 1, remaining_time = ?, elapsed = ? WHERE id = ?", \
                (msg.remaining_time, msg.elapsed, self.id)

    def resume(self, msg: Message):
        """Resume counting down from `msg.current_time`."""
        self.paused = False
        self.current_time = parse_time(msg.current_time)

        return "UPDATE timers SET paused = 0, current_time = ? WHERE id = ?", \
                (msg.current_time, self.id)

    def delete(self, msg: Message):
        """Soft-delete, folding the final elapsed time into `total_elapsed` for the record."""
        self.deleted = True
        self.elapsed = parse_total_timedelta(msg.elapsed)
        self.total_elapsed += self.elapsed

        return "UPDATE timers SET deleted = 1, total_elapsed = ?, elapsed = ? WHERE id = ?", \
                (self.get_elapsed_str(self.total_elapsed), msg.elapsed, self.id)

    def set_elapsed_remaining(self, msg: Message):
        """Shared helper: update `remaining_time`/`elapsed` from a Message (used by `pause`)."""
        self.remaining_time = parse_total_timedelta(msg.remaining_time)
        self.elapsed = parse_total_timedelta(msg.elapsed)

    def edit(self, msg : Message):
        """Rename and/or reset the countdown to a new `total_time`.

        Folds the elapsed time accrued so far into `total_elapsed` before
        resetting `elapsed`/`remaining_time`, so past progress on this timer
        isn't lost just because the countdown target changed.
        """
        self.label = msg.label
        self.total_elapsed += self.elapsed
        self.elapsed = zero_timedelta

        self.current_time = parse_time(msg.current_time)

        self.total_time = parse_total_timedelta(msg.total_time)
        self.remaining_time = self.total_time

        return "UPDATE timers SET label = ?, total_elapsed = ?, elapsed = ?, \
             current_time = ?, total_time = ?, remaining_time = ? WHERE id = ?", \
        (self.label, self.get_elapsed_str(self.total_elapsed),
         self.get_elapsed_str(self.elapsed), msg.current_time, msg.total_time, msg.total_time,
         self.id)

    def complete(self, msg : Message):
        """Toggle completed state, folding the current elapsed time into `total_elapsed`."""
        self.completed = not self.completed

        self.elapsed = parse_total_timedelta(msg.elapsed)
        self.total_elapsed += self.elapsed

        return "UPDATE timers SET completed = ?, total_elapsed = ?, elapsed = ? WHERE id = ?", \
                (self.completed, self.get_elapsed_str(self.total_elapsed), msg.elapsed, self.id)

    def ring(self, msg: Message):
        """Called when the countdown reaches zero."""
        self.alerting = True
        # A ringing timer has finished counting down and is no longer running —
        # without this, get_ApiDuration() keeps reporting started_at != None,
        # so a page refresh reloads it as still running with elapsed already
        # past total_time, which instantly re-fires ring().
        self.paused = True
        self.elapsed = parse_total_timedelta(msg.elapsed) if msg.elapsed else self.elapsed
        return "UPDATE timers SET alerting = 1, paused = 1, elapsed = ? WHERE id = ?", \
                (self.get_elapsed_str(self.elapsed), self.id)

    def stop_ring(self, msg: Message):
        """Clear the alerting flag (dismiss)."""
        self.alerting = False
        return "UPDATE timers SET alerting = 0 WHERE id = ?", (self.id,)

    def get_ApiDuration(self):
        """Serialize for the `GET /api` response's `durations` list (see `Duration.get_ApiDuration`)."""
        elapsed_ms = self.elapsed.total_seconds() * 1000
        started_at = self.current_time.timestamp() * 1000 if not self.paused else None
        total_ms = self.total_time.total_seconds() * 1000
        timer = dict(id=self.id, label=self.label, subtype="timer",
                         total_ms=total_ms, accumulated_ms=elapsed_ms, started_at=started_at,
                         alerting=self.alerting)
        return timer

class TaskManager:
    """Holds the in-memory card lists and routes each `Message` to the right one.

    `self.tasks`/`self.events`/`self.durations` are kept sorted by `id` at all
    times (see `retrieve_data`) so `sorted_find_index` can locate a card with
    a binary search instead of a linear scan.
    """
    def __init__(self):
        """Open/create the database and rebuild in-memory state from whatever it contains."""
        self.tasks : list[Task] = []
        self.events : list[Event] = []
        self.durations : list[Duration] = []

        self.db = Database()
        self.retrieve_data()
    # id: int | None = None
    # command: str
    # task: str | None = None # label
    # type: str | None = None # event, duration, or task
    # type_duration: str | None = None # timer or stopwatch
    # total_time: str | None = None # total time for the timer
    # current_time: str | None = None # current clock time
    # remaining_time: str | None = None
    # ring_time: str | None = None # time the event should ring
    # completed: bool | None = None # is type task object completed?
    def process_command(self, msg : Message):
        """Entry point for every `POST /api` call: dispatch on `msg.command` and persist the result."""
        command, arguments = "", ()

        match msg.command:
            case "create":
                command, arguments = self.create(msg)
            case "delete":
                command, arguments = self.delete(msg)
            case "pause":
                command, arguments = self.pause(msg)
            case "resume":
                command, arguments = self.resume(msg)
            case "edit":
                command, arguments = self.edit(msg)
            case "complete":
                command, arguments = self.complete(msg)
            case "ring":
                command, arguments = self.ring(msg)
            case "stop_ring":
                command, arguments = self.stop_ring(msg)
            case "close":
                pass
            case _:
                raise NotImplementedError(f"command {msg.command} not implemented")
        
        if command != "":
            self.db.execute(command, arguments)

    def get_ApiState(self):
        """Build the full `GET /api` response: every non-deleted card, plus the last-used id."""
        events = []
        durations = []
        tasks = []

        for event in self.events:
            events.append(event.get_ApiEvent())

        for duration in self.durations:
            durations.append(duration.get_ApiDuration())

        for task in self.tasks:
            tasks.append(task.get_ApiTask())

        return dict(
            last_id = self.db.last_id,
            events=events,
            durations=durations,
            tasks=tasks
        )

    def retrieve_data(self):
        """Rebuild in-memory card lists from every row currently in the database.

        Each DB row is round-tripped through `Message.model_validate` and
        `self.create`, so a reloaded card goes through exactly the same
        construction path as a freshly created one. Lists are sorted by id
        afterwards so `sorted_find_index`'s binary search stays valid.
        """
        last_id, data = self.db.retrieveAll()

        for card in data:
            msg = Message.model_validate(card)
            self.create(msg)

        self.tasks.sort(key=lambda x: x.id)
        self.events.sort(key=lambda x: x.id)
        self.durations.sort(key=lambda x: x.id)


    def create(self, msg : Message):
        """Instantiate the right card class for `msg.type` (and `msg.type_duration`), and save it."""

        match msg.type:
            case "task":
                task = Task(msg)
                self.tasks.append(task)

                return task.get_tuple_to_save()

            case "event":
                event = Event(msg)
                self.events.append(event)

                return event.get_tuple_to_save()
            
            case "duration":
                match msg.type_duration:
                    case "stopwatch":
                        stopwatch = Duration(msg)
                        self.durations.append(stopwatch)

                        return stopwatch.get_tuple_to_save()
                    
                    case "timer":
                        timer = Timer(msg)
                        self.durations.append(timer)

                        return timer.get_tuple_to_save() 

                    case _:
                        raise TypeError("msg.type = duration and Invalid msg.type_duration")
            case _:
                raise TypeError(f"Invalid msg.type: {msg.type}")

    def pause(self, msg : Message):
        """Pause the duration/timer with `msg.id` (durations only — no `type` dispatch needed)."""
        index = sorted_find_index(self.durations, msg.id)
        if index != -1:
            return self.durations[index].pause(msg)
        else:
            print(f"pause: no duration/timer with id={msg.id}")
            return "", ()

    def resume(self, msg : Message):
        """Resume the duration/timer with `msg.id`."""
        index = sorted_find_index(self.durations, msg.id)
        if index != -1:
            return self.durations[index].resume(msg)
        else:
            print(f"resume: no duration/timer with id={msg.id}")
            return "", ()

    def delete_helper(self, sorted_ids : list[Task], msg : Message):
        """Find `msg.id` in `sorted_ids`, remove it from the in-memory list, and soft-delete it in the DB."""
        index = sorted_find_index(sorted_ids, msg.id)

        if index != -1:
            card = sorted_ids[index]
            del sorted_ids[index]
            return card.delete(msg)
        else:
            print(f"delete: no {msg.type} with id={msg.id}")
            return "", ()

    def delete(self, msg : Message):
        """Dispatch a `delete` command to the list matching `msg.type`."""
        match msg.type:
            case "task":
                return self.delete_helper(self.tasks, msg)

            case "duration":
                return self.delete_helper(self.durations, msg)

            case "event":
                return self.delete_helper(self.events, msg)

    def edit_helper(self, sorted_ids : list[Task], msg : Message):
        """Find `msg.id` in `sorted_ids` and edit it in place."""
        index = sorted_find_index(sorted_ids, msg.id)
        if index != -1:
            return sorted_ids[index].edit(msg)
        else:
            print(f"edit: no {msg.type} with id={msg.id}")
            return "", ()

    def edit(self, msg : Message):
        """Dispatch an `edit` command to the list matching `msg.type`."""
        match msg.type:
            case "task":
                return self.edit_helper(self.tasks, msg)
            case "duration":
                return self.edit_helper(self.durations, msg)
            case "event":
                return self.edit_helper(self.events, msg)

    def ring_helper(self, sorted_ids : list[Task], msg : Message):
        """Find `msg.id` in `sorted_ids` and set it alerting."""
        index = sorted_find_index(sorted_ids, msg.id)
        if index != -1:
            return sorted_ids[index].ring(msg)
        else:
            print(f"ring: no {msg.type} with id={msg.id}")
            return "", ()

    def ring(self, msg : Message):
        """Dispatch a `ring` command to the list matching `msg.type`."""
        match msg.type:
            case "task":
                return self.ring_helper(self.tasks, msg)
            case "duration":
                return self.ring_helper(self.durations, msg)
            case "event":
                return self.ring_helper(self.events, msg)

    def stop_ring_helper(self, sorted_ids : list[Task], msg : Message):
        """Find `msg.id` in `sorted_ids` and dismiss its alert."""
        index = sorted_find_index(sorted_ids, msg.id)
        if index != -1:
            return sorted_ids[index].stop_ring(msg)
        else:
            print(f"stop_ring: no {msg.type} with id={msg.id}")
            return "", ()

    def stop_ring(self, msg : Message):
        """Dispatch a `stop_ring` command to the list matching `msg.type`."""
        match msg.type:
            case "task":
                return self.stop_ring_helper(self.tasks, msg)
            case "duration":
                return self.stop_ring_helper(self.durations, msg)
            case "event":
                return self.stop_ring_helper(self.events, msg)

    def complete_helper(self, sorted_ids : list[Task], msg : Message):
        """Find `msg.id` in `sorted_ids` and toggle its completed state."""
        index = sorted_find_index(sorted_ids, msg.id)
        if index != -1:
            return sorted_ids[index].complete(msg)
        else:
            print(f"complete: no {msg.type} with id={msg.id}")
            return "", ()

    def complete(self, msg : Message):
        """Dispatch a `complete` command to the list matching `msg.type`."""
        match msg.type:
            case "task":
                return self.complete_helper(self.tasks, msg)
            case "duration":
                return self.complete_helper(self.durations, msg)
            case "event":
                return self.complete_helper(self.events, msg)

def sorted_find_index(sorted_arr : list[Task], target_id : int):
    """Finds the index of a Task object by using an array of tasks sorted by id"""
    index = bisect.bisect_left(sorted_arr, target_id, key=lambda task : task.id)

    if (index < len(sorted_arr)) and (sorted_arr[index].id == target_id):
        return index
    return -1

