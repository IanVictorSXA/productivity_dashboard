"""Tests for Timer class and timer-related commands."""

import pytest
from datetime import timedelta
from classes import Timer, Message


class TestTimerCreation:
    """Test timer creation."""

    def test_create_timer(self, test_task_manager):
        """Test creating a timer via process_command."""
        msg = Message(
            id=1,
            command="create",
            label="Cooking timer",
            type="duration",
            type_duration="timer",
            current_time="02:30:00 PM",
            total_time="00:10:00",
            remaining_time="00:10:00",
            elapsed="00:00:00",
            total_elapsed="00:00:00",
            completed=False,
            paused=True,
            pos=0
        )

        test_task_manager.process_command(msg)

        assert len(test_task_manager.durations) == 1
        timer = test_task_manager.durations[0]
        assert timer.id == 1
        assert timer.label == "Cooking timer"
        assert timer.type_duration == "timer"
        assert timer.paused is True
        assert timer.deleted is False
        assert timer.completed is False

    def test_create_multiple_timers(self, test_task_manager):
        """Test creating multiple timers."""
        for i in range(3):
            msg = Message(
                id=i,
                command="create",
                label=f"Timer {i}",
                type="duration",
                type_duration="timer",
                current_time="02:30:00 PM",
                total_time=f"00:{i*5}:00",
                remaining_time=f"00:{i*5}:00",
                elapsed="00:00:00",
                total_elapsed="00:00:00",
                completed=False,
                paused=True,
                pos=i
            )
            test_task_manager.process_command(msg)

        assert len(test_task_manager.durations) == 3

    def test_timer_total_time_tracking(self, test_task_manager):
        """Test that timer tracks total time."""
        msg = Message(
            id=1,
            command="create",
            label="25 min timer",
            type="duration",
            type_duration="timer",
            current_time="02:30:00 PM",
            total_time="00:25:00",
            remaining_time="00:25:00",
            elapsed="00:00:00",
            total_elapsed="00:00:00",
            completed=False,
            paused=True,
            pos=0
        )

        test_task_manager.process_command(msg)

        timer = test_task_manager.durations[0]
        assert timer.total_time == timedelta(minutes=25)
        assert timer.remaining_time == timedelta(minutes=25)

    def test_timer_total_elapsed_tracking(self, test_task_manager):
        """Test that timer tracks total_elapsed across edits."""
        msg = Message(
            id=1,
            command="create",
            label="Timer",
            type="duration",
            type_duration="timer",
            current_time="02:30:00 PM",
            total_time="00:10:00",
            remaining_time="00:10:00",
            elapsed="00:00:00",
            total_elapsed="00:05:00",
            completed=False,
            paused=True,
            pos=0
        )

        test_task_manager.process_command(msg)

        timer = test_task_manager.durations[0]
        assert timer.total_elapsed == timedelta(minutes=5)


