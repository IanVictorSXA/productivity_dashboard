"""Tests for the sheet reconciliation in `sheets.py` and its `TaskManager` wiring (Phase 3, Groups 5-7, 10).

The Google client is never touched: `sheets.read_day` is replaced with a fake
that returns a parsed column (or a failed read). Each test builds a real
`TaskManager` on a temp database, with `SHEETS_SYNC_ENABLED` left false so the
startup sync is a no-op until the test calls `sheets.sync_day` itself.
"""

import sys

import pytest

import sheets
import sheets_config
from classes import Message, TaskManager
from sheets_parse import SheetRead, parse_column

HEADER = "7am wake up"  # row 1 is never a card


@pytest.fixture
def tm(temp_db_env):
    return TaskManager()


@pytest.fixture
def sheet(monkeypatch, frozen_clock):
    """Return `set_column(*cells)`: what the fake spreadsheet will say, plus a call counter."""
    state = {"read": None, "calls": 0}

    def fake_read_day(worksheet=None):
        state["calls"] += 1
        read = state["read"]
        if isinstance(read, Exception):
            raise read
        return read

    monkeypatch.setattr(sheets, "read_day", fake_read_day)

    def set_column(*cells):
        state["read"] = parse_column([HEADER, *cells])

    def set_read(read):
        state["read"] = read

    set_column.set_read = set_read
    set_column.state = state

    return set_column


def labels(cards):
    return sorted(c.label for c in cards)


def make_local_task(tm, label):
    tm.process_command(Message(command="create", id=tm.db.last_id + 1, type="task",
                               label=label, completed=False))


class TestCreate:
    def test_new_cells_become_cards_marked_as_sheet_owned(self, tm, sheet):
        sheet("check email", "2pm dentist")

        result = sheets.sync_day(tm)

        assert result["status"] == "ok"
        assert labels(tm.tasks) == ["check email"]
        assert labels(tm.events) == ["dentist"]
        assert tm.tasks[0].source == "sheet" and tm.tasks[0].sheet_key == "check email"
        assert tm.events[0].sheet_key == "2pm dentist"

    def test_event_whose_time_has_passed_is_not_created_and_is_counted(self, tm, sheet):
        sheet("9am breakfast", "2pm dentist")  # clock is frozen at 12:00 UTC

        result = sheets.sync_day(tm)

        assert labels(tm.events) == ["dentist"]
        assert result["detail"] == "created 1, deleted 0, past 1, unparsed 0"

    def test_unparseable_cell_is_counted_and_does_not_block_the_rest(self, tm, sheet):
        sheet("1pm", "a task")

        result = sheets.sync_day(tm)

        assert labels(tm.tasks) == ["a task"]
        assert result["detail"].endswith("unparsed 1")

    def test_duplicate_cells_make_one_card(self, tm, sheet):
        sheet("same", "same")

        sheets.sync_day(tm)

        assert labels(tm.tasks) == ["same"]

    def test_created_cards_survive_a_restart(self, tm, sheet):
        sheet("check email", "2pm dentist")
        sheets.sync_day(tm)

        reloaded = TaskManager()

        assert labels(reloaded.tasks) == ["check email"]
        assert labels(reloaded.events) == ["dentist"]
        assert reloaded.tasks[0].source == "sheet"


