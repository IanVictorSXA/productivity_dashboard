from datetime import datetime, timedelta
from pydantic import BaseModel
import bisect

total_time_format = "%H:%M:%S"
time_format = "%I:%M:%S %p" # datetime.strptime("12:00:00 PM", time_format)
datetime_format = "%Y-%m-%d %I:%M:%S %p" # datetime.strptime("2023-01-01 12:00:00 PM", datetime_format)
# parse ISO 8601: date_string = "2023-01-01T12:00:00Z" -
# dt_object = datetime.fromisoformat(date_string.replace('Z', '+00:00'))
zero_timedelta = timedelta()
zero_datetime = datetime.strptime("00:00:00", total_time_format)
parse_total_timedelta = lambda total_time_string: datetime.strptime(total_time_string, total_time_format) - zero_datetime
parse_time = lambda time_string: datetime.combine(datetime.today(), datetime.strptime(time_string, time_format).time())
parse_datetime = lambda datetime_string: datetime.strptime(datetime_string, datetime_format)
parse_iso_datetime = lambda iso_string: datetime.fromisoformat(iso_string.replace('Z', '+00:00'))

def sorted_find_index(sorted_arr, target_id):
    """"Finds the index of a Task object by using an array of tasks sorted by id"""
    index = bisect.bisect_left(sorted_arr, target_id, key=lambda task: task.id)

    if index < len(sorted_arr) and sorted_arr[index] == target_id:
        return index
    return -1

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

    def save(self):
        pass

    def delete(self):
        pass

    def complete(self):
        pass

class Event(Task):
    def __init__(self, id : int, label : str, ringTime : datetime, pos : int = 0):
        super().__init__(id=id, taskType=label, label="event", pos=pos)
        self.ringTime = ringTime

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
        elapsed_before_last_pause = parse_total_timedelta(msg.elapsed)
        self.elapsed = elapsed_before_last_pause
        # TODO save elapsed and paused to sql

    def resume(self, msg: Message):
        self.paused = False
        self.currentTime = parse_time(msg.current_time)
        # TODO save current and paused to sql

    def delete(self, msg: Message):
        self.elapsed = parse_total_timedelta(msg.elapsed)

class Timer(Duration):
    def __init__(self, id: int, typeDuration: str, label: str, currentTime : datetime, totalTime : timedelta, pos : int = 0):
        super().__init__(id=id, typeDuration="timer", label=label, currentTime=currentTime, pos=pos)
        self.typeDuration = typeDuration
        self.currentTime = currentTime
        self.totalTime = totalTime
    
    def pause(self, msg: Message):
        self.paused = True
        self.set_remaining_total(msg)

    def resume(self, msg: Message):
        self.paused = False
        self.currentTime = parse_time(msg.current_time)

    def delete(self, msg: Message):
        self.set_remaining_total(msg)

    def set_remaining_total(self, msg: Message):
        remaining = parse_total_timedelta(msg.remaining_time)
        elapsed_before_pause = self.totalTime - remaining
        self.elapsed += elapsed_before_pause
        self.totalTime = remaining

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
                print("success")
            case "delete":
                self.delete(msg)
            case "pause":
                self.pause(msg)
            case "resume":
                self.resume(msg)
            case _:
                pass

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
        self.durations[index].pause(msg)

    def resume(self, msg : Message):
        index = sorted_find_index(self.durations, msg.id)
        self.durations[index].resume(msg)

    def delete(self, msg : Message):
        match msg.type:
            case "task":
                index = sorted_find_index(self.tasks, msg.id)
                self.tasks[index].delete()
                del self.tasks[index]
            
            case "duration":
                index = (sorted_find_index(self.durations, msg.id))
                self.durations[index].delete()
                del self.durations[index]

            case "event":
                index = (sorted_find_index(self.events, msg.id))
                self.events[index].delete()
                del self.events[index]

    
    def ring(self, msg : Message):
        pass
    
    def complete(self, msg : Message):
        pass