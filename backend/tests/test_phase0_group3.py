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

    def test_ring_timer_does_not_resume_as_running_after_reload(self, test_task_manager, test_db):
        """Regression: a rung timer must not appear "running" again after reload.

        Bug: Timer.ring() set alerting=True but never set paused=True. Since
        get_ApiDuration()'s started_at is computed as `None if paused else
        current_time`, a rung-but-not-paused timer reloads with started_at
        != None — the frontend treats it as actively running with elapsed
        already past total_time, and instantly re-fires ring() again.
        """
        msg_create = Message(
            id=1,
            command="create",
            label="Test timer",
            type="duration",
            type_duration="timer",
            current_time="02:30:00 PM",
            total_time="00:00:02",
            remaining_time="00:00:00",
            elapsed="00:00:02",
            total_elapsed="00:00:00",
            completed=False,
            paused=False,  # was actively running right up to the moment it rang
            pos=0
        )
        test_task_manager.process_command(msg_create)
        timer = test_task_manager.durations[0]
        assert timer.paused is False

        msg_ring = Message(id=1, command="ring", type="duration", elapsed="00:00:02")
        test_task_manager.process_command(msg_ring)

        # ring() must freeze the running state
        assert timer.paused is True
        assert timer.get_ApiDuration()["started_at"] is None

        # Verify persisted to DB
        _, data = test_db.retrieveAll()
        record = next(d for d in data if d.get("type_duration") == "timer")
        assert record["paused"] == 1

        # Simulate a fresh TaskManager loading from DB (page refresh / restart)
        from classes import TaskManager
        reloaded_tm = TaskManager.__new__(TaskManager)
        reloaded_tm.tasks = []
        reloaded_tm.events = []
        reloaded_tm.durations = []
        reloaded_tm.db = test_db
        reloaded_tm.retrieve_data()

        reloaded_timer = reloaded_tm.durations[0]
        assert reloaded_timer.paused is True
        assert reloaded_timer.get_ApiDuration()["started_at"] is None


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

    def test_dismissed_event_stays_dismissed_after_reload(self, test_task_manager, test_db):
        """Regression: dismissing a ringing event must survive a page refresh.

        Root cause: the `events` table had no `completed` column, so nothing
        durably recorded that a ringing event had been dismissed. Since the
        event's ring_time stays in the past forever, `alerting=False` alone
        is not enough — on reload the frontend's countdown-check effect sees
        msUntil(ring_time) <= 0 and immediately re-fires ring(). Dismissing
        must also persist completed=True (mirroring what the frontend already
        does in memory via dismissEvent), and get_ApiEvent() must expose it.
        """
        msg_create = Message(
            id=2,
            command="create",
            label="Test event",
            type="event",
            ring_time="2026-07-25T15:30:00Z",  # in the past relative to "today" in these tests
            completed=False,
            pos=0
        )
        test_task_manager.process_command(msg_create)

        msg_ring = Message(id=2, command="ring", type="event", label="Test event")
        test_task_manager.process_command(msg_ring)

        api_event = test_task_manager.events[0].get_ApiEvent()
        assert api_event["alerting"] is True
        assert api_event["completed"] is False

        msg_stop_ring = Message(id=2, command="stop_ring", type="event", label="Test event")
        test_task_manager.process_command(msg_stop_ring)

        api_event = test_task_manager.events[0].get_ApiEvent()
        assert api_event["alerting"] is False
        assert api_event["completed"] is True

        # Verify persistence to DB directly
        _, data = test_db.retrieveAll()
        event_record = next(d for d in data if d.get("type") == "event")
        assert event_record["alerting"] == 0
        assert event_record["completed"] == 1

        # Simulate a fresh TaskManager loading from DB (page refresh / restart)
        from classes import TaskManager
        reloaded_tm = TaskManager.__new__(TaskManager)
        reloaded_tm.tasks = []
        reloaded_tm.events = []
        reloaded_tm.durations = []
        reloaded_tm.db = test_db
        reloaded_tm.retrieve_data()

        reloaded_event = reloaded_tm.events[0]
        assert reloaded_event.alerting is False
        assert reloaded_event.completed is True
        reloaded_api_event = reloaded_event.get_ApiEvent()
        assert reloaded_api_event["alerting"] is False
        assert reloaded_api_event["completed"] is True

    def test_editing_event_clears_stale_alerting_and_completed(self, test_task_manager, test_db):
        """Editing a ringing/dismissed event's ring_time should silence it going forward."""
        msg_create = Message(
            id=3,
            command="create",
            label="Test event",
            type="event",
            ring_time="2026-07-25T15:30:00Z",
            completed=False,
            pos=0
        )
        test_task_manager.process_command(msg_create)

        test_task_manager.process_command(Message(id=3, command="ring", type="event", label="Test event"))
        test_task_manager.process_command(Message(id=3, command="stop_ring", type="event", label="Test event"))

        event = test_task_manager.events[0]
        assert event.alerting is False
        assert event.completed is True

        # Edit pushes the ring time into the future — should reset alerting/completed
        msg_edit = Message(
            id=3,
            command="edit",
            type="event",
            label="Test event",
            ring_time="2026-07-26T09:00:00Z",
        )
        test_task_manager.process_command(msg_edit)

        assert event.alerting is False
        assert event.completed is False

        _, data = test_db.retrieveAll()
        event_record = next(d for d in data if d.get("type") == "event")
        assert event_record["alerting"] == 0
        assert event_record["completed"] == 0


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
