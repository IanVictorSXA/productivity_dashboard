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
parse_total_timedelta = lambda total_time_string: datetime.strptime(total_time_string, total_time_format) - zero_datetime

parse_time = lambda time_string: datetime.combine(
    datetime.now().date(), 
    datetime.strptime(time_string, time_format).time()).astimezone(timezone.utc)

parse_datetime = lambda datetime_string: datetime.strptime(datetime_string, datetime_format)
parse_iso_datetime = lambda iso_string: datetime.fromisoformat(iso_string.replace('Z', '+00:00'))

class Message(BaseModel): 
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
    def __init__(self, msg : Message):
        self.id = msg.id
        self.type = msg.type
        self.label = msg.label
        self.completed = msg.completed
        self.pos = msg.pos

        self.deleted = False
        self.alerting = False
        

    def get_tuple_to_save(self):
        return "INSERT OR IGNORE INTO tasks (id, label, completed, deleted, pos) VALUES(?, ?, ?, ?, ?)", \
                (self.id, self.label, self.completed, self.deleted, self.pos)

    def delete(self, msg : Message = None):
        self.deleted = True

        return "UPDATE tasks SET deleted = 1 WHERE id = ?", \
                (self.id)

    def complete(self, msg : Message):
        self.completed = not self.completed

        return "UPDATE tasks SET completed = ? WHERE id = ?", \
                (self.completed, self.id) 

    def edit(self, msg : Message):
        self.label = msg.label

        return "UPDATE tasks SET label = ? WHERE id = ?", \
                (self.label, self.id)

    def get_ApiTask(self):
        task = dict(id=self.id, label=self.label, completed=self.completed) 
        return task

    def __str__(self):
        return self.label + " id: "  + str(self.id)

class Event(Task):
    def __init__(self, msg : Message):
        super().__init__(msg)
        self.ring_time = parse_iso_datetime(msg.ring_time)


    def get_tuple_to_save(self):
        return "INSERT OR IGNORE INTO events (id, label, ring_time, deleted, pos) VALUES(?, ?, ?, ?, ?)", \
            (self.id, self.label, self.ring_time.isoformat(), self.deleted, self.pos)

    def edit(self, msg : Message):
        self.label = msg.label
        self.ring_time = parse_iso_datetime(msg.ring_time)
        
        return "UPDATE events SET label = ?, ring_time = ? WHERE id = ?", \
                (self.label, msg.ring_time, self.id)

    def get_ApiEvent(self):
        return self.get_ApiTask() | dict(ring_time=str(self.ring_time))

class Duration(Task):
    def __init__(self, msg):
        super().__init__(msg)
        self.type_duration = msg.type_duration
        self.current_time = parse_time(msg.current_time)
        self.elapsed : timedelta = parse_total_timedelta(msg.elapsed) if msg.elapsed is not None else zero_timedelta
        self.paused = msg.paused

    def get_tuple_to_save(self):
        return "INSERT OR IGNORE INTO stopwatches (id, label, current_time, elapsed, paused, deleted, pos) VALUES(?, ?, ?, ?, ?, ?, ?)", \
            (self.id, self.label, self.current_time.strftime(time_format),
             self.get_elapsed_str(self.elapsed), self.paused, self.deleted, self.pos)
    
    def get_elapsed_str(self, elapsed : timedelta):
        total_seconds = int(elapsed.total_seconds())
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)

        hhmmss = f"{hours:02}:{minutes:02}:{seconds:02}"

        return hhmmss

    def edit(self, msg : Message):
        self.label = msg.label

        return "UPDATE stopwatches SET label = ? WHERE id = ?", \
                (self.label, self.id)

    def pause(self, msg : Message):
        self.paused = True
        self.elapsed = parse_total_timedelta(msg.elapsed)
        
        return "UPDATE stopwatches SET paused = 1, elapsed = ? WHERE id = ?", \
                (msg.elapsed, self.id)

    def resume(self, msg: Message):
        self.paused = False
        self.current_time = parse_time(msg.current_time)
        
        return "UPDATE stopwatches SET paused = 0, current_time = ? WHERE id = ?", \
                (msg.current_time, self.id)

    def delete(self, msg: Message):
        self.deleted = True
        self.elapsed = parse_total_timedelta(msg.elapsed)

        return "UPDATE stopwatches SET deleted = 1, elapsed = ? WHERE id = ?", \
                (msg.elapsed, self.id)

    def get_ApiDuration(self):
        elapsed_ms = self.elapsed.total_seconds() * 1000
        started_at = self.current_time.timestamp() * 1000 if not self.paused else None
        print(started_at)
        stopwatch = dict(id=self.id, label=self.label, subtype="stopwatch",
                         total_ms=0, accumulated_ms=elapsed_ms, started_at=started_at,
                         alerting=False)
        return stopwatch