class TestReconcile:
    def test_rerunning_with_an_unchanged_sheet_changes_nothing(self, tm, sheet):
        sheet("check email", "2pm dentist")
        sheets.sync_day(tm)

        result = sheets.sync_day(tm, force=True)

        assert len(tm.tasks) == 1 and len(tm.events) == 1
        assert result["detail"].startswith("created 0, deleted 0")

    def test_cell_removed_from_the_sheet_deletes_its_card(self, tm, sheet):
        sheet("keep me", "drop me", "2pm dentist")
        sheets.sync_day(tm)

        sheet("keep me")
        result = sheets.sync_day(tm, force=True)

        assert labels(tm.tasks) == ["keep me"]
        assert tm.events == []
        assert result["detail"].startswith("created 0, deleted 2")

    def test_deletion_is_persisted(self, tm, sheet):
        sheet("drop me")
        sheets.sync_day(tm)
        sheet()
        sheets.sync_day(tm, force=True)

        assert TaskManager().tasks == []

    def test_cards_made_by_hand_are_never_deleted(self, tm, sheet):
        make_local_task(tm, "my own task")
        sheet("from sheet")
        sheets.sync_day(tm)

        sheet()  # the sheet now says nothing at all
        sheets.sync_day(tm, force=True)

        assert labels(tm.tasks) == ["my own task"]

    def test_empty_but_successful_read_does_delete_sheet_cards(self, tm, sheet):
        # The contrast with a *failed* read below: "the sheet is empty" is real information.
        sheet("from sheet")
        sheets.sync_day(tm)

        sheet.set_read(SheetRead(ok=True))
        sheets.sync_day(tm, force=True)

        assert tm.tasks == []

    def test_matched_card_is_left_alone(self, tm, sheet):
        sheet("check email")
        sheets.sync_day(tm)
        tm.process_command(Message(command="complete", id=tm.tasks[0].id, type="task", completed=True))

        sheets.sync_day(tm, force=True)

        assert tm.tasks[0].completed is True

    def test_dismissed_event_stays_dismissed(self, tm, sheet):
        sheet("2pm dentist")
        sheets.sync_day(tm)
        tm.process_command(Message(command="ring", id=tm.events[0].id, type="event"))
        tm.process_command(Message(command="stop_ring", id=tm.events[0].id, type="event"))
        assert tm.events[0].completed is True

        sheets.sync_day(tm, force=True)

        assert len(tm.events) == 1 and tm.events[0].completed is True

    def test_deleting_a_sheet_card_locally_does_not_stick(self, tm, sheet):
        # By design (requirements.md): column A still lists it, so the next sync recreates it.
        sheet("a task")
        sheets.sync_day(tm)
        tm.process_command(Message(command="delete", id=tm.tasks[0].id, type="task"))
        assert tm.tasks == []

        sheets.sync_day(tm, force=True)

        assert labels(tm.tasks) == ["a task"]

    def test_cell_that_stops_parsing_keeps_its_card(self, tm, sheet):
        sheet("2pm dentist")
        sheets.sync_day(tm)

        # Same cell text is still in column A, but as far as the parser is concerned it is
        # now unusable: it is in `cells`, not in `items`.
        sheet.set_read(SheetRead(ok=True, cells={"2pm dentist"}, skipped=[(2, "bad")]))
        sheets.sync_day(tm, force=True)

        assert labels(tm.events) == ["dentist"]

    def test_timers_and_stopwatches_are_untouched(self, tm, sheet):
        before = [(d.id, d.label) for d in tm.durations]
        sheet("a task")

        sheets.sync_day(tm)
        sheet()
        sheets.sync_day(tm, force=True)

        assert [(d.id, d.label) for d in tm.durations] == before


