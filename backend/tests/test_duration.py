"""Tests for Duration (Stopwatch) class and stopwatch-related commands."""

import pytest
from datetime import datetime, timedelta
from classes import Duration, Message


class TestStopwatchCreation:
    """Test stopwatch creation."""

    def test_create_stopwatch(self, test_task_manager):
        """Test creating a stopwatch via process_command."""
        msg = Message(
            id=1,
            command="create",
            label="Work session",
            type="duration",
            type_duration="stopwatch",
            current_time="02:30:00 PM",
            elapsed="00:00:00",
            paused=True,
            pos=0
        )

        test_task_manager.process_command(msg)

        assert len(test_task_manager.durations) == 1
        stopwatch = test_task_manager.durations[0]
        assert stopwatch.id == 1
        assert stopwatch.label == "Work session"
        assert stopwatch.type_duration == "stopwatch"
        assert stopwatch.paused is True
        assert stopwatch.deleted is False

    def test_create_multiple_stopwatches(self, test_task_manager):
        """Test creating multiple stopwatches."""
        for i in range(3):
            msg = Message(
                id=i,
                command="create",
                label=f"Stopwatch {i}",
                type="duration",
                type_duration="stopwatch",
                current_time="02:30:00 PM",
                elapsed="00:00:00",
                paused=True,
                pos=i
            )
            test_task_manager.process_command(msg)

        assert len(test_task_manager.durations) == 3

    def test_stopwatch_elapsed_time_tracking(self, test_task_manager):
        """Test that stopwatch tracks elapsed time."""
        elapsed_time = "00:05:30"
        msg = Message(
            id=1,
            command="create",
            label="Timed stopwatch",
            type="duration",
            type_duration="stopwatch",
            current_time="02:30:00 PM",
            elapsed=elapsed_time,
            paused=True,
            pos=0
        )

        test_task_manager.process_command(msg)

        stopwatch = test_task_manager.durations[0]
        assert stopwatch.elapsed == timedelta(hours=0, minutes=5, seconds=30)

    def test_stopwatch_paused_state(self, test_task_manager):
        """Test stopwatch paused state."""
        msg_paused = Message(
            id=1,
            command="create",
            label="Paused stopwatch",
            type="duration",
            type_duration="stopwatch",
            current_time="02:30:00 PM",
            elapsed="00:00:00",
            paused=True,
            pos=0
        )
        test_task_manager.process_command(msg_paused)
        assert test_task_manager.durations[0].paused is True

        msg_running = Message(
            id=2,
            command="create",
            label="Running stopwatch",
            type="duration",
            type_duration="stopwatch",
            current_time="02:30:00 PM",
            elapsed="00:00:00",
            paused=False,
            pos=1
        )
        test_task_manager.process_command(msg_running)
        assert test_task_manager.durations[1].paused is False


class TestStopwatchCommands:
    """Test stopwatch command handling."""

    def test_pause_stopwatch(self, test_task_manager):
        """Test pausing a running stopwatch."""
        msg_create = Message(
            id=1,
            command="create",
            label="Stopwatch",
            type="duration",
            type_duration="stopwatch",
            current_time="02:30:00 PM",
            elapsed="00:00:00",
            paused=False,
            pos=0
        )
        test_task_manager.process_command(msg_create)
        assert test_task_manager.durations[0].paused is False

        msg_pause = Message(
            id=1,
            command="pause",
            type="duration",
            elapsed="00:02:15"
        )
        test_task_manager.process_command(msg_pause)

        assert test_task_manager.durations[0].paused is True
        assert test_task_manager.durations[0].elapsed == timedelta(minutes=2, seconds=15)

    def test_resume_stopwatch(self, test_task_manager):
        """Test resuming a paused stopwatch."""
        msg_create = Message(
            id=1,
            command="create",
            label="Stopwatch",
            type="duration",
            type_duration="stopwatch",
            current_time="02:30:00 PM",
            elapsed="00:05:00",
            paused=True,
            pos=0
        )
        test_task_manager.process_command(msg_create)
        assert test_task_manager.durations[0].paused is True

        msg_resume = Message(
            id=1,
            command="resume",
            type="duration",
            current_time="02:35:00 PM"
        )
        test_task_manager.process_command(msg_resume)

        assert test_task_manager.durations[0].paused is False

    def test_edit_stopwatch_label(self, test_task_manager):
        """Test editing a stopwatch label."""
        msg_create = Message(
            id=1,
            command="create",
            label="Original label",
            type="duration",
            type_duration="stopwatch",
            current_time="02:30:00 PM",
            elapsed="00:00:00",
            paused=True,
            pos=0
        )
        test_task_manager.process_command(msg_create)

        msg_edit = Message(
            id=1,
            command="edit",
            label="Updated label",
            type="duration"
        )
        test_task_manager.process_command(msg_edit)

        assert test_task_manager.durations[0].label == "Updated label"

    def test_delete_stopwatch(self, test_task_manager):
        """Test deleting a stopwatch."""
        msg_create = Message(
            id=1,
            command="create",
            label="Stopwatch to delete",
            type="duration",
            type_duration="stopwatch",
            current_time="02:30:00 PM",
            elapsed="00:00:00",
            paused=True,
            pos=0
        )
        test_task_manager.process_command(msg_create)

        msg_delete = Message(
            id=1,
            command="delete",
            type="duration",
            elapsed="00:10:00"
        )
        test_task_manager.process_command(msg_delete)

        assert len(test_task_manager.durations) == 0

    def test_stopwatch_pause_resume_cycle(self, test_task_manager):
        """Test multiple pause/resume cycles."""
        # Create
        msg_create = Message(
            id=1,
            command="create",
            label="Cycle test",
            type="duration",
            type_duration="stopwatch",
            current_time="02:00:00 PM",
            elapsed="00:00:00",
            paused=True,
            pos=0
        )
        test_task_manager.process_command(msg_create)

        # Resume
        msg_resume1 = Message(id=1, command="resume", type="duration", current_time="02:00:00 PM")
        test_task_manager.process_command(msg_resume1)
        assert test_task_manager.durations[0].paused is False

        # Pause
        msg_pause1 = Message(id=1, command="pause", type="duration", elapsed="00:05:00")
        test_task_manager.process_command(msg_pause1)
        assert test_task_manager.durations[0].paused is True

        # Resume again
        msg_resume2 = Message(id=1, command="resume", type="duration", current_time="02:05:00 PM")
        test_task_manager.process_command(msg_resume2)
        assert test_task_manager.durations[0].paused is False

        # Pause again
        msg_pause2 = Message(id=1, command="pause", type="duration", elapsed="00:10:00")
        test_task_manager.process_command(msg_pause2)
        assert test_task_manager.durations[0].paused is True
        assert test_task_manager.durations[0].elapsed == timedelta(minutes=10)


