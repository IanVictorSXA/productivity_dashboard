"""Regression tests for Group 2: Fix confirmed crash bugs (0e).

This module tests:
1. close command does not raise
2. Timer.edit() (paused and while running) does not raise and persists correct values
"""

import pytest
from datetime import timedelta
from classes import Timer, Message


class TestCloseCommand:
    """Test close command handling."""

    def test_close_command_does_not_raise(self, test_task_manager):
        """Test that close command executes without raising."""
        msg = Message(
            command="close",
            current_time="02:30:00 PM"
        )
        # Should not raise NotImplementedError
        test_task_manager.process_command(msg)

    def test_close_command_with_other_fields(self, test_task_manager):
        """Test close command is handled regardless of other message fields."""
        msg = Message(
            command="close",
            id=1,
            label="ignored",
            type="task",
            current_time="02:30:00 PM"
        )
        # Should not raise NotImplementedError
        test_task_manager.process_command(msg)


class TestTimerEditRegressions:
    """Test Timer.edit() fix (self.self.total_elapsed typo removed)."""

    def test_edit_timer_label_paused(self, test_task_manager):
        """Test editing a paused timer label."""
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
        # Should not raise AttributeError: 'Timer' object has no attribute 'self'
        test_task_manager.process_command(msg_edit)

        timer = test_task_manager.durations[0]
        assert timer.label == "Updated timer"
        assert timer.total_time == timedelta(minutes=15)
        assert timer.remaining_time == timedelta(minutes=15)

    def test_edit_timer_duration_while_running(self, test_task_manager):
        """Test editing a running timer's duration."""
        msg_create = Message(
            id=1,
            command="create",
            label="Running timer",
            type="duration",
            type_duration="timer",
            current_time="02:30:00 PM",
            total_time="00:05:00",
            remaining_time="00:05:00",
            elapsed="00:01:00",
            total_elapsed="00:00:00",
            completed=False,
            paused=False,
            pos=0
        )
        test_task_manager.process_command(msg_create)

        msg_edit = Message(
            id=1,
            command="edit",
            label="Extended timer",
            type="duration",
            current_time="02:31:00 PM",
            total_time="00:10:00"
        )
        # Should not raise AttributeError
        test_task_manager.process_command(msg_edit)

        timer = test_task_manager.durations[0]
        assert timer.label == "Extended timer"
        assert timer.total_time == timedelta(minutes=10)
        assert timer.remaining_time == timedelta(minutes=10)
        # elapsed should be reset to 0 after edit
        assert timer.elapsed == timedelta(0)

    def test_edit_timer_persists_total_elapsed(self, test_task_manager, test_db):
        """Test that timer edits persist total_elapsed correctly to database."""
        msg_create = Message(
            id=1,
            command="create",
            label="Original timer",
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

        msg_edit = Message(
            id=1,
            command="edit",
            label="Modified timer",
            type="duration",
            current_time="02:30:00 PM",
            total_time="00:20:00"
        )
        # Should not raise AttributeError
        test_task_manager.process_command(msg_edit)

        _, data = test_db.retrieveAll()
        timer_records = [d for d in data if d.get("type_duration") == "timer"]
        assert len(timer_records) == 1
        record = timer_records[0]

        assert record["label"] == "Modified timer"
        assert record["total_time"] == "00:20:00"
        # total_elapsed should accumulate: previous 0 + elapsed 5 min = 5 min
        assert record["total_elapsed"] == "00:05:00"
        # elapsed should be reset to 0 after edit
        assert record["elapsed"] == "00:00:00"