class TestTimerCommands:
    """Test timer command handling."""

    def test_pause_timer(self, test_task_manager):
        """Test pausing a running timer."""
        msg_create = Message(
            id=1,
            command="create",
            label="Timer",
            type="duration",
            type_duration="timer",
            current_time="02:30:00 PM",
            total_time="00:10:00",
            remaining_time="00:10:00",
            elapsed="00:00:00",
            total_elapsed="00:00:00",
            completed=False,
            paused=False,
            pos=0
        )
        test_task_manager.process_command(msg_create)
        assert test_task_manager.durations[0].paused is False

        msg_pause = Message(
            id=1,
            command="pause",
            type="duration",
            elapsed="00:02:00",
            remaining_time="00:08:00"
        )
        test_task_manager.process_command(msg_pause)

        timer = test_task_manager.durations[0]
        assert timer.paused is True
        assert timer.elapsed == timedelta(minutes=2)
        assert timer.remaining_time == timedelta(minutes=8)

    def test_resume_timer(self, test_task_manager):
        """Test resuming a paused timer."""
        msg_create = Message(
            id=1,
            command="create",
            label="Timer",
            type="duration",
            type_duration="timer",
            current_time="02:30:00 PM",
            total_time="00:10:00",
            remaining_time="00:08:00",
            elapsed="00:02:00",
            total_elapsed="00:00:00",
            completed=False,
            paused=True,
            pos=0
        )
        test_task_manager.process_command(msg_create)
        assert test_task_manager.durations[0].paused is True

        msg_resume = Message(
            id=1,
            command="resume",
            type="duration",
            current_time="02:32:00 PM"
        )
        test_task_manager.process_command(msg_resume)

        assert test_task_manager.durations[0].paused is False

    def test_complete_timer(self, test_task_manager):
        """Test completing a timer."""
        msg_create = Message(
            id=1,
            command="create",
            label="Timer",
            type="duration",
            type_duration="timer",
            current_time="02:30:00 PM",
            total_time="00:10:00",
            remaining_time="00:00:00",
            elapsed="00:10:00",
            total_elapsed="00:00:00",
            completed=False,
            paused=True,
            pos=0
        )
        test_task_manager.process_command(msg_create)
        assert test_task_manager.durations[0].completed is False

        msg_complete = Message(
            id=1,
            command="complete",
            type="duration",
            elapsed="00:10:00"
        )
        test_task_manager.process_command(msg_complete)

        timer = test_task_manager.durations[0]
        assert timer.completed is True
        # total_elapsed should accumulate
        assert timer.total_elapsed == timedelta(minutes=10)

    @pytest.mark.xfail(reason="Timer.edit() has typo: self.self.total_elapsed (bug to fix in task 2)")
    def test_edit_timer_label(self, test_task_manager):
        """Test editing a timer label."""
        msg_create = Message(
            id=1,
            command="create",
            label="Original timer",
            type="duration",
            type_duration="timer",
            current_time="02:30:00 PM",
            total_time="00:10:00",
            remaining_time="00:10:00",
            elapsed="00:00:00",
            total_elapsed="00:00:00",
            completed=False,
            paused=True,
            pos=0
        )
        test_task_manager.process_command(msg_create)

        msg_edit = Message(
            id=1,
            command="edit",
            label="Updated timer",
            type="duration",
            current_time="02:30:00 PM",
            total_time="00:15:00"
        )
        test_task_manager.process_command(msg_edit)

        timer = test_task_manager.durations[0]
        assert timer.label == "Updated timer"
        # After edit, total_time should be updated and remaining_time reset
        assert timer.total_time == timedelta(minutes=15)

    @pytest.mark.xfail(reason="Timer.edit() has typo: self.self.total_elapsed (bug to fix in task 2)")
    def test_edit_timer_duration(self, test_task_manager):
        """Test editing a timer's duration."""
        msg_create = Message(
            id=1,
            command="create",
            label="Timer",
            type="duration",
            type_duration="timer",
            current_time="02:30:00 PM",
            total_time="00:10:00",
            remaining_time="00:10:00",
            elapsed="00:00:00",
            total_elapsed="00:00:00",
            completed=False,
            paused=True,
            pos=0
        )
        test_task_manager.process_command(msg_create)

        msg_edit = Message(
            id=1,
            command="edit",
            label="Timer",
            type="duration",
            current_time="02:30:00 PM",
            total_time="00:20:00"
        )
        test_task_manager.process_command(msg_edit)

        timer = test_task_manager.durations[0]
        assert timer.total_time == timedelta(minutes=20)
        assert timer.remaining_time == timedelta(minutes=20)

    def test_delete_timer(self, test_task_manager):
        """Test deleting a timer."""
        msg_create = Message(
            id=1,
            command="create",
            label="Timer to delete",
            type="duration",
            type_duration="timer",
            current_time="02:30:00 PM",
            total_time="00:10:00",
            remaining_time="00:05:00",
            elapsed="00:05:00",
            total_elapsed="00:00:00",
            completed=False,
            paused=True,
            pos=0
        )
        test_task_manager.process_command(msg_create)

        msg_delete = Message(
            id=1,
            command="delete",
            type="duration",
            elapsed="00:05:00"
        )
        test_task_manager.process_command(msg_delete)

        assert len(test_task_manager.durations) == 0

    def test_timer_alerting_state(self, test_task_manager):
        """Test that timer has alerting state."""
        msg = Message(
            id=1,
            command="create",
            label="Alert timer",
            type="duration",
            type_duration="timer",
            current_time="02:30:00 PM",
            total_time="00:10:00",
            remaining_time="00:10:00",
            elapsed="00:00:00",
            total_elapsed="00:00:00",
            completed=False,
            paused=True,
            pos=0
        )
        test_task_manager.process_command(msg)

        timer = test_task_manager.durations[0]
        assert hasattr(timer, 'alerting')
        assert timer.alerting is False