class TestFailureNeverTouchesCards:
    FAILED = SheetRead(ok=False, error="SheetsNetworkError: Could not reach Google Sheets")

    def test_failed_read_deletes_nothing_and_reports_error(self, tm, sheet):
        sheet("keep me", "2pm dentist")
        sheets.sync_day(tm)

        sheet.set_read(self.FAILED)
        result = sheets.sync_day(tm, force=True)

        assert result["status"] == "error"
        assert "SheetsNetworkError" in result["detail"]
        assert labels(tm.tasks) == ["keep me"]
        assert labels(tm.events) == ["dentist"]

    def test_failure_is_recorded_but_does_not_mark_the_day_done(self, tm, sheet):
        sheet.set_read(self.FAILED)
        sheets.sync_day(tm)

        assert tm.db.get_sheet_sync(tm.db.get_date())["status"] == "error"

        # Next (non-forced) attempt must retry, not skip.
        sheet("a task")
        result = sheets.sync_day(tm)

        assert result["status"] == "ok"
        assert labels(tm.tasks) == ["a task"]

    def test_unexpected_exception_is_swallowed_and_recorded(self, tm, sheet):
        sheet.set_read(RuntimeError("boom"))

        result = sheets.sync_day(tm)  # must not raise

        assert result["status"] == "error"
        assert "RuntimeError: boom" in result["detail"]
        assert tm.db.get_sheet_sync(tm.db.get_date())["status"] == "error"

    def test_failure_to_record_the_marker_is_swallowed(self, tm, sheet, monkeypatch):
        sheet("a task")

        def broken(*args, **kwargs):
            raise OSError("disk full")

        monkeypatch.setattr(tm.db, "set_sheet_sync", broken)

        assert sheets.sync_day(tm)["status"] == "ok"  # still reports, still created the card
        assert labels(tm.tasks) == ["a task"]


class TestOncePerDayMarker:
    def test_second_automatic_sync_is_skipped_without_reading(self, tm, sheet):
        sheet("a task")
        sheets.sync_day(tm)
        calls = sheet.state["calls"]

        result = sheets.sync_day(tm)

        assert result["status"] == "skipped"
        assert "created 1" in result["detail"]  # carries the earlier run's counts
        assert sheet.state["calls"] == calls

    def test_force_bypasses_the_marker(self, tm, sheet):
        sheet("a task")
        sheets.sync_day(tm)
        calls = sheet.state["calls"]

        sheets.sync_day(tm, force=True)

        assert sheet.state["calls"] == calls + 1


class TestTaskManagerWiring:
    def test_disabled_by_default_and_reported_on_the_api(self, tm):
        assert sheets_config.SHEETS_SYNC_ENABLED is False
        assert tm.sheet_sync["status"] == "disabled"
        assert tm.get_ApiState()["sheet_sync"]["status"] == "disabled"

    @pytest.fixture
    def enabled(self, monkeypatch):
        monkeypatch.setattr(sheets_config, "SHEETS_SYNC_ENABLED", True)

    def test_startup_sync_runs_when_enabled(self, temp_db_env, enabled, sheet):
        sheet("a task")

        started = TaskManager()

        assert started.sheet_sync["status"] == "ok"
        assert labels(started.tasks) == ["a task"]

    def test_sync_button_command_forces_a_resync(self, tm, enabled, sheet):
        sheet("a task")
        tm.sync_sheets()
        sheet("a task", "another")

        tm.process_command(Message(command="sync_sheets"))

        assert tm.sheet_sync["status"] == "ok"
        assert labels(tm.tasks) == ["a task", "another"]
        assert tm.get_ApiState()["sheet_sync"] == tm.sheet_sync

    def test_missing_google_libraries_do_not_stop_the_dashboard(self, tm, enabled, monkeypatch):
        monkeypatch.setitem(sys.modules, "sheets", None)  # makes `import sheets` raise ImportError

        result = tm.sync_sheets()

        assert result["status"] == "error"
        assert "ModuleNotFoundError" in result["detail"]


class TestReset:
    def test_reset_clears_cards_keeps_default_stopwatches_and_restores_sheet_cards(
            self, tm, sheet, monkeypatch):
        monkeypatch.setattr(sheets_config, "SHEETS_SYNC_ENABLED", True)
        sheet("from sheet")
        tm.sync_sheets()
        make_local_task(tm, "local task")
        defaults = sorted(d.label for d in tm.durations if d.type_duration == "stopwatch")

        tm.process_command(Message(command="reset"))

        assert labels(tm.tasks) == ["from sheet"]  # local gone, sheet one re-imported
        assert sorted(d.label for d in tm.durations if d.type_duration == "stopwatch") == defaults
