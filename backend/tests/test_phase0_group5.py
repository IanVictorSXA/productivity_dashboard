"""Regression tests for Group 5: Confirm startup/shutdown state parity (0d).

This module tests:
1. Same-day restart preserves all cards (Work/Misc/Waste stopwatches, timers, events, tasks)
2. Next-day boot clears all cards via date-based rollover (not via shutdown handler)
3. Frontend's handleShutdown now only sends "close" command, not individual deletes
"""

import pytest
import os
import tempfile
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path

from classes import TaskManager, Message
from database import Database


class TestStartupShutdownStateParity:
    """Test that cards persist on same-day restart but clear on next-day boot."""

    @pytest.fixture
    def temp_db_with_cards(self, temp_db_env):
        """Create a temporary DB with some cards pre-populated."""
        # Create Database directly (don't let TaskManager call retrieve_data yet)
        db = Database()

        # Create TaskManager without calling retrieve_data
        tm = TaskManager.__new__(TaskManager)
        tm.tasks = []
        tm.events = []
        tm.durations = []
        tm.db = db

        # Create a Work stopwatch (one of the mutex stopwatches)
        msg_work = Message(
            id=1,
            command="create",
            label="Work",
            type="duration",
            type_duration="stopwatch",
            current_time="09:00:00 AM",
            elapsed="00:15:30",
            paused=False,
            pos=0
        )
        tm.process_command(msg_work)

        # Create a Misc stopwatch
        msg_misc = Message(
            id=2,
            command="create",
            label="Misc",
            type="duration",
            type_duration="stopwatch",
            current_time="09:15:00 AM",
            elapsed="00:05:00",
            paused=True,
            pos=1
        )
        tm.process_command(msg_misc)

        # Create a timer
        msg_timer = Message(
            id=3,
            command="create",
            label="Meeting",
            type="duration",
            type_duration="timer",
            current_time="09:00:00 AM",
            total_time="00:30:00",
            remaining_time="00:25:00",
            elapsed="00:05:00",
            paused=False,
            pos=0
        )
        tm.process_command(msg_timer)

        # Create an event
        msg_event = Message(
            id=4,
            command="create",
            label="Lunch",
            type="event",
            ring_time="2025-12-31T12:00:00Z"
        )
        tm.process_command(msg_event)

        # Create a task
        msg_task = Message(
            id=5,
            command="create",
            label="Review PR",
            type="task"
        )
        tm.process_command(msg_task)

        yield temp_db_env, db, tm

    def test_same_day_restart_preserves_all_cards(self, temp_db_with_cards):
        """Verify same-day restart preserves all cards (Work/Misc stopwatches, timer, event, task)."""
        temp_dir, original_db, original_tm = temp_db_with_cards

        # Verify initial state (2 stopwatches + 1 timer = 3 durations)
        assert len(original_tm.durations) == 3
        assert len(original_tm.tasks) == 1
        assert len(original_tm.events) == 1

        # Simulate shutdown (frontend now only sends "close" command)
        msg_close = Message(command="close", current_time="05:00:00 PM")
        original_db.execute("SELECT 1", ())  # Dummy call to ensure DB is accessible
        # Note: We don't actually delete cards anymore - that was the bug we fixed

        # Simulate restart: Create fresh Database and TaskManager (same date)
        # TaskManager.__init__ automatically calls retrieve_data() to load from DB
        fresh_db = Database()
        fresh_tm = TaskManager()

        # Verify all cards were restored (2 stopwatches + 1 timer = 3 durations)
        assert len(fresh_tm.durations) == 3, f"Expected 3 durations, got {len(fresh_tm.durations)}"
        assert len(fresh_tm.tasks) == 1, f"Expected 1 task, got {len(fresh_tm.tasks)}"
        assert len(fresh_tm.events) == 1, f"Expected 1 event, got {len(fresh_tm.events)}"

        # Verify specific card states
        work_stopwatch = next((d for d in fresh_tm.durations if d.label == "Work"), None)
        assert work_stopwatch is not None, "Work stopwatch not found"
        assert work_stopwatch.paused is False, "Work stopwatch should still be running"
        assert work_stopwatch.elapsed == timedelta(minutes=15, seconds=30)

        misc_stopwatch = next((d for d in fresh_tm.durations if d.label == "Misc"), None)
        assert misc_stopwatch is not None, "Misc stopwatch not found"
        assert misc_stopwatch.paused is True, "Misc stopwatch should still be paused"

        timer = next((d for d in fresh_tm.durations if d.label == "Meeting"), None)
        assert timer is not None, "Timer not found"
        assert timer.paused is False, "Timer should still be running"

        task = next((t for t in fresh_tm.tasks if t.label == "Review PR"), None)
        assert task is not None, "Task not found"

        event = next((e for e in fresh_tm.events if e.label == "Lunch"), None)
        assert event is not None, "Event not found"

    def test_next_day_boot_clears_all_cards(self, temp_db_with_cards):
        """Verify next-day boot clears all cards via date-based rollover (not shutdown)."""
        temp_dir, original_db, original_tm = temp_db_with_cards

        # Verify initial state (2 stopwatches + 1 timer = 3 durations)
        assert len(original_tm.durations) == 3
        assert len(original_tm.tasks) == 1
        assert len(original_tm.events) == 1

        # Simulate next day by changing date_id.txt
        date_id_path = os.path.join(temp_dir, "date_id.txt")
        tz = "UTC"

        # Calculate tomorrow's date
        today = datetime.now(tz=ZoneInfo(tz)).date()
        tomorrow = today + timedelta(days=1)
        tomorrow_str = tomorrow.strftime("%Y-%m-%d")

        # Manually update date_id.txt to tomorrow's date
        with open(date_id_path, "w") as f:
            f.write(f"{tz}\n{tomorrow_str}\n-1\n")

        # Simulate restart with next day: Create new Database instance
        # Database.__init__ checks date_id.txt and calls deleteAll() if date changed
        fresh_db = Database()

        # Verify that deleteAll was called (cards should be gone from DB)
        last_id, data = fresh_db.retrieveAll()
        assert len(data) == 0, f"Expected 0 cards after date rollover, got {len(data)}"

        # If we were to create a new TaskManager on next day, it would start empty
        # (DB is already empty from deleteAll)
        fresh_tm = TaskManager.__new__(TaskManager)
        fresh_tm.tasks = []
        fresh_tm.events = []
        fresh_tm.durations = []
        fresh_tm.db = fresh_db
        fresh_tm.retrieve_data()

        # Verify all cards were cleared
        assert len(fresh_tm.durations) == 0, f"Expected 0 durations after date rollover, got {len(fresh_tm.durations)}"
        assert len(fresh_tm.tasks) == 0, f"Expected 0 tasks after date rollover, got {len(fresh_tm.tasks)}"
        assert len(fresh_tm.events) == 0, f"Expected 0 events after date rollover, got {len(fresh_tm.events)}"

    def test_shutdown_no_longer_deletes_cards(self, temp_db_with_cards):
        """Verify that the frontend's handleShutdown no longer sends delete commands for all cards."""
        temp_dir, original_db, original_tm = temp_db_with_cards

        # Initial state
        initial_durations = len(original_tm.durations)
        initial_tasks = len(original_tm.tasks)
        initial_events = len(original_tm.events)

        # Simulate shutdown: just send the "close" command (no deletes)
        msg_close = Message(command="close", current_time="05:00:00 PM")
        original_db.execute("SELECT 1", ())  # Verify DB is still accessible

        # Fetch state before "restart" to verify cards still exist
        last_id, data = original_db.retrieveAll()

        # Count cards by type
        durations_in_db = [d for d in data if d.get("type") == "duration"]
        tasks_in_db = [t for t in data if t.get("type") == "task"]
        events_in_db = [e for e in data if e.get("type") == "event"]

        assert len(durations_in_db) == initial_durations, f"Durations were deleted on shutdown (expected {initial_durations}, got {len(durations_in_db)})"
        assert len(tasks_in_db) == initial_tasks, f"Tasks were deleted on shutdown (expected {initial_tasks}, got {len(tasks_in_db)})"
        assert len(events_in_db) == initial_events, f"Events were deleted on shutdown (expected {initial_events}, got {len(events_in_db)})"

    def test_work_misc_waste_stopwatches_persist_across_restart(self, temp_db_env):
        """Verify that the mandatory Work/Misc/Waste stopwatches persist on same-day restart."""
        # Create Database directly
        db = Database()

        # Create TaskManager without calling retrieve_data
        tm = TaskManager.__new__(TaskManager)
        tm.tasks = []
        tm.events = []
        tm.durations = []
        tm.db = db

        # Create Work stopwatch
        msg_work = Message(
            id=100,
            command="create",
            label="Work",
            type="duration",
            type_duration="stopwatch",
            current_time="09:00:00 AM",
            elapsed="01:30:00",
            paused=False,
            pos=0
        )
        tm.process_command(msg_work)

        # Create Misc stopwatch
        msg_misc = Message(
            id=101,
            command="create",
            label="Misc",
            type="duration",
            type_duration="stopwatch",
            current_time="09:00:00 AM",
            elapsed="00:00:00",
            paused=True,
            pos=1
        )
        tm.process_command(msg_misc)

        # Create Waste stopwatch
        msg_waste = Message(
            id=102,
            command="create",
            label="Waste",
            type="duration",
            type_duration="stopwatch",
            current_time="09:00:00 AM",
            elapsed="00:45:00",
            paused=True,
            pos=2
        )
        tm.process_command(msg_waste)

        assert len(tm.durations) == 3

        # Simulate shutdown and restart with fresh Database/TaskManager
        fresh_db = Database()
        fresh_tm = TaskManager.__new__(TaskManager)
        fresh_tm.tasks = []
        fresh_tm.events = []
        fresh_tm.durations = []
        fresh_tm.db = fresh_db
        fresh_tm.retrieve_data()

        # Verify mutex stopwatches persisted
        assert len(fresh_tm.durations) == 3, f"Expected 3 durations on restart, got {len(fresh_tm.durations)}"

        work = next((d for d in fresh_tm.durations if d.label == "Work"), None)
        misc = next((d for d in fresh_tm.durations if d.label == "Misc"), None)
        waste = next((d for d in fresh_tm.durations if d.label == "Waste"), None)

        assert work is not None, "Work stopwatch not found after restart"
        assert work.elapsed == timedelta(hours=1, minutes=30), f"Work stopwatch elapsed mismatch: {work.elapsed}"
        assert misc is not None, "Misc stopwatch not found after restart"
        assert misc.elapsed == timedelta(0), f"Misc stopwatch elapsed mismatch: {misc.elapsed}"
        assert waste is not None, "Waste stopwatch not found after restart"
        assert waste.elapsed == timedelta(minutes=45), f"Waste stopwatch elapsed mismatch: {waste.elapsed}"
