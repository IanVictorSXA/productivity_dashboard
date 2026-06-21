import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo
from contextlib import closing

date_str_format = "%Y-%m-%d"

def dict_factory(cursor, row):
    fields = [column[0] for column in cursor.description]

    return {key: value for key, value in zip(fields, row)}

class Database:
    tables = ["tasks", "events", "stopwatches", "timers"]
    # TODO create a function that handles the context manager protocol for sql connection and cursor
    def __init__(self):
        self.db_name = "productivity.db"

        with sqlite3.connect(self.db_name) as con:
            with closing(con.cursor()) as cursor:
                cursor.execute("""CREATE TABLE IF NOT EXISTS events(
                            id INTEGER UNIQUE, 
                            type TEXT DEFAULT event,
                            label TEXT NOT NULL,
                            ring_time TEXT NOT NULL, 
                            deleted BOOLEAN,
                            pos INTEGER)""")
                
                cursor.execute("""CREATE TABLE IF NOT EXISTS tasks(
                            id INTEGER UNIQUE, 
                            type TEXT DEFAULT task,
                            label TEXT NOT NULL,
                            completed BOOLEAN DEFAULT 0, 
                            deleted BOOLEAN,
                            pos INTEGER)""")
                
                cursor.execute("""CREATE TABLE IF NOT EXISTS stopwatches(
                            id INTEGER UNIQUE, 
                            type TEXT DEFAULT duration,
                            type_duration TEXT DEFAULT stopwatch,
                            label TEXT,
                            current_time TEXT,
                            elapsed TEXT,
                            paused BOOLEAN, 
                            deleted BOOLEAN,
                            pos INTEGER )""")
                
                cursor.execute("""CREATE TABLE IF NOT EXISTS timers(
                            id INTEGER UNIQUE, 
                            type TEXT DEFAULT duration,
                            type_duration TEXT DEFAULT timer,
                            label TEXT,
                            current_time TEXT,
                            total_time TEXT,
                            remaining_time TEXT,
                            elapsed TEXT,
                            total_elapsed TEXT,
                            completed BOOLEAN, 
                            paused BOOLEAN, 
                            deleted BOOLEAN,
                            pos INTEGER )""")
            con.commit()

        self.last_id = -1
        self.filename = "date_id.txt"
        with open(self.filename, "r") as file:
            self.text = file.readlines()
            # print("lines read: ", self.text)
            tz = ZoneInfo(self.text[0].strip())
            # print("today: ", datetime.now(tz=tz))

        if len(self.text) == 1:
            date = datetime.now(tz=tz).date()
            # print("completing text file")
            self.text.extend([date.strftime(date_str_format) + "\n", "" ])
            self.update_textfile()

        elif len(self.text) == 3: 
            date = datetime.strptime(self.text[1].strip(), date_str_format).date()
            today = datetime.now(tz=tz).date()
            # print(date, today, "date is not today? ", date != today)
            if date != today:
                self.deleteAll()
                self.text[1] = today.strftime(date_str_format) + "\n"
                # print("new_text: ", self.text)
                self.update_textfile()
            else:
                self.last_id = int(self.text[2].strip())
        else:
            print("text file does not have correct format")
        # print("last_id is ", self.last_id)

    def update_textfile(self):
        with open(self.filename, "w") as file:
            self.text[2] = str(self.last_id) + "\n"
            file.writelines(self.text)

    def execute(self, command : str, arguments=()):
        print(command, arguments)
        if command.startswith("INSERT"):
            self.last_id = arguments[0]
            self.update_textfile()
            # print(arguments)

        with sqlite3.connect(self.db_name) as con:
            with closing(con.cursor()) as cursor:
                cursor.execute(command, arguments)
            con.commit()

    def retrieveAll(self):
        """Retrieves all the data (array of tuples) + last id used:
        lasd id, data"""
        data = []
        with sqlite3.connect(self.db_name) as con:
            con.row_factory = dict_factory
            with closing(con.cursor()) as cursor:
                for table in self.tables:
                    command = f"SELECT * FROM {table} WHERE deleted = 0"
                    cursor.execute(command)
                    rows = cursor.fetchall()
                    data.extend(rows)
        # print(self.last_id, data)

        return self.last_id, data
    
    def deleteAll(self):
        with sqlite3.connect(self.db_name) as con:
            with closing(con.cursor()) as cursor:
                for table in self.tables:
                    command = f"DELETE FROM {table}"
                    cursor.execute(command)
                    
                con.commit()
                cursor.execute("VACUUM")
        # print("deleted everything")

