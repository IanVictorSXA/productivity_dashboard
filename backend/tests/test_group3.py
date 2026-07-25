"""Regression tests for Group 3: Make ring/stop_ring persist real state (0b, 0c).

This module tests:
1. ring persists frozen elapsed time + alerting=True to DB for timers and events
2. stop_ring clears alerting in both memory and DB
3. Sending ring twice for same card does not double-process or corrupt state
"""

import pytest
from datetime import datetime, timedelta
from classes import Timer, Event, Duration, Message


class TestTimerRing:
    """Test timer ring handling."""

    def test_ring_timer_sets_alerting_and_persists_elapsed(self, test_task_manager, test_db):
        """Test that ringing a timer sets alerting and persists elapsed time to DB."""
        msg_create = Message(
            id=1,
            command="create",
            label="Test timer",
            type="duration",
            type_duration="timer",
            current_time="02:30:00 PM",
            total_time="00:05:00",
            remaining_time="00:02:00",
            elapsed="00:03:00",
            total_elapsed="00:00:00",
            completed=False,
            paused=False,
            pos=0
        )
        test_task_manager.process_command(msg_create)
        timer = test_task_manager.durations[0]

        # Verify alerting is initially False
        assert timer.alerting is False

        # Ring the timer with elapsed time from the moment of ringing
        msg_ring = Message(
            id=1,
            command="ring",
            type="duration",
            elapsed="00:05:00"
        )
        test_task_manager.process_command(msg_ring)

        # Verify in-memory state
        assert timer.alerting is True
        assert timer.elapsed == timedelta(seconds=300)  # 5 minutes = 300 seconds

        # Verify database persistence
        _, data = test_db.retrieveAll()
        timer_records = [d for d in data if d.get("type_duration") == "timer"]
        assert len(timer_records) == 1
        record = timer_records[0]

        assert record["alerting"] == 1
        assert record["elapsed"] == "00:05:00"

    def test_stop_ring_timer_clears_alerting(self, test_task_manager, test_db):
        """Test that stop_ring clears alerting in both memory and DB."""
        msg_create = Message(
            id=1,
            command="create",
            label="Test timer",
            type="duration",
            type_duration="timer",
            current_time="02:30:00 PM",
            total_time="00:05:00",
            remaining_time="00:00:00",
            elapsed="00:05:00",
            total_elapsed="00:00:00",
            completed=False,
            paused=True,
            pos=0
        )
        test_task_manager.process_command(msg_create)

        # Ring the timer
        msg_ring = Message(
            id=1,
            command="ring",
            type="duration",
            elapsed="00:05:00"
        )
        test_task_manager.process_command(msg_ring)
        timer = test_task_manager.durations[0]
        assert timer.alerting is True

        # Stop the ring
        msg_stop_ring = Message(
            id=1,
            command="stop_ring",
            type="duration"
        )
        test_task_manager.process_command(msg_stop_ring)

        # Verify in-memory state
        assert timer.alerting is False

        # Verify database persistence
        _, data = test_db.retrieveAll()
        timer_records = [d for d in data if d.get("type_duration") == "timer"]
        assert len(timer_records) == 1
        record = timer_records[0]

        assert record["alerting"] == 0

    def test_ring_timer_twice_no_double_processing(self, test_task_manager, test_db):
        """Test that ringing twice for same timer doesn't corrupt state."""
        msg_create = Message(
            id=1,
            command="create",
            label="Test timer",
            type="duration",
            type_duration="timer",
            current_time="02:30:00 PM",
            total_time="00:05:00",
            remaining_time="00:02:00",
            elapsed="00:03:00",
            total_elapsed="00:00:00",
            completed=False,
            paused=False,
            pos=0
        )
        test_task_manager.process_command(msg_create)
        timer = test_task_manager.durations[0]

        # Ring the timer first time
        msg_ring1 = Message(
            id=1,
            command="ring",
            type="duration",
            elapsed="00:05:00"
        )
        test_task_manager.process_command(msg_ring1)

        # Ring the timer again with different elapsed time
        msg_ring2 = Message(
            id=1,
            command="ring",
            type="duration",
            elapsed="00:05:01"
        )
        test_task_manager.process_command(msg_ring2)

        # Verify state is consistent and updated with latest ring
        assert timer.alerting is True
        assert timer.elapsed == timedelta(seconds=301)  # 5 minutes 1 second = 301 seconds

        # Verify database reflects latest ring
        _, data = test_db.retrieveAll()
        timer_records = [d for d in data if d.get("type_duration") == "timer"]
        assert len(timer_records) == 1
        record = timer_records[0]

        assert record["alerting"] == 1
        assert record["elapsed"] == "00:05:01"