class TestTimerDatabasePersistence:
    """Test that timer changes persist to database."""

    def test_timer_persists_to_db(self, test_task_manager, test_db):
        """Test that created timer is saved to database."""
        msg = Message(
            id=1,
            command="create",
            label="Persist timer",
            type="duration",
            type_duration="timer",
            current_time="02:30:00 PM",
            total_time="00:10:00",
            remaining_time="00:10:00",
            elapsed="00:00:00",
            total_elapsed="00:00:00",
            completed=False,
            paused=True,
            pos=0
        )
        test_task_manager.process_command(msg)

        _, data = test_db.retrieveAll()
        timer_records = [d for d in data if d.get("type_duration") == "timer"]
        assert len(timer_records) == 1
        assert timer_records[0]["label"] == "Persist timer"

    def test_timer_total_time_persists(self, test_task_manager, test_db):
        """Test that timer total_time persists to database."""
        msg = Message(
            id=1,
            command="create",
            label="Timer",
            type="duration",
            type_duration="timer",
            current_time="02:30:00 PM",
            total_time="00:15:00",
            remaining_time="00:15:00",
            elapsed="00:00:00",
            total_elapsed="00:00:00",
            completed=False,
            paused=True,
            pos=0
        )
        test_task_manager.process_command(msg)

        _, data = test_db.retrieveAll()
        timer_records = [d for d in data if d.get("type_duration") == "timer"]
        assert timer_records[0]["total_time"] == "00:15:00"

    def test_timer_remaining_time_persists(self, test_task_manager, test_db):
        """Test that timer remaining_time persists to database."""
        msg_create = Message(
            id=1,
            command="create",
            label="Timer",
            type="duration",
            type_duration="timer",
            current_time="02:30:00 PM",
            total_time="00:10:00",
            remaining_time="00:10:00",
            elapsed="00:00:00",
            total_elapsed="00:00:00",
            completed=False,
            paused=False,
            pos=0
        )
        test_task_manager.process_command(msg_create)

        msg_pause = Message(
            id=1,
            command="pause",
            type="duration",
            elapsed="00:03:00",
            remaining_time="00:07:00"
        )
        test_task_manager.process_command(msg_pause)

        _, data = test_db.retrieveAll()
        timer_records = [d for d in data if d.get("type_duration") == "timer"]
        assert timer_records[0]["remaining_time"] == "00:07:00"

    def test_timer_total_elapsed_persists(self, test_task_manager, test_db):
        """Test that timer total_elapsed persists to database."""
        msg = Message(
            id=1,
            command="create",
            label="Timer",
            type="duration",
            type_duration="timer",
            current_time="02:30:00 PM",
            total_time="00:10:00",
            remaining_time="00:10:00",
            elapsed="00:00:00",
            total_elapsed="00:08:00",
            completed=False,
            paused=True,
            pos=0
        )
        test_task_manager.process_command(msg)

        _, data = test_db.retrieveAll()
        timer_records = [d for d in data if d.get("type_duration") == "timer"]
        assert timer_records[0]["total_elapsed"] == "00:08:00"

    @pytest.mark.xfail(reason="Timer.edit() has typo: self.self.total_elapsed (bug to fix in task 2)")
    def test_edited_timer_persists(self, test_task_manager, test_db):
        """Test that timer edits persist to database."""
        msg_create = Message(
            id=1,
            command="create",
            label="Original timer",
            type="duration",
            type_duration="timer",
            current_time="02:30:00 PM",
            total_time="00:10:00",
            remaining_time="00:10:00",
            elapsed="00:00:00",
            total_elapsed="00:00:00",
            completed=False,
            paused=True,
            pos=0
        )
        test_task_manager.process_command(msg_create)

        msg_edit = Message(
            id=1,
            command="edit",
            label="Modified timer",
            type="duration",
            current_time="02:30:00 PM",
            total_time="00:20:00"
        )
        test_task_manager.process_command(msg_edit)

        _, data = test_db.retrieveAll()
        timer_records = [d for d in data if d.get("type_duration") == "timer"]
        assert timer_records[0]["label"] == "Modified timer"
        assert timer_records[0]["total_time"] == "00:20:00"
