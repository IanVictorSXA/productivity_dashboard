import sqlite3

tables = ["task", "event", "stopwatch", "timer"]

con = sqlite3.connect("productivity.db", detect_types=sqlite3.PARSE_DECLTYPES)

cur = con.cursor()

res = cur.execute("SELECT name FROM sqlite_master")

if res.fetchone() == None:
    cur.execute("""CREATE TABLE event(
                id INTEGER UNIQUE, 
                label TEXT,
                ring_time TIMESTAMP, 
                pos INTEGER)""")
    
    cur.execute("""CREATE TABLE task(
                id INTEGER UNIQUE, 
                label TEXT NOT NULL,
                completed BOOLEAN, 
                pos INTEGER)""")
    
    cur.execute("""CREATE TABLE stopwatch(
                id INTEGER UNIQUE, 
                label TEXT,
                current_time TIMESTAMP,
                elapsed TIMESTAMP,
                paused BOOLEAN, 
                deleted BOOLEAN,
                pos INTEGER UNIQUE)""")
    
    cur.execute("""CREATE TABLE timer(
                id INTEGER UNIQUE, 
                label TEXT,
                total_time TIMESTAMP,
                remaining TIMESTAMP,
                current_time TIMESTAMP,
                elapsed TIMESTAMP,
                total_elapsed TIMESTAMP,
                completed, 
                paused BOOLEAN, 
                deleted BOOLEAN,
                pos INTEGER UNIQUE)""")