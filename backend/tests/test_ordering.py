"""Phase 5 Group 2 tests: backend-owned card order (`pos`), the `reorder` command, persistence.

Covers: new cards append last, `reorder` for tasks and for mixed stopwatch+timer
lists, order surviving a fresh `TaskManager` on the same DB, the races `reorder`
tolerates (deleted / newly created cards), malformed requests changing nothing,
and the old `NotImplementedError` regression. Uses the temp-DB fixtures only.
"""

import pytest

from classes import TaskManager, Message
from database import Database


@pytest.fixture
def tm(temp_db_env):
    """A real TaskManager (restores from the temp DB) with the sheet sync stubbed out."""
    manager = TaskManager.__new__(TaskManager)
    manager.tasks, manager.events, manager.durations = [], [], []
    manager.sheet_sync = None
    manager.db = Database()
    manager.retrieve_data()
    return manager


def restart(old):
    """Simulate a backend restart: a brand-new TaskManager reading the same DB file."""
    fresh = TaskManager.__new__(TaskManager)
    fresh.tasks, fresh.events, fresh.durations = [], [], []
    fresh.sheet_sync = None
    fresh.db = Database()
    fresh.retrieve_data()
    return fresh


def add_task(tm, id, label=None, pos=0):
    tm.process_command(Message(id=id, command="create", type="task", label=label or f"t{id}", pos=pos))


def add_stopwatch(tm, id, pos=0):
    tm.process_command(Message(id=id, command="create", type="duration", type_duration="stopwatch",
                               label=f"s{id}", current_time="09:00:00 AM", elapsed="00:00:00", pos=pos))


def add_timer(tm, id, pos=0):
    tm.process_command(Message(id=id, command="create", type="duration", type_duration="timer",
                               label=f"m{id}", current_time="09:00:00 AM", total_time="00:10:00",
                               remaining_time="00:10:00", elapsed="00:00:00", total_elapsed="00:00:00", pos=pos))


def add_event(tm, id, pos=0):
    tm.process_command(Message(id=id, command="create", type="event", label=f"e{id}",
                               ring_time="2030-01-01T10:00:00Z", pos=pos))


def ids(state, key):
    return [card["id"] for card in state[key]]


def reorder(tm, type, order):
    tm.process_command(Message(command="reorder", type=type, order=order))


class TestCreateOrder:
    def test_new_cards_append_in_creation_order(self, tm):
        for i in (1, 2, 3):
            add_task(tm, i)
        assert ids(tm.get_ApiState(), "tasks") == [1, 2, 3]
        assert [t.pos for t in tm.tasks] == [0, 1, 2]

    def test_client_pos_is_ignored(self, tm):
        # A client claiming pos=99 / pos=0 cannot jump the queue.
        add_task(tm, 1, pos=99)
        add_task(tm, 2, pos=0)
        assert [t.pos for t in tm.tasks] == [0, 1]

    def test_stopwatches_and_timers_share_one_counter(self, tm):
        add_stopwatch(tm, 1)
        add_timer(tm, 2)
        add_stopwatch(tm, 3)
        assert [d.pos for d in tm.durations] == [0, 1, 2]

    def test_lists_count_independently(self, tm):
        add_task(tm, 1)
        add_event(tm, 2)
        add_stopwatch(tm, 3)
        assert (tm.tasks[0].pos, tm.events[0].pos, tm.durations[0].pos) == (0, 0, 0)

    def test_new_card_after_reorder_lands_last(self, tm):
        for i in (1, 2, 3):
            add_task(tm, i)
        reorder(tm, "task", [3, 1, 2])
        add_task(tm, 4)
        assert ids(tm.get_ApiState(), "tasks") == [3, 1, 2, 4]

    def test_append_still_works_after_deleting_the_last_card(self, tm):
        for i in (1, 2, 3):
            add_task(tm, i)
        tm.process_command(Message(command="delete", type="task", id=3))
        add_task(tm, 4)
        assert ids(tm.get_ApiState(), "tasks") == [1, 2, 4]
        tm.process_command(Message(command="delete", type="task", id=1))
        add_task(tm, 5)
        assert ids(tm.get_ApiState(), "tasks") == [2, 4, 5]


