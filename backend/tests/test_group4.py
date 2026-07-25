"""Regression tests for Group 4: Audit stopwatch mutual-exclusivity edge cases (0a).

This module tests:
1. Rapid pause/resume switching arriving out of order
2. App restart with stopwatch mid-run
3. Clock changes (DST, manual adjustments)
"""

import pytest
from datetime import timedelta
from classes import Duration, Message


class TestRapidSwitching:
    """Test rapid pause/resume switching arriving out of order."""

    def test_resume_then_pause_sequence(self, test_task_manager, test_db):
        """Test resume followed immediately by pause ends in consistent state."""
        # Create a paused stopwatch
        msg_create = Message(
            id=1,
            command="create",
            label="Work",
            type="duration",
            type_duration="stopwatch",
            current_time="02:30:00 PM",
            elapsed="00:05:00",
            paused=True,
            pos=0
        )
        test_task_manager.process_command(msg_create)
        stopwatch = test_task_manager.durations[0]

        assert stopwatch.paused is True
        assert stopwatch.elapsed == timedelta(minutes=5)

        # Resume the stopwatch
        msg_resume = Message(
            id=1,
            command="resume",
            type="duration",
            current_time="02:30:00 PM"
        )
        test_task_manager.process_command(msg_resume)

        # Immediately pause it (before frontend calculates elapsed)
        msg_pause = Message(
            id=1,
            command="pause",
            type="duration",
            elapsed="00:05:01"  # Slight elapsed time from resume
        )
        test_task_manager.process_command(msg_pause)

        # Verify final state is consistent
        assert stopwatch.paused is True
        assert stopwatch.elapsed == timedelta(minutes=5, seconds=1)

        # Verify DB is consistent
        _, data = test_db.retrieveAll()
        stopwatch_records = [d for d in data if d.get("type_duration") == "stopwatch"]
        assert len(stopwatch_records) == 1
        record = stopwatch_records[0]

        assert record["paused"] == 1
        assert record["elapsed"] == "00:05:01"

    def test_pause_then_resume_sequence(self, test_task_manager, test_db):
        """Test pause followed immediately by resume ends in consistent state."""
        # Create a running stopwatch
        msg_create = Message(
            id=2,
            command="create",
            label="Misc",
            type="duration",
            type_duration="stopwatch",
            current_time="02:30:00 PM",
            elapsed="00:00:00",
            paused=False,
            pos=1
        )
        test_task_manager.process_command(msg_create)
        stopwatch = test_task_manager.durations[0]

        assert stopwatch.paused is False

        # Pause the stopwatch
        msg_pause = Message(
            id=2,
            command="pause",
            type="duration",
            elapsed="00:01:30"
        )
        test_task_manager.process_command(msg_pause)

        # Immediately resume it
        msg_resume = Message(
            id=2,
            command="resume",
            type="duration",
            current_time="02:31:30 PM"
        )
        test_task_manager.process_command(msg_resume)

        # Verify final state is consistent and running
        assert stopwatch.paused is False
        assert stopwatch.elapsed == timedelta(minutes=1, seconds=30)
        # Note: current_time is stored in UTC internally, so we just verify it was updated
        assert stopwatch.current_time is not None

        # Verify DB is consistent
        _, data = test_db.retrieveAll()
        stopwatch_records = [d for d in data if d.get("type_duration") == "stopwatch"]
        assert len(stopwatch_records) == 1
        record = stopwatch_records[0]

        assert record["paused"] == 0

    def test_multiple_rapid_toggles(self, test_task_manager, test_db):
        """Test multiple rapid pause/resume toggles end in consistent state."""
        msg_create = Message(
            id=3,
            command="create",
            label="Waste",
            type="duration",
            type_duration="stopwatch",
            current_time="02:30:00 PM",
            elapsed="00:00:00",
            paused=False,
            pos=2
        )
        test_task_manager.process_command(msg_create)

        # Pause 1
        msg_pause1 = Message(
            id=3, command="pause", type="duration", elapsed="00:00:10"
        )
        test_task_manager.process_command(msg_pause1)
        assert test_task_manager.durations[0].paused is True

        # Resume 1
        msg_resume1 = Message(
            id=3, command="resume", type="duration", current_time="02:30:10 PM"
        )
        test_task_manager.process_command(msg_resume1)
        assert test_task_manager.durations[0].paused is False

        # Pause 2
        msg_pause2 = Message(
            id=3, command="pause", type="duration", elapsed="00:00:20"
        )
        test_task_manager.process_command(msg_pause2)
        assert test_task_manager.durations[0].paused is True

        # Resume 2
        msg_resume2 = Message(
            id=3, command="resume", type="duration", current_time="02:30:20 PM"
        )
        test_task_manager.process_command(msg_resume2)
        assert test_task_manager.durations[0].paused is False

        # Final pause
        msg_pause3 = Message(
            id=3, command="pause", type="duration", elapsed="00:00:30"
        )
        test_task_manager.process_command(msg_pause3)
        assert test_task_manager.durations[0].paused is True

        # Verify DB is in consistent final state
        _, data = test_db.retrieveAll()
        stopwatch_records = [d for d in data if d.get("type_duration") == "stopwatch"]
        assert len(stopwatch_records) == 1
        record = stopwatch_records[0]

        assert record["paused"] == 1
        assert record["elapsed"] == "00:00:30"