class TestStopwatchDatabasePersistence:
    """Test that stopwatch changes persist to database."""

    def test_stopwatch_persists_to_db(self, test_task_manager, test_db):
        """Test that created stopwatch is saved to database."""
        msg = Message(
            id=1,
            command="create",
            label="Persist stopwatch",
            type="duration",
            type_duration="stopwatch",
            current_time="02:30:00 PM",
            elapsed="00:00:00",
            paused=True,
            pos=0
        )
        test_task_manager.process_command(msg)

        _, data = test_db.retrieveAll()
        sw_records = [d for d in data if d.get("type_duration") == "stopwatch"]
        assert len(sw_records) == 1
        assert sw_records[0]["label"] == "Persist stopwatch"

    def test_stopwatch_elapsed_persists(self, test_task_manager, test_db):
        """Test that stopwatch elapsed time persists to database."""
        msg_create = Message(
            id=1,
            command="create",
            label="Stopwatch",
            type="duration",
            type_duration="stopwatch",
            current_time="02:30:00 PM",
            elapsed="00:00:00",
            paused=False,
            pos=0
        )
        test_task_manager.process_command(msg_create)

        msg_pause = Message(
            id=1,
            command="pause",
            type="duration",
            elapsed="00:03:45"
        )
        test_task_manager.process_command(msg_pause)

        _, data = test_db.retrieveAll()
        sw_records = [d for d in data if d.get("type_duration") == "stopwatch"]
        assert sw_records[0]["elapsed"] == "00:03:45"

    def test_stopwatch_paused_state_persists(self, test_task_manager, test_db):
        """Test that stopwatch paused state persists to database."""
        msg_create = Message(
            id=1,
            command="create",
            label="Stopwatch",
            type="duration",
            type_duration="stopwatch",
            current_time="02:30:00 PM",
            elapsed="00:00:00",
            paused=False,
            pos=0
        )
        test_task_manager.process_command(msg_create)

        msg_pause = Message(
            id=1,
            command="pause",
            type="duration",
            elapsed="00:01:00"
        )
        test_task_manager.process_command(msg_pause)

        _, data = test_db.retrieveAll()
        sw_records = [d for d in data if d.get("type_duration") == "stopwatch"]
        assert sw_records[0]["paused"] == 1

    def test_edited_stopwatch_persists(self, test_task_manager, test_db):
        """Test that stopwatch edits persist to database."""
        msg_create = Message(
            id=1,
            command="create",
            label="Original stopwatch",
            type="duration",
            type_duration="stopwatch",
            current_time="02:30:00 PM",
            elapsed="00:00:00",
            paused=True,
            pos=0
        )
        test_task_manager.process_command(msg_create)

        msg_edit = Message(
            id=1,
            command="edit",
            label="Modified stopwatch",
            type="duration"
        )
        test_task_manager.process_command(msg_edit)

        _, data = test_db.retrieveAll()
        sw_records = [d for d in data if d.get("type_duration") == "stopwatch"]
        assert sw_records[0]["label"] == "Modified stopwatch"
