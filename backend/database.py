"""SQLite persistence layer, plus the daily rollover mechanism.

`Database` owns the `productivity.db` schema (tasks/events/stopwatches/
timers) and `date_id.txt`, a small sidecar file that tracks the last date the
app ran and the last id it handed out. On every startup, if `date_id.txt`'s
stored date doesn't match today, all tables are wiped (`deleteAll`) so each
calendar day starts from a clean board; if it matches, existing rows are left
alone so a same-day restart (e.g. a Pi reboot) doesn't lose in-progress state.
"""

import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo
from contextlib import closing

date_str_format = "%Y-%m-%d"

def dict_factory(cursor, row):
    """sqlite3 row_factory that returns each row as a `{column_name: value}` dict."""
    fields = [column[0] for column in cursor.description]

    return {key: value for key, value in zip(fields, row)}

class Database:
    """Owns the SQLite connection lifecycle, schema, and the date-based rollover."""
    tables = ["tasks", "events", "stopwatches", "timers"]
    # TODO create a function that handles the context manager protocol for sql connection and cursor
    def __init__(self):
        """Create the schema if needed, then reconcile `date_id.txt` against today's date.

        `date_id.txt` has three lines: an IANA timezone name, the last-seen
        date (`YYYY-MM-DD`), and the last-used id. If the stored date is
        today, `self.last_id` is restored from it and existing rows are kept.
        If it's a different day, `deleteAll()` runs and the file is rewritten
        for today. A missing/malformed file (wrong line count, or an
        unparseable date) is treated as first-run and reinitialized rather
        than raising.
        """
        self.db_name = "productivity.db"

        with sqlite3.connect(self.db_name) as con:
            with closing(con.cursor()) as cursor:
                cursor.execute("""CREATE TABLE IF NOT EXISTS events(
                            id INTEGER UNIQUE,
                            type TEXT DEFAULT event,
                            label TEXT NOT NULL,
                            ring_time TEXT NOT NULL,
                            alerting BOOLEAN DEFAULT 0,
                            completed BOOLEAN DEFAULT 0,
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
                            alerting BOOLEAN DEFAULT 0,
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
                            alerting BOOLEAN DEFAULT 0,
                            completed BOOLEAN,
                            paused BOOLEAN,
                            deleted BOOLEAN,
                            pos INTEGER )""")
            con.commit()

        self.last_id = -1
        self.filename = "date_id.txt"
        with open(self.filename, "r") as file:
            self.text = file.readlines()
            tz = ZoneInfo(self.text[0].strip())

        if len(self.text) == 1:
            date = datetime.now(tz=tz).date()
            self.text.extend([date.strftime(date_str_format) + "\n", "" ])
            self.update_textfile()

        elif len(self.text) == 3:
            try:
                date = datetime.strptime(self.text[1].strip(), date_str_format).date()
                today = datetime.now(tz=tz).date()
                if date != today:
                    self.deleteAll()
                    self.text[1] = today.strftime(date_str_format) + "\n"
                    self.update_textfile()
                else:
                    self.last_id = int(self.text[2].strip())
            except (ValueError, IndexError):
                print("date_id.txt is corrupted, reinitializing")
                today = datetime.now(tz=tz).date()
                self.text[1] = today.strftime(date_str_format) + "\n"
                self.text[2] = "-1\n"
                self.update_textfile()
        else:
            print("text file does not have correct format, reinitializing")
            today = datetime.now(tz=tz).date()
            self.text = [self.text[0], today.strftime(date_str_format) + "\n", "-1\n"]
            self.update_textfile()

    def update_textfile(self):
        """Rewrite `date_id.txt` with the current `self.last_id` (line 1 timezone / line 2 date are untouched here)."""
        with open(self.filename, "w") as file:
            self.text[2] = str(self.last_id) + "\n"
            file.writelines(self.text)

    def execute(self, command : str, arguments=()):
        """Run a single SQL statement against `productivity.db`.

        Every card's `get_tuple_to_save()` puts `id` first in its INSERT
        params, so an `INSERT` here also updates and persists `last_id` —
        the id-tracking side effect is inferred from the SQL keyword rather
        than passed explicitly.
        """
        if command.startswith("INSERT"):
            self.last_id = arguments[0]
            self.update_textfile()

        with sqlite3.connect(self.db_name) as con:
            with closing(con.cursor()) as cursor:
                cursor.execute(command, arguments)
            con.commit()

    def retrieveAll(self):
        """Retrieves all the data (array of tuples) + last id used:
        last id, data"""
        data = []
        with sqlite3.connect(self.db_name) as con:
            con.row_factory = dict_factory
            with closing(con.cursor()) as cursor:
                for table in self.tables:
                    command = f"SELECT * FROM {table} WHERE deleted = 0"
                    cursor.execute(command)
                    rows = cursor.fetchall()
                    data.extend(rows)

        return self.last_id, data
    
    def deleteAll(self):
        """Wipe every table (the daily-rollover path) and reclaim disk space via `VACUUM`."""
        with sqlite3.connect(self.db_name) as con:
            with closing(con.cursor()) as cursor:
                for table in self.tables:
                    command = f"DELETE FROM {table}"
                    cursor.execute(command)
                    
                con.commit()
                cursor.execute("VACUUM")

