from datetime import datetime, timedelta, timezone
from pydantic import BaseModel
import bisect
import database

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
    command: str
    task: str | None = None # label
    type: str | None = None # event, duration, or task
    type_duration: str | None = None # timer or stopwatch
    total_time: str | None = None # total time for the timer
    current_time: str | None = None # current clock time
    remaining_time: str | None = None
    elapsed: str | None = None
    ring_time: str | None = None # time the event should ring
    completed: bool | None = None # is type task object completed?
    pos: int = 0 # position of task

class Task:
    def __init__(self, id : int, label : str, taskType : str = "task", completed : bool = False, pos : int = 0,):
        self.id = id
        self.type = taskType
        self.label = label
        self.completed = completed
        self.pos = pos
        self.deleted = False
        self.alerting = False

    def save(self):
        pass

    def delete(self, msg : Message):
        self.deleted = True

    def complete(self, msg : Message):
        self.completed = True

    def edit(self, msg : Message):
        self.label = msg.task

    def get_ApiTask(self):
        task = dict(id=self.id, label=self.label, completed=self.completed)
        return task

    def __str__(self):
        return self.label + " id: "  + str(self.id)

class Event(Task):
    def __init__(self, id : int, label : str, ringTime : datetime, pos : int = 0):
        super().__init__(id=id, taskType=label, label="event", pos=pos)
        self.ringTime = ringTime

    def edit(self, msg : Message):
        super().edit(msg)
        self.ringTime = parse_iso_datetime(msg.ring_time)

    def get_ApiEvent(self):
        return self.get_ApiTask() | dict(ring_time=str(self.ringTime))

class Duration(Task):
    def __init__(self, id: int, typeDuration: str, label: str, currentTime : datetime, pos : int = 0):
        super().__init__(id=id, taskType="duration", label=label, pos=pos)
        self.typeDuration = typeDuration
        self.currentTime = currentTime
        self.elapsed = zero_timedelta
        self.paused = True
        # TODO save creation to SQL

    def pause(self, msg : Message):
        self.paused = True
        self.elapsed = parse_total_timedelta(msg.elapsed)
        # TODO save elapsed and paused to sql

    def resume(self, msg: Message):
        self.paused = False
        self.currentTime = parse_time(msg.current_time)
        # TODO save current and paused to sql

    def delete(self, msg: Message):
        super().delete(msg)
        self.elapsed = parse_total_timedelta(msg.elapsed)

    def get_ApiDuration(self):
        elapsed_ms = self.elapsed.total_seconds() * 1000
        started_at = self.currentTime.timestamp() * 1000 if not self.paused else None
        print(started_at)
        stopwatch = dict(id=self.id, label=self.label, subtype="stopwatch",
                         total_ms=0, accumulated_ms=elapsed_ms, started_at=started_at,
                         alerting=False)
        return stopwatch

class Timer(Duration):
    def __init__(self, id: int, typeDuration: str, label: str, currentTime : datetime, totalTime : timedelta, pos : int = 0):
        super().__init__(id=id, typeDuration="timer", label=label, currentTime=currentTime, pos=pos)
        self.typeDuration = typeDuration
        self.currentTime = currentTime
        self.totalTime = totalTime
        self.totalElapsed = zero_timedelta # Total time elapsed accross all edits, self.elapsed is time elapsed without for current time card (no edits)
        self.remaining_time = totalTime

    def pause(self, msg: Message):
        self.paused = True
        self.set_elapsed_remaining(msg)

    def resume(self, msg: Message):
        self.paused = False
        self.currentTime = parse_time(msg.current_time)

    def delete(self, msg: Message):
        super().delete(msg)
        self.totalElapsed += self.elapsed

    def set_elapsed_remaining(self, msg: Message):
        self.remaining_time = parse_total_timedelta(msg.remaining_time)
        self.elapsed = parse_total_timedelta(msg.elapsed)
        # print(self.remaining_time)
        # print(self.elapsed)

    def edit(self, msg : Message):
        super().edit(msg) # takes care of label
        self.totalElapsed += self.elapsed
        self.elapsed = zero_timedelta
        
        self.currentTime = parse_time(msg.current_time)

        self.totalTime = parse_total_timedelta(msg.total_time)
        self.remaining_time = self.totalTime

    def complete(self, msg : Message):
        super().complete()
        self.elapsed = parse_total_timedelta(msg.elapsed)
        self.totalElapsed += self.elapsed

    def get_ApiDuration(self):
        elapsed_ms = self.elapsed.total_seconds() * 1000
        started_at = self.currentTime.timestamp() * 1000 if not self.paused else None
        total_ms = self.totalTime.total_seconds() * 1000
        stopwatch = dict(id=self.id, label=self.label, subtype="timer",
                         total_ms=total_ms, accumulated_ms=elapsed_ms, started_at=started_at,
                         alerting=self.alerting)
        return stopwatch

