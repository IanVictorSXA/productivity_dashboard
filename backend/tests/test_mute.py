"""Phase 5 Group 6 tests: the `mute` command on timers and events.

Covers: mute is a set (not a toggle), it is saved and restored by a fresh
`TaskManager`, a ringing card restored after a restart is still muted and still
alerting, muting never changes `alerting`, edits keep the mute flag, stopwatches
and tasks cannot be muted, and a stale id is ignored. Temp-DB fixtures only.
"""

import pytest

from classes import TaskManager, Message
from database import Database


@pytest.fixture
def tm(temp_db_env):
    """A real TaskManager (restores from the temp DB) with the sheet sync stubbed out."""
    return fresh_manager()


def fresh_manager():
    """A brand-new TaskManager reading the temp DB file — also how a backend restart is simulated."""
    manager = TaskManager.__new__(TaskManager)
    manager.tasks, manager.events, manager.durations = [], [], []
    manager.sheet_sync = None
    manager.db = Database()
    manager.retrieve_data()
    return manager


def add_timer(tm, id=1):
    tm.process_command(Message(id=id, command="create", type="duration", type_duration="timer",
                               label="t", current_time="09:00:00 AM", total_time="00:10:00",
                               remaining_time="00:10:00", elapsed="00:00:00", total_elapsed="00:00:00"))


def add_stopwatch(tm, id=2):
    tm.process_command(Message(id=id, command="create", type="duration", type_duration="stopwatch",
                               label="s", current_time="09:00:00 AM", elapsed="00:00:00"))


def add_event(tm, id=3):
    tm.process_command(Message(id=id, command="create", type="event", label="e",
                               ring_time="2030-01-01T10:00:00Z"))


def mute(tm, type, id, muted):
    tm.process_command(Message(command="mute", type=type, id=id, muted=muted))


def api(tm, key, id):
    return next(card for card in tm.get_ApiState()[key] if card["id"] == id)


class TestMuteCommand:
    def test_new_cards_start_unmuted(self, tm):
        add_timer(tm)
        add_event(tm)
        assert api(tm, "durations", 1)["muted"] is False
        assert api(tm, "events", 3)["muted"] is False

    def test_mute_timer_and_event(self, tm):
        add_timer(tm)
        add_event(tm)
        mute(tm, "duration", 1, True)
        mute(tm, "event", 3, True)
        assert api(tm, "durations", 1)["muted"] is True
        assert api(tm, "events", 3)["muted"] is True

    def test_mute_is_a_set_not_a_toggle(self, tm):
        # A retried request must not flip the state back.
        add_timer(tm)
        mute(tm, "duration", 1, True)
        mute(tm, "duration", 1, True)
        assert api(tm, "durations", 1)["muted"] is True
        mute(tm, "duration", 1, False)
        mute(tm, "duration", 1, False)
        assert api(tm, "durations", 1)["muted"] is False

    def test_mute_only_touches_the_named_card(self, tm):
        add_timer(tm, 1)
        add_timer(tm, 4)
        mute(tm, "duration", 1, True)
        assert api(tm, "durations", 4)["muted"] is False


class TestPersistence:
    def test_mute_survives_restart(self, tm):
        add_timer(tm)
        add_event(tm)
        mute(tm, "duration", 1, True)
        mute(tm, "event", 3, True)
        fresh = fresh_manager()
        assert api(fresh, "durations", 1)["muted"] is True
        assert api(fresh, "events", 3)["muted"] is True

    def test_unmute_survives_restart(self, tm):
        add_timer(tm)
        mute(tm, "duration", 1, True)
        mute(tm, "duration", 1, False)
        assert api(fresh_manager(), "durations", 1)["muted"] is False

    def test_ringing_muted_card_restores_muted_and_alerting(self, tm):
        add_timer(tm)
        add_event(tm)
        mute(tm, "duration", 1, True)
        mute(tm, "event", 3, True)
        tm.process_command(Message(command="ring", type="duration", id=1, elapsed="00:10:00"))
        tm.process_command(Message(command="ring", type="event", id=3))
        fresh = fresh_manager()
        for key, id in (("durations", 1), ("events", 3)):
            card = api(fresh, key, id)
            assert card["alerting"] is True
            assert card["muted"] is True


class TestMuteDoesNotChangeOtherState:
    def test_muting_does_not_change_alerting(self, tm):
        add_timer(tm)
        add_event(tm)
        tm.process_command(Message(command="ring", type="duration", id=1, elapsed="00:10:00"))
        tm.process_command(Message(command="ring", type="event", id=3))
        mute(tm, "duration", 1, True)
        mute(tm, "event", 3, True)
        assert api(tm, "durations", 1)["alerting"] is True
        assert api(tm, "events", 3)["alerting"] is True
        mute(tm, "duration", 1, False)
        mute(tm, "event", 3, False)
        assert api(tm, "durations", 1)["alerting"] is True
        assert api(tm, "events", 3)["alerting"] is True

    def test_muting_an_event_does_not_complete_it(self, tm):
        add_event(tm)
        mute(tm, "event", 3, True)
        assert tm.events[0].completed is False

    def test_dismissing_keeps_mute(self, tm):
        add_event(tm)
        mute(tm, "event", 3, True)
        tm.process_command(Message(command="ring", type="event", id=3))
        tm.process_command(Message(command="stop_ring", type="event", id=3))
        assert api(fresh_manager(), "events", 3)["muted"] is True

    def test_editing_keeps_mute(self, tm):
        add_event(tm)
        mute(tm, "event", 3, True)
        tm.process_command(Message(command="edit", type="event", id=3, label="new",
                                   ring_time="2030-01-02T10:00:00Z"))
        assert api(tm, "events", 3)["muted"] is True

        add_timer(tm)
        mute(tm, "duration", 1, True)
        tm.process_command(Message(command="edit", type="duration", id=1, label="new",
                                   current_time="09:05:00 AM", total_time="00:20:00"))
        assert api(tm, "durations", 1)["muted"] is True


class TestRejected:
    def test_stopwatch_cannot_be_muted(self, tm):
        add_stopwatch(tm)
        with pytest.raises(ValueError):
            mute(tm, "duration", 2, True)
        assert "muted" not in api(tm, "durations", 2)

    def test_task_cannot_be_muted(self, tm):
        tm.process_command(Message(id=5, command="create", type="task", label="x"))
        with pytest.raises(ValueError):
            mute(tm, "task", 5, True)

    def test_stale_id_is_ignored(self, tm):
        add_timer(tm)
        tm.process_command(Message(command="delete", type="duration", id=1, elapsed="00:00:00"))
        mute(tm, "duration", 1, True)  # must not raise
        mute(tm, "event", 99, True)
