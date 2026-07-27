"""Tests for Event class and event-related commands."""

import pytest
from datetime import datetime
from classes import Event, Message


class TestEventCreation:
    """Test event creation."""

    def test_create_event(self, test_task_manager):
        """Test creating an event via process_command."""
        ring_time = "2026-07-25T14:30:00Z"
        msg = Message(
            id=1,
            command="create",
            label="Meeting reminder",
            type="event",
            ring_time=ring_time,
            pos=0
        )

        test_task_manager.process_command(msg)

        assert len(test_task_manager.events) == 1
        event = test_task_manager.events[0]
        assert event.id == 1
        assert event.label == "Meeting reminder"
        assert event.deleted is False
        # Verify ring_time was parsed
        assert event.ring_time is not None

    def test_create_multiple_events(self, test_task_manager):
        """Test creating multiple events."""
        for i in range(3):
            msg = Message(
                id=i,
                command="create",
                label=f"Event {i}",
                type="event",
                ring_time=f"2026-07-25T{14+i}:00:00Z",
                pos=i
            )
            test_task_manager.process_command(msg)

        assert len(test_task_manager.events) == 3
        assert test_task_manager.events[0].label == "Event 0"
        assert test_task_manager.events[1].label == "Event 1"
        assert test_task_manager.events[2].label == "Event 2"

    def test_event_ring_time_parsing(self, test_task_manager):
        """Test that ring_time is properly parsed to datetime."""
        ring_time = "2026-07-25T14:30:00Z"
        msg = Message(
            id=1,
            command="create",
            label="Event with time",
            type="event",
            ring_time=ring_time,
            pos=0
        )

        test_task_manager.process_command(msg)

        event = test_task_manager.events[0]
        assert isinstance(event.ring_time, datetime)
        assert event.ring_time.year == 2026
        assert event.ring_time.month == 7
        assert event.ring_time.day == 25


class TestEventCommands:
    """Test event command handling."""

    def test_complete_event(self, test_task_manager):
        """Test completing an event."""
        msg_create = Message(
            id=1,
            command="create",
            label="Event to complete",
            type="event",
            ring_time="2026-07-25T14:30:00Z",
            pos=0,
            completed=False
        )
        test_task_manager.process_command(msg_create)

        # Events inherit from Task and should have completed attribute
        event = test_task_manager.events[0]
        initial_completed = event.completed

        msg_complete = Message(
            id=1,
            command="complete",
            type="event"
        )
        test_task_manager.process_command(msg_complete)

        # Complete should toggle the completed state
        assert event.completed != initial_completed

    def test_edit_event_label(self, test_task_manager):
        """Test editing an event label."""
        msg_create = Message(
            id=1,
            command="create",
            label="Original event",
            type="event",
            ring_time="2026-07-25T14:30:00Z",
            pos=0
        )
        test_task_manager.process_command(msg_create)

        msg_edit = Message(
            id=1,
            command="edit",
            label="Updated event",
            type="event",
            ring_time="2026-07-25T15:00:00Z"
        )
        test_task_manager.process_command(msg_edit)

        assert test_task_manager.events[0].label == "Updated event"

    def test_edit_event_ring_time(self, test_task_manager):
        """Test editing an event's ring_time."""
        old_ring_time = "2026-07-25T14:30:00Z"
        new_ring_time = "2026-07-25T16:45:00Z"

        msg_create = Message(
            id=1,
            command="create",
            label="Event",
            type="event",
            ring_time=old_ring_time,
            pos=0
        )
        test_task_manager.process_command(msg_create)

        old_time = test_task_manager.events[0].ring_time

        msg_edit = Message(
            id=1,
            command="edit",
            label="Event",
            type="event",
            ring_time=new_ring_time
        )
        test_task_manager.process_command(msg_edit)

        new_time = test_task_manager.events[0].ring_time
        assert old_time != new_time
        assert new_time.hour == 16
        assert new_time.minute == 45

    def test_delete_event(self, test_task_manager):
        """Test deleting an event."""
        msg_create = Message(
            id=1,
            command="create",
            label="Event to delete",
            type="event",
            ring_time="2026-07-25T14:30:00Z",
            pos=0
        )
        test_task_manager.process_command(msg_create)

        msg_delete = Message(
            id=1,
            command="delete",
            type="event"
        )
        test_task_manager.process_command(msg_delete)

        assert len(test_task_manager.events) == 0

    def test_event_alerting_state(self, test_task_manager):
        """Test that event has alerting state."""
        msg = Message(
            id=1,
            command="create",
            label="Alert event",
            type="event",
            ring_time="2026-07-25T14:30:00Z",
            pos=0
        )
        test_task_manager.process_command(msg)

        event = test_task_manager.events[0]
        assert hasattr(event, 'alerting')
        assert event.alerting is False


class TestEventDatabasePersistence:
    """Test that event changes persist to database."""

    def test_event_persists_to_db(self, test_task_manager, test_db):
        """Test that created event is saved to database."""
        msg = Message(
            id=1,
            command="create",
            label="Persist event",
            type="event",
            ring_time="2026-07-25T14:30:00Z",
            pos=0
        )
        test_task_manager.process_command(msg)

        _, data = test_db.retrieveAll()
        event_records = [d for d in data if d.get("type") == "event"]
        assert len(event_records) == 1
        assert event_records[0]["label"] == "Persist event"

    def test_event_ring_time_persists(self, test_task_manager, test_db):
        """Test that event ring_time persists to database."""
        ring_time = "2026-07-25T14:30:00Z"
        msg = Message(
            id=1,
            command="create",
            label="Event with ring",
            type="event",
            ring_time=ring_time,
            pos=0
        )
        test_task_manager.process_command(msg)

        _, data = test_db.retrieveAll()
        event_records = [d for d in data if d.get("type") == "event"]
        assert event_records[0]["ring_time"] is not None

    def test_edited_event_persists(self, test_task_manager, test_db):
        """Test that event edits persist to database."""
        msg_create = Message(
            id=1,
            command="create",
            label="Original event",
            type="event",
            ring_time="2026-07-25T14:30:00Z",
            pos=0
        )
        test_task_manager.process_command(msg_create)

        msg_edit = Message(
            id=1,
            command="edit",
            label="Modified event",
            type="event",
            ring_time="2026-07-25T15:00:00Z"
        )
        test_task_manager.process_command(msg_edit)

        _, data = test_db.retrieveAll()
        event_records = [d for d in data if d.get("type") == "event"]
        assert event_records[0]["label"] == "Modified event"