class TaskManager:
    def __init__(self):
        self.tasks : list[Task] = []
        self.events : list[Event] = []
        self.durations : list[Duration] = []

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
        print(msg)
        match msg.command:
            case "create":
                self.create(msg)
            case "delete":
                self.delete(msg)
            case "pause":
                self.pause(msg)
            case "resume":
                self.resume(msg)
            case "edit":
                self.edit(msg)
            case _:
                pass
    
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
            events=events,
            durations=durations,
            tasks=tasks
        )

    def create(self, msg : Message):
        match msg.type:
            case "task":
                task = Task(msg.id, msg.task)
                self.tasks.append(task)

            case "event":
                event = Event(msg.id, msg.task, parse_iso_datetime(msg.ring_time))
                self.events.append(event)

            case "duration":
                match msg.type_duration:
                    case "stopwatch":
                        stopwatch = Duration(msg.id, msg.type_duration, msg.task, parse_time(msg.current_time))
                        self.durations.append(stopwatch)
                    case "timer":
                        timer = Timer(msg.id, msg.type_duration, msg.task, parse_time(msg.current_time), parse_total_timedelta(msg.total_time), msg.pos)
                        self.durations.append(timer)
                    case _:
                        raise TypeError("msg.type = duration and Invalid msg.type_duration")
            case _:
                raise TypeError("Invalid msg.type")

    def pause(self, msg : Message):
        index = sorted_find_index(self.durations, msg.id)
        if index != -1:
            self.durations[index].pause(msg)
        else:
            print("Card not in array")

    def resume(self, msg : Message):
        index = sorted_find_index(self.durations, msg.id)
        if index != -1:
            self.durations[index].resume(msg)
        else:
            print("Card not in array")

    def delete_helper(self, sorted_ids : list[Task], msg : Message):
        index = sorted_find_index(sorted_ids, msg.id)

        if index != -1:
            sorted_ids[index].delete(msg)
        else:
            print("Card not in array")

        del sorted_ids[index]

    def delete(self, msg : Message):
        match msg.type:
            case "task":
                self.delete_helper(self.tasks, msg)
                print("array", "array:", [str(task) for task in self.tasks])
            
            case "duration":
                self.delete_helper(self.durations, msg)

            case "event":
                self.delete_helper(self.events, msg)
    
    def edit_helper(self, sorted_ids : list[Task], msg : Message):
        index = sorted_find_index(sorted_ids, msg.id)
        if index != -1:
            sorted_ids[index].edit(msg)
        else:
            print("Card not in array")

    def edit(self, msg : Message):
        match msg.type:
            case "task":
                self.edit_helper(self.tasks, msg)
            case "duration":
                self.edit_helper(self.durations, msg)
            case "event":
                self.edit_helper(self.events, msg)

    def ring(self, msg : Message):
        pass
    
    def complete_helper(self, sorted_ids : list[Task], msg : Message):
        index = sorted_find_index(sorted_ids, msg.id)
        if index != -1:
            sorted_ids[index].complete(msg)
        else:
            print("Card not in array")

    def complete(self, msg : Message):
        match msg.type:
            case "task":
                self.complete_helper(self.tasks, msg)
            case "duration":
                self.complete_helper(self.durations, msg)
            case "event":
                self.complete_helper(self.events, msg)

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