class Timer(Duration):
    def __init__(self, msg : Message):
        super().__init__(msg)
        self.total_time = parse_total_timedelta(msg.total_time)
        # Total time elapsed accross all edits, self.elapsed is time elapsed without for current time card (no edits)
        self.total_elapsed = parse_total_timedelta(msg.total_elapsed) if msg.total_elapsed is not None else zero_timedelta 
        self.remaining_time = parse_total_timedelta(msg.remaining_time) if msg.remaining_time is not None else self.total_time
        
    def get_tuple_to_save(self):
        return "INSERT OR IGNORE INTO timers (id, label, current_time, total_time, remaining_time, elapsed, total_elapsed, completed, paused, deleted, pos) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", \
            (self.id, self.label, self.current_time.strftime(time_format), self.get_elapsed_str(self.total_time),
             self.get_elapsed_str(self.remaining_time), self.get_elapsed_str(self.elapsed),
             self.get_elapsed_str(self.total_elapsed), self.completed, self.paused,
             self.deleted, self.pos)

    def pause(self, msg: Message):
        self.paused = True
        self.set_elapsed_remaining(msg)

        return "UPDATE timers SET paused = 1, remaining_time = ?, elapsed = ? WHERE id = ?", \
                (msg.remaining_time, msg.elapsed, self.id)

    def resume(self, msg: Message):
        self.paused = False
        self.current_time = parse_time(msg.current_time)

        return "UPDATE timers SET paused = 0, current_time = ? WHERE id = ?", \
                (msg.current_time, self.id)

    def delete(self, msg: Message):
        self.deleted = True
        self.elapsed = parse_total_timedelta(msg.elapsed)
        self.total_elapsed += self.elapsed

        return "UPDATE timers SET deleted = 1, total_elapsed = ?, elapsed = ? WHERE id = ?", \
                (self.get_elapsed_str(self.total_elapsed), msg.elapsed, self.id)

    def set_elapsed_remaining(self, msg: Message):
        self.remaining_time = parse_total_timedelta(msg.remaining_time)
        self.elapsed = parse_total_timedelta(msg.elapsed)
        # print(self.remaining_time)
        # print(self.elapsed)

    def edit(self, msg : Message):
        self.label = msg.label
        self.total_elapsed += self.elapsed
        self.elapsed = zero_timedelta
        
        self.current_time = parse_time(msg.current_time)

        self.total_time = parse_total_timedelta(msg.total_time)
        self.remaining_time = self.total_time

        return "UPDATE timers SET label = ?, total_elapsed = ?, elapsed = ?, \
             current_time = ?, total_time = ?, remaining_time = ? WHERE id = ?", \
        (self.label, self.get_elapsed_str(self.self.total_elapsed), 
         self.get_elapsed_str(self.elapsed), msg.current_time, msg.total_time, msg.total_time,
         self.id)

    def complete(self, msg : Message):
        self.completed = not self.completed

        self.elapsed = parse_total_timedelta(msg.elapsed)
        self.total_elapsed += self.elapsed
    
        return "UPDATE timers SET completed = ?, total_elapsed = ?, elapsed = ? WHERE id = ?", \
                (self.completed, self.get_elapsed_str(self.total_elapsed), msg.elapsed, self.id)

    def get_ApiDuration(self):
        elapsed_ms = self.elapsed.total_seconds() * 1000
        started_at = self.current_time.timestamp() * 1000 if not self.paused else None
        total_ms = self.total_time.total_seconds() * 1000
        timer = dict(id=self.id, label=self.label, subtype="timer",
                         total_ms=total_ms, accumulated_ms=elapsed_ms, started_at=started_at,
                         alerting=self.alerting)
        return timer