class TestAppRestartMidRun:
    """Test app restart with stopwatch left running."""

    def test_running_stopwatch_persists_correct_state(self, test_task_manager, test_db):
        """Test that a running stopwatch persists startedAt and paused=False."""
        msg_create = Message(
            id=1,
            command="create",
            label="Work",
            type="duration",
            type_duration="stopwatch",
            current_time="02:30:00 PM",
            elapsed="00:05:00",
            paused=False,  # Running
            pos=0
        )
        test_task_manager.process_command(msg_create)
        stopwatch = test_task_manager.durations[0]

        # Verify in-memory state
        assert stopwatch.paused is False
        # Note: current_time is stored in UTC internally
        assert stopwatch.current_time is not None
        assert stopwatch.elapsed == timedelta(minutes=5)

        # Verify DB persistence
        _, data = test_db.retrieveAll()
        stopwatch_records = [d for d in data if d.get("type_duration") == "stopwatch"]
        assert len(stopwatch_records) == 1
        record = stopwatch_records[0]

        assert record["paused"] == 0
        # Note: times are converted to UTC when stored in DB
        assert record["current_time"] is not None
        assert record["elapsed"] == "00:05:00"

    def test_paused_stopwatch_persists_correct_state(self, test_task_manager, test_db):
        """Test that a paused stopwatch persists paused=True with correct elapsed."""
        msg_create = Message(
            id=2,
            command="create",
            label="Misc",
            type="duration",
            type_duration="stopwatch",
            current_time="03:15:00 PM",
            elapsed="00:10:30",
            paused=True,  # Paused
            pos=1
        )
        test_task_manager.process_command(msg_create)
        stopwatch = test_task_manager.durations[0]

        # Verify in-memory state
        assert stopwatch.paused is True
        assert stopwatch.elapsed == timedelta(minutes=10, seconds=30)

        # Verify DB persistence
        _, data = test_db.retrieveAll()
        stopwatch_records = [d for d in data if d.get("type_duration") == "stopwatch"]
        assert len(stopwatch_records) == 1
        record = stopwatch_records[0]

        assert record["paused"] == 1
        assert record["elapsed"] == "00:10:30"

    def test_restore_running_stopwatch_on_startup(self, test_task_manager, test_db):
        """Test that retrieve_data restores running stopwatch in correct state."""
        msg_create = Message(
            id=3,
            command="create",
            label="Waste",
            type="duration",
            type_duration="stopwatch",
            current_time="04:00:00 PM",
            elapsed="00:03:45",
            paused=False,  # Running when "crash" occurred
            pos=2
        )
        test_task_manager.process_command(msg_create)

        # Simulate backend restart by creating new TaskManager with same DB
        # Clear the current task manager's data
        test_task_manager.durations.clear()
        test_task_manager.tasks.clear()
        test_task_manager.events.clear()

        # Call retrieve_data to simulate startup
        test_task_manager.retrieve_data()

        # Verify the stopwatch was restored correctly
        assert len(test_task_manager.durations) == 1
        restored = test_task_manager.durations[0]

        assert restored.paused is False
        assert restored.elapsed == timedelta(minutes=3, seconds=45)
        assert restored.label == "Waste"


class TestClockChanges:
    """Test behavior around clock changes (DST, manual adjustments)."""

    def test_parse_time_with_consistent_clock(self, test_task_manager):
        """Test that parse_time works correctly when system clock doesn't change."""
        from classes import parse_time
        from datetime import datetime

        time1_str = "02:30:00 PM"
        time2_str = "03:00:00 PM"

        time1 = parse_time(time1_str)
        time2 = parse_time(time2_str)

        # Both should be on the same date
        assert time1.date() == time2.date()

        # Time2 should be 30 minutes after time1
        diff = time2 - time1
        assert diff.total_seconds() == 1800  # 30 minutes in seconds

    def test_stopwatch_with_extended_running_time(self, test_task_manager, test_db):
        """Test stopwatch that runs for extended period accumulates time correctly."""
        msg_create = Message(
            id=1,
            command="create",
            label="Work",
            type="duration",
            type_duration="stopwatch",
            current_time="09:00:00 AM",
            elapsed="00:00:00",
            paused=False,
            pos=0
        )
        test_task_manager.process_command(msg_create)

        # Simulate multiple pause/resume cycles over extended period
        times = [
            ("10:00:00 AM", "01:00:00"),  # After 1 hour
            ("11:30:00 AM", "02:30:00"),  # After 2.5 hours
            ("02:00:00 PM", "05:00:00"),  # After 5 hours
        ]

        for current_time, total_elapsed in times:
            msg_pause = Message(
                id=1,
                command="pause",
                type="duration",
                elapsed=total_elapsed
            )
            test_task_manager.process_command(msg_pause)

            msg_resume = Message(
                id=1,
                command="resume",
                type="duration",
                current_time=current_time
            )
            test_task_manager.process_command(msg_resume)

        # Final pause at end of day
        msg_final_pause = Message(
            id=1,
            command="pause",
            type="duration",
            elapsed="08:00:00"  # After 8 hours total
        )
        test_task_manager.process_command(msg_final_pause)

        stopwatch = test_task_manager.durations[0]
        assert stopwatch.elapsed == timedelta(hours=8)

        # Verify DB
        _, data = test_db.retrieveAll()
        record = [d for d in data if d.get("type_duration") == "stopwatch"][0]
        assert record["elapsed"] == "08:00:00"