class TestEventRing:
    """Test event ring handling."""

    def test_ring_event_sets_alerting(self, test_task_manager, test_db):
        """Test that ringing an event sets alerting and persists to DB."""
        from classes import parse_iso_datetime

        msg_create = Message(
            id=2,
            command="create",
            label="Test event",
            type="event",
            ring_time="2026-07-25T15:30:00Z",
            completed=False,
            pos=0
        )
        test_task_manager.process_command(msg_create)
        event = test_task_manager.events[0]

        # Verify alerting is initially False
        assert event.alerting is False

        # Ring the event
        msg_ring = Message(
            id=2,
            command="ring",
            type="event",
            label="Test event"
        )
        test_task_manager.process_command(msg_ring)

        # Verify in-memory state
        assert event.alerting is True

        # Verify database persistence
        _, data = test_db.retrieveAll()
        event_records = [d for d in data if d.get("type") == "event"]
        assert len(event_records) == 1
        record = event_records[0]

        assert record["alerting"] == 1

    def test_stop_ring_event_clears_alerting(self, test_task_manager, test_db):
        """Test that stop_ring clears alerting for event."""
        msg_create = Message(
            id=2,
            command="create",
            label="Test event",
            type="event",
            ring_time="2026-07-25T15:30:00Z",
            completed=False,
            pos=0
        )
        test_task_manager.process_command(msg_create)

        # Ring the event
        msg_ring = Message(
            id=2,
            command="ring",
            type="event",
            label="Test event"
        )
        test_task_manager.process_command(msg_ring)
        event = test_task_manager.events[0]
        assert event.alerting is True

        # Stop the ring
        msg_stop_ring = Message(
            id=2,
            command="stop_ring",
            type="event",
            label="Test event"
        )
        test_task_manager.process_command(msg_stop_ring)

        # Verify in-memory state
        assert event.alerting is False

        # Verify database persistence
        _, data = test_db.retrieveAll()
        event_records = [d for d in data if d.get("type") == "event"]
        assert len(event_records) == 1
        record = event_records[0]

        assert record["alerting"] == 0


class TestStopwatchRing:
    """Test stopwatch ring handling."""

    def test_ring_stopwatch_sets_alerting_and_persists_elapsed(self, test_task_manager, test_db):
        """Test that ringing a stopwatch sets alerting and persists elapsed time."""
        msg_create = Message(
            id=3,
            command="create",
            label="Work",
            type="duration",
            type_duration="stopwatch",
            current_time="02:30:00 PM",
            elapsed="00:10:30",
            paused=False,
            pos=0
        )
        test_task_manager.process_command(msg_create)
        stopwatch = test_task_manager.durations[0]

        assert stopwatch.alerting is False

        # Ring the stopwatch with elapsed time
        msg_ring = Message(
            id=3,
            command="ring",
            type="duration",
            elapsed="00:10:30"
        )
        test_task_manager.process_command(msg_ring)

        # Verify in-memory state
        assert stopwatch.alerting is True
        assert stopwatch.elapsed == timedelta(minutes=10, seconds=30)

        # Verify database persistence
        _, data = test_db.retrieveAll()
        stopwatch_records = [d for d in data if d.get("type_duration") == "stopwatch"]
        assert len(stopwatch_records) == 1
        record = stopwatch_records[0]

        assert record["alerting"] == 1
        assert record["elapsed"] == "00:10:30"

    def test_stop_ring_stopwatch_clears_alerting(self, test_task_manager, test_db):
        """Test that stop_ring clears alerting for stopwatch."""
        msg_create = Message(
            id=3,
            command="create",
            label="Work",
            type="duration",
            type_duration="stopwatch",
            current_time="02:30:00 PM",
            elapsed="00:10:30",
            paused=True,
            pos=0
        )
        test_task_manager.process_command(msg_create)

        # Ring the stopwatch
        msg_ring = Message(
            id=3,
            command="ring",
            type="duration",
            elapsed="00:10:30"
        )
        test_task_manager.process_command(msg_ring)
        stopwatch = test_task_manager.durations[0]
        assert stopwatch.alerting is True

        # Stop the ring
        msg_stop_ring = Message(
            id=3,
            command="stop_ring",
            type="duration"
        )
        test_task_manager.process_command(msg_stop_ring)

        # Verify in-memory state
        assert stopwatch.alerting is False

        # Verify database persistence
        _, data = test_db.retrieveAll()
        stopwatch_records = [d for d in data if d.get("type_duration") == "stopwatch"]
        assert len(stopwatch_records) == 1
        record = stopwatch_records[0]

        assert record["alerting"] == 0


class TestRingAlertingGuard:
    """Test frontend's alerting guard to prevent double-fire."""

    def test_multiple_durations_ring_independently(self, test_task_manager, test_db):
        """Test that ringing multiple durations doesn't affect others."""
        msg_create1 = Message(
            id=1,
            command="create",
            label="Timer 1",
            type="duration",
            type_duration="timer",
            current_time="02:30:00 PM",
            total_time="00:05:00",
            remaining_time="00:00:00",
            elapsed="00:05:00",
            total_elapsed="00:00:00",
            completed=False,
            paused=True,
            pos=0
        )
        msg_create2 = Message(
            id=2,
            command="create",
            label="Timer 2",
            type="duration",
            type_duration="timer",
            current_time="02:30:00 PM",
            total_time="00:10:00",
            remaining_time="00:00:00",
            elapsed="00:10:00",
            total_elapsed="00:00:00",
            completed=False,
            paused=True,
            pos=1
        )
        test_task_manager.process_command(msg_create1)
        test_task_manager.process_command(msg_create2)

        # Ring timer 1
        msg_ring1 = Message(
            id=1,
            command="ring",
            type="duration",
            elapsed="00:05:00"
        )
        test_task_manager.process_command(msg_ring1)

        # Timer 1 should be alerting, timer 2 should not
        assert test_task_manager.durations[0].alerting is True
        assert test_task_manager.durations[1].alerting is False

        # Ring timer 2
        msg_ring2 = Message(
            id=2,
            command="ring",
            type="duration",
            elapsed="00:10:00"
        )
        test_task_manager.process_command(msg_ring2)

        # Both should now be alerting
        assert test_task_manager.durations[0].alerting is True
        assert test_task_manager.durations[1].alerting is True

        # Verify database
        _, data = test_db.retrieveAll()
        timer_records = [d for d in data if d.get("type_duration") == "timer"]
        assert len(timer_records) == 2

        for record in timer_records:
            assert record["alerting"] == 1