class TaskManager:
    def __init__(self):
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
        # print(msg)
        command, arguments = "", ()

        match msg.command:
            case "create":
                print(msg)
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
            case _:
                raise NotImplementedError(f"command {msg.command} not implemented")
        
        if command != "":
            self.db.execute(command, arguments)

    def get_ApiState(self):
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
        last_id, data = self.db.retrieveAll()

        for card in data:
            print("Card: ", card)
            msg = Message.model_validate(card)
            print(msg)
            self.create(msg)


    def create(self, msg : Message):
        
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
        index = sorted_find_index(self.durations, msg.id)
        if index != -1:
            return self.durations[index].pause(msg)
        else:
            print("Card not in array")

    def resume(self, msg : Message):
        index = sorted_find_index(self.durations, msg.id)
        if index != -1:
            return self.durations[index].resume(msg)
        else:
            print("Card not in array")

    def delete_helper(self, sorted_ids : list[Task], msg : Message):
        index = sorted_find_index(sorted_ids, msg.id)

        if index != -1:
            card = sorted_ids[index]
            del sorted_ids[index]
            return card.delete(msg)
        else:
            print("Card not in array")

    def delete(self, msg : Message):
        match msg.type:
            case "task":
                return self.delete_helper(self.tasks, msg)
                # print("array", "array:", [str(task) for task in self.tasks])
            
            case "duration":
                return self.delete_helper(self.durations, msg)

            case "event":
                return self.delete_helper(self.events, msg)
    
    def edit_helper(self, sorted_ids : list[Task], msg : Message):
        index = sorted_find_index(sorted_ids, msg.id)
        if index != -1:
            return sorted_ids[index].edit(msg)
        else:
            print("Card not in array")

    def edit(self, msg : Message):
        match msg.type:
            case "task":
                return self.edit_helper(self.tasks, msg)
            case "duration":
                return self.edit_helper(self.durations, msg)
            case "event":
                return self.edit_helper(self.events, msg)

    def ring(self, msg : Message):
        pass
    
    def complete_helper(self, sorted_ids : list[Task], msg : Message):
        index = sorted_find_index(sorted_ids, msg.id)
        if index != -1:
            return sorted_ids[index].complete(msg)
        else:
            print("Card not in array")

    def complete(self, msg : Message):
        match msg.type:
            case "task":
                return self.complete_helper(self.tasks, msg)
            case "duration":
                return self.complete_helper(self.durations, msg)
            case "event":
                return self.complete_helper(self.events, msg)

def sorted_find_index(sorted_arr : list[Task], target_id : int):
    """"Finds the index of a Task object by using an array of tasks sorted by id"""
    index = bisect.bisect_left(sorted_arr, target_id, key=lambda task : task.id)
    
    if (index < len(sorted_arr)) and (sorted_arr[index].id == target_id):
        return index
    return -1

# task = Task(0, "task 1")
# task2 = Task(1, "task 2", completed=True)

# stopwatch = Duration(2, "stopwatch", "stopwatch paused", parse_time("01:27:00 AM"))
# stopwatch2 = Duration(1, "stopwatch", "stopwatch resumed",parse_time("01:16:00 AM"))
# stopwatch2.paused = False
# stopwatch2.elapsed = parse_total_timedelta("00:10:00")

# timer1 = Timer(4, "timer","paused", parse_time("3:11:00 AM"), parse_total_timedelta("1:20:30"))
# timer2 = Timer(5, "timer","resume", parse_time("3:00:00 AM"), parse_total_timedelta("2:00:00"))
# timer2.paused = False


# tm = TaskManager()

# tm.durations.clear()
# print("test")
# print(parse_time("01:28:00 AM").timestamp())
# print(datetime.now(timezone.utc).timestamp())

# event1 = Event(8, "event 00:30", parse_iso_datetime("2026-06-19T05:30:00.000Z"))

# tm.tasks.append(task)
# tm.tasks.append(task2)

# tm.durations.append(stopwatch)
# tm.durations.append(stopwatch2)

# tm.durations.append(timer1)
# tm.durations.append(timer2)

# tm.events.append(event1)