class TestReorder:
    def test_reorder_tasks(self, tm):
        for i in (1, 2, 3):
            add_task(tm, i)
        reorder(tm, "task", [2, 3, 1])
        assert ids(tm.get_ApiState(), "tasks") == [2, 3, 1]

    def test_reorder_mixed_stopwatches_and_timers(self, tm):
        add_stopwatch(tm, 1)
        add_timer(tm, 2)
        add_stopwatch(tm, 3)
        add_timer(tm, 4)
        reorder(tm, "duration", [4, 1, 3, 2])
        assert ids(tm.get_ApiState(), "durations") == [4, 1, 3, 2]

    def test_in_memory_lists_stay_sorted_by_id(self, tm):
        # sorted_find_index binary-searches on id; display order must not leak into it.
        for i in (1, 2, 3):
            add_task(tm, i)
        reorder(tm, "task", [3, 2, 1])
        assert [t.id for t in tm.tasks] == [1, 2, 3]
        # ...and commands that look cards up by id still work afterwards.
        tm.process_command(Message(command="complete", type="task", id=2))
        assert tm.tasks[1].completed is True

    def test_order_survives_restart(self, tm):
        for i in (1, 2, 3):
            add_task(tm, i)
        add_stopwatch(tm, 4)
        add_timer(tm, 5)
        reorder(tm, "task", [3, 1, 2])
        reorder(tm, "duration", [5, 4])
        state = restart(tm).get_ApiState()
        assert ids(state, "tasks") == [3, 1, 2]
        assert ids(state, "durations") == [5, 4]

    def test_new_card_after_restart_lands_last(self, tm):
        for i in (1, 2, 3):
            add_task(tm, i)
        reorder(tm, "task", [3, 1, 2])
        fresh = restart(tm)
        add_task(fresh, 4)
        assert ids(fresh.get_ApiState(), "tasks") == [3, 1, 2, 4]

    def test_delete_then_reorder(self, tm):
        for i in (1, 2, 3, 4):
            add_task(tm, i)
        tm.process_command(Message(command="delete", type="task", id=2))
        reorder(tm, "task", [4, 3, 1])
        assert ids(tm.get_ApiState(), "tasks") == [4, 3, 1]
        assert ids(restart(tm).get_ApiState(), "tasks") == [4, 3, 1]

    def test_stale_id_is_skipped(self, tm):
        # The card was deleted between the drag starting and the request arriving.
        for i in (1, 2, 3):
            add_task(tm, i)
        tm.process_command(Message(command="delete", type="task", id=2))
        reorder(tm, "task", [3, 2, 1])
        assert ids(tm.get_ApiState(), "tasks") == [3, 1]

    def test_card_the_client_did_not_know_keeps_its_place_after_listed_ones(self, tm):
        for i in (1, 2, 3):
            add_task(tm, i)
        reorder(tm, "task", [2, 1])  # 3 was created "meanwhile"
        assert ids(tm.get_ApiState(), "tasks") == [2, 1, 3]
        assert sorted(t.pos for t in tm.tasks) == [0, 1, 2]  # still gap-free

    def test_reorder_is_idempotent(self, tm):
        for i in (1, 2, 3):
            add_task(tm, i)
        reorder(tm, "task", [3, 2, 1])
        reorder(tm, "task", [3, 2, 1])
        assert ids(tm.get_ApiState(), "tasks") == [3, 2, 1]

    def test_reordering_one_kind_leaves_the_other_alone(self, tm):
        add_task(tm, 1)
        add_task(tm, 2)
        add_stopwatch(tm, 3)
        add_timer(tm, 4)
        reorder(tm, "task", [2, 1])
        assert ids(tm.get_ApiState(), "durations") == [3, 4]


class TestMalformedReorder:
    @pytest.fixture
    def board(self, tm):
        for i in (1, 2, 3):
            add_task(tm, i)
        add_stopwatch(tm, 4)
        return tm

    def snapshot(self, tm):
        return (ids(tm.get_ApiState(), "tasks"), [t.pos for t in tm.tasks])

    @pytest.mark.parametrize("type,order", [
        ("task", None),          # no list at all
        ("task", [1, 1, 2]),     # duplicate id
        ("task", [3, 4]),        # 4 is a stopwatch
        ("duration", [4, 1]),    # 1 is a task
        ("event", [1]),          # events are not reorderable
        (None, [1, 2]),          # no type
    ])
    def test_rejected_without_changing_anything(self, board, type, order):
        before = self.snapshot(board)
        with pytest.raises(ValueError):
            reorder(board, type, order)
        assert self.snapshot(board) == before
        assert self.snapshot(restart(board)) == before

    def test_reorder_no_longer_raises_not_implemented(self, board):
        # Regression: before Phase 5 the frontend's `reorder` hit
        # `raise NotImplementedError` and the API returned a 500.
        try:
            reorder(board, "task", [3, 2, 1])
        except NotImplementedError:
            pytest.fail("reorder is still unimplemented")

    def test_database_transaction_is_all_or_nothing(self, board):
        # A statement that fails midway must roll back the ones before it.
        with pytest.raises(Exception):
            board.db.execute_many([
                ("UPDATE tasks SET pos = 50 WHERE id = 1", ()),
                ("UPDATE no_such_table SET pos = 1", ()),
            ])
        assert restart(board).tasks[0].pos == 0
